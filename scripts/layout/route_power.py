#!/usr/bin/env python3
"""Stage 5: hand-first routing of the POWER STAGES and power distribution of the bay-station
board (KiCad's python).  Run it on a SCRATCH copy of the placed board:

    KP scripts/layout/route_power.py --board SCRATCH/bay-station.kicad_pcb [--out X] [--report r.json]
                                     [--no-save] [--only u8,u40,...] [--skip-zones]

What it does, in this order (all deterministic; KIIDs seeded; a second run on its own output is a no-op
because every item it creates is tagged by a fixed name and removed before it is rebuilt):

  0. strips the copper and zones of a previous run of itself (marker: net-independent, track/via/zone
     UUIDs are not used; instead every track/via it makes is remembered in the `.power_items` side
     list written next to the board) -- see `strip_previous`.
  1. PLACEMENT TWEAK (only power-stage passives; ICs, connectors and everything else stay put): each
     part of a power loop is moved to the legal spot (courtyard gap >= 0.6 mm to every other part,
     outside keep-outs, inside the board) that minimises the distance from its loop pad to the IC pin
     it serves.  Every move is reported.
  2. HOT LOOPS first, by explicit geometry on F.Cu over In1 (h = 0.254 mm): input cap -> VIN, switch
     node -> inductor (short, 0.8-1.0 mm wide, 45 degree corners), output cap, feedback divider on
     its own short quiet track, and >= 2 ground vias (0.45/0.20) at every power-ground pad.
  3. DISTRIBUTION: +VSYS, +3V3, +VBAT_LTE, +5V_IN ... by a small A* on a 0.25 mm grid (45 degree
     moves, chamfered corners, class widths, via PAIRS at layer transitions), growing each net as a
     tree from its source; keep-off corridors reserved around the RF50/CLK nets of stage 4.
  4. writes `power_nets.json` (nets routed / pads left) and the loop table (area, inductance).

The Manhattan router skips the nets in power_nets.json["routed_nets"].  Documentation, formulas,
assumptions and the results table: docs/power-layout.md.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew                      # noqa: E402
import pcbutil as U                # noqa: E402
import stackup as SK               # noqa: E402
from mh_model import Model, Prim   # noqa: E402

SEED = 0x50575231
GAP_COURTYARD = 0.30               # per part, >= 0.6 mm between courtyards (place_bay_station.GAP)
CLR = 0.15
VIA_D, VIA_DR = 0.45, 0.20         # GND / small vias
VIAP_D, VIAP_DR = 0.8, 0.4         # POWER_HI via (netclass)
H = SK.H_F_IN1                     # 0.254 mm F.Cu -> In1
ER = SK.ER_FILE
MU0 = 4e-7 * math.pi
RHO_CU = 1.72e-5                   # ohm*mm at 20 C
T_CU = SK.T_CU
SIDE_FILE = ".power_items.json"    # created next to the board: names of items made by this script
F, B = 0, 1                         # model layer indices
LAYERS = {F: U.F_CU, B: U.B_CU}


def d2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# =============================================================================== power builder
class PB:
    """Board + obstacle model + helpers that only create legal copper."""

    def __init__(self, board, pitch=0.25):
        self.b = board
        self.grp = pcbnew.PCB_GROUP(board)
        self.grp.SetName(GROUP_NAME)
        self.m = Model(board, pitch)
        self.name2idx = {v["name"]: k for k, v in self.m.nets.items()}
        self.items = []                 # (kind, name, tag) of everything created
        self.legs = {}                  # tag -> list of dict(kind, ...)
        self.failures = []
        self.necked = []
        self.nvia = 0
        self.ntrack = 0
        self.vias = []                  # (x, y, net)
        poly = self.m.poly
        self.outline = poly
        # keep-out rule areas that forbid vias
        self.novia = []
        for z in list(board.Zones()):
            if z.GetIsRuleArea() and z.GetDoNotAllowVias():
                bb = z.GetBoundingBox()
                self.novia.append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())))
        # keep-out rule areas (also those inside footprints): tracks keep 0.1 mm off their outline
        for z in list(board.Zones()) + [z for f in board.GetFootprints() for z in f.Zones()]:
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                bb = z.GetBoundingBox()
                self.m._add_static(Prim("rect", (U.mm(bb.GetLeft()) - 0.1, U.mm(bb.GetTop()) - 0.1, U.mm(bb.GetRight()) + 0.1,
                                                 U.mm(bb.GetBottom()) + 0.1), (F, B), 0, 0.0))
        self.reserve_corridors()

    def _t(self, nobj, layer, x0, y0, x1, y1, w):
        t = U.add_track(self.b, nobj, layer, x0, y0, x1, y1, w)
        self.grp.AddItem(t)
        return t

    def _v(self, nobj, x, y, d, drill):
        v = U.add_via(self.b, nobj, x, y, d, drill)
        self.grp.AddItem(v)
        return v

    # ------------------------------------------------------------- netlist helpers
    def net(self, name):
        return self.name2idx[name]

    def fp(self, ref):
        f = self.b.FindFootprintByReference(ref)
        if f is None:
            raise KeyError(ref)
        return f

    def pad(self, ref, num):
        for p in self.fp(ref).Pads():
            if p.GetNumber() == str(num):
                q = p.GetPosition()
                bb = p.GetBoundingBox()
                return dict(x=U.mm(q.x), y=U.mm(q.y), w=U.mm(bb.GetWidth()), h=U.mm(bb.GetHeight()),
                            net=p.GetNetname(), pad=p, ref=ref, num=str(num))
        raise KeyError((ref, num))

    def pads_of_net(self, netname):
        out = []
        for f in self.b.GetFootprints():
            for p in f.Pads():
                if p.GetNetname() == netname:
                    q = p.GetPosition()
                    if U.point_in_poly(U.mm(q.x), U.mm(q.y), self.outline):
                        bb = p.GetBoundingBox()
                        out.append(dict(x=U.mm(q.x), y=U.mm(q.y), w=U.mm(bb.GetWidth()), h=U.mm(bb.GetHeight()),
                                        net=netname, ref=f.GetReference(), num=str(p.GetNumber()),
                                        smd=not p.HasHole(), lays=tuple(l for l, kl in ((F, U.F_CU), (B, U.B_CU)) if p.IsOnLayer(kl))))
        return out

    # ------------------------------------------------------------- RF/CLK corridors (stage 4 not routed yet)
    def reserve_corridors(self):
        """Virtual keep-off: for every RF50/CLK net that has no copper yet, the MST of its pad centres
        is blocked on F.Cu for 0.225 + CORRIDOR (default 1.0) mm, plus vias on every layer."""
        self.corridor_nets = []
        routed = set()
        for t in self.b.GetTracks():
            routed.add(t.GetNetname())
        cls = {v["name"]: v["cls"] for v in self.m.nets.values()}
        for name, c in sorted(cls.items()):
            if c not in ("RF50", "CLK") or name in routed:
                continue
            pads = [p for p in self.pads_of_net(name)]
            if len(pads) < 2:
                continue
            pts = [(p["x"], p["y"]) for p in pads]
            inT = {0}
            while len(inT) < len(pts):
                best = None
                for i in inT:
                    for j in range(len(pts)):
                        if j not in inT:
                            dd = d2(pts[i], pts[j])
                            if best is None or dd < best[0]:
                                best = (dd, i, j)
                inT.add(best[2])
                a, c2 = pts[best[1]], pts[best[2]]
                Lc = d2(a, c2)
                if Lc > 2 * CORRIDOR_END + 0.5:      # pads themselves are real copper; the estimate is for the middle only
                    ux, uy = (c2[0] - a[0]) / Lc, (c2[1] - a[1]) / Lc
                    a, c2 = (a[0] + ux * CORRIDOR_END, a[1] + uy * CORRIDOR_END), (c2[0] - ux * CORRIDOR_END, c2[1] - uy * CORRIDOR_END)
                    self.m._add_static(Prim("seg", (a[0], a[1], c2[0], c2[1], 0.225), (F,), CORR_NET, CORRIDOR_CLR))
            self.corridor_nets.append(name)

    # ------------------------------------------------------------- legality
    def seg_ok(self, net, layer, a, b, w, ignore=()):
        return self.m.obst.seg_ok(net, layer, a[0], a[1], b[0], b[1], w / 2, ignore=ignore)

    def via_ok(self, net, x, y, d, drill, ignore_nets=()):
        r = d / 2
        for rect in self.novia:
            if rect[0] - r < x < rect[2] + r and rect[1] - r < y < rect[3] + r:
                return False
        if not U.point_in_poly(x, y, self.outline):
            return False
        bb = (x - r - 1.0, y - r - 1.0, x + r + 1.0, y + r + 1.0)
        for p in self.m.obst.near(bb):
            if p.net == net and net != 0:
                continue
            # a drill prim has net 0 and clr HOLE_CLR; copper prims of other nets need their clr
            if p.dist_pt(x, y) < r + p.clr - 0.001:
                return False
        return True

    # ------------------------------------------------------------- copper creation
    def _reg_seg(self, net, layer, a, b, w):
        self.m._add_static(Prim("seg", (a[0], a[1], b[0], b[1], w / 2), (layer,), net, CLR))

    def track(self, netname, pts, w, tag, layer=F, check=True, chamfer=0.0):
        """Polyline of tracks.  Returns True when every segment is legal and was added."""
        net = self.net(netname)
        if chamfer:
            pts = chamfer_poly(pts, chamfer)
        pts = dedupe(pts)
        if len(pts) < 2:
            return True
        if check:
            for a, b in zip(pts, pts[1:]):
                if not self.seg_ok(net, layer, a, b, w):
                    self.failures.append("track %s %s %s->%s w%.2f blocked" % (tag, netname, fmt(a), fmt(b), w))
                    return False
        nobj = self.b.FindNet(netname)
        for a, b in zip(pts, pts[1:]):
            self._t(nobj, LAYERS[layer], a[0], a[1], b[0], b[1], w)
            self._reg_seg(net, layer, a, b, w)
            self.items.append(("track", netname, tag))
            self.ntrack += 1
            self.legs.setdefault(tag, []).append(dict(kind="trace", w=w, l=d2(a, b), net=netname, a=a, b=b, layer=layer))
        return True

    def via(self, netname, x, y, tag, d=VIA_D, drill=VIA_DR, check=True):
        net = self.net(netname)
        if check and not self.via_ok(net, x, y, d, drill):
            return False
        nobj = self.b.FindNet(netname)
        self._v(nobj, x, y, d, drill)
        self.m._add_static(Prim("circ", (x, y, d / 2), (F, B), net, CLR))
        self.m._add_static(Prim("circ", (x, y, drill / 2), (F, B), 0, U.mm(0) + 0.25))
        self.items.append(("via", netname, tag))
        self.nvia += 1
        self.vias.append((x, y, net))
        self.legs.setdefault(tag, []).append(dict(kind="via", x=x, y=y, net=netname))
        return True

    def ground_pad(self, ref, num, tag, n=2, maxd=1.6, stub_w=0.3, d=VIA_D, drill=VIA_DR, prefer=None,
                   netname="GND", min_sep=0.62):
        """n GND vias around the pad (nearest legal sites first), each tied by a short stub.
        `prefer`: optional (x, y) the sites should lean towards."""
        p = self.pad(ref, num)
        c = (p["x"], p["y"])
        net = self.net(netname)
        cands = []
        step = 0.05
        k = int(maxd / step)
        for ix in range(-k, k + 1):
            for iy in range(-k, k + 1):
                x, y = c[0] + ix * step, c[1] + iy * step
                dd = math.hypot(x - c[0], y - c[1])
                if dd > maxd:
                    continue
                score = dd
                if prefer is not None:
                    score = dd + 0.35 * d2((x, y), prefer)
                cands.append((score, round(x, 3), round(y, 3)))
        cands.sort()
        got = []
        for score, x, y in cands:
            # already tied vias of this pad count (idempotent re-runs never reach here: stripped first)
            if any(d2((x, y), g) < min_sep for g in got):
                continue
            if any(d2((x, y), (vx, vy)) < min_sep and vn == net for vx, vy, vn in self.vias):
                continue
            if not self.via_ok(net, x, y, d, drill):
                continue
            # stub from the pad centre to the via; the stub itself must be legal
            if d2((x, y), c) > 0.02 and not self.seg_ok(net, F, c, (x, y), stub_w):
                continue
            # via must also not cut the pad of another net through the stub path (seg_ok covers that)
            got.append((x, y))
            if len(got) >= n:
                break
        if len(got) < n:
            self.failures.append("ground_pad %s.%s: %d/%d vias" % (ref, num, len(got), n))
        for (x, y) in got:
            if d2((x, y), c) > 0.02:
                nobj = self.b.FindNet(netname)
                self._t(nobj, U.F_CU, c[0], c[1], x, y, stub_w)
                self._reg_seg(net, F, c, (x, y), stub_w)
                self.items.append(("track", netname, tag))
                self.ntrack += 1
                self.legs.setdefault(tag, []).append(dict(kind="trace", w=stub_w, l=d2((x, y), c), net=netname, a=c, b=(x, y), layer=F))
            self.via(netname, x, y, tag, d, drill, check=False)
        return got

    # ------------------------------------------------------------- generic pad-to-pad connect
    def connect(self, netname, a, b, w, tag, chamfer=0.4, layer=F, via_pts=None):
        """Shortest legal straight / L / Z path (45 degree chamfer) between two points; None on failure."""
        net = self.net(netname)
        cands = []
        ax, ay = a
        bx, by = b
        cands.append([a, b])
        cands.append([a, (bx, ay), b])
        cands.append([a, (ax, by), b])
        # 45 degree dogleg: diagonal first, then straight
        dx, dy = bx - ax, by - ay
        m = min(abs(dx), abs(dy))
        sx, sy = (1 if dx >= 0 else -1), (1 if dy >= 0 else -1)
        if m > 1e-6:
            cands.append([a, (ax + sx * m, ay + sy * m), b])
            cands.append([a, (bx - sx * m, by - sy * m), b])
        # Z paths through the middle
        cands.append([a, ((ax + bx) / 2, ay), ((ax + bx) / 2, by), b])
        cands.append([a, (ax, (ay + by) / 2), (bx, (ay + by) / 2), b])
        variants = [(w, None)] + ([(w, 0.3), (w, 0.2)] if w > 0.3 else []) + [(x, None) for x in (0.5, 0.4, 0.3, 0.25, 0.2) if x < w]
        for wide, neck in variants:
            best = None
            for pts in cands:
                pts2 = chamfer_poly(pts, chamfer) if chamfer and len(pts) > 2 else pts
                pts2 = dedupe(pts2)
                segs = neck_segments(pts2, wide, neck)
                if all(self.seg_ok(net, layer, p, q, ww) for p, q, ww in segs):
                    L = sum(d2(p, q) for p, q in zip(pts2, pts2[1:]))
                    if best is None or L < best[0] - 1e-9:
                        best = (L, segs)
            if best is not None:
                for p, q, ww in best[1]:
                    self.track(netname, [p, q], ww, tag, layer=layer, check=False)
                if wide < w or neck:
                    self.necked.append((tag, netname, wide, neck))
                return [s_[0] for s_ in best[1]] + [best[1][-1][1]]
        self.failures.append("connect %s %s %s->%s w%.2f: no legal L/Z" % (tag, netname, fmt(a), fmt(b), w))
        return None

    # ------------------------------------------------------------- placement
    def part_bbox(self, f, inflate=GAP_COURTYARD):
        cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if cy.GetWidth() == 0:
            cy = f.GetBoundingBox(False, False)
        return (U.mm(cy.GetLeft()) - inflate, U.mm(cy.GetTop()) - inflate,
                U.mm(cy.GetRight()) + inflate, U.mm(cy.GetBottom()) + inflate)


def neck_segments(pts, w, neck, nl=0.6):
    """[(a, b, width)] for a polyline: width w, but the first and last `nl` mm at `neck` (None: no neck)."""
    if not neck or neck >= w:
        return [(a, b, w) for a, b in zip(pts, pts[1:])]
    segs = []
    tot = sum(d2(a, b) for a, b in zip(pts, pts[1:]))
    if tot < 2 * nl + 0.3:
        return [(a, b, neck) for a, b in zip(pts, pts[1:])]
    pos = 0.0
    for a, b in zip(pts, pts[1:]):
        L = d2(a, b)
        cuts = sorted({0.0, L, max(0.0, min(L, nl - pos)), max(0.0, min(L, tot - nl - pos))})
        for c0, c1 in zip(cuts, cuts[1:]):
            if c1 - c0 < 1e-6:
                continue
            mid = pos + (c0 + c1) / 2
            ww = neck if (mid < nl or mid > tot - nl) else w
            p = (a[0] + (b[0] - a[0]) * c0 / L, a[1] + (b[1] - a[1]) * c0 / L)
            q = (a[0] + (b[0] - a[0]) * c1 / L, a[1] + (b[1] - a[1]) * c1 / L)
            segs.append((p, q, ww))
        pos += L
    return segs


def fmt(p):
    return "(%.2f,%.2f)" % (p[0], p[1])


def dedupe(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if d2(p, out[-1]) > 1e-6:
            out.append(p)
    return out


def chamfer_poly(pts, c):
    """Replace every interior vertex of a polyline by a 45 degree-ish chamfer of leg length <= c."""
    if len(pts) < 3 or c <= 0:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = d2(p0, p1), d2(p1, p2)
        if l1 < 1e-9 or l2 < 1e-9:
            out.append(p1)
            continue
        u1 = ((p1[0] - p0[0]) / l1, (p1[1] - p0[1]) / l1)
        u2 = ((p2[0] - p1[0]) / l2, (p2[1] - p1[1]) / l2)
        cross = abs(u1[0] * u2[1] - u1[1] * u2[0])
        if cross < 1e-6:
            out.append(p1)
            continue
        cc = min(c, 0.5 * l1, 0.5 * l2)
        out.append((p1[0] - u1[0] * cc, p1[1] - u1[1] * cc))
        out.append((p1[0] + u2[0] * cc, p1[1] + u2[1] * cc))
    out.append(pts[-1])
    return out


GROUP_NAME = "route_power"
CORRIDOR_END = 1.5     # mm of each estimated RF/CLK corridor left unreserved at its pads
CORR_NET = 60000
CORRIDOR_CLR = 0.55     # clearance reserved around not-yet-routed RF50/CLK straight-line corridors (rule: 0.5)


# =============================================================================== placement tweak
class Placer:
    """Moves power-stage passives only.  Candidate poses on a 0.1 mm grid, 4 rotations; legal =
    courtyard (+0.3 per side => >= 0.6 mm gap) clear of every other footprint, of the no-track rule
    areas and of the board edge; score = weighted pad-to-target distances.  Deterministic: the
    movers are ignored as obstacles until re-placed in a fixed order."""

    def __init__(self, board, movers, step=0.1):
        self.b = board
        self.step = step
        self.moved = {}                 # ref -> (x, y, rot) final
        self.orig = {}
        self.local = {}
        self.fixed = []                 # (ref, rect)
        poly = U.outline_polygon(board)
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        self.edge = (min(xs) + 0.8, min(ys) + 0.8, max(xs) - 0.8, max(ys) - 0.8)
        self.rules = []
        for z in board.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                bb = z.GetBoundingBox()
                self.rules.append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())))
        self.movers = list(movers)
        for r in self.movers:
            f = board.FindFootprintByReference(r)
            if f is None:
                raise SystemExit("placer: %s not on the board" % r)
            p = f.GetPosition()
            self.orig[r] = (U.mm(p.x), U.mm(p.y), f.GetOrientationDegrees())
            self.local[r] = self._local(f)
        for f in board.GetFootprints():
            r = f.GetReference()
            if r in self.movers:
                continue
            p = f.GetPosition()
            if not U.point_in_poly(U.mm(p.x), U.mm(p.y), poly):
                continue            # parked test pads etc.
            self.fixed.append((r, self.rect(f)))

    @staticmethod
    def rect(f):
        cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if cy.GetWidth() == 0:
            cy = f.GetBoundingBox(False, False)
        g = GAP_COURTYARD
        return (U.mm(cy.GetLeft()) - g, U.mm(cy.GetTop()) - g, U.mm(cy.GetRight()) + g, U.mm(cy.GetBottom()) + g)

    def _local(self, f):
        """{rot: (courtyard rect rel. to the position, {pad number: (dx, dy)})}."""
        p0 = f.GetPosition()
        rot0 = f.GetOrientationDegrees()
        out = {}
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot)
            cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
            if cy.GetWidth() == 0:
                cy = f.GetBoundingBox(False, False)
            g = GAP_COURTYARD
            rel = (U.mm(cy.GetLeft() - p0.x) - g, U.mm(cy.GetTop() - p0.y) - g,
                   U.mm(cy.GetRight() - p0.x) + g, U.mm(cy.GetBottom() - p0.y) + g)
            pads = {}
            for pad in f.Pads():
                q = pad.GetPosition()
                pads[pad.GetNumber()] = (U.mm(q.x - p0.x), U.mm(q.y - p0.y))
            out[rot] = (rel, pads)
        f.SetOrientationDegrees(rot0)
        return out

    def padpos(self, ref, num):
        if ref in self.moved:
            x, y, rot = self.moved[ref]
            dx, dy = self.local[ref][rot][1][str(num)]
            return (x + dx, y + dy)
        f = self.b.FindFootprintByReference(ref)
        for p in f.Pads():
            if p.GetNumber() == str(num):
                return (U.mm(p.GetPosition().x), U.mm(p.GetPosition().y))
        raise KeyError((ref, num))

    @staticmethod
    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    def legal(self, ref, x, y, rot):
        rel = self.local[ref][rot][0]
        r = (x + rel[0], y + rel[1], x + rel[2], y + rel[3])
        e = self.edge
        if r[0] < e[0] or r[1] < e[1] or r[2] > e[2] or r[3] > e[3]:
            return False
        for q, rect in self.fixed:
            if self.hit(r, rect):
                return False
        for rect in self.rules:
            if self.hit(r, rect):
                return False
        return True

    def place(self, ref, targets, radius=8.0, rots=(0, 90, 180, 270), center=None, avoid=()):
        """targets: [(pad number, (tx, ty), weight)].  Best legal pose within `radius` of `center`
        (default: the weighted target centroid).  `avoid`: extra rectangles the courtyard must not hit."""
        wsum = sum(w for _, _, w in targets)
        if center is None:
            center = (sum(t[0] * w for _, t, w in targets) / wsum, sum(t[1] * w for _, t, w in targets) / wsum)
        st = self.step
        n = int(radius / st)
        cx0 = round(center[0] / st) * st
        cy0 = round(center[1] / st) * st
        best = None
        for ix in range(-n, n + 1):
            x = cx0 + ix * st
            for iy in range(-n, n + 1):
                y = cy0 + iy * st
                for rot in rots:
                    loc = self.local[ref][rot]
                    sc = 0.0
                    for num, t, w in targets:
                        dx, dy = loc[1][str(num)]
                        sc += w * math.hypot(x + dx - t[0], y + dy - t[1])
                    if best is not None and sc >= best[0] - 1e-9:
                        continue
                    if not self.legal(ref, x, y, rot):
                        continue
                    r = (x + loc[0][0], y + loc[0][1], x + loc[0][2], y + loc[0][3])
                    if any(self.hit(r, a) for a in avoid):
                        continue
                    best = (sc, x, y, rot)
        if best is None and radius < 30:
            return self.place(ref, targets, radius * 2, rots, center, avoid)
        if best is None:
            raise SystemExit("placer: no legal pose for %s near %s" % (ref, fmt(center)))
        sc, x, y, rot = best
        x, y = round(x, 3), round(y, 3)
        f = self.b.FindFootprintByReference(ref)
        f.SetPosition(U.pt(x, y))
        f.SetOrientationDegrees(rot)
        rel = self.local[ref][rot][0]
        self.fixed.append((ref, (x + rel[0], y + rel[1], x + rel[2], y + rel[3])))
        self.moved[ref] = (x, y, rot)
        return x, y, rot

    def report(self):
        out = []
        for r in self.movers:
            if r in self.moved:
                o, n = self.orig[r], self.moved[r]
                out.append(dict(ref=r, frm=[round(o[0], 2), round(o[1], 2), o[2]], to=[n[0], n[1], n[2]],
                                moved_mm=round(math.hypot(o[0] - n[0], o[1] - n[1]), 2)))
        return out


# =============================================================================== tree router (distribution)
import heapq                                  # noqa: E402

WIDTHS = {"POWER_HI": [1.0, 0.6, 0.4], "POWER_MID": [0.5, 0.4, 0.3], "POWER_LO": [0.3, 0.25, 0.2],
          "Default": [0.25, 0.2]}


class Comp:
    def __init__(self):
        self.pads = []       # pad dicts
        self.segs = []       # (a, b, w, layer)


def build_components(pb, netname):
    """Connected components of the net's copper (pads + tracks in the board) by geometric contact."""
    pads = pb.pads_of_net(netname)
    segs = []
    for t in pb.b.GetTracks():
        if t.GetNetname() != netname or t.Type() == pcbnew.PCB_VIA_T:
            continue
        s, e = t.GetStart(), t.GetEnd()
        segs.append(((U.mm(s.x), U.mm(s.y)), (U.mm(e.x), U.mm(e.y)), U.mm(t.GetWidth()),
                     F if t.GetLayer() == U.F_CU else B))
    vias = [(v[0], v[1]) for v in pb.vias if v[2] == pb.net(netname)]
    for t in pb.b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == netname:
            q = t.GetPosition()
            vias.append((U.mm(q.x), U.mm(q.y)))
    items = [("p", p) for p in pads] + [("s", s) for s in segs]
    par = list(range(len(items)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def touch(a, b):
        ka, ia = a
        kb, ib = b
        if ka == "p" and kb == "p":
            return abs(ia["x"] - ib["x"]) < (ia["w"] + ib["w"]) / 2 and abs(ia["y"] - ib["y"]) < (ia["h"] + ib["h"]) / 2
        if ka == "s" and kb == "p":
            a, b, ia, ib = b, a, ib, ia
            ka, kb = "p", "s"
        if ka == "p" and kb == "s":
            if ib[3] not in ia["lays"]:
                return False
            return U.dist_pt_rect(*_closest_to_rect(ia, ib), ia["x"] - ia["w"] / 2, ia["y"] - ia["h"] / 2,
                                  ia["x"] + ia["w"] / 2, ia["y"] + ia["h"] / 2) <= ib[2] / 2 + 1e-3
        if ib[3] != ia[3]:
            return False
        from mh_model import seg_seg_dist
        return seg_seg_dist(ia[0][0], ia[0][1], ia[1][0], ia[1][1], ib[0][0], ib[0][1], ib[1][0], ib[1][1]) <= (ia[2] + ib[2]) / 2 + 1e-3

    for i in range(len(items)):
        for j in range(i):
            if touch(items[i], items[j]):
                par[find(i)] = find(j)
    # a via ties segments on F and B that contain its point
    for (vx, vy) in vias:
        hit = []
        for i, (k, it) in enumerate(items):
            if k == "s" and U.dist_pt_seg(vx, vy, it[0][0], it[0][1], it[1][0], it[1][1]) <= it[2] / 2 + 0.01:
                hit.append(i)
            if k == "p" and abs(vx - it["x"]) <= it["w"] / 2 and abs(vy - it["y"]) <= it["h"] / 2 and it.get("smd", True):
                hit.append(i)
        for i in hit[1:]:
            par[find(i)] = find(hit[0])
    comps = {}
    for i, (k, it) in enumerate(items):
        c = comps.setdefault(find(i), Comp())
        (c.pads if k == "p" else c.segs).append(it)
    return list(comps.values())


def _closest_to_rect(pad, seg):
    cx, cy = pad["x"], pad["y"]
    a, b = seg[0], seg[1]
    # closest point on the segment to the pad centre
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((cx - a[0]) * dx + (cy - a[1]) * dy) / L2))
    return (a[0] + t * dx, a[1] + t * dy)


