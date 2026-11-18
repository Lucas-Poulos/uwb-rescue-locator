# Handoff: io agent (orientation, indicators, testpoints, mechanical, root)

Branch: `worktree-agent-a7426cfbb677d0e64` (merged `redesign/nrf9151-host` for
`docs/net-contract.md` first). All five sheets were regenerated from small
Python emitters kept in the session scratchpad (not committed -- this board's
sheets are hand-edited, and the emitters only reproduce the existing KiCad 10
s-expression format). Existing symbol UUIDs were kept for every surviving part
(U10, U11, C35, C36, D4-D7, R29-R32, TP1-TP21, H1-H4).

## 1. Summary of changes

### ERC (kicad-cli 10.0.5, run from scratch dir on `bay-station.kicad_sch`)

| | Total | Errors | Warnings | BOM rows (`sch export bom`) |
|---|---|---|---|---|
| Before | 596 | 572 | 24 | 141 parts |
| After  | 534 | 483 | 51 | 206 parts |

Per sheet, before -> after: GNSS/Orientation **66 -> 0**, Indicators **16 -> 0**,
Test Points **7 -> 0**, Mechanical 0 -> 0. Root `/` 16 -> 43: the increase is
37 `isolated_pin_label` warnings, one per contract net whose only connection
in *this* worktree is my test pad (the owning sheets have not placed their
labels yet -- they clear as connectivity/uwb/clock/power merge), plus the
pre-existing `FG_SCL`/`FG_SDA` labels on power_bms. The 6 Device:LED
`lib_symbol_mismatch` warnings are gone (re-embedded the KiCad 10 LED
symbol); 5 mismatches + the TPS62A02 `lib_symbol_issues` on other sheets are
untouched. Component count did not drop to zero (no `extends` failure).

### `gnss.kicad_sch` -> `orientation.kicad_sch` (sheet name "Orientation")

- **Removed** U9 MAX-M10S and C32 (U9 VCC 100nF), C33 (U9 bulk 1uF), C34
  (U9 V_BCKP 100nF). Each one's Description said it decoupled U9 only;
  checked before deleting. C35/C36 kept (they were U10/U11 Vdd caps).
- Root `Sheetfile` -> `orientation.kicad_sch`, `Sheetname` -> `Orientation`;
  `bay-station.kicad_pro` `sheets` list name updated to match. File is a
  new git path (`git rm gnss.kicad_sch`), same sheet UUID, so instance paths
  are unchanged. Paper A4 -> A3.
