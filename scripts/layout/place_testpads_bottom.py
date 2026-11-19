#!/usr/bin/env python3
"""Move the 62 bay-station test pads (TP*) to the BOTTOM side, in function-group rows.

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \\
        scripts/layout/place_testpads_bottom.py [--board IN.kicad_pcb] [--out OUT.kicad_pcb] \\
        [--sidecar testpads_bottom.json] [--no-save]

Reads a PLACED board (any Edge.Cuts outline: the bbox and the polygon are read from the board),
flips every TP listed in testpoint_labels.json to B.Cu (pcbnew Flip, so pads end up on
B.Cu + B.Mask and the reference/value fields on B.Fab), lays the pads out in rows and writes the
mirrored 1.0 mm B.SilkS label of each pad.  Idempotent and deterministic: the pad targets come from
non-TP geometry only, so a second run reproduces the first byte for byte (KIIDs are seeded, the
existing label texts are reused, .kicad_pro is restored).  No zone is filled here.

Layout rules (all numbers are constants below):
  * one row per function group (power is split into two rows of <= 9 pads); pads in a row sit on a
    2.54 mm pitch, sorted by the x of their target so stubs do not cross;
  * every pad carries a vertical, mirrored 1.0 mm silk label directly below it (reads downwards when
    the board is turned over about its vertical axis), a via/escape strip of ESC mm above it, and
    rows sit on common band lines so the table is regular; bands are >= 3.5 mm apart pad to pad;
  * a row is placed at the legal slot (band, x on a 0.635 grid) nearest the centroid of the top-side
    pins of its nets; rows are placed in a fixed group order, so earlier groups win contested spots;
  * rows keep LAT_GAP mm of clear lateral space (a vertical routing channel) to each other;
  * keep-outs: >= 3.5 mm from the edge of M3 holes, >= 2 mm from the board edge, the RF corridor
    from each DW3210 centre to its SMA, the SMA connectors, the BT840 antenna rule area, and every
    through hole / B.Cu pad / via already on the board;
  * the 7 GND pads are placed last, each beside the row of the area it is named after.
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
import pcbutil as U  # noqa: E402

DEFAULT_BOARD = os.path.join(U.REPO, "bay-station", "bay-station.kicad_pcb")
LABELS = os.path.join(HERE, "testpoint_labels.json")

PITCH = 2.54            # pad centre to centre inside a row
MAX_ROW = 9             # longest row (power is split)
BAND_MIN_PAD_GAP = 3.5  # minimum pad-to-pad distance between rows
EDGE_CLR = 2.0          # board edge to pad / label / escape strip
HOLE_CLR = 3.5          # clearance from the edge of an M3 hole
OBST_CLR = 1.0          # from any other B.Cu copper / hole / via
SMA_CLR = 6.0           # around each SMA connector body
BT_CLR = 3.0            # around the BT840 antenna rule area
RF_HALF_W = 5.0         # half width of the DW3210 -> SMA corridor
ESC = 2.2               # via / escape strip above the pad centre (box top)
LABEL_GAP = 0.5         # pad edge to first label character
LABEL_H = 1.0           # silk text height (mm), thickness 0.15
LABEL_THK = 0.15
LAT_GAPS = (4.0, 3.5, 3.0, 2.5)   # tried in turn until every row fits
GND_LAT_GAP = 2.5       # a GND pad may sit this close beside its row
GRID = 0.635

ROW_ORDER = ["power", "clock", "spi", "a0", "a1", "a2", "a3", "sensors", "host", "modem"]
# GND pad -> the pads (by TP ref) whose placed row it is named after
GND_AREA = {
    "TP3": ["TP5"],                      # GND CLK1: TCXO output
    "TP110": ["TP6"],                    # GND CLK2: clock buffer output
    "TP111": ["TP10", "TP11", "TP12"],   # GND SPI
    "TP113": ["TP104", "TP2", "TP103"],  # GND PWR: input / VSYS
    "TP114": ["TP400", "TP403"],         # GND REG: 3V3 buck
    "TP115": ["TP150", "TP151"],         # GND HOST: bridge UART
    "TP116": ["TP101"],                  # GND UWB: 3V3 UWB
}
# Rails with dozens of pins (centroid would be the board centre): measure where the rail is made / used.
RAIL_AT = {
    "TP1": ["U8"], "TP103": ["U8"], "TP2": ["U1"], "TP100": ["U40"], "TP101": ["U4", "U5", "U6", "U7"],
    "TP102": ["U20", "U3"], "TP121": ["U10", "U11"],
}
CHAR_W = 0.88           # estimated advance of one 1.0 mm stroke-font character (verified on the render)


def label_len(text):
    return CHAR_W * len(text) + 0.3


# ----------------------------------------------------------------------------- board facts

def fp_by_ref(board):
    return {f.GetReference(): f for f in board.GetFootprints()}


def pos_mm(item):
    p = item.GetPosition()
    return (U.mm(p.x), U.mm(p.y))


def gather(board, labels):
    """Obstacles, keep-outs and per-pad targets, all from non-TP geometry."""
    fps = fp_by_ref(board)
    bx0, by0, bx1, by1 = U.board_outline(board)
    poly = U.outline_polygon(board)
    holes, rects, pad_pos = [], [], {}
    pins_by_net = {}
    for ref, f in fps.items():
        is_tp = ref in labels
        for p in f.Pads():
            c = pos_mm(p)
            pn = p.GetNetname()
            if not is_tp and pn:
                pins_by_net.setdefault(pn, []).append((ref, c))
            if is_tp:
                continue
            if ref.startswith("H") and p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                holes.append((c[0], c[1], U.mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2.0, "mount " + ref))
                continue
            if p.HasHole() or p.IsOnLayer(U.B_CU):
                bb = p.GetBoundingBox()
                r = (U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()))
                rects.append((r[0] - OBST_CLR, r[1] - OBST_CLR, r[2] + OBST_CLR, r[3] + OBST_CLR, "%s pad %s" % (ref, p.GetNumber())))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            c = pos_mm(t)
            r = U.mm(t.GetWidth()) / 2 + OBST_CLR
            rects.append((c[0] - r, c[1] - r, c[0] + r, c[1] + r, "via"))
        elif t.GetLayer() == U.B_CU:
            a, b = (U.mm(t.GetStart().x), U.mm(t.GetStart().y)), (U.mm(t.GetEnd().x), U.mm(t.GetEnd().y))
            w = U.mm(t.GetWidth()) / 2 + OBST_CLR
            rects.append((min(a[0], b[0]) - w, min(a[1], b[1]) - w, max(a[0], b[0]) + w, max(a[1], b[1]) + w, "B.Cu track"))
    # SMA bodies and the DW3210 -> SMA RF corridor
    smas = [(r, f) for r, f in fps.items() if re.match(r"J2\d$", r) and "SMA" in f.GetValue().upper()]
    for r, f in smas:
        c = pos_mm(f)
        rects.append((c[0] - SMA_CLR, c[1] - SMA_CLR, c[0] + SMA_CLR, c[1] + SMA_CLR, "SMA " + r))
    for r, f in sorted(fps.items()):
        if "DW3210" not in f.GetValue():
            continue
        c = pos_mm(f)
        # RF pins face south for rotation 0 and north for rotation 180 (place_bay_station.py)
        north = abs(abs(f.GetOrientationDegrees()) - 180) < 1
        cand = [(abs(pos_mm(sf)[0] - c[0]), sr, pos_mm(sf)) for sr, sf in smas
                if (pos_mm(sf)[1] < c[1]) == north]
        if not cand:
            continue
        _, sr, sp = min(cand)
        y_a, y_b = sorted([c[1], sp[1]])
        # from the chip centre outwards through the SMA, to the board edge on that side
        if sp[1] > c[1]:
            y_b = by1
        else:
            y_a = by0
        rects.append((c[0] - RF_HALF_W, y_a, c[0] + RF_HALF_W, y_b, "RF corridor %s->%s" % (r, sr)))
    for z in board.Zones():
        if z.GetZoneName() == "KO_BT840_antenna":
            ol = z.Outline().COutline(0)
            xs = [U.mm(ol.CPoint(i).x) for i in range(ol.PointCount())]
            ys = [U.mm(ol.CPoint(i).y) for i in range(ol.PointCount())]
            rects.append((min(xs) - BT_CLR, min(ys) - BT_CLR, max(xs) + BT_CLR, max(ys) + BT_CLR, "BT840 antenna"))
    return {"fps": fps, "bbox": (bx0, by0, bx1, by1), "poly": poly, "holes": holes, "rects": rects,
            "pins_by_net": pins_by_net}


def targets(board, labels, G):
    """ref -> (x, y, how): centroid of the top-side pins of the pad's net (RAIL_AT for big rails)."""
    fps = G["fps"]
    out = {}
    for ref in sorted(labels):
        f = fps[ref]
        net = list(f.Pads())[0].GetNetname()
        pins = G["pins_by_net"].get(net, [])
        how = "net %d pins" % len(pins)
        if ref in RAIL_AT:
            sel = [c for r, c in pins if r in RAIL_AT[ref]] or [pos_mm(fps[r]) for r in RAIL_AT[ref] if r in fps]
            if sel:
                pins, how = [("", c) for c in sel], "rail at " + "/".join(RAIL_AT[ref])
        if not pins or net == "GND":
            out[ref] = None
            continue
        out[ref] = (sum(c[0] for _, c in pins) / len(pins), sum(c[1] for _, c in pins) / len(pins), how)
    return out


