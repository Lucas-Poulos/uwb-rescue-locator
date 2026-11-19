# Bay station routing plan

Routing infrastructure for `bay-station/bay-station.kicad_pcb` (150 x 80 mm, 4 layers, placement done).
Everything is scripted and lives in `scripts/layout/`; the numbers come from `scripts/layout/stackup.py`
and the per-net inventory from `scripts/layout/hs_nets.json`, which also generates the project rules
(`scripts/layout/apply_rules.py`). Status: the hand-first high-speed stage and the stitch/rescue stage
were run on the real placement (section 8); the ordinary router, the power stage and the final HS
clean-up (`hs_finish.py`) are other agents' scripts and only their interfaces are described here.

User routing policy, as implemented:

1. Every high-speed signal that needs a solid ground reference is routed first, by script, on F.Cu
   over solid In1 (section 2), then locked.  The GND pads of the chips that carry those signals are
   tied BEFORE the clocks and host RF are laid (section 6), so those route around the ties.
2. Everything else is Manhattan: F.Cu horizontal, B.Cu vertical, vias only at direction changes, no
   45 degrees from the router (45 degrees or arcs only on the hand-first RF/clock lines and on pad
   stubs of at most 2.0 mm).
3. GND stitching vias across the whole board, a fence along RF lines (section 6).
4. The inner layers are the reference planes (section 1).

Order of work is one command, `scripts/layout/run_pipeline.py` (any python3; every stage runs in a
subprocess with KiCad's python on a COPY of the board, logs and a board md5 per stage, stops on the
first hard failure, `--stages`/`--skip`/`--silk`/`--keep-going`/`--in-place`):

```
python3 scripts/layout/run_pipeline.py --workdir /tmp/bay_pipe [--stages cutouts,fanout,...] [--seconds 900]
  cutouts   stitch.py --cutouts-only         DW3210 cut-out + tie rule areas, before anything is routed
  fanout    fanout.py                        stub + via for every non-HS pad
  testpads  place_testpads_bottom.py         test pads to the bottom side
  hs        route_hs_uwb.py all              RF x4 -> DW3210 GND ties -> host RF/TCXO -> UWB clocks -> other chips' ties
  power     route_power.py                   (skipped until the script has a CLI)
  hs_finish hs_finish.py                     (skipped until present: arcs, mask openings, fence)
  manhattan route_manhattan.py --jobs 6      ordinary nets
  stitch    stitch.py --zones --rescue auto  lattice, pours, GND pad ties
  fill, drc kicad-cli zone fill on a scratch copy, DRC --all-track-errors
  gates     check_gates.py --json
```

fanout runs before the test pads (its own doc says so, and the test-pad placer then keeps clear of
its vias).  Stages whose script is absent, or has no `__main__` yet, are skipped with a note.

## 1. Stackup, reference planes, impedance

### Stackup (as in the board file)

| Layer | Thickness | Role |
|---|---|---|
| F.Cu | 35 um | signal; RF50, CLK first, then horizontal ordinary tracks |
| prepreg | 254 um | |
| In1.Cu | 35 um | **GND**, solid except the cut-outs under each DW3210 body |
| core | 400 um | |
| In2.Cu | 35 um | **GND**, solid (Qorvo's "first solid ground") |
| prepreg | 254 um | |
| B.Cu | 35 um | signal, vertical ordinary tracks |

1.048 mm finished: DW3000 Datasheet v1.1 s7.3.2 Fig 35 (QFN stack-up). Material is
KiCad's default FR4, `epsilon_r` 4.5 / tan d 0.02; **that is not a datasheet or fab
value** (decisions.md says the same). 1.048 mm is also not a catalogue thickness:
the fab's own stackup governs and `stackup.py` has to be re-run with their numbers.

### Which inner layer is what

Both inner layers are GND. There is no power plane.

* Qorvo requires ground removed under the chip on Top and Inner Layer 1 and the
  first solid ground on Inner Layer 2 (DW3000 DS v1.1 s7.3, Fig 35). In1 is
  therefore solid GND everywhere *except* under each DW3210 body, and In2 is
  solid everywhere.
* F.Cu signals then see In1 (h = 0.254 mm) and B.Cu signals see In2 (h = 0.254 mm,
  the stackup is symmetric): every track, not just the RF lines, has an adjacent
  unbroken plane. A split In2 (GND + +3V3) would put every B.Cu crossing of the
  split over a gap; the power budget does not need it (largest steady load is
  +VSYS 0.75 A at 5 V / 1.2 A at a 3.0 V cell, `handoff/power.md`), so power
  is distributed as wide tracks and local pours on the outer layers
  (POWER_* classes, section 5). The cost is more outer-layer copper devoted to power.
* The v1.1 text in the local PDF says the first solid ground must be "at least
  0.45 mm away from the Top Layer"; the repo's 0.25 mm (decisions.md, bay-station
  note) comes from v1.3, which could not be re-read. In2 is 0.689 mm below the
  F.Cu surface (0.254 + 0.035 + 0.400), which satisfies either number.

