#!/usr/bin/env python3
"""High-speed routing library for the bay-station board (KiCad 10 pcbnew).

These are scripted PRIMITIVES, not an autorouter: the caller (a layout script
or the CLI below) names the pads/waypoints; this module lays copper at the
right width with 45 degree or arc bends, fences it with GND vias, adds
length-matching meanders and locks the result.  Run with KiCad's python.

  microstrip_path()   polyline -> tracks, corners chamfered (45) or arced
  route_pads()        pad -> pad with an L (or given waypoints), DW3210 neck-down
  via_fence()         GND vias both sides of a polyline, pitch < lambda_g/10
  meander()           insert a serpentine into a straight leg to add length
  match_group()       route a set of paths and meander the short ones
  lock()              lock tracks/vias so the Manhattan router treats them as fixed

Numbers (all derived in stackup.py / docs/routing-plan.md):
  RF/CLK line  w = 0.45 mm  (50 ohm microstrip over In1, h = 0.254, er 4.5)
  DW3210 pad neck 0.24 mm (pad is 0.25 mm on a 0.4 mm pitch: any wider
      touches the GND pad neighbours at the 0.15 mm clearance)
  fence: via 0.45/0.20, centre offset 0.96 mm from the line, pitch 1.5 mm
      (lambda_g at 6.4896 GHz = 25.0 mm -> lambda/10 = 2.5 mm)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U
import stackup as S

RF_W = 0.45
NECK_W = 0.24
NECK_EXTRA = 0.32         # keep the neck this far past the end of the DW3210 pad
FENCE_VIA = (0.45, 0.20)
FENCE_OFFSET = 0.96       # 0.45/2 + 0.5 (RF50 keep-off in .kicad_dru) + 0.45/2 + 0.01
FENCE_PITCH = 1.5
CLEAR_DEFAULT = 0.15
_DEBUG_NORAISE = bool(os.environ.get("HS_NORAISE"))   # debugging: keep the untuned copper instead of raising
BEND_R = 1.0             # arc radius for bend='arc'


def fence_pitch_ok(pitch=FENCE_PITCH):
    lam, lam10 = S.fence_pitch_mm(divisor=10)
    return pitch < lam10, lam, lam10


# ------------------------------------------------------------------ geometry
def _unit(ax, ay, bx, by):
    d = math.hypot(bx - ax, by - ay)
    return ((bx - ax) / d, (by - ay) / d, d) if d > 0 else (0, 0, 0)


def bend_points(pts, style="chamfer", cut=None, radius=BEND_R):
    """Expand a polyline into a list of primitives:
         ('L', p, q)            straight
         ('A', p, mid, q)       arc
    Corners with a turn of <= ~1 degree are left alone.  chamfer: cut each corner
    at 45 degrees (for a 90 degree turn two 45 degree turns); the cut distance
    along each leg is `cut` (default 0.6 mm, limited to 40 % of the leg)."""
    cut = 0.6 if cut is None else cut
    pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
    n = len(pts)
    out = []
    cur = pts[0]
    for i in range(1, n - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        u1x, u1y, d1 = _unit(*p0, *p1)
        u2x, u2y, d2 = _unit(*p1, *p2)
        cosang = u1x * u2x + u1y * u2y
        turn = math.acos(max(-1.0, min(1.0, cosang)))
        if turn < math.radians(1.0):
            out.append(("L", cur, p1)); cur = p1
            continue
        if style == "arc":
            t = radius * math.tan(turn / 2)
            t = min(t, 0.45 * d1, 0.45 * d2)
            r_eff = t / math.tan(turn / 2)
            a = (p1[0] - u1x * t, p1[1] - u1y * t)
            b = (p1[0] + u2x * t, p1[1] + u2y * t)
            # arc midpoint: from the centre toward the corner
            bis = (u2x - u1x, u2y - u1y)
            bl = math.hypot(*bis)
            bis = (bis[0] / bl, bis[1] / bl)
            cdist = r_eff / math.cos(turn / 2)
            centre = (p1[0] + bis[0] * cdist, p1[1] + bis[1] * cdist)
            mid = (centre[0] - bis[0] * r_eff, centre[1] - bis[1] * r_eff)
            out.append(("L", cur, a))
            out.append(("A", a, mid, b))
            cur = b
        else:
            c = min(cut, 0.4 * d1, 0.4 * d2)
            a = (p1[0] - u1x * c, p1[1] - u1y * c)
            b = (p1[0] + u2x * c, p1[1] + u2y * c)
            out.append(("L", cur, a)); out.append(("L", a, b))
            cur = b
    out.append(("L", cur, pts[-1]))
    return [p for p in out if not (p[0] == "L" and math.dist(p[1], p[2]) < 1e-6)]


def prim_length(prims):
    tot = 0.0
    for p in prims:
        if p[0] == "L":
            tot += math.dist(p[1], p[2])
        else:
            a, m, b = p[1], p[2], p[3]
            # circumcircle arc length
            ax, ay = a; mx, my = m; bx, by = b
            d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
            ux = ((ax**2 + ay**2) * (my - by) + (mx**2 + my**2) * (by - ay) + (bx**2 + by**2) * (ay - my)) / d
            uy = ((ax**2 + ay**2) * (bx - mx) + (mx**2 + my**2) * (ax - bx) + (bx**2 + by**2) * (mx - ax)) / d
            r = math.hypot(ax - ux, ay - uy)
            a1 = math.atan2(ay - uy, ax - ux); a2 = math.atan2(by - uy, bx - ux)
            da = abs(a2 - a1)
            if da > math.pi:
                da = 2 * math.pi - da
            tot += r * da
    return tot


def microstrip_path(board, net, layer, pts, width=RF_W, style="chamfer", cut=None,
                    radius=BEND_R, locked=False):
    """Lay a polyline as tracks/arcs.  Returns (items, length_mm)."""
    prims = bend_points(pts, style, cut, radius)
    items = []
    for p in prims:
        if p[0] == "L":
            items.append(U.add_track(board, net, layer, *p[1], *p[2], width, locked))
        else:
            items.append(U.add_arc(board, net, layer, p[1], p[2], p[3], width, locked))
    return items, prim_length(prims)


# ------------------------------------------------------------------ clearance probe
_PAD_CACHE = {}


def _pads(board):
    """Cached (x0,y0,x1,y1,netcode,layers,(ref,num)) per pad; footprints do not move
    while a routing script runs."""
    key = id(board)
    if key not in _PAD_CACHE:
        lst = []
        for f in board.GetFootprints():
            ref = str(f.GetReference())
            for p in f.Pads():
                bb = p.GetBoundingBox()
                lst.append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()),
                            p.GetNetCode(), tuple(l for l in (U.F_CU, U.B_CU) if p.IsOnLayer(l)),
                            (ref, str(p.GetNumber()))))
        _PAD_CACHE[key] = lst
    return _PAD_CACHE[key]


def seg_clearance_ok(board, net, layer, a, b, width, clearance=CLEAR_DEFAULT, ignore_pads=(),
                     clearance_trk=None):
    """True if a straight track a-b (mm) keeps `clearance` to every foreign-net pad
    (on that layer) and `clearance_trk` (default: same) to foreign tracks/vias.
    Cheap geometric test, not a DRC -- the DRC remains the judge."""
    hw = width / 2
    nid = net.GetNetCode()
    ct_foreign = clearance if clearance_trk is None else clearance_trk
    own_cls = str(net.GetNetClassName())
    lo_x, hi_x = min(a[0], b[0]), max(a[0], b[0])
    lo_y, hi_y = min(a[1], b[1]), max(a[1], b[1])
    L = math.dist(a, b)
    steps = max(2, int(L / 0.05))
    pts = [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps) for i in range(steps + 1)]
    m = hw + clearance
    for (x0, y0, x1, y1, pnet, layers, key) in _pads(board):
        if pnet == nid or layer not in layers or key in ignore_pads:
            continue
        if x1 < lo_x - m or x0 > hi_x + m or y1 < lo_y - m or y0 > hi_y + m:
            continue
        for (x, y) in pts:
            if U.dist_pt_rect(x, y, x0, y0, x1, y1) < m - 1e-6:
                return False
    for t in board.GetTracks():
        if t.GetNetCode() == nid:
            continue
        # the .kicad_dru keep-off exempts same-class neighbours (CLK next to CLK)
        ct = clearance if str(t.GetNetClassName()) == own_cls else ct_foreign
        if t.Type() == pcbnew.PCB_VIA_T:
            r = U.mm(t.GetWidth(U.F_CU)) / 2
            q = t.GetPosition()
            if U.dist_pt_seg(U.mm(q.x), U.mm(q.y), a[0], a[1], b[0], b[1]) < hw + r + ct - 1e-6:
                return False
        elif t.GetLayer() == layer:
            s, e = t.GetStart(), t.GetEnd()
            sx, sy, ex, ey = U.mm(s.x), U.mm(s.y), U.mm(e.x), U.mm(e.y)
            r = U.mm(t.GetWidth()) / 2
            mt = hw + r + ct
            if max(sx, ex) < lo_x - mt or min(sx, ex) > hi_x + mt or max(sy, ey) < lo_y - mt or min(sy, ey) > hi_y + mt:
                continue
            for (x, y) in pts:
                if U.dist_pt_seg(x, y, sx, sy, ex, ey) < mt - 1e-6:
                    return False
    return True


def candidate_paths(ca, cb, span=8.0, step=0.5):
    """Orthogonal candidates ca -> cb, shortest first: straight, two Ls, then Z
    shapes (H-V-H with a swept mid x, V-H-V with a swept mid y)."""
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    out = []
    if abs(dx) < 0.02 or abs(dy) < 0.02:
        out.append((abs(dx) + abs(dy), [ca, cb]))
    out.append((abs(dx) + abs(dy), [ca, (cb[0], ca[1]), cb]))
    out.append((abs(dx) + abs(dy), [ca, (ca[0], cb[1]), cb]))
    xs, ys = sorted((ca[0], cb[0])), sorted((ca[1], cb[1]))
    nx_ = int((xs[1] - xs[0] + 2 * span) / step)
    ny_ = int((ys[1] - ys[0] + 2 * span) / step)
    for k in range(nx_ + 1):
        mx = xs[0] - span + k * step
        out.append((abs(mx - ca[0]) + abs(dy) + abs(cb[0] - mx), [ca, (mx, ca[1]), (mx, cb[1]), cb]))
    for k in range(ny_ + 1):
        my = ys[0] - span + k * step
        out.append((abs(my - ca[1]) + abs(dx) + abs(cb[1] - my), [ca, (ca[0], my), (cb[0], my), cb]))
    # interior Z shapes
    for f in (0.25, 0.5, 0.75):
        mx, my = ca[0] + dx * f, ca[1] + dy * f
        out.append((abs(dx) + abs(dy), [ca, (mx, ca[1]), (mx, cb[1]), cb]))
        out.append((abs(dx) + abs(dy), [ca, (ca[0], my), (cb[0], my), cb]))
    out.sort(key=lambda t: t[0])
    seen, res = set(), []
    for _, pts in out:
        k = tuple((round(x, 3), round(y, 3)) for x, y in pts)
        if k not in seen:
            seen.add(k)
            res.append(pts)
    return res


# ------------------------------------------------------------------ A* fallback
def _keepout_rects(board, layer):
    """Axis-aligned bboxes of rule areas that forbid tracks on `layer` (board and footprint level)."""
    zs = list(board.Zones())
    for f in board.GetFootprints():
        zs += list(f.Zones())
    out = []
    for z in zs:
        if z.GetIsRuleArea() and z.GetDoNotAllowTracks() and z.IsOnLayer(layer):
            bb = z.GetBoundingBox()
            out.append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())))
    return out


class GridCtx:
    """Non-uniform routing grid (0.25 mm lattice + the special rows/columns given) with
    a blocked-node mask for one net/width/layer.  search() is an orthogonal least-bends
    A*.  Obstacles: foreign pads (0.15), foreign tracks/vias (clearance_trk, 0.15 for the
    same class), track-forbidding rule areas, board edge (0.5)."""

    def __init__(self, board, net, layer, width, special_x, special_y, box, ignore_pads=(),
                 step=0.25, clearance_trk=0.5, margin_extra=0.03):
        import bisect
        self.bisect = bisect
        self.hw = hw = width / 2
        self.width = width
        nid = net.GetNetCode()
        x0, y0, x1, y1 = box

        def axis(lo, hi, sp):
            v = {round(s, 4) for s in sp}
            k = math.ceil(lo / step)
            while k * step <= hi:
                v.add(round(k * step, 4)); k += 1
            return sorted(v)
        self.X, self.Y = axis(x0, x1, special_x), axis(y0, y1, special_y)
        self.nx, self.ny = len(self.X), len(self.Y)
        self.blocked = bytearray(self.nx * self.ny)
        m = hw + CLEAR_DEFAULT + margin_extra
        for (px0, py0, px1, py1, pnet, layers, key) in _pads(board):
            if pnet == nid or layer not in layers or key in ignore_pads:
                continue
            self._rrect(self.blocked, px0, py0, px1, py1, m)
        for (kx0, ky0, kx1, ky1) in _keepout_rects(board, layer):
            self._rect(self.blocked, kx0 - hw, ky0 - hw, kx1 + hw, ky1 + hw)
        own_cls = str(net.GetNetClassName())
        for t in board.GetTracks():
            if t.GetNetCode() == nid:
                continue
            ct = CLEAR_DEFAULT if str(t.GetNetClassName()) == own_cls else clearance_trk
            if t.Type() == pcbnew.PCB_VIA_T:
                q = t.GetPosition(); r = U.mm(t.GetWidth(U.F_CU)) / 2
                cx, cy = U.mm(q.x), U.mm(q.y); mm_ = hw + r + ct + margin_extra
                self._rect(self.blocked, cx - mm_, cy - mm_, cx + mm_, cy + mm_)
            elif t.GetLayer() == layer:
                s_, e_ = t.GetStart(), t.GetEnd()
                self._seg(self.blocked, U.mm(s_.x), U.mm(s_.y), U.mm(e_.x), U.mm(e_.y),
                          hw + U.mm(t.GetWidth()) / 2 + ct + margin_extra)
        bo = U.board_outline(board)
        if bo:
            e = 0.5 + hw
            self._rect(self.blocked, -1e9, -1e9, bo[0] + e, 1e9)
            self._rect(self.blocked, bo[2] - e, -1e9, 1e9, 1e9)
            self._rect(self.blocked, -1e9, -1e9, 1e9, bo[1] + e)
            self._rect(self.blocked, -1e9, bo[3] - e, 1e9, 1e9)

    def idx(self, p):
        return self.X.index(round(p[0], 4)), self.Y.index(round(p[1], 4))

    def _rect(self, arr, x0, y0, x1, y1):
        b = self.bisect
        i0, i1 = b.bisect_right(self.X, x0), b.bisect_left(self.X, x1)
        j0, j1 = b.bisect_right(self.Y, y0), b.bisect_left(self.Y, y1)
        for i in range(i0, i1):
            base = i * self.ny
            for j in range(j0, j1):
                arr[base + j] = 1

    def _rrect(self, arr, x0, y0, x1, y1, m):
        """Rectangle inflated by m with ROUND corners (exact point-to-rect distance)."""
        b = self.bisect
        i0, i1 = b.bisect_left(self.X, x0 - m), b.bisect_right(self.X, x1 + m)
        j0, j1 = b.bisect_left(self.Y, y0 - m), b.bisect_right(self.Y, y1 + m)
        for i in range(i0, i1):
            for j in range(j0, j1):
                if U.dist_pt_rect(self.X[i], self.Y[j], x0, y0, x1, y1) < m:
                    arr[i * self.ny + j] = 1

    def _seg(self, arr, ax, ay, bx, by, mt):
        b = self.bisect
        i0, i1 = b.bisect_left(self.X, min(ax, bx) - mt), b.bisect_right(self.X, max(ax, bx) + mt)
        j0, j1 = b.bisect_left(self.Y, min(ay, by) - mt), b.bisect_right(self.Y, max(ay, by) + mt)
        for i in range(i0, i1):
            for j in range(j0, j1):
                if U.dist_pt_seg(self.X[i], self.Y[j], ax, ay, bx, by) < mt:
                    arr[i * self.ny + j] = 1

    def with_polyline(self, pts, margin=0.03):
        """Copy of the blocked mask with an own-net polyline (already 'laid') as obstacle."""
        arr = bytearray(self.blocked)
        for a, b in zip(pts, pts[1:]):
            self._seg(arr, a[0], a[1], b[0], b[1], self.width + CLEAR_DEFAULT + margin)
        return arr

    def search(self, sa, sb, first_dir=None, last_dir=None, bend_cost=1.0, blocked=None, free_ends=True):
        import heapq
        blk = self.blocked if blocked is None else blocked
        X, Y, nx_, ny_ = self.X, self.Y, self.nx, self.ny
        si, sj = self.idx(sa); gi, gj = self.idx(sb)
        if free_ends:
            blk = bytearray(blk)
            blk[si * ny_ + sj] = 0; blk[gi * ny_ + gj] = 0
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        start = (si, sj, -1 if first_dir is None else dirs.index(first_dir))
        best = {start: 0.0}
        prev = {}
        heap = [(abs(X[si] - X[gi]) + abs(Y[sj] - Y[gj]), 0.0, start)]
        found = None
        ld = None if last_dir is None else dirs.index(last_dir)
        while heap:
            f, g, st = heapq.heappop(heap)
            if best.get(st, 1e18) < g - 1e-9:
                continue
            i, j, d = st
            if i == gi and j == gj and (ld is None or d == ld):
                found = st; break
            for nd, (di, dj) in enumerate(dirs):
                if d >= 0 and dirs[d][0] == -di and dirs[d][1] == -dj:
                    continue
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx_ and 0 <= nj < ny_) or blk[ni * ny_ + nj]:
                    continue
                ng = g + abs(X[ni] - X[i]) + abs(Y[nj] - Y[j]) + (bend_cost if d >= 0 and nd != d else 0.0)
                ns = (ni, nj, nd)
                if ng < best.get(ns, 1e18) - 1e-9:
                    best[ns] = ng; prev[ns] = st
                    heapq.heappush(heap, (ng + abs(X[ni] - X[gi]) + abs(Y[nj] - Y[gj]), ng, ns))
        if found is None:
            return None
        pts, st = [], found
        while True:
            pts.append((X[st[0]], Y[st[1]]))
            if st not in prev:
                break
            st = prev[st]
        pts.reverse()
        return simplify_poly(pts)


def simplify_poly(pts):
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[k], pts[k + 1]
        if (abs(b[0] - a[0]) < 1e-9 and abs(c[0] - b[0]) < 1e-9) or (abs(b[1] - a[1]) < 1e-9 and abs(c[1] - b[1]) < 1e-9):
            continue
        out.append(b)
    out.append(pts[-1])
    return out


def astar_waypoints(board, net, layer, sa, sb, width, ignore_pads=(), step=0.25, bend_cost=1.0,
                    clearance_trk=0.5, first_dir=None, last_dir=None, margin_extra=0.03):
    """Orthogonal least-bends path sa -> sb around everything foreign (see GridCtx).
    first_dir / last_dir force the leaving / arriving axis direction (neck pads)."""
    box = (min(sa[0], sb[0]) - 12.0, min(sa[1], sb[1]) - 12.0, max(sa[0], sb[0]) + 12.0, max(sa[1], sb[1]) + 12.0)
    g = GridCtx(board, net, layer, width, [sa[0], sb[0]], [sa[1], sb[1]], box, ignore_pads, step,
                clearance_trk, margin_extra)
    return g.search(sa, sb, first_dir, last_dir, bend_cost)


def detour_waypoints(board, net, layer, sa, sb, width, want_len, ignore_pads=(), step=0.25,
                     clearance_trk=0.5, first_dir=None, last_dir=None, margin_extra=0.08,
                     span=14.0, wstep=1.0, slack=(0.0, 2.5)):
    """Longer orthogonal path sa -> W -> sb through a free lattice point W, chosen so the
    chamfered polyline length lands in [want_len - slack[1], want_len - slack[0]] (the rest is
    left to the meander).  Candidates are ranked by closeness to want_len - slack mid.  The
    second half sees the first as an obstacle, so the path never touches itself.
    Returns (polyline, length) or None."""
    cands = []
    xs = [sa[0], sb[0]]; ys = [sa[1], sb[1]]
    box = (min(sa[0], sb[0]) - span, min(sa[1], sb[1]) - span, max(sa[0], sb[0]) + span, max(sa[1], sb[1]) + span)
    # W candidates on a coarse sub-lattice (multiples of wstep), snapped to the 0.25 lattice
    wx = [round(round(x / wstep) * wstep, 4) for x in [box[0] + k * wstep for k in range(int((box[2] - box[0]) / wstep) + 1)]]
    wy = [round(round(y / wstep) * wstep, 4) for y in [box[1] + k * wstep for k in range(int((box[3] - box[1]) / wstep) + 1)]]
    g = GridCtx(board, net, layer, width, xs, ys, box, ignore_pads, step, clearance_trk, margin_extra)
    tgt = want_len - 0.5 * (slack[0] + slack[1])
    # cheap pre-filter: Manhattan length through W
    scored = []
    for x in wx:
        for y in wy:
            est = abs(sa[0] - x) + abs(sa[1] - y) + abs(sb[0] - x) + abs(sb[1] - y)
            scored.append((abs(est - 0.9 * tgt) , x, y))
    scored.sort()
    tried = 0
    results = []
    for _, x, y in scored[:400]:
        W = (x, y)
        if round(x, 4) not in g.X or round(y, 4) not in g.Y:
            continue
        if g.blocked[g.X.index(round(x, 4)) * g.ny + g.Y.index(round(y, 4))]:
            continue
        p1 = g.search(sa, W, first_dir, None, 1.0)
        if not p1:
            continue
        # trim the last 1 mm of p1 so the way out of W is not walled in by p1 itself
        tp, left = list(p1), 1.0
        while len(tp) >= 2 and left > 0:
            seg = math.dist(tp[-1], tp[-2])
            if seg <= left:
                left -= seg; tp.pop()
            else:
                f = (seg - left) / seg
                tp[-1] = (tp[-2][0] + (tp[-1][0] - tp[-2][0]) * f, tp[-2][1] + (tp[-1][1] - tp[-2][1]) * f)
                break
        arr = g.with_polyline(tp) if len(tp) >= 2 else bytearray(g.blocked)
        dx, dy = p1[-1][0] - p1[-2][0], p1[-1][1] - p1[-2][1]
        d_in = (int(math.copysign(1, dx)), 0) if abs(dx) > abs(dy) else (0, int(math.copysign(1, dy)))
        p2 = g.search(W, sb, d_in, last_dir, 1.0, blocked=arr)
        if not p2:
            continue
        poly = simplify_poly(p1 + p2[1:])
        if not _poly_ok(board, net, layer, poly, width, ignore_pads, clearance_trk, "chamfer"):
            continue
        ln = prim_length(bend_points(poly, "chamfer"))
        tried += 1
        if want_len - slack[1] <= ln <= want_len - slack[0]:
            return poly, ln
        results.append((abs(ln - tgt), poly, ln))
        if tried > 60:
            break
    return None


# ------------------------------------------------------------------ pad routing
def pad_of(board, ref, number):
    for f in board.GetFootprints():
        if str(f.GetReference()) == ref:
            for p in f.Pads():
                if str(p.GetNumber()) == str(number):
                    return f, p
    raise KeyError((ref, number))


def pad_center(p):
    q = p.GetPosition()
    return (U.mm(q.x), U.mm(q.y))


def pad_extent_along(p, direction):
    """Half-length of the pad's bbox along an axis direction (dx,dy)."""
    bb = p.GetBoundingBox()
    return (U.mm(bb.GetWidth()) if abs(direction[0]) > 0.5 else U.mm(bb.GetHeight())) / 2


