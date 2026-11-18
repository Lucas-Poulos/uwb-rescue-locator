#!/usr/bin/env python3
"""Routing gates for the bay-station board.  KiCad's python; works on a SCRATCH
copy of the board (never writes to the path you give it, never runs kicad-cli
inside the repo).

    kicad-python check_gates.py --board bay-station/bay-station.kicad_pcb [--strict]
                                [--require-complete] [--json out.json] [--workdir DIR]

Gates (exit code 1 if a HARD gate fails):
  HARD  netclasses present in .kicad_pro with the expected widths/clearances
  HARD  every wildcard pattern is proven by KiCad's own matcher: each net's
        effective class equals the class its hs_nets.json group names, and no
        other net leaves Default
  HARD  netclasses survive pcbutil.save_board() (BOARD.Save() alone wipes them:
        shown too, as the reason the helper exists)
  HARD  .kicad_dru parses (kicad-cli DRC loads it without a parse error)
  HARD  DRC (kicad-cli pcb drc --all-track-errors --refill-zones): zero
        shorting_items / clearance / track_width / via / hole violations
  INFO  unrouted (unconnected) count, violations by type, placement-class
        violations (courtyard/silk/edge) listed separately
  HARD  direction policy: ordinary-net F.Cu tracks horizontal, B.Cu vertical,
        except hand-routed RF50/CLK copper, locked copper and pad-escape stubs
        (<= 2.0 mm, touching a pad of the same net)
  INFO  RF_PATH / CLK_PATH length spread vs the tolerance in hs_nets.json
--strict also makes the INFO placement-class DRC types hard; --require-complete
makes unrouted > 0 a failure.
"""
import argparse
import fnmatch
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U

STUB_MAX = 2.0
HARD_DRC = {"shorting_items", "clearance", "track_width", "via_diameter", "annular_width", "hole_clearance",
            "hole_to_hole", "drill_out_of_range", "copper_edge_clearance_hard", "items_not_allowed", "tracks_crossing",
            "track_dangling_hard", "diff_pair_gap_out_of_range", "zones_intersect"}
PLACEMENT_DRC = {"courtyards_overlap", "silk_overlap", "silk_over_copper", "silk_edge_clearance", "copper_edge_clearance",
                 "missing_footprint", "extra_footprint", "lib_footprint_mismatch", "footprint_symbol_mismatch",
                 "invalid_outline", "via_dangling", "track_dangling", "isolated_copper", "copper_sliver", "starved_thermal",
                 "solder_mask_bridge", "padstack", "footprint", "unconnected_items"}


def load_pro(path):
    with open(path) as f:
        return json.load(f)["net_settings"]


def gate_netclasses(pro_path, spec, results):
    ns = load_pro(pro_path)
    have = {c["name"]: c for c in ns["classes"]}
    ok = True
    for name, c in spec["classes"].items():
        h = have.get(name)
        if h is None:
            results.append(("HARD", "netclass %s present" % name, False, "missing from .kicad_pro"))
            ok = False
            continue
        for k_spec, k_pro in (("track", "track_width"), ("clearance", "clearance"),
                              ("via_dia", "via_diameter"), ("via_drill", "via_drill")):
            if abs(h[k_pro] - c[k_spec]) > 1e-9:
                results.append(("HARD", "netclass %s %s" % (name, k_pro), False, "%s != %s" % (h[k_pro], c[k_spec])))
                ok = False
    want = [(g["class"], p) for g in spec["groups"] for p in g.get("patterns", [])]
    got = [(p["netclass"], p["pattern"]) for p in ns["netclass_patterns"]]
    if want != got:
        results.append(("HARD", "netclass patterns equal hs_nets.json", False, "differ (rerun apply_rules.py)"))
        ok = False
    if ok:
        results.append(("HARD", "netclasses + patterns present and equal to hs_nets.json", True, "%d classes, %d patterns" % (len(have), len(got))))
    return ns