### Reference plane of each high-speed net

| Net group | Reference | h (mm) | Note |
|---|---|---|---|
| RF1 -> SMA (x4), RF2 stubs | In1 | 0.254 | outside the cut-out. Inside the cut-out (only the pad escape, ~1 mm) the plane is In2, h = 0.689 mm, where 50 ohm would be 1.26 mm wide: that stretch is the DW3210 pad neck and is not 50 ohm (accepted, ~lambda/25). |
| LTE / GNSS RF (u.FL) | In1 | 0.254 | no cut-out nearby |
| UWB_CLK0-3, TCXO_OUT | In1 | 0.254 | none of them may cross a DW3210 cut-out except at the XTI pad |
| SPI, UART, SWD (FASTDIG) | In1 on F.Cu, In2 on B.Cu | 0.254 | keep out of the cut-outs |
| everything else | same | | |

Fig 35 in the datasheet itself shows the 50 ohm lines on the top layer over the solid
In1 copper with top-layer ground either side (coplanar clearance), so the
"RF line references In1 or In2" question resolves to In1 with the cut-out being
the only place In2 takes over.

### 50 ohm geometry

Method (all closed-form, none replaces the fab's impedance report):
Hammerstad and Jensen, "Accurate Models for Microstrip Computer-Aided Design",
IEEE MTT-S Digest 1980, with their thickness correction (Pozar, *Microwave
Engineering* 4th ed. s3.8; Wadell, *Transmission Line Design Handbook* 1991),
Getsinger/Edwards-Owens dispersion for er_eff at 6.4896 GHz; grounded coplanar
waveguide by conformal mapping (Simons, *Coplanar Waveguide Circuits, Components
and Systems*, 2001 s2.2). Run `python3 scripts/layout/stackup.py` to reprint.

50 ohm microstrip, t = 35 um:

| er | w over In1, h = 0.254 | w over In2, h = 0.689 | er_eff at 6.49 GHz |
|---|---|---|---|
| 3.9 | 0.498 mm | 1.401 mm | 3.02 |
| 4.2 | 0.471 | 1.325 | 3.21 |
| **4.5 (file)** | **0.446** | 1.258 | **3.40** |
| 4.6 | 0.439 | 1.237 | 3.47 |

**Adopted: 0.45 mm** (RF50 and CLK classes). The repo's earlier "~0.45 mm" estimate
(uwb_array_notes.md) agrees.

Sensitivity at w = 0.45: er 3.9 -> 53.2 ohm, 4.2 -> 51.5, 4.8 -> 48.6; width
-/+0.03 mm -> 52.0 / 48.2 ohm. Dispersion moves Z0 by 0.1 ohm at 6.49 GHz, so it
is not the issue; the dielectric constant is.

**Dk at 6.5 GHz differs from the file's 4.5.** FR4 laminates quote Dk at 1 GHz or
below and Dk drifts down with frequency; prepreg with high resin content is lower
than core. I did not find, and did not look up, a datasheet for the fab's prepreg,
so the plausible window used here (3.9-4.6, roughly +/-2.5 ohm at fixed width) is a
judgement, not a cited number. Solder mask over the line lowers Z0 by 1-2 ohm more
(not modelled). Action: ask the fab for the exact prepreg Dk/thickness for a
1.048 mm 4-layer stack and re-run `stackup.py`; the width in `hs_nets.json` and
`RF_W` in `route_hs.py` are the only places to change.

Coplanar with ground (top pour beside the line, In1 below), er 4.5:

| gap to pour | width for 50 ohm |
|---|---|
| 0.20 mm | 0.300 mm |
| 0.30 | 0.356 |
| 0.50 | 0.397 |

With w = 0.45 and a top pour at gap 0.3 / 0.5 / 0.75 mm / none, Z0 = 44.4 / 46.8 /
48.1 / 49.8 ohm. So the line is a **microstrip** by design and the pour must stay
**0.5 mm or more** from it (the `.kicad_dru` keep-off; Z0 ends up 47-50 ohm
where the pour is close). Do not shrink the gap without changing the width.

**Trace-to-ground gap rules:** pour/via/foreign copper 0.5 mm from RF50 and CLK
tracks (`.kicad_dru`); GND fence via centre 0.96 mm from the line centre (0.225 line
half-width + 0.5 keep-off + 0.225 via radius + 0.01); RF to other tracks at least 0.5 mm
(about 2h). The DW3210 pads (0.25 mm on 0.4 mm pitch, 0.15 mm gap) force a 0.24 mm
neck on RF1, RF2 and XTI, continuing 0.32 mm past the pad end before widening to
0.45 mm. A wider line touches the GND neighbours: on the fixture the first attempt (0.2
mm past the pad) measured 0.14 mm to pads 17/19 because the round end cap of the wide
section sits closer than its edge; 0.32 mm clears 0.15 mm.

### SMA launch (not solved)

The CONSMA020.042-G footprint is a **PLACEHOLDER**: the centre pad is drawn 1.52 x
5.08 mm from Linx DS21264 Fig 2, 3.4x the 0.45 mm line, with two GND pads 4.24 mm
off-axis on both layers. At 6.49 GHz (lambda_g 25 mm) a 1.5 mm step plus the pad's
edge-launch field is not negligible. A tapered launch and a ground cut-back
under the pad need an EM simulation (e.g. openEMS or a field solver; not
available on this machine and not attempted). Nothing in this repo claims that
launch is 50 ohm. The router treats the pad as a plain target; `route_hs` routes
into the pad centre at 0.45 mm.

### Via fence pitch

lambda_g(6.4896 GHz) in the actual line = c/(f sqrt(er_eff)) = 25.04 mm with
er_eff 3.40; lambda/10 = 2.50 mm, lambda/20 = 1.25 mm. Adopted fence pitch
**1.5 mm** (lambda/16.7), via 0.45/0.20. `route_hs.via_fence` asserts pitch <
lambda/10 from `stackup.py` every time it runs. Delay: 6.15 ps/mm (1 cm = 61.5 ps),
which is what the length-matching tolerances below are quoted against.

## 2. High-speed net inventory

Source of truth: `scripts/layout/hs_nets.json` (patterns, widths, classes, match
groups with citations). Summary:

| Tier | Group | Class | Width | Reference | Length match |
|---|---|---|---|---|---|
| **hand first** | RF1 -> C47 2 pF -> R220 0R -> SMA, x4; RF2 stub to 49R9 x4 | RF50 | 0.45 (0.24 neck) | In1 | **RF_PATH** x4, +/-0.5 mm (3.1 ps) |
| hand first | LTE ANT -> pi -> J10 u.FL; GNSS pin -> pi -> BGA524N6 -> J11 u.FL | RF50 | 0.45 | In1 | no |
| hand first | CLK_Yn -> R231-234 -> CLK_Tn -> C24-27 -> UWB_CLKn (buffer to XTI) x4 | CLK | 0.45 | In1 | **CLK_PATH** x4, +/-0.5 mm (3.1 ps) |
| hand first | TCXO_OUT, TCXO_RF (TCXO -> buffer) | CLK | 0.45 | In1 | no (common to all four) |
| ordinary, fast | SPI bus (SCK/MOSI/MISO shared; CSn, IRQn per anchor) | FASTDIG | 0.2 | In1/In2 | not required (+/-10 mm hygiene) |
| ordinary, fast | BLE bridge UART (TXD/RXD/RTS/CTS/IRQ) | FASTDIG | 0.2 | In1/In2 | no |
| ordinary, fast | SWDIO/SWDCLK x2, debug UART | FASTDIG | 0.2 | In1/In2 | no |
| ordinary | I2C_SCL/SDA, interrupts, LEDs, straps | Default | 0.2 | In1/In2 | no |
| power | +5V_IN, +VSYS, VBATT_PROT, BATT_RAW, BARREL_VIN, SW_3V3, L1/L2_LTE | POWER_HI | 1.0 | | no |
| power | +3V3, +VBAT_LTE, regulator outputs, NRF_VDD | POWER_MID | 0.5 | | no |
| power | +3V3_A0-A3, +3V3_TCXO, +3V3_CLKBUF, +3V3_SNS, LNA VCC, NRF_VDD_GPIO | POWER_LO | 0.3 | | no |

Tolerances and where they come from:

* **RF_PATH +/-0.5 mm.** positioning.md: 1 cm of differential path = 10 cm of position
  error at 10 m, and the outer-anchor relative delays must be calibrated to ~1 cm
  (~33 ps); uwb_array_notes.md "Length matching" 1: same geometry, same length, same
  via count (0), same orientation on all four. 0.5 mm = 3.1 ps = about 10 % of the
  33 ps. That ratio is my choice, not a datasheet value. The fixed part calibrates
  out; only drift matters, which is why identical geometry matters more than the number.
* **CLK_PATH +/-0.5 mm.** clock_dist_notes.md "Layout": equal length, same layer, same via
  count, away from SPI and RF; the buffer's own 25/50 ps skew (TI SNAS791D) is fixed
  and calibrates out.  **Counting rule** (route_hs_uwb.py and check_gates.py use the same one): the
  length of anchor n is the sum of the track lengths of its three chain nets (CLK_Yn + CLK_Tn +
  UWB_CLKn), buffer pin centre to XTI pad centre, series R and C pads count as zero, and every
  **dead-end spur counts 1:1**.  The spurs are the other pads on UWB_CLKn: on A0 the unfitted R403
  link pad and the DNP crystal option Y1 / C209 (1-3 mm of copper each in the placement, routed
  as an MST onto the chain); A1-A3 have none (R404-R406 were removed).  Lumped-capacitance
  estimate behind the 1:1 choice: 50 ohm line = 0.123 pF/mm, so a spur seen by the 50 + 22 ohm
  source delays the edge by about 72 ohm x 0.123 pF = 8.9 ps/mm against 6.15 ps/mm of line, i.e.
  1:1 is within 1.5x of the physical term and errs toward a longer A0 path.  It is an estimate,
  not a simulation; the residual is a fixed A0 offset that the calibration absorbs.
* **SPI.** connectivity_notes.md s2: SPIM3 8 MHz is the limit; DW3000 DS v1.1 Table 19:
  t3 setup 14 ns, t4 hold 2 ns, t2 8.5 ns against a 125 ns period. The tightest skew
  limit (2 ns hold) is ~330 mm of trace, so matching is not required.
* **UART** 1 Mbaud (decisions.md, system-overview.md), 1 us bit time: no matching.
* **SWD/SWO.** SWO is not connected anywhere (no SWO net in net-contract.md s6;
  programming_debug_notes.md). Nothing to route.
* **GNSS/LTE.** connectivity_notes.md: GNSS line loss <= 0.5 dB; LTE matching close to the
  antenna. The LNA input path (GNSS_ANT, GNSS_LNA_IN_DC, GNSS_LNA_AI) is the
  noise-critical segment: keep it the shortest.
* **Why the clock is 50 ohm at all.** 38.4 MHz is electrically short (lambda ~ 5 m). The
  LMK1C1104 and RPT1490LN edges are 1-2 ns, critical length ~ tr/(6 x 6.15 ps/mm)
  ~ 27 mm, and the runs are 15-60 mm, so source-terminated 50 ohm is the safe
  choice; equal length is for thermal skew stability, not reflections.

Power widths (IPC-2221A s6.2, external 35 um, dT = 10 C; IPC-2152 is less
conservative; `stackup.ipc2221_width_mm`): 0.5 A -> 0.12 mm, 1.2 A -> 0.39, 1.8 A -> 0.68,
3.4 A -> 1.62 mm. Currents from `handoff/power.md` (+3V3 ~356 mA peak, +VBAT_LTE 505 mA,
+VSYS 1.2 A, MCP73871 input limit 1.8 A, inductor peak 3.4 A on the switch node).
POWER_HI is 1.0 mm (about 2.4 A at 10 C) and the switch-node nets (SW_3V3, L1/L2_LTE)
are in it: keep them short and stub-free (regulation_notes.md). Pad escapes on power
nets are 0.2 mm for at most 2 mm (router) -- noted, not hidden.

## 3. Rules adopted

Fab: the repo names no fab, so **JLCPCB 4-layer standard** is assumed
(`~/.claude/skills/jlcpcb/SKILL.md`, "PCB Design Rules": multi-layer min trace/space
0.09 mm, min via 0.25 mm pad / 0.15 mm drill; 1-2 layer annular ring 0.125 mm). These
were not re-checked against jlcpcb.com. Adopted, with margin:

| Item | Value | Why |
|---|---|---|
| min track / space | 0.15 / 0.15 mm | decisions.md: DW3210 pad gap is exactly 0.15 mm; fab minimum is 0.09 |
| default track | 0.2 mm | |
| via (signal) | 0.6 / 0.3 mm | existing Default class |
| via (stitch, fence) | 0.45 / 0.20 mm | annular ring 0.125 mm = JLC stated ring; above their 0.25/0.15 minimum |
| min hole to hole | 0.25 mm | |
| copper to edge | 0.5 mm | unchanged; the SMA edge-mount pads sit on the edge and will need a rule exception once the footprint is real |

Netclasses written into `bay-station.kicad_pro` by `apply_rules.py` (edits the JSON,
keeps every other key; the file round-trips unchanged through `json.dumps(indent=2)`):

| Class | Track | Clearance | Via | Patterns |
|---|---|---|---|---|
| Default | 0.2 | 0.15 | 0.6/0.3 | everything else |
| RF50 | 0.45 | 0.15 (0.5 via .kicad_dru) | 0.6/0.3 | 15 |
| CLK | 0.45 | 0.15 (0.5 via .kicad_dru) | 0.6/0.3 | 5 |
| FASTDIG | 0.2 | 0.15 | 0.6/0.3 | 26 |
| POWER_HI | 1.0 | 0.15 | 0.8/0.4 | 8 |
| POWER_MID | 0.5 | 0.15 | 0.6/0.3 | 5 |
| POWER_LO | 0.3 | 0.15 | 0.6/0.3 | 6 |

Netclass clearance is 0.15 mm in every class because the clearance of an item pair is
the larger of the two classes and the DW3210 pad pitch forbids anything larger at the
pads; the larger spacing is a conditioned `.kicad_dru` rule.

**Patterns are wildcards matched against the full net name**, which for sheet-local nets
carries the sheet path with a space (`/UWB Array/A0_RF1`, `/Clock Distribution/CLK_T0`),
hence the leading `*`. `check_gates.py` proves them with KiCad's own matcher:
`GetNetClassName()` on the loaded board agrees with the intended class for all 339
nets (98 in non-Default classes, no pattern dead). See also
kicad-netclass-patterns-are-wildcards (memory note).

`bay-station.kicad_dru` (generated, every rule conditioned; an unconditioned clearance
rule would override all netclasses):

* RF50 track/via/zone to foreign track/via/zone: 0.5 mm (never pad-to-pad).
* RF50 track width window 0.2 (neck) to 0.5 mm.
* RF50 carries no vias.
* CLK track to foreign track/via/zone: 0.5 mm (CLK next to CLK exempt, 0.15).
* **GND pad-tie exception (last rule):** a GND *track* may sit 0.15 mm (the netclass clearance) from an
  RF50/CLK track when it touches a tie rule area; vias, pours and every other net keep 0.5 mm.
  Source: `hs_nets.json` `gnd_tie_exception`, written by `apply_rules.py`, verified by `check_gates.py`.
  Justification and scope: section 6.
* No POWER_* minimum-width rule: KiCad 10.0.5 reported a custom rule marked `(severity warning)`
  as an error, and the router's 0.2 mm power-pad stubs are deliberate, so `check_gates.py`
  audits power-class track widths (INFO) instead.

All four rule types were exercised: a deliberate violation of the no-via and keep-off
rules on the fixture produced exactly those `items_not_allowed` / `clearance` errors.

## 4. `route_hs.py` and `route_hs_uwb.py` (hand-first stage)

`route_hs.py` is the library: `microstrip_path` (chamfer 45 degree or arc bends), `route_pads`
(orthogonal candidates shortest first: straight, L, Z, swept U, each tested against pads, tracks,
vias and track-forbidding rule areas, then an A* fallback; automatic neck at pads narrower than the
line), `via_fence` (never inside a via-forbidding rule area), `meander_points`/`match_group`
(accordion with 3 x width gap between legs, meanders spread over the straight legs, detour hop
when the shortfall is large), `lock`.  GND tracks inside a tie area (section 6) are checked at the
0.15 mm of the .kicad_dru exception, everything else at 0.5 mm.

`route_hs_uwb.py` is the bay-station stage.  It uses no coordinates and no board size, only the
netlist, footprint geometry and `hs_nets.json`; every hop that cannot be routed is reported
(exit code 2) instead of aborting:

1. `rf`: the four DW3210 chains RF1 -> C -> R -> SMA (+ RF2 stub), identical geometry, no vias; then
   every DNP pad on those nets (pi-network shunts) as a short spur; then the GND fence.
2. `ties`: all GND pads of the DW3210s (stub + via outside the cut-out, `stitch.py` section 6).
   Done before the clocks and host RF, which then route around them.
3. `host`: every other RF50/CLK net (LTE, GNSS, TCXO): minimum spanning tree over the F.Cu pads,
   phase 1 populated pads (noise-critical GNSS input first), phase 2 DNP pads as spurs so an unfitted
   part never walls in a populated path; width ladder 0.45 -> 0.24 mm when a 0.4 mm pitch pad forces
   it (the relaxed rows break the 0.5 mm keep-off and are printed); fence on RF50.
4. `clocks`: UWB_CLK0-3 with `match_group`, spurs counted (section 2).
5. `ties2`: GND pads of the other HS chips (LNA, nRF9151 RF pins) after their RF lanes exist.

Greedy: no topology search; the first clean candidate wins.  GNSS_LNA_AO (R123.1 to U24.3) crossed
GNSS_LNA_IN_DC in the earlier placement and needed a via bridge, which the `RF50 carries no vias`
rule forbids.  In the current placement the two nets do not cross and AO routes as a 4.9 mm
0.24 mm line; if a later placement makes them cross again the stage reports the hop and the fix is a
placement change (put R123 on the U24 side of the IN_DC line), not a via on an RF50 net.


## 5. `route_manhattan.py` (ordinary nets)

See the module docstring for the method, and section 8 for what it achieved. In short:
A* on a 0.1 mm grid, F.Cu horizontal / B.Cu vertical, via only at direction changes,
per-class widths and the via sizes from the netclass, locked copper as obstacle,
rip-up and retry (<= 3 rips per net), nets in classes named by `--skip-class` (default
RF50) left alone. It does not do GND (see `gnd_fanout`: a via to the planes within 3 mm
of every SMD GND pad), differential pairs, length matching or 45 degree bends.

Details that matter: a path is checked exactly (distance to every pad, track, via, hole,
fiducial clearance override, footprint keep-out) before it is committed and rejected if the
raster let something through; vias keep 0.7 mm centre to centre (drill to drill 0.25); a
connection that will not fit at the class width is retried necked down to 0.5, 0.3, 0.2 mm
(reported as `nets_necked_down`); RF50 and CLK nets are skipped (hand-first; their DNP-shunt and
test-pad leftovers are listed as `skipped_class_open_connections`). The DW3210 cut-out rule
areas must exist **before** the router runs, otherwise its vias land in them.

Policy exceptions it makes, all listed in its report and accepted by
`check_gates.py`: pad escape stubs (0.2 mm wide, at most 2 mm, any orthogonal direction)
and GND stubs (at most 3 mm). Fine-pitch pads cannot take a horizontal track from every
side, and pad centres are off the 0.1 mm grid.

## 6. Stitching, zones and GND pad ties (`stitch.py`)

**Lattice** (sized from the Edge.Cuts polygon, any outline incl. arcs; verified on the 150 x 80 mm
board): general lattice pitch <= 5.0 mm, evenly spread over the outline minus 2 mm (n = ceil(span/5),
so no 4.9 mm leftover row); dense lattice <= 2.5 mm within 4 mm of RF50/CLK copper (lambda_g/10 at
6.49 GHz is 2.5 mm); edge ring 2.5 mm pitch, 1.0 mm inset.  Plane-stitching rule of thumb pitch
<= lambda_g/20 would be 3.7 mm at LTE 2.2 GHz, so 5 mm is a compromise, not a derivation that closes.
A candidate within 0.4 x pitch of an existing GND via counts as stitched (a second run adds almost
nothing).  Skips: pads (0.25 mm edge to via edge), TestPoint pads (0.6 mm: pogo probe tip and guide),
tracks (0.15; 0.5 to RF50/CLK), other vias and holes (drill edge to drill edge >= the hole-to-hole
rule, 0.25 mm, `hs_nets.json` fab block), the board edge, keep-out rule areas including footprint
ones, and the 5.5 x 5.5 mm square under each DW3210 (no vias: DS v1.1 Fig 35).  Zones: GND on In1,
In2, F.Cu, B.Cu (outer pours drop every island that is not connected), rule areas under each DW3210
(no pour on F.Cu/In1, no vias).  Never filled in process: `kicad-cli pcb drc --refill-zones` on a
scratch copy fills with the `.kicad_dru` applied.

**GND pad ties** (`--rescue auto`; the same engine is called by `route_hs_uwb.py ties`).  Why they
are needed: the 0.5 mm RF50 keep-off and the no-via cut-out leave the DW3210 RF-side VSS pins (12,
14-17, 19, 20) and some pads beside RF pins with no route to a pour or a stitch via (70 isolated
GND pads on the first routed board).  Method: a Dijkstra search on the pad's own layer (0.05 mm
grid, 0.2 mm stub, orthogonal and 45 degree steps, bend penalty) to the nearest of an existing GND
via, an earlier tie stub, or a new legal via site; chain length pad centre to via <= 2.0 mm (the
direction-policy stub limit).  Vias are never inside the DW3210 cut-out, so a DW3210 pad reaches
out past the 5.5 mm square, and In1 under the body stays cleared while In2 is the first solid
ground (DW3000 DS v1.1 s7.3, Fig 35; positioning.md "Required passives and layout").  `auto`
finds the isolated pads itself: kicad-cli fills a scratch copy, the unconnected GND items name
them, two passes.