def _pad_exit(fp, pad, width):
    """For a pad narrower than the line (e.g. DW3210 0.25 mm pads on 0.4 mm pitch):
    (neck_width, exit_dir, neck_end_point).  The neck runs along the pad's long axis,
    away from the footprint centre, to NECK_EXTRA beyond the pad end.  None if the pad
    is wide enough to take the line directly."""
    bb = pad.GetBoundingBox()
    w, h = U.mm(bb.GetWidth()), U.mm(bb.GetHeight())
    d = min(w, h)
    if d >= width - 1e-6:
        return None
    nw = d - 0.01 if d >= 0.21 else d
    c = pad_center(pad)
    fc = fp.GetPosition()
    if w >= h:
        sgn = 1 if c[0] >= U.mm(fc.x) else -1
        ex = (sgn, 0)
        half = w / 2
    else:
        sgn = 1 if c[1] >= U.mm(fc.y) else -1
        ex = (0, sgn)
        half = h / 2
    far = (c[0] + ex[0] * (half + NECK_EXTRA), c[1] + ex[1] * (half + NECK_EXTRA))
    return nw, ex, far


def _poly_ok(board, net, layer, pts, width, ign, trk_clearance, style):
    """Check the polyline AS LAID (corner chamfers move copper toward the inside of a turn)."""
    for p in bend_points(pts, style):
        if p[0] == "L" and not seg_clearance_ok(board, net, layer, p[1], p[2], width, ignore_pads=ign,
                                                clearance_trk=trk_clearance):
            return False
    return True


