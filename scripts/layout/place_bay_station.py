#!/usr/bin/env python3
"""Place every footprint on bay-station.kicad_pcb, draw the board outline, no routing.

Run with KiCad 10's bundled python (the only one with pcbnew):

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        scripts/layout/place_bay_station.py [--dump /scratch/dir/layout.json] [--no-save]

Idempotent: the result depends only on the netlist/footprints already in the
board, never on where the footprints currently sit.  Hand-placed parts (ICs,
connectors, mechanical, the RF chains) come from FIXED below; every passive and
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
W, H = 128.0, 68.0          # outline

CORNER_R = 3.0              # rounded corners
OX, OY = 60.0, 50.0         # where the board origin sits on the KiCad sheet
GAP = 0.20                  # courtyard inflation per part -> >= 0.6 mm between parts
EDGE_MARGIN = 1.0           # courtyard to board edge for ordinary parts
GRID = 0.25

# Anchor slots.  Chips: rot 0 = RF pins face south (SMA on the south edge),
# rot 180 = RF pins face north (SMA on the north edge).  XC is the block centre.
XC = 26.0
CHIP_Y_S = 54.0
CHIP_Y_N = 14.0
SLOT = {  # anchor index -> (chip x, chip y, chip rot); chosen by a brute-force search over the 24
    # slot permutations x 4 buffer rotations for the shortest, most equal, non-crossing clock tree
    0: (XC + 11.0, CHIP_Y_S, 0),      # A0 centre anchor, south-east slot (nearest the host)
    1: (XC - 11.0, CHIP_Y_N, 180),
    2: (XC - 11.0, CHIP_Y_S, 0),
    3: (XC + 11.0, CHIP_Y_N, 180),
}

# Hand placed parts: ref -> (x, y, rot).  Everything else is greedy.
FIXED = {
    # --- mechanical -------------------------------------------------------
    "H1": (XC, 3.5, 0), "H2": (XC, H - 3.5, 0),
    "H3": (W - 4.0, 3.5, 0), "H4": (W - 4.0, H - 3.5, 0),
    "FID1": (3.5, 3.5, 0), "FID2": (W - 3.5, 25.5, 0), "FID3": (3.5, H - 3.5, 0),
    # --- clock tree -------------------------------------------------------
    "U30": (13.0, 36.0, 270),
    "U31": (24.5, 35.0, 90),    # pose from a search that equalises the four buffer pin -> XTI straight distances (23.0-23.8 mm)
    # --- magnetometer / accelerometer (centre of the UWB block, far from power)
    "U10": (38.0, 33.0, 0),
    "U11": (38.0, 38.5, 0),
    # --- host -------------------------------------------------------------
    "U3": (57.0, 8.4, 0),            # BT840, antenna end on the north edge
    "J32": (71.0, 12.0, 90), "J35": (71.0, 5.5, 0),   # BT840 SWD / Tag-Connect east of the module
    "U20": (66.0, 28.0, 0),          # nRF9151: UWB pins face west, BT840 UART pins north, SIM/SWD south
    "J11": (82.5, 14.0, 0), "J10": (79.5, 25.5, 0),    # GNSS / LTE u.FL: vertical-mating, so beside the nRF RF pins, not on an edge
    "J3": (60.5, 40.0, 0), "J34": (67.0, 49.5, 0), "J33": (62.0, 56.0, 90),
    "J12": (80.0, 48.0, 0),
    # --- power ------------------------------------------------------------
    "J1": (W - 12.25, 16.0, 90),
    "J2": (W - 3.5, 34.0, 90),
    "BT1": (W - 6.3, 54.0, 90),
    "U1": (112.0, 34.0, 0),
    "U8": (104.0, 48.0, 0),
    "U40": (84.5, 33.0, 0),            # next to the nRF9151 so +VBAT_LTE stays short
    # --- user interface: LEDs / buttons along the north edge east of the RF connectors -------
    "D4": (104.0, 64.5, 0), "D5": (109.5, 64.5, 0), "D6": (115.0, 64.5, 0),
    "D7": (96.0, 3.5, 0), "D400": (101.0, 3.5, 0), "D401": (106.0, 3.5, 0),
    "SW12": (97.0, 9.5, 0), "SW11": (92.0, 17.0, 0),
}
# anchors are added to FIXED programmatically (chips, SMAs)

# test pads / parts that get explicit attractors (ref -> list of (ref, pad)) -------------
HINT = {}


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
    fixed = dict(FIXED)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="write layout JSON (board-local mm) for the renderer")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--out", help="write the placed board here instead of overwriting bay-station.kicad_pcb")
    args = ap.parse_args()

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
        before[fp.GetReference()] = (pcbnew.ToMM(fp.GetX()), pcbnew.ToMM(fp.GetY()), fp.GetOrientationDegrees())
    m_before = metrics(parts, before)

    pl = Placer(parts)
    fixed = build_fixed(parts)
    for ref in fixed:
        if ref not in parts:
            raise SystemExit("unknown ref in FIXED: " + ref)
    for n in range(4):
        pl.edge_ok.add("J%d" % (20 + n))
    for ref in ("J1", "J2", "BT1", "J10", "J11", "J12", "J13"):
        pl.edge_ok.add(ref)

    # 1. hand placed
    for ref, (x, y, rot) in fixed.items():
        infl = 0.0 if ref.startswith("J2") and len(ref) == 3 and ref[1] in "0123" else GAP
        pl.put(ref, x, y, rot, infl=infl)
    # RF chains
    for n in range(4):
        for ref, (x, y, rot) in chain_positions(n).items():
            pl.put(ref, x, y, rot, infl=0.15)

    # BT840 printed antenna: nothing but the module within 10 mm either side of it (Fanstel keep-out is
    # copper-free under/around the antenna end; the exact distance is NOT verified -- see docs/layout-notes.md)
    u3 = parts["U3"]
    pl.nogo.append((u3.x - 10.0, -5.0, u3.x + 10.0, u3.y - 1.0))
    # greedy passes are added below (see place_all)
    place_all(pl, parts)

    positions = {r: (p.x, p.y, p.rot) for r, p in parts.items()}
    m_after = metrics(parts, positions)
    print("BEFORE", summarize(m_before))
    print("AFTER ", summarize(m_after))

    if args.dump:
        dump = {"W": W, "H": H, "parts": {}, "nets_before": {k: v for k, v in m_before.items()},
                "nets_after": {k: v for k, v in m_after.items()}}
        for ref, p in parts.items():
            dump["parts"][ref] = {"x": p.x, "y": p.y, "rot": p.rot, "cy": p.cy, "value": p.value,
                                  "pads": p.world_pads(), "fp": p.fpname}
        json.dump(dump, open(args.dump, "w"))

    if args.no_save:
        return
    apply_to_board(board, parts)
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

HOME_FALLBACK = [("/Regulation/", (92, 45)), ("/Connectivity/", (70, 28)), ("/Programming", (56, 38)),
                 ("/Orientation/", (38, 36)), ("/Clock", (27, 38)), ("/UWB", (27, 38))]


def home_of(p):
    for _, _, _, net in p.pads:
        for key, h in HOME_FALLBACK:
            if net.startswith(key):
                return h
    return (100, 45)


def anchor_bounds(n, grow=0.0):
    cx, cy, rot = SLOT[n]
    if rot == 0:
        return (cx - 13 - grow, cy - 10 - grow, cx + 12 + grow, min(H - 1.0, cy + 8.5 + grow))
    return (cx - 12 - grow, max(1.0, cy - 8.5 - grow), cx + 13 + grow, cy + 10 + grow)


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
        G("R%d" % (231 + n), hint={"1": [("pt", ypin[0], ypin[1])], "2": [("pt", xpin[0], xpin[1])]}, w={"1": 8, "2": 1},
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
        place_tp_list(pl, parts, ["TP%d" % (500 + 7 * n + k) for k in range(7)])   # claim pad space before straps
        for ref, hint, w in seq[10:]:
            G(ref, hint=hint, home=home, w=w, radius=7.0, bounds=bnd)
    # A0 fallback crystal (DNP): tight to XTI/XTO of U4
    G("Y1", hint={"1": [("U4", "22")], "3": [("U4", "21")]}, home=(SLOT[0][0], SLOT[0][1]), rots=(0, 90, 180, 270))
    G("C208", hint={"1": [("U4", "22")]}, home=(SLOT[0][0], SLOT[0][1]))
    G("C209", hint={"1": [("U4", "21")]}, home=(SLOT[0][0], SLOT[0][1]))

    # ---- 2. clock tree --------------------------------------------------------------------
    ck = (24.5, 35)
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
        G(ref, hint={"1": [h]} if h else None, w={"1": 3}, home=(38, 36))
    for ref in ("R407", "R408", "R409", "R410", "R414", "R415", "R411"):
        G(ref, home=(38, 36))

    # ---- 4. the remaining blocks, each confined to its own floorplan region -----------------
    def group(name, refs, bounds, home, rots=None, radius=8.0, hints=None, w=None):
        hints = hints or {}
        w = w or {}
        for ref in refs:
            if P[ref].placed:
                continue
            is_p = P[ref].is_passive
            r = rots or ((0, 90) if is_p else (0, 90, 180, 270))
            G(ref, hint=hints.get(ref), home=home, w=w.get(ref), rots=r, radius=radius, bounds=bounds)

    R = lambda a, b: ["R%d" % i for i in range(a, b + 1)]
    C = lambda a, b: ["C%d" % i for i in range(a, b + 1)]

    # host: nRF9151 supply / reset / strap / bridge / SPI series parts
    group("host_crit", ["FB10", "C102", "C103", "C100", "C101", "C109", "C104", "C110", "C107", "C108", "C111", "R101",
                       "R103", "R104", "U21", "R102", "C105", "C106", "R155"],
          (50, 14, 86, 47), (66, 29), radius=8.0)
    # GNSS front end and LTE feed near the north edge
    group("gnss", ["U24", "U25", "C127", "L101", "C123", "C128", "C129", "R123", "R124", "R125", "L100", "R122", "C122",
                   "C124", "C125", "C126", "D100"], (70, 1, 100, 26), (78, 17), radius=8.0)
    group("lte", ["R130", "R131", "C130", "C131", "D101", "J13"], (70, 14, 100, 32), (80, 23), radius=8.0)
    # SIM and its ESD / series parts
    group("sim", ["U22", "R106", "R107", "R108", "R109", "U23", "R110", "R111", "R112", "R113", "C112"],
          (64, 34, 98, 66), (76, 42), radius=8.0)
    # regulation: U40 (LTE rail) next to the nRF, U8 (3V3) toward the power block
    group("u40", ["C300", "L300", "C301", "C302", "R302", "R306", "R307", "R308", "R309", "R310", "R311", "R312",
                  "J31", "R304"], (76, 18, 106, 48), (86, 33), radius=8.0)
    # host test pads claim their space after the RF / supply parts (those paths are the critical ones),
    # and before the series links, pull-ups and DNP options, which can sit a little further out
    group("u8", ["C20", "L1", "C21", "C22", "R8", "R9", "R300", "R301", "J30", "R303", "R305", "C303",
                 "C5", "C6", "C7"], (90, 44, 120, 74), (104, 54), radius=8.0)
    # charger / battery / inputs
    group("charger", ["D1", "D2", "D3", "U2", "Q1", "TH1", "C1", "C2", "C3", "C4", "R1", "R2", "R3", "R4", "R5",
                      "R6", "R7", "R29", "R30", "R31"], (100, 16, W, H), (114, 44), radius=8.0)
    # every test pad claims its slot next to its pin/net now: after all pin-critical parts (decoupling, hot
    # loops, clock, RF) and before the series links, pull-ups, DNP options and UI parts, which can sit further out
    place_test_pads(pl, parts)
    group("host", [
                   "R150", "R151", "R152", "R153", "R154", "R140", "R141", "R142", "R143", "R144", "R145",
                   "R37", "R38", "R39", "R224", "R313", "R315", "C304", "R103", "R104", "U21", "R102", "C105",
                   "C106", "R155", "R314"],
          (50, 14, 86, 47), (66, 29), radius=8.0,
          hints={"R224": {"1": [("U20", "2")]}})
    group("ui", ["R32", "R400", "R401"], (92, 1, 114, 15), (101, 8), radius=8.0)
    group("dbg", ["SW2"], (52, 34, 74, 62), (62, 44), radius=10.0)
    # array entry bank on +3V3 at the east edge of the UWB block, centre band
    for ref in ("C72", "C73", "C74"):
        G(ref, hint={"1": [("pt", 47.0, 38.0)]}, home=(47, 38), bounds=(42, 24, 56, 52), radius=8.0)
    for ref in ("SW2", "SW11", "SW12"):
        pass

    # ---- 5. anything not covered above (should be empty) --------------------------------------------
    left = sorted(r for r, p in P.items() if not p.placed and not r.startswith("TP"))
    if left:
        print("WARNING: unplaced by groups:", left)
    for ref in left:
        G(ref, rots=(0, 90), radius=10.0)

    # ---- 6. test pads ----------------------------------------------------------------------
    place_test_pads(pl, parts)

    # ---- 7. polish -----------------------------------------------------------------------------
    polish(pl, parts, sorted(pl.rec), passes=POLISH_PASSES)


TP_EXPLICIT = {  # (host pads that name a pin follow the pin, so no coordinates here)
    "TP1": ("R300", "2"), "TP101": ("U4", "29"), "TP102": ("U3", "9"), "TP2": ("U1", "1"), "TP103": ("U8", "4"),
    "TP100": ("U20", "14"), "TP104": ("J2", "A9"), "TP414": ("U1", "3"),
    "TP3": ("U31", "4"), "TP110": ("pt", XC, 31.0), "TP4": ("pt", 50.0, 56.0),
    "TP113": ("U1", "4"), "TP114": ("U8", "2"), "TP115": ("U20", "1"), "TP116": ("pt", XC, 27.0),
    "TP117": ("J3", "3"), "TP118": ("D5", "1"), "TP119": ("U10", "6"),
}
TP_LATE = ("TP3", "TP110", "TP4", "TP113", "TP114", "TP115", "TP116", "TP117", "TP118", "TP119")
TP_AFTER = {"TP111": ("TP10", "1"), "TP112": ("TP12", "1")}
TP_STEP = 1.25
TP_GAP = 0.21          # 2.09 mm courtyard + 2 x 0.21 = 2.51 mm centre pitch: the 2.5 mm spring-probe spacing
HINTS_USED = {}


def place_tp_list(pl, parts, refs):
    """Place the named test pads (skipping ones already placed) near the pin/net each one measures."""
    P = parts
    for ref in refs:
        if ref not in P or P[ref].placed:
            continue
        p = P[ref]
        hint = None
        if ref in TP_EXPLICIT:
            e = TP_EXPLICIT[ref]
            hint = {"1": [e if e[0] == "pt" else (e[0], e[1])]}
        elif ref in TP_AFTER:
            hint = {"1": [TP_AFTER[ref]]}
        num = int(ref[2:])
        bnd = None
        if 500 <= num <= 527:
            bnd = anchor_bounds((num - 500) // 7, grow=6.0)
        infl = TP_GAP if p.cy[2] - p.cy[0] < 2.2 else GAP
        try:
            pl.greedy(ref, hint=hint, home=home_of(p), rots=(0,), radius=8.0, infl=infl, bounds=bnd, step=TP_STEP)
        except RuntimeError:
            print("WARNING: %s did not fit its bounds" % ref)
            pl.greedy(ref, hint=hint, home=home_of(p), rots=(0,), radius=8.0, infl=infl, step=TP_STEP)
        HINTS_USED[ref] = hint


def place_test_pads(pl, parts):
    P = parts
    tps = sorted((r for r in P if r.startswith("TP")), key=lambda r: int(r[2:]))
    order = [r for r in tps if r not in TP_AFTER and r not in TP_LATE]
    order += [r for r in tps if r in TP_LATE]
    order += [r for r in tps if r in TP_AFTER]
    place_tp_list(pl, parts, order)
    refine_test_pads(pl, parts, HINTS_USED)


def refine_test_pads(pl, parts, hints_used):
    """Pairwise-swap test pads between the slots the greedy pass found, while that shortens the total
    distance to their nets.  Pads of equal size only, so every swap stays collision free."""
    P = parts
    tps = [r for r in P if r.startswith("TP")]
    tgt = {}
    for r in tps:
        tg = pl.targets_for(r, hints_used.get(r))
        tgt[r] = [pt for _, _, _, _, pts in tg for pt in pts]

    def cost(r, x, y):
        pts = tgt[r]
        if not pts:
            return 0.0
        return min(math.hypot(x - a, y - b) for a, b in pts)

    def size(r):
        x0, y0, x1, y1 = P[r].cy
        return round(x1 - x0, 2)

    improved = True
    passes = 0
    while improved and passes < 12:
        improved = False
        passes += 1
        order = sorted(tps, key=lambda r: -cost(r, P[r].x, P[r].y))
        for a in order:
            ca = cost(a, P[a].x, P[a].y)
            if ca < 3.0:
                continue
            best = None
            for b in tps:
                if b == a or size(b) != size(a):
                    continue
                cb = cost(b, P[b].x, P[b].y)
                new = cost(a, P[b].x, P[b].y) + cost(b, P[a].x, P[a].y)
                gain = (ca + cb) - new
                if gain > 0.5 and (best is None or gain > best[0]):
                    best = (gain, b)
            if best:
                b = best[1]
                P[a].x, P[b].x = P[b].x, P[a].x
                P[a].y, P[b].y = P[b].y, P[a].y
                improved = True
    # the swaps moved pads between slots: re-register every test pad at its final position
    for r in tps:
        pl.remove(r)
        pl.put(r, P[r].x, P[r].y, P[r].rot, infl=pl.rec[r]["infl"])


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


def apply_to_board(board, parts):
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
        if z.GetZoneName().startswith("KO_"):
            board.Remove(z)

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
        ch = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ch.Append(mm(x + OX), mm(y + OY))
        ch.SetClosed(True)
        z.Outline().AddOutline(ch)
        board.Add(z)

    u3 = parts["U3"]
    keepout("KO_BT840_antenna", u3.x - 7.5, 0.0, u3.x + 7.5, u3.y - 1.3,
            [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu])
    for n in range(4):
        cx, cy, rot = SLOT[n]
        keepout("KO_DW3210_A%d_body" % n, cx - 2.0, cy - 2.0, cx + 2.0, cy + 2.0, [pcbnew.F_Cu, pcbnew.In1_Cu])


if __name__ == "__main__":
    main()