**The one rule exception.**  A GND stub leaving such a pad is inside the 0.5 mm RF keep-off by
construction: the DW3210 pads are 0.25 mm on 0.4 mm pitch, the GND pads sit 0.15 mm from the RF1/RF2
pads, and the 0.24 mm neck continues straight out between them.  The `.kicad_dru` therefore relaxes
GND *track* to RF50/CLK *track* clearance from 0.5 to the netclass 0.15 mm, only where the GND track
touches a rule area that forbids nothing: `DW3210_TIE_n` (cut-out + 2 mm per side) or `HS_TIE_k` (3 mm
square round an RF/CLK pad of a fine-pitch non-DW3210 chip: nRF9151 LGA RF pins, BGA524N6).  Within
that stretch the line is a pad neck over the cleared In1 (In2 at h = 0.689 mm is the reference),
which is not 50 ohm anyway (a 0.24 mm neck over In2 is about 100 ohm); GND copper beside it lowers
Z0 toward 50 ohm, as the chip's own GND pads do.  Evidence: on the first routed board the same
filled board gave 25 `clearance` errors without the rule and 0 with it.  Not simulated; the width of
the stretch is at most ~1.5 mm (lambda_g/16 at 6.49 GHz).  Vias, pours and other nets keep 0.5 mm.
Optional tiers, off by default and flagged: `--tented` (tie via 0.15 mm instead of 0.25 mm from a
foreign pad, valid only if vias are tented) and `--via-in-pad` (a via ON a pad whose short side is
>= 0.65 mm, needs filled/capped vias at the fab; check_gates flags every via-in-pad).  The
only pads that qualified on the first board were C102.2 and C401.2; with ties first they got stubs
instead, so neither tier is used.

