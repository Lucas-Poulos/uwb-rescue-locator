#!/usr/bin/env python3
"""Place every footprint on bay-station.kicad_pcb, draw the board outline, no routing.

Run with KiCad 10's bundled python (the only one with pcbnew):

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        scripts/layout/place_bay_station.py [--dump /scratch/dir/layout.json] [--no-save]

Idempotent: the result depends only on the netlist/footprints already in the
board, never on where the footprints currently sit.  Hand-placed parts (ICs,
connectors, mechanical, the RF chains) come from fixed_table() below; every passive and
test pad is then placed by a deterministic greedy search that pulls it toward
the pin it serves, and a polish pass then re-seats every such part (all four
rotations) to minimise the MST length of its nets.  Metrics: scripts/layout/layout_metrics.py.
Rationale and citations: docs/layout-notes.md.

The BEFORE line it prints is the metric of the positions found in the file, so it only equals the
import baseline (HPWL 11217.6 / MST 9749.7 mm excl. GND, commit d7b3e2b) on the first run.

Gotchas handled (memory note kicad-pcbnew-headless-gotchas): BOARD.Save()
rewrites bay-station.kicad_pro, so the original bytes are restored after the
save; KIIDs are seeded; zones are saved unfilled.
"""
import argparse
import heapq
import json
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PCB = os.path.join(ROOT, "bay-station", "bay-station.kicad_pcb")
PRO = os.path.join(ROOT, "bay-station", "bay-station.kicad_pro")

# ---------------------------------------------------------------------------
# Board geometry (board-local mm, x east, y south, origin = top-left corner)
# ---------------------------------------------------------------------------
W, H = 150.0, 80.0         # outline (2026-11-18: was 128.1 x 68.1; see docs/layout-notes.md "History")

CORNER_R = 3.0              # rounded corners
OX, OY = 60.0, 50.0         # where the board origin sits on the KiCad sheet
GAP = 0.30                  # courtyard inflation per part -> >= 0.6 mm between parts
EDGE_MARGIN = 1.0           # courtyard to board edge for ordinary parts
GRID = 0.25
HOLE_KEEP = 4.6             # half-width of the standoff keep-out around each M3 hole centre (1.6 hole radius + 3 mm)

# Host cluster offset relative to the 128 x 68 design.  The BT840 U3 and its SWD headers stay at x = 57..71 on the
# north edge (its antenna keep-out sits clear of the SMA J23); HX < 0 pulls U20 and everything below it west,
# which shortens the UWB bus (13 mm of ratsnest per mm of x).
HX, HY = -8.0, 4.0
BAND = 6.0                  # centre band (TCXO, buffer, sensors) moves down with the taller array

# Anchor slots.  Chips: rot 0 = RF pins face south (SMA on the south edge),
# rot 180 = RF pins face north (SMA on the north edge).  XC is the block centre.
# The chain chip -> SMA is 14 mm, so the chip rows sit 14 mm from each edge: 52 mm apart on an 80 mm board.
XC = 26.0
CHIP_Y_S = H - 14.0
CHIP_Y_N = 14.0
SLOT = {  # anchor index -> (chip x, chip y, chip rot); chosen by a brute-force search over the 24
    # slot permutations x 4 buffer rotations for the shortest, most equal, non-crossing clock tree
    0: (XC + 11.0, CHIP_Y_S, 0),      # A0 centre anchor, south-east slot (nearest the host)
    1: (XC - 11.0, CHIP_Y_N, 180),
    2: (XC - 11.0, CHIP_Y_S, 0),
    3: (XC + 11.0, CHIP_Y_N, 180),
}
HOLES = {"H1": (4.0, 4.0), "H2": (4.0, H - 4.0), "H3": (W - 4.0, 4.0), "H4": (W - 4.0, H - 4.0)}
U31_POSE = (22.5, 42.0, 90)   # pose search (0 ratsnest crossings, equal buffer pin -> XTI straight distances 28.3-29.6 mm)

# Hand placed parts: ref -> (x, y, rot).  Everything else is greedy.  Refs that are not on the board are skipped.
ESSENTIAL = {"U3", "U20", "U10", "U11", "U30", "U31", "U1", "U8", "U40", "J1", "J2", "BT1", "J10", "J11", "J12",
             "H1", "H2", "H3", "H4"}


def fixed_table():
    f = {
        # --- mechanical: M3 holes in the four corners (3 mm standoff keep-out, HOLE_KEEP) ---------
        "H1": HOLES["H1"] + (0,), "H2": HOLES["H2"] + (0,), "H3": HOLES["H3"] + (0,), "H4": HOLES["H4"] + (0,),
        "FID1": (3.5, 13.0, 0), "FID2": (W - 3.5, 13.0, 0), "FID3": (3.5, H - 13.0, 0),
        # --- clock tree -------------------------------------------------------
        "U30": (13.0, 36.0 + BAND, 270),
        "U31": U31_POSE,
        # --- magnetometer / accelerometer (centre of the UWB block, far from power)
        "U10": (38.0, 33.0 + BAND, 0),
        "U11": (38.0, 38.5 + BAND, 0),
        # --- host -------------------------------------------------------------
        "U3": (57.0, 8.4, 0),            # BT840, antenna end on the north edge
        "J32": (71.0, 12.0, 90), "J35": (71.0, 5.5, 0),   # BT840 SWD / Tag-Connect east of the module
        "U20": (66.0 + HX, 28.0 + HY, 0),     # nRF9151: UWB pins face west, BT840 UART pins north, SIM/SWD south
        "J11": (82.5 + HX, 14.0 + HY, 0), "J10": (79.5 + HX, 25.5 + HY, 0),   # GNSS / LTE u.FL beside the nRF RF pins
        "J3": (60.5 + HX, 40.0 + HY, 0), "J34": (67.0 + HX, 49.5 + HY, 0), "J33": (62.0 + HX, 56.0 + HY, 90),
        "J12": (80.0 + HX, 48.0 + HY, 0),
        # --- power: east edge ---------------------------------------------------
        "J1": (W - 12.25, 22.0, 90),
        "J2": (W - 3.5, 42.0, 90),
        "BT1": (W - 6.3, 61.0, 90),
        "U1": (W - 16.0, 42.0, 0),
        "U8": (W - 26.0, 58.0, 0),
        "U40": (84.5 + HX, 33.0 + HY, 0),     # next to the nRF9151 so +VBAT_LTE stays short
        # --- user interface: LEDs / buttons along the north edge east of the RF connectors -------
        "D4": (W - 34.0, H - 3.5, 0), "D5": (W - 28.5, H - 3.5, 0), "D6": (W - 23.0, H - 3.5, 0),
        "D7": (100.0, 3.5, 0), "D400": (105.0, 3.5, 0), "D401": (110.0, 3.5, 0),
        "SW12": (101.0, 9.5, 0), "SW11": (92.0 + HX, 17.0 + HY, 0),
    }
    return f
