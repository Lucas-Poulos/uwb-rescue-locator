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

  (The missing BOM rows and SW2 footprint that used to sit in this item were
  closed on 2026-11-17 -- see Resolved.)

### nRF9151 redesign -- open risks (2026-11-17)

Raised by the five sheet/firmware handoffs (`bay-station/handoff/*.md`,
`firmware/handoff.md`). The first three block fab outright.

- ~~nRF9151 footprint is a PLACEHOLDER with invented pad positions~~ --
  **replaced 2026-11-18 with Nordic's own DK pad data**, see Resolved
  ("Footprints from vendor sources"). Residual: it has not been checked
  against the PS land-pattern figure, which still needs the PDF (next item).
- **No Nordic PDF could be fetched.** docs.nordicsemi.com served a
  Cloudflare challenge; every nRF9151 PS / HDG / DK fact in this repo was read
  from Nordic's HTML renditions through a text-extraction fetch, not with
  `pdftotext -layout/-raw` (root `CLAUDE.md` rule 1). Figures (pinout drawing,
  reference schematic, package drawing) could not be seen at all. Before fab:
  re-check the 113-pin table against the PDF in both modes, the SPIM
  FREQUENCY table (the 8 MHz figure below comes from the nrfx MDK header),
  the pinout figure (the "slow pins near the RF corner" placement rests on pin
  *numbers* only), and record the PDF revisions. Same caveat for the
  nRF91x1 PTI / `%XRFTEST` facts in `verification-plan.md`.
- ~~U40 (TPS63802) footprint is a PLACEHOLDER~~ -- **resolved 2026-11-18**
  from the rendered SLVSEU9D land-pattern and stencil pages (Resolved,
  "Footprints from vendor sources").
- ~~U3 (BT840) footprint is still missing~~ -- **resolved 2026-11-18**, from
  Fanstel's own Eagle library (same section).
- **UWB SMA launch needs EM simulation.** The CONSMA020.042-G footprint is a
  PLACEHOLDER and its 1.52 mm centre pad is far wider than the 50 ohm line;
  the taper / ground cut-back at 6.5 GHz has to be designed, not guessed. The
  connector is rated for 1.07 mm boards and this one is 1.048 mm.
  `uwb_array_notes.md`, RF front end.
- **DW3210 exposed pad net.** The QFN footprint has an EP, the symbol has 40
  pins, and DS v1.1 Table 2 does not name the EP. Expected GND, unverified --
  resolve from Figure 38 / a Qorvo layout before layout. (Separate from the
  still-open EP *size* caveat on the DW3210 footprint entry under Resolved.)
- **FB1-FB4 (BLM03PG330SN1D): footprint assigned, land pattern unverified.**
  Case size is 0201 inch / 0603 metric (0.6 x 0.3 x 0.3 mm), assigned the
  stock `Inductor_SMD:L_0201_0603Metric` on 2026-11-18, but the Murata PDF
  (ENFA0020) could not be fetched -- murata.com served a maintenance page and
  Mouser/alldatasheet/DigiKey refused automated fetches -- so Murata's own
  land-dimension table for BLM03PG was not read. Check it before layout.
- **TCXO is quote-only.** The proposed Rakon RPT1490LN (Resolved below) has
  no catalogue ordering code for 38.4 MHz -- one distributor lists E8246LF,
  zero stock, RFQ -- and is 14.5 x 9.5 x 6 mm. Its phase-noise margin is from
  typical plot markers, not guaranteed limits. Get a Rakon quote, and do one
  more search for a smaller CMOS 38.4 MHz TCXO with a guaranteed 1 kHz figure
  (`clock_dist_notes.md`).
- **XTI drive amplitude.** A 3.3 V LMK1C1104 through 2200 pF gives >= 2.6 Vpp,
  near the top of DW3000 Table 10's 0.8 V..VDD2 window. Bench-test at a 2.5 V
  buffer supply (via TP529) before deciding whether a 2.5 V LDO is needed.
- **Shared RSTn contention.** Four O-H RSTn pins are tied (each via 0R) to
  `UWB_RST_N`; check on first boards that a chip still in POR does not fight
  the others. Fallback is one reset GPIO per anchor, and there are none spare.
- **GNSS LNA has no pre-filter.** HDG *GNSS* warns that coupled LTE TX can
  damage an external LNA and recommends a filter ahead of it; the BGA524N6 RF
  input is 0 dBm abs max. Choose between an LTE-to-GNSS antenna isolation
  budget, a verified 1575 MHz SAW footprint, or an active antenna with an
  integrated SAW and the U24 bypass (R124).
- **No spare nRF9151 GPIOs, and all four serial instances are used.** 35
  GPIO-type signals competed for 32 pins; the charger status nets were
  dropped to LEDs only (Resolved below). Anything new -- a second button, a
  per-anchor reset, the `VSYS_SENSE` divider firmware asked for, a TCXO
  enable -- needs a GPIO expander, a pin freed elsewhere, or a move to the
  BT840. ETM trace pins are in use as GPIO, so trace is SWO/RTT only.
- **Budget the 8 MHz SPI cap.** The nRF9151 SPIM tops out at 8 MHz (Resolved
  below), against the 32 MHz the nRF52840 design assumed. It costs readout
  time, not precision -- but A0's DS-TWR reply delay and the achievable update
  rate have not been re-derived at 8 MHz.
- **LIS2DH lifecycle.** A Farnell listing marks the ST LIS2DH as no longer
  manufactured; ST's product page could not be fetched. LIS2DH12 is NOT a
  drop-in (LGA-12 vs LGA-14, different pinout). Check ST status before
  ordering; if obsolete, re-pick (LIS2DH12 or LIS2DW12) and re-author U11.
- **Third-party copies stand in for several datasheets.** BGA524N6 (Rev 3.5
  from a mirror; its E6327/XTSA1 OPN seen only at distributors), LIS3MDL and
  LIS2DH (ST mirrors), Hirose U.FL (not read at all), MFF2 eSIM pad map
  (unverified, DNP part). Replace with manufacturer copies before ordering.