**BT840 U3.F0-F3 (decision needed).**  The four 1.5 x 1.5 mm GND pads sit inside `KO_BT840_antenna`,
which forbids tracks, vias and pours on all layers (pads allowed), so no tie is possible and they are
the one structural leftover.  Fanstel's datasheet was not re-read here (p.16 is cited by the silk
notes).  Options: (a) read the datasheet: if those pads are NC or only mechanical, drop the net from
them; (b) if they must be GND, shrink the rule area at its inner edge so the pads fall outside and tie
them like any chip pad (the antenna region proper starts beyond the pad row); (c) keep the keep-out
and tie the module GND through its other GND castellations only.  Recommendation: (a) first, then (b).

## 7. `check_gates.py`

Runs on a scratch copy of any board (`--board`, `--json out.json`, `--workdir` outside the repo).
HARD (exit 1): netclasses present and equal to `hs_nets.json`; each net's class equals the
intended one by KiCad's matcher; no dead pattern; classes survive `pcbutil.save_board()`;
`.kicad_dru` parses and carries the GND-tie exception; DRC (`--all-track-errors --refill-zones`)
has no short/clearance/width/via/hole violations; **every GND pad tied** (unconnected GND items
after the fill = 0); direction policy, strict: F.Cu horizontal, B.Cu vertical, except RF50/CLK/locked
copper and stub chains (same-net segments joined end to end, <= 2.0 mm in total from a pad).
WARN: thin POWER_* copper (< 0.3 mm), via-in-pad, courtyard gap < 0.6 mm (bounding-box test).
INFO: unrouted count, violations by type, RF_PATH / CLK_PATH spread against `hs_nets.json`, RF50
fence coverage (share of RF50 copper with a GND via within 2.5 mm); `hs_finish.gates(board, results)`
is called if that module provides it (mask opening over GHz copper).  `--require-complete`, `--strict`.

