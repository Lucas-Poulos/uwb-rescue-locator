#!/usr/bin/env python3
"""Make throw-away placed copies of the bay-station board to exercise silkscreen.py.

  python3 test_arrangements.py A|B|T <scratch_dir> [--tp-bottom]

Copies bay-station/ into <scratch_dir>/<mode>/ and places every footprint with a quick
shelf packer (NOT a real layout; it is only a stand-in for the placement agent's board):
  A  loose grid, no rotation, 2.0 mm between courtyards, 150 mm wide board
  B  tight pack (0.5 mm), seeded random 0/90/180/270 rotations, 100 mm wide board
  T  keep the repo's placement as is (no re-packing); only useful with --tp-bottom
--tp-bottom flips every TP* footprint to the BOTTOM side and lays them out in function rows
(testpoint_labels.json groups, small groups share a line) inside the outline, as a stand-in for the
real bottom placement.
The repo's bay-station.kicad_pcb is never modified.  Needs KiCad's python (pcbnew).
"""
import json
import os
import random
import shutil
import sys

import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "..", "bay-station"))


def flip_tps_to_bottom(b, line_pitch=6.5):
    """Flip all TP* footprints to B.Cu and place them in function rows (one JSON group per row run)."""
    J = json.load(open(os.path.join(HERE, "testpoint_labels.json")))
    groups, pads = J["groups"], J["pads"]
    ex = [d.GetBoundingBox() for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    x0 = min(ToMM(e.GetLeft()) for e in ex) + 5.0
    x1 = max(ToMM(e.GetRight()) for e in ex) - 8.0
    y0 = min(ToMM(e.GetTop()) for e in ex) + 6.0
    tps = {f.GetReference(): f for f in b.GetFootprints() if f.GetReference().startswith("TP")}
    # obstacles on the bottom: drilled pads of the parts that stay.  Vias are NOT avoided: instead every via
    # inside a row's reserved corridor is deleted afterwards (a real placement reserves that corridor before routing).
    obst = []
    for f in b.GetFootprints():
        if f.GetReference() in tps:
            continue
        for p in f.Pads():
            if p.GetDrillSize().x > 0:
                bb = p.GetBoundingBox()
                obst.append((ToMM(bb.GetLeft()) - 0.5, ToMM(bb.GetTop()) - 0.5, ToMM(bb.GetRight()) + 0.5,
                             ToMM(bb.GetBottom()) + 0.5))
    placed = []

    def clear(x, y, w):
        reg = (x - 1.2, y - 1.5, x - 1.2 + w, y + 3.3)
        return not any(reg[0] < o[2] and o[0] < reg[2] and reg[1] < o[3] and o[1] < reg[3] for o in obst + placed)

    x, y, first = x0, y0, True
    for g in groups:
        refs = sorted([r for r in tps if pads.get(r, {}).get("group") == g], key=lambda r: int(r[2:]))
        for r in refs:
            f = tps[r]
            w = 0.9 * len(pads[r]["label"]) + 2.5
            while not clear(x, y, w):
                x += 1.0
                if x > x1:
                    x, y = x0, y + line_pitch
            f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            placed.append((x - 1.2, y - 1.5, x - 1.2 + w, y + 3.3))
            x += w - 1.2
        x += 3.0            # gap between functions on the same line
        if x > x1 - 25:     # keep a function row from starting at the very end of a line
            x, y = x0, y + line_pitch
    dead = []
    for t in list(b.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            px, py = ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)
            if any(o[0] - 0.5 < px < o[2] + 0.5 and o[1] - 0.5 < py < o[3] + 0.5 for o in placed):
                dead.append(t)
    for t in dead:
        b.Remove(t)
    print("removed %d vias from the reserved bottom corridors" % len(dead))
    for r, f in tps.items():     # TPs not in the JSON (should not happen after the cut)
        if not f.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    print("bottom rows end at y=%.1f mm" % y)


def main(mode, scratch, tp_bottom=False):
    dst = os.path.join(scratch, mode)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("handoff", "*.lck", "*-backups"))
    pcb = os.path.join(dst, "bay-station.kicad_pcb")
    pro = os.path.join(dst, "bay-station.kicad_pro")
    pro_bytes = open(pro, "rb").read()
    b = pcbnew.LoadBoard(pcb)
    rnd = random.Random(7)
    gap, width = (2.0, 150.0) if mode == "A" else (0.5, 100.0)
    if mode == "T":
        if tp_bottom:
            flip_tps_to_bottom(b)
        b.Save(pcb)
        open(pro, "wb").write(pro_bytes)
        print("T: %s" % pcb)
        return
    fps = sorted(b.GetFootprints(), key=lambda f: (f.GetReference()[0] not in "UJBH", -f.GetCourtyard(pcbnew.F_CrtYd).BBox().GetWidth() * f.GetCourtyard(pcbnew.F_CrtYd).BBox().GetHeight()))
    x0, y0 = 10.0, 10.0
    x, y, rowh = x0, y0, 0.0
    maxx = 0.0
    for f in fps:
        if mode == "B" and f.GetPadCount() <= 6 and not f.GetReference().startswith(("H", "FID")):
            f.SetOrientationDegrees(rnd.choice([0, 90, 180, 270]))
        f.SetPosition(VECTOR2I(0, 0))
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bb = cy.BBox()
        else:
            bb = f.GetBoundingBox(False)
        w, h = ToMM(bb.GetWidth()), ToMM(bb.GetHeight())
        if x + w > x0 + width:
            x, y, rowh = x0, y + rowh + gap, 0.0
        f.SetPosition(VECTOR2I(FromMM(x - ToMM(bb.GetLeft())), FromMM(y - ToMM(bb.GetTop()))))
        x += w + gap
        rowh = max(rowh, h)
        maxx = max(maxx, x)
    old_edges = [d for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]  # keep wrappers alive after Remove
    for d in old_edges:                  # the repo board already has its own outline: replace it
        b.Remove(d)
    ymax = y + rowh
    m = 4.0
    xs, xe, ys, ye = x0 - m, maxx - gap + m, y0 - m, ymax + m
    for (a, c_, d, e) in ((xs, ys, xe, ys), (xe, ys, xe, ye), (xe, ye, xs, ye), (xs, ye, xs, ys)):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(VECTOR2I(FromMM(a), FromMM(c_)))
        s.SetEnd(VECTOR2I(FromMM(d), FromMM(e)))
        s.SetWidth(FromMM(0.1))
        b.Add(s)
    if tp_bottom:
        flip_tps_to_bottom(b)
    b.Save(pcb)
    open(pro, "wb").write(pro_bytes)
    print("%s: board %.0f x %.0f mm -> %s" % (mode, xe - xs, ye - ys, pcb))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--tp-bottom" in sys.argv)
