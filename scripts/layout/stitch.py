#!/usr/bin/env python3
"""GND stitching vias, DW3210 cut-outs, GND pours and GND pad ties for the bay-station
board.  KiCad's python.  Run it on a SCRATCH copy of the board AFTER routing.

Lattice (derived, see docs/routing-plan.md section 6), all sized from the board outline
(nothing is tied to a board size; works for a rectangle or an Edge.Cuts polygon with arcs):
  * general lattice, pitch <= 5.0 mm, spread evenly over [outline + 2 mm] (n = ceil(span/5),
    so the last row is never a 4.9 mm leftover).  5 mm is lambda_g/15 at LTE band edge 2.2 GHz
    (lambda_g ~ 74 mm in the 4.5 / eps_eff ~3.4 stack; /20 would be 3.7 mm): a compromise
    against via count and routing area, tightened where it matters:
  * dense lattice, pitch <= 2.5 mm (lambda_g/10 at 6.49 GHz is 2.5 mm, the RF rule) within
    4 mm of any RF50 / CLK copper;
  * board edge ring: 2.5 mm pitch, 1.0 mm inset (edge clearance 0.5 + via radius 0.225 + margin);
  * the 4 DW3210 bodies: no vias (DW3000 DS v1.1 s7.3.2 Fig 35: keep clear of copper, tracks and
    vias under the body on Top and Inner Layer 1);
  * bottom-side test pads (pogo probes land there): vias keep TP_CLEAR (0.6 mm) from any
    TestPoint pad, so a probe tip / guide never sits on a via hole;
  * a candidate within 0.4 x pitch of an existing GND via counts as already stitched, so a
    second run on a stitched board adds almost nothing (idempotent);
  * via-to-via drill edge to drill edge >= the board's hole-to-hole rule (hs_nets.json
    fab.min_hole_to_hole_mm, which apply_rules.py writes into the .kicad_pro), checked against every via and
    every through hole, also the vias this run just placed.
RF fences along locked RF lines come from route_hs.via_fence (1.5 mm pitch).

Vias are 0.45/0.20 GND, through (JLCPCB min via 0.25/0.15 per the jlcpcb skill; 0.45 gives a
0.125 mm annular ring).  Skipped near: any pad (0.25 mm edge to via edge: keeps vias out of mask
openings and solder wicking), tracks (0.15; 0.5 for RF50/CLK), other vias/holes, the board edge,
keep-out rule areas.  Candidate positions are nudged up to +-1.2 mm (spiral) before skipping.

GND pad ties (--rescue auto | list.json): every GND pad that the pours + lattice leave
isolated is tied by a Dijkstra search on its own copper layer, 0.2 mm stub, orthogonal or 45
degree steps, to the nearest of: an existing GND via, a GND stub placed earlier in this run, or
a NEW legal via site.  Chain length (pad centre to via) <= --reach (2.0 mm = the direction-policy
stub limit of check_gates.py).  Vias are never put inside the DW3210 cut-out; a DW3210 GND pad
therefore reaches out past the 5.5 mm square.  Inside DW3210_TIE_n (cut-out + 2 mm) a GND stub
may sit 0.15 mm from an RF50 track instead of the 0.5 mm keep-off; the matching .kicad_dru rule
is "GND pad tie stub next to an RF50 neck" (see docs/routing-plan.md section 6).  That is the
only rule relaxed; vias, pours and every other net keep the 0.5 mm.
`auto` finds the isolated pads itself: it fills a scratch copy with kicad-cli (never in
process) and reads the DRC's unconnected GND items, twice (the second pass catches pads whose
only neighbours were ties of the first).

    kicad-python stitch.py --board SCRATCH.kicad_pcb [--out X] [--zones] [--pitch 5.0]
                           [--rescue auto|list.json] [--rescue-only] [--reach 2.0] [--report r.json]
"""
import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
import heapq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U
from mh_model import Model, Prim, F, B