# ----------------------------------------------------------------------------- packing

class Row:
    def __init__(self, name, group, refs, labels, radii, tgt):
        self.name, self.group, self.refs = name, group, refs
        self.n = len(refs)
        self.labels = labels
        self.radii = radii
        self.tgt = tgt                           # (x, y) centroid target
        self.xs = [i * PITCH for i in range(self.n)]
        r = max(radii)
        self.half = max(r, LABEL_H / 2 + 0.1)
        self.w = self.xs[-1] + 2 * self.half
        self.L = max(label_len(t) for t in labels)
        self.up = ESC                             # box top above pad centre
        self.down = max(radii) + LABEL_GAP + self.L
        self.h = self.up + self.down

    def box(self, ox, oy):
        """Bounding box of the whole row with the first pad at (ox, oy)."""
        return (ox - self.half, oy - self.up, ox + self.xs[-1] + self.half, oy + self.down)


def rect_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return dx, dy


def inside_outline(box, G):
    bx0, by0, bx1, by1 = G["bbox"]
    if box[0] < bx0 + EDGE_CLR or box[2] > bx1 - EDGE_CLR or box[1] < by0 + EDGE_CLR or box[3] > by1 - EDGE_CLR:
        return False
    poly = G["poly"]
    # only the rounded corners can cut into the 2 mm bbox margin: test the polygon near them
    cr = G.setdefault("corner_zone", 12.0)
    near = ((box[0] < bx0 + cr or box[2] > bx1 - cr) and (box[1] < by0 + cr or box[3] > by1 - cr))
    if poly and near:
        xm, ym = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        for q in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]),
                  (xm, box[1]), (xm, box[3]), (box[0], ym), (box[2], ym)):
            if not U.point_in_poly(q[0], q[1], poly):
                return False
            n = len(poly)
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                if U.dist_pt_seg(q[0], q[1], a[0], a[1], b[0], b[1]) < EDGE_CLR - 1e-6:
                    return False
    return True


