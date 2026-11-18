#!/usr/bin/env python3
"""Generate and verify the silkscreen of the bay-station PCB.

Run with KiCad's bundled interpreter (the only one that can import pcbnew):

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/layout/silkscreen.py bay-station/bay-station.kicad_pcb [--out other.kicad_pcb] [--log log.txt]
  ... silkscreen.py board.kicad_pcb --check-only        # run only the checker

The script is generic (it reads the placed board; nothing is hard-coded to
coordinates) and idempotent: every item it creates lives in the board group
SILK_AUTO (or is an OrientationMark_* footprint) and is deleted and rebuilt on
each run; footprint reference/value text is reset from scratch each run.
Rules and their sources: docs/silkscreen-notes.md.

Order of work (earlier = higher priority for space):
  1. station-frame arrow, sensor axes glyphs, board text blocks (large)
  2. pin-1 dots / cathode bars / +,- polarity marks
  3. function labels (J/SW/LED/links/DNP), RF labels, keep-out marking
  4. test-point net-name labels
  5. reference designators (ICs/connectors first, passives last)
  6. component values on silk (non-passives only, where they fit)
  7. enforcement: the checker runs; any generated item that still violates
     is removed (reference -> moved to F.Fab) and logged.
"""
import argparse
import math
import os
import re
import sys

import pcbnew
from pcbnew import (FromMM, ToMM, VECTOR2I, F_SilkS, F_Fab, F_Cu, F_Mask, F_CrtYd,
                    Edge_Cuts, PCB_TEXT, PCB_SHAPE, PCB_GROUP, SHAPE_T_SEGMENT,
                    SHAPE_T_CIRCLE, SHAPE_T_RECT, SHAPE_T_POLY, SHAPE_T_ARC)

HERE = os.path.dirname(os.path.abspath(__file__))
PRETTY = os.path.normpath(os.path.join(HERE, "..", "..", "bay-station", "libs", "bay_station.pretty"))

# ---------------------------------------------------------------- rules ----
# JLCPCB PCB capabilities page (jlcpcb.com/capabilities/pcb-capabilities, fetched
# 2026-11-18): silkscreen line width >= 0.15 mm, text height >= 1.0 mm,
# silkscreen-to-pad clearance >= 0.15 mm.  Board-edge and hole clearance for
# silkscreen are NOT stated there; EDGE_CLR is this project's own choice.
TEXT_SIZES = [(1.0, 0.15), (0.8, 0.15)]   # (height, stroke); 0.8 is below JLC's 1.0 min -> logged
LINE_W = 0.15
PAD_CLR_PLAN = 0.20     # planning clearance silk-bbox to pad (JLC min 0.15 + bbox slop)
PAD_CLR_CHECK = 0.15    # checker clearance (JLC min)
EDGE_CLR = 0.50         # planning: keep silk this far inside the board edge
EDGE_CLR_CHECK = 0.30
SILK_GAP = 0.05         # half of the minimum gap between two silk items (box inflation)
DOT_D = 0.5
GROUP_NAME = "SILK_AUTO"
MARK_PREFIX = "OrientationMark_"
REPO_URL = "Lucas-Poulos/uwb-rescue-locator"   # git remote origin

PASSIVE_RE = re.compile(r"^(R|C|L|FB|TH)\d+")
SMALL_PASSIVE_FP = re.compile(r"^(R|C|L|D)_(0201|0402|0603)")

# ref -> list of alternative label line-lists, longest first.  Sources in docs/silkscreen-notes.md.
LABELS = {
    "J1": [["5V DC IN", "CENTRE +", "5V ONLY"], ["5V DC IN", "CTR +"], ["5V IN"]],
    "J2": [["USB-C", "5V PWR ONLY"], ["USB-C 5V"], ["USB-C"]],
    "J3": [["SWD 9151"], ["SWD"]],
    "J32": [["SWD BT840"], ["SWD BLE"]],
    "J33": [["UART", "1=GND"], ["UART"]],
    "J34": [["TC SWD", "DNP"], ["DNP"]],
    "J35": [["TC BLE", "DNP"], ["DNP"]],
    "J30": [["PPK 3V3", "DNP"], ["DNP"]],
    "J31": [["PPK VBAT", "DNP"], ["DNP"]],
    "J10": [["LTE u.FL"], ["LTE"]],
    "J11": [["GNSS u.FL"], ["GNSS"]],
    "J12": [["SIM"]],
    "J13": [["LTE TEST", "DNP"], ["DNP"]],
    "J20": [["A0 CTR", "TWR"], ["A0 CTR"], ["A0"]],
    "J21": [["A1 TDoA"], ["A1"]],
    "J22": [["A2 TDoA"], ["A2"]],
    "J23": [["A3 TDoA"], ["A3"]],
    "BT1": [["BATT"]],
    "SW2": [["RESET"]],
    "SW11": [["RESET BLE"], ["RST BLE"]],
    "SW12": [["USER"]],
    "D4": [["CHG"]], "D5": [["FULL"]], "D6": [["PG"]],
    "D7": [["SYS"]], "D400": [["LTE"]], "D401": [["LINK"]],
    "R300": [["CUT 3V3"], ["CUT"]],
    "R302": [["CUT VBAT"], ["CUT"]],
    "R402": [["FIT"]], "R403": [["FIT"]], "R404": [["FIT"]], "R405": [["FIT"]], "R406": [["FIT"]],
    "U10": [["MAG"]],
    "U11": [["ACC"]],
    "H1": [["M3"]], "H2": [["M3"]], "H3": [["M3"]], "H4": [["M3"]],
}
RF_NOTE = (["J20", "J21", "J22", "J23"], [["UWB CH5 6.5GHz"], ["UWB CH5"]])
MAG_NOTE = ("U10", [["MAG: NO FERROUS", ">10mA KEEP OFF"], ["NO FERROUS"]])
# BT840 antenna region in footprint-local mm (Fanstel_BT840 footprint descr: "antenna region is y < -1.5 mm")
KEEPOUTS = {"Fanstel_BT840": ((-7.0, -8.0, 7.0, -1.5), [["BLE ANT", "NO METAL", "KEEP OUT"], ["NO METAL"]])}
PIN1_SKIP_FP = ("BarrelJack", "USB_C", "SMA_", "U.FL", "Fiducial", "MountingHole", "SW_", "TestPoint",
                "L_", "R_", "C_", "Crystal", "Tag-Connect")