# anchors are added to the fixed table programmatically (chips, SMAs)



# ---------------------------------------------------------------------------
def rot_pt(x, y, rot):
    """KiCad convention: +rot is CCW on screen with y pointing down."""
    r = rot % 360
    if r == 0:
        return x, y
    if r == 90:
        return y, -x
    if r == 180:
        return -x, -y
    if r == 270:
        return -y, x
    a = math.radians(r)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def snap(v, g=GRID):
    return round(v / g) * g


class Part:
    def __init__(self, fp):
        self.fp = fp
        self.ref = fp.GetReference()
        self.value = fp.GetValue()
        self.fpname = str(fp.GetFPID().GetLibItemName())
        self.pads = []   # (num, dx, dy, net)
        self.x = self.y = None
        self.rot = 0
        self.placed = False
        self.dnp = False

    @property
    def is_passive(self):
        return self.ref.startswith(("R", "C", "L", "FB", "TH")) and len(self.pads) == 2

    def world_pads(self, x=None, y=None, rot=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        rot = self.rot if rot is None else rot
        out = []
        for num, dx, dy, net in self.pads:
            rx, ry = rot_pt(dx, dy, rot)
            out.append((num, x + rx, y + ry, net))
        return out

    def rect(self, x=None, y=None, rot=None, infl=0.0):
        x = self.x if x is None else x
        y = self.y if y is None else y
        rot = self.rot if rot is None else rot
        x0, y0, x1, y1 = self.cy
        pts = [rot_pt(a, b, rot) for a, b in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (x + min(xs) - infl, y + min(ys) - infl, x + max(xs) + infl, y + max(ys) + infl)


def load_parts(board):
    parts = {}
    for fp in board.GetFootprints():
        p = Part(fp)
        fp.SetOrientationDegrees(0)
        pos = fp.GetPosition()
        for pad in fp.Pads():
            pp = pad.GetPosition()
            net = pad.GetNetname()
            if net.startswith("unconnected-") or net.startswith("Net-(") is False and net == "":
                net = ""
            p.pads.append((pad.GetNumber(), pcbnew.ToMM(pp.x - pos.x), pcbnew.ToMM(pp.y - pos.y), net))
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if cy.GetWidth() == 0:
            bb = fp.GetBoundingBox(False, False)
            cy = bb
        p.cy = (pcbnew.ToMM(cy.GetLeft() - pos.x), pcbnew.ToMM(cy.GetTop() - pos.y),
                pcbnew.ToMM(cy.GetRight() - pos.x), pcbnew.ToMM(cy.GetBottom() - pos.y))
        p.dnp = fp.IsDNP() if hasattr(fp, "IsDNP") else False
        parts[p.ref] = p
    return parts


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def net_points(parts, positions=None):
    nets = {}
    for ref, p in parts.items():
        if positions is not None:
            if ref not in positions:
                continue
            x, y, rot = positions[ref]
            wp = p.world_pads(x, y, rot)
        else:
            if not p.placed:
                continue
            wp = p.world_pads()
        for num, x, y, net in wp:
            if net == "" or net.startswith("unconnected-"):
                continue
            nets.setdefault(net, []).append((x, y, ref, num))
    return nets


def mst_len(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    inT = [False] * n
    d = [1e18] * n
    d[0] = 0.0
    tot = 0.0
    for _ in range(n):
        u = -1
        for i in range(n):
            if not inT[i] and (u < 0 or d[i] < d[u]):
                u = i
        inT[u] = True
        tot += d[u]
        for v in range(n):
            if not inT[v]:
                dd = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if dd < d[v]:
                    d[v] = dd
    return tot


def hpwl(pts):
    if len(pts) < 2:
        return 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def metrics(parts, positions=None):
    nets = net_points(parts, positions)
    out = {}
    for n, pts in nets.items():
        out[n] = (hpwl(pts), mst_len(pts), len(pts))
    return out


def summarize(m):
    sig_h = sum(v[0] for k, v in m.items() if k != "GND")
    sig_m = sum(v[1] for k, v in m.items() if k != "GND")
    gnd = m.get("GND", (0, 0, 0))
    return {"hpwl_excl_gnd": round(sig_h, 1), "mst_excl_gnd": round(sig_m, 1),
            "hpwl_gnd": round(gnd[0], 1), "mst_gnd": round(gnd[1], 1), "nets": len(m)}


# ---------------------------------------------------------------------------
class Placer:
    def __init__(self, parts):
        self.parts = parts
        self.rects = []          # placed inflated rects (x0,y0,x1,y1)
        self.bucket = {}
        self.nogo = []           # extra keep-out rects
        self.edge_ok = set()     # refs allowed to sit outside the inset area
        self.rec = {}            # ref -> arguments of the greedy call that placed it (re-used by polish)
        self.idx_of = {}

    # --- collision ------------------------------------------------------
    def _cells(self, r):
        B = 5.0
        for i in range(int(math.floor(r[0] / B)), int(math.floor(r[2] / B)) + 1):
            for j in range(int(math.floor(r[1] / B)), int(math.floor(r[3] / B)) + 1):
                yield (i, j)

    def add_rect(self, r, ref):
        idx = len(self.rects)
        self.rects.append((r, ref))
        self.idx_of[ref] = idx
        for c in self._cells(r):
            self.bucket.setdefault(c, []).append(idx)

    def collides(self, r, ignore=()):
        seen = set()
        for c in self._cells(r):
            for idx in self.bucket.get(c, ()):
                if idx in seen:
                    continue
                seen.add(idx)
                o, ref = self.rects[idx]
                if ref in ignore:
                    continue
                if r[0] < o[2] and r[2] > o[0] and r[1] < o[3] and r[3] > o[1]:
                    return True
        for o in self.nogo:
            if r[0] < o[2] and r[2] > o[0] and r[1] < o[3] and r[3] > o[1]:
                return True
        return False

    def inside(self, r):
        return (r[0] >= EDGE_MARGIN and r[1] >= EDGE_MARGIN and r[2] <= W - EDGE_MARGIN and r[3] <= H - EDGE_MARGIN)

    # --- placement ------------------------------------------------------
    def put(self, ref, x, y, rot, infl=GAP):
        p = self.parts[ref]
        p.x, p.y, p.rot, p.placed = x, y, rot, True
        self.add_rect(p.rect(infl=infl), ref)

    def remove(self, ref):
        """lift a part out of the collision map (its record is overwritten by the next put)"""
        self.rects[self.idx_of[ref]] = ((1e9, 1e9, 1e9 + 1, 1e9 + 1), "__dead__")

    def targets_for(self, ref, hint=None):
        """per pad: list of target points (placed pads on the same net)."""
        p = self.parts[ref]
        nets = net_points(self.parts)
        res = []
        for num, dx, dy, net in p.pads:
            pts = []
            if (hint and num in hint) or (net and net != "GND"):
                if hint and num in hint:
                    for h in hint[num]:
                        if h[0] == "pt":
                            pts.append((h[1], h[2]))
                            continue
                        hr, hp = h
                        hq = self.parts[hr]
                        if not hq.placed:
                            continue
                        for n2, x, y, n in hq.world_pads():
                            if n2 == hp:
                                pts.append((x, y))
                else:
                    for x, y, r2, n2 in nets.get(net, ()):
                        if r2 == ref:
                            continue
                        q = self.parts[r2]
                        pts.append((x, y, 1 if (q.is_passive or r2.startswith("TP")) else 0))
                    # prefer IC/connector pads when the net is big
                    ic = [(a, b) for a, b, c in pts if c == 0]
                    if ic:
                        pts = ic
                    else:
                        pts = [(a, b) for a, b, c in pts]
            res.append((num, dx, dy, net, pts))
        return res

    def greedy(self, ref, hint=None, home=None, rots=(0, 90), radius=9.0, weight=None, infl=GAP,
               prefer=None, bounds=None, step=GRID, center=None):
        p = self.parts[ref]
        self.rec[ref] = dict(hint=hint, weight=weight, rots=rots, infl=infl, bounds=bounds, step=step, home=home)
        tg = self.targets_for(ref, hint)
        allpts = [pt for _, _, _, _, pts in tg for pt in pts]
        if center:
            cx, cy = center
        elif allpts:
            cx = sum(a for a, b in allpts) / len(allpts)
            cy = sum(b for a, b in allpts) / len(allpts)
        elif home:
            cx, cy = home
        else:
            raise RuntimeError("no target for %s" % ref)
        if home and not allpts:
            pass
        wts = weight or {}
        R = radius
        while True:
            best = []
            n = int(R / step)
            gx0 = snap(cx, step)
            gy0 = snap(cy, step)
            for ix in range(-n, n + 1):
                x = gx0 + ix * step
                for iy in range(-n, n + 1):
                    y = gy0 + iy * step
                    for rot in rots:
                        cost = 0.0
                        for num, dx, dy, net, pts in tg:
                            if not pts:
                                continue
                            rx, ry = rot_pt(dx, dy, rot)
                            px, py = x + rx, y + ry
                            d = min((px - a) ** 2 + (py - b) ** 2 for a, b in pts)
                            cost += wts.get(num, 1.0) * math.sqrt(d)
                        if home:
                            cost += 0.02 * math.hypot(x - home[0], y - home[1])
                        if prefer:
                            cost += prefer(x, y, rot)
                        best.append((cost, x, y, rot))
            best.sort()
            for cost, x, y, rot in best:
                r = p.rect(x, y, rot, infl=infl)
                if not self.inside(r) and ref not in self.edge_ok:
                    continue
                if bounds and not (r[0] >= bounds[0] and r[1] >= bounds[1] and r[2] <= bounds[2] and r[3] <= bounds[3]):
                    continue
                if self.collides(r):
                    continue
                self.put(ref, x, y, rot, infl=infl)
                return cost
            R *= 1.7
            if R > (45 if bounds else 120):
                raise RuntimeError("cannot place " + ref)


# ---------------------------------------------------------------------------
# polish: re-seat every greedily placed part once the whole board exists
# ---------------------------------------------------------------------------
def _mst(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    d = [math.hypot(pts[0][0] - q[0], pts[0][1] - q[1]) for q in pts]
    used = [False] * n
    used[0] = True
    tot = 0.0
    for _ in range(n - 1):
        u = -1
        bd = 1e18
        for i in range(n):
            if not used[i] and d[i] < bd:
                bd, u = d[i], i
        used[u] = True
        tot += bd
        ux, uy = pts[u]
        for i in range(n):
            if not used[i]:
                dd = math.hypot(ux - pts[i][0], uy - pts[i][1])
                if dd < d[i]:
                    d[i] = dd
    return tot


POLISH_PASSES = 6
RF_NET = re.compile(r"LTE_RF_PIN|LTE_ANT|GNSS_RF|GNSS_ANT$|GNSS_LNA_A|GNSS_LNA_IN")
LARGE_NET = 9        # nets with more pads than this are costed by nearest-pad distance, not MST
# clock tree parts (precision-critical, positioned by the constructive pass) are not polished
POLISH_SKIP = {"R230", "R231", "R232", "R233", "R234", "C24", "C25", "C26", "C27", "C210", "C211", "C212", "C213", "C214"}


def polish(pl, parts, refs, passes=3, log=True):
    """Move each part (all four rotations) to the legal pose that minimises the MST length of the nets it
    sits on, plus a pull toward the hinted pins / the nearest connection.  Parts are visited in a fixed
    order and a move is taken only when it shortens the cost, so the result is deterministic."""
    P = parts
    members = {}
    for ref, p in P.items():
        for num, dx, dy, net in p.pads:
            if net and net != "GND" and not net.startswith("unconnected-"):
                members.setdefault(net, set()).add(ref)

    def context(ref):
        p = P[ref]
        rec = pl.rec[ref]
        wts = rec["weight"] or {}
        nets = {}
        for num, dx, dy, net in p.pads:
            if net and net != "GND" and not net.startswith("unconnected-"):
                nets.setdefault(net, []).append((num, dx, dy))
        ctx = []
        for net, own in nets.items():
            others = []
            for r2 in members[net]:
                if r2 == ref or not P[r2].placed:
                    continue
                for n2, x, y, nt in P[r2].world_pads():
                    if nt == net:
                        others.append((x, y))
            if not others:
                continue
            wm = max(wts.get(num, 1.0) for num, _, _ in own)
            if RF_NET.search(net):
                wm *= 4.0        # RF lines to the u.FL connectors: short and straight beats everything else
            ctx.append((others, own, len(others) + len(own) > LARGE_NET, wm))
        hints = []
        hint = rec["hint"]
        if hint:
            for num, dx, dy, net in p.pads:
                if num in hint:
                    pts = []
                    for h in hint[num]:
                        if h[0] == "pt":
                            pts.append((h[1], h[2]))
                        elif P[h[0]].placed:
                            pts += [(x, y) for n2, x, y, nt in P[h[0]].world_pads() if n2 == h[1]]
                    if pts:
                        hints.append((dx, dy, pts, wts.get(num, 1.0)))
        return ctx, hints

    def cost(ctx, hints, x, y, rot):
        c = 0.0
        for others, own, large, wm in ctx:
            pp = []
            for num, dx, dy in own:
                rx, ry = rot_pt(dx, dy, rot)
                pp.append((x + rx, y + ry))
            if large:
                s = 0.0
                for a, b in pp:
                    s += min(math.hypot(a - o[0], b - o[1]) for o in others)
                c += wm * s
            else:
                near = 0.0
                for a, b in pp:
                    near += min(math.hypot(a - o[0], b - o[1]) for o in others)
                c += wm * (_mst(others + pp) + 0.1 * near)
        for dx, dy, pts, w in hints:
            rx, ry = rot_pt(dx, dy, rot)
            a, b = x + rx, y + ry
            c += w * min(math.hypot(a - o[0], b - o[1]) for o in pts)
        return c

    ROT_PREF = {0: 0.0, 180: 0.0005, 90: 0.001, 270: 0.0015}
    moved_total = 0
    for it in range(passes):
        moved = 0
        gain = 0.0
        for ref in refs:
            if ref not in pl.rec or ref in POLISH_SKIP:
                continue
            p = P[ref]
            rec = pl.rec[ref]
            ctx, hints = context(ref)
            if not ctx and not hints:
                continue
            step = rec["step"]
            is_tp = ref.startswith("TP")
            rots = (0, 90, 180, 270) if (p.is_passive or not is_tp and len(p.pads) <= 6) else rec["rots"]
            if is_tp:
                rots = (0,)
            cur = cost(ctx, hints, p.x, p.y, p.rot) + ROT_PREF.get(p.rot % 360, 0)
            allp = [q for o, _, _, _ in ctx for q in o]
            cen = (sum(a for a, b in allp) / len(allp), sum(b for a, b in allp) / len(allp)) if allp else (p.x, p.y)
            centres = [(p.x, p.y, 3.0 if not is_tp else 10.0)]
            if math.hypot(cen[0] - p.x, cen[1] - p.y) > 2.0:
                centres.append((cen[0], cen[1], 4.0 if not is_tp else 10.0))
            cands = {}
            for cx, cy, R in centres:
                n = int(R / step)
                gx, gy = snap(cx, step), snap(cy, step)
                for ix in range(-n, n + 1):
                    x = gx + ix * step
                    for iy in range(-n, n + 1):
                        y = gy + iy * step
                        for rot in rots:
                            if (x, y, rot) not in cands:
                                cands[(x, y, rot)] = cost(ctx, hints, x, y, rot) + ROT_PREF.get(rot, 0)
            if not cands:
                continue
            pl.remove(ref)
            order = sorted(cands.items(), key=lambda kv: kv[1])
            bounds = rec["bounds"]
            placed = False
            for (x, y, rot), c in order:
                if c >= cur - 0.02:
                    break
                r = p.rect(x, y, rot, infl=rec["infl"])
                if not pl.inside(r) and ref not in pl.edge_ok:
                    continue
                if bounds and not (r[0] >= bounds[0] and r[1] >= bounds[1] and r[2] <= bounds[2] and r[3] <= bounds[3]):
                    continue
                if pl.collides(r):
                    continue
                pl.put(ref, x, y, rot, infl=rec["infl"])
                moved += 1
                gain += cur - c
                placed = True
                break
            if not placed:
                pl.put(ref, p.x, p.y, p.rot, infl=rec["infl"])
        moved_total += moved
        if log:
            print("polish pass %d: %d parts moved, cost -%.1f" % (it + 1, moved, gain))
        if moved == 0:
            break


# ---------------------------------------------------------------------------
def build_fixed(parts):
    fixed = fixed_table()
    for n in range(4):
        cx, cy, rot = SLOT[n]
        fixed["U%d" % (4 + n)] = (cx, cy, rot)
        # SMA at the board edge, pad 1 on the RF1 pin x
        if rot == 0:
            fixed["J%d" % (20 + n)] = (cx + 1.0, H, 180)
        else:
            fixed["J%d" % (20 + n)] = (cx - 1.0, 0.0, 0)
    return fixed


def chain_positions(n):
    """RF chain from DW3210 RF1 to the SMA: identical template for all four anchors."""
    cx, cy, rot = SLOT[n]
    s = 1.0 if rot == 0 else -1.0       # +1: chain runs south, -1: runs north
    xl = cx + (1.0 if rot == 0 else -1.0)  # RF1 pin x
    vr = 270 if rot == 0 else 90      # vertical series parts: pad 1 toward the chip
    pos = {}
    pos["C%d" % (47 + 8 * n)] = (xl, cy + s * 4.25, vr)           # 2.0 pF series, at the pin
    pos["C%d" % (200 + 2 * n)] = (xl + s * 1.75, cy + s * 5.5, 0 if rot == 0 else 180)   # DNP pi shunt A
    pos["R%d" % (220 + n)] = (xl, cy + s * 6.5, vr)             # 0R pi series
    pos["C%d" % (201 + 2 * n)] = (xl + s * 1.75, cy + s * 7.75, 0 if rot == 0 else 180)    # DNP pi shunt B at the SMA
    # RF2 termination 49R9 under pin 13 (x - 1.0 of centre => mirrored for rot 180)
    x13 = cx - 1.0 if rot == 0 else cx + 1.0
    pos["R%d" % (33 + n)] = (x13, cy + s * 4.25, vr)
    return pos


def main():
    global HX, HY, U31_POSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="write layout JSON (board-local mm) for the renderer")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--hx", type=float, help="host cluster x offset (default %.1f)" % HX)
    ap.add_argument("--hy", type=float, help="host cluster y offset (default %.1f)" % HY)
    ap.add_argument("--u31", type=float, nargs=3, metavar=("X", "Y", "ROT"), help="override the buffer pose (trials)")
    ap.add_argument("--keep-copper", action="store_true",
                    help="keep tracks/vias/zones (they are stale once parts move; default is to strip them)")
    ap.add_argument("--out", help="write the placed board here instead of overwriting bay-station.kicad_pcb")
    args = ap.parse_args()
    if args.u31:
        U31_POSE = tuple(args.u31)
    if args.hx is not None:
        HX = args.hx
    if args.hy is not None:
        HY = args.hy

    pro_bytes = open(PRO, "rb").read()
    pcbnew.KIID.SeedGenerator(20261118)
    board = pcbnew.LoadBoard(PCB)
    parts = load_parts(board)
    before_pos = {}
    for ref, p in parts.items():
        pass
    # "before": positions as found in the file
    board_b = pcbnew.LoadBoard(PCB)
    before = {}
    for fp in board_b.GetFootprints():
        if not fp.GetReference().startswith("TP"):
            before[fp.GetReference()] = (pcbnew.ToMM(fp.GetX()), pcbnew.ToMM(fp.GetY()), fp.GetOrientationDegrees())
    m_before = metrics(parts, before)    # test pads excluded (they are parked / bottom-side)

    pl = Placer(parts)
    fixed = build_fixed(parts)
    for ref in sorted(fixed):
        if ref not in parts:
            if ref in ESSENTIAL:
                raise SystemExit("essential ref missing from the board: " + ref)
            print("note: %s is not on the board, skipped" % ref)
            del fixed[ref]
    for n in range(4):
        pl.edge_ok.add("J%d" % (20 + n))
    for ref in ("J1", "J2", "BT1", "J10", "J11", "J12", "J13"):
        pl.edge_ok.add(ref)
    for hx, hy in HOLES.values():       # standoff keep-out around the corner M3 holes (greedy parts only)
        pl.nogo.append((hx - HOLE_KEEP, hy - HOLE_KEEP, hx + HOLE_KEEP, hy + HOLE_KEEP))

    # 1. hand placed
    for ref, (x, y, rot) in fixed.items():
        pl.put(ref, x, y, rot, infl=GAP)
    # RF chains
    for n in range(4):
        for ref, (x, y, rot) in chain_positions(n).items():
            pl.put(ref, x, y, rot, infl=GAP)   # the chain's own 0.3-0.35 mm internal gaps are fixed by its 9 mm length

    # BT840 printed antenna: nothing but the module within 10 mm either side of it (Fanstel keep-out is
    # copper-free under/around the antenna end; the exact distance is NOT verified -- see docs/layout-notes.md)
    u3 = parts["U3"]
    pl.nogo.append((u3.x - 10.0, -5.0, u3.x + 10.0, u3.y - 1.0))
    # greedy passes are added below (see place_all)
    place_all(pl, parts)

    park_test_pads(parts)
    positions = {r: (p.x, p.y, p.rot) for r, p in parts.items() if not r.startswith("TP")}
    m_after = metrics(parts, positions)
    print("BEFORE", summarize(m_before))
    print("AFTER ", summarize(m_after))

    if args.dump:
        dump = {"W": W, "H": H, "parts": {}, "nets_before": {k: v for k, v in m_before.items()},
                "nets_after": {k: v for k, v in m_after.items()}}
        for ref, p in parts.items():
            dump["parts"][ref] = {"x": p.x, "y": p.y, "rot": p.rot, "cy": p.cy, "value": p.value,
                                  "pads": p.world_pads(), "fp": p.fpname, "parked": p.ref.startswith("TP")}
        json.dump(dump, open(args.dump, "w"))

    if args.no_save:
        return
    apply_to_board(board, parts, strip_copper=not args.keep_copper)
    if args.out:
        board.Save(args.out)
        refresh_note(args.out)
    else:
        board.Save(PCB)
        open(PRO, "wb").write(pro_bytes)
        refresh_note(PCB)


OWNER = {}
for _r in ("R150", "R151", "R152", "R153", "R154", "R407", "R408", "R409", "R410", "R411", "R414", "R415"):
    OWNER[_r] = "2" if _r.startswith("R4") else "1"
for _b in (204, 208, 212, 216):
    for _n in range(4):
        OWNER["R%d" % (_b + _n)] = "1"

HOME_FALLBACK = [("/Regulation/", (118, 52)), ("/Connectivity/", (70 + HX, 28 + HY)), ("/Programming", (56 + HX, 38 + HY)),
                 ("/Orientation/", (38, 33 + BAND)), ("/Clock", (27, 38 + BAND)), ("/UWB", (27, 38 + BAND))]


def home_of(p):
    for _, _, _, net in p.pads:
        for key, h in HOME_FALLBACK:
            if net.startswith(key):
                return h
    return (104 + HX, 45 + HY)


def anchor_bounds(n, grow=0.0):
    """Box the anchor's supply / strap parts must stay in.  Room beyond the old 25 x 20 mm box is given on the
    outer (west or east) side and toward the centre band; the 22 mm column pitch is unchanged."""
    cx, cy, rot = SLOT[n]
    ox = 3.0 if cx < XC else 0.0          # extra room west of the west column
    ex = 3.0 if cx > XC else 0.0          # extra room east of the east column
    if rot == 0:
        return (cx - 13 - ox - grow, cy - 13 - grow, cx + 12 + ex + grow, min(H - 1.0, cy + 8.5 + grow))
    return (cx - 12 - ox - grow, max(1.0, cy - 8.5 - grow), cx + 13 + ex + grow, cy + 13 + grow)


def pad_xy(part, num):
    return [(x, y) for n, x, y, net in part.world_pads() if n == num][0]


def place_all(pl, parts):
    P = parts

    def wts(ref, extra=None):
        w = {}
        if ref in OWNER:
            w = {"1": 0.15, "2": 0.15}
            w[OWNER[ref]] = 1.0
        if extra:
            w.update(extra)
        return w

    def G(ref, hint=None, home=None, w=None, **kw):
        if ref not in P:
            return                       # absent from the board (e.g. removed in stage 1): nothing to place
        if P[ref].placed:
            return
        home = home or home_of(P[ref])
        try:
            pl.greedy(ref, hint=hint, home=home, weight=wts(ref, w), **kw)
        except RuntimeError:
            kw.pop("bounds", None)
            print("WARNING: %s did not fit its bounds" % ref)
            pl.greedy(ref, hint=hint, home=home, weight=wts(ref, w), **kw)

    # ---- 0. clock tree R/C pairs first: 22R at the buffer pin, 2200 pF at the XTI pin, so each path is the
    #         straight buffer -> chip run plus two pads (equal-length goal, positioning.md) ---------------
    for n in range(4):
        c = "U%d" % (4 + n)
        ypin = [(x, y) for num, x, y, net in P["U31"].world_pads() if net.endswith("CLK_Y%d" % n)][0]
        xpin = pad_xy(P[c], "21")
        G("R%d" % (231 + n), hint={"1": [("pt", ypin[0], ypin[1])], "2": [("pt", xpin[0], xpin[1])]}, w={"1": 8, "2": 3},
          home=ypin, radius=4.0,
          rots=(0, 90, 180, 270), center=ypin)
        G("C%d" % (24 + n), hint={"2": [(c, "21")]}, w={"2": 8, "1": 1}, home=SLOT[n][:2], radius=5.0,
          rots=(0, 90, 180, 270), bounds=anchor_bounds(n), center=xpin)

    # ---- 1. UWB anchors: supply caps on their pins, straps, clock caps --------------------
    for n in range(4):
        c = "U%d" % (4 + n)
        cx, cy, rot = SLOT[n]
        home = (cx, cy)
        seq = [
            ("C%d" % (28 + n), {"1": [(c, "22")]}, {"1": 3}),
            ("C%d" % (24 + n), {"2": [(c, "21")]}, {"2": 3}),
            ("C%d" % (45 + 8 * n), {"1": [(c, "27")]}, {"1": 3}),
            ("C%d" % (41 + 8 * n), {"1": [(c, "28")]}, {"1": 3}),
            ("FB%d" % (1 + n), {"1": [(c, "29")], "2": [(c, "28")]}, None),
            ("C%d" % (40 + 8 * n), {"1": [(c, "29")]}, {"1": 3}),
            ("C%d" % (42 + 8 * n), {"1": [(c, "26")]}, {"1": 3}),
            ("C%d" % (43 + 8 * n), {"1": [(c, "26")]}, {"1": 2}),
            ("C%d" % (44 + 8 * n), {"1": [(c, "26")]}, {"1": 1.5}),
            ("C%d" % (46 + 8 * n), {"1": [(c, "38")]}, {"1": 3}),
            ("R%d" % (200 + n), {"2": [(c, "23")]}, {"1": 0.05}),
            ("R%d" % (25 + n), {"1": [(c, "1")]}, None),
            ("R%d" % (208 + n), {"1": [(c, "1")]}, None),
            ("R%d" % (10 + 2 * n), {"1": [(c, "5")]}, None),
            ("R%d" % (11 + 2 * n), {"1": [(c, "2")]}, None),
            ("R%d" % (204 + n), {"1": [(c, "37")]}, None),
            ("R%d" % (212 + n), {"1": [(c, "33")]}, None),
            ("R%d" % (216 + n), {"1": [(c, "9")]}, None),
        ]
        bnd = anchor_bounds(n)
        for ref, hint, w in seq[:10]:
            G(ref, hint=hint, home=home, w=w, radius=7.0, bounds=bnd)
        for ref, hint, w in seq[10:]:
            G(ref, hint=hint, home=home, w=w, radius=7.0, bounds=bnd)
    # A0 fallback crystal (DNP): tight to XTI/XTO of U4
    G("Y1", hint={"1": [("U4", "22")], "3": [("U4", "21")]}, home=(SLOT[0][0], SLOT[0][1]), rots=(0, 90, 180, 270))
    G("C208", hint={"1": [("U4", "22")]}, home=(SLOT[0][0], SLOT[0][1]))
    G("C209", hint={"1": [("U4", "21")]}, home=(SLOT[0][0], SLOT[0][1]))

    # ---- 2. clock tree --------------------------------------------------------------------
    ck = (U31_POSE[0], U31_POSE[1])
    G("R230", home=ck)
    for ref, h in (("C213", ("U31", "6")), ("C214", ("U31", "6")), ("C210", ("U30", "6")), ("C211", ("U30", "6"))):
        G(ref, hint={"1": [h]}, w={"1": 3}, home=ck)
    for n in range(4):
        G("R%d" % (231 + n), home=ck, w={"1": 8, "2": 0.3}, radius=5.0, rots=(0, 90, 180, 270))   # already placed in step 0
    for ref in ("R226", "R229", "R225", "R227", "R228", "C215"):
        G(ref, home=ck)
    G("C212", hint={"1": [("R225", "2")]}, home=ck)
    G("R402", home=ck)
    for n in range(4):
        G("R%d" % (403 + n), hint={"2": [("U%d" % (4 + n), "21")]}, w={"2": 3}, home=SLOT[n][:2], radius=7.0)

    # ---- 3. orientation sensors -----------------------------------------------------------
    for ref, h in (("C400", None), ("C401", ("U10", "3")), ("C402", ("U10", "9")), ("C35", ("U10", "10")),
                   ("C403", ("U11", "2")), ("C404", ("U11", "9")), ("C36", ("U11", "10"))):
        G(ref, hint={"1": [h]} if h else None, w={"1": 3}, home=(38, 36 + BAND))
    for ref in ("R407", "R408", "R409", "R410", "R414", "R415", "R411"):
        G(ref, home=(38, 36 + BAND))

    # ---- 4. the remaining blocks, each confined to its own floorplan region -----------------
    def group(name, refs, bounds, home, rots=None, radius=8.0, hints=None, w=None):
        hints = hints or {}
        w = w or {}
        for ref in refs:
            if ref not in P or P[ref].placed:
                continue
            is_p = P[ref].is_passive
            r = rots or ((0, 90) if is_p else (0, 90, 180, 270))
            G(ref, hint=hints.get(ref), home=home, w=w.get(ref), rots=r, radius=radius, bounds=bounds)

    R = lambda a, b: ["R%d" % i for i in range(a, b + 1)]
    C = lambda a, b: ["C%d" % i for i in range(a, b + 1)]

    # host: nRF9151 supply / reset / strap / bridge / SPI series parts
    host_b = (50 + HX, 14, 90 + HX, 58 + HY)
    group("host_crit", ["FB10", "C102", "C103", "C100", "C101", "C109", "C104", "C110", "C107", "C108", "C111", "R101",
                       "R103", "R104", "U21", "R102", "C105", "C106", "R155"],
          host_b, (66 + HX, 29 + HY), radius=8.0)
    # GNSS front end and LTE feed near the north edge
    group("gnss", ["U24", "U25", "C127", "L101", "C123", "C128", "C129", "R123", "R124", "R125", "L100", "R122", "C122",
                   "C124", "C125", "C126", "D100"], (70 + HX, 1, 106 + HX, 30 + HY), (78 + HX, 17 + HY), radius=8.0)
    group("lte", ["R130", "R131", "C130", "C131", "D101", "J13"], (70 + HX, 14 + HY, 106 + HX, 36 + HY), (80 + HX, 23 + HY), radius=8.0)
    # SIM and its ESD / series parts
    group("sim", ["U22", "R106", "R107", "R108", "R109", "U23", "R110", "R111", "R112", "R113", "C112"],
          (64 + HX, 36 + HY, 106 + HX, H - 1), (76 + HX, 42 + HY), radius=8.0)
    # regulation: U40 (LTE rail) next to the nRF, U8 (3V3) toward the power block
    group("u40", ["C300", "L300", "C301", "C302", "R302", "R306", "R307", "R308", "R309", "R310", "R311", "R312",
                  "J31", "R304"], (76 + HX, 18 + HY, 114 + HX, 58 + HY), (86 + HX, 33 + HY), radius=8.0)
    group("u8", ["C20", "L1", "C21", "C22", "R8", "R9", "R300", "R301", "J30", "R303", "R305", "C303",
                 "C5", "C6", "C7"], (W - 52, 40, W - 2, H - 1), (W - 26, 62), radius=8.0)
    # charger / battery / inputs
    group("charger", ["D1", "D2", "D3", "U2", "Q1", "TH1", "C1", "C2", "C3", "C4", "R1", "R2", "R3", "R4", "R5",
                      "R6", "R7", "R29", "R30", "R31"], (W - 42, 14, W, H), (W - 14, 48), radius=8.0)
    group("host", [
                   "R150", "R151", "R152", "R153", "R154", "R140", "R141", "R142", "R143", "R144", "R145",
                   "R37", "R38", "R39", "R224", "R313", "R315", "C304", "R103", "R104", "U21", "R102", "C105",
                   "C106", "R155", "R314"],
          host_b, (66 + HX, 29 + HY), radius=8.0,
          hints={"R224": {"1": [("U20", "2")]}})
    group("ui", ["R32", "R400", "R401"], (92, 1, 118, 15), (105, 8), radius=8.0)
    group("dbg", ["SW2"], (52 + HX, 34 + HY, 82 + HX, H - 2), (62 + HX, 44 + HY), radius=10.0)
    # array entry bank on +3V3 at the east edge of the UWB block, centre band
    for ref in ("C72", "C73", "C74"):
        G(ref, hint={"1": [("pt", 47.0, 38.0 + BAND)]}, home=(47, 38 + BAND), bounds=(42, 26, 56, H - 26), radius=8.0)

    # ---- 5. anything not covered above (should be empty) --------------------------------------------
    left = sorted(r for r, p in P.items() if not p.placed and not r.startswith("TP"))
    if left:
        print("WARNING: unplaced by groups:", left)
    for ref in left:
        G(ref, rots=(0, 90), radius=10.0)

    # ---- 7. polish -----------------------------------------------------------------------------
    polish(pl, parts, sorted(pl.rec), passes=POLISH_PASSES)


# Test pads: all TP* footprints are kept off the top placement.  The bottom-side test-pad script (functions rows,
# scripts/layout/testpoint_labels.json) places them later; until then they are parked off-board in a fixed grid so
# they neither overlap anything nor feed the wirelength metrics.
PARK_X0, PARK_Y0, PARK_DX, PARK_DY, PARK_COLS = W + 10.0, 5.0, 4.0, 4.0, 8


def park_test_pads(parts):
    tps = sorted((r for r in parts if r.startswith("TP")), key=lambda r: (len(r), r))
    for i, ref in enumerate(tps):
        p = parts[ref]
        p.x = PARK_X0 + (i % PARK_COLS) * PARK_DX
        p.y = PARK_Y0 + (i // PARK_COLS) * PARK_DY
        p.rot = 0
        p.placed = False
    return tps


def refresh_note(path):
    """The Cmts.User stackup note still said 'no outline / no footprints'.  Rewrite that sentence in the saved file."""
    txt = open(path, encoding="utf-8").read()
    old_start = "No board outline exists yet"
    old_end = "See bay-station/README.md."
    if old_start in txt:
        i = txt.index(old_start)
        j = txt.index(old_end, i) + len(old_end)
        new = ("Board outline, 4x M3 holes, 3 fiducials and the footprint placement are drawn by\\n"
               "scripts/layout/place_bay_station.py (see docs/layout-notes.md). Nothing is routed and\\n"
               "no zone is filled; the Section 7.3 copper rules above are still open for routing.")
        txt = txt[:i] + new + txt[j:]
        open(path, "w", encoding="utf-8").write(txt)


def apply_to_board(board, parts, strip_copper=True):
    mm = pcbnew.FromMM

    def V(x, y):
        return pcbnew.VECTOR2I(mm(x + OX), mm(y + OY))

    for ref, p in parts.items():
        fp = p.fp
        fp.SetOrientationDegrees(p.rot)
        fp.SetPosition(V(p.x, p.y))

    # drop the rule areas written by an earlier run (done first: touching Zones() after Remove() of a
    # drawing segfaults KiCad 10.0.5's bindings)
    old_zones = list(board.Zones())
    old_drawings = list(board.GetDrawings())
    for z in old_zones:
        # KO_* are redrawn below.  Everything else at board level (GND pours, DW3210_CUTOUT_* rule areas from
        # stitch.py) has the old outline / old chip positions and is stale once the parts move.
        if z.GetZoneName().startswith("KO_") or strip_copper:
            board.Remove(z)
    if strip_copper:
        # routing and stitching vias were made for the previous placement and would short the new one
        for t in list(board.GetTracks()):
            board.Remove(t)

    # Edge.Cuts: rounded rectangle
    for d in old_drawings:
        if d.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(d)

    R = CORNER_R
    k = R * (1 - math.sqrt(0.5))
    segs = [((R, 0), (W - R, 0)), ((W, R), (W, H - R)), ((W - R, H), (R, H)), ((0, H - R), (0, R))]
    arcs = [((0, R), (k, k), (R, 0)), ((W - R, 0), (W - k, k), (W, R)),
            ((W, H - R), (W - k, H - k), (W - R, H)), ((R, H), (k, H - k), (0, H - R))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
    for a, m, b in arcs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(V(*a), V(*m), V(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    # keep-out rule areas ------------------------------------------------------------

    def keepout(name, x0, y0, x1, y1, layers, vias=True):
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetZoneName(name)
        ls = pcbnew.LSET()
        for l in layers:
            ls.AddLayer(l)
        z.SetLayerSet(ls)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ps = pcbnew.SHAPE_POLY_SET()
        ps.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ps.Append(mm(x + OX), mm(y + OY))
        z.SetOutline(ps)
        board.Add(z)

    u3 = parts["U3"]
    keepout("KO_BT840_antenna", u3.x - 7.5, 0.0, u3.x + 7.5, u3.y - 1.3,
            [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu])
    for n in range(4):
        cx, cy, rot = SLOT[n]
        keepout("KO_DW3210_A%d_body" % n, cx - 2.0, cy - 2.0, cx + 2.0, cy + 2.0, [pcbnew.F_Cu, pcbnew.In1_Cu])


if __name__ == "__main__":
    main()
