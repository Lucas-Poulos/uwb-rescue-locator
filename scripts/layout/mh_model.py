"""Data model for the Manhattan router: exact obstacles (Obst), clearance-inflated
grid occupancy per track half-width (Grid/Tier) and the board loader (Model).
See route_manhattan.py for the router and policy."""
import argparse
import heapq
import json
import math
import os
import sys
import time
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U

F, B = 0, 1
LAYER_OF = {F: U.F_CU, B: U.B_CU}
MULTI = 65534
STATIC = 65535

CLR = 0.15              # default copper clearance (all netclasses; hs_nets.json)
CLR_KEEPOFF = 0.5       # .kicad_dru: track/via/zone to RF50/CLK track
STUB_W = 0.2
STUB_MAX = 2.0          # mm, pad escape reach
GND_STUB_MAX = 3.0
VIA_COST = 30
STEP_COST = 1
STUB_COST = 2
CONFLICT_COST = 80
MAX_RIPS = 3
EDGE_CLR = 0.5          # board edge to copper (project rule)
HOLE_CLR = 0.25         # drill to copper / drill to drill


# ======================================================================= geometry
def seg_seg_dist(ax, ay, bx, by, cx, cy, dx, dy):
    """Minimum distance between segments AB and CD."""
    def orient(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    o1 = orient(ax, ay, bx, by, cx, cy); o2 = orient(ax, ay, bx, by, dx, dy)
    o3 = orient(cx, cy, dx, dy, ax, ay); o4 = orient(cx, cy, dx, dy, bx, by)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0:
        return 0.0
    return min(U.dist_pt_seg(ax, ay, cx, cy, dx, dy), U.dist_pt_seg(bx, by, cx, cy, dx, dy),
               U.dist_pt_seg(cx, cy, ax, ay, bx, by), U.dist_pt_seg(dx, dy, ax, ay, bx, by))


class Prim:
    """One piece of copper or keep-out.  kind: 'rect' (x0,y0,x1,y1), 'circ' (x,y,r),
    'seg' (x0,y0,x1,y1,hw).  layers: tuple of 0/1 (F/B); net: net index or 0 (no net);
    clr: required clearance to OTHER nets' copper; static: never ripped."""
    __slots__ = ("kind", "g", "layers", "net", "clr", "static", "owner_item")

    def __init__(self, kind, g, layers, net, clr, static=True, owner_item=None):
        self.kind, self.g, self.layers, self.net, self.clr, self.static = kind, g, layers, net, clr, static
        self.owner_item = owner_item

    def bbox(self):
        g = self.g
        if self.kind == "rect":
            return g
        if self.kind == "circ":
            return (g[0] - g[2], g[1] - g[2], g[0] + g[2], g[1] + g[2])
        return (min(g[0], g[2]) - g[4], min(g[1], g[3]) - g[4], max(g[0], g[2]) + g[4], max(g[1], g[3]) + g[4])

    def dist_pt(self, x, y):
        """Distance from a point to this copper's edge (negative inside)."""
        g = self.g
        if self.kind == "rect":
            return U.dist_pt_rect(x, y, *g)
        if self.kind == "circ":
            return math.hypot(x - g[0], y - g[1]) - g[2]
        return U.dist_pt_seg(x, y, g[0], g[1], g[2], g[3]) - g[4]

    def dist_seg(self, ax, ay, bx, by):
        """Distance from segment AB (centre line) to this copper's edge."""
        g = self.g
        if self.kind == "seg":
            return seg_seg_dist(ax, ay, bx, by, g[0], g[1], g[2], g[3]) - g[4]
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L / 0.04))
        best = 1e9
        for i in range(n + 1):
            t = i / n
            d = self.dist_pt(ax + (bx - ax) * t, ay + (by - ay) * t)
            if d < best:
                best = d
        return best


