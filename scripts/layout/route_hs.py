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
BEND_R = 1.0              # arc radius for bend='arc'


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
            r = U.mm(t.GetWidth()) / 2
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
            if all(seg_clearance_ok(board, net, layer, o[i], o[i + 1], width, ignore_pads=ign,
                                    clearance_trk=trk_clearance) for i in range(len(o) - 1)):
                pts = o
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
            rr = U.mm(t.GetWidth()) / 2
            need = r + rr + (0.25 if True else 0)  # hole-to-hole 0.25 edge to edge on drills
            dr = U.mm(t.GetDrill()) / 2
            if math.hypot(x - U.mm(q.x), y - U.mm(q.y)) < max(r + rr + (0 if t.GetNetCode() == nid else clr),
                                                               via[1] / 2 + dr + 0.25) - 1e-6:
                return False
        else:
            if t.GetNetCode() == nid:
                continue
            s, e = t.GetStart(), t.GetEnd()
            need = r + U.mm(t.GetWidth()) / 2 + clr
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
    Tries both sides of the leg; returns (new_items, added_len) or None."""
    s, e = trk.GetStart(), trk.GetEnd()
    a, b = (U.mm(s.x), U.mm(s.y)), (U.mm(e.x), U.mm(e.y))
    w = U.mm(trk.GetWidth())
    old_len = U.mm(trk.GetLength())
    for side in (1, -1):
        try:
            cand = meander_points(a, b, extra, w, side=side)
        except ValueError:
            return None
        # the leg itself is the track being replaced: remove it for the probe
        board.Remove(trk)
        ok = all(seg_clearance_ok(board, net, layer, cand[i], cand[i + 1], w,
                                  ignore_pads={tuple(pa), tuple(pb)}, clearance_trk=0.5)
                 for i in range(len(cand) - 1))
        if ok:
            new, ln = microstrip_path(board, net, layer, cand, w, style, cut=0.45)
            return new, ln - old_len
        board.Add(trk)
    return None


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
    for name, spec in group.items():
        r = res[name]
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
                want = min(extra, cap)
                got = _try_meander(board, net, layer, trk, want, pa, pb, style)
                if got is None and want > 4.0:
                    got = _try_meander(board, net, layer, trk, want * 0.5, pa, pb, style)
                if got is None:
                    continue
                new, added = got
                r["items"] = [i for i in r["items"] if i is not trk] + new
                its[:] = [i for i in its if i is not trk] + new
                r["length"] += added
                extra -= added
        if extra > tol_mm:
            raise RuntimeError("path %s still %.2f mm short of the group target after meandering" % (name, extra))
    lens = [r["length"] for r in res.values()]
    res["_spread_mm"] = max(lens) - min(lens)
    if res["_spread_mm"] > tol_mm:
        raise RuntimeError("group spread %.3f mm exceeds tolerance %.3f" % (res["_spread_mm"], tol_mm))
    return res
