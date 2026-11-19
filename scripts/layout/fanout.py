#!/usr/bin/env python3
"""Pad fan-out for the bay station: short locked escape stub + a via beside every signal / GND pad of
every IC with >= 6 pins, so the later routers (route_hs_uwb, route_manhattan, power stage) start from
a via that is already on the net instead of fighting for a path out of a 0.4 mm pad row.

Run with KiCad's python, AFTER place_bay_station.py and BEFORE place_testpads_bottom.py:

    KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KP scripts/layout/fanout.py [--board B.kicad_pcb] [--out OUT.kicad_pcb] [--report r.json] [--dump d.json]
    python3 scripts/layout/fanout.py --render d.json out.png --crop X0 Y0 X1 Y1     # system python, PIL

What it draws (rules, all in docs/fanout-notes.md):
  * stub 0.2 mm wide on the pad layer (F.Cu), starts at the pad centre, runs OUTWARD from the package
    (along the pad's long axis; for square pads along the axis it sits on), orthogonal or orthogonal +
    ONE 45 degree jog, total length <= 2.0 mm, ends in a 0.45/0.20 through via; no via in pad (via
    edge >= 0.10 mm from its own pad, >= 0.20 from every other pad).
  * 0.16 mm copper clearance (0.15 rule + 0.01) to every pad / track / via of another net, via to via
    centre >= 0.61 mm (so hole to hole >= 0.41 > 0.25), 0.51 mm to the board edge, outside the
    DW3210 4 x 4 keep-out and the 5.5 x 5.5 mm no-via cut-out (stitch.py), outside the future RF50/CLK
    hand-route corridors (hs_nets.json classes RF50 + CLK) with the 0.5 mm keep-off of the .kicad_dru.
  * adjacent pads of one net (GND pairs, supply pairs) may share one via (stub to the neighbour's via).
  * everything is locked, on the pad's net.
Skipped, with the reason in the report: no net / unconnected, RF50 + CLK class pads, pads next to such a
pad (the keep-off makes them the stage-4 hand route's business), DW3210 RF-side VSS 12,14-17,19,20, EP /
thermal pads (> 1.0 mm), interior pads that no stub can leave, power-stage pins of U1/U8/U40 (power agent),
TCXO U30 (clock tree), test pads, connectors other than the SIM socket.

Idempotent: the items made by an earlier run are listed in fanout_manifest.json (next to the board) and
removed first; the search is deterministic (fixed candidate order, seeded permutations).
"""
import argparse
import fnmatch
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_BOARD = os.path.join(ROOT, "bay-station", "bay-station.kicad_pcb")
MANIFEST_NAME = "fanout_manifest.json"      # written next to the board it describes

# ----------------------------------------------------------------------------- numbers
STUB_W = 0.2
VIA_D, VIA_DRILL = 0.45, 0.20
VR = VIA_D / 2
STUB_MAX = 2.0           # total stub length, pad centre to via centre (check_gates STUB_MAX)
CLR = 0.16               # 0.15 mm copper clearance + 0.01 margin
VIA_PAD_OWN = 0.10       # via edge to its own pad edge (no via in pad, keeps the mask web)
VIA_PAD_OTHER = 0.20     # via edge to any other pad
VIA_VIA = 0.61           # centre to centre: 0.45 + 0.16
EDGE = 0.51              # copper to board edge (project rule 0.5)
KEEPOFF = 0.50           # .kicad_dru RF50/CLK to foreign track/via
NECK_EXT = 0.32          # RF neck continues this far past the pad end (docs/routing-plan.md s1)
CUTOUT_HALF = 2.75       # stitch.py CUTOUT 5.5 mm square under each DW3210
CORR_LEN = 4.0           # reserved corridor length behind an RF50/CLK pad
EP_MAX = 0.9             # pads whose SHORT side exceeds this (or area > 2.5 mm2) are EP / thermal pads
STEP = float(os.environ.get("FANOUT_STEP", "0.1"))   # candidate grid for the straight and diagonal legs
MAX_SHARE = 3            # pads per via

# DW3210 RF-side VSS pins (docs: skipped, tied by stitch.py rescue)
DW_RF_VSS = {"12", "14", "15", "16", "17", "19", "20"}
POWER_STAGE = {"U1", "U8", "U40"}            # power agent owns the hot loop: signal pins only
POWER_CLASSES = {"POWER_HI", "POWER_MID"}
NO_FAN = {"U30": "TCXO: clock tree is hand routed (stage 4), pads are the 15 x 10 mm placeholder"}
WITH_CONN = {"J12"}                          # SIM socket: the only connector fanned out