class Obst:
    """Exact primitives in a bucket hash, for stub legality and final checks."""

    def __init__(self, bucket=2.0):
        self.b = bucket
        self.cells = {}
        self.items = {}
        self.nid = 0

    def _keys(self, bb):
        b = self.b
        for ix in range(int(math.floor(bb[0] / b)), int(math.floor(bb[2] / b)) + 1):
            for iy in range(int(math.floor(bb[1] / b)), int(math.floor(bb[3] / b)) + 1):
                yield (ix, iy)

    def add(self, p):
        self.nid += 1
        self.items[self.nid] = p
        # clearance is applied by the query, not the bucket
        for k in self._keys(p.bbox()):
            self.cells.setdefault(k, []).append(self.nid)
        return self.nid

    def remove(self, i):
        p = self.items.pop(i)
        for k in self._keys(p.bbox()):
            self.cells[k].remove(i)

    def near(self, bb):
        seen = set()
        for k in self._keys(bb):
            for i in self.cells.get(k, ()):
                if i not in seen:
                    seen.add(i)
                    yield self.items[i]

    def seg_ok(self, net, layer, ax, ay, bx, by, hw, slack=0.004):
        """Exact: does a track AB of half-width hw on `layer` clear all copper of other nets?"""
        pad = hw + CLR_KEEPOFF + 0.3
        bb = (min(ax, bx) - pad, min(ay, by) - pad, max(ax, bx) + pad, max(ay, by) + pad)
        for p in self.near(bb):
            if p.net == net or layer not in p.layers:
                continue
            need = hw + p.clr
            if p.dist_seg(ax, ay, bx, by) < need - slack:
                return False
        return True


# ======================================================================= grid maps
class Tier:
    """Clearance-inflated occupancy for one copper half-width."""

    def __init__(self, grid, hw):
        self.g = grid
        self.hw = hw
        n = grid.W * grid.H
        self.S = [array("H", bytes(2 * n)), array("H", bytes(2 * n))]
        self.D = [array("H", bytes(2 * n)), array("H", bytes(2 * n))]
        self.multi = [{}, {}]


class Grid:
    def __init__(self, bbox, pitch):
        self.p = pitch
        self.x0, self.y0 = bbox[0], bbox[1]
        self.W = int((bbox[2] - bbox[0]) / pitch) + 1
        self.H = int((bbox[3] - bbox[1]) / pitch) + 1
        self.tiers = {}
        self.nopad = bytearray(self.W * self.H)     # via not allowed (on/near any pad)
        self.viablk = array('H', bytes(2 * self.W * self.H))   # count of dynamic vias within drill-to-drill range
        self.prims_static = []
        self.prims_dyn = {}                          # item id -> Prim

    def xy(self, ix, iy):
        return (self.x0 + ix * self.p, self.y0 + iy * self.p)

    def cell(self, x, y):
        return (int(round((x - self.x0) / self.p)), int(round((y - self.y0) / self.p)))

    def tier(self, hw):
        key = round(hw, 3)
        if key not in self.tiers:
            t = Tier(self, key)
            self.tiers[key] = t
            for pr in self.prims_static:
                self._stamp(t, pr, dyn=False)
            for pr in self.prims_dyn.values():
                self._stamp(t, pr, dyn=True)
        return self.tiers[key]

    # -- stamping ------------------------------------------------------------
    def _cells(self, pr, r):
        """Yield (idx) of cells whose centre is within r of the primitive's copper."""
        bb = pr.bbox()
        p = self.p
        ix0 = max(0, int(math.floor((bb[0] - r - self.x0) / p)))
        ix1 = min(self.W - 1, int(math.ceil((bb[2] + r - self.x0) / p)))
        iy0 = max(0, int(math.floor((bb[1] - r - self.y0) / p)))
        iy1 = min(self.H - 1, int(math.ceil((bb[3] + r - self.y0) / p)))
        W = self.W
        k, g = pr.kind, pr.g
        for iy in range(iy0, iy1 + 1):
            y = self.y0 + iy * p
            base = iy * W
            for ix in range(ix0, ix1 + 1):
                x = self.x0 + ix * p
                if k == "rect":
                    d = U.dist_pt_rect(x, y, *g)
                elif k == "circ":
                    d = math.hypot(x - g[0], y - g[1]) - g[2]
                else:
                    d = U.dist_pt_seg(x, y, g[0], g[1], g[2], g[3]) - g[4]
                if d < r - 1e-9:
                    yield base + ix

    def _stamp(self, tier, pr, dyn, remove=False):
        r = tier.hw + pr.clr + 0.004
        for l in pr.layers:
            arr = (tier.D if dyn else tier.S)[l]
            multi = tier.multi[l]
            net = pr.net if pr.net else STATIC
            for i in self._cells(pr, r):
                if not remove:
                    v = arr[i]
                    if v == 0:
                        arr[i] = net
                    elif v != net:
                        if v == MULTI:
                            multi[i].add(net)
                        else:
                            multi[i] = {v, net}
                            arr[i] = MULTI
                else:
                    v = arr[i]
                    if v == net:
                        arr[i] = 0
                    elif v == MULTI:
                        s = multi.get(i)
                        if s is not None:
                            s.discard(net)
                            if len(s) == 1:
                                arr[i] = next(iter(s))
                                del multi[i]
                            elif not s:
                                arr[i] = 0
                                del multi[i]

    def add_static(self, pr):
        self.prims_static.append(pr)
        for t in self.tiers.values():
            self._stamp(t, pr, dyn=False)

    def add_dyn(self, iid, pr):
        self.prims_dyn[iid] = pr
        for t in self.tiers.values():
            self._stamp(t, pr, dyn=True)

    def remove_dyn(self, iid):
        pr = self.prims_dyn.pop(iid)
        for t in self.tiers.values():
            self._stamp(t, pr, dyn=True, remove=True)


