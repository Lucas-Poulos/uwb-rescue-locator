#!/usr/bin/env python3
"""In-house orthogonal router for the ORDINARY nets of the bay-station board.

Policy (the user's): F.Cu carries HORIZONTAL tracks only, B.Cu VERTICAL only;
a via appears only where the direction changes; 45 degrees is never used by
this router.  Two listed exceptions, both short:
  * pad escape stubs (<= 2 mm, any orthogonal direction on the pad's own layer,
    0.2 mm wide): fine-pitch pads cannot take a horizontal track from every side
    and pad centres are not on the routing grid;
  * GND fan-out stubs (<= 3 mm) ending in a via to the In1/In2 planes.

Method: grid maze router (A*) on a 0.1 mm grid, two layers, pure python (KiCad's
interpreter has no numpy).  Obstacles are rasterised per track half-width
("tier") with clearance already added, so a legal node is a legal track.
Congestion: rip-up and retry -- a net that cannot be routed against fixed copper
is searched again allowed to cross other routed nets at a penalty; the nets it
crosses are ripped up and re-queued (<= MAX_RIPS per net).  Multi-pin nets grow
a tree.  Copper already on the board (locked hand-routed RF/CLK lines, fences)
is a fixed obstacle and, for its own net, a connection target.

NOT done: differential pairs, length matching, 45 degree/arc bends, zone fill,
look-ahead beyond rip-up, DRC-driven repair.  The kicad-cli DRC is the judge.

    kicad-python route_manhattan.py --board SCRATCH.kicad_pcb [--out OTHER.kicad_pcb]
        [--pitch 0.1] [--seconds 900] [--skip-class RF50] [--no-gnd] [--report r.json]
"""
import argparse
import heapq
import json
import math
import os
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import pcbutil as U
from mh_model import (F, B, LAYER_OF, MULTI, STATIC, CLR, CLR_KEEPOFF, Prim, Model)

STUB_W = 0.2
STUB_MAX = 2.0
GND_STUB_MAX = 3.0
VIA_COST = 30
STEP_COST = 1
STUB_COST = 2
CONFLICT_COST = 80
MAX_RIPS = 3
WEIGHT = 1.5
CLASS_RANK = {"POWER_HI": 0, "POWER_MID": 1, "FASTDIG": 2, "POWER_LO": 3, "CLK": 4, "Default": 5}