# ----------------------------------------------------------------------------- geometry
def d_pt_rect(px, py, r):
    dx = max(r[0] - px, 0.0, px - r[2])
    dy = max(r[1] - py, 0.0, py - r[3])
    return math.hypot(dx, dy)


def d_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _orient(px, py, qx, qy, rx, ry):
    return (qx - px) * (ry - py) - (qy - py) * (rx - px)


def d_seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    o1 = _orient(ax, ay, bx, by, cx, cy)
    o2 = _orient(ax, ay, bx, by, dx, dy)
    o3 = _orient(cx, cy, dx, dy, ax, ay)
    o4 = _orient(cx, cy, dx, dy, bx, by)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(d_pt_seg(ax, ay, cx, cy, dx, dy), d_pt_seg(bx, by, cx, cy, dx, dy),
               d_pt_seg(cx, cy, ax, ay, bx, by), d_pt_seg(dx, dy, ax, ay, bx, by))


def d_seg_rect(ax, ay, bx, by, r):
    """Exact distance between segment AB and an axis-aligned rectangle (0 when they touch)."""
    if d_pt_rect(ax, ay, r) == 0.0 or d_pt_rect(bx, by, r) == 0.0:
        return 0.0
    x0, y0, x1, y1 = r
    best = min(d_pt_rect(ax, ay, r), d_pt_rect(bx, by, r))
    for (cx, cy, dx, dy) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        best = min(best, d_seg_seg(ax, ay, bx, by, cx, cy, dx, dy))
        if best == 0.0:
            return 0.0
    return best


# ----------------------------------------------------------------------------- obstacle store
class Prim:
    """kind: pad (rect) | trk (seg + hw) | via (circle) | edge (seg) | kotrk (rect, no tracks) |
    kovia (rect, no vias) | corr (rect, RF/CLK corridor: no foreign track/via).  net: net code or 0."""
    __slots__ = ("kind", "g", "net", "own", "gid", "front")

    def __init__(self, kind, g, net=0, own=None, gid=None, front=True):
        self.kind, self.g, self.net, self.own, self.gid, self.front = kind, g, net, own, gid, front

    def bbox(self):
        g = self.g
        if self.kind in ("pad", "kotrk", "kovia", "corr"):
            return g
        if self.kind == "via":
            return (g[0] - g[2], g[1] - g[2], g[0] + g[2], g[1] + g[2])
        return (min(g[0], g[2]) - g[4], min(g[1], g[3]) - g[4], max(g[0], g[2]) + g[4], max(g[1], g[3]) + g[4])


