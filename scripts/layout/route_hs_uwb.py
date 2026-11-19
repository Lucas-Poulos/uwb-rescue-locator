#!/usr/bin/env python3
"""Bay-station specifics on top of route_hs: the hand-first high-speed stage.  Everything is
found from the netlist and the footprint geometry (no coordinates, no fixed board size): the
four DW3210 RF chains, the DW3210 GND ties, the LTE / GNSS RF50 nets, the TCXO clock hops and
the four-way UWB_CLK group.

    kicad-python route_hs_uwb.py {rf|ties|host|clocks|all} --board SCRATCH.kicad_pcb [--out X]
                                 [--tented] [--via-in-pad] [--report r.json]

`all` runs, in this order (each step sees the copper of the one before as an obstacle):
  1. rf      RF1 -> C -> R -> SMA chains x4 (identical geometry, no vias) + RF2 stub, then every
             DNP pad that hangs on those nets (pi-network shunts) as a short spur, then the fence;
  2. ties    GND pads of every chip that carries an RF50/CLK pin (all DW3210 pads, the LNA, ...):
             0.2 mm stub + via outside the DW3210 cut-out, BEFORE the clock and host RF so those
             route around the ties.  GND stubs may sit 0.15 mm from an RF neck inside DW3210_TIE_n
             (.kicad_dru exception).  See stitch.py;
  3. host    every other RF50 / CLK net (LTE, GNSS, TCXO): a minimum spanning tree over the net's
             F.Cu pads, shortest edge first, width ladder when a 0.4 mm pitch pad forces it, fence on
             RF50;
  4. clocks  UWB_CLK0-3 buffer -> XTI, length-matched with match_group.  Every other pad on a
             UWB_CLKn net (the DNP R403 link pad, the DNP Y1 / C209 crystal option on A0) is a
             SPUR routed to the chain and its copper is COUNTED in that anchor's length.

Length counting rule (also what check_gates.py measures): the length of anchor n is the sum of
the track lengths of its three chain nets, measured pad centre to pad centre; series R and C pads
count as zero; dead-end spur copper counts 1:1.  A dead-end stub is not a delay in the through
path (it is a lumped capacitance, 0.123 pF/mm at 50 ohm, i.e. R*C = 72 ohm x 0.123 pF = 8.9 ps/mm
of stub seen by a 50 + 22 ohm source), so 1:1 (6.15 ps/mm) is the same order as the physical term
(within 1.5x) and is conservative on the side of a longer A0 path.

Always point --board at a scratch copy of the placed board, never the file under version control.
"""
import argparse
import fnmatch
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U
import route_hs as R

FAILED = []          # (net, what, error) of every hop that could not be routed (reported, not fatal)


def pads_on(board, netname, front_only=False):
    out = []
    for f in board.GetFootprints():
        for p in f.Pads():
            if str(p.GetNetname()) == netname:
                if front_only and not p.IsOnLayer(U.F_CU):
                    continue
                out.append((str(f.GetReference()), str(p.GetNumber()), str(f.GetValue())))
    return out


def centre(board, rp):
    return R.pad_center(R.pad_of(board, *rp)[1])


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


# ------------------------------------------------------------------ spurs
def spur_edges(board, netname, tree, front_only=True):
    """Minimum-spanning growth: [(tree_pad, new_pad)] connecting every F.Cu pad of the net that is not
    in `tree`, shortest edge first.  tree = [(ref, num)] already connected."""
    tree = list(tree)
    todo = [(r, k) for r, k, v in pads_on(board, netname, front_only) if (r, k) not in tree]
    edges = []
    while todo:
        best = min(((math.dist(centre(board, a), centre(board, b)), a, b) for a in tree for b in todo),
                   key=lambda t: t[0])
        edges.append((best[1], best[2]))
        tree.append(best[2])
        todo.remove(best[2])
    return edges


