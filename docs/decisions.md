# Decision log

Open calls first, resolved calls below with the reasoning, so we don't
relitigate them. Keep this updated as the team decides things.

## Open

- **U8 `lib_symbol_issues` warning -- investigated, deliberately NOT "fixed".**
  ERC reports `Symbol 'TPS62A02PDDCR' not found in symbol library
  'Regulator_Switching'`. The library's actual symbol is `TPS62A02PDDC`,
  without the trailing R (that is TI's tape-and-reel suffix on the orderable
  part number, not part of the symbol name).

  **Do not simply rename it.** KiCad's `TPS62A02PDDC` is defined as
  `(extends "TPS62A01PDDC")`, and this repo has been bitten by `extends`
  before: `kicad-cli` fails to load an entire file, silently, reporting zero
  components and zero violations. Pointing U8 at a lib_id that does not
  resolve means the flattened 6-pin copy embedded in `regulation.kicad_sch`
  is always used -- which may well be why it was done this way, matching the
  flattened-copy workaround already used for AO3401A and MCP1700.

  So the warning is arguably the correct trade rather than a defect. Decide
  deliberately: either keep it and annotate the sheet, or rename to
  `TPS62A02PDDC` and re-verify that ERC still reports a non-zero component
  count. Do not change it without that check.

  Separately, three parts on the schematic have **no row in
  `libs/components.csv`** at all, found 2026-09-23 while cross-checking the
  board against a `kicad-cli sch export bom` run:

  - **U8**, the buck converter itself -- only its inductor L1 has a row.
  - **SW2** (RESET button) and **J3** (SWD header), both added when
    `programming_debug.kicad_sch` was rebuilt for Nordic. The BOM was never
    updated to match.

  **SW2 additionally has no footprint assigned**, which puts it in the same
  bucket as L1 and U3 (BT840) -- the three parts that cannot be placed on the
  PCB today. L1 and U3 are recorded as known gaps; SW2 was not. None of the
  three has a chosen part number yet, so no rows are being invented here.

### Environment and georeferencing -- what the enclosure does not cover

The bay station gets an **enclosure** (resolved 2026-09-23), which settles
ingress rating and weatherproofing the SMA/coax and GNSS antenna entries.
Those are enclosure-design problems now, not board problems. What a box does
not settle:

- **The enclosure has to pass RF.** The BT840's BLE link to the laptop runs
  off an antenna printed on the module itself, which is inside the box. A
  metal enclosure would kill that link. Either the enclosure is
  plastic/RF-transparent, or the BLE antenna moves outside -- and no RF
  connector is placed for that, so the first option is the assumption until
  someone says otherwise. Only BLE is exposed to this: the four UWB antennas
  are already remote on coax and the GNSS antenna is external on SMA.
- **Li-Ion charging below 0 degC.** An enclosure keeps water out, not cold
  out; an unheated box tracks ambient. Most single-cell Li-Ion must not be
  charged below freezing -- doing so plates lithium and permanently damages
  the cell. The MCP73871 has a THERM input and an NTC is placed, but
  `power_bms_notes.md` records it only as "10k per the datasheet's typical
  application circuit" -- it has never been sized for a specific cold-charge
  cutoff.
- **Temperature range across the BOM.** Same reason: the interior tracks
  ambient plus self-heating. Nothing has been checked against a range;
  several parts are specified at Tamb = 25 degC in the notes.
- **GNSS survey-in warm-up.** Not environmental at all. Absolute coordinates
  are not trustworthy until the average settles, and that restarts at every
  site. Relative UWB positioning is available immediately. Decide what the
  operator sees during warm-up so a coarse early fix is not mistaken for a
  settled one.
- **Magnetometer calibration procedure.** Hard-iron/soft-iron calibration is
  needed per build, and the enclosure is now part of what gets calibrated
  out -- ferrous fasteners or a steel lid sit fixed relative to U10. Calibrate
  with the board in its enclosure, not on the bench. No procedure exists.

### Critical path for the bay station

- **Baseline length: 1 m as specified, but bigger is nearly free.** Corrected
  2026-09-19: cable loss was previously recorded as the constraint on
  baseline. It is not. With ~17 dB of link margin and ~1 dB/m for decent coax
  at CH5, even 5 m spends under a third of the budget. **The real cap is the
  size of rigid frame the team is willing to build.** This matters because at
  1 m the 10 cm target depends on averaging, while at 3 m it falls out of a
  single shot -- the cheapest accuracy in the design, costing no parts and no
  firmware. Decide the frame size deliberately rather than defaulting.
- **Cable loss per metre at 6.5 GHz for the chosen coax** -- still worth
  verifying (every figure quoted so far is an estimate), but it is no longer
  a gating number. It sets how much of the 17 dB you spend, which feeds
  timestamp precision via SNR.