class Store:
    def __init__(self, cell=1.0):
        self.c = cell
        self.cells = {}
        self.stack = []

    def _keys(self, bb, pad=0.0):
        c = self.c
        for ix in range(int(math.floor((bb[0] - pad) / c)), int(math.floor((bb[2] + pad) / c)) + 1):
            for iy in range(int(math.floor((bb[1] - pad) / c)), int(math.floor((bb[3] + pad) / c)) + 1):
                yield (ix, iy)

    def add(self, p):
        for k in self._keys(p.bbox()):
            self.cells.setdefault(k, []).append(p)
        self.stack.append(p)
        return p

    def mark(self):
        return len(self.stack)

    def rollback(self, m):
        while len(self.stack) > m:
            p = self.stack.pop()
            for k in self._keys(p.bbox()):
                self.cells[k].remove(p)

    def near(self, bb, pad):
        seen = set()
        for k in self._keys(bb, pad):
            for p in self.cells.get(k, ()):
                if id(p) not in seen:
                    seen.add(id(p))
                    yield p

    # --- legality ------------------------------------------------------------------------------
    def via_ok(self, x, y, net, own_pad, ignore_gid=None, cutouts=()):
        for (cx0, cy0, cx1, cy1) in cutouts:
            if d_pt_rect(x, y, (cx0, cy0, cx1, cy1)) < VR + 0.02:
                return False
        for p in self.near((x, y, x, y), 1.0):
            k, g = p.kind, p.g
            if k == "pad":
                need = VIA_PAD_OWN if p.own == own_pad else VIA_PAD_OTHER
                if d_pt_rect(x, y, g) - VR < need:
                    return False
            elif k == "via":
                if p.gid is not None and p.gid == ignore_gid:
                    continue
                if math.hypot(x - g[0], y - g[1]) < VIA_VIA:
                    return False
            elif k == "trk":
                if p.gid is not None and p.gid == ignore_gid:
                    continue
                need = KEEPOFF + 0.01 if p.own == "hs" else CLR
                if d_pt_seg(x, y, g[0], g[1], g[2], g[3]) - g[4] - VR < need:
                    return False
            elif k == "edge":
                if d_pt_seg(x, y, g[0], g[1], g[2], g[3]) - VR < EDGE:
                    return False
            elif k == "kovia":
                if d_pt_rect(x, y, g) < VR + 0.02:
                    return False
            elif k == "corr":
                if p.net != net and d_pt_rect(x, y, g) < VR:
                    return False
        return True

    def seg_ok(self, a, b, hw, net, own_pad, ignore_gid=None):
        ax, ay = a
        bx, by = b
        for p in self.near((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)), 1.0):
            k, g = p.kind, p.g
            if k == "pad":
                if p.own == own_pad or p.net == net:
                    continue
                if not p.front:
                    continue
                if d_seg_rect(ax, ay, bx, by, g) - hw < CLR:
                    return False
            elif k == "via":
                if p.gid is not None and p.gid == ignore_gid:
                    continue
                if d_pt_seg(g[0], g[1], ax, ay, bx, by) - hw - g[2] < CLR:
                    return False
            elif k == "trk":
                if p.gid is not None and p.gid == ignore_gid:
                    continue
                need = KEEPOFF + 0.01 if p.own == "hs" else CLR
                if d_seg_seg(ax, ay, bx, by, g[0], g[1], g[2], g[3]) - hw - g[4] < need:
                    return False
            elif k == "edge":
                if d_seg_seg(ax, ay, bx, by, g[0], g[1], g[2], g[3]) - hw < EDGE:
                    return False
            elif k == "kotrk":
                if d_seg_rect(ax, ay, bx, by, g) - hw < 0.01:
                    return False
            elif k == "corr":
                if p.net != net and d_seg_rect(ax, ay, bx, by, g) - hw < 0.005:
                    return False
        return True


# ----------------------------------------------------------------------------- board model
def load(board, spec):
    """Everything the search needs, in sheet mm."""
    import pcbnew
    import pcbutil as U
    mm = U.mm

    hs_pat = []
    for g in spec["groups"]:
        if g["class"] in ("RF50", "CLK"):
            hs_pat += g["patterns"]
    names = {str(n): net for n, net in board.GetNetsByName().items()}
    hs_codes = set()
    for n, net in names.items():
        if n and any(fnmatch.fnmatchcase(n, p) for p in hs_pat):
            hs_codes.add(net.GetNetCode())
    classes = {str(n): str(net.GetNetClassName()) for n, net in names.items()}

    pads = []          # dicts
    for f in board.GetFootprints():
        ref = str(f.GetReference())
        for p in f.Pads():
            bb = p.GetBoundingBox()
            rect = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
            c = p.GetPosition()
            name = str(p.GetNetname())
            pads.append(dict(ref=ref, num=str(p.GetNumber()), rect=rect, c=(mm(c.x), mm(c.y)), net=name,
                             code=p.GetNetCode(), npth=p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
                             front=p.IsOnLayer(U.F_CU), fp=str(f.GetFPID().GetLibItemName()),
                             hs=p.GetNetCode() in hs_codes and name != "",
                             cls=classes.get(name, "Default"), w=rect[2] - rect[0], h=rect[3] - rect[1]))
    return dict(pads=pads, hs_codes=hs_codes, classes=classes, names=names)