def comp_cells(pb, comp, layers_ok=(F, B)):
    """dict cell(ix,iy,l) -> ('p', pad) | ('s', seg)."""
    g = pb.m.grid
    out = {}
    for p in comp.pads:
        lays = p["lays"]
        for l in lays:
            ix0, iy0 = g.cell(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2)
            ix1, iy1 = g.cell(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)
            got = False
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    x, y = g.xy(ix, iy)
                    if abs(x - p["x"]) <= p["w"] / 2 and abs(y - p["y"]) <= p["h"] / 2:
                        out[(ix, iy, l)] = ("p", p)
                        got = True
            if not got:
                ix, iy = g.cell(p["x"], p["y"])
                out[(ix, iy, l)] = ("p", p)
    for s in comp.segs:
        a, b, w, l = s
        L = d2(a, b)
        n = max(1, int(L / 0.125))
        for k in range(n + 1):
            x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
            ix, iy = g.cell(x, y)
            out.setdefault((ix, iy, l), ("s", s))
    return out


def astar(pb, net, hw, src, goal, via_d, max_exp=350000, via_cost=30.0):
    g = pb.m.grid
    tier = g.tier(hw)
    W, Hh = g.W, g.H
    S = tier.S

    def free(ix, iy, l):
        if ix < 0 or iy < 0 or ix >= W or iy >= Hh:
            return False
        v = S[l][iy * W + ix]
        return v == 0 or v == net

    gx = [k[0] for k in goal]
    gy = [k[1] for k in goal]
    bx0, bx1, by0, by1 = min(gx), max(gx), min(gy), max(gy)

    def h(ix, iy):
        dx = max(bx0 - ix, 0, ix - bx1)
        dy = max(by0 - iy, 0, iy - by1)
        return (max(dx, dy) + 0.414 * min(dx, dy))

    gbest = {}
    prev = {}
    heap = []
    for k in src:
        gbest[k] = 0.0
        heapq.heappush(heap, (h(k[0], k[1]), 0.0, k))
    nbr = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    exp = 0
    viac = {}
    while heap:
        f, gc, k = heapq.heappop(heap)
        if gc > gbest.get(k, 1e18) + 1e-9:
            continue
        if k in goal:
            path = [k]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        exp += 1
        if exp > max_exp:
            return None
        ix, iy, l = k
        for dx, dy, c in nbr:
            jx, jy = ix + dx, iy + dy
            nk = (jx, jy, l)
            if nk not in goal and not free(jx, jy, l):
                continue
            if dx and dy and not (free(ix + dx, iy, l) and free(ix, iy + dy, l)):
                continue
            ng = gc + c
            if ng < gbest.get(nk, 1e18) - 1e-9:
                gbest[nk] = ng
                prev[nk] = k
                heapq.heappush(heap, (ng + h(jx, jy), ng, nk))
        # via to the other layer
        ol = 1 - l
        nk = (ix, iy, ol)
        if free(ix, iy, ol) or nk in goal:
            ok = viac.get((ix, iy))
            if ok is None:
                x, y = g.xy(ix, iy)
                ok = pb.via_site(net, x, y, via_d) is not None
                viac[(ix, iy)] = ok
            if ok:
                ng = gc + via_cost
                if ng < gbest.get(nk, 1e18) - 1e-9:
                    gbest[nk] = ng
                    prev[nk] = k
                    heapq.heappush(heap, (ng + h(ix, iy), ng, nk))
    return None