BOARD_BLOCKS = [
    ("title", [["UWB RESCUE LOCATOR", "BAY STATION"], ["UWB LOCATOR", "BAY STATION"]]),
    ("rev", [["REV -   YYYY-MM-DD"]]),
    ("url", [["github.com/" + REPO_URL.split("/")[0], "/" + REPO_URL.split("/")[1]]]),
    ("proto", [["PROTOTYPE", "NOT CERTIFIED"]]),
]


# ------------------------------------------------------------ geometry -----
def box_of(bb):
    return (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))


def infl(b, m):
    return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def inside(a, outer):
    return a[0] >= outer[0] and a[1] >= outer[1] and a[2] <= outer[2] and a[3] <= outer[3]


class Hash:
    def __init__(self, cell=4.0):
        self.cell = cell
        self.g = {}

    def _cells(self, b):
        c = self.cell
        for i in range(int(math.floor(b[0] / c)), int(math.floor(b[2] / c)) + 1):
            for j in range(int(math.floor(b[1] / c)), int(math.floor(b[3] / c)) + 1):
                yield (i, j)

    def add(self, b, owner, kind):
        it = (b, owner, kind)
        for c in self._cells(b):
            self.g.setdefault(c, []).append(it)

    def query(self, b):
        seen = set()
        for c in self._cells(b):
            for it in self.g.get(c, ()):
                if id(it) not in seen and overlap(it[0], b):
                    seen.add(id(it))
                    yield it


def shape_boxes(sh):
    """Boxes (mm) covering one PCB_SHAPE; unfilled rects/polys become their edges."""
    t = sh.GetShape()
    w = ToMM(sh.GetWidth()) / 2.0
    if t == SHAPE_T_RECT and not sh.IsAnyFill():
        x0, y0, x1, y1 = box_of(sh.GetBoundingBox())
        e = w
        return [(x0, y0, x1, y0 + 2 * e), (x0, y1 - 2 * e, x1, y1), (x0, y0, x0 + 2 * e, y1), (x1 - 2 * e, y0, x1, y1)]
    if t == SHAPE_T_SEGMENT:
        a, b = sh.GetStart(), sh.GetEnd()
        # split long diagonal segments into pieces so the box does not over-block
        n = max(1, int(math.hypot(ToMM(a.x - b.x), ToMM(a.y - b.y)) / 1.0))
        out = []
        for i in range(n):
            x0 = ToMM(a.x + (b.x - a.x) * i / n)
            y0 = ToMM(a.y + (b.y - a.y) * i / n)
            x1 = ToMM(a.x + (b.x - a.x) * (i + 1) / n)
            y1 = ToMM(a.y + (b.y - a.y) * (i + 1) / n)
            out.append((min(x0, x1) - w, min(y0, y1) - w, max(x0, x1) + w, max(y0, y1) + w))
        return out
    return [box_of(sh.GetBoundingBox())]


def fnum(v):
    return v if isinstance(v, float) else float(v)


# --------------------------------------------------------------- state -----
class Ctx:
    def __init__(self, b, args):
        self.b = b
        self.args = args
        self.log = []
        self.hash = Hash()
        self.gen = []            # generated board-level items
        self.tpl = {}
        self.scratch = PCB_TEXT(b)
        self.scratch.SetLayer(F_SilkS)
        self.scratch.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        self.scratch.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        self.board_box = None
        self.fps = {}
        self.stats = {}
        self.tp_dropped = set()

    def say(self, msg):
        self.log.append(msg)

    def count(self, k):
        self.stats[k] = self.stats.get(k, 0) + 1

    # text template: (offx, offy, w, h) of the stroked glyph bbox relative to the text position
    def text_tpl(self, s, size, th, ang):
        key = (s, size, th, ang)
        if key not in self.tpl:
            t = self.scratch
            t.SetText(s)
            t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
            t.SetTextThickness(FromMM(th))
            t.SetTextAngleDegrees(ang)
            t.SetPosition(VECTOR2I(0, 0))
            bb = t.GetEffectiveTextShape().BBox()
            x0, y0, x1, y1 = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
            pad = th / 2.0
            self.tpl[key] = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
        return self.tpl[key]

    def free(self, box, owner, strict=True, margin=SILK_GAP, own_silk_ok=False):
        bb = infl(box, margin)
        if self.board_box and not inside(bb, self.board_box):
            return False
        for (_b, o, kind) in self.hash.query(bb):
            if kind == "crtyd":
                if o == owner or not strict:
                    continue
                return False
            if kind == "silk" and own_silk_ok and o == owner:
                continue
            return False
        return True

    def commit(self, box, owner, kind="gen"):
        self.hash.add(infl(box, SILK_GAP), owner, kind)