- **Import vendor footprints for BT840 and DWM3001C.** Neither should be
  hand-authored: both land patterns exist only as mechanical drawings, and
  guessing pad geometry on a 65- or 48-pad module is not a risk worth taking.
  Sources found: SnapMagic/SnapEDA lists a **Qorvo-provided** DWM3001C
  symbol/footprint/3D model, and both SnapMagic and Ultra Librarian list
  BT840 -- plus Fanstel ships a 61-pin library component with its EV-BT840F
  V4 Gerbers. Note that 61-pin part omits F0-F3, which are real solderable
  ground pads; see the pin-count item below before trusting it.

  **When importing, check pad naming.** KiCad matches symbol pins to footprint
  pads *by name*. Both symbols here use the datasheets' own schemes -- BT840
  as 1-16 then Z0-Z6/A0-A6/B0-B6/C0-C6/D0-D6/E0-E6/F0-F6, DWM3001C as 1-48.
  A vendor footprint numbered differently will silently connect nothing.
  Also confirm what the vendor does with DWM3001C pin 18, which its own
  datasheet leaves undocumented.
- ~~Reconcile the BT840 pin count~~ -- **resolved at 65, after a wrong turn.**
  The datasheet summary says 45 LGA while its own Pin Function table lists
  49 designators. An intermediate revision of this symbol dropped F0-F3 to
  reach 61, reasoning that they are bare "Ground pad" entries with no ball
  reference and that 16+45=61 matched Fanstel's library component. **That was
  wrong.** A real BT840 footprint shows F0-F3 as 1.4986mm SQUARE pads, far
  larger than the 0.6mm circular signal pads -- physical pads that must be
  soldered and grounded. The stated 45 evidently counts only signal pads.
  Symbol models all 65. Three agreeing numbers were agreeing with each other,
  not with the part.
- **TCXO + 1:4 low-skew fan-out buffer part selection**, against the DW3000
  Table 10 external-reference spec (0.8 V to VDD2 Vpp, AC coupled via 2200
  pF, -132 dBc/Hz @ 1 kHz, -145 dBc/Hz @ 10 kHz, 40-60% duty). See
  `positioning.md`.
- **Array calibration procedure and fixture.** Not optional -- the design
  does not close without it. Table 14's +/-6 cm generic-calibration residual
  would give ~85 cm of position error at a 1 m baseline, three times worse
  than the loosest target. Measured once at manufacture, since the rigid
  frame fixes both geometry and cable lengths.

  **Note the two halves are not the same job** (full treatment in
  `positioning.md`):
  - **A0** needs its *absolute* antenna+cable delay. Error maps 1:1 into
    radial range error. Needs a known true distance to measure against.
  - **A1-A3** need their delay *relative to A0*. Error is amplified by
    `range/B` -- 10x at 10 m on a 1 m baseline -- so these must be ~10x
    tighter than A0's (~1 cm equivalent path, vs ~10 cm for A0). They do
    *not* need a known distance, only the same signal observed
    simultaneously, so tag-position error largely cancels.

  The harder target is also the one needing less reference equipment. Design
  the fixture around that.
- **Captive vs. detachable antenna assembly.** A user-swappable cable
  invalidates the delay calibration. Leaning captive; confirm against
  serviceability requirements. (This used to be partly a regulatory question
  too -- see the certification entry under Resolved, which removes that half
  of it.)
- **Multi-instance driver support.** This design drives four DW3210s from one
  host; the common community driver (`br101/dw3000-decadriver-source`) was
  trimmed to one DW3000 per board. Multi-instance support exists in Qorvo's
  upstream driver and needs restoring. **Easier since the move to Nordic** --
  Qorvo's reference stack targets nRF52840 directly, so this is now working
  with the vendor grain. Still scope it before it surprises anyone.
- **Is SYNC/OSTR needed at all** now that the clock is genuinely shared? The
  DW3000 **User Manual** (not the datasheet) documents the one-shot timebase
  reset procedure. Read it before committing the schematic.
- **Mechanical frame design**: the rigid structure carrying the four
  antennas, including the A0 out-of-plane offset (see `positioning.md`).
- **Firmware**: nothing written, nothing assigned, and it is on the critical
  path -- the accuracy target is not met without the array calibration
  routine. Both boards are now Nordic (nRF52840 on the station, nRF52833 on
  the tag), so the remaining framework choice is a single one -- nRF5 SDK vs
  Zephyr / nRF Connect SDK -- rather than one per board. Where the position
  solve runs is also open. Skeleton and task list in `../firmware/README.md`.
- **LED drive rails and GPIO allocation.** The status LEDs are placed
  (`indicators.kicad_sch` on both boards) with indicative 1k series
  resistors. Confirm the drive rail for each and recompute, and allocate the
  GPIOs on each board's Nordic part for the two system-status LEDs.

### Everything else

- **Bay station uplink backend**: what protocol/service position data gets
  sent to, and whether the station sends raw timestamps for a server-side
  solve or computes the position itself.
- **UWB link parameters**: PRF, preamble, data rate, update rate, and
  multi-tag scheduling. (Channel is resolved -- CH5, see below.)
- **Antenna part selection.** Candidates covering CH5, existence and band
  confirmed from vendor product pages but full datasheets not yet pulled:
  Taoglas UWC.01 (6-8 GHz SMD chip), ILA.68 (LTCC 6-8.5 GHz), UWCCP.01
  (circularly polarized). Abracon ACR1004U is 3-6 GHz and does **not** cover
  CH5. Verify before BOM.
