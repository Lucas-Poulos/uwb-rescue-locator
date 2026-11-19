#!/usr/bin/env python3
"""Run the whole bay-station layout pipeline, stage by stage, on a COPY of the board.

    python3 scripts/layout/run_pipeline.py [--board bay-station/bay-station.kicad_pcb]
            [--workdir DIR] [--stages a,b,c | --skip a,b] [--jobs 6] [--seconds 900] [--silk]
            [--keep-going] [--in-place] [--dry-run]

Any python3 runs this driver; every stage is a subprocess with KiCad's own python (or kicad-cli),
cwd = the log directory (kicad-cli drops .rpt files in its cwd, so never the repo), one log file per
stage, md5 of the board after each stage.  The repo board is never written unless --in-place
(and then only after every selected stage succeeded).

Stages, in order (a stage whose script is not in scripts/layout is SKIPPED with a note, so the driver
works while other stages are still being merged):

  cutouts    stitch.py --cutouts-only          DW3210 cut-out + tie rule areas (before anything is routed)
  fanout     fanout.py                         stub + via for every non-HS pad (its doc: before the test pads)
  testpads   place_testpads_bottom.py          test pads to the bottom side
  hs         route_hs_uwb.py all               RF chains, DW3210 GND ties first, clocks (CLK0 spurs counted),
                                               LTE/GNSS/TCXO, other HS-chip ties   (exit 2 = a hop unrouted)
  power      route_power.py                    power stages and distribution
  hs_finish  hs_finish.py                      corners, mask openings, fence (hs_finish agent)
  manhattan  route_manhattan.py --jobs N       ordinary nets
  stitch     stitch.py --zones --rescue auto   lattice, DW3210 cut-outs, GND pours, GND pad ties
  fill       kicad-cli pcb drc --refill-zones --save-board   on a scratch copy (never in process)
  drc        kicad-cli pcb drc --all-track-errors on the filled copy; counts, unconnected items
  gates      check_gates.py --json             every gate (its own refill + DRC)
  silk       silkscreen.py                     only with --silk or --stages ...,silk

Stopping rule: a stage that exits non-zero stops the run with a message naming the log (hs may exit 2
for an unrouted hop; --keep-going continues anyway).  The `gates` stage failing is reported at the end
(exit 1) but nothing after it is skipped.  Result: WORKDIR/pipeline.json and a summary table.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
KP = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
ORDER = ["cutouts", "fanout", "testpads", "hs", "power", "hs_finish", "manhattan", "stitch", "fill", "drc", "gates", "silk"]
DEFAULT = [s for s in ORDER if s != "silk"]
SCRIPT = {"cutouts": "stitch.py", "fanout": "fanout.py", "testpads": "place_testpads_bottom.py", "hs": "route_hs_uwb.py",
          "power": "route_power.py", "hs_finish": "hs_finish.py", "manhattan": "route_manhattan.py", "stitch": "stitch.py",
          "gates": "check_gates.py", "silk": "silkscreen.py"}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:12]


class Pipe:
    def __init__(self, a):
        self.a = a
        self.work = os.path.abspath(a.workdir or tempfile.mkdtemp(prefix="bay_pipe_"))
        if self.work.startswith(REPO):
            raise SystemExit("workdir must be outside the repo (kicad-cli drops .rpt files)")
        self.bdir = os.path.join(self.work, "board")
        self.logs = os.path.join(self.work, "logs")
        os.makedirs(self.logs, exist_ok=True)
        src = os.path.abspath(a.board)
        self.src = src
        if os.path.isdir(self.bdir):
            shutil.rmtree(self.bdir)
        shutil.copytree(os.path.dirname(src), self.bdir, ignore=shutil.ignore_patterns("*.rpt", "*.lck", "*-backups", "fp-info-cache"))
        base = os.path.splitext(os.path.basename(src))[0]
        self.pcb = os.path.join(self.bdir, base + ".kicad_pcb")
        self.res = []          # stage records
        self.notes = {}
        self.n = 0

    def run(self, name, cmd, env_ok=(0,)):
        self.n += 1
        log = os.path.join(self.logs, "%02d_%s.log" % (self.n, name))
        t0 = time.time()
        with open(log, "w") as f:
            f.write("$ %s\n" % " ".join(cmd))
            f.flush()
            p = subprocess.run(cmd, cwd=self.logs, stdout=f, stderr=subprocess.STDOUT)
        dt = time.time() - t0
        rec = dict(stage=name, rc=p.returncode, seconds=round(dt, 1), log=log, md5=md5(self.pcb) if os.path.exists(self.pcb) else None,
                   ok=p.returncode in env_ok)
        self.res.append(rec)
        print("%-10s rc=%d %6.1fs  board md5 %s  log %s" % (name, p.returncode, dt, rec["md5"], log), flush=True)
        return rec, log

    def tail(self, log, pat=None, n=6):
        lines = [l for l in open(log, errors="replace").read().splitlines() if "traits" not in l and "GetWidth" not in l]
        if pat:
            lines = [l for l in lines if re.search(pat, l)]
        return lines[-n:]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=os.path.join(REPO, "bay-station", "bay-station.kicad_pcb"))
    ap.add_argument("--workdir", help="scratch dir OUTSIDE the repo (default: a new temp dir)")
    ap.add_argument("--stages", help="comma list, default: " + ",".join(DEFAULT))
    ap.add_argument("--skip", help="comma list of stages to leave out")
    ap.add_argument("--silk", action="store_true", help="also run silkscreen.py at the end")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=900.0, help="route_manhattan.py time budget")
    ap.add_argument("--keep-going", action="store_true", help="continue after a failing stage (default: stop)")
    ap.add_argument("--in-place", action="store_true", help="copy the final board over --board when all stages succeeded")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    a = ap.parse_args()

    sel = [s.strip() for s in (a.stages.split(",") if a.stages else DEFAULT) if s.strip()]
    if a.silk and "silk" not in sel:
        sel.append("silk")
    bad = [s for s in sel if s not in ORDER]
    if bad:
        raise SystemExit("unknown stage(s) %s; stages are %s" % (bad, ORDER))
    skip = set((a.skip or "").split(","))
    sel = [s for s in ORDER if s in sel and s not in skip]
    plan, missing = [], []
    for s in sel:
        sc = SCRIPT.get(s)
        p = os.path.join(HERE, sc) if sc else None
        if sc and (not os.path.exists(p) or "__main__" not in open(p).read()):     # absent, or a library without a CLI yet
            missing.append(s)
        else:
            plan.append(s)
    print("plan:", " -> ".join(plan), "| skipped (script absent): %s" % (missing or "none"))
    if a.dry_run:
        return
    P = Pipe(a)
    print("workdir", P.work, "| board copy", P.pcb, "md5", md5(P.pcb), flush=True)
    L = lambda s: os.path.join(HERE, s)
    b = P.pcb
    failed = None
    summary = {}
    for s in plan:
        if s == "cutouts":
            rec, log = P.run(s, [KP, L("stitch.py"), "--board", b, "--cutouts-only"])
        elif s == "fanout":
            rec, log = P.run(s, [KP, L("fanout.py"), "--board", b, "--report", os.path.join(P.logs, "fanout.json")])
        elif s == "testpads":
            rec, log = P.run(s, [KP, L("place_testpads_bottom.py"), "--board", b, "--out", b, "--sidecar", os.path.join(P.logs, "testpads_bottom.json")])
        elif s == "hs":
            rec, log = P.run(s, [KP, L("route_hs_uwb.py"), "all", "--board", b, "--report", os.path.join(P.logs, "hs.json")],
                             env_ok=(0, 2) if a.keep_going else (0,))
            summary["hs"] = P.tail(log, r"lengths|spread|ties|UNROUTED", 8)
        elif s == "power":
            rec, log = P.run(s, [KP, L("route_power.py"), "--board", b, "--report", os.path.join(P.logs, "power.json")])
        elif s == "hs_finish":
            rec, log = P.run(s, [KP, L("hs_finish.py"), "--board", b])
        elif s == "manhattan":
            rec, log = P.run(s, [KP, L("route_manhattan.py"), "--board", b, "--jobs", str(a.jobs), "--seconds", str(a.seconds),
                                 "--report", os.path.join(P.logs, "manhattan.json")])
            summary["manhattan"] = P.tail(log, r"complet|unrouted|connections", 4)
        elif s == "stitch":
            rec, log = P.run(s, [KP, L("stitch.py"), "--board", b, "--zones", "--rescue", "auto",
                                 "--workdir", os.path.join(P.work, "stitch_probe"), "--report", os.path.join(P.logs, "stitch.json")])
            summary["stitch"] = P.tail(log, r"placed|after:", 3)
        elif s == "fill":
            d = os.path.join(P.work, "filled")
            if os.path.isdir(d):
                shutil.rmtree(d)
            shutil.copytree(P.bdir, d)
            fb = os.path.join(d, os.path.basename(b))
            rec, log = P.run(s, [KCLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json", "--units", "mm",
                                 "-o", os.path.join(d, "fill_drc.json"), fb])
            P.filled = fb
        elif s == "drc":
            fb = getattr(P, "filled", None)
            if not fb:                      # fill stage not selected: DRC with its own refill
                d = os.path.join(P.work, "filled")
                shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(P.bdir, d)
                fb = os.path.join(d, os.path.basename(b))
                extra = ["--refill-zones"]
            else:
                extra = []
            out = os.path.join(P.work, "drc.json")
            rec, log = P.run(s, [KCLI, "pcb", "drc", "--all-track-errors", "--severity-all", "--format", "json", "--units", "mm"] + extra +
                             ["-o", out, fb])
            if os.path.exists(out):
                d = json.load(open(out))
                cnt = {}
                for v in d.get("violations", []):
                    cnt[v["type"]] = cnt.get(v["type"], 0) + 1
                gnd = sum(1 for x in d.get("unconnected_items", []) if any("[GND]" in i["description"] for i in x["items"]))
                summary["drc"] = dict(violations=cnt, unconnected=len(d.get("unconnected_items", [])), unconnected_gnd=gnd)
                print("           DRC", json.dumps(cnt, sort_keys=True), "| unconnected %d (GND %d)" % (len(d.get("unconnected_items", [])), gnd))
        elif s == "gates":
            gj = os.path.join(P.work, "gates.json")
            rec, log = P.run(s, [KP, L("check_gates.py"), "--board", b, "--json", gj, "--workdir", os.path.join(P.work, "gates_work")],
                             env_ok=(0, 1))
            if os.path.exists(gj):
                g = json.load(open(gj))
                hard = [x for x in g if x["kind"] == "HARD" and not x["ok"]]
                warn = [x for x in g if x["kind"] == "WARN" and not x["ok"]]
                summary["gates"] = dict(hard_failed=[x["name"] for x in hard], warnings=[x["name"] for x in warn])
                print("           gates: %d hard failed %s | %d warnings" % (len(hard), [x["name"][:50] for x in hard], len(warn)))
            rec["ok"] = rec["rc"] == 0
            if not rec["ok"]:
                failed = failed or s          # reported at the end; later stages still run
                continue
        elif s == "silk":
            rec, log = P.run(s, [KP, L("silkscreen.py"), b])
        if not rec["ok"]:
            print("STOP: stage %s failed (rc=%d). Last lines of %s:" % (s, rec["rc"], log))
            for l in P.tail(log, None, 12):
                print("   |", l)
            failed = s
            if not a.keep_going:
                break
    out = dict(board=P.src, workdir=P.work, final=b, stages=P.res, summary=summary, failed=failed, skipped_absent=missing)
    with open(os.path.join(P.work, "pipeline.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\nfinal board:", b, "(md5 %s)" % md5(b))
    print("summary:", json.dumps(summary, default=str)[:1500])
    if a.in_place and not failed:
        shutil.copy(b, P.src)
        print("copied over", P.src)
    elif a.in_place:
        print("--in-place NOT done: stage %s failed" % failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