def route_pads(board, net, pad_a, pad_b, layer=U.F_CU, width=RF_W, waypoints=None,
               style="chamfer", neck_pads=(), locked=False, trk_clearance=0.5):
    """Route pad_a -> pad_b (each a (ref, number)) on `layer`.

    Pads narrower than the line get a neck (see _pad_exit) and the path leaves
    them straight along the pad axis.  Without waypoints, orthogonal candidates
    (straight, L, Z, swept U) are tried shortest-first and the first one that
    clears every foreign pad/track/via (0.15 to pads, trk_clearance to copper)
    is used.  Returns (items, length_mm) measured pad centre to pad centre."""
    fa, pa = pad_of(board, *pad_a)
    fb, pb = pad_of(board, *pad_b)
    ca, cb = pad_center(pa), pad_center(pb)
    ign = {tuple(pad_a), tuple(pad_b)}
    items, total = [], 0.0
    ea, eb = _pad_exit(fa, pa, width), _pad_exit(fb, pb, width)
    sa = ea[2] if ea else ca
    sb = eb[2] if eb else cb
    if waypoints is not None:
        pts = [sa] + [tuple(w) for w in waypoints] + [sb]
    else:
        pts = None
        for o in candidate_paths(sa, sb):
            if ea and math.dist(o[0], o[1]) > 1e-6 and \
                    (o[1][0] - o[0][0]) * ea[1][0] + (o[1][1] - o[0][1]) * ea[1][1] <= 0:
                continue
            if eb and math.dist(o[-1], o[-2]) > 1e-6 and \
                    (o[-2][0] - o[-1][0]) * eb[1][0] + (o[-2][1] - o[-1][1]) * eb[1][1] <= 0:
                continue
            if _poly_ok(board, net, layer, o, width, ign, trk_clearance, style):
                pts = o
                break
        if pts is None:
            fd = tuple(ea[1]) if ea else None
            ld = tuple(-v for v in eb[1]) if eb else None
            for me in (0.0, 0.03, 0.15, 0.3):
                cand = astar_waypoints(board, net, layer, sa, sb, width, ignore_pads=ign,
                                       clearance_trk=trk_clearance, first_dir=fd, last_dir=ld, margin_extra=me)
                if cand and _poly_ok(board, net, layer, cand, width, ign, trk_clearance, style):
                    pts = cand
                    break
        if pts is None:
            raise RuntimeError("no clean orthogonal path between %s and %s" % (pad_a, pad_b))
    if ea:
        items.append(U.add_track(board, net, layer, *ca, *sa, ea[0], locked))
        total += math.dist(ca, sa)
    if eb:
        items.append(U.add_track(board, net, layer, *sb, *cb, eb[0], locked))
        total += math.dist(sb, cb)
    if math.dist(pts[0], pts[-1]) > 1e-6 or len(pts) > 2:
        its, ln = microstrip_path(board, net, layer, pts, width, style, locked=locked)
        items += its
        total += ln
    else:
        pass
    # without necks the path starts/ends at the pad centres themselves
    if not ea:
        pass
    return items, total