def spur_edges_to(board, tree, targets):
    """MST growth of `targets` onto `tree` (both lists of (ref, num))."""
    tree, todo, edges = list(tree), list(targets), []
    while todo:
        best = min(((math.dist(centre(board, a), centre(board, b)), a, b) for a in tree for b in todo),
                   key=lambda t: t[0])
        edges.append((best[1], best[2]))
        tree.append(best[2])
        todo.remove(best[2])
    return edges


def spur_edges_among(board, tree, pads):
    return spur_edges_to(board, tree, [p for p in pads if p not in tree])


def route_edge(board, netname, a, b, ladder=((R.RF_W, 0.5),), fail_to=None):
    """route_pads over a (width, keep-off) ladder.  Returns (items, length) or (None, 0)."""
    net = U.get_net(board, netname)
    err = None
    for w, tc in ladder:
        try:
            its, ln = R.route_pads(board, net, a, b, neck_pads={a, b}, width=w, trk_clearance=tc)
            if (w, tc) != ladder[0]:
                print("note: %s %s-%s routed at %.2f mm width, %.2f keep-off (%.2f / %.2f did not fit)"
                      % (netname, a, b, w, tc, ladder[0][0], ladder[0][1]))
            return its, ln
        except RuntimeError as e:
            err = e
    FAILED.append((netname, "%s-%s" % (a, b), str(err)))
    print("UNROUTED HS hop", netname, a, b, err)
    return None, 0.0


# ------------------------------------------------------------------ 1. UWB RF
def route_uwb_rf(board, fence=True, lock_items=True):
    """Four identical RF chains on F.Cu, no vias, DNP shunt pads as spurs, then the GND fence.
    Returns {n: RF1 -> SMA centre-line length}."""
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
        spur_items = []
        for (netname, pa, pb, kw) in ch["hops"] + [ch["rf2"]]:
            for (ta, nb) in spur_edges(board, netname, [pa, pb]):
                its, ln = route_edge(board, netname, ta, nb)
                spur_items += its or []
        out[n] = tot
        locked += items + spur_items
        if fence:
            locked += R.via_fence(board, items)
    if lock_items:
        R.lock(locked)
    return out


# ------------------------------------------------------------------ 2. GND ties
def hs_chip_gnd_pads(board, near=3.0):
    """GND pads that belong in the ties-first step: every GND pad of a DW3210, and every GND pad
    within `near` mm of an RF50 / CLK pin of the same footprint (LNA, nRF9151 RF pins, TCXO...).
    Pads that already touch GND copper (a fan-out stub or via) are skipped."""
    gnd = U.get_net(board, "GND").GetNetCode()
    touch = []
    for t in board.GetTracks():
        if t.GetNetCode() != gnd:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition(); touch.append((U.mm(q.x), U.mm(q.y)))
        else:
            for q in (t.GetStart(), t.GetEnd()):
                touch.append((U.mm(q.x), U.mm(q.y)))
    out = []
    for f in board.GetFootprints():
        ref = str(f.GetReference())
        hs = [p for p in f.Pads() if str(p.GetNetClassName()) in ("RF50", "CLK") and p.IsOnLayer(U.F_CU)]
        is_dw = "DW3210" in str(f.GetFPIDAsString())
        if not hs and not is_dw:
            continue
        hs_c = [R.pad_center(p) for p in hs]
        for p in f.Pads():
            if p.GetNetCode() != gnd or not p.IsOnLayer(U.F_CU) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            c = R.pad_center(p)
            if not is_dw and not any(math.dist(c, h) <= near for h in hs_c):
                continue
            bb = p.GetBoundingBox()
            x0, y0, x1, y1 = U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom())
            if any(x0 - 0.01 <= tx <= x1 + 0.01 and y0 - 0.01 <= ty <= y1 + 0.01 for tx, ty in touch):
                continue
            out.append((ref, str(p.GetNumber()), is_dw))
    return out