def _via_site(self, net, x, y, d, n=2):
    """(x, y) of the partner via of a via PAIR at (x, y), or None when no legal pair exists."""
    if not self.via_ok(net, x, y, d, VIA_DR if d < 0.7 else VIAP_DR):
        return None
    drill = VIA_DR if d < 0.7 else VIAP_DR
    sp = d + 0.30
    for dx, dy in ((sp, 0), (-sp, 0), (0, sp), (0, -sp)):
        if self.via_ok(net, x + dx, y + dy, d, drill) and U.point_in_poly(x + dx, y + dy, self.outline):
            return (x + dx, y + dy)
    return None


PB.via_site = _via_site


def route_tree(pb, netname, cls, report, tag, source_ref=None):
    """Connect all components of `netname` into one by A*; returns (ncomps_before, ncomps_after)."""
    net = pb.net(netname)
    ladder = WIDTHS.get(cls, WIDTHS["Default"])
    comps = build_components(pb, netname)
    n0 = len(comps)
    if n0 <= 1:
        return n0, n0
    # main component = the one containing the source pad, else the largest
    main = None
    if source_ref:
        for c in comps:
            if any(p["ref"] == source_ref[0] and p["num"] == str(source_ref[1]) for p in c.pads):
                main = c
    if main is None:
        main = max(comps, key=lambda c: len(c.pads) + len(c.segs))
    rest = [c for c in comps if c is not main]
    failed = []
    while rest:
        mc = comp_cells(pb, main)
        mcen = [(p["x"], p["y"]) for p in main.pads] or [s[0] for s in main.segs]
        rest.sort(key=lambda c: min(d2((q["x"], q["y"]), m) for q in (c.pads or [dict(x=c.segs[0][0][0], y=c.segs[0][0][1])]) for m in mcen))
        c = rest.pop(0)
        cc = comp_cells(pb, c)
        done = False
        for w in ladder:
            via_d = VIAP_D if w >= 0.9 else VIA_D
            path = astar(pb, net, w / 2, cc, mc, via_d)
            if path is None:
                continue
            ok = commit_path(pb, netname, path, w, via_d, tag, cc, mc)
            if ok:
                done = True
                report.setdefault("necked", []).append((netname, w)) if w < ladder[0] else None
                break
        if done:
            main.pads += c.pads
            main.segs += c.segs
        else:
            failed.append(c)
    return n0, 1 + len(failed)