# ------------------------------------------------------------------ via fence
def _polyline_pts(items):
    pts = []
    for t in items:
        if t.GetClass() == "PCB_ARC":
            continue
        s, e = t.GetStart(), t.GetEnd()
        pts.append(((U.mm(s.x), U.mm(s.y)), (U.mm(e.x), U.mm(e.y))))
    return pts


def via_fence(board, items, gnd="GND", pitch=FENCE_PITCH, offset=FENCE_OFFSET,
              via=FENCE_VIA, skip_ends=0.3, locked=True, sides=(1, -1), min_pad_clear=CLEAR_DEFAULT):
    """Drop GND vias along both sides of the straight pieces of `items` (tracks;
    arcs are skipped).  A via is skipped when it would violate clearance to a
    foreign pad/track/via (cheap test).  Returns the list of vias placed."""
    assert pitch < S.fence_pitch_mm(divisor=10)[1], "fence pitch must be < lambda/10"
    net = U.get_net(board, gnd)
    placed = []
    r = via[0] / 2
    from stitch import dw3210_cutouts       # no vias under a DW3210 body (DS v1.1 Fig 35)
    cuts = dw3210_cutouts(board)
    for (a, b) in _polyline_pts(items):
        ux, uy, L = _unit(*a, *b)
        if L < 2 * skip_ends:
            continue
        nx, ny = -uy, ux
        n = max(1, int(math.floor((L - 2 * skip_ends) / pitch)))
        step = (L - 2 * skip_ends) / n if n > 0 else 0
        for side in sides:
            for i in range(n + 1):
                d = skip_ends + i * step
                x = a[0] + ux * d + nx * offset * side
                y = a[1] + uy * d + ny * offset * side
                if any(abs(x - cx) < w / 2 + r and abs(y - cy) < h / 2 + r for (cx, cy, w, h) in cuts):
                    continue
                if _via_site_ok(board, net, x, y, via, min_pad_clear):
                    v = U.add_via(board, net, x, y, via[0], via[1], locked)
                    placed.append(v)
    return placed


