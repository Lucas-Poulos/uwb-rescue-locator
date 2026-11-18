#!/usr/bin/env python3
"""Bay-station specifics on top of route_hs: the four DW3210 RF chains and the
four-way UWB_CLK group, found from the netlist (no hard-coded refs).

    kicad-python route_hs_uwb.py {rf|clocks|all} --board SCRATCH.kicad_pcb [--out X]

Always point --board at a scratch copy of the placed board, never the file
under version control.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbutil as U
import route_hs as R


def pads_on(board, netname):
    out = []
    for f in board.GetFootprints():
        for p in f.Pads():
            if str(p.GetNetname()) == netname:
                out.append((str(f.GetReference()), str(p.GetNumber()), str(f.GetValue())))
    return out


def chip_of(board, n):
    return [r for r in sorted({p[0] for p in pads_on(board, "/UWB Array/A%d_CSN" % n)})
            if r.startswith("U")][0]


def find_uwb_chain(board, n):
    chip = chip_of(board, n)
    cap = [(r, k) for r, k, v in pads_on(board, "/UWB Array/A%d_RF1" % n) if r != chip][0]
    node = "Net-(C%d-Pad1)" % (200 + 2 * n)
    cap_out = [(r, k) for r, k, v in pads_on(board, node) if r == cap[0]][0]
    rpi = [(r, k) for r, k, v in pads_on(board, node) if v == "0R"][0]
    sma_net = "Net-(J%d-In)" % (20 + n)
    rpi_out = [(r, k) for r, k, v in pads_on(board, sma_net) if r == rpi[0]][0]
    sma = [(r, k) for r, k, v in pads_on(board, sma_net) if r.startswith("J")][0]
    rf2 = [(r, k) for r, k, v in pads_on(board, "/UWB Array/A%d_RF2" % n) if r != chip][0]
    p18, p13 = (chip, "18"), (chip, "13")
    return dict(
        hops=[("/UWB Array/A%d_RF1" % n, p18, cap, {"neck_pads": {p18}}),
              (node, cap_out, rpi, {}),
              (sma_net, rpi_out, sma, {})],
        rf2=("/UWB Array/A%d_RF2" % n, p13, rf2, {"neck_pads": {p13}}))


def route_uwb_rf(board, fence=True, lock_items=True):
    """Step 1 of the hand-first order: four identical RF chains on F.Cu, no vias,
    then the GND fence.  Returns {n: pad-centre-to-pad-centre length of RF1->SMA}."""
    out, locked = {}, []
    for n in range(4):
        ch = find_uwb_chain(board, n)
        tot, items = 0.0, []
        for hop in ch["hops"]:
            netname, pa, pb, kw = hop
            its, ln = R.route_pads(board, U.get_net(board, netname), pa, pb, **kw)
            items += its
            tot += ln
        netname, pa, pb, kw = ch["rf2"]
        its, _ = R.route_pads(board, U.get_net(board, netname), pa, pb, **kw)
        items += its
        out[n] = tot
        locked += items
        if fence:
            locked += R.via_fence(board, items)
    if lock_items:
        R.lock(locked)
    return out


def clock_group_spec(board):
    g = {}
    for n in range(4):
        y = pads_on(board, "/Clock Distribution/CLK_Y%d" % n)
        t = pads_on(board, "/Clock Distribution/CLK_T%d" % n)
        c = pads_on(board, "UWB_CLK%d" % n)
        buf = [(r, k) for r, k, v in y if r.startswith("U")][0]
        rs = [(r, k) for r, k, v in y if r.startswith("R") and v == "22R"][0]
        rs2 = [(r, k) for r, k, v in t if r == rs[0]][0]
        cc = [(r, k) for r, k, v in t if r.startswith("C") and v.startswith("2200")][0]
        cc2 = [(r, k) for r, k, v in c if r == cc[0]][0]
        g["A%d" % n] = {"hops": [
            ("/Clock Distribution/CLK_Y%d" % n, buf, rs, {}),
            ("/Clock Distribution/CLK_T%d" % n, rs2, cc, {}),
            ("UWB_CLK%d" % n, cc2, (chip_of(board, n), "21"), {}),
        ], "tune_hop": 1}
    return g


def route_uwb_clocks(board, tol_mm=0.5, lock_items=True):
    res = R.match_group(board, clock_group_spec(board), tol_mm=tol_mm)
    if lock_items:
        for k, v in res.items():
            if k != "_spread_mm":
                R.lock(v["items"])
    return {k: v["length"] for k, v in res.items() if k != "_spread_mm"}, res["_spread_mm"]


# (net, ref_a, pin_a, ref_b, pin_b, fence): host-side RF50 / clock hops, in signal order.
# Pins come from the netlist of the placed board (checked at run time against the net).
HOST_HOPS = [   # GNSS is routed antenna -> modem: the LNA input (noise critical) gets the shortest lane
    ("/Connectivity/LTE_RF_PIN", "U20", "35", "R130", "1", True),
    ("/Connectivity/LTE_ANT", "R130", "2", "J10", "1", True),
    ("/Connectivity/GNSS_ANT", "C123", "1", "J11", "1", True),
    ("/Connectivity/GNSS_LNA_AI", "U24", "5", "L101", "2", True),
    ("/Connectivity/GNSS_LNA_IN_DC", "L101", "1", "C123", "2", True),
    ("/Connectivity/GNSS_LNA_AO", "R123", "1", "U24", "3", True),
    ("/Connectivity/GNSS_RF_A", "R125", "1", "R123", "2", True),
    ("/Connectivity/GNSS_RF_PIN", "U20", "42", "R125", "2", True),
    ("/Clock Distribution/TCXO_RF", "U30", "4", "R230", "1", False),
    ("TCXO_OUT", "R230", "2", "U31", "1", False),
]


def route_host_rf(board, lock_items=True, report=None):
    """LTE / GNSS RF50 chains and the TCXO -> buffer clock hops, each a plain pad-to-pad
    0.45 mm microstrip on F.Cu (A* around obstacles when no orthogonal candidate fits).
    RF hops get a GND fence; the TCXO clock is not fenced (clock, not RF).  Returns {net: length}."""
    out, locked = {}, []
    for netname, ra, pa, rb, pb, fence in HOST_HOPS:
        have = {(r, k) for r, k, v in pads_on(board, netname)}
        assert (ra, pa) in have and (rb, pb) in have, (netname, ra, pa, rb, pb, sorted(have))
        its = None
        # (width, keep-off to foreign copper): narrower / tighter only where the 0.4 mm pitch
        # pads of the BGA524N6 force it; the relaxed rows break the .kicad_dru RF50 0.5 mm rule
        # on purpose and are reported.
        for w, tc in ((R.RF_W, 0.5), (0.35, 0.5), (0.30, 0.5), (0.24, 0.5), (0.24, 0.3), (0.24, 0.15)):
            try:
                its, ln = R.route_pads(board, U.get_net(board, netname), (ra, pa), (rb, pb),
                                       neck_pads={(ra, pa), (rb, pb)}, width=w, trk_clearance=tc)
                if (w, tc) != (R.RF_W, 0.5):
                    print("note: %s routed at %.2f mm width, %.2f keep-off (0.45 / 0.5 did not fit)" % (netname, w, tc))
                break
            except RuntimeError as e:
                err = e
        if its is None:
            print("UNROUTED HS hop", netname, err)
            out[netname] = None
            continue
        out[netname] = ln
        locked += its
        if fence:
            locked += R.via_fence(board, its)
    if lock_items:
        R.lock(locked)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["rf", "clocks", "host", "all"])
    ap.add_argument("--board", required=True, help="PLACED board (a scratch copy!)")
    ap.add_argument("--out", help="save here (default: overwrite --board)")
    a = ap.parse_args()
    b = U.load_board(a.board)
    if a.step in ("rf", "all"):
        print("RF lengths (mm):", {k: round(v, 3) for k, v in route_uwb_rf(b).items()})
    if a.step in ("host", "all"):     # before the clock group: the short TCXO / LTE / GNSS runs take their direct lanes first
        print("host RF/TCXO lengths (mm):", {k: (None if v is None else round(v, 3)) for k, v in route_host_rf(b).items()})
    if a.step in ("clocks", "all"):
        L, sp = route_uwb_clocks(b)
        print("clock path lengths (mm):", {k: round(v, 3) for k, v in L.items()}, "spread %.3f" % sp)
    U.save_board(b, a.out or a.board)