def build_store(board, model, rm_items=()):
    """Store with every pad, edge, rule area and the corridor reserved behind each RF50/CLK pad.
    Existing tracks/vias are added too, except those in rm_items (previous fan-out)."""
    import pcbnew
    import pcbutil as U
    mm = U.mm
    st = Store()
    cut = []
    for p in model["pads"]:
        if not p["rect"]:
            continue
        st.add(Prim("pad", p["rect"], p["code"], own=(p["ref"], p["num"]), front=p["front"]))
    poly = U.outline_polygon(board)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        st.add(Prim("edge", (a[0], a[1], b[0], b[1], 0.0)))
    zones = list(board.Zones()) + [z for f in board.GetFootprints() for z in f.Zones()]
    for z in zones:
        if not z.GetIsRuleArea():
            continue
        bb = z.GetBoundingBox()
        r = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        if z.GetDoNotAllowTracks() and z.IsOnLayer(U.F_CU):
            st.add(Prim("kotrk", r))
        if z.GetDoNotAllowVias():
            st.add(Prim("kovia", r))
    # DW3210 no-via cut-out + tracks keep-out are made later by stitch.py; reserve the same boxes now
    for f in board.GetFootprints():
        if "DW3210" in str(f.GetFPID().GetLibItemName()):
            ps = [p for p in model["pads"] if p["ref"] == str(f.GetReference())]
            cx = sum(p["c"][0] for p in ps) / len(ps)
            cy = sum(p["c"][1] for p in ps) / len(ps)
            cut.append((cx - CUTOUT_HALF, cy - CUTOUT_HALF, cx + CUTOUT_HALF, cy + CUTOUT_HALF))
    for r in cut:
        st.add(Prim("kovia", r))
    for t in board.GetTracks():
        key = item_key(t)
        if key in rm_items:
            continue
        net = t.GetNetCode()
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            st.add(Prim("via", (mm(q.x), mm(q.y), mm(t.GetWidth()) / 2), net))
        elif t.GetLayer() == U.F_CU:
            s, e = t.GetStart(), t.GetEnd()
            hs = str(t.GetNetClassName()) in ("RF50", "CLK")
            st.add(Prim("trk", (mm(s.x), mm(s.y), mm(e.x), mm(e.y), mm(t.GetWidth()) / 2), net, own="hs" if hs else None))
    return st, cut


def item_key(t):
    import pcbnew
    if t.Type() == pcbnew.PCB_VIA_T:
        q = t.GetPosition()
        return "V:%d:%d:%d" % (q.x, q.y, t.GetWidth())
    s, e = t.GetStart(), t.GetEnd()
    return "T:%d:%d:%d:%d:%d:%d" % (t.GetLayer(), s.x, s.y, e.x, e.y, t.GetWidth())


def add_corridors(st, model):
    """Reserve the future RF50/CLK track behind every such pad: pad centre outward, neck zone
    (neck half width 0.12 + keep-off) then the 0.45 mm line (0.225 + keep-off)."""
    pads = model["pads"]
    byref = {}
    for p in pads:
        byref.setdefault(p["ref"], []).append(p)
    for ref, ps in byref.items():
        if not any(p["hs"] for p in ps):
            continue
        for p in ps:
            if not p["hs"] or p["npth"] or is_ep(p):
                continue
            d = out_dirs(p, ps)
            if not d:
                continue
            dx, dy = d[0]
            hl = (p["w"] if dx else p["h"]) / 2
            cx, cy = p["c"]
            for (u0, u1, hw) in ((0.0, hl + NECK_EXT, 0.12 + KEEPOFF), (hl + NECK_EXT, CORR_LEN, 0.225 + KEEPOFF)):
                xs = (cx + dx * u0, cx + dx * u1)
                ys = (cy + dy * u0, cy + dy * u1)
                if dx:
                    r = (min(xs), cy - hw, max(xs), cy + hw)
                else:
                    r = (cx - hw, min(ys), cx + hw, max(ys))
                st.add(Prim("corr", r, p["code"]))


# ----------------------------------------------------------------------------- pad directions
def is_ep(p):
    return min(p["w"], p["h"]) > EP_MAX or p["w"] * p["h"] > 2.5