def _via_site_ok(board, net, x, y, via, clr):
    r = via[0] / 2
    nid = net.GetNetCode()
    for f in board.GetFootprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            if p.GetNetCode() == nid and not p.HasHole():
                # a GND pad: don't land a via ON it (mask/solder wicking), keep copper-to-copper 0
                pass
            x0, y0, x1, y1 = U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())
            need = r + (0.0 if p.GetNetCode() == nid else clr)
            if p.GetNetCode() == nid:
                need = r + 0.25          # no via-in-pad / mask bridge on GND pads either
            if U.dist_pt_rect(x, y, x0, y0, x1, y1) < need - 1e-6:
                return False
            if p.HasHole():
                dr = U.mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                q = p.GetPosition()
                if math.hypot(x - U.mm(q.x), y - U.mm(q.y)) < r + dr + 0.25 - 1e-6:   # hole-to-hole
                    return False
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            rr = U.mm(t.GetWidth(U.F_CU)) / 2
            need = r + rr + (0.25 if True else 0)  # hole-to-hole 0.25 edge to edge on drills
            dr = U.mm(t.GetDrill()) / 2
            if math.hypot(x - U.mm(q.x), y - U.mm(q.y)) < max(r + rr + (0 if t.GetNetCode() == nid else clr),
                                                               via[1] / 2 + dr + 0.25) - 1e-6:
                return False
        else:
            if t.GetNetCode() == nid:
                continue
            s, e = t.GetStart(), t.GetEnd()
            need = r + U.mm(t.GetWidth()) / 2 + (0.5 if str(t.GetNetClassName()) in ("RF50", "CLK") else clr)
            if t.GetLayer() in (U.F_CU, U.B_CU) and U.dist_pt_seg(x, y, U.mm(s.x), U.mm(s.y), U.mm(e.x), U.mm(e.y)) < need - 1e-6:
                return False
    return True