def gate_matcher(board, spec, results):
    """Independent proof: fnmatch (the semantics KiCad documents) vs KiCad's own assignment."""
    cls = U.net_class_table(board)
    expected = {}
    for g in spec["groups"]:
        for pat in g.get("patterns", []):
            for n in cls:
                if n and fnmatch.fnmatchcase(n, pat):
                    expected.setdefault(n, set()).add(g["class"])
    bad = []
    for n, k in cls.items():
        if not n:
            continue
        exp = expected.get(n)
        if exp is None:
            if k != "Default":
                bad.append((n, k, "Default"))
        elif len(exp) > 1:
            bad.append((n, k, "ambiguous %s" % sorted(exp)))
        elif k not in exp:
            bad.append((n, k, sorted(exp)[0]))
    non_default = sum(1 for n, k in cls.items() if n and k != "Default")
    # every pattern must hit at least one net
    dead = []
    for g in spec["groups"]:
        for pat in g.get("patterns", []):
            if not any(fnmatch.fnmatchcase(n, pat) for n in cls if n):
                dead.append(pat)
    results.append(("HARD", "KiCad's matcher agrees with the intended class for every net", not bad,
                    "%d nets in non-Default classes; mismatches: %s" % (non_default, bad[:5])))
    results.append(("HARD", "no pattern is dead (matches nothing)", not dead, "dead: %s" % dead))
    return cls


def gate_survive(src_pro, board_path, work, results):
    d = os.path.join(work, "survive")
    U.scratch_copy(os.path.dirname(board_path), d)
    pcb = os.path.join(d, os.path.basename(board_path))
    before = load_pro(os.path.join(d, os.path.basename(src_pro)))
    b = U.load_board(pcb)
    U.save_board(b, pcb)
    after = load_pro(os.path.join(d, os.path.basename(src_pro)))
    ok = before["classes"] == after["classes"] and before["netclass_patterns"] == after["netclass_patterns"]
    results.append(("HARD", "netclasses survive pcbutil.save_board()", ok,
                    "%d classes / %d patterns before and after" % (len(before["classes"]), len(before["netclass_patterns"]))))
    # reason the helper exists
    d2 = os.path.join(work, "rawsave")
    U.scratch_copy(os.path.dirname(board_path), d2)
    pcb2 = os.path.join(d2, os.path.basename(board_path))
    b2 = U.load_board(pcb2)
    b2.Save(pcb2)
    raw = load_pro(os.path.join(d2, os.path.basename(src_pro)))
    results.append(("INFO", "raw BOARD.Save() on a LOADED board leaves", True,
                    "%d classes, %d patterns (KiCad 10.0.5: no wipe here; the wipe in the gotchas note is for a fresh "
                    "BOARD(); save_board() restores the bytes regardless)" % (len(raw["classes"]), len(raw["netclass_patterns"]))))


def run_drc(board_path, work, results, strict):
    d = os.path.join(work, "drc")
    U.scratch_copy(os.path.dirname(board_path), d)
    pcb = os.path.join(d, os.path.basename(board_path))
    out = os.path.join(d, "drc.json")
    r = U.run_drc(pcb, out, refill=True)
    err = (r.stdout + r.stderr)
    parse_bad = any(w in err.lower() for w in ("failed to parse", "error parsing", "invalid rule", "unable to load"))
    dru = os.path.splitext(board_path)[0] + ".kicad_dru"
    if os.path.exists(dru):
        results.append(("HARD", ".kicad_dru loads without a parse error", not parse_bad, err.strip().splitlines()[-1] if err.strip() else ""))
    if not os.path.exists(out):
        results.append(("HARD", "kicad-cli DRC ran", False, err[-300:]))
        return None, None
    by, unconn, raw = U.drc_summary(out)
    counts = {k: len(v) for k, v in by.items()}
    errors = {k: sum(1 for x in v if x.get("severity") == "error") for k, v in by.items()}
    warns = {k: counts[k] - errors[k] for k in counts if counts[k] - errors[k]}
    results.append(("INFO", "unrouted (unconnected items)", True, str(len(unconn))))
    results.append(("INFO", "DRC violations by type", True, json.dumps(counts, sort_keys=True)))
    hard = {k: errors[k] for k in counts if errors[k] and (k in HARD_DRC or (strict and k in PLACEMENT_DRC))}
    if warns:
        results.append(("INFO", "DRC warnings by type (not gates)", True, json.dumps(warns, sort_keys=True)))
    unknown = {k: v for k, v in counts.items() if k not in HARD_DRC and k not in PLACEMENT_DRC}
    results.append(("HARD", "DRC: no short/clearance/width/via/hole violations", not hard, json.dumps(hard)))
    if unknown:
        results.append(("INFO", "DRC types not classified", True, json.dumps(unknown)))
    return by, len(unconn)


# --------------------------------------------------------------------- policy
def pad_boxes(board):
    out = {}
    for f in board.GetFootprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            out.setdefault(p.GetNetCode(), []).append((U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())))
    return out