def out_dirs(p, same_fp):
    """Outward unit vectors for a pad (preferred first); [] if the pad is interior."""
    xs = [q["c"][0] for q in same_fp if not q["npth"]]
    ys = [q["c"][1] for q in same_fp if not q["npth"]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx, hy = max((max(xs) - min(xs)) / 2, 1e-6), max((max(ys) - min(ys)) / 2, 1e-6)
    ox, oy = p["c"][0] - cx, p["c"][1] - cy
    w, h = p["w"], p["h"]
    sx = 1 if ox > 0 else -1
    sy = 1 if oy > 0 else -1
    if w >= 1.4 * h:                                   # long axis horizontal
        return [(sx, 0)] if abs(ox) > 1e-6 else []
    if h >= 1.4 * w:
        return [(0, sy)] if abs(oy) > 1e-6 else []
    nx, ny = abs(ox) / hx, abs(oy) / hy
    if max(nx, ny) < 0.8:
        return []
    out = []
    first = (sx, 0) if nx >= ny else (0, sy)
    second = (0, sy) if nx >= ny else (sx, 0)
    out.append(first)
    if min(nx, ny) >= 0.5 * max(nx, ny):
        out.append(second)
    return out


_CAND = {}


def candidates(p, d, step=STEP):
    key = (round((p["w"] if d[0] else p["h"]) / 2, 4), step)
    if key not in _CAND:
        _CAND[key] = _candidates(p, d, step)
    return _CAND[key]


def _candidates(p, d, step=STEP):
    """(length, a, b, lat, c) sorted shortest first.  a = straight leg out of the pad, b = the ONE 45 degree
    jog (0 = none), lat = +-1 side of the jog, c = straight leg after the jog (a bend back to the outward
    direction: an offset, not a second turn)."""
    dx, dy = d
    hl = (p["w"] if dx else p["h"]) / 2
    out = []
    amin = hl + VIA_PAD_OWN + VR
    n = int(round((STUB_MAX - amin) / step))
    for i in range(n + 1):
        L = amin + i * step
        if L <= STUB_MAX + 1e-9:
            out.append((L, L, 0.0, 0, 0.0))
    a0 = max(0.2, hl - 0.1)
    na = int(round((STUB_MAX - 0.1 - a0) / step))
    for ia in range(na + 1):
        a = a0 + ia * step
        nb = int(round((STUB_MAX - a) / step))
        for ib in range(1, nb + 1):
            b = ib * step
            nc = int(round((STUB_MAX - a - b) / step))
            for ic in range(0, nc + 1):
                c = ic * step
                for lat in (1, -1):
                    out.append((a + b + c + 0.001 * (ic > 0), a, b, lat, c))
    out.sort(key=lambda t: (round(t[0], 3), t[2] > 0, -t[3], t[1]))
    return out


def geom(p, d, a, b, lat, c):
    """polyline points: pad centre, end of leg a, [end of the diagonal], [via centre after leg c]."""
    dx, dy = d
    cx, cy = p["c"]
    if b == 0.0:
        return [(cx, cy), (cx + dx * a, cy + dy * a)]
    c1 = (cx + dx * a, cy + dy * a)
    lx, ly = -dy * lat, dx * lat           # lateral unit vector
    k = b / math.sqrt(2)
    c2 = (c1[0] + dx * k + lx * k, c1[1] + dy * k + ly * k)
    if c <= 1e-9:
        return [(cx, cy), c1, c2]
    return [(cx, cy), c1, c2, (c2[0] + dx * c, c2[1] + dy * c)]


# ----------------------------------------------------------------------------- the search
class Fan:
    def __init__(self, st, cut, model):
        self.st, self.cut, self.model = st, cut, model
        self.vias = []        # dicts(gid, x, y, net, n)
        self.stubs = []       # dicts(gid, pts, net)
        self.gid = 0
        self.cache = {}

    def share_targets(self, p):
        out = []
        for v in self.vias:
            if v["net"] == p["code"] and v["n"] < MAX_SHARE and math.hypot(v["x"] - p["c"][0], v["y"] - p["c"][1]) < STUB_MAX:
                out.append(v)
        return out

    def try_pad(self, p, ps):
        """Place the best legal fan-out for pad p.  Returns result dict or None."""
        net, own = p["code"], (p["ref"], p["num"])
        dirs = out_dirs(p, ps)
        # 1. share a via of the same net (neighbouring pad's via)
        for v in self.share_targets(p):
            for d in dirs:
                u = (v["x"] - p["c"][0]) * d[0] + (v["y"] - p["c"][1]) * d[1]
                lat = (v["x"] - p["c"][0]) * -d[1] + (v["y"] - p["c"][1]) * d[0]
                if u <= 0.05 or abs(lat) > u + 1e-6:
                    continue
                if abs(lat) < 1e-6:
                    pts = [p["c"], (v["x"], v["y"])]
                else:
                    c1 = (p["c"][0] + d[0] * (u - abs(lat)), p["c"][1] + d[1] * (u - abs(lat)))
                    pts = [p["c"], c1, (v["x"], v["y"])]
                L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
                if L > STUB_MAX:
                    continue
                if all(self.st.seg_ok(pts[i], pts[i + 1], STUB_W / 2, net, own, ignore_gid=v["gid"]) for i in range(len(pts) - 1)):
                    return self.commit(p, pts, None, v)
        # 2. new via
        memo = {}

        def seg(a, b):
            k = (round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4))
            if k not in memo:
                memo[k] = self.st.seg_ok(a, b, STUB_W / 2, net, own)
            return memo[k]

        for d in dirs:
            for (L, a, b, lat, c) in candidates(p, d):
                pts = geom(p, d, a, b, lat, c)
                via = pts[-1]
                if not self.st.via_ok(via[0], via[1], net, own):
                    continue
                if all(seg(pts[i], pts[i + 1]) for i in range(len(pts) - 1)):
                    return self.commit(p, pts, via, None)
        return None

    def commit(self, p, pts, via, shared):
        self.gid += 1
        gid = self.gid
        if via is not None:
            v = dict(gid=gid, x=via[0], y=via[1], net=p["code"], n=1, pads=[(p["ref"], p["num"])])
            self.vias.append(v)
            self.st.add(Prim("via", (via[0], via[1], VR), p["code"], gid=gid))
            tgt = v
        else:
            shared["n"] += 1
            shared["pads"].append((p["ref"], p["num"]))
            tgt = shared
            gid = shared["gid"]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            self.st.add(Prim("trk", (a[0], a[1], b[0], b[1], STUB_W / 2), p["code"], gid=gid))
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        rec = dict(ref=p["ref"], num=p["num"], net=p["net"], code=p["code"], pts=pts, via=(tgt["x"], tgt["y"]),
                   shared=via is None, length=L, jog=len(pts) >= 3, gid=gid)
        self.stubs.append(rec)
        return rec