def route_gnd_ties(board, tented=False, via_in_pad=False, lock_items=True, reach=2.0, which="all"):
    """Ties-first: stub + via for the GND pads of HS chips (see hs_chip_gnd_pads).  DW3210 pads first.
    Returns (tied {pad: info}, failed {pad: reason})."""
    import stitch as S
    S.add_tie_areas(board)
    st = S.Stitcher(board)
    st.tie = S.tie_areas(board)
    pads = [p for p in hs_chip_gnd_pads(board) if which == "all" or (p[2] == (which == "dw"))]
    pads.sort(key=lambda t: (not t[2], t[0], int(t[1]) if t[1].isdigit() else 0))
    tied, failed = {}, {}
    for ref, num, _dw in pads:
        res, info = st.tie_pad(ref, num, reach, S.RELAX_PAD if tented else None, via_in_pad)
        (tied if res == "tied" else failed)["%s.%s" % (ref, num)] = info
    if lock_items:
        R.lock(st.added)
    R._PAD_CACHE.clear()
    return tied, failed


# ------------------------------------------------------------------ 3. host RF / TCXO
def group_nets(spec, gid):
    pats = []
    for g in spec["groups"]:
        if g["id"] == gid:
            pats += g.get("patterns", [])
    return pats


def host_nets(board, spec):
    """RF50 / CLK nets that are not part of the UWB chains, noise-critical GNSS input nets first."""
    uwb = group_nets(spec, "RF_UWB") + group_nets(spec, "CLK_UWB")
    names = []
    for name, net in board.GetNetsByName().items():
        nm = str(name)
        if str(net.GetNetClassName()) not in ("RF50", "CLK") or any(fnmatch.fnmatchcase(nm, p) for p in uwb):
            continue
        if len(pads_on(board, nm, True)) >= 2:
            names.append(nm)

    def key(nm):
        crit = 0 if ("LNA_AI" in nm or "LNA_IN" in nm) else 1
        return (str(board.FindNet(nm).GetNetClassName()) != "RF50", crit, nm)
    return sorted(names, key=key)


HOST_LADDER = ((R.RF_W, 0.5), (0.35, 0.5), (0.30, 0.5), (0.24, 0.5), (0.24, 0.3), (0.24, 0.15))


def is_dnp(board, rp):
    return str(R.pad_of(board, *rp)[0].GetValue()).strip().upper() == "DNP"


def route_host_rf(board, spec=None, lock_items=True):
    """Every non-UWB RF50 / CLK net.  Phase 1: MST over the POPULATED F.Cu pads of every net (shortest
    edge first, noise-critical GNSS input nets first), so the through paths get the clean lanes.
    Phase 2: every DNP pad (pi-network shunts, test links) as a spur of its net, so an unfitted part
    never walls in a populated path.  RF50 nets get a GND fence, the TCXO clock does not.  The relaxed
    rows of the width ladder break the .kicad_dru 0.5 mm keep-off on purpose (BGA524N6 0.4 mm pitch)
    and are reported.  Returns {net: length or None} (spur copper included)."""
    spec = spec or U.load_spec()
    names = host_nets(board, spec)
    out = {nm: 0.0 for nm in names}
    items = {nm: [] for nm in names}
    todo2 = []
    for nm in names:
        pads = [(r, k) for r, k, v in pads_on(board, nm, True)]
        live = [p for p in pads if not is_dnp(board, p)] or pads
        dnp = [p for p in pads if p not in live]
        if len(live) >= 2:
            pairs = sorted(((math.dist(centre(board, a), centre(board, b)), a, b)
                            for i, a in enumerate(live) for b in live[i + 1:]), key=lambda t: t[0])
            first = pairs[0]
            tree = [first[1], first[2]]
            edges = [(first[1], first[2])]
            for (ta, nb) in spur_edges_among(board, tree, live):
                edges.append((ta, nb))
        else:
            tree, edges = list(live), []
        for a, b in edges:
            its, ln = route_edge(board, nm, a, b, HOST_LADDER)
            if its is None:
                out[nm] = None
            else:
                items[nm] += its
                out[nm] = None if out[nm] is None else out[nm] + ln
        todo2.append((nm, set(tree) | set(live), dnp))
    for nm, have, dnp in todo2:
        tree = sorted(have)
        for (ta, nb) in spur_edges_to(board, tree, dnp):
            its, ln = route_edge(board, nm, ta, nb, HOST_LADDER)
            if its is None:
                out[nm] = None
            else:
                items[nm] += its
                out[nm] = None if out[nm] is None else out[nm] + ln
    locked = []
    for nm in names:
        locked += items[nm]
        if str(board.FindNet(nm).GetNetClassName()) == "RF50":
            locked += R.via_fence(board, items[nm])
    if lock_items:
        R.lock(locked)
    return out