- **U10 LIS3MDL** (DocID024204 Rev 4, read from the real PDF -- ST's own site
  refused the download, copy taken from Pololu's mirror of the ST datasheet):
  Table 2 pinout matches KiCad's stock symbol (checked `-raw`; `-layout`
  agrees). Vdd + Vdd_IO -> `+3V3_SNS`; CS -> Vdd_IO ("CS line must be tied
  high", sec 5.1); SDO/SA1 -> GND via R412 = **0x1C** (sec 5.1.1), DNP R413
  to Vdd_IO for 0x1E; C1 pin 4 -> C400 100nF (Table 2 / sec 4.1, mandatory);
  Vdd C35 100nF + C401 1uF (sec 4.1 / Figure 5); C402 100nF on Vdd_IO
  (extra, not in Figure 5); DRDY -> `MAG_DRDY`, INT -> `MAG_INT`; GND/Reserved
  pins 2,3,12 -> GND.
- **U11 LIS2DH** (Doc ID 022516 Rev 1, Nov 2011, from a distributor mirror):
  Table 2 pinout matches KiCad stock symbol (pins 10-14 "Res, connect to
  GND" -> GND). Vdd + Vdd_IO -> `+3V3_SNS`; CS -> high ("When using the I2C,
  CS must be tied high", sec 3); SDO/SA0 -> Vdd_IO via R414 = **0x19**
  (sec 5.1.1 / Table 14), DNP R415 to GND for 0x18 -- high chosen because SDO
  has an internal pull-up; C36 100nF + C403 10uF at pin 8 (sec 3: "100 nF
  ceramic, 10 uF aluminum"); C404 100nF Vdd_IO (extra); INT1 -> `ACC_INT1`,
  INT2 -> `ACC_INT2`.
- **Addresses vs MAX17048:** MAX17048 is fixed **0x36** (19-6171 Rev 7,
  "Slave Address": `0110110`, 0x6C/0x6D with R/W). 0x36 / 0x1C / 0x19 are
  distinct, and so are both alternate strap positions (0x1E, 0x18).
- **Rework:** R407/R408 (U10 SCL/SDA) and R409/R410 (U11 SCL/SDA) 0R links
  from `I2C_SCL`/`I2C_SDA`; R411 0R `+3V3` -> `+3V3_SNS` current-measure break
  with local test pad TP121 and a PWR_FLAG (#FLG400, ERC only).
- Sheet notes rewritten (old text described U9 and a BT840 host): why the
  sheet exists, I2C address table with citations, **magnetometer keep-out
  guidance** (buck inductor >= 25 mm, LTE feed / `+VBAT_LTE` >= 20 mm,
  battery/charger loops out of the footprint, no steel, verify by logging
  heading with LTE + charger cycling -- the mm figures are my engineering
  guidance, ST only says ">10 mA a few mm away", sec 4.3), and a verified/not
  block.

### `indicators.kicad_sch`

Wired. Drive topology decided from the MCP73871 datasheet (DS20002090E):

| LED | Net / drive | Rail | Part | R | I (typ, range) |
|---|---|---|---|---|---|
| D4 | `nSTAT1_LBO` sinks | `+VSYS` | Kingbright APT2012LSECK/J3-PRV hyper red | R29 1.5k | 2.0 mA adapter; 1.1 mA at VBAT 3.6 V |
| D5 | `nSTAT2` sinks | `+VSYS` | Kingbright APTD2012LCGCK green | R30 1.5k | 1.9 mA (1.6 at VF max) |
| D6 | `nPG` sinks | `+5V_IN` | Kingbright APT2012LVBC/D blue | R31 1k | 2.2 mA (1.6 at VIN 4.75 / VF 3.0) |
| D7 | `LED_SYS` sources (active high) | nRF9151 GPIO | APTD2012LCGCK green | R32 1.2k | 1.1 mA (0.7-1.5) |
| D400 | `LED_LTE` sources | nRF9151 GPIO | APT2012LSYCK/J3-PRV yellow | R400 1.2k | 1.1 mA (0.7-1.5) |
| D401 | `LED_LINK` sources | BT840 GPIO | APT2012LSECK/J3-PRV hyper red | R401 1.2k | 1.2 mA (0.7-1.5) |

Why those rails:
- STAT1/STAT2/PG are open-drain sinks, ISINK max 35 mA, VOL 0.4 V typ @
  4 mA (DC table "Status Indicators"; sec 3.10-3.12). Abs max for all pins is
  -0.3 V to VDD+0.3 V, VDD = VIN or VBAT -- `+VSYS` (MCP73871 OUT) never
  exceeds that, `+3V3` would be marginal at a 3.0 V cell.
- **PG must not be pulled above VIN** -- sec 5.2.4: "there is a diode path
  back to VIN". So D6 hangs off `+5V_IN`; an LED from `+VSYS` would back-feed
  the input and glow on battery.
- GPIO LEDs source from the pin to GND so an unpowered MCU is never back-fed
  through an LED from +3V3, and are sized for <= 1.5 mA so standard drive is
  enough.
- VF values are the Kingbright datasheet values at IF = 2 mA (all four parts
  are specified at 2 mA): LSECK 1.5/1.8/2.1 V (DSAN8393 V.8A), LSYCK
  1.5/1.85/2.1 V (DSAN8395 V.5B), APTD2012LCGCK 1.5/1.9/2.1 V (DSAO7908
  V.7B), LVBC/D 2.2/2.65/3.0 V (DSAN8396 V.8B). All 0805 (2.0 x 1.25 mm),
  -40..+85 degC, IF(DC) max 30 mA. Downloaded from kingbrightusa.com and read.

### `testpoints.kicad_sch` (A4 -> A3)

- Fixed a real bug: TP1/TP5/TP10, TP2/TP6/TP11, TP3/TP7/TP12, TP4/TP8/TP13
  and TP9/TP14 were stacked on identical coordinates, so their pins were
  shorted together on the schematic (e.g. TP3 GND was joined to TP7 CLK_A1
  and TP12 SPI_MISO). Every pad now has its own position.
- TP1-TP21 connected to contract nets (old value -> net): TP1 `+3V3_SYS` ->
  `+3V3`, TP2 `+VSYS`, TP3/TP4 `GND`, TP5 `REF_38M4` -> `TCXO_OUT`,
  TP6-TP9 `CLK_A0..3` -> `UWB_CLK0..3`, TP10-12 `SPI_*` -> `UWB_SCK/MOSI/MISO`,
  TP13 `IRQ_A0` -> `UWB_IRQ0`, TP14 `ANCHOR_RSTn` -> `UWB_RST_N`, TP15-18
  `CS_A0..3` -> `UWB_CS0_N..3_N`, TP19-21 `IRQ_A1..3` -> `UWB_IRQ1..3`.
- Added TP100-TP175: every net in net-contract sections 1-7, extra rail pads
  at far ends of `+3V3` and `+VSYS`, `+5V_IN`, two GND probe-spring pairs
  (TP3+TP110 at the clock, TP111+TP112 at the SPI bus) and one GND pad per
  functional area (TP113-TP119). 66 pads on the sheet + TP121 on orientation.
- Footprints: rails/GND `TestPoint_Pad_D1.5mm`, signals
  `TestPoint_Pad_D1.0mm` (TP5-TP21 changed from D1.5 to D1.0).
- **Clock pads behind DNP 0R:** TP5-TP9 connect to `TCXO_OUT` /
  `UWB_CLK0-3` only through DNP 0402 0R R402-R406, whose pad sits on the
  clock trace. Default build adds one unfitted 0402 pad to the trace and
  nothing else. Sheet note gives the layout rule (keep R403/R404 if layout
  forces a cut; equal length including the pad). This replaces the previous
  "minimal pad on the routing" approach -- decisions.md entry below.
- Grouped in columns with headers: rails, ground, UWB SPI/control, sensors
  I2C, clock, BLE bridge, debug, status. Each pad's hidden Description holds
  purpose + placement + bring-up expectation; the index is in section 7.

### `mechanical.kicad_sch`

- H1-H4 unchanged. Added FID1-FID3 (`Mechanical:Fiducial`, flattened from
  the installed KiCad 10 lib, no `extends`) with
  `Fiducial:Fiducial_1mm_Mask2mm`, plus a placement note (L-shaped, three
  corners, top side; add bottom/local fiducials only if the assembler asks).
- Holes are NPTH with no net. Note added recommending plated
  `MountingHole_3.2mm_M3_Pad_Via` to GND (ESD path for an outdoor, handled
  box with coax shields on GND; edge stitching near LTE/SMA), with the
  ground-loop counter-argument and a 0R/DNP-per-hole middle path. Not
  applied -- depends on the enclosure decision.

### Root `bay-station.kicad_sch`

A4 -> A3 (the old layout ran past the A4 frame at x = 360 mm). Sheets
regrouped in four labelled rows (Power / Host+radios+sensors / UWB array /
Debug+test+mechanical); page numbers unchanged. Added the architecture block
note (nRF9151 host + BT840 BLE bridge + 4x DW3210, A0 centre TWR / A1-A3
TDoA, shared TCXO, georeference) and a one-line data-flow note. Title-block
comment updated.

No new symbols or footprints were authored, so nothing was added to
`libs/bay_station.kicad_sym` or `libs/bay_station.pretty/`.

## 2. components.csv rows

Remove (MAX-M10S gone; GNSS decoupling row was C32-C36, now split):

```csv
"GNSS receiver (gnss.kicad_sch, U9)",u-blox MAX-M10S,...   <- REMOVE row 29
"GNSS decoupling (gnss.kicad_sch, C32-C36)",...           <- REMOVE row 32
```

Row 33 "GNSS antenna (x1)" -- reassign to the connectivity agent (nRF9151
GNSS antenna); its MAX-M10S VCC_RF/LNA_EN text no longer applies.

Replace rows 26, 27, 30, 31 and add the rest:

```csv
"Magnetometer (orientation.kicad_sch, U10)",ST LIS3MDL,Sensor_Magnetic:LIS3MDL (KiCad default),Package_LGA:LGA-12_2x2mm_P0.5mm (KiCad default),https://www.st.com/resource/en/datasheet/lis3mdl.pdf,"Station HEADING; required (position without heading = circle of tag locations). WIRED 2026-11-17. Pinout verified vs DocID024204 Rev 4 Table 2 (matches KiCad stock symbol). I2C 0x1C: SDO/SA1 to GND via R412 (DNP R413 for 0x1E), sec 5.1.1. CS tied to Vdd_IO for I2C (sec 5.1). C1 pin 4 = 100nF C400 (Table 2, mandatory); Vdd 100nF C35 + 1uF C401 (sec 4.1 / Figure 5). Vdd 1.9-3.6V, Vdd_IO 1.71V..Vdd+0.1 (Table 5) -> both on +3V3_SNS. Siting: >10mA currents a few mm away (sec 4.3); sheet keep-out note covers buck inductor / LTE feed / battery loops."
"Accelerometer (orientation.kicad_sch, U11)",ST LIS2DH,Sensor_Motion:LIS2DH (KiCad default),Package_LGA:LGA-14_2x2mm_P0.35mm_LayoutBorder3x4y (KiCad default),https://www.st.com/resource/en/datasheet/lis2dh.pdf,"Tilt compensation for U10 + knock/move detect on INT1. WIRED 2026-11-17. Pinout verified vs Doc ID 022516 Rev 1 Table 2 (matches KiCad stock symbol; pins 10-14 Res -> GND). I2C 0x19: SDO/SA0 to Vdd_IO via R414 (DNP R415 for 0x18), sec 5.1.1 / Table 14. CS tied high for I2C (sec 3). Decoupling 100nF C36 + 10uF C403 at pin 8 (sec 3). LIFECYCLE UNVERIFIED: a Farnell listing marks LIS2DH no longer manufactured; LIS2DH12 is a different (LGA-12) part -- check ST status before ordering."
"Orientation decoupling (orientation.kicad_sch, C35 C36 C400-C404)","Ceramic 0603: C35 C36 C400 C402 C404 = 100nF; C401 = 1uF; C403 = 10uF X5R",Device:C (KiCad default),Capacitor_SMD:C_0603_1608Metric (KiCad default),n/a (generic passive -- values from ST),"Values from the ST datasheets, not defaults: LIS3MDL sec 4.1 (C1 100nF, Vdd 100nF + 1uF) and LIS2DH sec 3 (100nF + 10uF at pin 8; ST says aluminium, X5R ceramic used -- check DC-bias derating). C402/C404 on Vdd_IO are extra insurance, DNP-able. MPNs not chosen."
"Orientation rework 0R links (orientation.kicad_sch, R407-R415)","Generic 0603 0R; R413 and R415 DNP",Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive),"R407/R408 = U10 SCL/SDA isolation, R409/R410 = U11 SCL/SDA isolation, R411 = +3V3 -> +3V3_SNS sensor-rail current break, R412/R413 = U10 SA1 strap (fitted GND / DNP high), R414/R415 = U11 SA0 strap (fitted high / DNP GND)."
"Status LEDs, red (indicators.kicad_sch, D4 D401)",Kingbright APT2012LSECK/J3-PRV,Device:LED (KiCad 10 default),LED_SMD:LED_0805_2012Metric (KiCad default),https://www.kingbrightusa.com/images/catalog/SPEC/APT2012LSECK-J3-PRV.pdf,"Hyper red AlGaInP 0805, low-current part: VF 1.5/1.8/2.1 V min/typ/max @ IF=2mA, IF(DC) max 30mA, -40..+85 degC (Spec DSAN8393 Rev V.8A, read from the PDF). D4 = charging/LBO (MCP73871 STAT1, from +VSYS), D401 = LED_LINK (BT840 GPIO). Verify cathode mark vs KiCad pad 1 = K at footprint time."
"Status LEDs, green (indicators.kicad_sch, D5 D7)",Kingbright APTD2012LCGCK,Device:LED (KiCad 10 default),LED_SMD:LED_0805_2012Metric (KiCad default),https://www.kingbrightusa.com/images/catalog/SPEC/APTD2012LCGCK.pdf,"Green AlGaInP 0805 (2.0x1.25mm), VF 1.5/1.9/2.1 V @ IF=2mA, IF(DC) max 30mA, 40deg viewing angle (Spec DSAO7908 Rev V.7B). D5 = charge complete (STAT2), D7 = LED_SYS (nRF9151 GPIO). Chosen over APT2012CGCK because CGCK is only specified at 20mA."
"Status LED, yellow (indicators.kicad_sch, D400)",Kingbright APT2012LSYCK/J3-PRV,Device:LED (KiCad 10 default),LED_SMD:LED_0805_2012Metric (KiCad default),https://www.kingbrightusa.com/images/catalog/SPEC/APT2012LSYCK-J3-PRV.pdf,"Super-bright yellow AlGaInP 0805, VF 1.5/1.85/2.1 V @ IF=2mA, IF(DC) max 30mA (Spec DSAN8395 Rev V.5B). D400 = LED_LTE (nRF9151 GPIO)."
"Status LED, blue (indicators.kicad_sch, D6)",Kingbright APT2012LVBC/D,Device:LED (KiCad 10 default),LED_SMD:LED_0805_2012Metric (KiCad default),https://www.kingbrightusa.com/images/catalog/SPEC/APT2012LVBC-D.pdf,"Blue InGaN 0805, VF 2.2/2.65/3.0 V @ IF=2mA, IF(DC) max 30mA (Spec DSAN8396 Rev V.8B). D6 = power good (MCP73871 ~PG) driven from +5V_IN, where VF headroom is ample; too high a VF for any 3.3V GPIO LED on this board."
"LED series resistors (indicators.kicad_sch, R29-R32 R400 R401)","0603 1%: R29 R30 = 1.5k, R31 = 1k, R32 R400 R401 = 1.2k",Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive -- values computed),"Computed from Kingbright VF at the real drive rail (replaces the indicative 1k): R29/R30 +VSYS -> LED -> STAT1/STAT2, (5.0-VF-0.2)/R ~= 2mA on adapter; R31 +5V_IN -> LED -> ~PG, (5.0-2.65-0.2)/1k = 2.2mA (PG must not be pulled above VIN, DS20002090E sec 5.2.4); R32/R400/R401 GPIO -> R -> LED -> GND, ~1.1mA typ, 0.7-1.5mA over VF/VOH spread, assuming 3.3V GPIO."
"Test pads (testpoints.kicad_sch TP1-TP21 TP100-TP175, orientation.kicad_sch TP121)","Bare SMD copper pad, no part",Connector:TestPoint (KiCad default),"TestPoint:TestPoint_Pad_D1.5mm (rails, GND) / TestPoint:TestPoint_Pad_D1.0mm (signals) (KiCad default)",n/a (copper only),"67 pads: every net in docs/net-contract.md sections 1-7, extra rail pads at far rail ends, two GND spring pairs (clock TP3/TP110, SPI TP111/TP112), one GND per functional area (TP113-TP119). Index with expected bring-up values in bay-station/handoff/io.md. in_bom yes in KiCad's symbol but nothing is purchased."
"Clock probe isolation links (testpoints.kicad_sch, R402-R406)",0402 0R -- DNP by default,Device:R (KiCad default),Resistor_SMD:R_0402_1005Metric (KiCad default),n/a (generic passive),"Keep TP5-TP9 off the TCXO_OUT / UWB_CLK0-3 nets in the default build: the unfitted 0402 pad on the clock trace is the only stub. Fit a 0R only while probing. 0402 (not the 0603 standard) because this sits on the precision clock path, same reasoning as the RF-path 0402 exception."
"Fiducials (mechanical.kicad_sch, FID1-FID3)","Copper dot, no part",Mechanical:Fiducial (KiCad 10 default),Fiducial:Fiducial_1mm_Mask2mm (KiCad default),n/a,"3 global fiducials, top side, non-collinear at three corners. 1.0mm copper / 2.0mm mask opening. Not in BOM."
```

## 3. decisions.md entries

Move from **Open -> Resolved** ("LED drive rails and GPIO allocation", Critical path section -- resistor half only; GPIO allocation stays with connectivity):

```markdown
- **Status LED drive rails and series resistors -- resolved 2026-11-17.**
  Replaces the indicative 1k. MCP73871 STAT1/STAT2/PG are open-drain sinks
  (DS20002090E sec 3.10-3.12; ISINK max 35 mA, VOL 0.4 V typ @ 4 mA), so the
  LED anode rail is a choice, and it is constrained two ways: every pin's
  abs max is -0.3 V to VDD+0.3 V with VDD = VIN or VBAT, and **PG "must not
  be pulled up higher than VIN because there is a diode path back to VIN"**
  (sec 5.2.4). Hence D4 (STAT1, red) and D5 (STAT2, green) from `+VSYS`
  through 1.5k (~2 mA on adapter, ~1.1 mA on battery), D6 (PG, blue) from
  `+5V_IN` through 1k (~2.2 mA). The host/radio LEDs D7 `LED_SYS`, D400
  `LED_LTE`, D401 `LED_LINK` are GPIO-sourced, active high, 1.2k for
  ~1.1 mA (0.7-1.5 mA spread) so standard drive suffices. Parts are
  Kingbright low-current 0805s specified at IF = 2 mA (APT2012LSECK/J3-PRV,
  APTD2012LCGCK, APT2012LSYCK/J3-PRV, APT2012LVBC/D), VF read from each
  datasheet. Open caveat: assumes the nRF9151 GPIO runs at 3.3 V.
- **Clock test pads behind DNP 0R -- 2026-11-17.** Supersedes "keep TP5-TP9
  as minimal pads on the existing routing". TP5-TP9 now reach `TCXO_OUT` /
  `UWB_CLK0-3` only through DNP 0402 0R links R402-R406 whose pad sits on
  the trace; the default build carries one unfitted 0402 pad per clock net
  and no probe stub. Fit to probe, then remove. If layout cannot take all
  four anchor links, keep A0/A1 (R403/R404).
- **Test-point coverage: every net-contract net, 2026-11-17.** 67 pads:
  all of `docs/net-contract.md` sections 1-7, far-end rail pads, GND spring
  pairs at the clock and SPI bus, one GND per area. Rails/GND D1.5, signals
  D1.0. Also fixed: TP1-TP14 had been stacked on shared coordinates, which
  shorted unrelated test points together on the schematic.
- **Orientation sheet (was GNSS / Orientation), 2026-11-17.** MAX-M10S U9 and
  its C32-C34 removed (GNSS now from the nRF9151). LIS3MDL 0x1C and LIS2DH
  0x19 strapped, distinct from MAX17048 0x36 (19-6171 Rev 7); each sensor
  has its own SCL/SDA 0R and a shared `+3V3_SNS` current break.
```

New **Open** items:

```markdown
- **LIS2DH lifecycle.** A Farnell listing marks the ST LIS2DH as no longer
  manufactured; ST's product page could not be fetched to confirm. LIS2DH12
  is NOT a drop-in (LGA-12 2x2 vs LGA-14, different pinout). Check ST status
  before ordering; if obsolete, re-pick (LIS2DH12 or LIS2DW12) and re-author
  the U11 symbol/footprint.
- **Mounting holes: ground or not.** H1-H4 are NPTH with no net. Recommended:
  plated `MountingHole_3.2mm_M3_Pad_Via` to GND, optionally via a 0R per hole
  to break a ground loop through a metal frame. Decide with the enclosure.
- **MCP73871 orderable variant / LBO.** D4 doubles as a low-battery LED only
  if the ordered suffix enables LBO (sec 3.13, third option character).
  Variant not yet chosen.
```

## 4. net-contract.md changes requested

- **Add `+5V_IN` to section 1 (Rails).** It already exists as a global label
  on power_bms (MCP73871 IN, barrel/USB-C input), and indicators now uses it
  for D6 because PG must not be pulled above VIN. It also has a test pad
  (TP104). No rename.
- No other new cross-sheet nets. Sheet-local only: `+3V3_SNS`,
  `U10_SCL/SDA/SA1/C1`, `U11_SCL/SDA/SA0` (orientation).

## 5. For other sheet owners

- **power**: rename `FG_SCL`/`FG_SDA` -> `I2C_SCL`/`I2C_SDA` (contract). Keep
  `+5V_IN` spelled exactly (indicators + TP104 use it). Add local test pads on
  `VBATT_PROT`, `BATT_RAW`, `VPCC`, `THERM` if you want them -- not contract
  nets, so I did not. `+VBAT_LTE` needs its current break; TP100 is the rail pad.
- **regulation**: the rail must be labelled `+3V3` (TP1 previously read
  `+3V3_SYS` and the regulation title still says `+3V3_SYS`).
- **connectivity**: allocate GPIOs for `LED_SYS`, `LED_LTE` (nRF9151) and
  `LED_LINK` (BT840) -- active high, ~1.1 mA each. If `nSTAT1_LBO`/`nSTAT2`/
  `nPG` go to GPIOs, do not tap them raw: when the output is off the node
  floats up to ~`+VSYS - VF` (~3.2 V, more with VF at min) -- add a series R
  or a divider/clamp. Confirm the nRF9151 GPIO voltage is 3.3 V (VIO =
  `+3V3`) -- the LED resistors assume it. Pull-ups R37/R38 now serve
  LIS3MDL + LIS2DH + MAX17048 only.
- **uwb / clock**: the clock pads TP5-TP9 are behind R402-R406; place each
  0402 pad directly on the respective trace (at the TCXO output and at each
  DW3210 XTI after the AC-coupling cap) and include the pad in the
  equal-length match. Ground-spring pads TP3/TP110 (clock) and TP111/TP112
  (SPI) go within 5 mm of those pads. If `TCXO_EN` is dropped (TCXO without
  enable), delete TP135 too.
- **coordinator / docs** (references to the old `gnss.kicad_sch` filename or
  MAX-M10S that I did not edit): `CLAUDE.md` line 52 (`gnss.kicad_sch`, and
  the "MAX-M10S GNSS for position" sentence); `bay-station/README.md` line 49
  (sheet table row) and line 243; `bay-station/libs/components.csv` rows
  29-33; `docs/decisions.md` georeferencing entry (U9 MAX-M10S text) and the
  Level-shifting audit's MAX-M10S mention; `connectivity.kicad_sch` R37/R38
  Descriptions ("bus crosses from power_bms to gnss"). No `.kicad_sch` or
  `.kicad_pro` still references `gnss.kicad_sch`.

## 6. Unverified items / risks

1. **nRF9151 GPIO level and drive** not read (no PS available offline here).
   LED resistors assume 3.3 V I/O and standard drive >= 1.5 mA. At 1.8 V I/O
   D7/D400 would not light.
2. **LIS2DH lifecycle** (above). Datasheet read was Rev 1 (2011) from a
   distributor mirror; ST's site blocked the download, so a later revision
   could differ.
3. **LIS3MDL datasheet** read from Pololu's mirror of ST DocID024204 Rev 4
   (May 2015), not st.com directly.
4. **Magnetometer keep-out distances** (25 mm from L1, 20 mm from the LTE
   feed) are engineering guidance, not ST numbers -- must be checked by
   logging heading while the buck, charger and LTE TX run.
5. **Kingbright cathode mark vs KiCad `LED_0805_2012Metric` pad 1 = K** not
   cross-checked against the package drawing; MPN capacitor choices
   (C401/C403 DC-bias derating) not made.
6. Test-pad expected values are design targets taken from each block's
   intent, not measured or datasheet-guaranteed numbers (e.g. the +3V3
   tolerance depends on the TPS62A02 feedback network on regulation).
7. Root and testpoints moved A4 -> A3, orientation A4 -> A3; anyone with
   coordinates in notes for those sheets should re-check.

## 7. Test-point index (feeds the verification plan)

All expected values assume the board powered from the adapter unless noted.
Clock pads read nothing until their DNP 0R is fitted.

| TP | Net | Purpose | Expected at bring-up |
|---|---|---|---|
| TP1 | `+3V3` | Main 3.3V rail from TPS62A02 (regulation). Check first when anything misbehaves. | 3.30 V +/-3% with load; ripple < 30 mVpp |
| TP101 | `+3V3` | +3V3 at the far end of the UWB array: IR drop across four DW3210. | within 50 mV of TP1 during TX bursts |
| TP102 | `+3V3` | +3V3 at the nRF9151 / BT840 end. | within 50 mV of TP1 |
| TP2 | `+VSYS` | Unregulated system rail out of the MCP73871 power path (power_bms). | ~4.5-5.0 V on adapter; = VBAT (3.0-4.2 V) on battery |
| TP103 | `+VSYS` | +VSYS at the regulator inputs: drop along the system feed. | within 100 mV of TP2 |
| TP100 | `+VBAT_LTE` | nRF9151 VBAT supply (LTE PA peaks). Pair with the regulation sheet current break. | per regulation sheet (nRF9151 VBAT range, verify PS); droop during LTE TX burst on a scope |
| TP104 | `+5V_IN` | Adapter / USB input = MCP73871 IN (also D6 PG LED rail). | 4.75-5.25 V with adapter, 0 V on battery |
| TP3 | `GND` | Clock scope ground #1: short ground-spring next to TCXO/clock pads. | 0 V |
| TP110 | `GND` | Clock scope ground #2: second spring point at the anchor clock pads. | 0 V |
| TP111 | `GND` | SPI scope ground #1: spring ground beside UWB_SCK. | 0 V |
| TP112 | `GND` | SPI scope ground #2: spring ground beside UWB_MISO / CS pads. | 0 V |
| TP4 | `GND` | General-purpose ground, away from the clock area. | 0 V |
| TP113 | `GND` | Ground: power_bms area. | 0 V |
| TP114 | `GND` | Ground: regulation area. | 0 V |
| TP115 | `GND` | Ground: connectivity area (nRF9151 / BT840). | 0 V |
| TP116 | `GND` | Ground: UWB array area. | 0 V |
| TP117 | `GND` | Ground: programming / debug area. | 0 V |
| TP118 | `GND` | Ground: indicators area. | 0 V |
| TP119 | `GND` | Ground: orientation area. | 0 V |
| TP10 | `UWB_SCK` | Shared SPI clock to all four DW3210. | bursts at the configured SPI rate; idle level per SPI mode 0 = low |
| TP11 | `UWB_MOSI` | Shared SPI MOSI to all four anchors. | data during CSn low |
| TP12 | `UWB_MISO` | Shared SPI MISO from all four anchors. | driven only while one CSn is low; DEV_ID read returns the value in the DW3000 User Manual on each CSn |
| TP15 | `UWB_CS0_N` | Chip-select A0 (CENTER anchor, TWR). | idle 3.3 V; one low pulse per A0 transaction |
| TP16 | `UWB_CS1_N` | Chip-select A1 (outer, TDoA). | idle 3.3 V |
| TP17 | `UWB_CS2_N` | Chip-select A2 (outer, TDoA). | idle 3.3 V |
| TP18 | `UWB_CS3_N` | Chip-select A3 (outer, TDoA). | idle 3.3 V |
| TP13 | `UWB_IRQ0` | IRQ from A0 (center): ranging exchange timing. | low idle (100k pull-down); high pulse per event |
| TP19 | `UWB_IRQ1` | IRQ from A1: TDoA timestamp latch, independent of A0. | low idle; pulse on RX of the tag frame, within ns-us of TP13 |
| TP20 | `UWB_IRQ2` | IRQ from A2. | as TP19 |
| TP21 | `UWB_IRQ3` | IRQ from A3. | as TP19 |
| TP14 | `UWB_RST_N` | Shared DW3210 RSTn (open-drain). | low during reset, then released high by the DW3210s |
| TP130 | `UWB_WAKEUP` | Shared DW3210 WAKEUP. | low idle; high pulse to wake from sleep |
| TP131 | `UWB_SYNC` | Shared SYNC/OSTR (use still open in decisions.md). | low unless firmware uses SYNC |
| TP140 | `I2C_SCL` | Shared I2C SCL (MAX17048 0x36, LIS3MDL 0x1C, LIS2DH 0x19). | idle 3.3 V; 100/400 kHz bursts; rise time < 300 ns @400k |
| TP141 | `I2C_SDA` | Shared I2C SDA. | idle 3.3 V; ACKs from 0x19, 0x1C, 0x36 on a bus scan |
| TP142 | `MAG_DRDY` | LIS3MDL DRDY. | toggles at the set ODR once U10 is running |
| TP143 | `MAG_INT` | LIS3MDL INT. | low unless threshold interrupt configured |
| TP144 | `ACC_INT1` | LIS2DH INT1 (knock / move detect). | pulses when the board is tapped (after config) |
| TP145 | `ACC_INT2` | LIS2DH INT2. | low unless configured |
| TP146 | `FG_ALRT` | MAX17048 ALRT (open-drain, R39 pull-up). | idle 3.3 V; low on SOC/voltage alert |
| TP5 | `TCXO_OUT` | Raw TCXO output before the 1:4 buffer. (behind DNP R402) | fit R402 first; 38.4 MHz, amplitude per TCXO datasheet (clipped sine) |
| TP6 | `UWB_CLK0` | Buffer output to A0 (center) XTI, after AC coupling. (behind DNP R403) | fit R403 first; 38.4 MHz, 0.8 V to VDD2 Vpp at XTI (DW3000 DS Table 10) |
| TP7 | `UWB_CLK1` | Buffer output to A1 XTI. (behind DNP R404) | as TP6; compare skew to TP6 |
| TP8 | `UWB_CLK2` | Buffer output to A2 XTI. (behind DNP R405) | as TP6 |
| TP9 | `UWB_CLK3` | Buffer output to A3 XTI. (behind DNP R406) | as TP6 |
| TP135 | `TCXO_EN` | TCXO enable from the host (omit if the TCXO has none). | high = TCXO running |
| TP150 | `BRIDGE_TXD` | nRF9151 TX -> BT840 RX. | idle high 3.3 V; UART frames at the bridge baud |
| TP151 | `BRIDGE_RXD` | BT840 TX -> nRF9151 RX. | idle high 3.3 V |
| TP152 | `BRIDGE_RTS` | Flow control, nRF9151 RTS out. | low = nRF9151 ready to receive |
| TP153 | `BRIDGE_CTS` | Flow control, nRF9151 CTS in. | low = BT840 ready to receive |
| TP154 | `BRIDGE_IRQ` | BT840 -> nRF9151 attention line. | pulse when the BT840 has data / link event |
| TP155 | `RESET_BLE_N` | BT840 reset (open-drain, from nRF9151 and SWD header). | idle 3.3 V; pull low with tweezers to GND pad TP115 to reset the BT840 |
| TP160 | `SWDIO_MCU` | nRF9151 SWDIO (also on the SWD header). | SWD traffic during flashing |
| TP161 | `SWDCLK_MCU` | nRF9151 SWDCLK. | clock bursts during flashing |
| TP162 | `RESET_MCU_N` | nRF9151 reset. | idle 3.3 V (internal pull-up) |
| TP163 | `SWDIO_BLE` | BT840 SWDIO. | SWD traffic during flashing |
| TP164 | `SWDCLK_BLE` | BT840 SWDCLK. | clock bursts during flashing |
| TP165 | `DBG_UART_TX` | nRF9151 log/shell UART TX. | idle high; boot banner at power-up |
| TP166 | `DBG_UART_RX` | nRF9151 log/shell UART RX. | idle high |
| TP167 | `BTN_USER` | User button (active low). | 3.3 V released, 0 V pressed; short to GND to fake a press |
| TP170 | `nSTAT1_LBO` | MCP73871 STAT1/LBO (open-drain, D4). | low while charging; else ~VSYS-VF through D4 |
| TP171 | `nSTAT2` | MCP73871 STAT2 (open-drain, D5). | low when charge complete |
| TP172 | `nPG` | MCP73871 ~PG (pseudo open-drain, D6). | low with adapter present |
| TP173 | `LED_SYS` | nRF9151 system LED drive (D7). | 3.3 V = LED on (active high) |
| TP174 | `LED_LTE` | nRF9151 LTE LED drive (D400). | 3.3 V = LED on |
| TP175 | `LED_LINK` | BT840 BLE-link LED drive (D401). | 3.3 V = LED on |
| TP121 | `+3V3_SNS (local, orientation)` | Sensor rail after the R411 current break (on orientation sheet). | = TP1 with R411 fitted; 0 V with R411 lifted |