# ------------------------------------------------------ board scanning -----
def load_obstacles(c):
    b = c.b
    ex = []
    for d in b.GetDrawings():
        if d.GetLayer() == Edge_Cuts:
            ex.append(box_of(d.GetBoundingBox()))
    if ex:
        eb = union(ex)
        c.board_box = (eb[0] + EDGE_CLR, eb[1] + EDGE_CLR, eb[2] - EDGE_CLR, eb[3] - EDGE_CLR)
        c.outline = eb
    else:
        c.outline = None
        c.say("WARNING: no Edge.Cuts outline on the board; edge clearance is not enforced and board text "
              "blocks are placed within the part bounding box + 3 mm.")
    pads_all = []
    for f in b.GetFootprints():
        ref = f.GetReference()
        c.fps[ref] = f
        if f.IsFlipped():
            c.say("WARNING: %s is on the back side; skipped (front-side silkscreen only)." % ref)
        for p in f.Pads():
            sme = 0.0
            try:
                sme = ToMM(p.GetSolderMaskExpansion(F_Mask))
            except Exception:
                pass
            pb = infl(box_of(p.GetBoundingBox()), max(PAD_CLR_PLAN, sme + 0.05))
            c.hash.add(pb, ref, "pad")
            pads_all.append(box_of(p.GetBoundingBox()))
        cy = f.GetCourtyard(F_CrtYd)
        if cy.OutlineCount():
            cb = box_of(cy.BBox())
        else:
            pb = [box_of(p.GetBoundingBox()) for p in f.Pads()]
            cb = infl(union(pb), 0.25) if pb else box_of(f.GetBoundingBox(False))
        c.hash.add(cb, ref, "crtyd")
        c.fp_box = getattr(c, "fp_box", {})
        c.fp_box[ref] = cb
        for g in f.GraphicalItems():
            if g.GetLayer() != F_SilkS:
                continue
            if isinstance(g, PCB_SHAPE) or g.GetClass() == "PCB_SHAPE":
                for sb in shape_boxes(g):
                    c.hash.add(infl(sb, 0.1), ref, "silk")
            else:
                try:
                    c.hash.add(infl(box_of(g.GetEffectiveTextShape().BBox()), 0.1), ref, "silk")
                except Exception:
                    c.hash.add(infl(box_of(g.GetBoundingBox()), 0.1), ref, "silk")
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            r = ToMM(t.GetWidth(F_Cu)) / 2.0 + 0.2
            x, y = ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)
            c.hash.add((x - r, y - r, x + r, y + r), "via", "via")
    for d in b.GetDrawings():
        if d.GetLayer() == F_SilkS:      # pre-existing board-level silk (not ours; ours are cleared first)
            c.hash.add(infl(box_of(d.GetBoundingBox()), 0.1), "board", "silk")
    if c.board_box is None:
        allb = list(c.fp_box.values())
        u = union(allb)
        c.board_box = (u[0] - 3, u[1] - 3, u[2] + 3, u[3] + 3)


def clear_generated(c):
    b = c.b
    n = 0
    marks = [f for f in b.GetFootprints() if str(f.GetFPID().GetLibItemName()).startswith(MARK_PREFIX)]
    groups = [g for g in b.Groups() if g.GetName() == GROUP_NAME]
    items = [it for g in groups for it in g.GetItems()]
    c.keepalive = marks + groups + items      # removed objects must outlive the Python wrappers
    for it in items + marks:
        b.Remove(it)
        n += 1
    for g in groups:
        b.Remove(g)
    if n:
        c.say("cleared %d items from a previous run" % n)


# ------------------------------------------------------- item creation ----
def add_text(c, s, cx, cy, size, th, ang, owner):
    tpl = c.text_tpl(s, size, th, ang)
    t = PCB_TEXT(c.b)
    t.SetLayer(F_SilkS)
    t.SetText(s)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(th))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    t.SetTextAngleDegrees(ang)
    t.SetPosition(VECTOR2I(FromMM(cx - tpl[0]), FromMM(cy - tpl[1])))
    c.b.Add(t)
    c.gen.append(t)
    return t


def add_line(c, x0, y0, x1, y1, w=LINE_W):
    s = PCB_SHAPE(c.b)
    s.SetShape(SHAPE_T_SEGMENT)
    s.SetLayer(F_SilkS)
    s.SetStart(VECTOR2I(FromMM(x0), FromMM(y0)))
    s.SetEnd(VECTOR2I(FromMM(x1), FromMM(y1)))
    s.SetWidth(FromMM(w))
    c.b.Add(s)
    c.gen.append(s)
    return s


def add_dot(c, x, y, d=DOT_D):
    s = PCB_SHAPE(c.b)
    s.SetShape(SHAPE_T_CIRCLE)
    s.SetLayer(F_SilkS)
    s.SetCenter(VECTOR2I(FromMM(x), FromMM(y)))
    s.SetEnd(VECTOR2I(FromMM(x + d / 2.0), FromMM(y)))
    s.SetWidth(FromMM(0.1))
    s.SetFilled(True)
    c.b.Add(s)
    c.gen.append(s)
    return s


