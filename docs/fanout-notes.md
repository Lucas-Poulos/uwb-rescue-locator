# Pad fan-out (stage 2)

`scripts/layout/fanout.py` (KiCad python) runs after `place_bay_station.py`, before routing. Run:
`$KP scripts/layout/fanout.py [--board B] [--out O] [--report r.json] [--dump d.json]`; render with
system python: `fanout.py --render d.json out.png --crop X0 Y0 X1 Y1 --scale 60` (sheet mm).

## Rules

* Stub 0.2 mm, F.Cu (the pad layer; via-in-pad is forbidden, so the stub always starts on F.Cu), locked,
  on the pad net. Starts at the pad centre, runs outward along the pad's long axis (square pads: the axis
  they sit on), orthogonal, optionally one 45 degree jog and a straight leg after it. Total <= 2.0 mm
  (longest made: 1.08 mm). Ends in a locked 0.45/0.20 via, edge >= 0.10 mm from its own pad, >= 0.20 mm from
  any other pad.
* Clearance 0.16 mm (0.15 + 0.01) to other-net pads/tracks/vias, via centre to via centre >= 0.61 mm,
  0.51 mm to the board edge, outside the DW3210 4 x 4 keep-out and the 5.5 x 5.5 no-via cut-out of
  `stitch.py`, and outside a reserved corridor behind every RF50/CLK pad (neck 0.12 + 0.5, line 0.225 + 0.5,
  4 mm long) so no stub or via will violate the `.kicad_dru` keep-off.
* Two adjacent pads of one net may share a via (13 do).
* Layer for the continuation: the via is through. For pads that leave east/west the router continues on F.Cu
  (horizontal), for pads that leave north/south on B.Cu (vertical); the stub itself is always F.Cu.
* Search: per package side, 16 deterministic pad orders, best (most pads, then shortest) is kept. Idempotent:
  made items are listed in `fanout_manifest.json` beside the board and removed first (two runs: identical md5).

## Result (board df9c5a7 + place_testpads_bottom.py, scratch)

| IC | pads | fanned | notes |
|---|---|---|---|
| U4-U7 DW3210 | 40 each | 17,17,17,16 | skipped 17 each: RF-side VSS 12,14-17,19,20; RF1/RF2/XTI 13,18,21; XTO 22 (next to XTI, 0.5 keep-off); NC 3,4,6,7,8,31. Not fanned (0.4 mm pitch, geometry): 26/28/33/35/37/11 (A3: 11/23/27/29/33/35/37) |
| U20 nRF9151 | 113 | 60 | EP/inner large pads 105-113, LTE 35 / GNSS 42 and their neighbours 34,36,43, NC; 30 (GND) not fanned; inner 0.3 mm LGA pads are not reachable by any stub |
| U3 BT840 | 65 | 11 | castellated pads that are connected; the rest NC or interior |
| U10, U11 | 12 | 9, 11 | NC pads skipped |
| U2, U21, U22, U23, U24 | | 7, 5, 7, 5, 1 | U24: RF pins 3,5 and neighbours skipped |
| U1, U8, U40 | | 7, 3, 4 | power/GND pins skipped for the power agent (7+13...: 13 on U1, 3 on U8, 6 on U40) |
| U31 | 8 | 0 | CLK pins 1,3,5,7,8 skipped; pins 2,4,6 boxed in by the clock corridors |
| U30, J12 | | 0 | TCXO (clock tree); SIM socket pads are large contacts |
| Total | 468 | 197 | 184 vias, 152 mm of stub |

DRC (`--all-track-errors`, scratch): shorting 0, clearance 0, hole 0, courtyards 0, no new copper-edge or
silk items; the 184 `via_dangling` are the unrouted vias.

## Not done / for later stages

* No passive was moved: every blocked pad was limited by pad geometry or the RF corridors, not by a passive.
* U31 pins 2/4/6 (0.65 mm pitch between CLK pads) cannot take a 0.5 mm keep-off stub; they need the stage 4
  clock route (or the CLK keep-off relaxed next to the buffer). Left for the router.
* The dense DW3210 pins above and U20 pin 30 are left to `route_manhattan` (its own pad escapes).
