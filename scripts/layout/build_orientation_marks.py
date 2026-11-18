#!/usr/bin/env python3
"""Generate the pinless silkscreen orientation-mark footprints in
bay-station/libs/bay_station.pretty (plain Python, no pcbnew needed).

Re-run to regenerate; output is deterministic.  Footprints written:

  OrientationMark_Axes_IIS2DLPC  - U11 accelerometer X/Y/Z glyph
  OrientationMark_Axes_IIS2MDC   - U10 magnetometer X/Y glyph (Z NOT drawn)
  OrientationMark_StationFrame   - station forward (FWD) arrow

All three are silkscreen-only, have no pads and no courtyard, and are
excluded from BOM and position files.  Local frame of the two sensor glyphs
is the sensor footprint at rotation 0 with KiCad's stock
Package_LGA:LGA-12_2x2mm_P0.5mm: pad 1 top-left, pads 1-4 down the left edge,
pads 1,12,11,10 along the top edge.  silkscreen.py places each glyph with the
SAME rotation as its sensor, so the arrows stay parallel to the real axes.

Axis sources (read from the rendered figures, not from memory):
  IIS2DLPC  ST DocID031788 Rev 4, Figure 2 (p.9), "TOP VIEW, direction of the
            detectable accelerations": pin-1 dot on the back corner, +X runs
            along the pin 1-4 edge (down in the footprint view), +Y along the
            pin 1-12-11-10 edge (right), +Z out of the top face.  Right-handed.
  IIS2MDC   ST DocID030986 Rev 1, Figure 2 (p.7), "TOP VIEW, direction of
            detectable magnetic fields": pin-1 dot on the back corner, +Y runs
            along the pin 1-4 edge (down), +X along the pin 1-12-11-10 edge
            (right).  As drawn the triad (X lower-right, Y lower-left, Z up)
            is LEFT-handed, so Z is deliberately not drawn: UNVERIFIED.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRETTY = os.path.normpath(os.path.join(HERE, "..", "..", "bay-station", "libs",
                                       "bay_station.pretty"))


def line(x1, y1, x2, y2, w=0.15, layer="F.SilkS"):
    return ("\t(fp_line\n\t\t(start %g %g)\n\t\t(end %g %g)\n\t\t(stroke\n\t\t\t(width %g)\n"
            "\t\t\t(type solid)\n\t\t)\n\t\t(layer \"%s\")\n\t)\n" % (x1, y1, x2, y2, w, layer))


def poly(pts, layer="F.SilkS", fill="solid", w=0.1):
    p = " ".join("(xy %g %g)" % q for q in pts)
    return ("\t(fp_poly\n\t\t(pts %s)\n\t\t(stroke\n\t\t\t(width %g)\n\t\t\t(type solid)\n\t\t)\n"
            "\t\t(fill %s)\n\t\t(layer \"%s\")\n\t)\n" % (p, w, fill, layer))


def circle(cx, cy, r, fill="none", w=0.15, layer="F.SilkS"):
    return ("\t(fp_circle\n\t\t(center %g %g)\n\t\t(end %g %g)\n\t\t(stroke\n\t\t\t(width %g)\n"
            "\t\t\t(type solid)\n\t\t)\n\t\t(fill %s)\n\t\t(layer \"%s\")\n\t)\n"
            % (cx, cy, cx + r, cy, w, fill, layer))


def text(s, x, y, size=1.0, th=0.15, layer="F.SilkS"):
    return ("\t(fp_text user \"%s\"\n\t\t(at %g %g)\n\t\t(layer \"%s\")\n\t\t(effects\n\t\t\t(font\n"
            "\t\t\t\t(size %g %g)\n\t\t\t\t(thickness %g)\n\t\t\t)\n\t\t)\n\t)\n"
            % (s, x, y, layer, size, size, th))


def arrow(x1, y1, x2, y2, head=1.1):
    """Shaft + two-stroke head from (x1,y1) to (x2,y2)."""
    import math
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    s = line(x1, y1, x2, y2)
    for sgn in (1, -1):
        s += line(x2, y2, x2 - ux * head + sgn * px * head * 0.55,
                  y2 - uy * head + sgn * py * head * 0.55)
    return s


def header(name, descr, tags, vsize_y):
    return ("(footprint \"%s\"\n\t(version 20240108)\n\t(generator \"uwb_rescue_locator_lib_builder\")\n"
            "\t(layer \"F.Cu\")\n\t(descr \"%s\")\n\t(tags \"%s\")\n"
            "\t(property \"Reference\" \"REF**\"\n\t\t(at 0 %g 0)\n\t\t(layer \"F.SilkS\")\n\t\t(hide yes)\n"
            "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n"
            "\t(property \"Value\" \"%s\"\n\t\t(at 0 %g 0)\n\t\t(layer \"F.Fab\")\n\t\t(hide yes)\n"
            "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n"
            "\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)\n"
            % (name, descr, tags, -vsize_y, name, vsize_y))


def axes_dlpc():
    name = "OrientationMark_Axes_IIS2DLPC"
    d = ("Silkscreen-only axes glyph for U11 IIS2DLPC. ST DocID031788 Rev 4 Figure 2 (p.9), TOP VIEW: "
         "pin-1 corner top-left in the footprint view, +X along the pin 1-4 edge (DOWN), +Y along the "
         "pin 1-12-11-10 edge (RIGHT), +Z out of the board (dot-in-circle). Place with the SAME rotation "
         "as U11 (silkscreen.py does). No pads, no courtyard, excluded from BOM/pos.")
    s = header(name, d, "orientation marker axes silkscreen IIS2DLPC", 4.2)
    ox, oy = -1.6, -1.6
    s += arrow(ox, oy, ox, oy + 3.4)          # X down
    s += arrow(ox, oy, ox + 3.4, oy)          # Y right
    s += circle(ox, oy, 0.7)                  # Z out of board
    s += circle(ox, oy, 0.25, fill="solid", w=0.1)
    s += text("X", ox, oy + 4.6)
    s += text("Y", ox + 4.7, oy)
    s += text("Z", ox - 1.5, oy - 1.0)
    s += text("U11", 0.5, 0.5)
    s += text("IIS2DLPC axes: DocID031788 Rev4 Fig2 (X down, Y right, Z out); place at U11 rotation", 0, 6.5,
              0.5, 0.08, "F.Fab")
    return name, s + ")\n"


def axes_mdc():
    name = "OrientationMark_Axes_IIS2MDC"
    d = ("Silkscreen-only axes glyph for U10 IIS2MDC, UNVERIFIED. ST DocID030986 Rev 1 Figure 2 (p.7), TOP VIEW: "
         "+Y along the pin 1-4 edge (DOWN in the footprint view), +X along the pin 1-12-11-10 edge (RIGHT). "
         "Z is NOT drawn: the figure's X lower-right / Y lower-left / Z up triad is left-handed, so the Z "
         "direction could not be established from it. Place with the SAME rotation as U10. No pads, "
         "no courtyard, excluded from BOM/pos.")
    s = header(name, d, "orientation marker axes silkscreen IIS2MDC", 4.2)
    ox, oy = -1.6, -1.6
    s += arrow(ox, oy, ox, oy + 3.4)          # Y down
    s += arrow(ox, oy, ox + 3.4, oy)          # X right
    s += circle(ox, oy, 0.25, fill="solid", w=0.1)
    s += text("Y", ox, oy + 4.6)
    s += text("X", ox + 4.7, oy)
    s += text("U10", 0.5, 0.5)
    s += text("IIS2MDC axes UNVERIFIED: DocID030986 Rev1 Fig2 top view (Y down, X right); Z not drawn", 0, 6.5,
              0.5, 0.08, "F.Fab")
    return name, s + ")\n"


def station_frame():
    name = "OrientationMark_StationFrame"
    d = ("Silkscreen-only station-frame marker: bold FWD arrow. docs/positioning.md (Mechanical) defines "
         "only that A0 is offset forward out of the A1-A3 plane; it defines no x/y/z or heading-zero "
         "convention and does not say which board edge faces forward, so the arrow direction is a "
         "placeholder set by silkscreen.py --fwd (default: toward the top of the board). No pads, no "
         "courtyard, excluded from BOM/pos.")
    s = header(name, d, "orientation marker station frame forward arrow silkscreen", 9.0)
    s += poly([(-0.6, 4), (0.6, 4), (0.6, -2.5), (-0.6, -2.5)])
    s += poly([(0, -7), (2.2, -2.5), (-2.2, -2.5)])
    s += text("STATION", 0, 6.0)
    s += text("FWD", 0, 7.4)
    s += text("Frame axes/heading zero NOT defined in docs/positioning.md; arrow direction is a placeholder",
              0, 9.0, 0.5, 0.08, "F.Fab")
    return name, s + ")\n"


def main():
    os.makedirs(PRETTY, exist_ok=True)
    for name, body in (axes_dlpc(), axes_mdc(), station_frame()):
        with open(os.path.join(PRETTY, name + ".kicad_mod"), "w") as f:
            f.write(body)
        print("wrote", name)


if __name__ == "__main__":
    main()
