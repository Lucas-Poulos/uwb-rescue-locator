#!/usr/bin/env python3
"""Draw a placement + ratsnest PNG from the JSON written by place_bay_station.py --dump.

    python3 scripts/layout/render_layout.py layout.json out.png [--scale 10] [--crop x0 y0 x1 y1] [--nets uwb|all]

Needs PIL (system python3).  Courtyards are grey boxes, pads are dots, ratsnest is the
minimum spanning tree of every net except GND, coloured by function.
"""
import argparse
import json
import math

from PIL import Image, ImageDraw, ImageFont


def rot_pt(x, y, rot):
    r = rot % 360
    if r == 0:
        return x, y
    if r == 90:
        return y, -x
    if r == 180:
        return -x, -y
    if r == 270:
        return -y, x
    a = math.radians(r)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def mst(pts):
    n = len(pts)
    if n < 2:
        return []
    inT = [False] * n
    d = [1e18] * n
    par = [-1] * n
    d[0] = 0
    edges = []
    for _ in range(n):
        u = min((i for i in range(n) if not inT[i]), key=lambda i: d[i])
        inT[u] = True
        if par[u] >= 0:
            edges.append((par[u], u))
        for v in range(n):
            if not inT[v]:
                dd = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if dd < d[v]:
                    d[v] = dd
                    par[v] = u
    return edges


def color_for(net):
    n = net.split("/")[-1]
    if n.startswith(("UWB_CLK", "CLK_", "TCXO_OUT", "TCXO_RF")):
        return (220, 0, 0)
    if "RF1" in n or n.startswith("Net-(J2") or n.startswith("Net-(C20") or "_XTO" in n or n.startswith("LTE") or n.startswith("GNSS"):
        return (200, 0, 200)
    if n.startswith(("UWB_", "A0_", "A1_", "A2_", "A3_")):
        return (0, 90, 220)
    if n.startswith(("+", "VBATT", "BATT", "NRF_VDD", "SW_", "L1_", "L2_")):
        return (240, 140, 0)
    return (0, 150, 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("png")
    ap.add_argument("--scale", type=float, default=10.0)
    ap.add_argument("--crop", type=float, nargs=4)
    ap.add_argument("--nets", default="all")
    ap.add_argument("--labels", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.json))
    W, H = d["W"], d["H"]
    x0, y0, x1, y1 = a.crop if a.crop else (-3, -12, W + 3, H + 12)
    S = a.scale
    img = Image.new("RGB", (int((x1 - x0) * S), int((y1 - y0) * S)), (250, 250, 245))
    dr = ImageDraw.Draw(img, "RGBA")

    def P(x, y):
        return ((x - x0) * S, (y - y0) * S)

    dr.rounded_rectangle([P(0, 0), P(W, H)], radius=3 * S, outline=(0, 0, 0), width=2, fill=(235, 240, 235))
    try:
        font = ImageFont.load_default(size=max(8, int(S * 0.8)))
    except Exception:
        font = ImageFont.load_default()
    nets = {}
    for ref, p in d["parts"].items():
        cx0, cy0, cx1, cy1 = p["cy"]
        pts = [rot_pt(u, v, p["rot"]) for u, v in ((cx0, cy0), (cx1, cy0), (cx0, cy1), (cx1, cy1))]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        r = (p["x"] + min(xs), p["y"] + min(ys), p["x"] + max(xs), p["y"] + max(ys))
        big = ref[0] in "UJBHS" and ref[:2] != "TP"
        col = (120, 120, 160, 70) if big else ((90, 90, 90, 60))
        if ref.startswith("TP"):
            col = (200, 160, 0, 120)
        dr.rectangle([P(r[0], r[1]), P(r[2], r[3])], outline=(60, 60, 60), fill=col)
        if a.labels or big:
            dr.text(P((r[0] + r[2]) / 2 - 1, (r[1] + r[3]) / 2 - 0.6), ref, fill=(0, 0, 0), font=font)
        for num, x, y, net in p["pads"]:
            dr.ellipse([P(x - 0.25, y - 0.25), P(x + 0.25, y + 0.25)], fill=(30, 100, 30))
            if net and not net.startswith("unconnected-"):
                nets.setdefault(net, []).append((x, y))
    for net, pts in nets.items():
        if net == "GND":
            continue
        c = color_for(net)
        if a.nets == "uwb" and c not in ((220, 0, 0), (200, 0, 200), (0, 90, 220)):
            continue
        for i, j in mst(pts):
            dr.line([P(*pts[i]), P(*pts[j])], fill=c + (200,), width=1)
    img.save(a.png)


if __name__ == "__main__":
    main()
