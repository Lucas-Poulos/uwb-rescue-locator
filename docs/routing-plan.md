# Bay station routing plan

Routing infrastructure for `bay-station/bay-station.kicad_pcb` (written 2026-11-18,
before the placement exists). Everything here is scripted and lives in
`scripts/layout/`; the numbers come from `scripts/layout/stackup.py` and the
per-net inventory from `scripts/layout/hs_nets.json`, which also generates the
project rules (`scripts/layout/apply_rules.py`). Nothing in this file was
verified on a real placement: the tools were exercised on a throw-away fixture
(section 8), and the router's quality figures are for that fixture only.

User routing policy, as implemented:

1. Every high-speed signal that needs a solid ground reference is routed first,
   by script, on F.Cu over solid In1 (section 2), then locked.
2. Everything else is Manhattan: F.Cu horizontal, B.Cu vertical, vias only at
   direction changes, no 45 degrees from the router (45 degrees or arcs only on
   the hand-first RF/clock lines).
3. GND stitching vias across the whole board, a fence along RF lines (section 6).
4. The inner layers are the reference planes (section 1).

Order of work on the placed board:

```
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
$KP scripts/layout/apply_rules.py                         # once; rewrites .kicad_pro netclasses + .kicad_dru
# on a SCRATCH copy (never the file under version control until the result is reviewed):
$KP scripts/layout/route_hs_uwb.py all --board SCRATCH/bay-station.kicad_pcb     # RF x4 + fence, UWB_CLK group
$KP scripts/layout/route_manhattan.py --board SCRATCH/bay-station.kicad_pcb --report r.json
$KP scripts/layout/stitch.py --board SCRATCH/bay-station.kicad_pcb --zones
$KP scripts/layout/check_gates.py --board SCRATCH/bay-station.kicad_pcb --workdir /tmp/gates
```

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
* **CLK_PATH +/-0.5 mm.** clock_dist_notes.md "Layout": equal length, same layer, same
  via count, away from SPI and RF; the buffer's own 25/50 ps skew (TI SNAS791D) is fixed
  and calibrates out. Measured buffer pin -> XTI pad centre, series R and C pads counting
  as zero. A0's DNP crystal stub (Y1/C209 on UWB_CLK0 and XTO) makes A0's electrical
  length differ by the stub; keep that stub shorter than 1 mm.
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
* POWER_HI >= 0.4 mm, POWER_MID >= 0.25 mm track width, as warnings only.

All five rule types were exercised: a deliberate violation of the no-via and keep-off
rules on the fixture produced exactly those `items_not_allowed` / `clearance` errors.

## 4. `route_hs.py` (hand-first library)

`microstrip_path` (chamfer 45 degree or arc bends), `route_pads` (orthogonal candidates
shortest first: straight, L, Z, swept U, each tested against pads/tracks/vias; automatic
neck at pads narrower than the line), `via_fence`, `meander_points`/`match_group`
(accordion with 3 x width gap between legs, amplitude up to 10 mm, meanders spread over
the straight legs of a path, longest-path target), `lock`. `route_hs_uwb.py` finds the
RF chains and clock hops from the netlist (no hard-coded references).

Greedy: it does not search for topologies. The first clean candidate wins, so
unlucky placement (one clock path walling in another) fails with an error instead of
finding a way round; the fixture needed the chip order chosen so the four clock lines
nest. That is a tooling limit, and a real placement should put the buffer where the
four runs are similar.

## 5. `route_manhattan.py` (ordinary nets)

See the module docstring for the method, and section 8 for what it achieved. In short:
A* on a 0.1 mm grid, F.Cu horizontal / B.Cu vertical, via only at direction changes,
per-class widths and the via sizes from the netclass, locked copper as obstacle,
rip-up and retry (<= 3 rips per net), nets in classes named by `--skip-class` (default
RF50) left alone. It does not do GND (see `gnd_fanout`: a via to the planes within 3 mm
of every SMD GND pad), differential pairs, length matching or 45 degree bends.

Policy exceptions it makes, all listed in its report and accepted by
`check_gates.py`: pad escape stubs (0.2 mm wide, at most 2 mm, any orthogonal direction)
and GND stubs (at most 3 mm). Fine-pitch pads cannot take a horizontal track from every
side, and pad centres are off the 0.1 mm grid.

## 6. Stitching and zones (`stitch.py`)

* General lattice **5.0 mm**; **2.5 mm** within 4 mm of any RF50/CLK copper (lambda/10 at
  6.49 GHz is 2.5 mm); **2.5 mm along the board edge**, 1.0 mm inset. Plane stitching rule
  of thumb: pitch <= lambda_g/20 at the highest frequency that matters, which would be
  3.7 mm for LTE at 2.2 GHz and 25 mm for 1-2 ns CMOS edges, so 5 mm is lambda/15 at the
  LTE band edge: a deliberate compromise, not a derivation that closes.
* Skips: pads (0.25 mm edge to via edge, covers mask openings and wicking), tracks (0.15,
  0.5 to RF50/CLK), other vias/holes (0.25 drill to drill), edge, keep-out rule areas
  including those inside footprints (the u.FL keep-outs), local pad clearance overrides
  (fiducials), and the 5.5 x 5.5 mm square under each DW3210 (no vias:
  Fig 35 "keep clear of copper, tracks and vias").
* Zones, deterministic (seeded KIIDs, fixed names, board outline inset 0.6 mm): GND on
  In1, In2, F.Cu, B.Cu, plus rule areas under each DW3210 (no pour on F.Cu and In1.Cu, no
  vias). **Never filled in-process**: `check_gates.py` fills a scratch copy with
  `kicad-cli pcb drc --refill-zones` (zone fill honours the `.kicad_dru`, so the pour stays
  0.5 mm off the RF lines).

## 7. `check_gates.py`

Hard gates (exit 1): netclasses present and equal to `hs_nets.json`; every net's class
equals the intended one by KiCad's matcher; no dead pattern; classes survive
`pcbutil.save_board()`; `.kicad_dru` parses; DRC (`--all-track-errors --refill-zones`) has
no short/clearance/width/via/hole violations; direction policy. Info: unrouted count,
violations by type, length spread of RF_PATH and CLK_PATH. `--require-complete`, `--strict`.

## 8. What was tested, and how good it is

Fixture: `make_test_board.py` puts a throw-away placement on a scratch copy (118 x 151
mm, all 428 footprints, chips and RF chains hand-placed on the bottom edge, everything
else shelf-packed by sheet; courtyard fill ~24 %, so **sparser than a real board**).
It is test scaffolding, not a layout proposal.

RESULTS_PLACEHOLDER

## 9. Uncertainties and things I could not do

* Dk of the real laminate at 6.5 GHz and the fab stackup (above). All widths follow from it.
* SMA launch (placeholder footprint, needs EM simulation).
* Fab not named in the repo: JLCPCB assumed, capability numbers from the skill note,
  not re-checked; the 1.048 mm thickness may not be orderable as is.
* Dielectric loss: tan d 0.02 at 6.5 GHz gives roughly 0.7-0.8 dB/10 cm in a 0.45 mm
  microstrip (estimate, not computed in the scripts; the RF runs are ~1.5 cm, so ~0.1 dB).
* The length tolerances (0.5 mm) are my choice against the 33 ps budget.
* `route_hs` and `route_manhattan` never saw the real placement; a real board will find
  cases the fixture did not.
* An external autorouter (e.g. Freerouting) would very likely complete more nets than the
  in-house router, but cannot honour the H/V policy or the class keep-offs without
  setup, and I was told not to fetch one. It is the obvious next step if
  completion on the real board is poor: the decision is yours.