VIA_D, VIA_DRILL = 0.45, 0.20
R = VIA_D / 2
PAD_MARGIN = 0.25
TP_CLEAR = 0.6            # via edge to a test-pad edge
GEN_PITCH, DENSE_PITCH, DENSE_DIST = 5.0, 2.5, 4.0
EDGE_PITCH, EDGE_INSET = 2.5, 1.0
LATTICE_INSET = 2.0       # general / dense lattice starts this far inside the outline
NUDGE = 1.2
COVER = 0.4               # an existing GND via within COVER x pitch already stitches a candidate
CUTOUT = 5.5              # mm square under each DW3210 (QFN 5x5 body + 0.25 per side)
TIE_MARGIN = 2.0          # DW3210_TIE_n = cut-out + this per side (scope of the RF keep-off exception)
TIE_CLEARANCE = 0.15      # GND stub to RF50 track inside DW3210_TIE_n (= the netclass clearance)
STUB_W = 0.2
STEP = 0.05               # grid of the pad-tie search
RELAX_PAD = 0.15          # second-tier via-to-foreign-pad margin of a tie via (netclass clearance)
H2H_DEFAULT = 0.25


def hole_to_hole():
    """Board hole-to-hole rule (drill edge to drill edge), mm: the larger of hs_nets.json and the
    .kicad_pro design rule, if it can be read."""
    try:
        return float(U.load_spec()["fab"]["min_hole_to_hole_mm"])
    except Exception:
        return H2H_DEFAULT


def dw3210_cutouts(board):
    """[(cx, cy, w, h)] square under each DW3210, centred on its pad centroid."""
    out = []
    for f in board.GetFootprints():
        if "DW3210" in str(f.GetFPIDAsString()):
            xs, ys = [], []
            for p in f.Pads():
                q = p.GetPosition()
                xs.append(U.mm(q.x)); ys.append(U.mm(q.y))
            out.append((sum(xs) / len(xs), sum(ys) / len(ys), CUTOUT, CUTOUT))
    return out


def tie_areas(board):
    return [(cx, cy, w + 2 * TIE_MARGIN, h + 2 * TIE_MARGIN) for (cx, cy, w, h) in dw3210_cutouts(board)]


class Hash:
    """Tiny bucket hash for point-in-radius queries over rectangles / circles."""

    def __init__(self, cell=3.0):
        self.c = cell
        self.d = {}

    def add(self, bb, obj):
        c = self.c
        for ix in range(int(math.floor(bb[0] / c)), int(math.floor(bb[2] / c)) + 1):
            for iy in range(int(math.floor(bb[1] / c)), int(math.floor(bb[3] / c)) + 1):
                self.d.setdefault((ix, iy), []).append(obj)

    def near(self, x, y, r):
        c = self.c
        seen = set()
        for ix in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
            for iy in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                for o in self.d.get((ix, iy), ()):
                    if id(o) not in seen:
                        seen.add(id(o))
                        yield o


