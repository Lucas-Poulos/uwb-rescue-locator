#!/usr/bin/env python3
"""Benchmark harness for route_manhattan.py.  KiCad's python.  Never touches the source board.

    kicad-python route_bench.py --src PLACED.kicad_pcb --workdir /tmp/bench1 [--strip] [-- router args...]

* copies the board (+ .kicad_pro/.kicad_dru) into --workdir (must be outside the repo),
* --strip removes every UNLOCKED track/via first (locked hand-routed RF/CLK copper and fences stay),
* runs route_manhattan.py on the copy with the router args after `--`,
* runs check_gates.py (DRC --all-track-errors --refill-zones, direction policy) on the result,
* prints one summary block: unrouted before/after, runtime, DRC counts by type, gate lines.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew
import pcbutil as U


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--strip", action="store_true", help="remove unlocked tracks/vias first")
    ap.add_argument("--skip-gates", action="store_true")
    a, rest = ap.parse_known_args()
    rest = [r for r in rest if r != "--"]
    work = os.path.abspath(a.workdir)
    if work.startswith(U.REPO):
        raise SystemExit("workdir must be outside the repo")
    os.makedirs(work, exist_ok=True)
    src = os.path.abspath(a.src)
    sd = os.path.dirname(src)
    base = os.path.splitext(os.path.basename(src))[0]
    for ext in (".kicad_pro", ".kicad_dru"):
        if os.path.exists(os.path.join(sd, base + ext)):
            shutil.copy(os.path.join(sd, base + ext), os.path.join(work, base + ext))
    board_path = os.path.join(work, base + ".kicad_pcb")
    if a.strip:
        b = U.load_board(src)
        n = 0
        for t in list(b.GetTracks()):
            if not t.IsLocked():
                b.Remove(t)
                n += 1
        print("stripped %d unlocked tracks/vias" % n)
        U.save_board(b, board_path)
    else:
        shutil.copy(src, board_path)
    rep = os.path.join(work, "report.json")
    t0 = time.time()
    cmd = [sys.executable, os.path.join(HERE, "route_manhattan.py"), "--board", board_path, "--report", rep] + rest
    with open(os.path.join(work, "route.log"), "w") as lg:
        r = subprocess.run(cmd, stdout=lg, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    print("router exit %d, wall %.0f s" % (r.returncode, dt))
    if os.path.exists(rep):
        d = json.load(open(rep))
        print("connections %d  unrouted %d  completion %.2f%%  tracks %d  vias %d  stub segs %d"
              % (d["connections_total"], d["connections_unrouted"], d["completion_pct"], d["tracks"], d["vias"], d["stub_segments"]))
        print("necked power nets:", d.get("nets_necked_down"))
        print("power nets left unrouted for width floor:", d.get("power_nets_removed_below_width_floor"))
        print("per-net leftovers:", json.dumps(d.get("failed_detail")))
    if not a.skip_gates:
        gw = os.path.join(work, "gates")
        g = subprocess.run([sys.executable, os.path.join(HERE, "check_gates.py"), "--board", board_path, "--workdir", gw],
                           capture_output=True, text=True)
        print(g.stdout[-4000:])


if __name__ == "__main__":
    main()
