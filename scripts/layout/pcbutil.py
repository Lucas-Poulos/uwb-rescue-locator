"""Shared helpers for the bay-station layout scripts (KiCad 10 pcbnew).

Run everything with KiCad's own python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
Only the standard library is used (no numpy in that interpreter).

Rules of the road, from kicad-pcbnew-headless-gotchas:
  * BOARD.Save() rewrites <project>.kicad_pro and wipes netclasses -> use
    save_board(), which restores the project file bytes.
  * Zones are NEVER filled in-process; fill a scratch copy with kicad-cli.
  * kicad-cli runs from a scratch dir, never inside the repo.
"""
import json
import math
import os
import shutil
import subprocess
import sys

import pcbnew

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

F_CU, IN1_CU, IN2_CU, B_CU = pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu
LAYER_NAME = {F_CU: "F.Cu", IN1_CU: "In1.Cu", IN2_CU: "In2.Cu", B_CU: "B.Cu"}


def mm(v):
    return pcbnew.ToMM(v)


def iu(v):
    return int(round(pcbnew.FromMM(v)))


def pt(x_mm, y_mm):
    return pcbnew.VECTOR2I(iu(x_mm), iu(y_mm))


def load_spec():
    with open(os.path.join(HERE, "hs_nets.json")) as f:
        return json.load(f)


def load_board(path):
    return pcbnew.LoadBoard(path)


def save_board(board, path):
    """Save and restore the .kicad_pro next to it (Save() wipes netclasses)."""
    pro = os.path.splitext(path)[0] + ".kicad_pro"
    before = open(pro, "rb").read() if os.path.exists(pro) else None
    board.Save(path)
    if before is not None:
        with open(pro, "wb") as f:
            f.write(before)


def scratch_copy(src_dir, dst_dir):
    """Copy the board + project files (+ lib tables) into dst_dir."""
    os.makedirs(dst_dir, exist_ok=True)
    for fn in os.listdir(src_dir):
        if fn.endswith((".kicad_pcb", ".kicad_pro", ".kicad_dru")) or fn in ("fp-lib-table", "sym-lib-table"):
            shutil.copy(os.path.join(src_dir, fn), os.path.join(dst_dir, fn))
    libs = os.path.join(src_dir, "libs")
    if os.path.isdir(libs) and not os.path.exists(os.path.join(dst_dir, "libs")):
        shutil.copytree(libs, os.path.join(dst_dir, "libs"))


def run_drc(pcb_path, out_json, refill=False, save_board_flag=False, extra=()):
    """kicad-cli pcb drc with --all-track-errors; cwd = the scratch dir of pcb_path."""
    cwd = os.path.dirname(os.path.abspath(pcb_path))
    cmd = [KICAD_CLI, "pcb", "drc", "--all-track-errors", "--format", "json",
           "--severity-all", "--units", "mm", "-o", out_json]
    if refill:
        cmd.append("--refill-zones")
    if save_board_flag:
        cmd.append("--save-board")
    cmd += list(extra) + [pcb_path]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r


def drc_summary(json_path):
    with open(json_path) as f:
        d = json.load(f)
    by = {}
    for v in d.get("violations", []):
        by.setdefault(v["type"], []).append(v)
    unconnected = d.get("unconnected_items", [])
    return by, unconnected, d


def netclass_of(board, net):
    return str(net.GetNetClassName())


def eff_class(item):
    """(track, clearance, via_dia, via_drill) in mm from the item's effective netclass."""
    nc = item.GetEffectiveNetClass()
    return (mm(nc.GetTrackWidth()), mm(nc.GetClearance()), mm(nc.GetViaDiameter()), mm(nc.GetViaDrill()))


def net_class_table(board):
    """{netname: classname} as KiCad's own matcher assigns them (the proof that the
    wildcard patterns hit)."""
    return {str(name): str(net.GetNetClassName()) for name, net in board.GetNetsByName().items()}