- **RF small parts not chosen:** ESD diodes D100/D101 (DNP footprints), the
  active-antenna bias-tee values (R122/L100/C122, estimates), and the L101
  8.2 nH LQW MPN.
- **MCP73871 orderable variant / LBO.** D4 doubles as a low-battery LED only
  if the ordered suffix enables LBO (DS20002090E sec 3.13, third option
  character). Variant not yet chosen.
- **Mounting holes: ground or not.** H1-H4 are NPTH with no net. Recommended
  on the mechanical sheet: plated `MountingHole_3.2mm_M3_Pad_Via` to GND,
  optionally through a 0R per hole to break a ground loop through a metal
  frame. Decide with the enclosure.

### Environment and georeferencing -- what the enclosure does not cover

The bay station gets an **enclosure** (resolved 2026-09-23), which settles
ingress rating and weatherproofing the SMA/coax and antenna entries.
Those are enclosure-design problems now, not board problems. What a box does
not settle:

- **The enclosure has to pass RF.** The BT840's BLE link to the laptop runs
  off an antenna printed on the module itself, which is inside the box, so a
  metal enclosure kills that link. The nRF9151's LTE-M and GNSS antennas are
  on u.FL pigtails (J10/J11): they can be mounted outside the box, or the box
  must pass 0.7-2.2 GHz as well. Neither antenna placement is decided, so an
  RF-transparent enclosure is the assumption until someone says otherwise.
  The four UWB antennas are already remote on coax and are not exposed to
  this.
- **Temperature range across the BOM.** The interior tracks ambient plus
  self-heating. Nothing has been checked against a range; several parts are
  specified at Tamb = 25 degC in the notes. (Cold *charging* is resolved: see
  the THERM entry under Resolved.)
- **GNSS survey-in warm-up.** Not environmental at all. Absolute coordinates
  are not trustworthy until the average settles, and that restarts at every
  site. With the nRF9151 the GNSS also only runs while LTE is idle (PSM /
  eDRX windows), so warm-up is longer when LTE is busy. Relative UWB
  positioning is available immediately. Decide what the operator sees during
  warm-up so a coarse early fix is not mistaken for a settled one.
- **Magnetometer calibration procedure.** Hard-iron/soft-iron calibration is
  needed per build, and the enclosure is now part of what gets calibrated
  out -- ferrous fasteners or a steel lid sit fixed relative to U10. Calibrate
  with the board in its enclosure, not on the bench. No procedure exists. The
  orientation sheet's keep-out distances (buck inductor >= 25 mm, LTE feed >=
  20 mm) are engineering guidance, not ST numbers; verify by logging heading
  while the buck, charger and LTE TX run.

### Firmware