def feasible(row, ox, oy, placed, G, lat):
    box = row.box(ox, oy)
    if not inside_outline(box, G):
        return False
    for hx, hy, hr, _ in G["holes"]:
        if U.dist_pt_rect(hx, hy, *box) < hr + HOLE_CLR:
            return False
    for r in G["rects"]:
        if rect_gap(box, r)[0] <= 0 and rect_gap(box, r)[1] <= 0:
            return False
    for other, obox, olat in placed:
        dx, dy = rect_gap(box, obox)
        need = min(lat, olat)
        if not (dx >= need or dy >= 1.0):
            return False
    return True


def build_rows(labels, T, fps):
    rows = []
    per = {g: [r for r in labels if labels[r]["group"] == g] for g in ROW_ORDER + ["gnd"]}

    def rad(ref):
        return U.mm(list(fps[ref].Pads())[0].GetSize().x) / 2.0

    for g in ROW_ORDER:
        refs = sorted(per[g], key=lambda r: (T[r][0], r))
        if len(refs) > MAX_ROW:
            half = (len(refs) + 1) // 2
            chunks = [refs[:half], refs[half:]]
        else:
            chunks = [refs]
        for k, ch in enumerate(chunks):
            name = g if len(chunks) == 1 else "%s %s" % (g, "AB"[k])
            ty = (sum(T[r][1] for r in ch) / len(ch))
            tx = (sum(T[r][0] for r in ch) / len(ch))
            rows.append(Row(name, g, ch, [labels[r]["label"] for r in ch], [rad(r) for r in ch], (tx, ty)))
    return rows, per