## 8. What was tested, and how good it is

### Real placement (150 x 80 mm, 2026-11-18), `run_pipeline.py`, router budget 150 s

Stages run: cutouts, fanout, testpads, hs, manhattan, stitch, fill, drc, gates (power and hs_finish
skipped: no CLI yet).  Numbers:

* RF: four chains, 7.042-7.043 mm (RF1 pad to SMA centre), identical geometry, no vias, DNP
  pi-network pads as spurs, fence.  DRC clean.
* Clocks: A0 55.354, A1 55.354, A2 55.354, A3 55.832 mm, spread 0.478 mm against 0.5 (A0 counts its
  R403 / Y1 / C209 spurs; pre-tune lengths were 55.35 / 38.61 / 48.68 / 37.16).  The meander
  overshoot on A3 is the limit of the tuner (it stops within 0.05 mm of its target per leg, then
  the last meander can overshoot); a tighter spread needs a finer final meander.
* GND ties: all 56 DW3210 GND pads tied (32 when fanout has already tied the others), 0 without a
  site; 30 pads of other HS chips tied, 2 DNP caps beside RF pins left (C124.2, C125.2).
* Hand-first HS hops: all routed, GNSS_LNA_AO included.  LTE/GNSS hops at 0.24 mm width where the
  0.4 mm pitch pads force it (listed in the log).