# ------------------------------------------------------------------ meander
def meander_points(a, b, extra, width=RF_W, gap_factor=3.0, amp_max=10.0, amp_min=0.9, side=1):
    """Return a polyline from a to b (straight leg) with a chamfered accordion that
    adds `extra` mm of electrical length (computed on the chamfered polyline).
    Legs are spaced (gap_factor+1)*width centre to centre so adjacent legs stay
    >= gap_factor*width apart (3 x w ~ 3h, limits self-coupling).  Raises if the
    leg is too short for the requested extra length."""
    ux, uy, L = _unit(*a, *b)
    nx, ny = -uy * side, ux * side
    pitch = (gap_factor + 1) * width
    # one bump = up leg + across + down leg; adds 2*amp (minus chamfer savings)
    nb_max = int((L - 2 * pitch) // (2 * pitch))
    if nb_max < 1:
        raise ValueError("leg %.2f mm too short for a meander" % L)

    def build(nb, amp):
        pts = [a]
        x = pitch                       # start 1 pitch in
        for k in range(nb):
            for (dx, h) in ((x, 0.0), (x, amp), (x + pitch, amp), (x + pitch, 0.0)):
                pts.append((a[0] + ux * dx + nx * h, a[1] + uy * dx + ny * h))
            x += 2 * pitch
        pts.append(b)
        return pts

    best = None
    for nb in range(1, nb_max + 1):
        lo, hi = amp_min, amp_max
        # length is monotonic in amp
        def added(amp):
            pts = build(nb, amp)
            return prim_length(bend_points(pts, "chamfer", cut=min(0.45, amp / 2.2, pitch / 2.2))) - L
        if added(hi) < extra:
            continue
        if added(lo) > extra:
            return build(nb, lo)    # shortest meander still longer: caller must accept
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if added(mid) < extra:
                lo = mid
            else:
                hi = mid
        amp = 0.5 * (lo + hi)
        best = (nb, amp)
        break
    if best is None:
        raise ValueError("cannot add %.2f mm on a %.2f mm leg" % (extra, L))
    return build(*best)


# ------------------------------------------------------------------ groups
def lock(items):
    for it in items:
        it.SetLocked(True)


def net_length(board, netnames):
    names = set(netnames)
    tot = 0.0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        if str(t.GetNetname()) in names:
            tot += U.mm(t.GetLength())
    return tot


def meander_capacity(L, width=RF_W, gap_factor=3.0, amp_max=10.0):
    """Upper bound on the extra length a meander can add on a straight leg of length L."""
    pitch = (gap_factor + 1) * width
    nb = int((L - 2 * pitch) // (2 * pitch))
    return max(0.0, nb * 2 * (amp_max - 0.5))


def _try_meander(board, net, layer, trk, extra, pa, pb, style):
    """Replace straight track `trk` by a meandered polyline adding ~extra mm.
    Tries both sides of the leg; the meander is built on a chamfer-length model, so
    with arcs (or any style) the length actually placed is measured and the request
    corrected, up to 4 rounds.  Returns (new_items, added_len) or None."""
    s, e = trk.GetStart(), trk.GetEnd()
    a, b = (U.mm(s.x), U.mm(s.y)), (U.mm(e.x), U.mm(e.y))
    w = U.mm(trk.GetWidth())
    old_len = U.mm(trk.GetLength())
    board.Remove(trk)
    try:
        for side, amp_max in [(sd, am) for am in (10.0, 6.0, 4.0, 2.5, 1.6) for sd in (1, -1)]:
            want = extra
            for _round in range(4):
                try:
                    cand = meander_points(a, b, want, w, side=side, amp_max=amp_max)
                except ValueError:
                    break
                if not all(seg_clearance_ok(board, net, layer, cand[i], cand[i + 1], w,
                                            ignore_pads={tuple(pa), tuple(pb)}, clearance_trk=0.5)
                           for i in range(len(cand) - 1)):
                    break
                new, ln = microstrip_path(board, net, layer, cand, w, style, cut=0.45)
                added = ln - old_len
                if abs(added - extra) <= 0.1 or _round == 3:
                    return new, added
                for it in new:
                    board.Remove(it)
                want += extra - added
        board.Add(trk)
        return None
    except Exception:
        board.Add(trk)
        raise


def _detour_hop(board, r, hi, extra, layer, width, style):
    """Replace hop `hi` of path record r by a longer route through a free waypoint that
    adds about `extra` mm (the meander finishes the job).  Leaves r untouched on failure."""
    its, netname, pa, pb = r["hop_info"][hi]
    net = U.get_net(board, netname)
    fa, ppa = pad_of(board, *pa)
    fb, ppb = pad_of(board, *pb)
    ea, eb = _pad_exit(fa, ppa, width), _pad_exit(fb, ppb, width)
    ca, cb = pad_center(ppa), pad_center(ppb)
    sa = ea[2] if ea else ca
    sb = eb[2] if eb else cb
    neck = (math.dist(ca, sa) if ea else 0.0) + (math.dist(sb, cb) if eb else 0.0)
    old = sum(U.mm(t.GetLength()) for t in its)
    for t in its:
        board.Remove(t)
    got = detour_waypoints(board, net, layer, sa, sb, width, old + extra - neck,
                           ignore_pads={tuple(pa), tuple(pb)},
                           first_dir=tuple(ea[1]) if ea else None,
                           last_dir=tuple(-v for v in eb[1]) if eb else None)
    if got:
        poly, _ = got
        new, ln = route_pads(board, net, pa, pb, layer=layer, width=width, waypoints=poly[1:-1], style=style)
        r["items"] = [i for i in r["items"] if i not in its] + new
        its[:] = new
        r["length"] += ln - old
        return True
    for t in its:
        board.Add(t)
    return False


def match_group(board, group, layer=U.F_CU, width=RF_W, tol_mm=0.5, style="chamfer"):
    """Route + length-match a set of paths on one layer.

    group = {name: {"hops": [(netname, pad_a, pad_b, kw), ...], "tune_hop": i}}
    Each path is routed with route_pads (kw passes through).  The longest path sets
    the target; every shorter path gets meanders on its straight legs (longest leg
    of the tune hop first, then the others) until it is within tol_mm.  Greedy and
    placement dependent: raises if a meander does not fit or the final spread
    exceeds tol_mm.  Returns {name: {"length", "items"}, "_spread_mm": x}."""
    def reach(spec):
        tot = 0.0
        for (_, pa, pb, _) in spec["hops"]:
            ca, cb = pad_center(pad_of(board, *pa)[1]), pad_center(pad_of(board, *pb)[1])
            tot += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1])
        return tot

    res = {}
    # longest manhattan reach first: long runs take the outside lane, short ones nest
    for name, spec in sorted(group.items(), key=lambda kv: -reach(kv[1])):
        items_all, tot, hop_info = [], 0.0, []
        for (netname, pa, pb, kw) in spec["hops"]:
            net = U.get_net(board, netname)
            its, ln = route_pads(board, net, pa, pb, layer=layer, width=width, style=style, **kw)
            items_all += its
            tot += ln
            hop_info.append((its, netname, pa, pb))
        res[name] = {"items": items_all, "length": tot, "hop_info": hop_info}
    target = max(r["length"] for r in res.values())
    print("pre-tune lengths:", {k: round(v["length"], 2) for k, v in res.items()}, file=sys.stderr)
    for name, spec in group.items():
        r = res[name]
        extra = target - r["length"]
        if extra > 2.0:
            _detour_hop(board, r, spec["tune_hop"], extra, layer, width, style)
            extra = target - r["length"]
        order = [spec["tune_hop"]] + [i for i in range(len(r["hop_info"])) if i != spec["tune_hop"]]
        for hi in order:
            if extra <= 0.05:
                break
            its, netname, pa, pb = r["hop_info"][hi]
            net = U.get_net(board, netname)
            legs = sorted([t for t in its if t.GetClass() != "PCB_ARC" and abs(U.mm(t.GetWidth()) - width) < 1e-6],
                          key=lambda t: -U.mm(t.GetLength()))
            for trk in legs:
                if extra <= 0.05:
                    break
                cap = meander_capacity(U.mm(trk.GetLength()))
                if cap < 1.0:
                    continue
                for frac in (1.0, 0.7, 0.5, 0.35, 0.25, 0.15):
                    want = min(extra, cap) * frac
                    if want < 0.3:
                        break
                    got = _try_meander(board, net, layer, trk, want, pa, pb, style)
                    if got is not None:
                        break
                if got is None:
                    continue
                new, added = got
                r["items"] = [i for i in r["items"] if i is not trk] + new
                its[:] = [i for i in its if i is not trk] + new
                r["length"] += added
                extra -= added
        if extra > tol_mm and not _DEBUG_NORAISE:
            raise RuntimeError("path %s still %.2f mm short of the group target after meandering" % (name, extra))
    lens = [r["length"] for r in res.values()]
    res["_spread_mm"] = max(lens) - min(lens)
    if res["_spread_mm"] > tol_mm and not _DEBUG_NORAISE:
        raise RuntimeError("group spread %.3f mm exceeds tolerance %.3f" % (res["_spread_mm"], tol_mm))
    return res