# ======================================================================= board model
class Model:
    def __init__(self, board, pitch, skip_classes=("RF50",)):
        self.b = board
        self.pitch = pitch
        self.nets = {}               # net index -> dict(name, code, cls, track, via_dia, via_drill)
        self.code2idx = {}
        classes = U.load_spec()["classes"]     # same numbers apply_rules.py wrote to the .kicad_pro
        names = board.GetNetsByName()
        idx = 0
        for name, net in names.items():
            nm = str(name)
            if nm == "":
                continue
            idx += 1
            cname = str(net.GetNetClassName())
            nc = classes.get(cname) or classes["Default"]
            self.nets[idx] = dict(name=nm, code=net.GetNetCode(), cls=cname,
                                  track=nc["track"], via_dia=nc["via_dia"],
                                  via_drill=nc["via_drill"], pads=[])
            self.code2idx[net.GetNetCode()] = idx
        self.skip_classes = set(skip_classes)
        self.pad_prims = []
        self.obst = Obst()
        poly = U.outline_polygon(board)
        if poly is None:
            raise SystemExit("board has no Edge.Cuts outline: place and outline the board first")
        self.poly = poly
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        self.grid = Grid((min(xs), min(ys), max(xs), max(ys)), pitch)
        self._load_static()
        self.routes = {}             # net idx -> list of records
        self.iid = 0

    # -- static obstacles ------------------------------------------------------
    def _add_static(self, pr):
        self.grid.add_static(pr)
        self.obst.add(pr)

    def _load_static(self):
        b = self.b
        g = self.grid
        for f in b.GetFootprints():
            for p in f.Pads():
                net = self.code2idx.get(p.GetNetCode(), 0)
                layers = tuple(l for l, kl in ((F, U.F_CU), (B, U.B_CU)) if p.IsOnLayer(kl))
                bb = p.GetBoundingBox()
                rect = (U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()))
                c = p.GetPosition()
                info = dict(pad=p, net=net, c=(U.mm(c.x), U.mm(c.y)), rect=rect, layers=layers,
                            ref=str(f.GetReference()), num=str(p.GetNumber()),
                            th=p.HasHole(), npth=p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH)
                lc = None
                try:
                    lc = p.GetLocalClearance()
                    lc = U.mm(lc) if lc is not None else None
                except Exception:
                    lc = None
                pclr = max(CLR, lc) if lc else CLR
                if layers:
                    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                        pr = Prim("circ", (info["c"][0], info["c"][1], (rect[2] - rect[0]) / 2), layers, net, pclr, owner_item="pad")
                    else:
                        pr = Prim("rect", rect, layers, net, pclr, owner_item="pad")
                    self._add_static(pr)
                    # no vias on or near any pad
                    for i in g._cells(Prim("rect", (rect[0] - 0.2, rect[1] - 0.2, rect[2] + 0.2, rect[3] + 0.2), (), 0, 0), 1e-6):
                        g.nopad[i] = 1
                if p.HasHole():
                    d = max(p.GetDrillSize().x, p.GetDrillSize().y)
                    hr = U.mm(d) / 2
                    # drill keep-away on both layers against OTHER nets (own pad already stamped)
                    if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not layers:
                        self._add_static(Prim("circ", (info["c"][0], info["c"][1], hr), (F, B), 0, HOLE_CLR))
                if net and not info["npth"]:
                    self.nets[net]["pads"].append(info)
        # existing tracks and vias: fixed
        for t in b.GetTracks():
            net = self.code2idx.get(t.GetNetCode(), 0)
            cls = str(t.GetNetClassName())
            clr = CLR_KEEPOFF if cls in ("RF50", "CLK") else CLR
            if t.Type() == pcbnew.PCB_VIA_T:
                q = t.GetPosition()
                self._add_static(Prim("circ", (U.mm(q.x), U.mm(q.y), U.mm(t.GetWidth()) / 2), (F, B), net, clr))
                self._add_static(Prim("circ", (U.mm(q.x), U.mm(q.y), U.mm(t.GetDrill()) / 2), (F, B), 0, HOLE_CLR))
            else:
                l = F if t.GetLayer() == U.F_CU else (B if t.GetLayer() == U.B_CU else None)
                if l is None:
                    continue
                if t.GetClass() == "PCB_ARC":
                    s, m, e = t.GetStart(), t.GetMid(), t.GetEnd()
                    pts = [(U.mm(s.x), U.mm(s.y)), (U.mm(m.x), U.mm(m.y)), (U.mm(e.x), U.mm(e.y))]
                    for a, c in zip(pts, pts[1:]):
                        self._add_static(Prim("seg", (a[0], a[1], c[0], c[1], U.mm(t.GetWidth()) / 2), (l,), net, clr))
                else:
                    s, e = t.GetStart(), t.GetEnd()
                    self._add_static(Prim("seg", (U.mm(s.x), U.mm(s.y), U.mm(e.x), U.mm(e.y), U.mm(t.GetWidth()) / 2),
                                          (l,), net, clr))
        # board edge: outline segments keep EDGE_CLR from copper centre-line + hw (via clr)
        n = len(self.poly)
        for i in range(n):
            a, c = self.poly[i], self.poly[(i + 1) % n]
            self._add_static(Prim("seg", (a[0], a[1], c[0], c[1], 0.0), (F, B), 0, EDGE_CLR))
        # outside the polygon: block cells (for non-rectangular outlines)
        self._block_outside()
        # keepout rule areas: block tracks and/or vias where the zone says so
        all_zones = list(b.Zones()) + [z for f in b.GetFootprints() for z in f.Zones()]
        for z in all_zones:
            if not z.GetIsRuleArea():
                continue
            bb = z.GetBoundingBox()
            rect = (U.mm(bb.GetLeft()), U.mm(bb.GetTop()), U.mm(bb.GetRight()), U.mm(bb.GetBottom()))
            lay = tuple(l for l, kl in ((F, U.F_CU), (B, U.B_CU)) if z.IsOnLayer(kl))
            if z.GetDoNotAllowTracks() and lay:
                self._add_static(Prim("rect", rect, lay, 0, 0.0))
            if z.GetDoNotAllowVias():
                for i in g._cells(Prim("rect", rect, (), 0, 0), 1e-6):
                    g.nopad[i] = 1

    def _block_outside(self):
        g = self.grid
        poly = self.poly
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        rect = len(poly) == 4 and all(abs(p[0] - xs[0]) < 1e-6 or abs(p[0] - xs[-1]) < 1e-6 or True for p in poly)
        is_rect = len(poly) == 4 and len(set(round(x, 4) for x in xs)) == 2 and len(set(round(y, 4) for y in ys)) == 2
        if is_rect:
            return
        # scanline: cells whose centre is outside the polygon are blocked in the S arrays of every tier
        self.outside_cells = []
        for iy in range(g.H):
            y = g.y0 + iy * g.p
            for ix in range(g.W):
                x = g.x0 + ix * g.p
                if not U.point_in_poly(x, y, poly):
                    self.outside_cells.append(iy * g.W + ix)
        outside = self.outside_cells
        orig_tier = g.tier

        def tier_with_outside(hw, _o=outside):
            created = round(hw, 3) not in g.tiers
            t = orig_tier(hw)
            if created:
                for l in (0, 1):
                    S = t.S[l]
                    for i in _o:
                        S[i] = STATIC
            return t
        g.tier = tier_with_outside