def place_rows(rows, gnd_refs, labels, T, fps, G, lat):
    """Returns ({row.name: (ox, oy)}, [unplaced], bands) for one lateral gap and the best band phase."""
    bx0, by0, bx1, by1 = G["bbox"]
    gnd_rows = []
    best = None
    tall = max([r.h for r in rows] + [labels[g]["label"] and Row("g", "gnd", [g], [labels[g]["label"]], [0.75], (0, 0)).h
                                         for g in gnd_refs])
    pitch = tall + 1.0                 # tallest box + 1 mm between a label end and the next escape strip
    pitch = max(pitch, BAND_MIN_PAD_GAP)
    phases = [i * 1.0 for i in range(int(pitch))]
    for phase in phases:
        y_first = by0 + EDGE_CLR + ESC + phase
        bands = []
        k = 0
        while y_first + k * pitch + (tall - ESC) <= by1 - EDGE_CLR + 1e-9:
            bands.append(y_first + k * pitch)
            k += 1
        placed, pos, unplaced, cost = [], {}, [], 0.0
        gnd_rows = []
        todo = list(rows)
        for row in todo:
            c = _best_slot(row, bands, placed, G, lat, bx0, GRID)
            if c is None:
                unplaced.append(row.name)
                cost += 1e4
                continue
            d, ox, oy = c
            placed.append((row, row.box(ox, oy), lat))
            pos[row.name] = (ox, oy)
            cost += d
        # GND pads, one per named area, placed beside the row of that area
        for gref in sorted(gnd_refs, key=lambda r: (r not in GND_AREA, r)):
            tg = [pos_of_pad(pos, rows, t) for t in GND_AREA.get(gref, [])]
            tg = [t for t in tg if t]
            tgt = (sum(t[0] for t in tg) / len(tg), sum(t[1] for t in tg) / len(tg)) if tg else (bx0, by0)
            row = Row("gnd " + gref, "gnd", [gref], [labels[gref]["label"]], [list(fps[gref].Pads())[0].GetSize().x / 2e6], tgt)
            c = _best_slot(row, bands, placed, G, GND_LAT_GAP, bx0, GRID)
            if c is None:
                unplaced.append(row.name)
                cost += 1e4
                continue
            d, ox, oy = c
            placed.append((row, row.box(ox, oy), GND_LAT_GAP))
            pos[row.name] = (ox, oy)
            gnd_rows.append(row)
            cost += d
        if best is None or cost < best[0] - 1e-9:
            best = (cost, pos, unplaced, bands, gnd_rows, phase)
    return best, pitch


def pos_of_pad(pos, rows, tpref):
    for r in rows:
        if tpref in r.refs and r.name in pos:
            ox, oy = pos[r.name]
            return (ox + r.xs[r.refs.index(tpref)], oy)
    return None


def _best_slot(row, bands, placed, G, lat, bx0, grid):
    bx1 = G["bbox"][2]
    best = None
    x = bx0 + EDGE_CLR
    xs = []
    while x + row.w <= bx1 - EDGE_CLR + 1e-9:
        xs.append(x + row.half)
        x += grid
    cands = []
    for oy in bands:
        for ox in xs:
            cx = ox + row.xs[-1] / 2
            cands.append((math.hypot(cx - row.tgt[0], oy - row.tgt[1]), ox, oy))
    cands.sort()                       # nearest first: the first legal slot wins
    for c in cands:
        if feasible(row, c[1], c[2], placed, G, lat):
            return c
    return best


# ----------------------------------------------------------------------------- apply