- **PCB layer count / stackup for the WRISTBAND** -- still a layout-phase
  call, likely 4-layer for RF. The bay station's is resolved and is now in
  the board file; see Resolved below.
- **Wristband module keep-out and edge spacing** -- two real DWM3001C
  datasheet requirements, neither actionable until layout starts:
  - **Section 7.1**: minimum 10mm with no metal either side of the module
    antenna, nothing above, below or beside it. Do not place the battery
    under the antenna. Ground flooded everywhere else.
  - **Section 7.2**: keep the module at least 1cm from the PCB edge. The
    antenna is cross-polarized in some regions, which helps link budget as a
    worn tag changes orientation, but that diversity can make ranging
    accuracy vary in harsh multipath. Qorvo's stated mitigation is the 1cm
    edge spacing, which reduces the horizontally polarized component.

  Moot for the bay station, which uses discrete ICs with remote antennas.
- **Bay station L1 (buck converter inductor) footprint**: the chosen part
  (Coilcraft XGL3520-102MEC) has no matching footprint in KiCad's default
  libraries -- pick/verify a real footprint at BOM time (see
  `bay-station/regulation_notes.md`).
- **Bay station power budget: re-check when the clock parts land.** Re-run
  twice on 2026-09-19 and now ~347mA against the TPS62A02's 2A (~5.8x). Three
  lines are estimates rather than datasheet figures -- the TCXO (~2mA), the
  1:4 fan-out buffer (~25mA), and the BT840 host (~20mA, since the Fanstel
  datasheet has no current table). Confirm both
  once chosen, along with whether the MCP73871 status LEDs pull from
  `+3V3_SYS` or `+VSYS`.

## Resolved

- **Bay-station stackup: 4 layers, 1.048 mm, controlled impedance.** Resolved
  2026-09-23 and now actually present in `bay-station.kicad_pcb`, which until
  this point was an empty 2-layer default stub contradicting the decision
  recorded here.

  Taken from DW3000 Datasheet v1.3, Section 7.3.2 Figure 35 "Recommended QFN
  Stack-up". The QFN variant is the one that applies -- this board uses the
  DW3210 (QFN40), not the WLCSP DW3110 that Figure 34 covers:

      F.Cu     35 um
      prepreg 254 um
      In1.Cu   35 um
      core    400 um
      In2.Cu   35 um
      prepreg 254 um
      B.Cu     35 um     = 1.048 mm finished

  Section 7.3's remaining requirements are recorded as a text note on the
  board's `Cmts.User` layer rather than repeated here, because they are
  layout instructions and that is where whoever does layout will see them:
  50 ohm impedance-controlled RF1/RF2 with the 2 pF DC-block pads embedded
  in the track at full width; ground copper removed under each DW3210 on
  F.Cu and In1.Cu, with In2.Cu as the first solid plane; analog, power and
  digital groups kept apart. If the stackup is ever changed, that first solid
  plane must stay at least 0.25 mm below F.Cu.

  **The dielectric constants are NOT from the datasheet**, which gives
  thicknesses only. KiCad's FR4 defaults (er 4.5, tan d 0.02) sit in the file
  as placeholders. Controlled impedance means the fab's stackup governs, and
  1.048 mm is not a catalogue thickness -- expect to take their numbers and
  re-solve trace widths rather than trusting anything geometric in the file.

- **Default netclass clearance cut from 0.2 mm to 0.15 mm.** Resolved
  2026-09-23. The DW3210 cannot physically satisfy 0.2 mm: KiCad's
  `QFN-40-1EP_5x5mm_P0.4mm_EP3.6x3.6mm` has 0.25 mm pads on a 0.4 mm pitch,
  leaving exactly 0.15 mm between neighbours. At 0.2 mm every adjacent pad
  pair on all four anchors would have failed DRC the moment footprints were
  placed. 0.15 mm leaves zero margin on that one geometry -- which is the
  part dictating the number -- and is comfortably inside standard fab
  capability everywhere else on the board.

- **The bay station gets an enclosure.** Resolved 2026-09-23. This closes the
  items that opened when outdoor deployment was confirmed: ingress rating,
  weatherproofing the four UWB SMA entries and the GNSS antenna entry, and
  weather exposure of the rigid antenna frame. All of it is enclosure design
  rather than board design, and it is not tracked here any further.

  Not selected or costed yet, and it does not cover what a box cannot: cold
  charging, BOM temperature range, and RF transparency for the BT840's
  on-module BLE antenna. Those three stay Open above.

