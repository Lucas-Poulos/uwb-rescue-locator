#!/usr/bin/env python3
"""GND stitching vias across the whole bay-station board, DW3210 cut-outs and the
GND pours.  KiCad's python.  Run it on the board AFTER routing.

Spacing (derived, see docs/routing-plan.md section 6):
  * general lattice 5.0 mm.  Return-current / plane-stitching rule of thumb:
    pitch <= lambda_g/20 at the highest frequency that matters on the board.  The
    fastest radiated content that is not on a fenced RF line is LTE (<= ~2.2 GHz;
    lambda_g in the 4.5 / eps_eff ~3.4 FR4 stack ~ 74 mm -> /20 = 3.7 mm) and the
    1-2 ns CMOS edges (knee ~0.35/tr = 175-350 MHz, lambda_g ~ 0.5 m -> /20 = 25 mm).
    5 mm is lambda_g/15 at 2.2 GHz: a compromise against via count and routing
    area, tightened where it matters:
  * dense lattice 2.5 mm (= lambda_g/10 at 6.49 GHz is 2.5 mm: the user's RF rule)
    within 4 mm of any RF50 / CLK copper;
  * board edge: 2.5 mm pitch, 1.0 mm inset (edge clearance 0.5 + via radius 0.225
    + margin);
  * the 4 DW3210 bodies: no vias (DW3000 DS v1.1 s7.3.2 Fig 35: "keep clear of
    copper, tracks and vias" under the body on Top and Inner Layer 1).
RF fences along locked RF lines are placed by route_hs.via_fence (1.5 mm pitch).

Vias are 0.45/0.20 GND, through (JLCPCB min via 0.25/0.15 per jlcpcb skill table;
0.45 gives 0.125 mm annular ring).  Skipped near: any pad (0.25 mm edge to via edge:
keeps vias out of mask openings and solder wicking), tracks (0.15, 0.5 for RF50/CLK),
other vias/holes (0.25 drill to drill), the board edge, keep-out rule areas.
Candidate positions are nudged up to +-1.2 mm (spiral) before being skipped.

    kicad-python stitch.py --board SCRATCH.kicad_pcb [--out X] [--zones] [--pitch 5.0]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U
from mh_model import Model, Prim, F, B

VIA_D, VIA_DRILL = 0.45, 0.20
R = VIA_D / 2
PAD_MARGIN = 0.25
GEN_PITCH, DENSE_PITCH, DENSE_DIST = 5.0, 2.5, 4.0
EDGE_PITCH, EDGE_INSET = 2.5, 1.0
NUDGE = 1.2
CUTOUT = 5.5      # mm square under each DW3210 (QFN 5x5 body + 0.25 per side)


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


class Stitcher:
    def __init__(self, board):
        self.b = board
        self.m = Model(board, 0.25)
        self.gnd = [i for i, n in self.m.nets.items() if n["name"] == "GND"][0]
        self.cut = dw3210_cutouts(board)
        self.placed = []
        self.pads = []
        self.padclr = []
        for f in board.GetFootprints():
            for p in f.Pads():
                bb = p.GetBoundingBox()
                try:
                    lc = p.GetLocalClearance()
                    lc = U.mm(lc) if lc else 0.0
                except Exception:
                    lc = 0.0
                self.padclr.append(max(PAD_MARGIN, lc + 0.05))
                self.pads.append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()),
                                  p.HasHole(), U.mm(p.GetPosition().x), U.mm(p.GetPosition().y),
                                  U.mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2))
        self.vias = []         # (x, y, drill_r) of every via (existing + new)
        self.rfpts = []        # sample points of RF50/CLK copper
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                q = t.GetPosition()
                self.vias.append((U.mm(q.x), U.mm(q.y), U.mm(t.GetDrill()) / 2, U.mm(t.GetWidth()) / 2))
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
        for ni, n in self.m.nets.items():
            pass

    def legal(self, x, y):
        # DW3210 body cut-out
        for (cx, cy, w, h) in self.cut:
            if abs(x - cx) < w / 2 + R and abs(y - cy) < h / 2 + R:
                return False
        # pads
        for k, (x0, y0, x1, y1, th, px, py, hr) in enumerate(self.pads):
            if U.dist_pt_rect(x, y, x0, y0, x1, y1) < R + self.padclr[k]:
                return False
            if th and math.hypot(x - px, y - py) < R + hr + 0.25:
                return False
        # vias / holes (drill to drill 0.25, copper 0.05)
        for (vx, vy, dr, vr) in self.vias:
            d = math.hypot(x - vx, y - vy)
            if d < VIA_DRILL / 2 + dr + 0.25 or d < R + vr + 0.05:
                return False
        # tracks, edge, keepouts: exact obstacle test (both outer layers)
        for l in (F, B):
            if not self.m.obst.seg_ok(self.gnd, l, x, y, x, y, R, slack=-0.02):
                return False
        # inside the outline?
        if not U.point_in_poly(x, y, self.m.poly):
            return False
        return True

    def try_site(self, x, y):
        if self.legal(x, y):
            return (x, y)
        # spiral nudge
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

    def candidates(self):
        poly = self.m.poly
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        seen = set()
        out = []
        # general lattice, anchored at the board corner + edge inset
        gx = x0 + EDGE_INSET + 1.0
        x = gx
        while x < x1 - EDGE_INSET:
            y = y0 + EDGE_INSET + 1.0
            while y < y1 - EDGE_INSET:
                out.append((x, y, "gen"))
                y += GEN_PITCH
            x += GEN_PITCH
        # dense lattice near RF/CLK copper (offset half a pitch from the general one so they interleave)
        x = x0 + EDGE_INSET + 1.0 + DENSE_PITCH
        while x < x1 - EDGE_INSET:
            y = y0 + EDGE_INSET + 1.0 + DENSE_PITCH
            while y < y1 - EDGE_INSET:
                if self.near_rf(x, y):
                    out.append((x, y, "rf"))
                y += DENSE_PITCH
            x += DENSE_PITCH
        # edge ring
        n = len(poly)
        for i in range(n):
            a, c = poly[i], poly[(i + 1) % n]
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
            # inward normal: test which side is inside
            nx, ny = -uy, ux
            mx, my = a[0] + ux * L / 2 + nx * 0.5, a[1] + uy * L / 2 + ny * 0.5
            if not U.point_in_poly(mx, my, poly):
                nx, ny = -nx, -ny
            k = 0
            while k * EDGE_PITCH <= L - 2 * EDGE_INSET:
                d = EDGE_INSET + k * EDGE_PITCH
                out.append((a[0] + ux * d + nx * EDGE_INSET, a[1] + uy * d + ny * EDGE_INSET, "edge"))
                k += 1
        return out

    def run(self, locked=False):
        gnd_net = U.get_net(self.b, "GND")
        stats = {"gen": [0, 0], "rf": [0, 0], "edge": [0, 0]}
        for (x, y, kind) in self.candidates():
            stats[kind][0] += 1
            site = self.try_site(x, y)
            if site is None:
                continue
            U.add_via(self.b, gnd_net, site[0], site[1], VIA_D, VIA_DRILL, locked)
            self.vias.append((site[0], site[1], VIA_DRILL / 2, R))
            self.placed.append(site)
            stats[kind][1] += 1
        return stats


# ----------------------------------------------------------------------- zones
def add_dw3210_cutouts(board):
    """Rule areas: no copper pour on F.Cu and In1.Cu, and no vias, under each DW3210
    body (DW3000 DS v1.1 s7.3.2 Fig 35).  Tracks stay allowed (the RF pad escapes)."""
    made = []
    for i, (cx, cy, w, h) in enumerate(dw3210_cutouts(board)):
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.In1_Cu)
        z.SetLayerSet(ls)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName("DW3210_CUTOUT_%d" % i)
        ol = z.Outline()
        ol.NewOutline()
        for (px, py) in ((cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)):
            ol.Append(U.iu(px), U.iu(py))
        board.Add(z)
        made.append(z)
    return made


def add_gnd_zones(board, inset=0.6):
    """Solid GND pours on In1.Cu and In2.Cu (the reference planes) and thinner pours on
    F.Cu and B.Cu.  Unfilled: fill a scratch copy with kicad-cli (never in-process).
    KIIDs are seeded so the file is reproducible."""
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
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
        z.SetMinIslandArea(U.iu(1.0) * U.iu(10.0))
        ol = z.Outline()
        ol.NewOutline()
        for (px, py) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(U.iu(px), U.iu(py))
        board.Add(z)
        made.append(z)
    return made


def rescue_gnd_pads(st, board, pads, stub_w=0.2, reach=4.0):
    """GND pads the pours cannot reach (from a zone-filled DRC's unconnected list): a straight
    0.2 mm stub, any direction, on the pad's own layer to a legal via site.  Policy exception,
    same family as the router's GND fan-out stubs.  Vias keep out of the DW3210 cut-outs, so a
    chip pad inside one has to reach past its edge (reach <= 4 mm).  Returns (done, failed)."""
    gnd = U.get_net(board, "GND")
    done, failed = [], []
    for (ref, num) in pads:
        pad = None
        for f in board.GetFootprints():
            if str(f.GetReference()) == ref:
                for p in f.Pads():
                    if str(p.GetNumber()) == str(num):
                        pad = p
        if pad is None or not pad.IsOnLayer(pcbnew.F_Cu):
            failed.append((ref, num)); continue
        c = pad.GetPosition(); cx, cy = U.mm(c.x), U.mm(c.y)
        best = None            # (legs, via point): legs = [(x0, y0, x1, y1), ...]
        hw = stub_w / 2
        for (dx, dy) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if best:
                break
            t = 0.3
            while t <= reach and best is None:
                x, y = cx + dx * t, cy + dy * t
                if not st.m.obst.seg_ok(st.gnd, F, cx, cy, x, y, hw, slack=-0.02):
                    break                      # the straight leg is already blocked further out
                if st.legal(x, y):
                    best = ([(cx, cy, x, y)], (x, y))
                    break
                # second leg sideways (a via often only fits in the middle of a channel)
                for (ex, ey) in ((-dy, dx), (dy, -dx)):
                    for k in range(1, 7):
                        s2 = 0.2 * k
                        x2, y2 = x + ex * s2, y + ey * s2
                        if not st.m.obst.seg_ok(st.gnd, F, x, y, x2, y2, hw, slack=-0.02):
                            break
                        if st.legal(x2, y2):
                            best = ([(cx, cy, x, y), (x, y, x2, y2)], (x2, y2))
                            break
                    if best:
                        break
                t += 0.2
        if best is None:
            failed.append((ref, num)); continue
        legs, (x, y) = best
        for (ax, ay, bx, by) in legs:
            U.add_track(board, gnd, U.F_CU, ax, ay, bx, by, stub_w)
            st.m.obst.add(Prim("seg", (ax, ay, bx, by, stub_w / 2), (F,), st.gnd, 0.15, static=True))
        U.add_via(board, gnd, x, y, VIA_D, VIA_DRILL)
        st.vias.append((x, y, VIA_DRILL / 2, R))
        done.append((ref, num))
    return done, failed


def main():
    global GEN_PITCH
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", required=True)
    ap.add_argument("--out")
    ap.add_argument("--zones", action="store_true", help="also add DW3210 cut-outs and the four GND pours")
    ap.add_argument("--cutouts-only", action="store_true", help="only add the DW3210 cut-out rule areas (run BEFORE routing so the router and the GND fan-out keep out of them) and exit")
    ap.add_argument("--rescue", help="JSON list of [ref, pad] GND pads to tie to the planes with a stub + via")
    ap.add_argument("--rescue-only", action="store_true", help="with --rescue: do only the rescue stubs (no lattice, no zones)")
    ap.add_argument("--pitch", type=float, default=GEN_PITCH)
    a = ap.parse_args()
    GEN_PITCH = a.pitch
    pcbnew.KIID.SeedGenerator(0x57175)
    b = U.load_board(a.board)
    if a.cutouts_only:
        n = len(add_dw3210_cutouts(b))
        print("added %d DW3210 cut-out rule areas" % n)
        U.save_board(b, a.out or a.board)
        return
    st = Stitcher(b)
    if a.rescue and a.rescue_only:
        done, failed = rescue_gnd_pads(st, b, json.load(open(a.rescue)))
        print("GND pad rescue: %d tied, %d without a site: %s" % (len(done), len(failed), failed))
        U.save_board(b, a.out or a.board)
        return
    stats = st.run()
    print("candidates/placed:", json.dumps(stats), "-> %d GND vias" % len(st.placed))
    if a.rescue:
        done, failed = rescue_gnd_pads(st, b, json.load(open(a.rescue)))
        print("GND pad rescue: %d tied, %d without a site: %s" % (len(done), len(failed), failed))
    if a.zones:
        if not any(str(z.GetZoneName()).startswith("DW3210_CUTOUT") for z in b.Zones()):
            add_dw3210_cutouts(b)
        add_gnd_zones(b)
    U.save_board(b, a.out or a.board)


if __name__ == "__main__":
    main()
