#!/usr/bin/env python3
"""Make throw-away placed copies of the bay-station board to exercise silkscreen.py.

  python3 test_arrangements.py A|B <scratch_dir>

Copies bay-station/ into <scratch_dir>/<mode>/ and places every footprint with a quick
shelf packer (NOT a real layout; it is only a stand-in for the placement agent's board):
  A  loose grid, no rotation, 2.0 mm between courtyards, 150 mm wide board
  B  tight pack (0.5 mm), seeded random 0/90/180/270 rotations, 100 mm wide board
The repo's bay-station.kicad_pcb is never modified.  Needs KiCad's python (pcbnew).
"""
import os
import random
import shutil
import sys

import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "..", "bay-station"))


def main(mode, scratch):
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
    b.Save(pcb)
    open(pro, "wb").write(pro_bytes)
    print("%s: board %.0f x %.0f mm -> %s" % (mode, xe - xs, ye - ys, pcb))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