def apply(board, labels, rows, gnd_rows, pos, G):
    fps = G["fps"]
    bx0, by0 = G["bbox"][0], G["bbox"][1]
    final = {}
    for row in rows + gnd_rows:
        ox, oy = pos[row.name]
        for i, ref in enumerate(row.refs):
            final[ref] = (ox + row.xs[i], oy, row)
    # footprints
    for ref in sorted(final):
        f = fps[ref]
        x, y, row = final[ref]
        if not f.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(0)
        f.SetPosition(U.pt(x, y))
        for fld, dy in ((f.Reference(), 0.0), (f.Value(), 0.7)):
            fld.SetLayer(pcbnew.B_Fab)
            fld.SetVisible(True)
            fld.SetMirrored(True)
            fld.SetTextSize(pcbnew.VECTOR2I(U.iu(0.6), U.iu(0.6)))
            fld.SetTextThickness(U.iu(0.09))
            fld.SetTextAngleDegrees(0)
            fld.SetPosition(U.pt(x, y + dy))
    # labels: reuse existing B.SilkS texts by content, delete stray duplicates
    want = {labels[r]["label"]: r for r in final}
    if len(want) != len(final):
        raise SystemExit("duplicate test-pad labels")
    have = {}
    for d in list(board.GetDrawings()):
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetLayer() == pcbnew.B_SilkS and d.GetText() in want:
            if d.GetText() in have:
                board.Remove(d)
            else:
                have[d.GetText()] = d
    for lab, ref in sorted(want.items(), key=lambda kv: kv[1]):
        x, y, row = final[ref]
        r = U.mm(list(fps[ref].Pads())[0].GetSize().x) / 2.0
        L = label_len(lab)
        t = have.get(lab)
        if t is None:
            t = pcbnew.PCB_TEXT(board)
            board.Add(t)
        t.SetText(lab)
        t.SetLayer(pcbnew.B_SilkS)
        t.SetMirrored(True)
        t.SetTextSize(pcbnew.VECTOR2I(U.iu(LABEL_H), U.iu(LABEL_H)))
        t.SetTextThickness(U.iu(LABEL_THK))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetTextAngleDegrees(LABEL_ANGLE)
        t.SetPosition(U.pt(x, y + r + LABEL_GAP + L / 2.0))
    return final


LABEL_ANGLE = 270.0   # reads top to bottom when the board is turned over about its vertical axis (checked on the render)


def verify(board, labels, final, T, G):
    """Independent check of the written board: layers, pitch, row spacing, holes, edge, target distance."""
    fps = G["fps"]
    bx0, by0, bx1, by1 = G["bbox"]
    v = {"pads_on_bottom": 0, "bad_layers": [], "min_pitch_in_row": 1e9, "min_pad_to_pad": 1e9,
         "min_hole_edge_clearance": 1e9, "min_edge_clearance": 1e9, "max_target_dist": 0.0, "mean_target_dist": 0.0}
    pts = {}
    for ref in final:
        f = fps[ref]
        ls = {pcbnew.LayerName(l) for p in f.Pads() for l in p.GetLayerSet().Seq()}
        if f.GetLayerName() == "B.Cu" and ls <= {"B.Cu", "B.Mask", "B.Paste"} and "B.Cu" in ls:
            v["pads_on_bottom"] += 1
        else:
            v["bad_layers"].append((ref, sorted(ls)))
        pts[ref] = pos_mm(f)
    refs = sorted(pts)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            d = math.dist(pts[a], pts[b])
            v["min_pad_to_pad"] = min(v["min_pad_to_pad"], d)
            if final[a][2] is final[b][2]:
                v["min_pitch_in_row"] = min(v["min_pitch_in_row"], d)
    dt = []
    for ref in refs:
        x, y = pts[ref]
        r = U.mm(list(fps[ref].Pads())[0].GetSize().x) / 2.0
        for hx, hy, hr, _ in G["holes"]:
            v["min_hole_edge_clearance"] = min(v["min_hole_edge_clearance"], math.hypot(x - hx, y - hy) - hr - r)
        v["min_edge_clearance"] = min(v["min_edge_clearance"], x - r - bx0, bx1 - x - r, y - r - by0, by1 - y - r)
        if T.get(ref):
            dt.append(math.hypot(x - T[ref][0], y - T[ref][1]))
    v["max_target_dist"] = max(dt) if dt else 0.0
    v["mean_target_dist"] = sum(dt) / len(dt) if dt else 0.0
    return {k: (round(x, 2) if isinstance(x, float) else x) for k, x in v.items()}


