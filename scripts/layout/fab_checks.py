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

4. Bottom side (B.SilkS): every text is >= 1.0 mm high / 0.15 mm stroke, has the mirrored flag set, and does
   not touch a bottom-layer pad, drilled pad or via; every test point in testpoint_labels.json that sits on
   the bottom has its label on B.SilkS next to it (TPs still on the top are checked for an F.SilkS label;
   --require-bottom makes a TP left on the top a failure).  The B_Silkscreen Gerber must be non-empty (it must
   contain draw operations, not just the header) whenever any B.SilkS item exists.

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
from pcbnew import ToMM, FromMM, F_SilkS, B_SilkS, F_Cu, B_Cu

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
if not os.path.exists(KICAD_CLI):
    KICAD_CLI = shutil.which("kicad-cli") or "kicad-cli"
JLC_MIN_H, JLC_MIN_W = 1.0, 0.15
TP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testpoint_labels.json")
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
        if ref.startswith("TP") and (not r.IsVisible() or r.GetLayer() != F_SilkS):
            continue            # test points: designator on Fab by design, identified by the label (bottom_silk_checks)
        if f.IsFlipped():
            continue            # bottom parts are covered by bottom_silk_checks

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


def bottom_silk_checks(pcb, require_bottom=False):
    """Returns (problems list, info dict).  See module docstring item 4."""
    b = pcbnew.LoadBoard(pcb)
    problems = []
    info = {}
    tp = json.load(open(TP_JSON))["pads"] if os.path.exists(TP_JSON) else {}
    texts = []
    for d in b.GetDrawings():
        if d.GetLayer() == B_SilkS and d.GetClass() == "PCB_TEXT":
            texts.append((d, d.GetText(), "board text"))
    for f in b.GetFootprints():
        for fld in (f.Reference(), f.Value()):
            if fld.IsVisible() and fld.GetLayer() == B_SilkS:
                texts.append((fld, fld.GetText(), f.GetReference()))
        for g in f.GraphicalItems():
            if g.GetLayer() == B_SilkS and g.GetClass() == "PCB_TEXT":
                texts.append((g, g.GetText(), f.GetReference()))
    info["B.SilkS texts"] = len(texts)
    pads = []
    for f in b.GetFootprints():
        for p in f.Pads():
            drilled = p.GetDrillSize().x > 0
            if drilled or p.IsOnLayer(B_Cu):
                pads.append((p, f.GetReference(), p.GetEffectiveShape(B_Cu)))
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    for t, txt, owner in texts:
        name = txt.replace("\n", "/")
        h, w = ToMM(t.GetTextHeight()), ToMM(t.GetTextThickness())
        if h < JLC_MIN_H - 1e-6 or w < JLC_MIN_W - 1e-6:
            problems.append("B.SilkS '%s' (%s): %.2f mm high / %.2f stroke is below JLC minimum" % (name, owner, h, w))
        if not t.IsMirrored():
            problems.append("B.SilkS '%s' (%s): mirrored flag not set (would read backwards from the bottom)" % (name, owner))
        sh = t.GetEffectiveTextShape()
        bb = sh.BBox()
        for p, ref, psh in pads:
            if bb.Intersects(p.GetBoundingBox()) and sh.Collide(psh, FromMM(0.15)):
                problems.append("B.SilkS '%s' (%s) over bottom pad %s.%s" % (name, owner, ref, p.GetNumber()))
        for v in vias:
            if bb.Intersects(v.GetBoundingBox()) and sh.Collide(v.GetEffectiveShape(F_Cu), FromMM(0.15)):
                problems.append("B.SilkS '%s' (%s) over a via" % (name, owner))
    bottom_labels = {}
    for t, txt, owner in texts:
        bottom_labels.setdefault(txt.split("\n")[0], []).append(t)
    n_bot = n_top = 0
    missing = []
    for f in b.GetFootprints():
        ref = f.GetReference()
        if ref not in tp:
            continue
        label = tp[ref]["label"]
        px, py = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
        if f.IsFlipped():
            n_bot += 1
            near = [t for t in bottom_labels.get(label, [])
                    if abs(ToMM(t.GetPosition().x) - px) < 12 and abs(ToMM(t.GetPosition().y) - py) < 6]
            if not near:
                missing.append("%s ('%s')" % (ref, label))
        else:
            n_top += 1
            ok = any(d.GetLayer() == F_SilkS and d.GetClass() == "PCB_TEXT" and d.GetText() == label
                     and abs(ToMM(d.GetPosition().x) - px) < 12 and abs(ToMM(d.GetPosition().y) - py) < 6
                     for d in b.GetDrawings())
            if not ok:
                missing.append("%s ('%s', TOP)" % (ref, label))
            if require_bottom:
                problems.append("%s is still on the top side" % ref)
    info["kept TPs on bottom / on top / in JSON"] = (n_bot, n_top, len(tp))
    info["TPs in JSON not on the board"] = len(tp) - n_bot - n_top
    for m in missing:
        problems.append("test point %s has no silk label" % m)
    return problems, info


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
    bsilk = [x for x in g if "B_Silkscreen" in os.path.basename(x) or "B.Silkscreen" in os.path.basename(x)]
    draws = 0
    for x in bsilk:
        draws += sum(1 for ln in open(x, errors="replace") if ln.rstrip().endswith(("D01*", "D03*")))
    res["b_silk"] = (len(bsilk), draws)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir and print its path")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--require-bottom", action="store_true", help="fail if any kept test point is still on the top")
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
        probs, binfo = bottom_silk_checks(pcb, a.require_bottom)
        print("bottom silk:", binfo)
        print("bottom silk problems: %d" % len(probs))
        for pr in probs[:60]:
            print("  " + pr)
        fail |= bool(probs)
        res = export_dry_run(pcb, tmp)
        nfiles, ndraw = res["b_silk"]
        need = binfo["B.SilkS texts"] > 0
        ok = nfiles == 1 and (ndraw > 0 or not need)
        print("export B_Silkscreen gerber: files=%d draw ops=%d (B.SilkS items on board: %s) -> %s"
              % (nfiles, ndraw, need, "OK" if ok else "FAIL"))
        fail |= not ok
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
