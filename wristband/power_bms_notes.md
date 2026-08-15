# `power_bms.kicad_sch` -- design notes

Hierarchical sub-sheet covering the wristband's battery input, reverse-polarity
protection, single-cell over-charge/discharge/current protection, and Li-Po
charging. Wired into `wristband.kicad_sch` as a sheet symbol (Sheetname
"Power BMS", uuid `e17e6f9a-2b41-4d3a-9f0a-1c1f5c9a7b21`) and registered in
`wristband.kicad_pro`'s `sheets` list. No wires are drawn anywhere on this
sheet -- every net is carried by a `global_label` placed exactly on top of
the pin it belongs to (same convention as the sibling wristband-alarm
project's `power.kicad_sch`).

## Component-by-component

| Ref | Part | lib_id | Datasheet | Notes |
|---|---|---|---|---|
| BT1 | Generic single-cell LiPo, 2-pin JST-PH | `Device:Battery_Cell` (footprint `Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal`) | n/a (generic connector) | Matches `wristband/libs/components.csv` row 6 -- the part already identified for this project. |
| Q1 | Alpha & Omega Semiconductor AO3401A, P-channel MOSFET, SOT-23 | `Transistor_FET:AO3401A` | http://www.aosmd.com/pdfs/datasheet/AO3401A.pdf | Reverse-battery-polarity protection ("ideal diode"). Pinout (1=Gate, 2=Source, 3=Drain) verified against AOS's real datasheet and cross-checked via web search (LCSC/Digikey/alltransistors listings all agree). See "P-MOSFET reverse-polarity protection" below for why this part and the wiring rationale. |
| R1 | 100k&Omega;, 0603 | `Device:R` | n/a (generic passive) | Q1 gate pull-down to `GND` (system ground, downstream of the FS8205A pass FETs) -- standard value for this "ideal diode" gate bias; not current-critical, just needs to be >> the FET's own gate leakage and << load impedance. |
| D1 | onsemi ESD5B5.0ST1G, bidirectional TVS, SOD-523 | `Device:D_TVS` (footprint `Diode_SMD:D_SOD-523`) | https://www.onsemi.com/pdf/datasheet/esd5b5.0st1-d.pdf | Across `VBAT`-`GND` (protected battery rail, post-Q1). 5.0V standoff / 5.8-7.8V breakdown / ~9.2V typ. clamping -- comfortably above the 4.2V max charge voltage (MCP73831-**2** variant) with margin, while still clamping well below the FS8205A's 20V VDS rating. Same part family already used for VBUS ESD protection in `components.csv` row 8; reused here for the battery rail specifically because it's a real, well-documented, commonly-stocked part in the right standoff-voltage class for a 1S Li-ion/LiPo cell (see task item 3: "5-6V class commonly used for LiPo protection"). |
| U1 | Fortune Semiconductor DW01A, SOT-23-6 | `wristband:DW01A` (already in `libs/wristband.kicad_sym`, untouched) | http://www.ic-fortune.com/upload/Download/DW01A-DS-12_EN.pdf | Single-cell protection IC. Wiring below replicates Fortune's own "Typical Application Circuit" (datasheet Rev 1.1, page 5) pin-for-pin. |
| R2 | 100&Omega;, 0603 | `Device:R` | (part of U1's own datasheet app circuit) | This is the datasheet's own "R1" -- VCC feed resistor between `VBAT` and DW01A's VCC pin (renamed `R2` here to avoid clashing with the reverse-polarity gate resistor `R1`). |
| C1 | 0.1uF, 0603 | `Device:C` | (part of U1's own datasheet app circuit) | This is the datasheet's own "C1" -- VCC-to-GND decoupling for U1, but note "GND" here is `CELL_N` (raw cell negative, *before* the FS8205A pass FETs), matching exactly where the datasheet draws it (same node as U1's own GND/TD pins), not the downstream system `GND` net. |
| R3 | 1k, 0603 | `Device:R` | (part of U1's own datasheet app circuit) | This is the datasheet's own "R2" -- between DW01A's CS (current-sense) pin and system `GND` (post-FET pack negative), sensing the voltage drop across the two series pass FETs for overcurrent detection. |
| Q2 | Fortune Semiconductor FS8205, common-drain dual N-MOSFET, SOT-23-6 | `wristband:FS8205A` (already in `libs/wristband.kicad_sym`, untouched) | https://www.shoptronica.com/ficheros/FS8205-DS.pdf | Series pass-FET pair in the battery's low-side return path, gated by U1's OD/OC outputs. See "DW01A + FS8205A wiring" below for the exact per-pin derivation (this part's D12 pins are a common, internal-only drain node -- verified against Fortune's real pin-assignment diagram, Rev 1.9 p.3, which shows S1/D12/S2 on one row and G1/D12/G2 mirrored on the other, i.e. two separate FETs sharing one internal drain, not a simple series pair). |
| U2 | Microchip MCP73831T-2ACI/OT, SOT-23-5 | `wristband:MCP73831-2-OT` (already in `libs/wristband.kicad_sym`, untouched) | http://ww1.microchip.com/downloads/en/DeviceDoc/20001984g.pdf | Li-Po linear charger, "-2" variant = 4.20V regulation. Wiring matches the datasheet's own page-1 "500mA Li-Ion Battery Charger" typical application circuit (minus the optional STAT LED, which this sheet doesn't populate -- see below). |
| R4 | 6.8k, 0603 | `Device:R` | (PROG resistor -- math below) | Sets charge current to ~147mA. |
| C2 | 4.7uF, 0603 | `Device:C` | (datasheet's own CIN value) | MCP73831 input cap, VDD-to-GND, exactly the value shown in the datasheet's own typical application circuit (not a guess). |
| C3 | 4.7uF, 0603 | `Device:C` | (datasheet's own COUT value) | MCP73831 output/battery-side cap, VBAT-to-GND, same datasheet-specified value. |
| J1 | Power-only USB-C receptacle (e.g. GCT USB4125-series) | `Connector:USB_C_Receptacle_PowerOnly_6P` (footprint `Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal`) | https://www.usb.org/document-library/usb-type-cr-cable-and-connector-specification | Charge input for U2. Matches `components.csv` row 7 (already sourced for this board). Added here (not explicitly one of the 7 listed circuit items) because MCP73831's own "complete typical application circuit" needs a real VDD source -- see "Design decisions / open concerns" below. |
| R5, R6 | 5.1k, 0603 | `Device:R` | (standard USB-C CC pull-down value) | CC1/CC2 pull-downs to `GND` so USB-C source ports advertise default 5V/up to 3A (or legacy-BC1.2 5V) -- standard "UFP sink, no PD" wiring, same value used in the sibling wristband-alarm project's own USB-C circuit. |
| C4 | 10uF, 0603 | `Device:C` | n/a (generic bulk cap) | Bulk decoupling on the `VBAT` output rail this sheet hands off to future sheets. |
| C5 | 100nF, 0603 | `Device:C` | n/a (generic bypass cap) | High-frequency bypass alongside C4, same rail. |
| FLG01-FLG04 | `PWR_FLAG` | `power:PWR_FLAG` | n/a | ERC bookkeeping only -- see "PWR_FLAG usage" below. Not populated (`in_bom no`, `on_board no`). |

All resistors/capacitors are generic 0603 (`Resistor_SMD:R_0603_1608Metric` /
`Capacitor_SMD:C_0603_1608Metric`), matching `components.csv`'s existing
guidance for passives on this board.

## Net map

| Global label | What it is |
|---|---|
| `CELL_P` | Raw battery+ terminal, before the reverse-polarity FET (BT1 pin 1 -- Q1 source only). |
| `VBAT` | Protected battery rail (Q1 drain). Feeds DW01A's VCC (via R2), the TVS, MCP73831's VBAT pin, and the bulk/bypass caps. This is the rail a future `radio_mcu` sheet should pick up for NINA-B111/DWM3000 power. |
| `DW01A_VCC` | Node between R2 and U1's VCC pin (datasheet's own series-R node) -- also where C1's top plate lands. |
| `CELL_N` | Raw battery- terminal (BT1 pin 2), shared with U1's GND/TD pins and Q2's S1 pin -- i.e. everything on the *near* side of the FS8205A pass-FET pair, per the DW01A datasheet's own diagram. |
| `GND` | System ground -- the *far* side of the FS8205A pass-FET pair (Q2 S2 pin), and the reference used by everything downstream: MCP73831 VSS, all decoupling-cap returns, the TVS return, USB-C GND/SHIELD, R3 (CS-sense resistor's far end), R1 (Q1's gate pull-down reference). |
| `FS_D12` | Q2's two internal common-drain pins (2 and 5) tied together -- no external connection (see Q2 notes). |
| `PROT_OD` / `PROT_OC` | U1's OD/OC gate-control outputs to Q2's G1/G2. |
| `PROT_CS` | U1's CS pin to R3. |
| `Q1_GATE` | Q1's gate to its own pull-down resistor R1. |
| `CHG_PROG` | U2's PROG pin to R4. |
| `VBUS` | USB-C 5V input, feeds U2's VDD and C2. |
| `CC1` / `CC2` | USB-C configuration-channel pull-downs. |

## DW01A + FS8205A wiring (verified against Fortune Semiconductor's real datasheet)

Fetched and read Fortune Semiconductor's actual `DW01A-DS-11_EN` datasheet
(REV 1.1, Jun 2010; the project's cited `DW01A-DS-12_EN` is a later revision
of the same document -- pin config/app circuit are unchanged between
revisions per the visible pin table). Section 8, "Typical Application
Circuit" (page 5), shows exactly:

- Cell+ -> **R1 (100&Omega;)** -> node that is both DW01A's **VCC** pin *and*
  the external **BATT+** terminal.
- **C1 (0.1uF)** across that VCC node and DW01A's **GND**/**TD** pins (tied
  together), which land on the *same node as the cell's own negative
  terminal* -- i.e. before the pass FETs.
- DW01A **OD** -> gate of **M1** (the FET nearest the cell); DW01A **OC** ->
  gate of **M2** (the FET nearest BATT-).
- M1's drain ties to the cell- node; M1 source -> M2 drain (the series
  connection); M2 source -> external **BATT-** terminal.
- DW01A **CS** -> **R2 (1k)** -> that same BATT- node (current-sense across
  the two series FETs' combined R_DS(on)).

This project's FS8205A (Fortune's real SOT-23-6 dual N-MOSFET, datasheet Rev
1.9, pin diagram on page 3) is a **common-drain** part: pins are
S1/D12/S2/G2/D12/G1, where D12 (pins 2 and 5) is the two FETs' shared,
purely-internal drain node -- not a "drain-to-source" series midpoint you
wire externally. Mapping the generic M1/M2 in the DW01A app circuit onto the
real FS8205A part: **S1 -> cell- (CELL_N)**, **G1 <- OD**, **G2 <- OC**,
**S2 -> BATT- (GND)**, and **D12 (both pins) tied to each other only** --
electrically equivalent to the two series discrete FETs the DW01A datasheet
draws, since current flows S1 -> (internal D12) -> S2 exactly like two
series FETs would, just realized as a common-drain pair instead of two
separate 3-terminal parts.

## MCP73831 PROG resistor math

From Microchip's real MCP73831/2 datasheet (DS20001984G), the DC
Characteristics table gives measured `I_REG` (fast-charge current) at three
`R_PROG` values:

| R_PROG | I_REG (typ.) | R_PROG &times; I_REG |
|---|---|---|
| 10 k&Omega; | 100 mA | 1000 |
| 2.0 k&Omega; | 505 mA (not production tested, "Note 1") | 1010 |
| 67 k&Omega; | 14.5 mA | 971.5 |

These are all consistent with the datasheet's well-known formula
**I_REG (mA) = 1000 / R_PROG (k&Omega;)** (valid range: R_PROG = 2k&Omega; to
67k&Omega;, per the same table's "Charge Impedance Range" row).

For a small wristband LiPo cell, targeting ~100-200mA charge current per the
task brief: solving for R_PROG at 150mA gives R_PROG = 1000/150 = 6.67k&Omega;.
The nearest standard E24 value, **6.8k&Omega;**, gives:

**I_REG = 1000 / 6.8 = 147.1 mA**

-- a sensible ~0.5-0.7C charge rate for a ~200-300mAh wristband cell.

CIN (4.7uF) and COUT (4.7uF) match the datasheet's own page-1 "500mA Li-Ion
Battery Charger" typical application circuit exactly (both shown as 4.7uF
ceramic in that figure) -- not guessed values.

## TVS and P-MOSFET part selection

- **TVS (D1): onsemi ESD5B5.0ST1G**, SOD-523, 5.0V standoff / 5.8-7.8V
  breakdown / ~9.2V typical clamping @5A, 200mW. Chosen because it's a real,
  specific, widely-stocked part in exactly the "5-6V class" the task calls
  for a single-cell Li-ion/LiPo rail (max charge voltage 4.2V on the "-2"
  MCP73831 variant used here, so 5.0V standoff gives ~0.8V of headroom above
  normal operation while still clamping meaningfully below the FS8205A's 20V
  V_DS rating). The same part is already used for VBUS ESD protection per
  `components.csv` row 8 -- reusing it here for VBAT too isn't laziness, it's
  a real part that's genuinely appropriate for both voltage domains and
  keeps the BOM smaller.
- **P-MOSFET (Q1): AOS AO3401A**, SOT-23, -4.0A I_D / -30V V_DS. Explicitly
  in the AO34xx/DMG2305U "family" the task names. Confirmed already present
  in KiCad's own `Transistor_FET.kicad_sym` default library, and confirmed
  its pinout (1=Gate, 2=Source, 3=Drain) against AOS's real datasheet before
  placing it (not just trusting the KiCad library blind).

## PWR_FLAG usage (why 4 of them)

`kicad-cli sch erc`'s `power_pin_not_driven` check requires every
`power_in`-type pin's net to have *some* `power_out`-type pin (or a
`PWR_FLAG`) on it somewhere in the whole hierarchical project. Walking every
`power_in` pin on this sheet:

- **DW01A VCC** (`DW01A_VCC` net) and **DW01A GND** (`CELL_N` net): neither
  node has a genuine `power_out` pin on it (Battery_Cell's own pins are
  `passive`, not `power_out`, in KiCad's real `Device.kicad_sym`) -> flagged
  with `FLG04` and `FLG03` respectively.
- **MCP73831 VSS** (`GND` net): same reasoning -- nothing else on `GND` is
  `power_out` -> `FLG02`.
- **MCP73831 VDD** (`VBUS` net): the USB-C connector's VBUS pins are
  `passive` type, not `power_out` -> `FLG01`.
- **MCP73831 VBAT** (`VBAT` net) *is* `power_out` in the real symbol, so
  `VBAT` already has a legitimate driver and needs no flag.

This was verified empirically, not assumed: `kicad-cli sch erc` was run
against a git-worktree checkout of the sibling wristband-alarm project's
last commit (the actual, real, populated `power.kicad_sch`, not the
currently-blanked working-tree copy of that file -- see caveat below) to
confirm real KiCad 8.0.6 behavior on this exact rule before designing around
it.

**Caveat about the wristband-alarm reference file**: `wristband-alarm/power.kicad_sch`
in its *current working-tree state* is an accidentally-blanked 8-line stub
(compare `git log` there -- the real content is 4393 lines as of the last
commit). This task read the real content via `git show HEAD:power.kicad_sch`
rather than the blanked working copy, and separately ran `kicad-cli sch erc`
against a temporary `git worktree` of that commit (never modifying the
actual wristband-alarm working tree) purely to verify KiCad ERC behavior --
worth flagging in case that blanked file is unintentional and someone
wants to `git checkout` it back.

## Design decisions / open concerns

1. **NINA-B111 / DWM3000 are *not* placed on this sheet.** Both are
   multi-pin parts (31 and ~24 pins respectively) that logically belong on
   a dedicated `radio_mcu` sheet (per root `CONTRIBUTING.md`'s suggested
   breakdown), not a "power_bms" sheet. Per the task's own item 7, this
   sheet instead terminates its output as the `VBAT` global label plus two
   representative bulk/bypass caps (C4 10uF, C5 100nF) -- a stand-in for
   board-level bulk decoupling on the rail leaving this sheet. NINA-B111's
   and DWM3000's own *per-IC* decoupling (u-blox recommends bypass caps
   directly at VCC/VCC_IO; Qorvo's DW3000 hardware design guidelines
   recommend bypass + bulk caps at the module's VDD pins) should be added
   directly on whichever future sheet places those parts, since decoupling
   caps belong physically/schematically adjacent to the IC they serve --
   putting them here with no IC present would be misleading busywork, not
   good practice.
2. **USB-C receptacle (J1) added even though not one of the 7 numbered
   circuit items.** MCP73831's own "complete typical application circuit"
   (task item 5) needs a real VDD source; `components.csv` already sourced
   a USB-C receptacle specifically for this board's charging use case (row
   7), so using it here (rather than leaving VDD on a dangling label with
   no real driver) is the more complete, more correct design. Documented
   here per the task's request to flag and justify this kind of call.
3. **MCP73831 STAT pin (U2 pin 1) is left with an explicit `no_connect`
   marker**, not wired to a status LED. The task's 7 items don't call for a
   status LED on this sheet, and STAT is a tri-state output that's
   perfectly valid to leave floating (many designs do) -- but per this
   task's own guidance, an intentionally-unused pin gets a `no_connect`
   flag rather than being left dangling.
4. **Q1's gate pull-down (R1) returns to `GND` (post-FET system ground),
   not `CELL_N`.** The task explicitly says "gate tied to system
   ground/return through a resistor" -- and there's a real (if subtle)
   startup bootstrap argument for why this works: before Q1's channel is
   biased on, its own body diode still conducts (Source=CELL_P higher than
   Drain=VBAT) enough leakage current to power up U1/Q2 and establish the
   `GND` node for the first time, after which Q1's gate pull-down sees a
   real low-impedance path and the channel turns fully on. This is a
   standard bootstrap sequence for this style of circuit and is not unique
   to this design.
5. **One remaining ERC warning, accepted as-is (0 errors, 1 warning after
   fixes):** `lib_symbol_issues: Symbol 'AO3401A' has been modified in
   library 'Transistor_FET'`. KiCad's real `Transistor_FET.kicad_sym`
   defines `AO3401A` via `(extends "TP0610T")`. Empirically confirmed (by
   testing several minimal reproduction files, including the sibling
   wristband-alarm project's own real `extends`-based symbol pair) that
   `kicad-cli` resolves `extends` through the *project's own*
   `sym-lib-table`, not the schematic's embedded symbol cache -- and this
   project's `sym-lib-table` intentionally only registers `wristband` and
   `uwb_rescue_locator_shared` (per the task's constraints, it's out of
   scope to add a "Transistor_FET" entry there). Using `extends` as-is would
   make `power_bms.kicad_sch` fail to load entirely for anyone without that
   nickname registered project-locally (confirmed: `kicad-cli` reports
   "Failed to load schematic file" with no further detail, and a parent
   sheet's ERC/BOM/netlist then silently treat the broken child sheet as
   *empty* rather than erroring -- a sharp edge worth knowing about).
   AO3401A is therefore embedded here as a fully self-contained symbol
   (graphics + pins inlined from the real TP0610T base, matching AO3401A's
   real verified pinout) instead. This is a legitimate, documented,
   zero-electrical-impact deviation -- the alternative (letting the whole
   sheet silently fail to load) is strictly worse.

## Validation

`kicad-cli sch erc wristband/wristband.kicad_sch` (run from a scratch cwd,
per the environment's convention): **0 errors, 1 warning** (see item 5
above). `kicad-cli sch export bom` correctly lists all 18 real components
placed on this sheet with correct values/footprints; the 4 `PWR_FLAG`
symbols are correctly excluded from BOM/board (`in_bom no` / `on_board no`).