- **Wristband GPIO.** On `dwm3001c-migration` only 12 of the DWM3001C's 48
  pins are tied (power, GND, SWD, `RESET_N`, `VBAT_SENSE`, and `P0.17` to the
  SOS button). The module's internal nRF52833-to-DW3110 wiring is fixed, so
  the open part is only what the remaining external pins do. (The bay
  station's allocation is resolved -- see Resolved.)

  Minor, but it will end up in code: the wristband net is spelled
  **`SOS_BNT`** (`/Radio MCU/SOS_BNT`). Almost certainly meant to be
  `SOS_BTN`; worth fixing before firmware names a symbol after it.
- **BLE link security level.** Nordic's own connectivity bridge ships its BLE
  NUS side off by default because it "is not encrypted or authenticated". The
  bridge skeleton requests encryption (L2) with bonding; decide whether L4
  (authenticated, needs passkey/OOB with no display) is required for a rescue
  deployment.
- **LTE-M service: endpoint, SIM/operator, data budget.** The laptop stays
  primary and the station must run fully with no SIM. Who receives LTE
  reports, at what rate, and on which operator/bands is undecided.
- **No rail-sense ADC net.** Firmware sees rails only indirectly (MAX17048
  VCELL, modem `%XVBAT`). A `VSYS_SENSE` divider into an nRF9151 AIN would be a
  net-contract change and needs a pin that does not exist today (see "No spare
  nRF9151 GPIOs" above).
- **Never built.** The NCS skeletons (`firmware/bay-station/`) were not built
  with `west`; Kconfig names, `SPI_DT_SPEC_GET` arity, NUS callback signatures
  and SoC dtsi paths come from docs/upstream `main`, not a pinned NCS tree.
  LIS2DH WHO_AM_I, every MAX17048 register/address, and the DW3210 DEV_ID
  (from Qorvo driver source, not the User Manual) are unverified.
  `firmware/handoff.md`.

### Wristband IMU -- proposed and rejected 2026-09-28

- **No external IMU on the wristband.** Asked for directly; declined, because
  the DWM3001C already contains an ST **LIS2DH12** accelerometer and adding a
  second one costs board area and standby current on the one board in this
  system that can least afford either. The tag is the power-constrained side
  -- the whole TDoA scheme is built around it transmitting once.

  This also upholds the standing rule in `CLAUDE.md`: *"Its BLE radio and
  accelerometer are unused -- do not add parts to 'use' them."* The module was
  bought for its M4 and its UWB radio; the accelerometer is dormant silicon
  that comes along with it.

  **What the module cannot do is measure angular rate.** LIS2DH12 is a 3-axis
  accelerometer and nothing more. Motion detection, wake-on-motion, tilt,
  free-fall and impact are all covered; orientation *during* motion, and
  anything resembling dead reckoning between UWB fixes, are not. **If a gyro
  is ever genuinely required, this decision reopens** -- that would be a real
  gap rather than a duplicate.

  Note the bay station took the opposite decision on the same day, and the
  asymmetry is deliberate: the station is mains-or-large-battery powered,
  fixed, and its orientation feeds the heading that georeferences every fix.
  The tag is worn, tiny and battery-critical.

- **OPEN: is motion-gating actually free?** `wristband/README.md` has long
  described motion-gating the UWB as "the largest battery lever available"
  costing "nothing in hardware". The second half is **not established.**

  `I2C0_SDA` (pin 14) and `I2C0_SCL` (pin 15) are real module pins and are
  **unconnected in the schematic** -- a netlist export puts both on
  `unconnected-(...)` nets. I2C is open-drain and cannot return to a logic
  high without a pull-up, so exactly one of these is true:
  - Qorvo fitted pull-ups inside the module, and motion-gating is genuinely
    firmware-only; or
  - they did not, and the bus needs **two external pull-ups to `+3V3`** --
    making the claim wrong and the change a hardware one after all.

  Resolve against the real **DWM3001C Data Sheet Rev B (May 2022)**, the same
  document `wristband/libs/` was authored from. Until then, do not plan
  firmware on the assumption that the accelerometer is reachable for free.

### Level shifting and pull-ups -- audited 2026-09-28, re-checked 2026-11-17

- **No level shifters are needed anywhere in this design, on either board.**
  Audited in answer to a direct question, and re-checked for the nRF9151 host.
  The result depends on one choice, recorded here so it does not get reversed
  by accident: **pull the I2C bus up to `+3V3`, never to `VBATT_PROT`.**

  Every digital part is 3.3 V-native or 3.3 V-tolerant: DW3210 (VDD1
  1.62-3.6 V, and VDD1 supplies the I/O), nRF9151 (`VDD_GPIO` 1.7-3.6 V, fed
  from `+3V3`; nRF9151 PS *Operating conditions*, HTML), Fanstel BT840 /
  nRF52840 (1.7-3.6 V), LIS3MDL and LIS2DH (separate VDD_IO, on `+3V3_SNS`),
  LMK1C1104 (CLKIN 3.3 V-tolerant at every VDD), ESP32-C5-WROOM-1 (3.0-3.6 V,
  PR #7 only). The nRF9151's only sub-3.3 V I/O -- the 1.8 V SIM, MAGPIO and
  MIPI RFFE pins -- are sheet-local and talk to 1.8 V parts or nothing.

  The one part that looked like a problem is the **MAX17048 fuel gauge**,
  whose VDD *is* the battery rail (2.5-4.5 V) because it senses cell voltage
  through that pin. It is not a problem, for three reasons, all from
  datasheet 19-6171 Rev 7:
  - I2C is **open-drain**. No device drives the bus high; the bus voltage is
    set entirely by the pull-up rail. A part on a 4.2 V supply still sees a
    3.3 V bus.
  - Its **VIH is a fixed 1.4 V**, not the usual 0.7*VDD. A 3.3 V bus is read
    correctly even at full charge.
  - **SDA/SCL/ALRT are rated -0.3 V to +5.5 V absolute max**, so 3.3 V is
    well inside.

  The hazard runs the *other* way: pulling the bus to `VBATT_PROT` would be
  fine for the MAX17048 but would put ~4.2 V on Nordic GPIO rated to 3.6 V.

  The same over-voltage reasoning is why the MCP73871 status outputs are
  **not** routed to a GPIO: they are open-drain with LEDs pulled to `+VSYS` /
  `+5V_IN`, so the off-state node sits near `+VSYS`, above `VDD_GPIO`
  (`connectivity_notes.md` section 2).

- **Pull-ups: three are required.** Placed 2026-09-28 as R37 (SDA), R38
  (SCL), R39 (ALRT) to `+3V3` on `connectivity.kicad_sch`; before that the
  bay station had **zero** I2C pull-ups while carrying three devices (MAX17048
  0x36, LIS3MDL 0x1C, LIS2DH 0x19). I2C is open-drain and cannot return high
  without them; ALRT is separately open-drain and needs its own.

  **R37/R38 are 3.3k, R39 is 2.2k -- derived, not defaulted** (changed from
  2.2k on 2026-11-17 for the nRF9151):
  - Lower bound, from the weakest sink on the bus: the nRF9151 standard-drive
    IOL is >= 1 mA at 0.4 V (PS *GPIO*, HTML), so Rp(min) = (3.3 - 0.4)/1 mA =
    **2.9k**. The old 2.2k was sized for the MAX17048's 4 mA and the nRF52840.
  - Upper bound, from the I2C-bus specification (NXP UM10204,
    tr = 0.8473 x Rp x Cb, 300 ns): 3.3k allows **~107 pF** at 400 kHz. If the
    bus from `power_bms` to `orientation` measures above that, run 100 kHz.
  - R39 stays 2.2k: the MAX17048 sinks ALRT and the nRF9151 only reads it.

  The existing pulls elsewhere are all correct and unrelated: R10-R17 (10k
  DW3210 SPI-mode straps), R25-R28 (100k DW3210 IRQ pull-downs, Qorvo
  Figure 11), R224 (100k `UWB_WAKEUP` pull-down), and the wristband's 5.1k CC
  resistors, which are mandatory USB-C pull-*downs*. `RESET_MCU_N` has **no
  pull-up anywhere**: Nordic's HDG *nRESET* says an external pull-up is not
  allowed (13k internal to 2.2 V).

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
- ~~Import vendor footprints for BT840 and DWM3001C~~ -- **done 2026-11-18**,
  from the vendors' own files (Resolved, "Footprints from vendor sources").
  Pad naming was checked programmatically: the BT840 footprint has exactly
  the symbol's 65 pad names and the DWM3001C footprint exactly pads 1-48.
  Vendor DWM3001C pin 18 is simply pad "18" in Qorvo's library -- it carries
  no extra information about the pin's function, which the datasheet still
  leaves undocumented in Table 2.
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
  the fixture around that. The procedure is drafted in
  `verification-plan.md` ("Array calibration procedure").
- **Captive vs. detachable antenna assembly.** A user-swappable cable
  invalidates the delay calibration. Leaning captive; confirm against
  serviceability requirements. (This used to be partly a regulatory question
  too -- see the certification entry under Resolved, which removes that half
  of it.)
- **Multi-instance DW3000 driver.** This design drives four DW3210s from one
  host; the common community driver (`br101/dw3000-decadriver-source`) was
  trimmed to one DW3000 per board, and the trimmed Qorvo 08.02.02 API is
  implicitly single-instance. Find the per-chip selector in the untrimmed
  source, else wrap it and swap the global context under a mutex. **The move
  to the nRF9151 removes the old "vendor grain" argument**: Qorvo's reference
  stack targets the nRF52840, and Qorvo publishes no Zephyr/NCS support and no
  TDoA reference for this use (staff reply on the Qorvo forum, 2026-08-10).
  Scope it before it surprises anyone.
- **Is SYNC/OSTR needed at all** now that the clock is genuinely shared? The
  DW3000 **User Manual** (not the datasheet) documents the one-shot timebase
  reset procedure, and could not be obtained on 2026-11-17 (Qorvo rate-limited;
  the same pass could not re-read DW3000 DS v1.3 either). Hardware hedge in
  place: `UWB_SYNC` reaches every anchor through DNP 0R R216-R219; fit them
  only after reading the OSTR section.
- **Mechanical frame design**: the rigid structure carrying the four
  antennas, including the A0 out-of-plane offset (see `positioning.md`).
- **Firmware is on the critical path.** The NCS skeletons, board definitions
  and bridge protocol exist (`firmware/`, Resolved below) but nothing has been
  built or run, and the accuracy target is not met without the array
  calibration routine. Task list in `../firmware/README.md`.

### Everything else

- **Bay station LTE-M uplink backend** -- see "LTE-M service" under Firmware.
  The laptop side is resolved: a framed relay over BLE carrying raw
  timestamps, solved on the laptop (Resolved below).
- **UWB link parameters**: PRF, preamble, data rate, update rate, and
  multi-tag scheduling. (Channel is resolved -- CH5, see below.)
- **Antenna part selection.** UWB candidates covering CH5, existence and band
  confirmed from vendor product pages but full datasheets not yet pulled:
  Taoglas UWC.01 (6-8 GHz SMD chip), ILA.68 (LTCC 6-8.5 GHz), UWCCP.01
  (circularly polarized). Abracon ACR1004U is 3-6 GHz and does **not** cover
  CH5. Verify before BOM. The LTE-M and GNSS antennas are not selected either
  (`components.csv`).
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

## Resolved

### Footprints from vendor sources (2026-11-18)

Rule applied: take pad geometry from a file the vendor itself publishes, then
confirm it against a second artifact (datasheet drawing or Gerber). Nothing
from SnapEDA / SnapMagic / Ultra Librarian / Flux was used.

- **nRF9151 (U20) -- real, from Nordic's DK.** The PDFs on docs.nordicsemi.com
  are behind Cloudflare, but Nordic's *nRF9151 DK Hardware files 1_0_0* ZIP
  (nordicsemi.com > nRF9151-DK > Download, hosted on Nordic's own blob
  storage) holds the DK's Altium `400797.PcbDoc` and Gerbers. The DK's M1 is
  `LGA50P1210X1110X130-113N`. Its 113 pads were parsed out of the binary
  PcbDoc (un-rotating the 270 degree placement) and **all 113 positions and
  sizes were matched against flashes in the same ZIP's top-copper Gerber
  `400797.GTL`**. Pad numbers agree with our symbol: the corner pads 1/20/41/60
  and centre pads 105-113 are all GND in `bay_station:nRF9151`, 81-104 are
  RSVD. Edge pitch is 0.5 mm; the PS "e 0.55" recorded earlier is the pitch of
  the inner RSVD pads. Mask and paste are Altium rules and are not in the
  data, so the large ground pads need a reduced paste aperture chosen with the
  stencil. **Not checked against the PS mechanical figure** (PDF
  unobtainable), so a last look when the PS is in hand is still warranted --
  but this is the footprint Nordic shipped on its own board.
  Footprint `Nordic_nRF9151_LGA-113_12.1x11.1mm_P0.5mm`.
- **BT840 (U3) -- real, from Fanstel.** Fanstel's download page offers
  `BT840.lbr` (Eagle). Package `BT840` has exactly 65 pads and its geometry
  reproduces the datasheet's pp. 9-10 drawings: castellations 1.10 mm pitch
  (1.5 x 0.7 mm, centred on the edge, so 0.75 mm outside the body as the
  "0.75 mm" dimension shows), LGA columns 1.50 mm and rows 1.20 mm apart,
  0.6 mm round signal pads, F0-F3 1.5 x 1.5 mm ground pads at 3.625/2.25 mm,
  F6 a 0.6 mm square. Eagle names (`P$1`, `P$A5`) were renamed to the
  datasheet's (`1`, `A5`), identical to the symbol's pin numbers. This also
  confirms F0-F3 are real pads (see the 65-pin item). The library's extra
  20.8 mm outline is the BT840F's and was not used; the body is the 14 x 16
  mm of Ver 1.15 p. 10. Footprint `Fanstel_BT840_Module_14x16mm_16Cast_49LGA`.
- **DWM3001C (U3, wristband) -- real, from Qorvo.** A Qorvo staff member
  posted Qorvo's own Altium library (`DWM3001C.IntLib` + STEP) on
  forum.qorvo.com (thread 12741, file dated 2023-03-09). The 48 pads were
  parsed from its embedded PcbLib and match DWM3001C Data Sheet Rev B
  Fig. 5: 2.54 x 0.75 mm pads, **1.00 mm pitch on all three edges**, 16.27 mm
  inner gap, last bottom pad 3.10 mm from the right edge. The earlier
  PLACEHOLDER's "1.06375 mm back-derived pitch" was wrong: the 17.77 mm on
  Fig. 5 is the ground-region extent, not the pad span. Pin 1 top-left,
  18-31 bottom, 32-48 right, as in Fig. 1. Footprint
  `Qorvo_DWM3001C_Module_19.13x27.1mm_48Pad`. The datasheet's NON-GROUND
  region above the antenna end still has to be honoured in layout. Only the
  U3 footprint assignment was changed on the wristband sheets.
  `wristband.kicad_pcb` still embeds the old placeholder footprint; run
  *Update PCB from Schematic* with the footprint replaced.
- **TPS63802DLA (U40) -- real land pattern.** The previous estimate came from
  `pdftotext`, which drops the dimension leaders. Reading the *rendered*
  SLVSEU9D pages (drawing 4223750/D) gives: pins 1-5 lands 0.6 x 0.25 mm
  centred 0.9 mm left of the package centreline; pins 6, 7, 9, 10 lands
  0.9 x 0.25 mm centred 0.75 mm right; **pin 8 (GND) a 1.3 x 0.25 mm land**
  spanning from 0.11 mm left of the centreline to 1.2 mm right, with its paste
  as two 0.55 mm apertures. The old placeholder had pin 8 as just another
  0.9 mm land. TI's "Example Board Layout" is itself an example, not a
  mandate, but it is TI's. Footprint `TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm`.
- **FB1-FB4 (BLM03PG330SN1D) -- case size resolved, land pattern not.** 0201
  inch (0603 metric), 0.6 x 0.3 x 0.3 mm, per Murata's naming and every
  distributor listing seen (DigiKey: "0201 (0603 Metric)"; TTI/SnapEDA
  dimensions agree). Assigned stock `Inductor_SMD:L_0201_0603Metric`. The
  Murata PDF could not be fetched, hence the Open item above.

### nRF9151 host redesign (2026-11-17)

- **Bay station host: Nordic nRF9151 SiP; the BT840 stays as a UART BLE
  bridge; the MAX-M10S is removed.** The user's call, 2026-11-17. Reasons:
  - **LTE-M uplink plus built-in GNSS in one part.** The nRF9151 (LTE-M /
    NB-IoT modem + GNSS + Cortex-M33 application core) gives the station a
    cellular path for reports when no laptop is in range, and its GNSS
    replaces the MAX-M10S, so the board loses a module rather than gaining
    one.
  - **The nRF91 has no Bluetooth radio, so the BT840 is kept** -- demoted from
    host to a bridge that relays frames between the nRF9151 (UART, RTS/CTS)
    and the laptop (BLE). Same split as Nordic's Thingy:91 X (nRF9151 +
    nRF5340). The laptop link survives unchanged from the operator's side.
  - **GNSS time-shares with LTE** (fixes only while LTE is idle / PSM /
    eDRX). That is acceptable here because the station is stationary and
    georeferences by survey-in averaging, not by tracking.

  Supersedes the 2026-09-19 "Bay station MCU: Fanstel BT840" entry (as host)
  and widens the "BLE to a laptop, not WiFi to the internet" entry: the
  laptop stays primary and the station must work with no SIM. The net
  contract all sheets wired against is `net-contract.md`; the GPIO allocation
  is `bay-station/connectivity_notes.md` section 2. The MAX-M10S's sheet
  `gnss.kicad_sch` became `orientation.kicad_sch` (entry below).
- **Toolchain: nRF Connect SDK v3.4.x (LTS) for every image**, replacing the
  open "nRF5 SDK vs. Zephyr / NCS" item. Forced by the nRF9151 host: Nordic
  describes the nRF5 SDK as the "Software development kit for the nRF52 Series
  and nRF51 Series SoCs", "in maintenance mode", and recommends NCS "for new
  projects" (nRF5 SDK product page); the nRF9151 download page lists only NCS.
  The BT840 bridge and the wristband's nRF52833 follow for one toolchain. The
  generated pin map is therefore a devicetree, filled from one `*_pins.h` per
  MCU under `firmware/boards/`. `firmware/bay-station/README.md`, "Toolchain".
- **nRF9151 modem firmware pinned at 2.0.4 with NCS 3.4.x.** Nordic's nRF9151
  compatibility matrix (Table 1) lists mfw 2.0.4 against NCS 3.1.0-3.4.0 LTS.
  Modem FW changes only together with NCS, is logged with every test result,
  and is checked by the app at boot via `AT+CGMR`.
- **nRF9151 <-> BT840 link is our own framed relay**, not HCI-over-UART and
  not a transparent NUS pipe. COBS + CRC-16/CCITT-FALSE frames at 1 Mbaud with
  RTS/CTS; the BT840 forwards end-to-end frames verbatim to/from BLE NUS. Keeps
  the BLE host stack off the chip running the modem and the UWB exchange (HCI
  would put it there), and unlike Nordic's connectivity bridge it carries
  message boundaries, integrity and link state.
  `firmware/common/include/uwbrl/bridge_proto.h`.
- **Raw timestamps end to end; the laptop solve is authoritative.** The
  station streams 40-bit DW3000 timestamps with the calibration table's CRC,
  not corrected values; the laptop applies calibration and solves. The station
  runs a quick-look solve only for LTE reports. Raw logs stay re-processable
  with a better calibration. (Closes "where the position solve runs".)
- **All antenna/cable delay lives in the calibration table; the DW3000
  antenna-delay registers are fixed (proposed 0) on all four anchors.**
  Prevents a delay being applied twice. A0 absolute and A1-A3 relative delays
  are separate fields.
- **GNSS first, then LTE; steady state LTE in PSM with GNSS in idle windows;
  A-GNSS optional.** `%XSYSTEMMODE=1,0,1,1` (LTE-M + GNSS, no NB-IoT --
  revisit if coverage needs NB-IoT). GNSS priority mode only after repeated
  `NOT_ENOUGH_WINDOW_TIME` flags, per Nordic's GNSS API guidance.
- **nRF9151 serial instances: UARTE0 = debug UART, UARTE1 = BLE bridge, TWIM2
  = I2C sensors, SPIM3 = UWB.** SPIM/SPIS/TWIM/TWIS/UARTE share four IDs (PS
  *Peripheral instances*) and four serial functions are needed, so every ID is
  used -- there is no spare SPI/UART for anything added later. NCS defaults
  UART **modem trace** and TF-M's log UART to UARTE1, which is the bridge: use
  the RTT trace backend, and the `/ns` builds silence TF-M logging.
- **nRF9151 GPIO allocation is fixed** in `bay-station/connectivity_notes.md`
  section 2, the single source of truth (copied into
  `firmware/boards/.../*_pins.h`). The three MCP73871 status nets go to LEDs
  only: the chip is out of pins, and the nodes idle near `+VSYS`, above
  `VDD_GPIO`. Charge state stays visible through the MAX17048. `LED_LINK` is on
  the BT840. Zero spare GPIOs remain (Open).
- **UWB SPI is 8 MHz max.** That is every nRF91 SPIM instance -- the nrfx MDK
  (`nrf9120_peripherals.h`, `SPIMn_MAX_DATARATE 8`; the nRF9151 uses the
  nRF9120 die in nrfx) -- and no faster instance exists. The DW3000 accepts
  36 MHz, so the host is now the limit. The firmware handoff had this as an
  unverified belief (the PS SPIM page did not load past the 500 kbps rows);
  the MDK settles it, with the PS table still to be read (Open, Nordic PDFs).
  The 32 MHz SPIM3 figure in older notes was nRF52840-specific. Consequence
  for the reply-delay budget is Open.
- **DW3210 SPI mode 0.** R10-R17 are pull-downs on GPIO5/SPIPOL and
  GPIO6/SPIPHA (DW3000 DS v1.1 Table 20), so firmware must use CPOL=0/CPHA=0.
  Start DEV_ID reads slow (2 MHz) -- the DW3000 runs SPI at only 7 MHz in
  INIT_RC (DS v1.1 Table 21).
- **GNSS front end copies the nRF9151 DK.** BGA524N6 LNA (U24) on a
  TPS7A0228 2.8 V LDO (U25) switched by COEX0 (`AT%XCOEX0`), mandatory 1 nF
  DC block (LNA input abs max 0.9 V), DNP bias-tee for an active antenna, DNP
  LNA bypass. No pre-filter (Open). `connectivity_notes.md` section 4.
- **SIM: TI TPD3F303 ESD/EMI filter + GCT SIM8060 nano-SIM**, both named or
  matched against Nordic's HDG *UICC*, with a DNP MFF2 eSIM footprint steered
  by 0R links, as on the nRF9151 DK.
- **nRF9151 `VDD` gets its own buck-boost (`+VBAT_LTE`, TI TPS63802,
  3.59 V).** On battery `+VSYS` is the cell minus Q1 and the MCP73871
  BAT-to-OUT FET (200 mOhm typ, DS20002090E), ~0.3 V at board peak, so a direct
  feed falls under Nordic's 3.2 V LTE recommendation (3.0 V floor "includes all
  voltage drops, ripple, and spikes", nRF9151 HDG) late in the discharge, and
  the path impedance already exceeds the HDG's 0.2 ohm target. The TPS63802
  regulates through the whole 2.9-5.25 V input range, and its PG sequences
  `+3V3` (= nRF9151 `VDD_GPIO`) 12-41 ms later against the HDG's >= 6 ms.
  That sequencing assumes ENABLE is tied to VDD through R101 10k, as wired; if
  host control of ENABLE is ever wanted, redo the `+3V3` delay. Rejected:
  direct jumper (above); TPS63000 (800 mA boost rating too close to 505 mA).
  `bay-station/regulation_notes.md` sections 1-4.
- **Board-level battery UVLO at `+VSYS` = 2.91 V** (TPS63802 EN divider
  191k/100k; on again at 3.20 V). Turns both rails off together. Tune R308
  when the cell and protection IC are chosen.
- **Bay station power budget re-run for the nRF9151 architecture.** `+3V3`:
  ~356 mA peak (~446 mA if the nRF9151 `VDD_GPIO` hits Nordic's 100 mA
  momentary ceiling) vs the TPS62A02's 2 A. `+VBAT_LTE`: 505 mA LTE-M TX
  subframe (nRF9151 HDG, B1, 3.0 V, 85 C, VSWR 3:1) vs the TPS63802's 2 A.
  Table in `bay-station/handoff/power.md`. The budget used ~2 mA / ~25 mA
  estimates for the TCXO and buffer; the proposed parts are 10 mA typ / 15 mA
  max (RPT1490LN) and ~33 mA typ at 100 MHz, less at 38.4 MHz (LMK1C1104),
  about +21 mA worst case -- well inside the >= 4.5x headroom. Still
  estimates: BT840 total and nRF9151 `VDD_GPIO`.
- **SW2 footprint, BOM rows for U8 / SW2 / J3, and L1's footprint.** SW2 (and
  the new SW11/SW12) are Omron B3U-1000P on
  `Button_Switch_SMD:SW_SPST_B3U-1000P`; rows for U8, J3 and the new
  buttons/headers were added to `components.csv`. L1 is now a Coilcraft
  XFL4020-102MEC on KiCad's `L_Coilcraft_XxL4020` instead of the
  footprint-less XGL3520-102MEC. The U8 flattened-symbol warning itself stays
  Open.
- **Li-Ion charging below 0 degC (MCP73871 THERM).** With the MCP73871's own
  tolerances (DS20002090E sec 1.0: ITHERM 47-53 uA, VT1 1.20-1.26 V, VT2
  0.23-0.27 V) a plain 10k NTC with B25/50 = 3380-3435 K suspends charging
  below +1.1..+5.3 C and above +40..+49 C. No trim resistors. The remaining
  requirement is mechanical: the NTC must sit on the cell (use the pack's
  NTC). `bay-station/power_bms_notes.md`, "THERM cold-charge window".
- **TCXO + 1:4 buffer: Rakon RPT1490LN (38.4 MHz, CMOS) + TI LMK1C1104PWR,
  PROPOSED pending availability.** Checked against DW3000 DS Table 10 from
  both PDFs: RPT1490LN typ -151 dBc/Hz @ 1 kHz / -166 @ 10 kHz (Rakon Issue B
  plot), duty 49-51 %; LMK1C1104 skew 50 ps max, ODC 45-55 %, no measurable
  close-in degradation at 3.3 V (SNAS791D Fig 10-3). The Qorvo-listed TCXO
  (TXC 7Z, DS Table 22) was rejected: TXC's own sheet gives -130 dBc/Hz @
  1 kHz, outside Table 10, and its clipped-sine output does not meet an LVCMOS
  buffer input. **`TCXO_EN` omitted**: the RPT1490LN has no enable pin, and
  stopping the clock would stall all four cores anyway. Availability is Open.
  `bay-station/clock_dist_notes.md`.
- **UWB SMA: Linx/TE CONSMA020.042-G edge-mount, PROPOSED.** 0-18 GHz, rated
  IL 0.23 dB / VSWR 1.1 over 5-7.125 GHz (DS21264 Table 3), sized for
  0.042 in boards (this one is 1.048 mm). Footprint PLACEHOLDER; the launch
  needs EM simulation (Open).
- **Status LED drive rails and series resistors** (replaces the indicative
  1k). MCP73871 STAT1/STAT2/PG are open-drain sinks (DS20002090E sec
  3.10-3.12; ISINK max 35 mA, VOL 0.4 V typ @ 4 mA), so the LED anode rail is a
  choice, constrained two ways: every pin's abs max is -0.3 V to VDD+0.3 V with
  VDD = VIN or VBAT, and **PG "must not be pulled up higher than VIN because
  there is a diode path back to VIN"** (sec 5.2.4). Hence D4 (STAT1, red) and
  D5 (STAT2, green) from `+VSYS` through 1.5k (~2 mA on adapter, ~1.1 mA on
  battery), D6 (PG, blue) from `+5V_IN` through 1k (~2.2 mA). The host/radio
  LEDs D7 `LED_SYS`, D400 `LED_LTE`, D401 `LED_LINK` are GPIO-sourced, active
  high, 1.2k for ~1.1 mA (0.7-1.5 mA spread). The io handoff's caveat that this
  assumed 3.3 V I/O is closed by the connectivity sheet: `VDD_GPIO` = `+3V3`,
  and nRF9151 standard drive guarantees IOH >= 1 mA at VDD-0.4 V (typ 2 mA;
  PS *GPIO*) -- at the edge of the guaranteed minimum, so firmware may set
  H0H1 if the LEDs look dim. Parts are Kingbright low-current 0805s specified
  at IF = 2 mA, VF read from each datasheet (`components.csv`).
- **Clock test pads behind DNP 0R.** Supersedes "keep TP5-TP9 as minimal pads
  on the existing routing" (test-points entry below). TP5-TP9 reach `TCXO_OUT`
  / `UWB_CLK0-3` only through DNP 0402 0R links R402-R406 whose pad sits on
  the trace; the default build carries one unfitted 0402 pad per clock net
  and no probe stub. Fit to probe, then remove. If layout cannot take all four
  anchor links, keep A0/A1 (R403/R404).
- **Test-point coverage: every net-contract net.** 66 pads: all of
  `net-contract.md` sections 1-7 on `testpoints.kicad_sch` (TP1-TP21,
  TP100-TP175), far-end rail pads, GND spring pairs at the clock and SPI bus,
  one GND per area, plus TP121 on `+3V3_SNS`. Rails/GND D1.5, signals D1.0.
  TP135 (`TCXO_EN`) was deleted with the enable. Also fixed: TP1-TP14 had been
  stacked on shared coordinates, which shorted unrelated test points together
  on the schematic. Sheet-local pads use their own blocks (mcu TP40-TP53,
  power TP400-TP417, uwb TP500-TP530, the last renumbered from TP400-TP430 at
  merge). Index: `verification-plan.md`, "Test-point index".
- **Orientation sheet (was GNSS / Orientation).** MAX-M10S U9 and its C32-C34
  removed (GNSS now from the nRF9151); `gnss.kicad_sch` renamed
  `orientation.kicad_sch`, same sheet UUID. LIS3MDL strapped to 0x1C and LIS2DH
  to 0x19, distinct from the MAX17048's fixed 0x36 (19-6171 Rev 7); each
  sensor has its own SCL/SDA 0R and a shared `+3V3_SNS` current break.

### Earlier decisions

- **Footprint convention: component Value on real silkscreen (F.SilkS), for
  every part, both boards.** Decided 2026-11-06. Previously inconsistent on
  the wristband (the only board with footprints placed): some Values hidden
  entirely, some visible but on F.Fab (CAD/Gerber-viewer only, not printed on
  the physical board) -- a non-obvious, undocumented split rather than a
  deliberate choice.

  **Known cost, accepted rather than worked around:** 0402/0603 passive
  values often don't fit cleanly in real silkscreen text at standard size.
  Applying this to the wristband's 36 already-placed footprints moved DRC's
  `silk_over_copper` from 57 to 91 and `silk_overlap` from 7 to 71 (kicad-cli
  10.0.5, 2026-11-06). Resolving those overlaps is layout work (repositioning
  text, shrinking font, or moving some values to F.Fab after all on a
  per-part basis) -- it is not a reason to hide the values again, and no
  such per-part exception has been made yet.

  Applies going forward to the bay station too, which has no footprints
  placed yet -- when they land, Value should go straight to F.SilkS rather
  than needing a second pass.

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

  Not selected or costed yet, and it does not cover what a box cannot: BOM
  temperature range and RF transparency (for the BT840's on-module BLE
  antenna, and for the LTE-M/GNSS antennas unless they are mounted outside).
  Both stay Open above; cold charging was resolved separately on the THERM
  side (2026-11-17).

- **GNSS + orientation added to the bay station** (`gnss.kicad_sch`, new
  sheet). Resolved 2026-09-23. **The GNSS half was superseded 2026-11-17**:
  the MAX-M10S (U9) was removed in favour of the nRF9151's built-in GNSS and
  the sheet is now `orientation.kicad_sch` (see the redesign entries above).
  The reasoning for position *plus heading* below still holds unchanged; the
  MAX-M10S-specific paragraphs are kept as history.

  The station is deployed outdoors and moved
  between sites, and the array only ever produced position RELATIVE to its
  own frame -- fine for an operator standing at it, useless as a coordinate
  to hand anyone else.

  **Position alone was not enough, and this is the part that is easy to
  miss.** A GNSS fix says where the station is, not which way it faces. The
  array reports a bearing relative to the frame, so without heading you get a
  circle of possible tag locations rather than a point. Hence three parts,
  not one:
  - **U9 u-blox MAX-M10S** -- where the station is. *(Removed 2026-11-17;
    the nRF9151 GNSS does this now.)*
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
  that relative UWB positioning does not. Averaging is host-side (on the
  BT840 then, on the nRF9151 now) -- u-blox's own "Survey-In" is a
  timing/RTK-part feature, not M10
  standard-precision, and host averaging is equivalent for static
  self-positioning without a pricier module.

  *(History, MAX-M10S only.)* Pin data verified against u-blox Data Sheet
  UBX-20035208 R02 Table 9:
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

  Bay station, originally 14 points chosen against this design's actual
  risks: the shared clock (TP5 at the TCXO, TP6-TP9 at each DW3210 XTI -- if
  the reference is missing at one anchor, TDoA produces nonsense rather than
  failing loudly), the SPI bus and anchor IRQ/reset for the multi-instance
  driver work, both power rails, and **two** grounds. TP3 is deliberately
  sited next to the clock points so a scope can use a short ground spring:
  at 38.4MHz a flying clip lead's inductance distorts the measurement.

  **Expanded to 21 points, 2026-11-06.** The original 14 probed the shared
  SPI bus and only A0's IRQ -- enough to see traffic, not enough to debug the
  multi-instance driver, since the bus alone doesn't show which anchor is
  being addressed and only one of four IRQs was visible. Added TP15-TP18
  (CS_A0-CS_A3) and TP19-TP21 (IRQ_A1-IRQ_A3): every anchor's chip-select and
  interrupt now has its own point instead of one anchor standing in for all
  four. None of these touch the clock network, so the stub caution below is
  unaffected.

  Wristband, 5: both rails, two grounds, and a firmware timing marker on a
  spare GPIO so tag-side exchange timing is visible on a scope.

  **Layout caveat recorded on the sheet** *(superseded 2026-11-17: the clock
  pads now sit behind DNP 0R links, see "Clock test pads behind DNP 0R"
  above)*: a test point on the clock network is a stub, and stubs degrade
  the very signal integrity this design depends
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
  2026-09-19. **Widened 2026-11-17**: the nRF9151 host adds an LTE-M path on
  top, while the BLE laptop link stays primary and the station must work with
  no SIM (redesign entries above). The rest of this entry is the 2026-09-19
  reasoning. The station now talks Bluetooth LE to a nearby computer. Note
  this is a real scope change from the original concept, which had the bay
  station uploading position data to the internet -- that is no longer what
  it does, and `system-overview.md` has been corrected accordingly.

  Confirmed with the team that a laptop will always be present, which is what
  made the MCU change below possible. **If that ever stops being true, both
  decisions reopen together.** (They did reopen together on 2026-11-17, in the
  direction of adding LTE-M rather than WiFi.)

  Two consequences worth knowing: BLE range reaches a nearby laptop, not a
  router, and Nordic parts are BLE-only with no Classic/SPP -- so the link is
  a GATT service (or USB-CDC over a cable, which is simpler still and worth
  considering since the station is wired for power anyway).
- ~~**Bay station MCU: Fanstel BT840 (Nordic nRF52840)**~~ -- **SUPERSEDED AS
  HOST 2026-11-17 by the nRF9151**; the BT840 stays on the board as the UART
  BLE bridge (redesign entries above). Kept for the reasoning, and because the
  package and symbol notes below still apply to U3. Replaced
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
  can signal ranging/fault. Resistor values and drive rails were indicative
  here; the bay station's were resolved 2026-11-17 ("Status LED drive rails
  and series resistors" above), and the board now also has D400 `LED_LTE` and
  D401 `LED_LINK`.
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
  - Wristband: **TI TPS7A0233PDBVR** LDO (fixed 3.3V, SOT-23-5),
    `wristband/regulation.kicad_sch`. **Replaced Microchip MCP1700T-3302E/TT
    on 2026-09-23.** The regulator is still required (battery reaches 4.2V,
    DWM3001C tops out at 3.6V operating / 4.0V abs max), but the MCP1700's
    1.6uA typ / 4uA max quiescent current had become the largest single
    standby draw on the board -- more than the DWM3001C's own 850nA sleep.
    TPS7A02 is 25nA typ / 46nA max at 25C, 3nA shut down, and also improves
    accuracy to +/-1.5% over temperature. Board standby ~4.3uA -> ~2.7uA.
    Verified against TI SBVS277C.

    Trade-offs accepted: 200mA rating instead of 250mA, ~$0.78 instead of
    ~$0.16, and a 5-pin package with an EN input that must be tied high
    (TPS7A02 is disabled when EN floats; it cannot be GPIO-driven, because
    the MCU it powers cannot enable its own supply). A buck converter was
    considered and rejected -- at this load it trades a few points of
    efficiency for an inductor, higher Iq and switching noise next to a UWB
    receiver.

    Load re-run 2026-09-19 for the DWM3001C: module 40mA (CH5 TX or RX,
    DWM3001C Datasheet Rev B Table 5) + D3 status LED ~3mA = **~43mA**,
    against the TPS7A02's 200mA rating -- 4.6x headroom.

    **Open follow-up:** with the LDO down to tens of nA, the 2MOhm R11/R12
    battery-sense divider (~1.85uA) is now the dominant standby term.
  - Bay station: **TI TPS62A02PDDCR** buck converter (2A, single-cell-Li-Ion
    input range), `bay-station/regulation.kicad_sch`. Current budget:
    **Re-run 2026-09-19 for the discrete architecture**: ESP32-S3-WROOM-1
    (~355mA peak TX) + 4x DW3210 (72mA each, CH5 RX peak, DW3000 Datasheet
    v1.3 Table 5) + clock network (~27mA, estimated) + status LEDs (~12mA)
    = **~682mA vs. 2A rating, ~2.9x headroom**. The part choice survives;
    no regulator change needed. Full working in
    `bay-station/regulation_notes.md`. *(This ESP32-era budget is superseded
    by the 2026-11-17 re-run for the nRF9151 architecture above, which also
    adds the TPS63802 `+VBAT_LTE` rail.)*
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