- **GNSS + orientation added to the bay station** (`gnss.kicad_sch`, new
  sheet). Resolved 2026-09-23. The station is deployed outdoors and moved
  between sites, and the array only ever produced position RELATIVE to its
  own frame -- fine for an operator standing at it, useless as a coordinate
  to hand anyone else.

  **Position alone was not enough, and this is the part that is easy to
  miss.** A GNSS fix says where the station is, not which way it faces. The
  array reports a bearing relative to the frame, so without heading you get a
  circle of possible tag locations rather than a point. Hence three parts,
  not one:
  - **U9 u-blox MAX-M10S** -- where the station is.
  - **U10 ST LIS3MDL** magnetometer -- which way it faces.
  - **U11 ST LIS2DH** accelerometer -- tilt compensation, because a
    magnetometer only reads heading correctly when level and this station is
    set down on varying terrain. It also detects the station being knocked,
    which silently invalidates both the fix and the heading.

  **All three are KiCad stock symbols AND footprints** -- deliberate. The
  board already carries two outstanding vendor-footprint imports; a third was
  not worth it. u-blox SAM-M10Q with its integrated patch antenna was the
  alternative and would have deleted the GNSS antenna entirely, but KiCad has
  neither symbol nor footprint for it. MAX-M10S needs an external antenna at
  1.575 GHz, which is far easier routing than the 6.5 GHz UWB work already on
  this board.

  **Accuracy, recorded so it is not a surprise.** Uncorrected GNSS is 2-5 m
  against the array's 10-30 cm -- the world-frame anchor is 10-30x coarser
  than the relative fix hanging off it. Team chose **survey-in**: firmware
  averages the station's own fix while stationary to reach sub-metre.
  Operational cost, given the station moves between deployments: that
  averaging restarts at every site, so absolute coordinates have a warm-up
  that relative UWB positioning does not. Averaging is host-side on the
  BT840 -- u-blox's own "Survey-In" is a timing/RTK-part feature, not M10
  standard-precision, and host averaging is equivalent for static
  self-positioning without a pricier module.

  Pin data verified against u-blox Data Sheet UBX-20035208 R02 Table 9:
  KiCad's symbol matches 17 of 18 pins. **Pin 15 differs** -- "Reserved" in
  R02, `VIO_SEL` in KiCad, probably a later revision. Leave it open and check
  the current datasheet. Datasheet also requires VCC (8) and V_IO (7) tied
  together, and SAFEBOOT_N (18) left open.

- **No power switch on the wristband.** Confirmed 2026-09-19. The tag is live
  from the moment a cell is connected, and the only thing that ever cuts the
  rail is the DW01A protection IC at overdischarge. Recorded because the
  absence of a switch previously looked like an oversight rather than a
  choice, and because it has two consequences worth knowing: shelf life is
  bounded by self-discharge plus quiescent draw rather than by being switched
  off, and the only way to check rail state without disconnecting the cell is
  TP1/TP2 on `testpoints.kicad_sch`.

- **Test points added to both boards** (`testpoints.kicad_sch`, new sheet on
  each). Zero existed before, on a design whose central difficulty is
  sub-nanosecond timing and per-anchor delay calibration -- bring-up would
  have meant measuring a board with nowhere to attach a probe. Free now,
  impossible after layout.

  Bay station, 14 points chosen against this design's actual risks: the
  shared clock (TP5 at the TCXO, TP6-TP9 at each DW3210 XTI -- if the
  reference is missing at one anchor, TDoA produces nonsense rather than
  failing loudly), the SPI bus and anchor IRQ/reset for the multi-instance
  driver work, both power rails, and **two** grounds. TP3 is deliberately
  sited next to the clock points so a scope can use a short ground spring:
  at 38.4MHz a flying clip lead's inductance distorts the measurement.

  Wristband, 5: both rails, two grounds, and a firmware timing marker on a
  spare GPIO so tag-side exchange timing is visible on a scope.

  **Layout caveat recorded on the sheet:** a test point on the clock network
  is a stub, and stubs degrade the very signal integrity this design depends
  on. Keep TP5-TP9 as minimal pads on the existing routing; if layout cannot
  take all four anchor clock points, keep TP6/TP7 and drop TP8/TP9 -- two is
  enough to compare skew.

- **DW3210 footprint: KiCad stock `QFN-40-1EP_5x5mm_P0.4mm_EP3.6x3.6mm`.**
  Verified to exist in KiCad 8.0.6 and checked geometrically -- 40 signal
  pads, pad 1 at y = -1.8mm with 0.4mm pitch spanning 3.6mm, correct for 10
  pins per side on a 5x5mm body. It is also the only QFN-40 5x5mm 0.4mm-pitch
  variant KiCad ships; the EP3.5 and EP3.7 variants do not exist.

  **One caveat carried deliberately:** the exposed-pad size is unverified.
  The DW3000 package drawing is Figure 38, an image, so D2/E2 do not extract
  as text. KiCad's 3.6 x 3.6mm EP comes from a generic Microchip packaging
  spec, and other vendors' 40-lead 5x5 QFNs use 3.7 x 3.7mm. A slightly
  smaller pad than the part's own EP is the conservative direction -- less
  copper, no bridging risk, some thermal loss -- which is the same call
  already made and documented for the MCP73871. Check Figure 38 before fab.