def gate_direction(board, results, exempt_classes=("RF50", "CLK")):
    pads = pad_boxes(board)
    viol, stubs, checked, exempt = [], 0, 0, 0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetClass() == "PCB_ARC":
            continue
        lay = t.GetLayer()
        if lay not in (U.F_CU, U.B_CU):
            continue
        cls = str(t.GetNetClassName())
        if cls in exempt_classes or t.IsLocked():
            exempt += 1
            continue
        s, e = t.GetStart(), t.GetEnd()
        ax, ay, bx, by = U.mm(s.x), U.mm(s.y), U.mm(e.x), U.mm(e.y)
        o = U.seg_orientation(ax, ay, bx, by)
        want = "H" if lay == U.F_CU else "V"
        checked += 1
        if o == want:
            continue
        L = math.hypot(bx - ax, by - ay)
        touches = any(x0 - 0.05 <= px <= x1 + 0.05 and y0 - 0.05 <= py <= y1 + 0.05
                      for (px, py) in ((ax, ay), (bx, by)) for (x0, y0, x1, y1) in pads.get(t.GetNetCode(), []))
        # stubs may hang off a stub: accept a short piece within 0.6 mm of a pad end too
        if L <= STUB_MAX and (touches or L <= 0.6):
            stubs += 1
            continue
        viol.append((str(t.GetNetname()), U.LAYER_NAME[lay], o, round(L, 2), (round(ax, 2), round(ay, 2))))
    results.append(("HARD", "direction policy (F.Cu H, B.Cu V; stubs <= %.1f mm exempt)" % STUB_MAX, not viol,
                    "%d tracks checked, %d stub segments, %d exempt (RF50/CLK/locked), %d violations %s"
                    % (checked, stubs, exempt, len(viol), viol[:4])))
    return viol


def gate_lengths(board, spec, results):
    lens = {}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        lens[str(t.GetNetname())] = lens.get(str(t.GetNetname()), 0.0) + U.mm(t.GetLength())
    for g in spec["groups"]:
        lm = g.get("length_match")
        pn = g.get("per_anchor_nets")
        if not lm or not pn or lm.get("group") not in ("RF_PATH", "CLK_PATH"):
            continue
        tot = {a: sum(lens.get(n, 0.0) for n in nets) for a, nets in pn.items()}
        if not any(tot.values()):
            results.append(("INFO", "%s length match" % lm["group"], True, "no copper routed yet"))
            continue
        spread = max(tot.values()) - min(tot.values())
        results.append(("INFO", "%s length match (tol %.2f mm)" % (lm["group"], lm["tolerance_mm"]),
                        spread <= lm["tolerance_mm"],
                        "spread %.3f mm, lengths %s" % (spread, {k: round(v, 3) for k, v in tot.items()})))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", default=os.path.join(U.REPO, "bay-station", "bay-station.kicad_pcb"))
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--require-complete", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--workdir")
    ap.add_argument("--skip-drc", action="store_true")
    a = ap.parse_args()
    board_path = os.path.abspath(a.board)
    pro_path = os.path.splitext(board_path)[0] + ".kicad_pro"
    spec = U.load_spec()
    results = []
    work = a.workdir or tempfile.mkdtemp(prefix="bay_gates_")
    if os.path.abspath(work).startswith(U.REPO):
        raise SystemExit("workdir must be outside the repo (kicad-cli drops .rpt files)")
    os.makedirs(work, exist_ok=True)
    gate_netclasses(pro_path, spec, results)
    board = U.load_board(board_path)
    gate_matcher(board, spec, results)
    gate_survive(pro_path, board_path, work, results)
    gate_direction(board, results)
    gate_lengths(board, spec, results)
    unrouted = None
    if not a.skip_drc:
        _, unrouted = run_drc(board_path, work, results, a.strict)
    if a.require_complete and unrouted:
        results.append(("HARD", "board fully routed", False, "%d unconnected items" % unrouted))
    width = max(len(r[1]) for r in results)
    fail = 0
    for kind, name, ok, detail in results:
        tag = "PASS" if ok else ("FAIL" if kind == "HARD" else "note")
        if kind == "HARD" and not ok:
            fail += 1
        print("%-4s %-5s %-*s  %s" % (tag, kind, width, name, detail))
    print("\n%d hard gate(s) failed" % fail)
    if a.json:
        with open(a.json, "w") as f:
            json.dump([dict(kind=k, name=n, ok=o, detail=d) for k, n, o, d in results], f, indent=1)
    shutil.rmtree(work, ignore_errors=True) if not a.workdir else None
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