def sidecar(path, board, labels, final, T, rows, gnd_rows, G, lat, phase, bands, ver=None):
    bx0, by0, bx1, by1 = G["bbox"]
    d = {"schema": 1, "board_bbox_mm": [bx0, by0, bx1, by1], "origin": "board-local = absolute - (bbox x0, y0)",
         "side": "B.Cu", "mirrored": True, "label_angle_deg": LABEL_ANGLE, "pitch_mm": PITCH, "lateral_gap_mm": lat,
         "band_phase_mm": phase, "verify": ver, "bands_y_mm": [round(b, 3) for b in bands], "pads": {}, "rows": []}
    for ref in sorted(final, key=lambda r: (int(re.sub(r"\D", "", r)))):
        x, y, row = final[ref]
        t = T.get(ref)
        d["pads"][ref] = {"x": round(x, 4), "y": round(y, 4), "local_x": round(x - bx0, 4), "local_y": round(y - by0, 4),
                          "rot": 0.0, "side": "bottom", "group": labels[ref]["group"], "label": labels[ref]["label"],
                          "row": row.name, "net": labels[ref].get("net", ""),
                          "target": None if not t else {"x": round(t[0], 3), "y": round(t[1], 3), "how": t[2]}}
    for row in rows + gnd_rows:
        ox, oy = final[row.refs[0]][0], final[row.refs[0]][1]
        d["rows"].append({"name": row.name, "group": row.group, "refs": row.refs, "n": row.n,
                          "y": round(oy, 3), "x0": round(ox, 3), "x1": round(ox + row.xs[-1], 3),
                          "label_len_mm": round(row.L, 2)})
    with open(path, "w") as f:
        json.dump(d, f, indent=1, sort_keys=False)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--out", help="write here instead of overwriting --board")
    ap.add_argument("--sidecar", help="JSON sidecar (default: testpads_bottom.json next to the output board)")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()

    spec = json.load(open(LABELS))
    labels = spec["pads"]
    out = a.out or a.board
    pro = os.path.splitext(a.board)[0] + ".kicad_pro"
    pcbnew.KIID.SeedGenerator(20261118)
    board = pcbnew.LoadBoard(a.board)
    G = gather(board, labels)
    missing = [r for r in labels if r not in G["fps"]]
    if missing:
        raise SystemExit("not on the board: %s" % missing)
    T = targets(board, labels, G)
    gnd_refs = sorted(r for r in labels if labels[r]["group"] == "gnd")
    rows, per = build_rows(labels, {r: (T[r] or (0, 0)) for r in labels if labels[r]["group"] != "gnd"}, G["fps"])
    best = None
    for lat in LAT_GAPS:
        best, pitch = place_rows(rows, gnd_refs, labels, T, G["fps"], G, lat)
        if not best[2]:
            break
    cost, pos, unplaced, bands, gnd_rows, phase = best
    if unplaced:
        raise SystemExit("could not place rows: %s" % unplaced)
    final = apply(board, labels, rows, gnd_rows, pos, G)
    print("lateral gap %.1f mm, band pitch %.2f mm, phase %.1f, %d bands, total target distance %.0f mm"
          % (lat, pitch, phase, len(bands), cost))
    for row in rows + gnd_rows:
        ox, oy = pos[row.name]
        print("  %-9s n=%2d  y=%7.2f  x=%7.2f..%7.2f" % (row.name, row.n, oy, ox, ox + row.xs[-1]))
    ver = verify(board, labels, final, T, G)
    print("verify:", json.dumps(ver))
    sc = a.sidecar or os.path.join(os.path.dirname(os.path.abspath(out)), "testpads_bottom.json")
    sidecar(sc, board, labels, final, T, rows, gnd_rows, G, lat, phase, bands, ver)
    if not a.no_save:
        if os.path.abspath(out) == os.path.abspath(a.board):
            U.save_board(board, out)
        else:
            board.Save(out)
            # an --out board keeps its own project; Save() above only touches <out>.kicad_pro if it exists
            opro = os.path.splitext(out)[0] + ".kicad_pro"
            if os.path.exists(pro) and os.path.exists(opro) and os.path.abspath(opro) != os.path.abspath(pro):
                import shutil
                shutil.copyfile(pro, opro)


if __name__ == "__main__":
    main()