# ------------------------------------------------------- text placement ----
def candidates(w, h, anchor, rings, step=0.5):
    """Yield (ring, side, centre) positions for a w x h box around the anchor box."""
    ax0, ay0, ax1, ay1 = anchor
    acx, acy = (ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0
    out = []
    for ri, g in enumerate(rings):
        for side in "NSEW":
            horiz = side in "NS"
            span = ((ax1 - ax0) + w) / 2.0 if horiz else ((ay1 - ay0) + h) / 2.0
            n = int(span / step) + 1
            for k in range(-n, n + 1):
                s = k * step
                if horiz:
                    cx = acx + s
                    cy = ay0 - g - h / 2.0 if side == "N" else ay1 + g + h / 2.0
                else:
                    cy = acy + s
                    cx = ax0 - g - w / 2.0 if side == "W" else ax1 + g + w / 2.0
                out.append((ri, abs(s), "NSEW".index(side), cx, cy))
    out.sort()
    return [(o[3], o[4]) for o in out]


def interior_candidates(w, h, anchor, step=0.75):
    ax0, ay0, ax1, ay1 = anchor
    out = []
    x = ax0 + w / 2.0
    while x <= ax1 - w / 2.0 + 1e-6:
        y = ay0 + h / 2.0
        while y <= ay1 - h / 2.0 + 1e-6:
            out.append((math.hypot(x - (ax0 + ax1) / 2, y - (ay0 + ay1) / 2), x, y))
            y += step
        x += step
    out.sort()
    return [(o[1], o[2]) for o in out]


def place_text(c, owner, lines_alts, anchor, sizes=TEXT_SIZES, angles=(0, 90), rings=(0.05, 0.5, 1.0, 2.0),
               interior=False, strict=True, what="text"):
    """Find a conflict-free spot for the first alternative/size that fits; commit and return spec."""
    for alt in lines_alts:
        s = "\n".join(alt)
        for si, (size, th) in enumerate(sizes):
            for ang in angles:
                tpl = c.text_tpl(s, size, th, ang)
                w, h = tpl[2], tpl[3]
                cands = []
                if interior:
                    cands += interior_candidates(w, h, anchor)
                cands += candidates(w, h, anchor, rings)
                for (cx, cy) in cands:
                    box = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
                    if c.free(box, owner, strict):
                        c.commit(box, owner)
                        return dict(text=s, cx=cx, cy=cy, size=size, th=th, ang=ang, box=box, small=(si > 0),
                                    alt=alt)
    return None


def place_free_block(c, w, h, owner, pref):
    """Search the whole board for a free w x h block closest to a preferred corner (pref = (px,py))."""
    bx0, by0, bx1, by1 = c.board_box
    best = None
    x = bx0
    while x + w <= bx1 + 1e-6:
        y = by0
        while y + h <= by1 + 1e-6:
            box = (x, y, x + w, y + h)
            d = math.hypot(x + w / 2 - pref[0], y + h / 2 - pref[1])
            if (best is None or d < best[0]) and c.free(box, owner, True):
                best = (d, box)
            y += 1.0
        x += 1.0
    return best[1] if best else None


# -------------------------------------------------------------- marks ------
def pad_by_number(f, num):
    for p in f.Pads():
        if p.GetNumber() == num:
            return p
    return None


def fp_pads_box(f):
    return union([box_of(p.GetBoundingBox()) for p in f.Pads()])


def outward_dirs(f, pad):
    """Unit axis directions ordered by how outward the pad sits (main axis first)."""
    fb = fp_pads_box(f)
    pb = box_of(pad.GetBoundingBox())
    cx, cy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
    px, py = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
    hx, hy = max((fb[2] - fb[0]) / 2, 1e-3), max((fb[3] - fb[1]) / 2, 1e-3)
    nx, ny = (px - cx) / hx, (py - cy) / hy
    dirs = []
    for d in ((1 if nx >= 0 else -1, 0, abs(nx)), (0, 1 if ny >= 0 else -1, abs(ny))):
        dirs.append(d)
    dirs.sort(key=lambda d: -d[2])
    out = [(d[0], d[1]) for d in dirs]
    out += [(-d[0], -d[1]) for d in out[::-1]][:0]
    return out, pb


def place_dot(c, ref, f, pad):
    dirs, pb = outward_dirs(f, pad)
    r = DOT_D / 2.0
    cb = c.fp_box[ref]
    pcx, pcy = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
    cands = []
    for (dx, dy) in dirs:
        half = ((pb[2] - pb[0]) / 2) if dx else ((pb[3] - pb[1]) / 2)
        # beyond the courtyard first (group A), then hugging the pad (group B)
        if dx:
            edge = (cb[2] if dx > 0 else cb[0])
            a_off = abs(edge - pcx) + r + 0.15
        else:
            edge = (cb[3] if dy > 0 else cb[1])
            a_off = abs(edge - pcy) + r + 0.15
        b_off = half + PAD_CLR_PLAN + r
        for grp, off in (("A", a_off), ("B", b_off)):
            for extra in (0.0, 0.3, 0.7, 1.2):
                for t in (0.0, 0.5, -0.5, 1.0, -1.0):
                    x = pcx + dx * (off + extra) + (t if dy else 0)
                    y = pcy + dy * (off + extra) + (t if dx else 0)
                    cands.append((grp, x, y))
    cands.sort(key=lambda q: 0 if q[0] == "A" else 1)
    # stable: keep generation order inside each group
    for (_g, x, y) in cands:
        box = (x - r, y - r, x + r, y + r)
        if c.free(box, ref):
            c.commit(box, ref)
            add_dot(c, x, y)
            return (x, y, _g)
    return None


def place_bar(c, ref, f, cathode, other):
    """Cathode bar on the outward side of the cathode pad of a 2-pad diode/LED."""
    pb = box_of(cathode.GetBoundingBox())
    ob = box_of(other.GetBoundingBox())
    cx, cy = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
    ox, oy = (ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2
    ax, ay = cx - ox, cy - oy
    n = math.hypot(ax, ay) or 1.0
    ux, uy = ax / n, ay / n
    if abs(ux) >= abs(uy):
        ux, uy = (1 if ux > 0 else -1), 0
        half_len = max((pb[3] - pb[1]) / 2, 0.5) + 0.1
        off0 = (pb[2] - pb[0]) / 2 + PAD_CLR_PLAN + 0.1
        mk = lambda o, k: (cx + ux * o, cy - half_len, cx + ux * o, cy + half_len)
    else:
        ux, uy = 0, (1 if uy > 0 else -1)
        half_len = max((pb[2] - pb[0]) / 2, 0.5) + 0.1
        off0 = (pb[3] - pb[1]) / 2 + PAD_CLR_PLAN + 0.1
        mk = lambda o, k: (cx - half_len, cy + uy * o, cx + half_len, cy + uy * o)
    for extra in (0.0, 0.3, 0.7, 1.2):
        x0, y0, x1, y1 = mk(off0 + extra, 0)
        box = (min(x0, x1) - LINE_W / 2, min(y0, y1) - LINE_W / 2, max(x0, x1) + LINE_W / 2, max(y0, y1) + LINE_W / 2)
        if c.free(box, ref):
            c.commit(box, ref)
            add_line(c, x0, y0, x1, y1)
            return True
    return False


def do_marks(c):
    for ref in sorted(c.fps, key=natural):
        f = c.fps[ref]
        if f.IsFlipped():
            continue
        fp = str(f.GetFPID().GetLibItemName())
        npad = f.GetPadCount()
        pre = re.match(r"[A-Za-z]+", ref).group(0)
        # polarity: diodes / LEDs (KiCad D_*/LED_* footprints: pad 1 = cathode K)
        if pre in ("D",) and (fp.startswith("D_") or fp.startswith("LED_")) and npad == 2:
            k, a = pad_by_number(f, "1"), pad_by_number(f, "2")
            if place_bar(c, ref, f, k, a):
                c.count("cathode_bar")
            else:
                c.say("DROPPED cathode bar on %s (%s): no conflict-free spot" % (ref, fp))
            continue
        if fp.startswith("CP_") or "Elec" in fp or "Tantalum" in fp:
            p = pad_by_number(f, "1")
            r = place_text(c, ref, [["+"]], box_of(p.GetBoundingBox()), rings=(0.2, 0.6, 1.0))
            if r:
                add_text(c, "+", r["cx"], r["cy"], r["size"], r["th"], r["ang"], ref)
                c.count("polarity_plus")
            else:
                c.say("DROPPED + mark on %s" % ref)
            continue
        if pre == "BT" and npad >= 2:
            for p in f.Pads():
                sign = "-" if p.GetNetname() in ("GND", "") else "+"
                r = place_text(c, ref, [[sign]], box_of(p.GetBoundingBox()), rings=(0.2, 0.6, 1.0, 1.6))
                if r:
                    add_text(c, sign, r["cx"], r["cy"], r["size"], r["th"], r["ang"], ref)
                    c.count("battery_polarity")
                else:
                    c.say("DROPPED %s on %s pad %s" % (sign, ref, p.GetNumber()))
        # pin-1 dot
        if pre in ("U", "J", "Q", "Y", "BT") and npad >= 3 or (pre in ("J", "BT") and npad == 2):
            if any(s in fp for s in PIN1_SKIP_FP):
                continue
            p = pad_by_number(f, "1") or pad_by_number(f, "A1") or pad_by_number(f, "Z0")
            if p is None:
                c.say("no pad 1 on %s (%s); no pin-1 mark" % (ref, fp))
                continue
            r = place_dot(c, ref, f, p)
            if r:
                c.count("pin1_dot")
                if r[2] == "B":
                    c.count("pin1_dot_inside_courtyard_margin")
            else:
                c.say("DROPPED pin-1 dot on %s (%s): no conflict-free spot" % (ref, fp))


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# ------------------------------------------------ marker footprints --------
def load_mark(name):
    return pcbnew.FootprintLoad(PRETTY, name)


def rot_box(box, deg):
    x0, y0, x1, y1 = box
    k = int(round(deg / 90.0)) % 4
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for _ in range(k):   # KiCad angle is CCW on screen; y is down
        pts = [(y, -x) for (x, y) in pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def add_marker(c, name, cx, cy, deg, owner_ref):
    f = load_mark(name)
    if f is None:
        c.say("ERROR: cannot load %s from %s" % (name, PRETTY))
        return None
    f.SetPosition(VECTOR2I(FromMM(cx), FromMM(cy)))
    f.SetOrientationDegrees(deg)
    f.Reference().SetVisible(False)
    f.Value().SetVisible(False)
    c.b.Add(f)
    for g in f.GraphicalItems():
        if g.GetClass() == "PCB_TEXT" and g.GetLayer() == F_SilkS:
            g.SetTextAngleDegrees(0)     # keep glyph labels upright whatever the footprint rotation
    return f


def do_sensor_axes(c):
    for ref, name, box in (("U11", "OrientationMark_Axes_IIS2DLPC", (-3.5, -3.0, 3.7, 3.6)),
                           ("U10", "OrientationMark_Axes_IIS2MDC", (-2.6, -2.4, 3.7, 3.6))):
        f = c.fps.get(ref)
        if f is None:
            c.say("%s not on board: no axes mark" % ref)
            continue
        deg = f.GetOrientationDegrees()
        rb = rot_box(box, deg)
        w, h = rb[2] - rb[0], rb[3] - rb[1]
        anchor = c.fp_box[ref]
        rings = (0.3, 0.8, 1.5) + tuple(float(i) for i in range(2, 15))
        placed = None
        for strict in (True, False):
            for (cx, cy) in candidates(w, h, anchor, rings, step=1.0):
                bx = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                if c.free(bx, ref, strict):
                    placed = (cx - (rb[0] + rb[2]) / 2, cy - (rb[1] + rb[3]) / 2, bx)
                    if not strict:
                        c.say("axes mark for %s overlaps a neighbour courtyard (no strict spot)" % ref)
                    break
            if placed:
                break
        if not placed:
            c.say("DROPPED axes mark for %s: no free spot within 14 mm" % ref)
            continue
        add_marker(c, name, placed[0], placed[1], deg, ref)
        c.commit(placed[2], ref)
        c.count("axes_mark")
        c.say("axes mark for %s placed at (%.2f, %.2f) rot %g" % (ref, placed[0], placed[1], deg))


def do_frame_arrow(c):
    box = (-2.4, -7.3, 2.4, 8.3)
    rb = rot_box(box, c.args.fwd)
    w, h = rb[2] - rb[0], rb[3] - rb[1]
    bb = c.board_box
    r = place_free_block(c, w, h, "frame", (bb[2], bb[1]))
    if not r:
        c.say("DROPPED station-frame arrow: no free %.1f x %.1f mm block" % (w, h))
        return
    cx = (r[0] + r[2]) / 2 - (rb[0] + rb[2]) / 2
    cy = (r[1] + r[3]) / 2 - (rb[1] + rb[3]) / 2
    add_marker(c, "OrientationMark_StationFrame", cx, cy, c.args.fwd, "frame")
    c.commit(r, "frame")
    c.count("frame_arrow")
    c.say("station-frame arrow at (%.1f, %.1f), forward = %g deg (placeholder direction)" % (cx, cy, c.args.fwd))


def do_board_text(c):
    bb = c.board_box
    corners = [(bb[0], bb[3]), (bb[2], bb[3]), (bb[0], bb[1])]
    for i, (name, alts) in enumerate(BOARD_BLOCKS):
        done = False
        for alt in alts:
            for (size, th) in TEXT_SIZES:
                s = "\n".join(alt)
                tpl = c.text_tpl(s, size, th, 0)
                w, h = tpl[2], tpl[3]
                r = place_free_block(c, w, h, "text_" + name, corners[i % len(corners)])
                if r:
                    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
                    add_text(c, s, cx, cy, size, th, 0, "text_" + name)
                    c.commit(r, "text_" + name)
                    c.count("board_text")
                    if size < 1.0:
                        c.say("board text '%s' set at %.1f mm (below JLC 1.0 mm min)" % (name, size))
                    done = True
                    break
            if done:
                break
        if not done:
            c.say("DROPPED board text block '%s': no free space" % name)


# ---------------------------------------------------------- labels ---------
def add_spec(c, spec, owner):
    add_text(c, spec["text"], spec["cx"], spec["cy"], spec["size"], spec["th"], spec["ang"], owner)


def do_labels(c):
    for ref in sorted(LABELS, key=natural):
        f = c.fps.get(ref)
        if f is None:
            continue
        anchor = c.fp_box[ref]
        interior = (anchor[2] - anchor[0]) * (anchor[3] - anchor[1]) > 60
        spec = place_text(c, ref, LABELS[ref], anchor, interior=interior, rings=(0.05, 0.5, 1.0, 2.0, 3.0))
        if spec:
            add_spec(c, spec, ref)
            c.count("label")
            if spec["small"]:
                c.say("label %s ('%s') set at 0.8 mm (below JLC 1.0 mm min)" % (ref, spec["text"].replace("\n", "/")))
            if spec["alt"] is not LABELS[ref][0]:
                c.say("label %s shortened to '%s'" % (ref, spec["text"].replace("\n", "/")))
        else:
            c.say("DROPPED label %s %s: no conflict-free spot" % (ref, LABELS[ref][0]))
    # DNP marker on non-passive DNP parts without a custom label
    for ref in sorted(c.fps, key=natural):
        f = c.fps[ref]
        fp = str(f.GetFPID().GetLibItemName())
        if f.IsDNP() and ref not in LABELS and (c.args.dnp_all or not SMALL_PASSIVE_FP.match(fp)):
            spec = place_text(c, ref, [["DNP"]], c.fp_box[ref])
            if spec:
                add_spec(c, spec, ref)
                c.count("dnp_label")
            else:
                c.say("DROPPED DNP label %s" % ref)
    # RF note near the SMA group
    refs, alts = RF_NOTE
    have = [r for r in refs if r in c.fps]
    if have:
        anchor = union([c.fp_box[r] for r in have])
        spec = place_text(c, "rfnote", alts, anchor, rings=(0.3, 1.0, 2.0, 3.0, 5.0), angles=(0,))
        if spec:
            add_spec(c, spec, "rfnote")
            c.count("rf_note")
        else:
            c.say("DROPPED RF note near SMAs")
    ref, alts = MAG_NOTE
    if ref in c.fps:
        spec = place_text(c, ref, alts, c.fp_box[ref], rings=(0.3, 1.0, 2.0, 3.0, 5.0, 8.0))
        if spec:
            add_spec(c, spec, ref)
            c.count("mag_note")
        else:
            c.say("DROPPED magnetometer note")


def xf_local(f, x, y):
    a = math.radians(f.GetOrientationDegrees())
    px, py = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
    # KiCad: positive angle rotates CCW on screen (y down)
    return (px + x * math.cos(a) + y * math.sin(a), py - x * math.sin(a) + y * math.cos(a))


def dashed(c, pts, owner, dash=2.0, gap=1.0):
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        L = math.hypot(x1 - x0, y1 - y0)
        t = 0.0
        while t < L:
            t2 = min(t + dash, L)
            ax, ay = x0 + (x1 - x0) * t / L, y0 + (y1 - y0) * t / L
            bx, by = x0 + (x1 - x0) * t2 / L, y0 + (y1 - y0) * t2 / L
            box = (min(ax, bx) - 0.1, min(ay, by) - 0.1, max(ax, bx) + 0.1, max(ay, by) + 0.1)
            if c.free(box, owner, strict=False, margin=0.0, own_silk_ok=True) and not any(
                    k == 'pad' for (_b, _o, k) in c.hash.query(box)):
                c.hash.add(box, owner, "gen")
                add_line(c, ax, ay, bx, by)
                c.count("keepout_dash")
            t += dash + gap


def do_keepouts(c):
    for ref in sorted(c.fps, key=natural):
        f = c.fps[ref]
        fp = str(f.GetFPID().GetLibItemName())
        for key, (rect, alts) in KEEPOUTS.items():
            if not fp.startswith(key):
                continue
            x0, y0, x1, y1 = rect
            pts = [xf_local(f, *p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            dashed(c, pts, ref)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            anchor = (min(xs), min(ys), max(xs), max(ys))
            spec = place_text(c, ref, alts, anchor, interior=True, rings=(), strict=False,
                              sizes=TEXT_SIZES)
            # interior only: candidates() with empty rings yields nothing
            if spec:
                add_spec(c, spec, ref)
                c.count("keepout_text")
            else:
                c.say("DROPPED keep-out text on %s (%s): antenna region has no free text area" % (ref, key))
    # generic rule areas (board level and inside footprints)
    zones = list(c.b.Zones())
    for f in c.fps.values():
        zones += list(f.Zones())
    for z in zones:
        if not z.GetIsRuleArea():
            continue
        if not (z.GetDoNotAllowZoneFills() or z.GetDoNotAllowTracks()):
            continue
        zb = box_of(z.GetBoundingBox())
        if zb[2] - zb[0] < 4 or zb[3] - zb[1] < 1.5:
            continue
        spec = place_text(c, "zone", [["NO METAL", "KEEP OUT"], ["KEEP OUT"]], zb, interior=True, rings=(),
                          strict=False)
        if spec:
            add_spec(c, spec, "zone")
            c.count("keepout_text")


def short_net(s):
    s = s.split("/")[-1]
    return s


def do_testpoints(c):
    tps = [r for r in c.fps if re.match(r"TP\d+$", r)]
    for ref in sorted(tps, key=natural):
        f = c.fps[ref]
        pads = list(f.Pads())
        name = pads[0].GetShortNetname() if pads else ""
        if not name or name.startswith("unconnected") or name.startswith("Net-("):
            name = f.GetValue()
        name = short_net(name)
        if len(name) > 12:
            c.say("TP label %s truncated '%s' -> '%s'" % (ref, name, name[:12]))
            name = name[:12]
        anchor = box_of(pads[0].GetBoundingBox())
        spec = place_text(c, ref, [[name]], anchor, rings=(0.1, 0.5, 1.0, 1.8))
        if spec:
            add_spec(c, spec, ref)
            c.count("tp_label")
            if spec["small"]:
                c.count("tp_label_small")
        else:
            c.say("DROPPED test-point net label %s (%s)" % (ref, name))
            c.tp_dropped.add(ref)


# ------------------------------------------------ refs and values ----------
def ref_priority(ref, f):
    a = c_area(f)
    return (-a, natural(ref))


def c_area(f):
    cb = f.GetCourtyard(F_CrtYd)
    if cb.OutlineCount():
        bb = cb.BBox()
        return ToMM(bb.GetWidth()) * ToMM(bb.GetHeight())
    return 0.0


def set_field(fld, layer, text_size, th, cx, cy, ang, visible=True):
    fld.SetLayer(layer)
    fld.SetVisible(visible)
    fld.SetTextSize(VECTOR2I(FromMM(text_size), FromMM(text_size)))
    fld.SetTextThickness(FromMM(th))
    fld.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    fld.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    fld.SetTextAngleDegrees(ang)
    fld.SetPosition(VECTOR2I(FromMM(cx), FromMM(cy)))


def field_centre_fix(c, fld, cx, cy):
    """Position a centred field so the stroked glyph box centre lands on (cx, cy)."""
    bb = fld.GetEffectiveTextShape().BBox()
    dx = cx - ToMM((bb.GetLeft() + bb.GetRight()) / 2)
    dy = cy - ToMM((bb.GetTop() + bb.GetBottom()) / 2)
    p = fld.GetPosition()
    fld.SetPosition(VECTOR2I(p.x + FromMM(dx), p.y + FromMM(dy)))


def to_fab(c, f, which):
    fld = f.Reference() if which == "ref" else f.Value()
    cb = c.fp_box.get(f.GetReference())
    cx, cy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
    off = 0.0 if which == "ref" else 0.7
    set_field(fld, F_Fab, 0.6, 0.09, cx, cy + off, 0)


def do_refs(c):
    order = sorted(c.fps, key=lambda r: (1 if PASSIVE_RE.match(r) or r.startswith("TP") else 0,
                                         ref_priority(r, c.fps[r])))
    for ref in order:
        f = c.fps[ref]
        if f.IsFlipped():
            continue
        if re.match(r"TP\d+$", ref) and not c.args.tp_refs and ref not in c.tp_dropped:
            to_fab(c, f, "ref")
            c.count("ref_to_fab_tp")
            continue
        anchor = c.fp_box[ref]
        interior = (anchor[2] - anchor[0]) * (anchor[3] - anchor[1]) > 60
        spec = place_text(c, ref, [[ref]], anchor, interior=interior, rings=(0.05, 0.5, 1.0, 2.0))
        if not spec and c.args.relax_courtyards:
            spec = place_text(c, ref, [[ref]], anchor, interior=interior, rings=(0.05, 0.5, 1.0, 2.0),
                              strict=False)
            if spec:
                c.count("ref_in_neighbour_courtyard")
        if spec:
            set_field(f.Reference(), F_SilkS, spec["size"], spec["th"], spec["cx"], spec["cy"], spec["ang"])
            field_centre_fix(c, f.Reference(), spec["cx"], spec["cy"])
            c.count("ref_on_silk")
            if spec["small"]:
                c.count("ref_small_0.8")
        else:
            to_fab(c, f, "ref")
            c.count("ref_to_fab")
            c.say("ref %s moved to F.Fab (no conflict-free silk spot)" % ref)


def do_values(c):
    for ref in sorted(c.fps, key=natural):
        f = c.fps[ref]
        pre = re.match(r"[A-Za-z]+", ref).group(0)
        if f.IsFlipped():
            continue
        to_fab(c, f, "val")
        if pre not in ("U", "J", "Q", "Y", "L", "D", "SW", "BT", "FB") or re.match(r"TP", ref):
            continue
        if SMALL_PASSIVE_FP.match(str(f.GetFPID().GetLibItemName())) or ref in LABELS:
            continue
        val = f.GetValue()
        if not val or val == "DNP" or len(val) > 24:
            continue
        anchor = c.fp_box[ref]
        interior = (anchor[2] - anchor[0]) * (anchor[3] - anchor[1]) > 60
        if not interior:
            continue            # values go on silk only when they sit inside the part's own courtyard
        spec = place_text(c, ref, [[val]], anchor, sizes=TEXT_SIZES[:1], interior=True,
                          rings=(), strict=True)
        if spec:
            set_field(f.Value(), F_SilkS, spec["size"], spec["th"], spec["cx"], spec["cy"], spec["ang"])
            field_centre_fix(c, f.Value(), spec["cx"], spec["cy"])
            c.count("value_on_silk")


# ------------------------------------------------------------ checker ------
class Item:
    __slots__ = ("obj", "label", "native", "shape", "box", "parent", "gen", "field")

    def __init__(self, obj, label, native, shape, parent, gen=False, field=None):
        self.obj, self.label, self.native, self.shape, self.parent, self.gen, self.field = \
            obj, label, native, shape, parent, gen, field
        bb = shape.BBox()
        self.box = (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))


def collect_silk(c):
    b = c.b
    items = []
    grp = [g for g in b.Groups() if g.GetName() == GROUP_NAME]
    gen_ids = set(id(x) for g in grp for x in g.GetItems()) if grp else set()
    gen_uuid = set(str(x.m_Uuid.AsString()) for g in grp for x in g.GetItems()) if grp else set()

    def shape_of(o):
        if o.GetClass() == "PCB_TEXT" or o.GetClass() == "PCB_FIELD":
            return o.GetEffectiveTextShape()
        return o.GetEffectiveShape()

    for d in b.GetDrawings():
        if d.GetLayer() == F_SilkS:
            gen = str(d.m_Uuid.AsString()) in gen_uuid
            items.append(Item(d, "%s %s" % (d.GetClass(), (d.GetText() if d.GetClass() == "PCB_TEXT" else "")),
                              not gen, shape_of(d), "board", gen))
    for f in b.GetFootprints():
        ref = f.GetReference()
        is_mark = str(f.GetFPID().GetLibItemName()).startswith(MARK_PREFIX)
        for fld, nm in ((f.Reference(), "ref"), (f.Value(), "value")):
            if fld.IsVisible() and fld.GetLayer() == F_SilkS:
                items.append(Item(fld, "%s %s '%s'" % (ref, nm, fld.GetText()), False, shape_of(fld), ref, True, f))
        for g in f.GraphicalItems():
            if g.GetLayer() == F_SilkS:
                try:
                    items.append(Item(g, "%s %s" % (ref, g.GetClass()), not is_mark, shape_of(g), ref, is_mark))
                except Exception:
                    pass
    return items


def check(c, verbose=True):
    """Return dict of violation lists. Non-native violations must be zero."""
    b = c.b
    items = collect_silk(c)
    pads = []
    for f in b.GetFootprints():
        for p in f.Pads():
            try:
                sh = p.GetEffectiveShape(F_Cu)
            except Exception:
                continue
            bb = p.GetBoundingBox()
            pads.append((box_of(bb), p, f.GetReference(), sh))
    ph = Hash()
    for pb, p, ref, sh in pads:
        ph.add(pb, (p, ref, sh), "pad")
    vias = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.append(t)
    edges = [d.GetEffectiveShape() for d in b.GetDrawings() if d.GetLayer() == Edge_Cuts]
    edge_box = c.outline
    res = {"silk_pad": [], "silk_overlap": [], "silk_edge": [], "silk_via": [], "native_silk_pad": [],
           "native_native": 0}
    ih = Hash()
    for it in items:
        ih.add(it.box, it, "silk")
    seen = set()
    for it in items:
        # pads
        for (_b, (p, ref, sh), _k) in ph.query(infl(it.box, PAD_CLR_CHECK + 0.05)):
            if it.native and ref == it.parent:
                pass
            try:
                hit = it.shape.Collide(sh, FromMM(PAD_CLR_CHECK))
            except Exception:
                hit = False
            if hit:
                key = "native_silk_pad" if it.native else "silk_pad"
                res[key].append((it, "pad %s.%s" % (ref, p.GetNumber())))
        # edge
        if edge_box and not inside(it.box, infl(edge_box, -EDGE_CLR_CHECK)):
            for es in edges:
                try:
                    if it.shape.Collide(es, FromMM(EDGE_CLR_CHECK)):
                        res["silk_edge"].append((it, "edge"))
                        break
                except Exception:
                    pass
        for v in vias:
            vp = v.GetPosition()
            r = ToMM(v.GetWidth(F_Cu)) / 2 + PAD_CLR_CHECK
            vx, vy = ToMM(vp.x), ToMM(vp.y)
            if overlap(it.box, (vx - r, vy - r, vx + r, vy + r)):
                if it.shape.Collide(v.GetEffectiveShape(F_Cu), FromMM(PAD_CLR_CHECK)):
                    res["silk_via"].append((it, "via"))
        # silk vs silk
        for (_b, other, _k) in ih.query(infl(it.box, 0.0)):
            if other is it:
                continue
            key = tuple(sorted((id(it), id(other))))
            if key in seen:
                continue
            seen.add(key)
            if it.parent == other.parent and (it.native or other.native or it.gen and other.gen and it.parent != "board"):
                continue            # items belonging to one footprint / glyph
            if it.native and other.native:
                continue
            try:
                hit = it.shape.Collide(other.shape, 0)
            except Exception:
                hit = False
            if hit:
                res["silk_overlap"].append((it, other.label))
    return res


def enforce(c):
    """Remove generated items that violate the checker; refs go to F.Fab."""
    for rnd in range(4):
        res = check(c)
        bad = []
        for k in ("silk_pad", "silk_overlap", "silk_edge", "silk_via"):
            for v in res[k]:
                bad.append((k, v))
        if not bad:
            c.say("checker: clean after %d enforcement round(s)" % rnd)
            return res
        done = set()
        for k, (it, other) in bad:
            if not (it.gen or it.field is not None):
                continue
            if id(it.obj) in done:
                continue
            done.add(id(it.obj))
            if it.field is not None:
                which = "ref" if it.field is it.field.Reference() else "val"
                c.say("ENFORCE %s: '%s' vs %s -> moved to F.Fab" % (k, it.label, other))
                to_fab(c, it.field, "ref" if "ref" in it.label.split()[1] else "val")
                c.count("enforced_to_fab")
            else:
                c.say("ENFORCE %s: removed %s vs %s" % (k, it.label, other))
                try:
                    c.b.Remove(it.obj)
                except Exception:
                    pass
                c.count("enforced_removed")
    return check(c)


def summarize(c, res, out=sys.stdout):
    nn = {k: len(v) for k, v in res.items() if isinstance(v, list)}
    print("checker:", nn, file=out)
    for k in ("silk_pad", "silk_overlap", "silk_edge", "silk_via"):
        for (it, other) in res[k][:15]:
            print("  VIOLATION %s: %s <-> %s" % (k, it.label, other), file=out)
    return sum(nn[k] for k in ("silk_pad", "silk_overlap", "silk_edge", "silk_via"))


# ---------------------------------------------------------------- main -----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--out", help="write here instead of in place")
    ap.add_argument("--log")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--fwd", type=float, default=0.0,
                    help="board rotation (deg CCW) of the station FWD arrow; 0 = toward top of board (placeholder)")
    ap.add_argument("--dnp-all", action="store_true", help="also put 'DNP' next to DNP 0402/0603 passives")
    ap.add_argument("--relax-courtyards", action="store_true",
                    help="allow reference text inside neighbours' courtyards (never over pads/silk/text) when "
                         "no strict spot exists; default off = such refs go to F.Fab")
    ap.add_argument("--tp-refs", action="store_true", help="also try TPnnn designators on silk (default: net name only)")
    args = ap.parse_args()

    path = os.path.abspath(args.board)
    pro = os.path.splitext(path)[0] + ".kicad_pro"
    pro_bytes = open(pro, "rb").read() if os.path.exists(pro) else None
    b = pcbnew.LoadBoard(path)
    c = Ctx(b, args)

    if args.check_only:
        c.outline = None
        ex = [box_of(d.GetBoundingBox()) for d in b.GetDrawings() if d.GetLayer() == Edge_Cuts]
        c.outline = union(ex) if ex else None
        n = summarize(c, check(c))
        sys.exit(1 if n else 0)

    pcbnew.KIID.SeedGenerator(20261118)
    clear_generated(c)
    load_obstacles(c)
    do_frame_arrow(c)
    do_sensor_axes(c)
    do_board_text(c)
    do_marks(c)
    do_keepouts(c)
    do_labels(c)
    do_testpoints(c)
    do_refs(c)
    do_values(c)

    # group all generated board-level items
    g = PCB_GROUP(b)
    g.SetName(GROUP_NAME)
    b.Add(g)
    for it in c.gen:
        g.AddItem(it)

    res = enforce(c)
    n = summarize(c, res)
    print("stats:", dict(sorted(c.stats.items())))
    for line in c.log:
        print(" ", line)
    if args.log:
        with open(args.log, "w") as fh:
            fh.write("\n".join(c.log) + "\nstats: %s\n" % dict(sorted(c.stats.items())))

    outp = os.path.abspath(args.out) if args.out else path
    b.Save(outp)
    if pro_bytes is not None and outp == path:
        with open(pro, "wb") as fh:          # BOARD.Save() rewrites .kicad_pro: restore it
            fh.write(pro_bytes)
    sys.exit(1 if n else 0)


if __name__ == "__main__":
    main()
