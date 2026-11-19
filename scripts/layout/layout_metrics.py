#!/usr/bin/env python3
"""Placement metrics from the JSON written by place_bay_station.py --dump (plain python3, no pcbnew).

    python3 scripts/layout/layout_metrics.py layout.json [--worst 30]

Reports total HPWL / MST (excluding GND), ratsnest crossings and MST length for the groups the
placement is judged on (whole board, shared UWB bus, clock tree, RF1 -> SMA chains), the four
buffer -> XTI estimated clock path lengths, the RF chain lengths, the magnetometer distances, the
test-pad statistics and the footprints with the largest distance to their nets.
"""
import argparse
import json
import math
import re


def mst_edges(pts):
    n = len(pts)
    if n < 2:
        return []
    inT = [False] * n
    d = [1e18] * n
    par = [-1] * n
    d[0] = 0
    out = []
    for _ in range(n):
        u = min((i for i in range(n) if not inT[i]), key=lambda i: d[i])
        inT[u] = True
        if par[u] >= 0:
            out.append((par[u], u))
        for v in range(n):
            if not inT[v]:
                dd = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if dd < d[v]:
                    d[v], par[v] = dd, u
    return out


def hpwl(pts):
    if len(pts) < 2:
        return 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(xs) - min(xs) + max(ys) - min(ys)


def seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if a == c or a == d or b == c or b == d:
        return False
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


INCLUDE_TP = False     # test pads are parked off-board (or bottom-side) in the top placement: not part of the metrics


def net_pts(d):
    nets = {}
    for ref, p in d["parts"].items():
        if p.get("parked") or (ref.startswith("TP") and not INCLUDE_TP):
            continue
        for num, x, y, net in p["pads"]:
            if net and not net.startswith("unconnected-"):
                nets.setdefault(net, []).append((x, y, ref, num))
    return nets


BUS_RE = re.compile(r"UWB_(WAKEUP|SCK|MOSI|MISO|SYNC|RST_N|IRQ\d|CS\d_N)$|NRF_UWB_|A\d_(IRQ|CSN|RSTN|SYNC)$")
SHARED_RE = re.compile(r"UWB_(WAKEUP|SCK|MOSI|MISO|SYNC|RST_N)$")
CLK_RE = re.compile(r"UWB_CLK|CLK_[YT]\d|TCXO_OUT|TCXO_RF")
RF_RE = re.compile(r"A\d_RF1$|Net-\(C20\d-Pad1\)|Net-\(J2\d-In\)")


def group_stats(nets, rx):
    sel = {k: v for k, v in nets.items() if rx.search(k)}
    edges = []
    tot = 0.0
    for k, v in sel.items():
        pts = [(a, b) for a, b, _, _ in v]
        for i, j in mst_edges(pts):
            edges.append((k, pts[i], pts[j]))
            tot += math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
    cr = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i][0] != edges[j][0] and seg_cross(edges[i][1], edges[i][2], edges[j][1], edges[j][2]):
                cr += 1
    return len(sel), cr, tot


def whole(nets):
    edges = []
    tot_m = tot_h = 0.0
    for k, v in nets.items():
        if k == "GND":
            continue
        pts = [(a, b) for a, b, _, _ in v]
        tot_h += hpwl(pts)
        for i, j in mst_edges(pts):
            edges.append((k, pts[i], pts[j]))
            tot_m += math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
    cr = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i][0] != edges[j][0] and seg_cross(edges[i][1], edges[i][2], edges[j][1], edges[j][2]):
                cr += 1
    return tot_h, tot_m, cr


def pad(d, ref, num, net=None):
    for n, x, y, nt in d["parts"][ref]["pads"]:
        if n == num and (net is None or nt == net):
            return (x, y)
    raise KeyError((ref, num))


def other_pad(d, ref, net, first):
    """the pad of a 2-pad part that is not on net `net`"""
    for n, x, y, nt in d["parts"][ref]["pads"]:
        if nt != net:
            return (x, y)
    return first


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def clock_paths(d):
    """buffer pin -> R231.. -> C24.. -> XTI estimated length (pad centres), per anchor"""
    res = []
    P = d["parts"]
    for n in range(4):
        r, c, u = "R%d" % (231 + n), "C%d" % (24 + n), "U%d" % (4 + n)
        ypin = None
        for num, x, y, net in P["U31"]["pads"]:
            if net.endswith("CLK_Y%d" % n):
                ypin = (x, y)
        rp = {num: (x, y, net) for num, x, y, net in P[r]["pads"]}
        cp = {num: (x, y, net) for num, x, y, net in P[c]["pads"]}
        L = dist(ypin, rp["1"][:2]) + dist(rp["1"][:2], rp["2"][:2]) + dist(rp["2"][:2], cp["1"][:2]) \
            + dist(cp["1"][:2], cp["2"][:2]) + dist(cp["2"][:2], pad(d, u, "21"))
        res.append(L)
    return res


def rf_chains(d):
    P = d["parts"]
    res = []
    for n in range(4):
        u, c, r, j = "U%d" % (4 + n), "C%d" % (47 + 8 * n), "R%d" % (220 + n), "J%d" % (20 + n)
        cp = {num: (x, y) for num, x, y, _ in P[c]["pads"]}
        rp = {num: (x, y) for num, x, y, _ in P[r]["pads"]}
        L = dist(pad(d, u, "18"), cp["1"]) + dist(cp["1"], cp["2"]) + dist(cp["2"], rp["1"]) + \
            dist(rp["1"], rp["2"]) + dist(rp["2"], pad(d, j, "1"))
        res.append(L)
    return res