* Stitch on the 150 x 80 outline: 772 vias (377 general, 226 near RF, 169 edge); after the fill 7
  isolated GND pads / 11 unconnected GND items remain: U3.F3 (BT840, section 6), C124.2, C125.2,
  C61.2, TP116.1, U1.4, U40.3, U40.8 and 2 zone fragments.  The fragments are GND_TOP pieces that
  KiCad's island removal keeps but no via reaches (the earlier board: 5 such pieces between dense
  pads); outer-layer pours are optional, and removing GND_TOP/GND_BOT removes them.
* Router (not mine): 168 of 418 connections unrouted at 150 s, 59.8 % complete.
* Remaining DRC at that point: hole_to_hole 2 (a fan-out via against J32 pin 10), track_dangling 2,
  plus placement items (courtyards, silk, copper-to-edge).  Gates: direction policy fails with 302
  ordinary-net segments (ESIM_VCC and others from the router/fan-out, not from the HS stage), GND
  tied fails (above), DRC hole_to_hole fails.  Warnings: thin power copper on 22 nets (0.2 mm stubs),
  courtyard gap < 0.6 mm on 69 pairs.

### Earlier fixture and first routed board (history, router figures)

Fixture: `make_test_board.py` (118 x 151 mm, all 428 footprints, courtyard fill ~24 %, sparser than a
real board).  On the first real board (128 x 68 mm, commits 7b940de / 68852d4) the old GND rescue
tied 4 pads and left 70 isolated; the stitch/rescue rework above ties 42 of them after the fact (28
boxed in by the clock and RF routing, which is why the ties now come first).  Manhattan router on the
fixture: 197 routable nets, 480 connections, 72-74 % completed in 600 s, 944 vias, 0 shorts and 0
direction violations; see section 5 for the method and its weaknesses (pad escape is the bottleneck,
the H/V rule costs vias, rip-up is shallow).  Those figures are for that fixture only.