class Router:
    def __init__(self, model, seconds=900.0, skip_classes=("RF50", "CLK"), do_gnd=True, verbose=True, only=None):
        self.only = set(only) if only else None
        self.m = model
        self.g = model.grid
        self.obst = model.obst
        self.deadline = time.time() + seconds * 0.85
        self.final_deadline = time.time() + seconds
        self.skip = set(skip_classes)
        self.do_gnd = do_gnd
        self.verbose = verbose
        self.rec = {}            # net -> list of records
        self.rips = {}
        self.access_cache = {}
        self.failed = {}         # net -> number of unconnected components left
        self.necked = {}         # net -> narrowest width it had to be routed at
        self.iid = 0
        self.stats = dict(expanded=0, searches=0)
        self.limit = 350000

    # ------------------------------------------------------------------ helpers
    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def node(self, ix, iy, l):
        return (iy * self.g.W + ix) * 2 + l

    def dec(self, n):
        i, l = divmod(n, 2)
        iy, ix = divmod(i, self.g.W)
        return ix, iy, l

    def tiers(self, net, hw=None):
        info = self.m.nets[net]
        return self.g.tier((info["track"] / 2) if hw is None else hw), self.g.tier(info["via_dia"] / 2)

    VIA_SPACING = 0.70      # centre to centre of two vias: drill-to-drill 0.25 with 0.3 drills + margin

    def via_block(self, x, y, delta):
        g = self.g
        rr = self.VIA_SPACING
        ix0, iy0 = g.cell(x - rr, y - rr)
        ix1, iy1 = g.cell(x + rr, y + rr)
        for iy in range(max(0, iy0), min(g.H - 1, iy1) + 1):
            for ix in range(max(0, ix0), min(g.W - 1, ix1) + 1):
                gx, gy = g.xy(ix, iy)
                if math.hypot(gx - x, gy - y) < rr:
                    g.viablk[iy * g.W + ix] += delta

    def verify_runs(self, net, path, width, ignore):
        """Exact check of every run and via of a found path against the obstacle set
        (nets in `ignore` are about to be ripped)."""
        info = self.m.nets[net]
        g = self.g
        k, n = 0, len(path)
        while k < n:
            ix, iy, l = self.dec(path[k])
            j = k
            while j + 1 < n and self.dec(path[j + 1])[2] == l:
                j += 1
            ix2, iy2, _ = self.dec(path[j])
            x0, y0 = g.xy(ix, iy)
            x1, y1 = g.xy(ix2, iy2)
            if not self.obst.seg_ok(net, l, x0, y0, x1, y1, width / 2, ignore=ignore):
                return False
            if j + 1 < n:
                for ll in (F, B):
                    if not self.obst.seg_ok(net, ll, x1, y1, x1, y1, info["via_dia"] / 2, ignore=ignore):
                        return False
            k = j + 1
        return True

    def stub_ok(self, net, layer, poly):
        if not poly:
            return True
        for a, c in zip(poly, poly[1:]):
            if not self.obst.seg_ok(net, layer, a[0], a[1], c[0], c[1], STUB_W / 2):
                return False
        return True

    # ------------------------------------------------------------------ pad access
    def pad_access(self, info, net, lmax):
        """{node: (cost, polyline)} grid nodes reachable from the pad centre by a short
        axis-parallel stub on the pad's layer(s).  Exact clearance test (Obst)."""
        key = (info["ref"], info["num"], lmax)
        if key in self.access_cache:
            return self.access_cache[key]
        g, obst = self.g, self.obst
        cx, cy = info["c"]
        hw = STUB_W / 2
        p = g.p
        res = {}
        for l in info["layers"]:
            lay = LAYER_OF[l]
            for (dx, dy) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                t = 0.0
                step = 0.05
                px, py = cx, cy
                while t < lmax:
                    nx, ny = cx + dx * (t + step), cy + dy * (t + step)
                    if not obst.seg_ok(net, l, px, py, nx, ny, hw):
                        break
                    px, py, t = nx, ny, t + step
                tmax = t
                if dx != 0:
                    ixa = int(math.ceil((min(cx, cx + dx * tmax) - g.x0) / p - 1e-9))
                    ixb = int(math.floor((max(cx, cx + dx * tmax) - g.x0) / p + 1e-9))
                    iy_f = (cy - g.y0) / p
                    rows = sorted({int(math.floor(iy_f)), int(math.ceil(iy_f))})
                    for ix in range(ixa, ixb + 1):
                        gx = g.x0 + ix * p
                        for iy in rows:
                            gy = g.y0 + iy * p
                            if abs(gy - cy) > 1e-6 and not obst.seg_ok(net, l, gx, cy, gx, gy, hw):
                                continue
                            pts = [(cx, cy)]
                            if abs(gx - cx) > 1e-6:
                                pts.append((gx, cy))
                            if abs(gy - cy) > 1e-6:
                                pts.append((gx, gy))
                            if len(pts) == 1:
                                pts.append((gx, gy))
                            cost = int(((abs(gx - cx) + abs(gy - cy)) / p) * STUB_COST) + 1
                            nd = self.node(ix, iy, l)
                            if nd not in res or res[nd][0] > cost:
                                res[nd] = (cost, pts)
                else:
                    iya = int(math.ceil((min(cy, cy + dy * tmax) - g.y0) / p - 1e-9))
                    iyb = int(math.floor((max(cy, cy + dy * tmax) - g.y0) / p + 1e-9))
                    ix_f = (cx - g.x0) / p
                    cols = sorted({int(math.floor(ix_f)), int(math.ceil(ix_f))})
                    for iy in range(iya, iyb + 1):
                        gy = g.y0 + iy * p
                        for ix in cols:
                            gx = g.x0 + ix * p
                            if abs(gx - cx) > 1e-6 and not obst.seg_ok(net, l, cx, gy, gx, gy, hw):
                                continue
                            pts = [(cx, cy)]
                            if abs(gy - cy) > 1e-6:
                                pts.append((cx, gy))
                            if abs(gx - cx) > 1e-6:
                                pts.append((gx, gy))
                            if len(pts) == 1:
                                pts.append((gx, gy))
                            cost = int(((abs(gx - cx) + abs(gy - cy)) / p) * STUB_COST) + 1
                            nd = self.node(ix, iy, l)
                            if nd not in res or res[nd][0] > cost:
                                res[nd] = (cost, pts)
        self.access_cache[key] = res
        return res

    # ------------------------------------------------------------------ components
    def components(self, net):
        """Connected groups of the net's pads and existing (pre-routed) copper.
        Returns list of dict(nodes={node:(cost,poly|None)}, pts=[(x,y)], npads=n)."""
        m, g = self.m, self.g
        info = m.nets[net]
        pads = info["pads"]
        # existing tracks/vias of this net (static prims with this net, not pads/edge)
        segs = [pr for pr in m.obst.items.values() if pr.net == net and pr.kind == "seg" and pr.static
                and pr.owner_item is None]
        vias = [pr for pr in m.obst.items.values() if pr.net == net and pr.kind == "circ" and len(pr.layers) == 2
                and pr.static and pr.owner_item is None and pr.g[2] > 0.2]
        n_el = len(pads) + len(segs) + len(vias)
        parent = list(range(n_el))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        # element shapes as Prims for distance tests
        els = []
        for pd in pads:
            r = pd["rect"]
            els.append(Prim("rect", r, tuple(pd["layers"]), net, 0))
        els += segs
        els += vias
        for i in range(n_el):
            for j in range(i + 1, n_el):
                a, b = els[i], els[j]
                if not set(a.layers) & set(b.layers):
                    continue
                # touching: centre-line of one within the other's copper
                if a.kind == "seg" or b.kind == "seg":
                    s, o = (a, b) if a.kind == "seg" else (b, a)
                    if o.kind == "seg":
                        from mh_model import seg_seg_dist
                        d = seg_seg_dist(*s.g[:4], *o.g[:4]) - s.g[4] - o.g[4]
                    else:
                        d = o.dist_seg(*s.g[:4]) - s.g[4]
                else:
                    d = a.dist_pt(*(b.g[:2] if b.kind == "circ" else ((b.g[0] + b.g[2]) / 2, (b.g[1] + b.g[3]) / 2)))
                if d < 0.01:
                    union(i, j)
        groups = {}
        for i in range(n_el):
            groups.setdefault(find(i), []).append(i)
        comps = []
        for idxs in groups.values():
            nodes, pts, npads = {}, [], 0
            has_copper = any(i >= len(pads) for i in idxs)
            for i in idxs:
                if i < len(pads):
                    npads += 1
                    pts.append(pads[i]["c"])
                    if not has_copper:
                        for nd, v in self.pad_access(pads[i], net, STUB_MAX).items():
                            if nd not in nodes or nodes[nd][0] > v[0]:
                                nodes[nd] = v
                else:
                    pr = els[i]
                    if pr.kind == "seg":
                        x0, y0, x1, y1 = pr.g[:4]
                        L = math.hypot(x1 - x0, y1 - y0)
                        n = max(1, int(L / 0.05))
                        for k in range(n + 1):
                            x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
                            ix, iy = g.cell(x, y)
                            gx, gy = g.xy(ix, iy)
                            if 0 <= ix < g.W and 0 <= iy < g.H and math.hypot(gx - x, gy - y) < 0.06:
                                nodes[self.node(ix, iy, pr.layers[0])] = (0, None)
                        pts.append(((x0 + x1) / 2, (y0 + y1) / 2))
                    else:
                        ix, iy = g.cell(pr.g[0], pr.g[1])
                        for l in (F, B):
                            nodes[self.node(ix, iy, l)] = (0, None)
                        pts.append((pr.g[0], pr.g[1]))
            comps.append(dict(nodes=nodes, pts=pts, npads=npads))
        return comps

    # ------------------------------------------------------------------ search
    def search(self, net, sources, goals, soft, margin_cells, hw=None):
        """A* from `sources` ({node:(cost,poly)}) to any node in `goals` ({node:(cost,poly)}).
        Returns (path_nodes, src_poly, goal_poly, conflicts) or None."""
        g = self.g
        W, H = g.W, g.H
        if not sources or not goals:
            return None
        tier, vtier = self.tiers(net, hw)
        S0, S1 = tier.S
        D0, D1 = tier.D
        VS = vtier.S
        VD = vtier.D
        Sl = (S0, S1)
        Dl = (D0, D1)
        nopad = g.nopad
        viablk = g.viablk
        gl = {}
        for nd in goals:
            ix, iy, l = self.dec(nd)
            gl[nd] = (ix, iy)
        gx0 = min(v[0] for v in gl.values()); gx1 = max(v[0] for v in gl.values())
        gy0 = min(v[1] for v in gl.values()); gy1 = max(v[1] for v in gl.values())
        sxs = [self.dec(nd) for nd in sources]
        bx0 = max(0, min(min(s[0] for s in sxs), gx0) - margin_cells)
        bx1 = min(W - 1, max(max(s[0] for s in sxs), gx1) + margin_cells)
        by0 = max(0, min(min(s[1] for s in sxs), gy0) - margin_cells)
        by1 = min(H - 1, max(max(s[1] for s in sxs), gy1) + margin_cells)
        def hfun(ix, iy, l):
            dx = max(gx0 - ix, 0, ix - gx1)
            dy = max(gy0 - iy, 0, iy - gy1)
            h = (dx + dy) * STEP_COST
            # F moves only sideways, B only up/down: needing the other direction costs a via
            if (l == F and dy > 0) or (l == B and dx > 0):
                h += VIA_COST
            return h
        heap = []
        gcost = {}
        par = {}
        for nd, (c0, poly) in sources.items():
            ix, iy, l = self.dec(nd)
            idx = iy * W + ix
            s = Sl[l][idx]
            d = Dl[l][idx]
            if (s and s != net) or (d and d != net and not soft):
                continue
            gcost[nd] = c0
            par[nd] = None
            h = hfun(ix, iy, l)
            heapq.heappush(heap, (c0 + WEIGHT * h, c0, nd))
        self.stats["searches"] += 1
        limit = self.limit
        exp = 0
        found = None
        while heap:
            f, gc, nd = heapq.heappop(heap)
            if gcost.get(nd, 1e18) < gc:
                continue
            if nd in goals:
                found = nd
                break
            exp += 1
            if exp > limit:
                self.stats['limit_hits'] = self.stats.get('limit_hits', 0) + 1
                break
            i2, l = divmod(nd, 2)
            iy, ix = divmod(i2, W)
            # in-layer moves
            if l == F:
                nbrs = ((ix - 1, iy), (ix + 1, iy))
            else:
                nbrs = ((ix, iy - 1), (ix, iy + 1))
            for (jx, jy) in nbrs:
                if jx < bx0 or jx > bx1 or jy < by0 or jy > by1:
                    continue
                idx = jy * W + jx
                s = Sl[l][idx]
                if s and s != net:
                    continue
                d = Dl[l][idx]
                cost = STEP_COST
                if d and d != net:
                    if not soft:
                        continue
                    cost += CONFLICT_COST
                nn = idx * 2 + l
                ng = gc + cost
                if ng < gcost.get(nn, 1e18):
                    gcost[nn] = ng
                    par[nn] = nd
                    h = hfun(jx, jy, l)
                    heapq.heappush(heap, (ng + WEIGHT * h, ng, nn))
            # via (not within 6 steps of the previous via on this path: drill-to-drill 0.25)
            idx = i2
            near_via = False
            q = nd
            for _k in range(7):
                pq = par.get(q)
                if pq is None:
                    break
                if (pq & 1) != (q & 1):
                    near_via = True
                    break
                q = pq
            if not near_via and not nopad[idx] and not viablk[idx]:
                ol = 1 - l
                s0, s1 = VS[0][idx], VS[1][idx]
                if (not s0 or s0 == net) and (not s1 or s1 == net):
                    d0, d1 = VD[0][idx], VD[1][idx]
                    cost = VIA_COST
                    ok = True
                    for d in (d0, d1):
                        if d and d != net:
                            if soft:
                                cost += CONFLICT_COST
                            else:
                                ok = False
                    # the track-width tier must also be free on the other layer
                    s = Sl[ol][idx]
                    d = Dl[ol][idx]
                    if (s and s != net) or (d and d != net and not soft):
                        ok = False
                    if ok:
                        nn = idx * 2 + ol
                        ng = gc + cost
                        if ng < gcost.get(nn, 1e18):
                            gcost[nn] = ng
                            par[nn] = nd
                            h = hfun(ix, iy, ol)
                            heapq.heappush(heap, (ng + WEIGHT * h, ng, nn))
        self.stats["expanded"] += exp
        if found is None:
            return None
        path = []
        nd = found
        while nd is not None:
            path.append(nd)
            nd = par[nd]
        path.reverse()
        conflicts = set()

        def owners(t, l, i2):
            d = t.D[l][i2]
            if d and d != net:
                if d == MULTI:
                    conflicts.update(t.multi[l].get(i2, ()))
                else:
                    conflicts.add(d)
        prev = None
        for nd in path:
            i2, l = divmod(nd, 2)
            owners(tier, l, i2)
            if prev is not None and prev[1] != l and prev[0] == i2:
                # a via: its (larger) copper is checked in the via tier on both layers
                owners(vtier, 0, i2)
                owners(vtier, 1, i2)
            prev = (i2, l)
        conflicts.discard(net)
        return path, sources[path[0]][1], goals[found][1], conflicts

    # ------------------------------------------------------------------ commit / rip
    def commit(self, net, path, src_poly, goal_poly, width=None):
        info = self.m.nets[net]
        w = info["track"] if width is None else width
        recs = self.rec.setdefault(net, [])
        g = self.g

        def add_seg(l, x0, y0, x1, y1, width, stub):
            if math.hypot(x1 - x0, y1 - y0) < 1e-6:
                return
            self.iid += 1
            kclr = CLR_KEEPOFF if info["cls"] in ("CLK", "RF50") else CLR
            pr = Prim("seg", (x0, y0, x1, y1, width / 2), (l,), net, kclr, static=False, owner_item=self.iid)
            g.add_dyn(self.iid, pr)
            oid = self.obst.add(pr)
            recs.append(("seg", l, x0, y0, x1, y1, width, stub, self.iid, oid))

        def add_via(x, y):
            self.via_block(x, y, +1)
            self.iid += 1
            pr = Prim("circ", (x, y, info["via_dia"] / 2), (F, B), net, CLR, static=False, owner_item=self.iid)
            g.add_dyn(self.iid, pr)
            oid = self.obst.add(pr)
            recs.append(("via", x, y, info["via_dia"], info["via_drill"], self.iid, oid))

        first = self.dec(path[0])
        if src_poly:
            for a, c in zip(src_poly, src_poly[1:]):
                add_seg(first[2], a[0], a[1], c[0], c[1], STUB_W, True)
        # runs along the path
        k = 0
        n = len(path)
        while k < n:
            ix, iy, l = self.dec(path[k])
            j = k
            while j + 1 < n and self.dec(path[j + 1])[2] == l:
                j += 1
            ix2, iy2, _ = self.dec(path[j])
            x0, y0 = g.xy(ix, iy)
            x1, y1 = g.xy(ix2, iy2)
            add_seg(l, x0, y0, x1, y1, w, False)
            if j + 1 < n:
                add_via(x1, y1)
            k = j + 1
        if goal_poly:
            last = self.dec(path[-1])
            for a, c in zip(goal_poly, goal_poly[1:]):
                add_seg(last[2], a[0], a[1], c[0], c[1], STUB_W, True)

    def rip(self, net):
        for r in self.rec.pop(net, []):
            if r[0] == "seg":
                iid, oid = r[8], r[9]
            else:
                iid, oid = r[5], r[6]
                self.via_block(r[1], r[2], -1)
            self.g.remove_dyn(iid)
            self.obst.remove(oid)

    # ------------------------------------------------------------------ net routing
    def width_ladder(self, net):
        t = self.m.nets[net]["track"]
        return [t] + [x for x in (0.5, 0.3, 0.2) if x < t - 1e-9]

    def connect(self, net, comp, tree_nodes):
        """Join `comp` to the tree, trying the class width first and necking the
        track down (0.5, 0.3, 0.2 mm) if it will not fit.  Returns ('ok'|'ripped'|'fail', conflicts)."""
        for width in self.width_ladder(net):
            hw = width / 2
            for margin in (150, 100000):
                for _retry in range(25):
                    res = self.search(net, comp["nodes"], tree_nodes, True, margin, hw)
                    if res is None:
                        break
                    path, sp, gp, conf = res
                    l0 = self.dec(path[0])[2]
                    l1 = self.dec(path[-1])[2]
                    # pad stubs were cached against older copper: re-verify exactly
                    bad = False
                    if not self.stub_ok(net, LAYER_OF[l0], sp):
                        comp["nodes"].pop(path[0], None)
                        bad = True
                    if not self.stub_ok(net, LAYER_OF[l1], gp):
                        tree_nodes.pop(path[-1], None)
                        bad = True
                    if bad:
                        continue
                    if conf and any(self.rips.get(c, 0) >= MAX_RIPS for c in conf):
                        res = None
                        break
                    if not self.verify_runs(net, path, width, conf):
                        self.stats["verify_rejects"] = self.stats.get("verify_rejects", 0) + 1
                        break
                    for c in conf:
                        self.rips[c] = self.rips.get(c, 0) + 1
                        self.rip(c)
                    self.commit(net, path, sp, gp, width)
                    if width < self.m.nets[net]["track"] - 1e-9:
                        self.necked[net] = min(self.necked.get(net, 9), width)
                    return ("ripped" if conf else "ok"), conf
                if time.time() > self.deadline:
                    return "fail", set()
        return "fail", set()

    def route_net(self, net):
        comps = self.components(net)
        if len(comps) <= 1:
            self.failed.pop(net, None)
            return [], 0
        # tree = largest (most pads) component
        comps.sort(key=lambda c: (not c["nodes"], -c["npads"]))
        tree = dict(comps[0]["nodes"])
        tpts = list(comps[0]["pts"])
        rest = comps[1:]
        requeue = []
        left = 0
        while rest:
            cx = sum(p[0] for p in tpts) / len(tpts)
            cy = sum(p[1] for p in tpts) / len(tpts)
            rest.sort(key=lambda c: min(math.hypot(p[0] - cx, p[1] - cy) for p in c["pts"]))
            comp = rest.pop(0)
            if not comp["nodes"]:
                left += 1
                continue
            status, conf = self.connect(net, comp, tree)
            if status == "fail":
                left += 1
                continue
            requeue += list(conf)
            # grow the tree with everything this path/comp laid
            for r in self.rec.get(net, []):
                if r[0] == "seg":
                    _, l, x0, y0, x1, y1, *_ = r
                    L = math.hypot(x1 - x0, y1 - y0)
                    n = max(1, int(L / 0.05))
                    for k in range(n + 1):
                        x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
                        ix, iy = self.g.cell(x, y)
                        gx, gy = self.g.xy(ix, iy)
                        if math.hypot(gx - x, gy - y) < 0.06:
                            tree[self.node(ix, iy, l)] = (0, None)
                else:
                    ix, iy = self.g.cell(r[1], r[2])
                    tree[self.node(ix, iy, F)] = (0, None)
                    tree[self.node(ix, iy, B)] = (0, None)
            for nd, v in comp["nodes"].items():
                if v[1] is None:
                    tree[nd] = v
            tpts += comp["pts"]
        if left:
            self.failed[net] = left
        else:
            self.failed.pop(net, None)
        return requeue, left

    # ------------------------------------------------------------------ drivers
    def routable_nets(self):
        out = []
        for idx, info in self.m.nets.items():
            if info["name"] == "GND" or info["name"].startswith("unconnected-"):
                continue
            if info["cls"] in self.skip or len(info["pads"]) < 2:
                continue
            if self.only is not None and info["name"] not in self.only:
                continue
            out.append(idx)

        def hpwl(i):
            ps = self.m.nets[i]["pads"]
            xs = [p["c"][0] for p in ps]; ys = [p["c"][1] for p in ps]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))
        out.sort(key=lambda i: (CLASS_RANK.get(self.m.nets[i]["cls"], 9), hpwl(i)))
        return out

    def run(self):
        order = self.routable_nets()
        # initial connection count
        total_conn = 0
        for i in order:
            total_conn += max(0, len(self.components(i)) - 1)
        self.total_conn = total_conn
        self.skipped_open = {}
        for idx, info in self.m.nets.items():
            if info["cls"] in self.skip and len(info["pads"]) >= 2 and not info["name"].startswith("unconnected-"):
                k = len(self.components(idx)) - 1
                if k > 0:
                    self.skipped_open[info["name"]] = k
        self.log("nets to route: %d, connections: %d, grid %dx%d" % (len(order), total_conn, self.g.W, self.g.H))
        q = deque(order)
        done = 0
        t0 = time.time()
        while q and time.time() < self.deadline:
            net = q.popleft()
            requeue, left = self.route_net(net)
            for c in requeue:
                if c not in q:
                    q.append(c)
            done += 1
            if done % 25 == 0:
                self.log("  %d/%d nets processed, queue %d, %.0fs, failed so far %d" %
                         (done, len(order), len(q), time.time() - t0, len(self.failed)))
        # unrouted leftovers after timeout
        for net in q:
            self.failed.setdefault(net, 1)
        self.deadline = self.final_deadline
        if self.do_gnd:
            self.gnd_fanout()

    def gnd_fanout(self):
        gnd = [i for i, n in self.m.nets.items() if n["name"] == "GND"]
        if not gnd:
            return
        net = gnd[0]
        info = self.m.nets[net]
        vtier = self.g.tier(info["via_dia"] / 2)
        placed = failed = 0
        self.gnd_fail = []
        for pd in info["pads"]:
            if pd["th"] or time.time() > self.deadline:
                continue
            acc = self.pad_access(pd, net, GND_STUB_MAX)
            best = None
            for nd, (cost, poly) in acc.items():
                ix, iy, l = self.dec(nd)
                idx = iy * self.g.W + ix
                if self.g.nopad[idx] or self.g.viablk[idx]:
                    continue
                ok = True
                for ll in (F, B):
                    s, d = vtier.S[ll][idx], vtier.D[ll][idx]
                    if (s and s != net) or (d and d != net):
                        ok = False
                if ok and (best is None or cost < best[0]):
                    best = (cost, nd, poly)
            if best is None:
                failed += 1
                self.gnd_fail.append((pd["ref"], pd["num"]))
                continue
            cost, nd, poly = best
            ix, iy, l = self.dec(nd)
            x, y = self.g.xy(ix, iy)
            if not (self.stub_ok(net, LAYER_OF[l], poly) and
                    self.obst.seg_ok(net, F, x, y, x, y, info["via_dia"] / 2) and
                    self.obst.seg_ok(net, B, x, y, x, y, info["via_dia"] / 2)):
                failed += 1
                self.gnd_fail.append((pd["ref"], pd["num"]))
                continue
            self.commit(net, [nd], poly, None)
            self.iid += 1
            pr = Prim("circ", (x, y, info["via_dia"] / 2), (F, B), net, CLR, static=False, owner_item=self.iid)
            self.g.add_dyn(self.iid, pr)
            oid = self.obst.add(pr)
            self.rec[net].append(("via", x, y, info["via_dia"], info["via_drill"], self.iid, oid))
            self.via_block(x, y, +1)
            placed += 1
        self.log("GND fan-out: %d vias placed, %d pads without a site" % (placed, failed))

    # ------------------------------------------------------------------ output
    def write(self, board):
        nets = board.GetNetsByName()
        n_trk = n_via = 0
        for net, recs in self.rec.items():
            nm = self.m.nets[net]["name"]
            bn = U.get_net(board, nm)
            for r in recs:
                if r[0] == "seg":
                    _, l, x0, y0, x1, y1, w, stub, *_ = r
                    U.add_track(board, bn, LAYER_OF[l], x0, y0, x1, y1, w)
                    n_trk += 1
                else:
                    U.add_via(board, bn, r[1], r[2], r[3], r[4])
                    n_via += 1
        return n_trk, n_via

    def report(self):
        left = sum(self.failed.values())
        tc = max(1, getattr(self, "total_conn", 1))
        stub_len = 0.0
        stubs = 0
        tracks = vias = 0
        for net, recs in self.rec.items():
            for r in recs:
                if r[0] == "seg":
                    tracks += 1
                    if r[7]:
                        stubs += 1
                        stub_len += math.hypot(r[4] - r[2], r[5] - r[3])
                else:
                    vias += 1
        return dict(
            connections_total=tc, connections_unrouted=left,
            completion_pct=round(100.0 * (tc - left) / tc, 2),
            nets_failed=sorted(self.m.nets[n]["name"] for n in self.failed),
            nets_necked_down={self.m.nets[n]["name"]: w for n, w in sorted(self.necked.items())},
            tracks=tracks, vias=vias, stub_segments=stubs, stub_length_mm=round(stub_len, 1),
            gnd_pads_without_via=getattr(self, "gnd_fail", []),
            rip_ups=sum(self.rips.values()), astar_searches=self.stats["searches"],
            astar_expanded=self.stats["expanded"], astar_limit_hits=self.stats.get("limit_hits", 0), verify_rejects=self.stats.get("verify_rejects", 0),
            skipped_classes=sorted(self.skip), skipped_class_open_connections=getattr(self, "skipped_open", {}))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", required=True, help="PLACED board; use a scratch copy")
    ap.add_argument("--out", help="write here (default: overwrite --board)")
    ap.add_argument("--pitch", type=float, default=0.1)
    ap.add_argument("--seconds", type=float, default=900.0)
    ap.add_argument("--skip-class", action="append", default=None, help="netclass to leave alone (default RF50 and CLK: hand-first classes)")
    ap.add_argument("--no-gnd", action="store_true", help="skip the GND fan-out vias")
    ap.add_argument("--report", help="write the JSON report here")
    ap.add_argument("--only", action="append", help="route only this net (repeatable); for debugging")
    a = ap.parse_args()
    board = U.load_board(a.board)
    t0 = time.time()
    model = Model(board, a.pitch, skip_classes=tuple(a.skip_class or ["RF50", "CLK"]))
    print("model built in %.1fs" % (time.time() - t0), flush=True)
    r = Router(model, seconds=a.seconds, skip_classes=tuple(a.skip_class or ["RF50", "CLK"]), do_gnd=not a.no_gnd, only=a.only)
    r.run()
    ntrk, nvia = r.write(board)
    U.save_board(board, a.out or a.board)
    rep = r.report()
    rep["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(rep, indent=1))
    if a.report:
        with open(a.report, "w") as f:
            json.dump(rep, f, indent=1)


if __name__ == "__main__":
    main()
