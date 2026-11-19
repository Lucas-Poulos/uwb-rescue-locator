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
        self.m = Model(board, pitch)
        self.name2idx = {v["name"]: k for k, v in self.m.nets.items()}
        self.items = []                 # (kind, name, tag) of everything created
        self.legs = {}                  # tag -> list of dict(kind, ...)
        self.failures = []
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
        self.reserve_corridors()

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
                                        smd=not p.HasHole()))
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
                self.m._add_static(Prim("seg", (a[0], a[1], c2[0], c2[1], 0.225), (F,), -1, CORRIDOR_CLR))
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
            U.add_track(self.b, nobj, LAYERS[layer], a[0], a[1], b[0], b[1], w)
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
        U.add_via(self.b, nobj, x, y, d, drill)
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
                U.add_track(self.b, nobj, U.F_CU, c[0], c[1], x, y, stub_w)
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
        best = None
        for pts in cands:
            pts2 = chamfer_poly(pts, chamfer) if chamfer and len(pts) > 2 else pts
            pts2 = dedupe(pts2)
            if all(self.seg_ok(net, layer, p, q, w) for p, q in zip(pts2, pts2[1:])):
                L = sum(d2(p, q) for p, q in zip(pts2, pts2[1:]))
                if best is None or L < best[0] - 1e-9:
                    best = (L, pts2)
        if best is None:
            self.failures.append("connect %s %s %s->%s w%.2f: no legal L/Z" % (tag, netname, fmt(a), fmt(b), w))
            return None
        self.track(netname, best[1], w, tag, layer=layer, check=False)
        return best[1]

    # ------------------------------------------------------------- placement
    def part_bbox(self, f, inflate=GAP_COURTYARD):
        cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if cy.GetWidth() == 0:
            cy = f.GetBoundingBox(False, False)
        return (U.mm(cy.GetLeft()) - inflate, U.mm(cy.GetTop()) - inflate,
                U.mm(cy.GetRight()) + inflate, U.mm(cy.GetBottom()) + inflate)


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


CORRIDOR_CLR = 1.0     # clearance reserved around not-yet-routed RF50/CLK straight-line corridors (rule: 0.5)


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
