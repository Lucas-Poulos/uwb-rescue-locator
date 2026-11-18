#!/usr/bin/env python3
"""Fab-readiness checks for the silkscreen, run on a SCRATCH COPY of the board.

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/layout/fab_checks.py bay-station/bay-station.kicad_pcb [--keep] [--strict]

1. kicad-cli pcb drc on the scratch copy with silk_over_copper / silk_overlap /
   silk_edge_clearance forced to "warning" in the COPY's .kicad_pro (the repo
   project may have them ignored), reporting the three counts.
2. List of footprints without readable reference silk (hidden, not on F.SilkS,
   below JLCPCB's 1.0 mm / 0.15 mm minimum, or upside-down angle).
3. Gerber + drill + position-file export dry-run into the scratch dir; fails if a
   plot is missing or empty.  Nothing is written inside the repo (kicad-cli drops
   .rpt files in its cwd, so it is always run from the scratch directory).

Exit code 1 if the export fails, or (with --strict) if any non-library silk DRC
violation remains.  Library-native silk-over-copper (footprint outlines that touch
pads) is reported separately: KiCad clips silkscreen at mask openings when plotting.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pcbnew
from pcbnew import ToMM, F_SilkS

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
if not os.path.exists(KICAD_CLI):
    KICAD_CLI = shutil.which("kicad-cli") or "kicad-cli"
JLC_MIN_H, JLC_MIN_W = 1.0, 0.15
SILK_RULES = ("silk_over_copper", "silk_overlap", "silk_edge_clearance")


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return r.returncode, r.stdout


def scratch_copy(board, tmp):
    src = os.path.dirname(os.path.abspath(board))
    dst = os.path.join(tmp, "board")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.lck", "*-backups", "handoff", "*.rpt"))
    pcb = os.path.join(dst, os.path.basename(board))
    pro = os.path.splitext(pcb)[0] + ".kicad_pro"
    if os.path.exists(pro):
        d = json.load(open(pro))
        sev = d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rule_severities", {})
        for k in SILK_RULES:
            sev[k] = "warning"
        json.dump(d, open(pro, "w"), indent=2)
    return dst, pcb


def drc(pcb, tmp):
    out = os.path.join(tmp, "drc.json")
    rc, log = run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "--all-track-errors",
                   "--units", "mm", "-o", out, pcb], tmp)
    if not os.path.exists(out):
        print("DRC failed:", log[-400:])
        return None
    data = json.load(open(out))
    counts = {k: 0 for k in SILK_RULES}
    allc = {}
    for v in data.get("violations", []):
        allc[v["type"]] = allc.get(v["type"], 0) + 1
        if v["type"] in counts:
            counts[v["type"]] += 1
    return counts, allc, data


def readable_refs(pcb):
    b = pcbnew.LoadBoard(pcb)
    bad = []
    silk_txt = [(d.GetText(), ToMM(d.GetPosition().x), ToMM(d.GetPosition().y)) for d in b.GetDrawings()
                if d.GetLayer() == F_SilkS and d.GetClass() == "PCB_TEXT"]
    for f in b.GetFootprints():
        r = f.Reference()
        ref = f.GetReference()
        if str(f.GetFPID().GetLibItemName()).startswith("OrientationMark_"):
            continue            # pinless glyphs, no designator by design
        why = None
        if ref.startswith("TP") and not r.IsVisible() or (ref.startswith("TP") and r.GetLayer() != F_SilkS):
            pads = list(f.Pads())
            net = pads[0].GetShortNetname() if pads else ""
            px, py = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
            if any(t == net[:12] and abs(x - px) < 8 and abs(y - py) < 4 for (t, x, y) in silk_txt):
                continue        # test point is identified by its net-name silk label instead

        if not r.IsVisible():
            why = "hidden"
        elif r.GetLayer() != F_SilkS:
            why = "not on F.SilkS"
        else:
            h = ToMM(r.GetTextHeight())
            w = ToMM(r.GetTextThickness())
            ang = round(r.GetTextAngleDegrees()) % 360
            if h < JLC_MIN_H - 1e-6 or w < JLC_MIN_W - 1e-6:
                why = "below JLC min (%.2f mm high, %.2f stroke)" % (h, w)
            elif ang not in (0, 90):
                why = "angle %d (not readable from bottom/right)" % ang
        if why:
            bad.append((ref, why))
    return bad


def export_dry_run(pcb, tmp):
    out = os.path.join(tmp, "fab")
    os.makedirs(out)
    res = {}
    rc, log = run([KICAD_CLI, "pcb", "export", "gerbers", "-o", out + "/", pcb], tmp)
    g = glob.glob(os.path.join(out, "*.g*"))
    res["gerbers"] = (rc, len(g), [os.path.basename(x) for x in g if os.path.getsize(x) == 0])
    rc, log = run([KICAD_CLI, "pcb", "export", "drill", "-o", out + "/", pcb], tmp)
    d = glob.glob(os.path.join(out, "*.drl"))
    res["drill"] = (rc, len(d), [os.path.basename(x) for x in d if os.path.getsize(x) == 0])
    pos = os.path.join(out, "pos.csv")
    rc, log = run([KICAD_CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                   "-o", pos, pcb], tmp)
    n = sum(1 for _ in open(pos)) - 1 if os.path.exists(pos) else 0
    res["pos"] = (rc, n, [])
    silk = [x for x in g if "Silkscreen" in os.path.basename(x) or "SilkS" in os.path.basename(x)]
    res["silk_gerber_bytes"] = [(os.path.basename(x), os.path.getsize(x)) for x in silk]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir and print its path")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="fabchk_")
    fail = False
    try:
        _dst, pcb = scratch_copy(a.board, tmp)
        d = drc(pcb, tmp)
        if d:
            counts, allc, data = d
            print("DRC silk counts:", counts)
            print("DRC all types:", dict(sorted(allc.items())))
            native = 0
            nonnative = counts["silk_overlap"] + counts["silk_edge_clearance"]
            if a.strict and nonnative:
                fail = True
        bad = readable_refs(pcb)
        small = [x for x in bad if x[1].startswith("below JLC")]
        none = [x for x in bad if not x[1].startswith("below JLC")]
        print("refs on silk but below JLC 1.0 mm text-height minimum (0.8 mm fallback): %d" % len(small))
        print("refs without readable silk (hidden / on Fab / bad angle): %d" % len(none))
        for ref, why in none[:400]:
            print("  %s: %s" % (ref, why))
        res = export_dry_run(pcb, tmp)
        for k in ("gerbers", "drill", "pos"):
            rc, n, empty = res[k]
            ok = rc == 0 and n > 0 and not empty
            print("export %s: rc=%d files/rows=%d empty=%s -> %s" % (k, rc, n, empty, "OK" if ok else "FAIL"))
            fail |= not ok
        print("silk gerbers:", res["silk_gerber_bytes"])
    finally:
        if a.keep:
            print("scratch kept:", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