def orderings(n, seed):
    idx = list(range(n))
    out = [idx, idx[::-1], idx[0::2] + idx[1::2], idx[1::2] + idx[0::2],
           sorted(idx, key=lambda i: abs(i - (n - 1) / 2)), sorted(idx, key=lambda i: -abs(i - (n - 1) / 2))]
    rng = random.Random(seed)
    for _ in range(int(os.environ.get("FANOUT_PERMS", "10"))):
        q = idx[:]
        rng.shuffle(q)
        out.append(q)
    seen, res = set(), []
    for o in out:
        if tuple(o) not in seen:
            seen.add(tuple(o))
            res.append(o)
    return res


def run_group(fan, group, ps, seed):
    """Pads of one package side.  Try several orders on the live store, keep the best, replay it."""
    group = sorted(group, key=lambda p: (round(p["c"][1], 3), round(p["c"][0], 3)))
    n = len(group)
    best = None
    for oi, order in enumerate(orderings(n, seed) if n > 2 else [list(range(n))]):
        m = fan.st.mark()
        nv, ns, ng = len(fan.vias), len(fan.stubs), fan.gid
        saved = [(v, v["n"], len(v["pads"])) for v in fan.vias]
        done, total = 0, 0.0
        for i in order:
            r = fan.try_pad(group[i], ps)
            if r:
                done += 1
                total += r["length"] + (0.0 if r["shared"] else 0.3)
        score = (done, -total)
        if best is None or score > best[0]:
            best = (score, order)
        fan.st.rollback(m)
        del fan.vias[nv:]
        del fan.stubs[ns:]
        fan.gid = ng
        for v, nn, npd in saved:
            v["n"] = nn
            del v["pads"][npd:]
        if done == n:
            break
    for i in best[1]:
        fan.try_pad(group[i], ps)


# ----------------------------------------------------------------------------- classification
def classify(p, ps_fp, model, nets_count):
    """None = fan this pad out, else the skip reason."""
    ref, num = p["ref"], p["num"]
    name = p["net"]
    if p["npth"]:
        return "npth"
    if not p["front"]:
        return "not on F.Cu"
    if name == "" or name.startswith("unconnected-"):
        return "no net (NC)"
    if p["hs"]:
        return "RF50/CLK class net: hand routed in stage 4"
    if nets_count.get(p["code"], 0) < 2:
        return "net has no other pad"
    if is_ep(p):
        return "EP / thermal pad (pour and stitch tie it)"
    if "DW3210" in p["fp"] and num in DW_RF_VSS:
        return "DW3210 RF-side VSS: tied by stitch.py rescue"
    if ref in POWER_STAGE and (p["cls"] in POWER_CLASSES or name == "GND"):
        return "power-stage pin of %s (power agent routes the hot loop)" % ref
    for q in ps_fp:
        if q["hs"] and q is not p and math.hypot(q["c"][0] - p["c"][0], q["c"][1] - p["c"][1]) < 0.55:
            return "next to RF50/CLK pad %s (0.5 mm keep-off, stage 4)" % q["num"]
    if not out_dirs(p, ps_fp):
        return "interior pad (no outward direction)"
    return None