- **Superseded parts are removed from schematics, not left in place.**
  Convention set 2026-09-19 after the bay station ended up with three sheets
  holding silicon that two architecture decisions had already replaced
  (ESP32-S3 on `connectivity`, 4x DWM3000 on `uwb_array`, ESP32-specific
  programming circuitry on `programming_debug`).

  The problem with leaving them: **a schematic containing the wrong part
  emits a wrong BOM and a wrong ERC.** `libs/components.csv` said DW3210 and
  BT840 while the schematic said DWM3000 and ESP32-S3 -- two checked-in files
  confidently disagreeing about the two most expensive parts on the board.
  A "pending rework" label in a README does not reach anyone generating a
  BOM from KiCad.

  **The rule: when a part is superseded, delete it from the sheet and leave a
  specification note in its place** -- what the replacement is, why, and what
  the person placing it needs to know. An empty sheet carrying a correct spec
  is strictly better than a populated sheet carrying a wrong one. Keep any
  passives whose requirement genuinely survives the change, and say which
  ones and why.

  Applied: `uwb_array` kept R10-R17 (GPIO5/6 straps) and R25-R28 (Figure 11
  IRQ pulldowns) because both are DW3000-core requirements unchanged by the
  module-to-IC move, and dropped C8-C19 because module decoupling does not
  map onto a bare IC with separate VDD1/VDD2/VDD3 rails. `connectivity` kept
  its generic 3V3 decoupling. `programming_debug` was rebuilt outright.

- **Bay station uplink: BLE to a laptop, not WiFi to the internet.** Resolved
  2026-09-19. The station now talks Bluetooth LE to a nearby computer. Note
  this is a real scope change from the original concept, which had the bay
  station uploading position data to the internet -- that is no longer what
  it does, and `system-overview.md` has been corrected accordingly.

  Confirmed with the team that a laptop will always be present, which is what
  made the MCU change below possible. **If that ever stops being true, both
  decisions reopen together.**

  Two consequences worth knowing: BLE range reaches a nearby laptop, not a
  router, and Nordic parts are BLE-only with no Classic/SPP -- so the link is
  a GATT service (or USB-CDC over a cable, which is simpler still and worth
  considering since the station is wired for power anyway).
- **Bay station MCU: Fanstel BT840 (Nordic nRF52840)**, replacing
  ESP32-S3-WROOM-1. Resolved 2026-09-19, and only possible because of the
  decision below it: the uplink moved from WiFi to BLE-to-a-laptop, and the
  team confirmed the station will never need to reach the internet without a
  laptop present. WiFi was the single reason Nordic was excluded.

  What it buys:
  - **One toolchain for the whole project.** The wristband already runs an
    nRF52833 inside its DWM3001C. Both boards become Nordic -- one SDK, one
    debug workflow -- instead of Nordic on one and ESP-IDF on the other.
    This matters because firmware is unstaffed and on the critical path.
  - **It attacks the hardest open firmware item head-on.** "Restore
    multi-instance DW3000 driver support" is critical path precisely because
    the community ESP-IDF port was trimmed to one chip per board. Qorvo's own
    reference stack targets Nordic (the QM33120WDK1 ships on nRF52840 DKs),
    so this works with the vendor grain rather than against it.
  - **`programming_debug.kicad_sch` collapses.** Nordic programs over SWD,
    which deletes the ESP32-S3 boot-strap resistors on GPIO0/3/45/46, the EN
    RC delay, and the native-USB flashing path -- see the two-USB-C item,
    now resolved by deletion.

  Costs, accepted: about +$3.40 per board ($6.88 vs ~$3.50); WiFi is gone
  structurally rather than provisionally; and `connectivity.kicad_sch` plus
  `programming_debug.kicad_sch` both need rebuilding.

  **Package note.** BT840 is 14 x 16 x 1.9mm with *hybrid* pins -- 16
  castellated plus 45 LGA. The datasheet notes SMT equipment is not needed
  for the castellated pins alone, but this design needs roughly 17-20 signals
  (3 SPI + 4 CS + 4 IRQ + reset + 2 SWD + 2 I2C + LED + power), so **the LGA
  pads are required** and the part must be reflowed. That is not a new
  constraint: the DW3210 is a QFN40 at 0.4mm pitch, so this board already
  needed reflow.

  **Symbol authored 2026-09-19** -- all 61 pins from the real Fanstel Pin
  Function table, once it was extracted with `pdftotext -raw`. An earlier
  pass wrongly concluded this was blocked: it had only tried `-layout`, which
  interleaves the BT840 and BT832 columns. The lesson is now a hard rule in
  `CLAUDE.md` -- a scrambled table means the wrong extraction mode, not
  missing data. Footprint should be imported from a vendor library rather
  than hand-authored; see Open.

- **Positioning scheme**: hybrid **two-way ranging + TDoA**. One center
  anchor does two-way ranging with the wristband for absolute range; three
  outer anchors timestamp the same tag transmission and yield TDoA against
  the center anchor for direction. Chosen over pure TWR-from-four-anchors
  (four bidirectional exchanges would cost tag air time and battery, and the
  wristband is the power-constrained side) and over pure TDoA (no absolute
  scale from a single burst). One tag transmission yields four measurements.
  Full writeup, math, and error budget: `positioning.md`.