class Stitcher:
    def __init__(self, board):
        self.b = board
        self.m = Model(board, 0.25)
        self.gnd = [i for i, n in self.m.nets.items() if n["name"] == "GND"][0]
        self.gnd_code = U.get_net(board, "GND").GetNetCode()
        self.cut = dw3210_cutouts(board)
        self.tie = tie_areas(board)
        self.h2h = hole_to_hole()
        self.relax_pad = None   # tie vias only: pad margin override (see tie_pad)
        self.placed = []
        self.padh = Hash()
        self.viah = Hash()
        for f in board.GetFootprints():
            ref = str(f.GetReference())
            is_tp = "TestPoint" in str(f.GetFPIDAsString()) or ref.startswith("TP")
            for p in f.Pads():
                bb = p.GetBoundingBox()
                try:
                    lc = p.GetLocalClearance()
                    lc = U.mm(lc) if lc else 0.0
                except Exception:
                    lc = 0.0
                clr = max(TP_CLEAR if is_tp else PAD_MARGIN, lc + 0.05)
                q = p.GetPosition()
                rec = (U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()),
                       p.HasHole(), U.mm(q.x), U.mm(q.y), U.mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2, clr)
                self.padh.add((rec[0] - 3, rec[1] - 3, rec[2] + 3, rec[3] + 3), rec)
        self.vias = []         # (x, y, drill_r, copper_r, is_gnd)
        self.gnd_vias = []
        self.rfpts = []        # sample points of RF50/CLK copper
        self.rf_prims = set()  # id() of the obstacle prims that are RF50 tracks (for the tie exception)
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                q = t.GetPosition()
                self._add_via_rec(U.mm(q.x), U.mm(q.y), U.mm(t.GetDrill()) / 2, U.mm(t.GetWidth(U.F_CU)) / 2,
                                  t.GetNetCode() == self.gnd_code)
            elif str(t.GetNetClassName()) in ("RF50", "CLK"):
                s, e = t.GetStart(), t.GetEnd()
                L = math.hypot(U.mm(e.x - s.x), U.mm(e.y - s.y))
                n = max(1, int(L / 1.0))
                for k in range(n + 1):
                    self.rfpts.append((U.mm(s.x) + U.mm(e.x - s.x) * k / n, U.mm(s.y) + U.mm(e.y - s.y) * k / n))
        for p in self.m.nets.values():
            if p["cls"] == "RF50":
                for pd in p["pads"]:
                    self.rfpts.append(pd["c"])
        self._mark_rf_prims()
        self.stubs = []        # (x0, y0, x1, y1, layer) of GND tie stubs placed in this run

    # ------------------------------------------------------------- bookkeeping
    def _add_via_rec(self, x, y, dr, cr, is_gnd):
        rec = (x, y, dr, cr, is_gnd)
        self.vias.append(rec)
        self.viah.add((x - 1, y - 1, x + 1, y + 1), rec)
        if is_gnd:
            self.gnd_vias.append(rec)

    def _mark_rf_prims(self):
        rf = []
        for t in self.b.GetTracks():
            if t.Type() != pcbnew.PCB_VIA_T and str(t.GetNetClassName()) in ("RF50", "CLK"):
                s, e = t.GetStart(), t.GetEnd()
                rf.append((round(U.mm(s.x), 3), round(U.mm(s.y), 3), round(U.mm(e.x), 3), round(U.mm(e.y), 3)))
        key = set(rf)
        # the model stores every via drill as a net-0 hole prim; a stub of the SAME net may touch it
        self.gnd_holes = set()
        gpos = {(round(v[0], 3), round(v[1], 3)) for v in self.gnd_vias}
        for p in self.m.obst.items.values():
            if p.kind == "circ" and p.net == 0 and abs(p.clr - 0.25) < 1e-9 and (round(p.g[0], 3), round(p.g[1], 3)) in gpos:
                self.gnd_holes.add(id(p))
        for p in self.m.obst.items.values():
            if p.kind == "seg" and p.clr >= 0.5 - 1e-9:
                g = p.g
                if (round(g[0], 3), round(g[1], 3), round(g[2], 3), round(g[3], 3)) in key:
                    self.rf_prims.add(id(p))

    def in_tie(self, x, y, pad=0.0):
        for (cx, cy, w, h) in self.tie:
            if abs(x - cx) <= w / 2 + pad and abs(y - cy) <= h / 2 + pad:
                return True
        return False

    # ------------------------------------------------------------- legality
    def legal(self, x, y):
        """Can a GND stitch / tie via of VIA_D/VIA_DRILL sit at (x, y)?"""
        for (cx, cy, w, h) in self.cut:
            if abs(x - cx) < w / 2 + R and abs(y - cy) < h / 2 + R:
                return False
        for (x0, y0, x1, y1, th, px, py, hr, clr) in self.padh.near(x, y, 3.0):
            c = self.relax_pad if (self.relax_pad is not None and clr <= PAD_MARGIN + 1e-9) else clr
            if U.dist_pt_rect(x, y, x0, y0, x1, y1) < R + c:
                return False
            if th and math.hypot(x - px, y - py) < VIA_DRILL / 2 + hr + self.h2h:
                return False
        for (vx, vy, dr, vr, _g) in self.viah.near(x, y, 1.5):
            d = math.hypot(x - vx, y - vy)
            if d < VIA_DRILL / 2 + dr + self.h2h or d < R + vr + 0.05:
                return False
        for l in (F, B):
            if not self.m.obst.seg_ok(self.gnd, l, x, y, x, y, R, slack=-0.02):
                return False
        if not U.point_in_poly(x, y, self.m.poly):
            return False
        return True

    def try_site(self, x, y):
        if self.legal(x, y):
            return (x, y)
        steps = int(NUDGE / 0.2)
        for k in range(1, steps + 1):
            r = k * 0.2
            n = 8 * k
            for i in range(n):
                a = 2 * math.pi * i / n
                xx, yy = x + r * math.cos(a), y + r * math.sin(a)
                if self.legal(xx, yy):
                    return (xx, yy)
        return None

    def near_rf(self, x, y):
        for (rx, ry) in self.rfpts:
            if abs(rx - x) < DENSE_DIST and abs(ry - y) < DENSE_DIST and math.hypot(rx - x, ry - y) < DENSE_DIST:
                return True
        return False

    def covered(self, x, y, r):
        for (vx, vy, _d, _c, g) in self.viah.near(x, y, r):
            if g and math.hypot(x - vx, y - vy) < r:
                return True
        return False

    # ------------------------------------------------------------- lattice
    @staticmethod
    def axis(lo, hi, pitch):
        """Evenly spread positions on [lo, hi] with spacing <= pitch (one point if the span is 0)."""
        if hi <= lo:
            return [0.5 * (lo + hi)]
        n = max(1, int(math.ceil((hi - lo) / pitch - 1e-9)))
        return [lo + (hi - lo) * k / n for k in range(n + 1)]

    def candidates(self, gen_pitch=None):
        gp = gen_pitch or GEN_PITCH
        poly = self.m.poly
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        out = []
        ax = self.axis(x0 + LATTICE_INSET, x1 - LATTICE_INSET, gp)
        ay = self.axis(y0 + LATTICE_INSET, y1 - LATTICE_INSET, gp)
        for x in ax:
            for y in ay:
                out.append((x, y, "gen"))
        dx = self.axis(x0 + LATTICE_INSET, x1 - LATTICE_INSET, DENSE_PITCH)
        dy = self.axis(y0 + LATTICE_INSET, y1 - LATTICE_INSET, DENSE_PITCH)
        for x in dx:
            for y in dy:
                if self.near_rf(x, y):
                    out.append((x, y, "rf"))
        n = len(poly)
        for i in range(n):
            a, c = poly[i], poly[(i + 1) % n]
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            if L < 1e-6:
                continue
            ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
            nx, ny = -uy, ux
            mx, my = a[0] + ux * L / 2 + nx * 0.5, a[1] + uy * L / 2 + ny * 0.5
            if not U.point_in_poly(mx, my, poly):
                nx, ny = -nx, -ny
            span = L - 2 * EDGE_INSET
            if span < 0:
                continue
            for d in self.axis(EDGE_INSET, EDGE_INSET + span, EDGE_PITCH):
                out.append((a[0] + ux * d + nx * EDGE_INSET, a[1] + uy * d + ny * EDGE_INSET, "edge"))
        return out

    def run(self, locked=False, gen_pitch=None):
        gnd_net = U.get_net(self.b, "GND")
        gp = gen_pitch or GEN_PITCH
        radius = {"gen": COVER * gp, "rf": COVER * DENSE_PITCH, "edge": COVER * EDGE_PITCH}
        stats = {"gen": [0, 0], "rf": [0, 0], "edge": [0, 0]}
        for (x, y, kind) in self.candidates(gp):
            stats[kind][0] += 1
            if self.covered(x, y, radius[kind]):
                continue
            site = self.try_site(x, y)
            if site is None:
                continue
            U.add_via(self.b, gnd_net, site[0], site[1], VIA_D, VIA_DRILL, locked)
            self._add_via_rec(site[0], site[1], VIA_DRILL / 2, R, True)
            self.placed.append(site)
            stats[kind][1] += 1
        return stats

    # ------------------------------------------------------------- pad ties
    def _stub_ok(self, layer, ax, ay, bx, by, hw):
        """Exact test for a GND stub: obstacles of other nets at their clearance, except an RF50
        track inside DW3210_TIE_n, which only needs the netclass clearance (the .kicad_dru
        exception)."""
        pad = hw + 0.5 + 0.3
        bb = (min(ax, bx) - pad, min(ay, by) - pad, max(ax, bx) + pad, max(ay, by) + pad)
        tie = self.in_tie(ax, ay, hw) or self.in_tie(bx, by, hw)
        for p in self.m.obst.near(bb):
            if p.net == self.gnd or layer not in p.layers or id(p) in self.gnd_holes:
                continue
            c = p.clr
            if tie and id(p) in self.rf_prims:
                c = TIE_CLEARANCE
            if p.dist_seg(ax, ay, bx, by) < hw + c - 0.001:
                return False
        return True

    def _goal_point(self, x, y, layer):
        """Return (kind, (gx, gy)) if (x, y) touches existing GND copper / is a legal new via site."""
        for (vx, vy, _d, cr, g) in self.viah.near(x, y, 0.5):
            if g and math.hypot(x - vx, y - vy) <= 0.12:
                return "via", (vx, vy)
        for (sx0, sy0, sx1, sy1, sl) in self.stubs:
            if sl == layer and U.dist_pt_seg(x, y, sx0, sy0, sx1, sy1) <= 0.03:
                return "stub", (x, y)
        if self.legal(x, y):
            return "new", (x, y)
        return None

    def find_tie(self, cx, cy, layer, reach):
        """Dijkstra on a STEP grid centred on the pad centre; 8 directions, bend penalty.  Returns
        (points, kind) or None.  points[0] is the pad centre."""
        hw = STUB_W / 2
        n = int(round(reach / STEP))
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        okc = {}

        def node_ok(i, j):
            k = (i, j)
            if k not in okc:
                x, y = cx + i * STEP, cy + j * STEP
                okc[k] = self._stub_ok(layer, x, y, x, y, hw) and U.point_in_poly(x, y, self.m.poly)
            return okc[k]

        start = (0, 0, -1)
        best = {start: 0.0}
        prev = {}
        heap = [(0.0, start)]
        while heap:
            g, st = heapq.heappop(heap)
            if best.get(st, 1e18) < g - 1e-12:
                continue
            i, j, d = st
            if (i or j):
                gp = self._goal_point(cx + i * STEP, cy + j * STEP, layer)
                if gp:
                    pts, s = [], st
                    while True:
                        pts.append((cx + s[0] * STEP, cy + s[1] * STEP))
                        if s not in prev:
                            break
                        s = prev[s]
                    pts.reverse()
                    if gp[0] == "via":      # land on the via centre
                        pts.append(gp[1])
                    return pts, gp[0]
            for nd, (di, dj) in enumerate(dirs):
                ni, nj = i + di, j + dj
                L = math.hypot(di, dj) * STEP
                ng = g + L + (0.04 if d >= 0 and nd != d else 0.0) + (0.0 if nd < 4 else 0.01)
                if ng > reach + 1e-9:
                    continue
                if abs(ni) > n or abs(nj) > n or not node_ok(ni, nj):
                    continue
                ns = (ni, nj, nd)
                if ng < best.get(ns, 1e18) - 1e-12:
                    # diagonal moves pass between two cells: test the edge itself
                    if nd >= 4 and not self._stub_ok(layer, cx + i * STEP, cy + j * STEP, cx + ni * STEP, cy + nj * STEP, hw):
                        continue
                    best[ns] = ng
                    prev[ns] = st
                    heapq.heappush(heap, (ng, ns))
        return None

    @staticmethod
    def simplify(pts):
        out = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = out[-1], pts[k], pts[k + 1]
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-9:
                continue
            out.append(b)
        out.append(pts[-1])
        return out

    def tie_pad(self, ref, num, reach, relax=None):
        """Tie one GND pad.  Returns ('tied', info) or ('fail', reason)."""
        pad = None
        for f in self.b.GetFootprints():
            if str(f.GetReference()) == ref:
                for p in f.Pads():
                    if str(p.GetNumber()) == str(num):
                        pad = p
        if pad is None:
            return "fail", "pad not found"
        layer = U.F_CU if pad.IsOnLayer(U.F_CU) else U.B_CU
        lidx = F if layer == U.F_CU else B
        c = pad.GetPosition(); cx, cy = U.mm(c.x), U.mm(c.y)
        got = self.find_tie(cx, cy, lidx, reach)
        tier = "strict"
        if got is None and relax is not None:
            # second tier: the via may sit 0.15 mm (the netclass clearance) from a foreign pad
            # instead of 0.25 mm.  Only sensible if vias are tented (mask over the via).
            self.relax_pad = relax
            try:
                got = self.find_tie(cx, cy, lidx, reach)
            finally:
                self.relax_pad = None
            tier = "relaxed-pad-margin"
        if got is None:
            return "fail", "no stub + via site within %.1f mm" % reach
        pts, kind = got
        pts = self.simplify(pts)
        gnd = U.get_net(self.b, "GND")
        length = 0.0
        for a, c2 in zip(pts, pts[1:]):
            U.add_track(self.b, gnd, layer, a[0], a[1], c2[0], c2[1], STUB_W)
            self.m.obst.add(Prim("seg", (a[0], a[1], c2[0], c2[1], STUB_W / 2), (lidx,), self.gnd, 0.15, static=True))
            self.stubs.append((a[0], a[1], c2[0], c2[1], lidx))
            length += math.hypot(c2[0] - a[0], c2[1] - a[1])
        if kind == "new":
            x, y = pts[-1]
            U.add_via(self.b, gnd, x, y, VIA_D, VIA_DRILL)
            self._add_via_rec(x, y, VIA_DRILL / 2, R, True)
            self.placed.append((x, y))
        return "tied", dict(kind=kind, length=round(length, 3), tier=tier, via=(round(pts[-1][0], 3), round(pts[-1][1], 3)))