def select_parts(model):
    byref = {}
    for p in model["pads"]:
        byref.setdefault(p["ref"], []).append(p)
    out = []
    for ref in sorted(byref):
        ps = byref[ref]
        n = len([q for q in ps if not q["npth"]])
        if ref.startswith("TP") or n < 6:
            continue
        if ref.startswith("U") or ref in WITH_CONN:
            out.append(ref)
    return out, byref


def side_of(d):
    return {(1, 0): "E", (-1, 0): "W", (0, 1): "S", (0, -1): "N"}[d]


def run(board, spec, rm_items):
    model = load(board, spec)
    st, cut = build_store(board, model, rm_items)
    add_corridors(st, model)
    fan = Fan(st, cut, model)
    nets_count = {}
    for p in model["pads"]:
        if p["code"] and not p["npth"]:
            nets_count[p["code"]] = nets_count.get(p["code"], 0) + 1
    refs, byref = select_parts(model)
    report = {"packages": {}}
    for ref in refs:
        ps = byref[ref]
        rep = dict(pads=len(ps), fanned=0, shared=0, skipped={}, failed=[], fp=ps[0]["fp"])
        if ref in NO_FAN:
            rep["skipped"][NO_FAN[ref]] = [p["num"] for p in ps]
            report["packages"][ref] = rep
            continue
        groups = {}
        for p in ps:
            why = classify(p, ps, model, nets_count)
            if why:
                rep["skipped"].setdefault(why, []).append(p["num"])
                continue
            d = out_dirs(p, ps)[0]
            groups.setdefault(side_of(d), []).append(p)
        for side in sorted(groups):
            run_group(fan, groups[side], ps, seed=hash_seed(ref, side))
        done = {(s["ref"], s["num"]) for s in fan.stubs}
        for side in sorted(groups):
            for p in groups[side]:
                if (p["ref"], p["num"]) not in done:
                    rep["failed"].append("%s(%s)" % (p["num"], p["net"].split("/")[-1]))
        rep["fanned"] = len([s for s in fan.stubs if s["ref"] == ref])
        rep["shared"] = len([s for s in fan.stubs if s["ref"] == ref and s["shared"]])
        report["packages"][ref] = rep
    return fan, report


def hash_seed(ref, side):
    h = 17
    for ch in ref + side:
        h = (h * 131 + ord(ch)) % 1000003
    return h


# ----------------------------------------------------------------------------- board output
def write(board, fan, old_keys):
    import pcbnew
    import pcbutil as U
    for t in list(board.GetTracks()):
        if item_key(t) in old_keys:
            board.Remove(t)
    keys = []
    vias_done = set()
    for s in fan.stubs:
        net = board.FindNet(s["net"])
        for i in range(len(s["pts"]) - 1):
            a, b = s["pts"][i], s["pts"][i + 1]
            t = U.add_track(board, net, U.F_CU, a[0], a[1], b[0], b[1], STUB_W, locked=True)
            keys.append(item_key(t))
        if s["gid"] not in vias_done:
            vias_done.add(s["gid"])
            v = U.add_via(board, net, s["via"][0], s["via"][1], VIA_D, VIA_DRILL, locked=True)
            keys.append(item_key(v))
    return keys


def dump(board, fan, report, path, model):
    import pcbutil as U
    d = {"pads": [dict(ref=p["ref"], num=p["num"], rect=p["rect"], net=p["net"], hs=p["hs"]) for p in model["pads"]
                  if p["front"]],
         "stubs": [dict(ref=s["ref"], num=s["num"], pts=s["pts"], via=s["via"], net=s["net"]) for s in fan.stubs],
         "outline": U.outline_polygon(board), "report": report}
    json.dump(d, open(path, "w"))