def part_dist(d):
    """per footprint: mean over its non-GND pads of the distance to the nearest other pad of that net, and
    distance to the centroid of the pads of small (<= 6 pin) nets it sits on"""
    nets = net_pts(d)
    out = []
    for ref, p in d["parts"].items():
        if ref.startswith(("H", "FID")) and not ref.startswith(("HS",)):
            continue
        ds = []
        cs = []
        for num, x, y, net in p["pads"]:
            if not net or net == "GND" or net.startswith("unconnected-"):
                continue
            others = [(a, b) for a, b, r2, n2 in nets[net] if r2 != ref]
            if not others:
                continue
            ds.append(min(dist((x, y), o) for o in others))
            if len(nets[net]) <= 6:
                cs += others
        if not ds:
            continue
        cen = None
        if cs:
            cen = dist((p["x"], p["y"]), (sum(a for a, b in cs) / len(cs), sum(b for a, b in cs) / len(cs)))
        out.append((max(ds), sum(ds) / len(ds), cen, ref))
    return out


def rect_of(p):
    x0, y0, x1, y1 = p["cy"]
    r = p["rot"] % 360
    pts = []
    for a, b in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        pts.append({0: (a, b), 90: (b, -a), 180: (-a, -b), 270: (-b, a)}[r] if r in (0, 90, 180, 270) else (a, b))
    return (p["x"] + min(q[0] for q in pts), p["y"] + min(q[1] for q in pts),
            p["x"] + max(q[0] for q in pts), p["y"] + max(q[1] for q in pts))


def courtyard_gaps(d):
    """minimum / count below 0.6 and 0.5 mm of the courtyard-to-courtyard distance (bounding boxes, parts not
    parked).  Overlaps are counted as negative gaps."""
    items = [(ref, rect_of(p)) for ref, p in d["parts"].items() if not p.get("parked")]
    gaps = []
    for i in range(len(items)):
        ra = items[i][1]
        for j in range(i + 1, len(items)):
            rb = items[j][1]
            dx = max(rb[0] - ra[2], ra[0] - rb[2])
            dy = max(rb[1] - ra[3], ra[1] - rb[3])
            g = max(dx, dy) if (dx < 0 and dy < 0) else math.hypot(max(dx, 0), max(dy, 0))
            if g < 0.6:
                gaps.append((round(g, 2), items[i][0], items[j][0]))
    gaps.sort()
    return "min %s, %d pairs < 0.6, %d < 0.5, %d overlapping; worst %s" % (
        gaps[0][0] if gaps else ">=0.6", len(gaps), sum(1 for g in gaps if g[0] < 0.5), sum(1 for g in gaps if g[0] < 0),
        gaps[:6])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--worst", type=int, default=30)
    ap.add_argument("--with-tp", action="store_true", help="include test pads in the nets (old 128 x 68 numbers)")
    a = ap.parse_args()
    global INCLUDE_TP
    INCLUDE_TP = a.with_tp
    d = json.load(open(a.json))
    nets = net_pts(d)
    h, m, cr = whole(nets)
    print("whole board: HPWL %.1f  MST %.1f  crossings %d" % (h, m, cr))
    for name, rx in (("UWB bus (all)", BUS_RE), ("UWB bus (6 shared nets)", SHARED_RE), ("clock tree", CLK_RE),
                     ("RF1->SMA chains", RF_RE)):
        n, c, t = group_stats(nets, rx)
        print("%-24s nets %2d  crossings %3d  MST %.1f mm" % (name, n, c, t))
    for k, v in sorted(nets.items()):
        if SHARED_RE.search(k):
            pts = [(x, y) for x, y, _, _ in v]
            print("   %-12s HPWL %.1f MST %.1f" % (k, hpwl(pts), sum(dist(pts[i], pts[j]) for i, j in mst_edges(pts))))
    print("clock buffer->XTI (A0..A3):", ["%.1f" % x for x in clock_paths(d)])
    print("RF chains (A0..A3):", ["%.2f" % x for x in rf_chains(d)])
    P = d["parts"]
    print("test pads: %d parked off-board / bottom side, excluded from every figure above" %
          sum(1 for r in P if r.startswith("TP")))
    print("courtyard gaps (top parts, edge-to-edge, mm):", courtyard_gaps(d))
    print("U10 distances: L1 %.1f, L300 %.1f, U40 %.1f" % (
        dist((P["U10"]["x"], P["U10"]["y"]), (P["L1"]["x"], P["L1"]["y"])),
        dist((P["U10"]["x"], P["U10"]["y"]), (P["L300"]["x"], P["L300"]["y"])),
        dist((P["U10"]["x"], P["U10"]["y"]), (P["U40"]["x"], P["U40"]["y"]))))
    pd = [t for t in part_dist(d) if not t[3].startswith("TP")]
    pd.sort(key=lambda t: -t[0])
    print("worst %d non-TP footprints by farthest-pad-to-nearest-connection (max / mean / centroid):" % a.worst)
    for mx, mean, cen, ref in pd[:a.worst]:
        print("  %-6s %5.1f %5.1f %s  %s" % (ref, mx, mean, "%5.1f" % cen if cen is not None else "  -  ",
                                              P[ref]["value"][:24]))


if __name__ == "__main__":
    main()