# ----------------------------------------------------------------------- DRC probe
def isolated_gnd_pads(board, board_dir, work):
    """Fill a scratch copy with kicad-cli and return ([(ref, pad)], n_unconnected_gnd_items, n_unconnected_total).
    The in-memory board is saved to the scratch copy; the repo's files are never touched."""
    d = os.path.join(work, "probe")
    if os.path.isdir(d):
        shutil.rmtree(d)
    U.scratch_copy(board_dir, d)
    pcb = os.path.join(d, "bay-station.kicad_pcb")
    for fn in os.listdir(d):
        if fn.endswith(".kicad_pcb"):
            os.remove(os.path.join(d, fn))
    for fn in os.listdir(board_dir):
        if fn.endswith(".kicad_pro"):
            shutil.copy(os.path.join(board_dir, fn), os.path.join(d, "bay-station.kicad_pro"))
        if fn.endswith(".kicad_dru"):
            shutil.copy(os.path.join(board_dir, fn), os.path.join(d, "bay-station.kicad_dru"))
    U.save_board(board, pcb)
    out = os.path.join(d, "drc.json")
    U.run_drc(pcb, out, refill=True)
    by, unconn, raw = U.drc_summary(out)
    pads, n = set(), 0
    for x in unconn:
        txt = " | ".join(i["description"] for i in x["items"])
        if "[GND]" in txt:
            n += 1
            for i in x["items"]:
                m = re.match(r"Pad (\S+) \[GND\] of (\S+)", i["description"])
                if m:
                    pads.add((m.group(2), m.group(1)))
    return sorted(pads), n, len(unconn)