# ----------------------------------------------------------------------------- render (system python)
def render(jpath, png, crop, scale):
    from PIL import Image, ImageDraw, ImageFont
    d = json.load(open(jpath))
    x0, y0, x1, y1 = crop
    S = scale
    img = Image.new("RGB", (int((x1 - x0) * S), int((y1 - y0) * S)), (28, 32, 30))
    dr = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.load_default(size=max(9, int(S * 0.2)))
    except Exception:
        font = ImageFont.load_default()

    def P(x, y):
        return ((x - x0) * S, (y - y0) * S)

    poly = d["outline"]
    if poly:
        dr.line([P(*q) for q in poly] + [P(*poly[0])], fill=(255, 255, 0), width=2)
    for p in d["pads"]:
        r = p["rect"]
        if r[2] < x0 or r[0] > x1 or r[3] < y0 or r[1] > y1:
            continue
        col = (60, 190, 90, 255) if p["net"] == "GND" else ((220, 60, 220, 255) if p["hs"] else (200, 70, 60, 255))
        dr.rectangle([P(r[0], r[1]), P(r[2], r[3])], fill=col)
        if p["ref"].startswith("U") and S >= 40:
            dr.text(P(r[0], r[1] - 0.18), p["num"], fill=(255, 255, 255, 230), font=font)
    for s in d["stubs"]:
        pts = s["pts"]
        col = (80, 160, 255, 235)
        for a, b in zip(pts, pts[1:]):
            dr.line([P(*a), P(*b)], fill=col, width=max(2, int(0.2 * S)))
    done = set()
    for s in d["stubs"]:
        v = s["via"]
        if tuple(v) in done:
            continue
        done.add(tuple(v))
        if x0 - 1 < v[0] < x1 + 1 and y0 - 1 < v[1] < y1 + 1:
            dr.ellipse([P(v[0] - 0.225, v[1] - 0.225), P(v[0] + 0.225, v[1] + 0.225)], fill=(230, 200, 60, 255))
            dr.ellipse([P(v[0] - 0.1, v[1] - 0.1), P(v[0] + 0.1, v[1] + 0.1)], fill=(20, 20, 20, 255))
    img.save(png)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--out", help="write here instead of --board (the manifest is only updated when writing --board)")
    ap.add_argument("--report", help="JSON report")
    ap.add_argument("--dump", help="geometry JSON for --render")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--render", nargs=2, metavar=("DUMP.json", "OUT.png"))
    ap.add_argument("--crop", type=float, nargs=4, help="sheet mm x0 y0 x1 y1 (render)")
    ap.add_argument("--scale", type=float, default=80.0)
    a = ap.parse_args()
    if a.render:
        render(a.render[0], a.render[1], a.crop, a.scale)
        return
    sys.path.insert(0, HERE)
    import pcbnew
    import pcbutil as U
    pcbnew.KIID.SeedGenerator(20261118)
    spec = U.load_spec()
    man_in = os.path.join(os.path.dirname(os.path.abspath(a.board)), MANIFEST_NAME)
    old = set(json.load(open(man_in))) if os.path.exists(man_in) else set()
    board = U.load_board(a.board)
    fan, report = run(board, spec, old)
    tot = dict(pads=0, fanned=0, shared=0, vias=len(fan.vias),
               stub_mm=round(sum(s["length"] for s in fan.stubs), 1),
               max_stub=round(max([s["length"] for s in fan.stubs] or [0]), 3))
    for ref, r in report["packages"].items():
        tot["pads"] += r["pads"]
        tot["fanned"] += r["fanned"]
        tot["shared"] += r["shared"]
        sk = sum(len(v) for v in r["skipped"].values())
        print("%-5s %-44s pads %3d fanned %3d (shared via %d) skipped %3d failed %3d" % (
            ref, r["fp"][:44], r["pads"], r["fanned"], r["shared"], sk, len(r["failed"])))
        for why, nums in sorted(r["skipped"].items()):
            print("        skip  %-62s %s" % (why[:62], ",".join(nums[:14]) + ("..." if len(nums) > 14 else "")))
        if r["failed"]:
            print("        FAIL  " + " ".join(r["failed"]))
    report["totals"] = tot
    print("TOTAL", tot)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1, sort_keys=True)
    if a.dump:
        dump(board, fan, report, a.dump, load(board, spec))
    if a.no_save:
        return
    keys = write(board, fan, old)
    target = a.out or a.board
    U.save_board(board, target)
    json.dump(sorted(keys), open(os.path.join(os.path.dirname(os.path.abspath(target)), MANIFEST_NAME), "w"), indent=0)


if __name__ == "__main__":
    main()