def commit_path(pb, netname, path, w, via_d, tag, src_cells, goal_cells):
    g = pb.m.grid
    net = pb.net(netname)
    # polylines per layer
    pts = [(g.xy(k[0], k[1]), k[2]) for k in path]
    first_k, last_k = path[0], path[-1]
    runs = []
    cur = [pts[0][0]]
    curl = pts[0][1]
    vias = []
    for (xy, l) in pts[1:]:
        if l != curl:
            vias.append(cur[-1])
            runs.append((curl, cur))
            cur = [xy]
            curl = l
        else:
            cur.append(xy)
    runs.append((curl, cur))

    def anchor(k, cells, p_other):
        t = cells.get(k)
        if t and t[0] == "p":
            return (t[1]["x"], t[1]["y"])
        if t and t[0] == "s":
            a, b, _, _ = t[1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            xy = g.xy(k[0], k[1])
            tt = 0 if L2 == 0 else max(0, min(1, ((xy[0] - a[0]) * dx + (xy[1] - a[1]) * dy) / L2))
            return (a[0] + tt * dx, a[1] + tt * dy)
        return g.xy(k[0], k[1])

    runs[0][1].insert(0, anchor(first_k, src_cells, None)) if anchor(first_k, src_cells, None) != runs[0][1][0] else None
    runs[-1][1].append(anchor(last_k, goal_cells, None)) if anchor(last_k, goal_cells, None) != runs[-1][1][-1] else None
    # simplify collinear
    out = []
    for l, p in runs:
        q = [p[0]]
        for i in range(1, len(p) - 1):
            a, b, c = q[-1], p[i], p[i + 1]
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-6:
                q.append(b)
        q.append(p[-1])
        out.append((l, dedupe(q)))
    # legality (with and without chamfer) before touching the board
    final = []
    for l, p in out:
        good = None
        for ch in (0.45, 0.0):
            pp = chamfer_poly(p, ch) if ch else p
            if all(pb.seg_ok(net, l, a, b, w) for a, b in zip(pp, pp[1:])):
                good = pp
                break
        if good is None:
            return False
        final.append((l, good))
    # via pairs
    pairs = []
    for (vx, vy) in vias:
        v2 = pb.via_site(net, vx, vy, via_d)
        if v2 is None:
            return False
        pairs.append(((vx, vy), v2))
    drill = VIA_DR if via_d < 0.7 else VIAP_DR
    for l, p in final:
        pb.track(netname, p, w, tag, layer=l, check=False)
    for (v1, v2) in pairs:
        pb.via(netname, v1[0], v1[1], tag, via_d, drill, check=False)
        pb.via(netname, v2[0], v2[1], tag, via_d, drill, check=False)
        for l in (F, B):
            pb.track(netname, [v1, v2], min(0.4, via_d), tag, layer=l, check=False)
    return True


# =============================================================================== placement plan + cells
def netfull(board, short):
    """Full net name for a short name (sheet-local nets carry '/Sheet/')."""
    names = [str(n) for n in board.GetNetsByName().keys()]
    if short in names:
        return short
    c = [n for n in names if n.endswith("/" + short)]
    if len(c) != 1:
        raise KeyError(short)
    return c[0]


ANCHORS = {"U4": ["C40", "C42", "C43", "C44"], "U5": ["C48", "C50", "C51", "C52"],
           "U6": ["C56", "C58", "C59", "C60"], "U7": ["C64", "C66", "C67", "C68"]}
# (cap, ic): cap pad 1 -> nearest IC pad on the same net
DECOUPLERS = [("C2", "U1"), ("C3", "U1"), ("C4", "U1"), ("C1", "U1"),
              ("C102", "U20"), ("C103", "U20"), ("C107", "U20"), ("C108", "U20"),
              ("C210", "U30"), ("C211", "U30"), ("C213", "U31"), ("C214", "U31")]
for _ic, _caps in ANCHORS.items():
    DECOUPLERS += [(c, _ic) for c in _caps]

U8_PARTS = ["L1", "C20", "C21", "R9", "R8", "C22", "R301"]
U40_PARTS = ["L300", "C300", "C301", "C302", "R306", "R307", "R302"]


def movers(board):
    out = list(U8_PARTS) + list(U40_PARTS)
    out += [c for c, _ in DECOUPLERS if board.FindFootprintByReference(c) is not None and c not in out]
    return out


def plan_placement(plc, board):
    P = plc.padpos
    plc.place("L1", [("1", P("U8", "3"), 1.0)])
    plc.place("C20", [("1", P("U8", "4"), 1.0), ("2", P("U8", "2"), 0.5)])
    plc.place("C21", [("1", P("L1", "2"), 1.0), ("2", P("U8", "2"), 0.2)])
    plc.place("R9", [("1", P("U8", "6"), 1.0), ("2", P("U8", "2"), 0.3)])
    plc.place("R8", [("2", P("U8", "6"), 1.0), ("1", P("C21", "1"), 0.2)])
    plc.place("C22", [("2", P("U8", "6"), 1.0), ("1", P("C21", "1"), 0.1)])
    plc.place("R301", [("2", P("U8", "5"), 1.0)])
    plc.place("L300", [("1", P("U40", "9"), 1.0), ("2", P("U40", "7"), 1.0)], rots=(90, 270))
    plc.place("C300", [("1", P("U40", "10"), 1.0), ("2", P("U40", "8"), 0.5)])
    plc.place("C301", [("1", P("U40", "6"), 1.0), ("2", P("U40", "8"), 0.4)])
    plc.place("C302", [("1", P("C301", "1"), 1.0), ("2", P("U40", "8"), 0.2)])
    plc.place("R307", [("1", P("U40", "4"), 1.0), ("2", P("U40", "3"), 0.3)])
    plc.place("R306", [("2", P("U40", "4"), 1.0), ("1", P("C301", "1"), 0.1)])
    plc.place("R302", [("1", P("C301", "1"), 1.0)], radius=10.0)
    rr = {}
    for cap, ic in DECOUPLERS:
        f = board.FindFootprintByReference(cap)
        if f is None or cap in plc.moved:
            continue
        net1 = [p for p in f.Pads() if p.GetNumber() == "1"][0].GetNetname()
        pins = [p for p in board.FindFootprintByReference(ic).Pads() if p.GetNetname() == net1]
        if not pins:
            continue
        # independent of where the cap currently sits (idempotent): caps of one IC take its supply pins in turn
        pins.sort(key=lambda p: (str(p.GetNumber())))
        k = rr.get((ic, net1), 0)
        rr[(ic, net1)] = k + 1
        pin = pins[k % len(pins)]
        plc.place(cap, [("1", (U.mm(pin.GetPosition().x), U.mm(pin.GetPosition().y)), 1.0)], radius=6.0)


def cap_pins(pb, cap, ic):
    """(cap pad dict, nearest IC pad dict on the same net) or None."""
    try:
        c1 = pb.pad(cap, "1")
    except KeyError:
        return None
    pins = [p for p in pb.pads_of_net(c1["net"]) if p["ref"] == ic]
    if not pins:
        return None
    return c1, min(pins, key=lambda p: d2((p["x"], p["y"]), (c1["x"], c1["y"])))


def build_cells(pb, board):
    N = lambda s: netfull(board, s)    # noqa: E731
    pad = pb.pad
    xy = lambda p: (p["x"], p["y"])    # noqa: E731
    res = {}
    # ---------------- U8 (+3V3 buck): hot loop = C20 -> VIN(4) -> die -> GND(2) -> vias -> In1 -> C20 gnd vias
    pb.connect("+VSYS", xy(pad("C20", 1)), xy(pad("U8", 4)), 0.8, "u8_vin")
    pb.ground_pad("U8", 2, "u8_gnd", n=2, maxd=1.4, stub_w=0.25, prefer=xy(pad("C20", 2)))
    pb.ground_pad("C20", 2, "u8_cgnd", n=2, maxd=1.4, stub_w=0.4, prefer=xy(pad("U8", 2)))
    pb.connect(N("SW_3V3"), xy(pad("U8", 3)), xy(pad("L1", 1)), 0.8, "u8_sw")
    pb.connect(N("+3V3_REG"), xy(pad("L1", 2)), xy(pad("C21", 1)), 1.0, "u8_out")
    pb.ground_pad("C21", 2, "u8_ogd", n=2, maxd=1.4, stub_w=0.4, prefer=xy(pad("U8", 2)))
    pb.connect(N("+3V3_REG"), xy(pad("C21", 1)), xy(pad("R8", 1)), 0.3, "u8_fbtop")
    pb.connect(N("+3V3_REG"), xy(pad("R8", 1)), xy(pad("C22", 1)), 0.3, "u8_fbtop")
    pb.connect(N("+3V3_REG"), xy(pad("C21", 1)), xy(pad("R301", 1)), 0.3, "u8_pg")
    pb.connect(N("FB_3V3"), xy(pad("U8", 6)), xy(pad("R8", 2)), 0.2, "u8_fb")
    pb.connect(N("FB_3V3"), xy(pad("R8", 2)), xy(pad("R9", 1)), 0.2, "u8_fb")
    pb.connect(N("FB_3V3"), xy(pad("R8", 2)), xy(pad("C22", 2)), 0.2, "u8_fb")
    pb.ground_pad("R9", 2, "u8_fbgnd", n=1, maxd=1.4, stub_w=0.25)
    pb.connect(N("PG_3V3"), xy(pad("U8", 5)), xy(pad("R301", 2)), 0.2, "u8_pgn")
    # ---------------- U40 (+VBAT_LTE buck-boost)
    pb.connect("+VSYS", xy(pad("C300", 1)), xy(pad("U40", 10)), 0.8, "u40_vin")
    pb.ground_pad("U40", 8, "u40_gnd", n=2, maxd=2.0, stub_w=0.25, prefer=xy(pad("C300", 2)))
    pb.ground_pad("C300", 2, "u40_cgnd", n=2, maxd=1.4, stub_w=0.4, prefer=xy(pad("U40", 8)))
    pb.connect(N("L1_LTE"), xy(pad("U40", 9)), xy(pad("L300", 1)), 0.6, "u40_sw")
    pb.connect(N("L2_LTE"), xy(pad("U40", 7)), xy(pad("L300", 2)), 0.6, "u40_sw")
    pb.connect(N("+VBAT_LTE_REG"), xy(pad("U40", 6)), xy(pad("C301", 1)), 0.6, "u40_out")
    pb.connect(N("+VBAT_LTE_REG"), xy(pad("C301", 1)), xy(pad("C302", 1)), 0.6, "u40_out")
    pb.ground_pad("C301", 2, "u40_ogd", n=2, maxd=1.4, stub_w=0.4, prefer=xy(pad("U40", 8)))
    pb.ground_pad("C302", 2, "u40_ogd2", n=2, maxd=1.4, stub_w=0.4, prefer=xy(pad("U40", 8)))
    pb.connect(N("+VBAT_LTE_REG"), xy(pad("C301", 1)), xy(pad("R302", 1)), 0.5, "u40_feed")
    pb.connect(N("+VBAT_LTE_REG"), xy(pad("C301", 1)), xy(pad("R306", 1)), 0.2, "u40_fbtop")
    pb.connect(N("FB_LTE"), xy(pad("U40", 4)), xy(pad("R306", 2)), 0.2, "u40_fb")
    pb.connect(N("FB_LTE"), xy(pad("R306", 2)), xy(pad("R307", 1)), 0.2, "u40_fb")
    pb.ground_pad("R307", 2, "u40_fbgnd", n=1, maxd=1.4, stub_w=0.25)
    # ---------------- local decoupling: cap pad 1 -> IC pin, 2+ ground vias at the cap
    for cap, ic in DECOUPLERS:
        cp = cap_pins(pb, cap, ic)
        if cp is None:
            continue
        c1, pin = cp
        cls = pb.m.nets[pb.net(c1["net"])]["cls"]
        w = {"POWER_HI": 0.8, "POWER_MID": 0.5}.get(cls, 0.3)
        pb.connect(c1["net"], (c1["x"], c1["y"]), (pin["x"], pin["y"]), w, "dec_" + cap)
        c2 = pad(cap, 2)
        if c2["net"] == "GND":
            pb.ground_pad(cap, 2, "decg_" + cap, n=2, maxd=1.6, stub_w=0.3, prefer=(pin["x"], pin["y"]))
    return res


# =============================================================================== loop metrics
def lprime(w):
    z0, ee = SK.microstrip(w, H, ER)
    return z0 * math.sqrt(ee) / SK.C0 * 1e6   # nH per mm (ohm * s/m = H/m)


def l_via(n, d=VIA_D):
    return MU0 / (2 * math.pi) * (H * 1e-3) * (math.log(4 * H / d) + 1) / n * 1e9


def loop_metrics(pb, spec):
    """spec: name, fwd tags, gnd tags (IC side, cap side), cap pad, vin pad, esl_nH, di, tr."""
    legs = pb.legs
    ltr = 0.0
    ltot = 0.0
    for t in spec["fwd"] + spec["gic"] + spec["gcap"]:
        for lg in legs.get(t, []):
            if lg["kind"] == "trace":
                ltr += lprime(lg["w"]) * lg["l"]
                ltot += lg["l"]
    ngic = sum(1 for t in spec["gic"] for lg in legs.get(t, []) if lg["kind"] == "via")
    ngcap = sum(1 for t in spec["gcap"] for lg in legs.get(t, []) if lg["kind"] == "via")
    vics = [(lg["x"], lg["y"]) for t in spec["gic"] for lg in legs.get(t, []) if lg["kind"] == "via"]
    vcap = [(lg["x"], lg["y"]) for t in spec["gcap"] for lg in legs.get(t, []) if lg["kind"] == "via"]
    if not vics or not vcap:
        return None
    ci = (sum(v[0] for v in vics) / len(vics), sum(v[1] for v in vics) / len(vics))
    cc = (sum(v[0] for v in vcap) / len(vcap), sum(v[1] for v in vcap) / len(vcap))
    dvv = max(d2(ci, cc), 0.8)
    lvia = l_via(ngic) + l_via(ngcap)
    lplane = MU0 / (2 * math.pi) * (H * 1e-3) * math.log(dvv / (VIA_D / 2)) * 1e9
    poly = [spec["pc"], spec["pv"], ci, cc]
    area_top = abs(sum(poly[i][0] * poly[(i + 1) % 4][1] - poly[(i + 1) % 4][0] * poly[i][1] for i in range(4))) / 2
    a_eff = H * (ltot + dvv)
    L = ltr + lvia + lplane
    out = dict(name=spec["name"], trace_mm=round(ltot, 2), via_per_return=[ngic, ngcap], via_dist_mm=round(dvv, 2),
               area_top_mm2=round(area_top, 2), area_eff_mm2=round(a_eff, 2),
               L_board_nH=round(L, 2), L_esl_nH=spec["esl"], L_total_nH=round(L + spec["esl"], 2))
    di, tr = spec["di"], spec["tr"]
    out["di_dt_A_per_ns"] = round(di / tr, 3)
    out["spike_V"] = round((L + spec["esl"]) * di / tr, 3)
    return out


LOOPS = [
    dict(name="U8 TPS62A02 input loop (C20-VIN-GND)", fwd=["u8_vin"], gic=["u8_gnd"], gcap=["u8_cgnd"],
         pc=None, pv=None, esl=0.6, di=0.45, tr=2.0, pads=(("C20", 1), ("U8", 4))),
    dict(name="U40 TPS63802 input loop (C300-VIN-GND)", fwd=["u40_vin"], gic=["u40_gnd"], gcap=["u40_cgnd"],
         pc=None, pv=None, esl=0.6, di=1.0, tr=2.0, pads=(("C300", 1), ("U40", 10))),
]


# =============================================================================== distribution plan
DIST = [  # (short net, class, source pad)
    ("SW_3V3", "POWER_HI", None), ("L1_LTE", "POWER_HI", None), ("L2_LTE", "POWER_HI", None),
    ("FB_3V3", "Default", None), ("FB_LTE", "Default", None),
    ("+3V3_A0", "POWER_LO", None), ("+3V3_A1", "POWER_LO", None), ("+3V3_A2", "POWER_LO", None), ("+3V3_A3", "POWER_LO", None),
    ("+3V3_TCXO", "POWER_LO", None), ("+3V3_CLKBUF", "POWER_LO", None),
    ("NRF_VDD", "POWER_MID", ("U20", 14)), ("NRF_VDD_GPIO", "POWER_LO", ("U20", 65)),
    ("+VBAT_LTE_REG", "POWER_MID", ("U40", 6)), ("+VBAT_LTE", "POWER_MID", ("R302", 2)),
    ("+3V3_REG", "POWER_MID", ("L1", 2)), ("+VSYS", "POWER_HI", ("U1", 1)),
    ("VBATT_PROT", "POWER_HI", ("U1", 14)), ("+5V_IN", "POWER_HI", ("U1", 17)),
    ("BATT_RAW", "POWER_HI", ("BT1", 1)), ("BARREL_VIN", "POWER_HI", ("J1", 1)),
    ("+3V3", "POWER_MID", ("R300", 2)), ("+3V3_SNS", "POWER_LO", None), ("GNSS_LNA_VCC", "POWER_LO", None),
    ("ESIM_VCC", "POWER_LO", None), ("SIM_CARD_VCC", "POWER_LO", None),
]


def strip_previous(board):
    """Remove the items of a previous run (members of the group GROUP_NAME).  The (empty) group itself is
    kept and re-used: removing a group with pcbnew's python binding corrupts the board's drawing list."""
    n = 0
    keep = None
    for g in list(board.Groups()):
        if g.GetName() == GROUP_NAME:
            keep = g
            for it in list(g.GetItems()):
                g.RemoveItem(it)
                board.RemoveNative(it)
                n += 1
    return n, keep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", required=True, help="PLACED board; use a scratch copy")
    ap.add_argument("--out", help="write here (default: overwrite --board)")
    ap.add_argument("--report", help="JSON report (loops, moves, failures)")
    ap.add_argument("--nets-json", default=os.path.join(HERE, "power_nets.json"))
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--no-dist", action="store_true", help="hot-loop cells only")
    a = ap.parse_args()

    pcbnew.KIID.SeedGenerator(SEED)
    board = U.load_board(a.board)
    removed, old_grp = strip_previous(board)
    plc = Placer(board, movers(board))
    plan_placement(plc, board)
    moves = plc.report()
    for m in moves:
        print("move %-5s %s -> %s  (%.2f mm)" % (m["ref"], m["frm"], m["to"], m["moved_mm"]))
    pb = PB(board)
    if old_grp is not None:
        pb.grp = old_grp
    print("corridors reserved for:", ", ".join(pb.corridor_nets))
    build_cells(pb, board)
    left = {}
    routed = {}
    if not a.no_dist:
        for short, cls, src in DIST:
            try:
                name = netfull(board, short)
            except KeyError:
                continue
            before, after = route_tree(pb, name, cls, {}, "dist_" + short, source_ref=src)
            print("net %-28s comps %d -> %d" % (name, before, after))
    # final connectivity per net
    for short, cls, src in DIST:
        try:
            name = netfull(board, short)
        except KeyError:
            continue
        comps = build_components(pb, name)
        comps.sort(key=lambda c: -len(c.pads))
        routed[name] = dict(cls=cls, pads_connected=sorted("%s.%s" % (p["ref"], p["num"]) for p in comps[0].pads) if comps else [])
        lp = sorted("%s.%s" % (p["ref"], p["num"]) for c in comps[1:] for p in c.pads)
        if lp:
            left[name] = lp
    loops = []
    for sp in LOOPS:
        (r1, n1), (r2, n2) = sp["pads"]
        p1, p2 = pb.pad(r1, n1), pb.pad(r2, n2)
        sp["pc"], sp["pv"] = (p1["x"], p1["y"]), (p2["x"], p2["y"])
        lm = loop_metrics(pb, sp)
        if lm:
            loops.append(lm)
            print(lm)
    print("tracks %d vias %d failures %d" % (pb.ntrack, pb.nvia, len(pb.failures)))
    for f in pb.failures:
        print("FAIL", f)
    if old_grp is None:
        board.Add(pb.grp)
    rep = dict(moves=moves, loops=loops, failures=pb.failures, left=left, tracks=pb.ntrack, vias=pb.nvia)
    if a.report:
        json.dump(rep, open(a.report, "w"), indent=1, sort_keys=True)
    if not a.no_save:
        out = a.out or a.board
        U.save_board(board, out)
        nets = dict(_comment="Nets routed by scripts/layout/route_power.py (stage 5). route_manhattan.py must skip every net in routed_nets. "
                    "left_unconnected lists pads of those nets that the script could not reach.",
                    schema=1, corridor_clearance_mm=CORRIDOR_CLR,
                    gnd_vias_added=True,
                    routed_nets={n: v for n, v in sorted(routed.items()) if any(it[1] == n for it in pb.items)},
                    other_nets_with_copper=sorted({it[1] for it in pb.items} - set(routed)),
                    left_unconnected=left)
        json.dump(nets, open(a.nets_json, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