def board_outline(board):
    """Axis-aligned bbox (x0,y0,x1,y1) in mm of Edge.Cuts, or None.  Built from the
    shape end points (PCB_SHAPE.GetBoundingBox aborts headless: wx traits assert)."""
    xs, ys = [], []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.Type() == pcbnew.PCB_SHAPE_T:
            for q in (d.GetStart(), d.GetEnd()):
                xs.append(mm(q.x)); ys.append(mm(q.y))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _arc_points(d, n=12):
    """Polyline (start .. end) approximating an Edge.Cuts arc, in mm."""
    st, mid, en = d.GetStart(), d.GetArcMid(), d.GetEnd()
    ax, ay, mx, my, bx, by = mm(st.x), mm(st.y), mm(mid.x), mm(mid.y), mm(en.x), mm(en.y)
    dd = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    ux = ((ax**2 + ay**2) * (my - by) + (mx**2 + my**2) * (by - ay) + (bx**2 + by**2) * (ay - my)) / dd
    uy = ((ax**2 + ay**2) * (bx - mx) + (mx**2 + my**2) * (ax - bx) + (bx**2 + by**2) * (mx - ax)) / dd
    r = math.hypot(ax - ux, ay - uy)
    a0, am, a1 = math.atan2(ay - uy, ax - ux), math.atan2(my - uy, mx - ux), math.atan2(by - uy, bx - ux)
    def ccw(a, b):
        return (b - a) % (2 * math.pi)
    sweep = ccw(a0, a1) if ccw(a0, am) < ccw(a0, a1) else -ccw(a1, a0)
    pts = [(ux + r * math.cos(a0 + sweep * k / n), uy + r * math.sin(a0 + sweep * k / n)) for k in range(n + 1)]
    pts[0], pts[-1] = (ax, ay), (bx, by)
    return pts


def outline_polygon(board):
    """Board outline as a list of (x,y) mm: a rectangle, or Edge.Cuts lines AND arcs chained
    into a closed polygon (arcs sampled); falls back to the bbox rectangle."""
    segs = []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts or d.Type() != pcbnew.PCB_SHAPE_T:
            continue
        if d.GetShape() == pcbnew.SHAPE_T_RECT:
            x0, y0 = mm(d.GetStart().x), mm(d.GetStart().y)
            x1, y1 = mm(d.GetEnd().x), mm(d.GetEnd().y)
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        if d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            segs.append([(mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))])
        elif d.GetShape() == pcbnew.SHAPE_T_ARC:
            segs.append(_arc_points(d))
    if segs:
        pts = list(segs[0])
        rest = segs[1:]
        while rest:
            for i, s in enumerate(rest):
                if math.dist(s[0], pts[-1]) < 1e-3:
                    pts += s[1:]; rest.pop(i); break
                if math.dist(s[-1], pts[-1]) < 1e-3:
                    pts += s[::-1][1:]; rest.pop(i); break
            else:
                break
        if len(pts) > 3 and math.dist(pts[0], pts[-1]) < 1e-3 and not rest:
            return pts[:-1]
    bb = board_outline(board)
    if bb:
        x0, y0, x1, y1 = bb
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return None


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_pt_rect(px, py, x0, y0, x1, y1):
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def pad_info(pad):
    """Geometry of a pad as dict: layers, aabb (mm), center, shape kind, drill."""
    bb = pad.GetBoundingBox()
    c = pad.GetPosition()
    drill = pad.GetDrillSize()
    shape = pad.GetShape()
    kind = "circle" if shape == pcbnew.PAD_SHAPE_CIRCLE else "rect"
    return {
        "aabb": (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())),
        "c": (mm(c.x), mm(c.y)),
        "kind": kind,
        "drill": mm(max(drill.x, drill.y)) if pad.HasHole() else 0.0,
        "npth": pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
        "layers": [l for l in (F_CU, B_CU) if pad.IsOnLayer(l)],
    }


def seg_orientation(ax, ay, bx, by, tol=1e-4):
    """'H', 'V', 'D' (45 deg) or 'X' (other) for a segment in any unit."""
    dx, dy = abs(bx - ax), abs(by - ay)
    if dy < tol:
        return "H"
    if dx < tol:
        return "V"
    if abs(dx - dy) < max(tol, 1e-3 * max(dx, dy)):
        return "D"
    return "X"


def add_track(board, net, layer, x0, y0, x1, y1, width, locked=False):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pt(x0, y0)); t.SetEnd(pt(x1, y1))
    t.SetWidth(iu(width)); t.SetLayer(layer); t.SetNet(net)
    if locked:
        t.SetLocked(True)
    board.Add(t)
    return t


def add_arc(board, net, layer, start, mid, end, width, locked=False):
    a = pcbnew.PCB_ARC(board)
    a.SetStart(pt(*start)); a.SetMid(pt(*mid)); a.SetEnd(pt(*end))
    a.SetWidth(iu(width)); a.SetLayer(layer); a.SetNet(net)
    if locked:
        a.SetLocked(True)
    board.Add(a)
    return a


def add_via(board, net, x, y, dia, drill, locked=False):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(iu(dia)); v.SetDrill(iu(drill))
    v.SetLayerPair(F_CU, B_CU)
    v.SetNet(net)
    if locked:
        v.SetLocked(True)
    board.Add(v)
    return v


def get_net(board, name):
    n = board.FindNet(name)
    if n is None:
        raise KeyError(name)
    return n


def track_length_mm(items):
    tot = 0.0
    for t in items:
        tot += mm(t.GetLength())
    return tot