# ----------------------------------------------------------------------- zones
def _rule_area(board, name, layers, rect, no_vias, no_zone_fill, no_tracks=False):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    z.SetDoNotAllowZoneFills(no_zone_fill)
    z.SetDoNotAllowVias(no_vias)
    z.SetDoNotAllowTracks(no_tracks)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetZoneName(name)
    ol = z.Outline()
    ol.NewOutline()
    cx, cy, w, h = rect
    for (px, py) in ((cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)):
        ol.Append(U.iu(px), U.iu(py))
    board.Add(z)
    return z


def add_dw3210_cutouts(board):
    """Rule areas: no copper pour on F.Cu and In1.Cu, and no vias, under each DW3210
    body (DW3000 DS v1.1 s7.3.2 Fig 35).  Tracks stay allowed (the RF pad escape).  Also the
    DW3210_TIE_n areas (cut-out + 2 mm, nothing forbidden): the scope of the .kicad_dru rule that
    lets a GND pad-tie stub sit 0.15 mm from an RF50 neck."""
    have = {str(z.GetZoneName()) for z in board.Zones()}
    made = []
    for i, rect in enumerate(dw3210_cutouts(board)):
        if "DW3210_CUTOUT_%d" % i not in have:
            made.append(_rule_area(board, "DW3210_CUTOUT_%d" % i, (pcbnew.F_Cu, pcbnew.In1_Cu), rect, True, True))
    add_tie_areas(board)
    return made