## 9. Uncertainties and things not done

* **Dk 4.5** is KiCad's FR4 default, not a datasheet or fab value; at 6.5 GHz the real laminate is
  probably 3.9-4.6 (about +/-2.5 ohm at fixed width).  All widths follow from it: re-run `stackup.py`
  with the fab's numbers (hs_finish.py owns that file now) and change `hs_nets.json` / `RF_W`.
* **1.048 mm** (Fig 35 stackup) is not an orderable thickness; the fab's own stackup governs.
* **SMA launch is unsimulated**: the CONSMA020.042-G footprint is a placeholder (1.52 mm centre pad);
  a tapered launch needs an EM solver, none available here.
* The GND-tie exception (0.15 mm GND stub beside an RF neck inside DW3210_TIE_n / HS_TIE_k) is
  argued, not simulated.  The extension to the CLK class and to HS_TIE areas round fine-pitch RF pins
  is a judgement call.
* The 1:1 counting of clock spurs is a lumped estimate (section 2), not a simulation.
* Tented vias are assumed only by the optional `--tented` tier; via-in-pad needs the fab's filled-via
  option and is off by default.
* BT840 U3.F0-F3: decision in section 6; datasheet not re-read.
* Fab not named in the repo: JLCPCB assumed, capability numbers from the skill note, not re-checked.
* Dielectric loss (tan d 0.02 -> about 0.7-0.8 dB/10 cm at 6.5 GHz, estimate): ~0.1 dB on the RF runs.
* The length tolerances (0.5 mm = 3.1 ps) are my choice against the 33 ps budget.
* Power stage and `hs_finish.py` were not run; the power-class copper is only audited (thin copper
  warning), not designed, here.
* An external autorouter would probably complete more ordinary nets than the in-house router, but
  cannot honour the H/V policy or the class keep-offs without setup, and none may be downloaded.
