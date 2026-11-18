#!/usr/bin/env python3
"""TEST FIXTURE ONLY: put a throw-away placement on a scratch copy of the bay
station board so the routing tools have something to chew on.

This is NOT the real placement (another agent owns that).  It
  * hand-places the four DW3210 + RF1 chains + SMAs along the bottom edge
    (RF1 is pin 18 on the bottom side of the QFN, so a straight vertical line
    leaves it toward the SMA at the board edge),
  * places the clock buffer/TCXO/series parts between the anchors,
  * shelf-packs every other footprint by schematic sheet above them,
  * draws a rectangular Edge.Cuts outline.

    kicad-python make_test_board.py --out /scratch/dir [--src PLACED_OR_UNPLACED.kicad_pcb]

Writes <out>/bay-station.kicad_pcb (+ .kicad_pro/.kicad_dru/libs copied).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U

SPACING = 12.5
# chip order along the bottom edge: the right-hand buffer pins are Y1,Y3,Y2 top to bottom,
# (top to bottom) so A2,A3,A1 left to right lets their clock lines nest without crossing:
# a higher row must descend further right than a lower row
SLOT = {0: 0, 2: 1, 3: 2, 1: 3}
GAP = 0.7


def fp_size(f):
    cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if cy.GetWidth() > 0:
        return U.mm(cy.GetWidth()), U.mm(cy.GetHeight()), cy
    bb = f.GetBoundingBox(False)
    return U.mm(bb.GetWidth()), U.mm(bb.GetHeight()), bb


def place_center(f, x, y, rot=0.0):
    """Place so the courtyard/bbox CENTRE is at x,y after rotating."""
    f.SetOrientationDegrees(rot)
    f.SetPosition(U.pt(0, 0))
    _, _, bb = fp_size(f)
    cx = U.mm(bb.GetX() + bb.GetWidth() // 2)
    cy = U.mm(bb.GetY() + bb.GetHeight() // 2)
    f.SetPosition(U.pt(x - cx, y - cy))


def place_origin(f, x, y, rot=0.0):
    f.SetOrientationDegrees(rot)
    f.SetPosition(U.pt(x, y))


def pad_by_net(f, netname_part):
    for p in f.Pads():
        if netname_part in str(p.GetNetname()):
            return p
    return None


def build(src_pcb, out_dir):
    src_dir = os.path.dirname(src_pcb)
    U.scratch_copy(src_dir, out_dir)
    dst = os.path.join(out_dir, "bay-station.kicad_pcb")
    b = U.load_board(dst)
    fps = {str(f.GetReference()): f for f in b.GetFootprints()}
    placed = set()

    # --- anchors strip --------------------------------------------------
    W = 118.0
    anchors = []
    for n in range(4):
        anchors.append(dict(n=n, chip=fps["U%d" % (4 + n)], sma=fps["J%d" % (20 + n)],
                            c_rf=fps["C%d" % (47 + n)] if "C%d" % (47 + n) in fps else None))
    # find the RF chain parts by net (compare by reference: SWIG wrappers are never `is`-equal)
    def refs_on(netname):
        out = []
        for f in b.GetFootprints():
            for p in f.Pads():
                if str(p.GetNetname()) == netname:
                    out.append(str(f.GetReference()))
        return out
    for a in anchors:
        n = a["n"]
        cref = str(a["chip"].GetReference())
        a["c_rf"] = fps[[r for r in refs_on("/UWB Array/A%d_RF1" % n) if r != cref][0]]
        crf = str(a["c_rf"].GetReference())
        a["r_pi"] = fps[[r for r in refs_on("Net-(C%d-Pad1)" % (200 + 2 * n))
                         if r != crf and fps[r].GetValue() == "0R"][0]]
        a["r_term"] = fps[[r for r in refs_on("/UWB Array/A%d_RF2" % n) if r != cref][0]]

    # packing first to know the height
    special = set()
    for a in anchors:
        for k in ("chip", "sma", "c_rf", "r_pi", "r_term"):
            special.add(str(a[k].GetReference()))
    clock_refs = set()
    for n in range(4):
        for f in b.GetFootprints():
            for p in f.Pads():
                nm = str(p.GetNetname())
                if nm in ("/Clock Distribution/CLK_Y%d" % n, "/Clock Distribution/CLK_T%d" % n):
                    clock_refs.add(str(f.GetReference()))
                if nm == "UWB_CLK%d" % n and f.GetValue().startswith("2200"):
                    clock_refs.add(str(f.GetReference()))
    for f in b.GetFootprints():
        v = str(f.GetValue())
        if str(f.GetReference()) in ("U30", "U31", "R230"):
            clock_refs.add(str(f.GetReference()))
    special |= clock_refs

    rest = [f for r_, f in fps.items() if r_ not in special]
    groups = {}
    for f in rest:
        groups.setdefault(str(f.GetSheetname()), []).append(f)
    # shelf pack, each sheet starting a new shelf
    y = 4.0
    for sheet in sorted(groups):
        lst = sorted(groups[sheet], key=lambda f: -fp_size(f)[1])
        x = 4.0
        rowh = 0.0
        for f in lst:
            w, h, _ = fp_size(f)
            if x + w > W - 4.0:
                x = 4.0
                y += rowh + GAP
                rowh = 0.0
            place_center(f, x + w / 2, y + h / 2)
            x += w + GAP
            rowh = max(rowh, h)
        y += rowh + GAP * 2
    packed_h = y
    strip_top = packed_h + 2
    chip_y = strip_top + 22.0
    H = chip_y + 22.0

    # --- RF chains ---------------------------------------------------------
    x0 = (W - (3 * SPACING)) / 2
    for a in anchors:
        n = a["n"]
        xc = x0 + SLOT[n] * SPACING
        rot = None
        for r_ in (0, 90, 180, 270):
            place_origin(a["chip"], xc, chip_y, r_)
            q = [p for p in a["chip"].Pads() if str(p.GetNumber()) == "18"][0].GetPosition()
            dx, dy = U.mm(q.x) - xc, U.mm(q.y) - chip_y
            if dy > abs(dx):
                rot = r_
                break
        assert rot is not None
        xl = U.mm([p for p in a["chip"].Pads() if str(p.GetNumber()) == "18"][0].GetPosition().x)
        place_origin(a["sma"], xl, H, 180)
        place_origin(a["c_rf"], xl, chip_y + 4.1, 270)
        place_origin(a["r_pi"], xl, chip_y + 5.9, 270)
        place_origin(a["r_term"], U.mm([p for p in a["chip"].Pads() if str(p.GetNumber()) == "13"][0].GetPosition().x), chip_y + 4.4, 270)
        a["x"] = xc
    # --- clock parts ------------------------------------------------------
    u31, u30 = fps["U31"], fps["U30"]
    mid = x0 + 0.5 * SPACING
    place_center(u31, mid, strip_top + 5.0, 0)
    place_center(u30, mid - 16, strip_top + 6.0, 0)
    place_center(fps["R230"], mid - 7.5, strip_top + 5.0, 0)
    for a in anchors:
        n = a["n"]
        xc = a["x"]
        for f in b.GetFootprints():
            ref = str(f.GetReference())
            if ref not in clock_refs or ref in ("U30", "U31", "R230"):
                continue
            nets = {str(p.GetNetname()) for p in f.Pads()}
            if "/Clock Distribution/CLK_Y%d" % n in nets and "/Clock Distribution/CLK_T%d" % n in nets:
                # series 22R fanned out beside its buffer pin (pad1 = buffer side)
                bp = [p for p in u31.Pads() if str(p.GetNetname()) == "/Clock Distribution/CLK_Y%d" % n][0]
                bc = u31.GetPosition()
                side = 1 if U.mm(bp.GetPosition().x - bc.x) > 0 else -1
                dyp = U.mm(bp.GetPosition().y - bc.y)
                place_center(f, U.mm(bc.x) + side * 6.6, U.mm(bc.y) + dyp * 4.0, 0 if side > 0 else 180)
            elif "UWB_CLK%d" % n in nets and "/Clock Distribution/CLK_T%d" % n in nets:
                place_center(f, xc + 5.0, chip_y + 1.8, 180)                      # AC cap at XTI, pad on UWB_CLKn toward the chip
    # outline
    r = pcbnew.PCB_SHAPE(b)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(U.pt(0, 0)); r.SetEnd(U.pt(W, H))
    r.SetLayer(pcbnew.Edge_Cuts); r.SetWidth(U.iu(0.1))
    b.Add(r)
    U.save_board(b, dst)
    return dst, W, H, anchors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", default=os.path.join(U.REPO, "bay-station", "bay-station.kicad_pcb"))
    a = ap.parse_args()
    dst, W, H, _ = build(a.src, a.out)
    print("wrote", dst, "board %.1f x %.1f mm" % (W, H))