- **No regulatory certification.** This is a **university prototype** -- not
  marketed, not sold, not deployed as a product -- so it does not go through
  FCC/CE intentional-radiator testing. Confirmed 2026-09-19.

  This matters more than it sounds: losing the DWM3000 module's pre-certified
  status was previously the single largest cost of moving to discrete
  DW3210s, and it is now simply not a cost. The discrete decision gets
  materially cheaper and lower-risk as a result.

  **If this ever becomes a product, certification comes straight back**, and
  it is not a small retrofit -- an intentional radiator has to be tested as
  the assembly it ships as, including the antenna and cable. Anyone reviving
  this for production should treat certification as a first-class schedule
  item, not a finishing step. Two design choices made here point that way
  anyway (a BPF on RF1/RF2 per the datasheet's note about regions mandating
  conducted testing, and a captive antenna assembly), so the door is left
  open rather than closed.
- **Performance target**: **10-30 cm accuracy at ~10 m range.** Set
  2026-09-19. This had been missing from the repo entirely; everything in
  `positioning.md` is derived from it, so changing it changes the design.
- **Status indication added to both boards.** Until 2026-09-19 the system had
  **zero LEDs** -- no way to tell whether either board was powered, charging,
  charged, or working -- while MCP73831's `STAT` and MCP73871's
  `STAT1`/`STAT2`/`~PG` all sat unconnected. Poor for a device whose purpose
  is locating someone in trouble, and much cheaper to fix at schematic stage
  than after layout. New `indicators.kicad_sch` on each board: wristband
  `D2`/`D3` (0603), bay station `D4`-`D7` (0805), each with a 0603 series
  resistor. Both boards also get one MCU-driven system-status LED so firmware
  can signal ranging/fault. Resistor values and drive rails are indicative --
  tracked under Open.
- **New sheets for the reworked architecture.** `uwb_anchors.kicad_sch`
  renamed to `uwb_array.kicad_sch` (the four receivers are one on-board
  array, not distributed anchor units), and `clock_dist.kicad_sch` added to
  hold the shared-reference network that defines this architecture. Both
  boards gained `indicators.kicad_sch`. Bay station is now 8 sheets,
  wristband 8.
- **UWB channel: Channel 5 (6489.6 MHz)**, not Channel 9. Chosen because the
  architecture is coax-fed: cable loss and free-space path loss both scale
  with frequency, so CH5 directly buys baseline length and range. Also sets
  antenna selection and connector rating. Revisit only if regulatory rules in
  a target market forbid it.
- **Anchor topology: all four transceivers on the one bay-station PCB
  sharing a single clock, with the four antennas remote on ~1-2 m coax.**
  Chosen 2026-09-19 over three alternatives:
  - *Four DWM3000 modules on one PCB* -- impossible. No clock pin, and a
    board-sized ~0.1 m baseline gives ~17 degrees of bearing error.
  - *Four discrete anchors on satellite boards, clock over the harness* --
    works, but pushes the timing problem into cables and multiplies BOM.
  - *Wireless clock-calibration-packet sync between independent anchors* --
    works, keeps the modules and their certification, but moves the entire
    problem into firmware.

  Putting all four receivers on one board makes synchronization
  **structurally absent rather than solved**: one oscillator, short matched
  traces, no drift model, no sync firmware. The cost moves into the RF path,
  where it becomes a link-budget question instead of a timing one. Accepted
  because CH5 leaves ~17 dB of link margin at 10 m, comfortably covering the
  2-5 dB of expected cable loss.
- **UWB: module vs. discrete IC** -- the bay station moves from the DWM3000
  module to the **bare DW3000-family IC** so all four anchors can share one
  38.4 MHz reference. TDoA compares timestamps across receivers, and 1 ns of
  clock error is 30 cm of position error. The DWM3000 module makes that
  impossible: its 24 pins (verified symbol in `shared/symbols/`) include no
  clock pin, and its crystal is internal and unreachable. The bare IC does
  support it -- DW3000 Datasheet v1.3 Table 10: "A 38.4 MHz signal can be
  provided from an external reference in place of a crystal if desired", with
  XTI documented as the "external reference overdrive pin" and XTO needing
  "1pF to the ground, only if external clock is used." **The wristband keeps
  the DWM3000 module** -- a single transceiver has nothing to synchronize
  against, so none of this applies.
- **Clock implementation: one TCXO + a 1:4 low-skew fan-out buffer**, not a
  shared passive crystal. A crystal cannot be shared -- each chip's XTI/XTO
  pair forms its own oscillator, so four chips would be four oscillators,
  which is the problem rather than the fix. Buffer output skew is a fixed
  per-chip offset and calibrates out with cable delay; only skew *stability*
  matters, which on-board is negligible. Selection spec in `positioning.md`.
- **Mechanical: rigid antenna frame, not field-installed anchors.** At 1-2 m
  spacing the four antennas mount on one rigid structure. Geometry is then
  fixed at manufacture to sub-millimetre, so there is **no install-time
  survey** (anchor position error otherwise feeds one-for-one into tag
  position error), cable lengths are fixed so the delay calibration stays
  valid, and the product is one unit rather than an installation job. **A0
  must be offset out of the plane of A1-A3** (20-30 cm on a standoff) --
  four coplanar antennas have a mirror ambiguity about that plane and
  degrade badly in elevation near it. Free at design time, impossible to
  retrofit.
