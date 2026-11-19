#!/usr/bin/env python3
"""Render the BOTTOM side of a bay-station board to a PNG (viewed from below, i.e. mirrored).

    python3 scripts/layout/render_bottom.py BOARD.kicad_pcb out.png [--dpi 220] [--no-courtyards]
                                            [--crop x0 y0 x1 y1]   (board-local mm, as seen from the TOP)

Uses KiCad's own plotter (kicad-cli pcb export pdf --mirror, run from a scratch directory so no .rpt
lands in the repo), then pdftoppm and PIL (system python3).  Layers: Edge.Cuts, B.Cu, B.Mask outlines
are not drawn; B.Silkscreen carries the test-pad labels, F.Courtyard (mirrored, grey) shows where the top-side
parts are so the pads can be judged against them.  The mirrored picture is what a probe user sees
when the board is turned over about its vertical axis, so the labels must read normally.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("png")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--no-courtyards", action="store_true")
    ap.add_argument("--title", default="Bay station, bottom side (viewed from below, mirrored)")
    a = ap.parse_args()

    layers = ["Edge.Cuts", "B.Cu", "B.Silkscreen"]
    if not a.no_courtyards:
        layers.append("F.Courtyard")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.abspath(a.board)
        stem = os.path.splitext(src)[0]
        dst = os.path.join(tmp, "b.kicad_pcb")
        shutil.copyfile(src, dst)
        if os.path.exists(stem + ".kicad_pro"):
            shutil.copyfile(stem + ".kicad_pro", os.path.join(tmp, "b.kicad_pro"))
        pdf = os.path.join(tmp, "b.pdf")
        cmd = [KICAD_CLI, "pcb", "export", "pdf", "--mirror", "--mode-single", "--exclude-refdes", "--exclude-value",
               "--black-and-white", "-l", ",".join(layers), "-o", pdf, dst]
        r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        if r.returncode or not os.path.exists(pdf):
            sys.exit("kicad-cli failed: " + r.stdout + r.stderr)
        base = os.path.join(tmp, "page")
        subprocess.run(["pdftoppm", "-r", str(a.dpi), "-png", "-singlefile", pdf, base], check=True)
        img = Image.open(base + ".png").convert("RGB")
    # trim the page margin
    bg = Image.new("RGB", img.size, (255, 255, 255))
    from PIL import ImageChops
    bbox = ImageChops.difference(img, bg).getbbox()
    if bbox:
        pad = 20
        img = img.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad)))
    try:
        font = ImageFont.load_default(size=22)
    except Exception:
        font = ImageFont.load_default()
    out = Image.new("RGB", (img.width, img.height + 40), (255, 255, 255))
    out.paste(img, (0, 40))
    ImageDraw.Draw(out).text((10, 8), a.title, fill=(0, 0, 0), font=font)
    out.save(a.png)
    print("wrote", a.png, out.size)


if __name__ == "__main__":
    main()