def add_tie_areas(board):
    have = {str(z.GetZoneName()) for z in board.Zones()}
    n = 0
    for i, rect in enumerate(tie_areas(board)):
        if "DW3210_TIE_%d" % i not in have:
            _rule_area(board, "DW3210_TIE_%d" % i, (pcbnew.F_Cu,), rect, False, False)
            n += 1
    return n


def add_gnd_zones(board, inset=0.6):
    """Solid GND pours on In1.Cu and In2.Cu (the reference planes) and thinner pours on
    F.Cu and B.Cu.  Unfilled: fill a scratch copy with kicad-cli (never in-process).
    KIIDs are seeded so the file is reproducible.  Outer pours drop every island that is not
    connected to GND (an unconnected island is dead copper and shows up as an unconnected item)."""
    poly = U.outline_polygon(board)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs) + inset, max(xs) - inset, min(ys) + inset, max(ys) - inset
    gnd = U.get_net(board, "GND")
    made = []
    for prio, (layer, name) in enumerate(((U.IN1_CU, "GND_IN1"), (U.IN2_CU, "GND_IN2"),
                                          (U.F_CU, "GND_TOP"), (U.B_CU, "GND_BOT"))):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetZoneName(name)
        z.SetAssignedPriority(prio)
        z.SetMinThickness(U.iu(0.25))
        z.SetLocalClearance(U.iu(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if layer in (U.IN1_CU, U.IN2_CU) else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(U.iu(0.3))
        z.SetThermalReliefSpokeWidth(U.iu(0.4))
        if layer in (U.F_CU, U.B_CU):
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        else:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
            z.SetMinIslandArea(U.iu(1.0) * U.iu(10.0))
        ol = z.Outline()
        ol.NewOutline()
        for (px, py) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(U.iu(px), U.iu(py))
        board.Add(z)
        made.append(z)
    return made


def outer_pours_drop_islands(board):
    """Same island rule for a board whose pours already exist."""
    n = 0
    for z in board.Zones():
        if str(z.GetZoneName()) in ("GND_TOP", "GND_BOT") and z.GetIslandRemovalMode() != pcbnew.ISLAND_REMOVAL_MODE_ALWAYS:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            n += 1
    return n


def rescue(st, board, pads, reach=2.0, relax=RELAX_PAD):
    """Tie the given [(ref, pad)] GND pads.  Returns (tied {pad: info}, failed {pad: reason})."""
    tied, failed = {}, {}
    order = sorted(pads, key=lambda rp: _nearest_gnd(st, board, rp))
    for ref, num in order:
        res, info = st.tie_pad(ref, num, reach, relax)
        (tied if res == "tied" else failed)["%s.%s" % (ref, num)] = info
    return tied, failed


def _nearest_gnd(st, board, rp):
    for f in board.GetFootprints():
        if str(f.GetReference()) == rp[0]:
            for p in f.Pads():
                if str(p.GetNumber()) == str(rp[1]):
                    q = p.GetPosition()
                    x, y = U.mm(q.x), U.mm(q.y)
                    return min([math.hypot(x - v[0], y - v[1]) for v in st.gnd_vias] or [1e9])
    return 1e9


def main():
    global GEN_PITCH
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", required=True)
    ap.add_argument("--out")
    ap.add_argument("--zones", action="store_true", help="also add DW3210 cut-outs and the four GND pours")
    ap.add_argument("--cutouts-only", action="store_true", help="only add the DW3210 cut-out + tie rule areas (run BEFORE routing so the router and the GND fan-out keep out of them) and exit")
    ap.add_argument("--rescue", help="'auto' (find isolated GND pads with a kicad-cli fill of a scratch copy) or a JSON list of [ref, pad]")
    ap.add_argument("--rescue-only", action="store_true", help="with --rescue: do only the pad ties (no lattice, no zones)")
    ap.add_argument("--reach", type=float, default=2.0, help="max stub length pad centre -> via, mm (check_gates stub limit)")
    ap.add_argument("--pitch", type=float, default=GEN_PITCH)
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--workdir", help="scratch dir for the --rescue auto fill (outside the repo)")
    a = ap.parse_args()
    GEN_PITCH = a.pitch
    pcbnew.KIID.SeedGenerator(0x57175)
    board_dir = os.path.dirname(os.path.abspath(a.board))
    b = U.load_board(a.board)
    report = {}
    if a.cutouts_only:
        n = len(add_dw3210_cutouts(b))
        print("added %d DW3210 cut-out rule areas (+ tie areas)" % n)
        U.save_board(b, a.out or a.board)
        return
    st = Stitcher(b)
    if not a.rescue_only:
        stats = st.run()
        report["lattice"] = stats
        print("candidates/placed:", json.dumps(stats), "-> %d GND vias" % len(st.placed))
    if a.zones:
        add_dw3210_cutouts(b)
        add_gnd_zones(b)
    if a.rescue:
        add_tie_areas(b)
        st.tie = tie_areas(b)
        outer_pours_drop_islands(b)
        work = a.workdir or tempfile.mkdtemp(prefix="stitch_probe_")
        if os.path.abspath(work).startswith(U.REPO):
            raise SystemExit("workdir must be outside the repo")
        passes = []
        if a.rescue == "auto":
            for k in range(3):
                pads, n_gnd, n_all = isolated_gnd_pads(b, board_dir, work)
                print("pass %d: %d isolated GND pads (%d unconnected GND items, %d unconnected total)" % (k, len(pads), n_gnd, n_all))
                done = passes_failed(passes) | passes_tied(passes)    # a tied pad is listed again as the 'other end' of a pair
                tgt = [p for p in pads if "%s.%s" % p not in done]
                if not tgt:
                    passes.append(dict(pads=len(pads), tied={}, failed={}, gnd_items=n_gnd))
                    break
                tied, failed = rescue(st, b, tgt, a.reach)
                passes.append(dict(pads=len(pads), tied=tied, failed=failed, gnd_items=n_gnd))
                print("  tied %d, no route %d: %s" % (len(tied), len(failed), sorted(failed)))
            pads, n_gnd, n_all = isolated_gnd_pads(b, board_dir, work)
            print("after: %d isolated GND pads, %d unconnected GND items, %d unconnected total" % (len(pads), n_gnd, n_all))
            report["rescue_final"] = dict(isolated_pads=["%s.%s" % p for p in pads], gnd_items=n_gnd, unconnected_total=n_all)
        else:
            tied, failed = rescue(st, b, json.load(open(a.rescue)), a.reach)
            passes.append(dict(tied=tied, failed=failed))
            print("GND pad rescue: %d tied, %d without a site: %s" % (len(tied), len(failed), sorted(failed)))
        report["rescue_passes"] = passes
        if not a.workdir:
            shutil.rmtree(work, ignore_errors=True)
    U.save_board(b, a.out or a.board)
    if a.report:
        with open(a.report, "w") as f:
            json.dump(report, f, indent=1)


def passes_tied(passes):
    s = set()
    for p in passes:
        s |= set(p.get("tied", {}))
    return s


def passes_failed(passes):
    s = set()
    for p in passes:
        s |= set(p.get("failed", {}))
    return s


if __name__ == "__main__":
    main()