- **UWB connectors: SMA.** CH5 at 6489.6 MHz is *above* the DC-6 GHz rating
  of U.FL, W.FL, MMCX and MCX; SMB is DC-4 GHz. SMA is DC-18 GHz. Prefer
  antennas with integral pigtails over a connector at each end -- every
  mated pair costs ~0.1-0.3 dB at 6.5 GHz plus a reflection. **The
  wristband's 2.4 GHz BLE U.FL (`J2`) is unaffected and stays** -- well
  inside rating, and the right choice for a wearable.
- ~~**Host MCU: ESP32-S3-WROOM-1 retained**, no second MCU.~~ **SUPERSEDED
  2026-09-19 by the Fanstel BT840** once the WiFi requirement was dropped --
  see that entry above. Kept for the reasoning, which still holds on its own
  terms: it was correct *while* WiFi was a requirement. Considered and
  rejected: switching to nRF52840 for native Qorvo driver support (loses
  WiFi, which is why the ESP32-S3 is there) and a dual-MCU split (permanent
  BOM, second toolchain, and an inter-MCU protocol to maintain, to avoid a
  one-time integration cost). A maintained ESP-IDF driver port exists
  (`br101/dw3000-decadriver-source`, wrapping Qorvo's own `dwt_uwb_driver`);
  its one-chip-per-board limitation is tracked under Open. MCU timing jitter
  does not affect accuracy -- timestamps are latched in hardware and read
  over SPI afterwards, and delayed-TX schedules transmissions in the chip.
  Four chips share one SPI bus with four chip selects; DW3000 runs to 36 MHz
  (20 MHz in CRC mode).
- **DW3000 variant: DW3210 (QFN40), not DW3110.** Per DW3000 Datasheet Table
  1, DW3110 is a **52-ball WLCSP, 3.1 x 3.5 mm** -- chip-scale, not
  realistically hand-assemblable. DW3210 is the same non-PDoA part in QFN40
  (5x5mm). Same hand-assembly reasoning already applied to the MAX17048
  TDFN-vs-WLP choice. Accepted tradeoff: the datasheet states QFN variants
  output about **2 dB less maximum TX power** than WLCSP. The PDoA variants
  (DW3120/DW3220) were considered and set aside -- PDoA on a single IC with
  two antenna ports is a different way to get bearing without cross-receiver
  synchronization, but it changes the whole architecture, and the team's call
  is the shared-clock TDoA array.
- **Wristband: one DWM3001C replaces NINA-B111 + DWM3000 + the whole antenna
  sheet.** Resolved 2026-09-19 after establishing that the tag's BLE radio
  serves no purpose in this system -- it talks only over UWB. Once BLE is not
  a requirement, the question stops being "which BLE module" and becomes
  "what is the simplest way to get a Cortex-M4 talking to a DW3110".

  The DWM3001C is exactly that in one part: DW3110 UWB transceiver, Nordic
  nRF52833 MCU, ST LIS2DH12 accelerometer, planar UWB antenna, Bluetooth chip
  antenna, power management and the 38.4MHz crystal. 48-pin side-castellated,
  27.1 x 19.13 x 3.2mm, VDD 2.5-3.6V. Its datasheet states it "requires no RF
  design as the antenna and associated analog and RF components are on the
  module" (Section 8).

  **Counterintuitively this is the simpler board, not the more complex one.**
  A discrete MCU would have meant a second part plus its crystal, decoupling,
  layout and an inter-chip SPI bus to design. Deleted instead: NINA-B111,
  DWM3000, `antenna.kicad_sch` in full (ProAnt InSide-2400, U.FL connector,
  L/C matching network), the GPIO5/6 SPI-mode straps R7/R8, and the R9 IRQ
  pulldown -- the host-to-transceiver link is internal now. Wristband went
  from 8 sheets to 6.

  **BLE and the accelerometer are deliberately unused.** They are dormant
  silicon on a module bought for its M4 and its UWB radio: no external parts,
  no wiring, no firmware. The accelerometer is worth revisiting as a way to
  motion-gate the UWB, which is the largest battery lever available on the
  power-constrained side of the system.

  Also true and not the reason: the LDO budget got easier (70mA -> 43mA,
  headroom 3.6x -> 5.8x), and the module ships factory-calibrated for crystal
  trim, TX power and antenna delay.

  Symbol hand-authored in `wristband/libs/` from the real DWM3001C Data Sheet
  Rev B (May 2022) Table 2. **Footprint not yet authored** -- the land pattern
  is in Figure 5, which does not extract as text; read the figure. Pin 18 is
  undocumented in Table 2 and is modelled as a passive NC -- confirm before
  fab.

  Superseded by this: the earlier NINA-B111 choice (u-blox NINA-B1-series
  external-antenna variant, datasheet UBX-15019243-R15) and its symbol and
  footprint, which stay in `wristband/libs/` unused for now.
- **UWB module (as currently drawn)**: Qorvo/Decawave **DWM3000** -- a bare
  UWB transceiver module with no onboard host MCU. Still correct for the
  wristband; superseded for the bay station by the discrete decision above.
  An earlier pass of this doc used the name "DWM3000C", which isn't a real
  Qorvo part number -- see `shared/README.md` for the correction writeup.
  Symbol in `shared/symbols/` (verified against Qorvo DWM3000 Data Sheet Rev
  B, May 2021); footprint is a flagged `DWM3000_PLACEHOLDER` pending one
  land-pattern dimension -- verify before fab.
- **Wristband BMS**: MCP73831 (LiPo linear charger) + DW01A/FS8205
  protection pair -- same proven pattern as the team's other wristband
  project (alarm-band). Symbols in `wristband/libs/`; battery connector and
  USB-C charging receptacle reuse KiCad's own default libraries.
- ~~**Bay station connectivity**: ESP32-S3-WROOM-1 module~~ -- **SUPERSEDED
  2026-09-19 by the Fanstel BT840**. The original reasoning (one part instead
  of discrete BLE+WiFi ICs) was sound, and the "revisit if 2.4GHz-only WiFi
  matters" caveat resolved in an unexpected direction: WiFi stopped being
  needed at all.
- **Bay station BMS**: MCP73871 (charge + power-path management, so the
  station can run continuously on external power while its battery tops off
  in the background) + MAX17048 fuel gauge (proven on alarm-band).
- **Repo structure**: monorepo, two KiCad projects (`wristband/`,
  `bay-station/`) + a `shared/` library folder. KiCad has no native
  multi-board project, and a monorepo keeps shared parts/docs/history in one
  place for a small team.
- **Voltage regulation** (a gap found by checking real datasheets: NINA-B111
  abs-max VCC is 3.9V, DWM3000 abs-max VDD3V3 is 4.0V, but a charged LiPo
  hits 4.2V -- both ICs were about to be fed straight off the unregulated
  battery/system rail with no margin against permanent damage):
  - Wristband: **Microchip MCP1700T-3302E/TT** LDO (fixed 3.3V, low-Iq),
    `wristband/regulation.kicad_sch`. **Re-run 2026-09-19 for the DWM3001C**:
    module 40mA (CH5 TX or RX, DWM3001C Datasheet Rev B Table 5) + D3 status
    LED ~3mA = **~43mA vs. the part's 250mA rating, ~5.8x headroom** -- up
    from 3.6x, because one module doing both jobs draws less than two modules
    doing one each.
  - Bay station: **TI TPS62A02PDDCR** buck converter (2A, single-cell-Li-Ion
    input range), `bay-station/regulation.kicad_sch`. Current budget:
    **Re-run 2026-09-19 for the discrete architecture**: ESP32-S3-WROOM-1
    (~355mA peak TX) + 4x DW3210 (72mA each, CH5 RX peak, DW3000 Datasheet
    v1.3 Table 5) + clock network (~27mA, estimated) + status LEDs (~12mA)
    = **~682mA vs. 2A rating, ~2.9x headroom**. The part choice survives;
    no regulator change needed. Full working in
    `bay-station/regulation_notes.md`. Re-check once the TCXO and clock
    buffer are actually selected -- those two lines are estimates.
- **Wristband antenna** -- ~~ProAnt InSide-2400 patch antenna on U.FL, chosen
  from u-blox's NINA-B1 approved-antenna list~~. **Superseded 2026-09-19**:
  the DWM3001C carries both its UWB and Bluetooth antennas on-module, so the
  external antenna, its U.FL connector, its matching network and the whole
  `antenna.kicad_sch` sheet were deleted. This also closed the open
  "matching-network values pending prototype RF tuning" item -- there is
  nothing left to tune.
- **DWM3000 GPIO5/GPIO6 SPI-mode strapping**: the power-up sequence requires
  these sampled at boot (per Qorvo's own timing diagrams) -- 10k pull-downs
  per instance (`wristband/radio_mcu.kicad_sch`;
  `bay-station/uwb_array.kicad_sch` x4).
- **ESP32-S3-WROOM-1 boot-strapping + programming**: pull resistors on
  GPIO0/3/45/46 per Espressif's real hardware design guidelines, an EN
  RC-delay network, BOOT/RESET buttons, and a native-USB flashing interface
  -- `bay-station/programming_debug.kicad_sch`. Surfaced the "two USB-C
  connectors" open item above.
- **Wristband programming**: standard 2x5 1.27mm ARM Cortex Debug SWD header,
  `wristband/programming_debug.kicad_sch`. Now targets the nRF52833 inside the
  DWM3001C via SWD_CLK (pin 2) and SWD_DIO (pin 3); unchanged otherwise.
- **KiCad version**: team standardizes on **KiCad 10.0.5** (current stable;
  supersedes an earlier, since-corrected plan to target 9.x). Files on disk
  are still KiCad 8.0 format -- re-checked and confirmed clean under 10.0.5
  via `kicad-cli` on 2026-08-14. See root `README.md`'s Toolchain section.
- **Passives audit against every chip's real reference design**: compiled in
  `passives-reference.md`. Found and fixed one real gap (100k IRQ/GPIO8
  pulldowns missing on all 5 DWM3000 instances, per Qorvo's own Figure 11 --
  added as R9 on the wristband, R25-R28 on the bay station). Also documented,
  not changed: DWM3000's placed decoupling exceeds Qorvo's own minimal
  application circuit (kept as conservative practice), and its GPIO5/6
  external straps are redundant with the chip's internal pulls (kept
  deliberately for tighter timing margin).