# ------------------------------------------------------------------ 4. UWB clocks
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
        xti = (chip_of(board, n), "21")
        hops = [("/Clock Distribution/CLK_Y%d" % n, buf, rs, {}),
                ("/Clock Distribution/CLK_T%d" % n, rs2, cc, {}),
                ("UWB_CLK%d" % n, cc2, xti, {})]
        # dead-end spurs (DNP link pad, crystal option): counted in this anchor's length
        for (ta, nb) in spur_edges(board, "UWB_CLK%d" % n, [cc2, xti]):
            hops.append(("UWB_CLK%d" % n, ta, nb, {}))
        g["A%d" % n] = {"hops": hops, "tune_hop": 1, "spurs": len(hops) - 3}
    return g


def route_uwb_clocks(board, tol_mm=0.5, lock_items=True):
    spec = clock_group_spec(board)
    res = R.match_group(board, spec, tol_mm=tol_mm)
    if lock_items:
        for k, v in res.items():
            if k != "_spread_mm":
                R.lock(v["items"])
    return {k: v["length"] for k, v in res.items() if k != "_spread_mm"}, res["_spread_mm"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["rf", "ties", "ties2", "host", "clocks", "all"])
    ap.add_argument("--board", required=True, help="PLACED board (a scratch copy!)")
    ap.add_argument("--out", help="save here (default: overwrite --board)")
    ap.add_argument("--tented", action="store_true", help="ties: via may be 0.15 mm from a foreign pad (tented vias)")
    ap.add_argument("--via-in-pad", action="store_true", help="ties: via ON a big pad as last tier (filled/capped vias)")
    ap.add_argument("--report")
    a = ap.parse_args()
    pcbnew.KIID.SeedGenerator(0x57175)
    b = U.load_board(a.board)
    rep = {}
    if a.step in ("rf", "all"):
        rep["rf"] = R_ = route_uwb_rf(b)
        print("RF lengths (mm):", {k: round(v, 3) for k, v in R_.items()})
    if a.step in ("ties", "all"):        # DW3210 pads: before the clocks and host RF, which then route around them
        tied, failed = route_gnd_ties(b, a.tented, a.via_in_pad, which="dw")
        rep["ties"] = dict(tied=tied, failed=failed)
        print("DW3210 GND ties: %d tied, %d without a site %s" % (len(tied), len(failed), sorted(failed)))
    if a.step in ("host", "all"):
        h = route_host_rf(b)
        rep["host"] = h
        print("host RF/TCXO lengths (mm):", {k: (None if v is None else round(v, 3)) for k, v in h.items()})
    if a.step in ("clocks", "all"):
        L, sp = route_uwb_clocks(b)
        rep["clocks"] = dict(lengths=L, spread=sp)
        print("clock path lengths (mm):", {k: round(v, 3) for k, v in L.items()}, "spread %.3f" % sp)
    if a.step in ("ties2", "all"):       # other HS chips (LNA, nRF9151 RF pins, TCXO): after their RF lanes exist
        tied, failed = route_gnd_ties(b, a.tented, a.via_in_pad, which="other")
        rep["ties2"] = dict(tied=tied, failed=failed)
        print("other HS-chip GND ties: %d tied, %d without a site %s" % (len(tied), len(failed), sorted(failed)))
    rep["failed"] = FAILED
    U.save_board(b, a.out or a.board)
    if a.report:
        json.dump(rep, open(a.report, "w"), indent=1, default=str)
    if FAILED:
        print("%d HS hop(s) UNROUTED: %s" % (len(FAILED), FAILED))
        sys.exit(2)
