# Passive components reference, per chip

Compiled from each chip's own datasheet reference/typical-application
circuit -- not guessed. This is the definitive cross-reference for "what
does this IC need around it and why"; per-sheet component tables in each
board's `*_notes.md` are the more detailed originals this was compiled from.
All passives are standard **0603** (`R_0603_1608Metric` / `C_0603_1608Metric`
/ `L_0603_1608Metric`) unless noted otherwise.

## Qorvo DWM3001C (wristband, U3)

No reference/application circuit exists for this part. It is a certified
module with on-board power management, its own 38.4MHz crystal, and both
antennas integrated -- the datasheet is explicit that it "requires no RF
design as the antenna and associated analog and RF components are on the
module" (Section 8). There is nothing external to add beyond supply
decoupling.

| Passive | Value | Role | Status |
|---|---|---|---|
| C6 | 100nF | VDD (pin 12) bypass | Placed (`radio_mcu.kicad_sch`). Conservative standard practice; Qorvo publishes no external application circuit, so there is no datasheet value to confirm against. |
| C7 | 10uF | VDD bulk | Placed (`radio_mcu.kicad_sch`). Same basis as C6. |

**Superseded:** this section previously covered u-blox NINA-B111 (C6/C7 as
VCC/VCC_IO bypass) and an L1/C13 DNP antenna matching network on
`antenna.kicad_sch`. Both parts and that whole sheet were deleted on
2026-09-19 when the wristband consolidated onto the DWM3001C -- see
`decisions.md`. The matching network no longer exists, so neither does the
open RF-tuning task attached to it.

## Qorvo DWM3000 (wristband U4; bay-station U4-U7, x5 total)

Real "Example DWM3000 Application Circuit" (datasheet Rev B, Figure 11,
Section 6.2) shows the module needs **only power + host connection** -- no
external decoupling caps drawn on VDD1/VDD3V3/VDD3V3 at all, since the
module has its own integrated regulation/crystal.

| Passive | Value | Role | Status |
|---|---|---|---|
| Decoupling caps (per instance) | 100nF/100nF/1uF (wristband: C8-C10; bay-station: C11-C19, 3 per anchor) | VDD1/VDD3V3/VDD3V3 bypass | Placed, **beyond what Qorvo's own minimal example circuit shows**. Not wrong (extra bypass capacitance on a supply rail is standard conservative practice), but worth knowing it's a "belt and suspenders" addition, not a datasheet mandate. |
| GPIO5/GPIO6 pull-downs (per instance) | 10k (wristband: R7/R8; bay-station: R10-R17, 2 per anchor) | SPI-mode boot strapping ("Sample GPIOs 5&6 to set SPI mode", Figures 1/2) | Placed. **Technically redundant** -- the chip's own GPIOs default to internal pull-down (10-30k, varies with VDD1) out of reset, per Section 6.3, so the strap would resolve correctly even with nothing external. Kept deliberately for tighter/more deterministic timing margin than the chip's own variable internal pull, not because it's strictly required. |
| IRQ/GPIO8 pull-down (per instance) | **100k** (wristband: R9; bay-station: R25-R28) | "Optional pulldown on IRQ to prevent spurious interrupts" -- explicitly shown in Figure 11 | **Newly added this pass** -- was missing from the design entirely until this audit. |
| RSTn | -- (open-drain from host) | Reset | Figure 11 shows this driven from an open-drain host GPIO with no external pull shown -- not yet wired (placement-only stage), nothing to add here. |

No external crystal needed -- the module has its own onboard 38.4MHz
reference crystal (Section 1.1), confirmed, not something to source.

## Microchip MCP73831 (wristband charger, U2)

Real typical application circuit, DS20001984G/H, page 1 ("500mA Li-Ion
Battery Charger").

| Passive | Value | Role | Status |
|---|---|---|---|
| R4 | 6.8k | PROG -- sets ~147mA fast-charge current (`IREG[mA] = 1000/RPROG[kΩ]`) | Placed |
| C2 | 4.7uF | VDD input decoupling (datasheet's exact shown value) | Placed |
| C3 | 4.7uF | VBAT output decoupling (datasheet's exact shown value) | Placed |
| R5, R6 | 5.1k | USB-C CC1/CC2 pull-downs (not part of the charger IC itself, but needed to source its VDD from a real USB-C port) | Placed |

## Fortune Semiconductor DW01A + FS8205 (wristband protection, U1 + Q2)

Real typical application circuit, DW01A-DS-11/12_EN, Section 8/page 5.

| Passive | Value | Role | Status |
|---|---|---|---|
| R2 | 100Ω | Cell+ to DW01A VCC feed (datasheet's own "R1") | Placed |
| C1 | 0.1uF | DW01A VCC-to-GND decoupling (datasheet's own "C1") | Placed |
| R3 | 1k | DW01A CS pin to post-FET GND, current-sense (datasheet's own "R2") | Placed |

No passives needed around FS8205 itself beyond what's shared with DW01A above
-- it's driven directly by DW01A's OD/OC outputs.

## AOS AO3401A (both boards, reverse-polarity "ideal diode" FET)

Not a datasheet-specified reference circuit (this is a general-purpose
technique, not an AOS application note) -- gate-pulldown value is a design
choice, not derived from a table.

| Passive | Value | Role | Status |
|---|---|---|---|
| Gate pull-down (wristband R1; bay-station R1) | 100k | Biases the FET off if the gate is ever undriven; value not critical, just needs to be much larger than the FET's own gate leakage | Placed |

## onsemi ESD5B5.0ST1G (TVS, both boards -- 1x wristband, 3x bay-station)

Standalone protection part -- no supporting passives required by its own
datasheet; used directly across the rail it protects.

## Fanstel BT840 / Nordic nRF52840 (bay-station connectivity, U3)

Host from 2026-09-19, demoted to the UART BLE bridge on 2026-11-17
(`decisions.md`). The BT840 is a certified module with on-board DC-DC and its
own antenna, so there is no external application circuit to work from --
C5/C6/C7 on `connectivity.kicad_sch` are conservative 3V3 supply decoupling,
not datasheet-specified values, and were kept through the redesign.
R140-R144 are 0R links on the five bridge lines (rework only).

## Nordic nRF9151 SiP (bay-station connectivity, U20)

Values are exactly the nRF9151 HDG *Schematic design* BOM (read as Nordic's
HTML rendition -- the PDF could not be fetched; `decisions.md` Open). HDG
designators in brackets. Nordic's examples are 0201/0402 Murata GRM; this
board uses 0603/0805 per the repo standard, which the HDG allows if DC
resistance and frequency behaviour stay close and VDD stays >= 3.0 V under
load. Detail: `bay-station/connectivity_notes.md` section 3.

| Passive | Value | Role | Status |
|---|---|---|---|
| FB10 | BLM18SD220SN1 (22 ohm @ 100 MHz, 6 A, 8 mOhm) | `+VBAT_LTE` -> `NRF_VDD` bead, "highly recommended", DCR < 0.1 ohm (HDG *VDD*) [FB1] | Placed |
| C100, C101 | 1uF | VDD bank, source side of FB10 [C1, C2 -- optional] | Placed |
| C102 | 47uF 0805 | VDD pin 14 bulk [C3] | Placed |
| C103 | 10uF | VDD pin 14 [C4] | Placed |
| R101 | 10k | ENABLE series resistor from `NRF_VDD` (HDG *ENABLE*) [R1] | Placed. The `+3V3`-after-VDD sequencing on regulation assumes ENABLE is tied this way |
| C104 | 100nF | ENABLE decoupling (HDG *ENABLE*: recommended) | Placed |
| C107 | 4.7uF | VDD_GPIO pin 65 -- the HDG minimum [C6] | Placed |
| C108 | 100nF | VDD_GPIO pin 65 [C5] | Placed |
| C109 | 4.7uF X5R | DEC0 pin 24, ground to the nRF9151 GND plane [C7] | Placed |
| C110 | 100nF | nRESET pin 9, close to the pin (HDG *nRESET*) [C8] | Placed |
| R313 | 1k | nRESET series, on `programming_debug` [R2]. **No pull-up anywhere** -- "External pull-up is not allowed" (13k internal to 2.2 V) | Placed |
| C111 | 100nF | SIM_1V8 (HDG *UICC*: 100-220 nF may be added) | Placed |
| R103 / R104 | 0R / 0R | `+3V3` -> VDD_GPIO; R104 is the VDD_GPIO current-measure link | Placed. DNP fallback U21 TPS22917 + R102/C105/C106/R155 if the regulation-sheet delay ever proves short |

**GNSS LNA (U24 BGA524N6, U25 TPS7A0228 2.8 V), from Infineon DS Rev 3.5
Table 6 and TI SBVS277C:** L101 8.2 nH 0402 input match [L1] and C123 1 nF
0402 DC block [C1] -- **C123 is mandatory**, the LNA input is 0.9 V abs max;
C129 1 uF VCC bypass at pin 2 [C2, > 10 nF]; C127/C128 1 uF LDO CIN/COUT
(0.5 uF effective COUT minimum). RF pi pads C124/R125/C125 (GPS pin) and
C130/R130/C131 (LTE, at J10) are 0R/DNP 0402 until tuned -- the HDG *ANT*
expects a >= 3-component match, values per design. Bias-tee R122/L100/C122
values are estimates, not from a Nordic BOM.

**I2C pull-ups R37/R38 moved to 3.3k** for the nRF9151's 1 mA standard-drive
sink (`decisions.md`, pull-ups).

## Qorvo DW3210 (bay-station uwb_array, U4-U7, x4)

**Placed 2026-09-28**, derived from the real **Qorvo DW3000 Datasheet v1.1,
Figure 32 "DW3000 WLCSP Application Circuit"** -- Qorvo's own reference
design. Note Figure 32 is an image, so none of this extracts as text; it was
read by rendering the page. The earlier C8-C19 were sized for a DWM3000
*module* with a single VDD3V3 rail and did not map onto a bare IC; they are
gone and none of their values were reused.

The DW3210 has three supply rails -- VDD1 (29, main + I/O), VDD2a/VDD2b
(28/23) and VDD3 (26) -- **plus two decoupling-only pins**, VTX_D (27) and
VIO_D (38), which each take their own capacitor to ground and **must not be
tied to a rail**. That distinction is the whole reason the module values were
wrong.

Per anchor (x4: U4-U7). Refdes run in consecutive blocks -- **U4 = C40-C47,
U5 = C48-C55, U6 = C56-C63, U7 = C64-C71** -- so the offset within each block
identifies the function. Figure 32's own designators in brackets:

| Offset | U4 | U5 | U6 | U7 | Value | Role |
|---|---|---|---|---|---|---|
| +0 | C40 | C48 | C56 | C64 | 100nF | VDD1 (29) + VDD2b (23) decoupling [C5] |
| +1 | C41 | C49 | C57 | C65 | 4.7nF | VDD2a (28) decoupling, at the pad [C1] |
| +2 | C42 | C50 | C58 | C66 | 4.7nF | VDD3 (26) decoupling [C10] |
| +3 | C43 | C51 | C59 | C67 | 100nF | VDD3 (26) decoupling [C11] |
| +4 | C44 | C52 | C60 | C68 | 10uF | VDD3 (26) bulk [C12] |
| +5 | C45 | C53 | C61 | C69 | 220nF | **VTX_D (27)** -- cap to ground only [C9] |
| +6 | C46 | C54 | C62 | C70 | 100nF | **VIO_D (38)** -- cap to ground only [C21] |
| +7 | C47 | C55 | C63 | C71 | 2.0pF | RF1 (18) series DC block [C2] |
| -- | FB1 | FB2 | FB3 | FB4 | BLM03PG330SN1D | Ferrite bead feeding VDD2a (28) [FB1] |
| -- | R33 | R34 | R35 | R36 | 49R9 | RF2 (13) 50 ohm termination [R1, DW3110 inset] |

Shared across all four anchors, on the +3V3 UWB rail: **C72 10uF [C6], C73
100nF [C7], C74 4.7nF [C8]**.

**Two things in that table are not ordinary decoupling and should not be
"tidied":**
- The **2.0pF on RF1** is not merely a DC block. Qorvo: *"C2 and C3 are not
  only a DC blocking capacitor, these capacitors are a part of the RF
  transmission line, this line was simulated in design and this capacitance
  value was chosen as the result of the simulation."* Section 7.3 adds that
  its pads must be embedded in the track at track width to avoid a
  discontinuity.
- The **ferrite bead is placed per anchor, not once on the rail.** Figure 32
  shows one because it shows one chip. Four transceivers sharing a supply is
  a different problem: a bead each keeps one anchor's TX transient out of the
  others' references, which matters on a board whose product is timestamp
  accuracy.

Also required per anchor and already placed: 10k GPIO5/GPIO6 SPI-mode straps
(R10-R17) and a 100k IRQ pull-down (R25-R28, Qorvo Figure 11).

**Not placed, deliberately:** Figure 32's X1/C100/C101 crystal network. Each
DW3210's XTI/XTO would form its own oscillator, which is exactly what the
shared-clock architecture forbids -- the four anchors take one TCXO through
`clock_dist.kicad_sch` instead (`docs/positioning.md`). Section 7.1 also
notes a **BPF on RF1/RF2 may be required for certification** in regions that
mandate conducted testing; not placed, flagged as an open item.

**Revision caveat:** these values come from datasheet **v1.1**, the copy that
could be obtained. This repo's DW3210 *pin* data was verified against
**v1.3**. The rails and decoupling scheme are unlikely to have changed, but
re-check Figure 32 against v1.3 before fab.

## Espressif ESP32-S3-WROOM-1 -- HISTORICAL (superseded by the BT840)

Decoupling per Espressif's hardware design guidelines; boot-strap resistors
per the real datasheet Section 4/Table 4-1/4-3/4-4/4-5; EN RC delay per the
separate ESP32-S3 Hardware Design Guidelines "Schematic Checklist".

| Passive | Value | Role | Status |
|---|---|---|---|
| C5 | 10uF | Bulk decoupling | Placed (`connectivity.kicad_sch`) |
| C6, C7 | 100nF | Bypass | Placed |
| R18 | 10k, pull-up | GPIO0 -> SPI Boot mode (explicit, matches default weak internal pull) | Placed (`programming_debug.kicad_sch`) |
| R19 | 10k, pull-down | GPIO3 -- datasheet requires an external pull here, "does not have any internal pull resistors" | Placed |
| R20 | 10k, pull-down | GPIO45 -- selects 3.3V VDD_SPI (matches this module's flash variant) | Placed |
| R21 | 10k, pull-down | GPIO46 -- avoids an explicitly-called-out invalid strap combination | Placed |
| R22 + C23 | 10k / 1uF | EN pin RC delay, exact values from Espressif's own recommendation | Placed |
| SW1, SW2 | -- | BOOT / RESET tactile buttons | Placed |

## Microchip MCP73871 (bay-station charge/power-path, U1)

Real typical application circuit + Sections 3-5, DS20002090E, page 2.

| Passive | Value | Role | Status |
|---|---|---|---|
| R2 (PROG1) | 2.00k | Sets 500mA fast-charge current (`IREG[mA] = 1000/RPROG1[kΩ]`, Eq. 4-1) | Placed |
| R3 (PROG3) | 20.0k | Sets 50mA termination current, 10:1 ratio (Eq. 4-2) | Placed |
| R4/R5 (VPCC divider) | 330k / 110k | Power-path priority threshold, datasheet's own worked example (Section 3.3) | Placed |
| TH1 | 10k NTC | THERM battery-temperature bias (typical application circuit) | Placed |
| C1 | 10uF | IN decoupling (datasheet diagram's shown value; Section 3.1's stated *minimum* is 4.7uF) | Placed -- flagged: 10uF in an 0603 case may be tight to source at a real working voltage rating, verify at BOM time |
| C2 | 4.7uF | OUT/+VSYS decoupling | Placed |
| C3 | 4.7uF | VBAT/VBATT_PROT decoupling | Placed |

Strap pins (SEL, PROG2, TE, CE) are tied directly to logic rails, not through
passives -- see `bay-station/power_bms_notes.md` for the full reasoning.

## Maxim/ADI MAX17048 (bay-station fuel gauge, U2)

Per the datasheet's "Simplified Operating Circuit."

| Passive | Value | Role | Status |
|---|---|---|---|
| C4 | 0.1uF | VDD decoupling (datasheet's typical operating circuit value) | Placed |

CTG tied to GND, QSTRT tied to GND, CELL left unconnected (correct for the
single-cell MAX17048 variant) -- no passives involved in any of those three.

## TI TPS7A0233PDBVR (wristband LDO, U5)

Real datasheet TI SBVS277C. Replaced the Microchip MCP1700T-3302E/TT on
2026-09-23 (`decisions.md`); the MCP1700's 1.6uA Iq had become the board's
largest standby draw.

| Passive | Value | Role | Status |
|---|---|---|---|
| C11 (Cin) | 1uF X7R | Input decoupling | Placed (`regulation.kicad_sch`) |
| C12 (Cout) | 2.2uF X7R | Output decoupling -- SBVS277C S6.3. **Sized up from the MCP1700's 1uF**, so don't "restore" it | Placed |

Note this part has an **EN pin that must be tied high** (pin 3). It is
disabled when EN floats, and it cannot be GPIO-gated, because the MCU it
powers cannot enable its own supply. Pin 4 is NC. The package is SOT-23-**5**
-- the PCB carried a 3-pad SOT-23 for it until 2026-09-25.

**Superseded:** this section previously covered the MCP1700T-3302E/TT with
C11/C12 both at 1uF X7R, from that part's page-2 "Typical Application
Circuit." The older MCP1700 walkthrough still sitting in
`../wristband/regulation_notes.md` under "Capacitors: C11 (Cin), C12 (Cout)"
is stale for the same reason and should be rewritten.

## TI TPS62A02PDDCR (bay-station buck, U8)

Real datasheet SLUSEG9E Table 8-2/8-3 component recommendations + Eq. 2 for
the feedback divider. Detail: `bay-station/regulation_notes.md` section 6.

| Passive | Value | Role | Status |
|---|---|---|---|
| L1 | 1uH, Coilcraft XFL4020-102MEC | Power inductor (Table 8-3 "++" 1uH/22uF pair). Isat 4.5 A, above the 3.4 A max high-side limit | Placed, footprint `L_Coilcraft_XxL4020` (replaced the footprint-less XGL3520-102MEC, 2026-11-17) |
| C20 (Cin) | 4.7uF, 0805 | Input decoupling (Table 8-2, sized up from 0603 for DC-bias derating) | Placed |
| C21 (Cout) | 22uF, 0805 | Output decoupling (Table 8-3's recommended pair for VOUT>=1.8V) | Placed |
| C22 | 120pF, **DNP** | Optional feedforward across R8 for PSM ripple. TI's 120 pF is for the 1.8 V example and is unverified at 3.3 V; fit only after measuring ripple | **Was wired `+3V3`-to-GND, not across R8 -- fixed 2026-11-17** |
| R8 | 453k | FB divider top -- sets VOUT=3.318V (Eq. 2 math, nearest E96 value) | Placed |
| R9 | 100k | FB divider bottom -- at the datasheet's own stated ceiling for acceptable noise sensitivity | Placed |
| R301 | 100k | PG pull-up to `+3V3_REG` (PG gates nothing) | Placed |
| R303 / C303 / R304 | 100k / 1uF / 4.7k | EN delay from U40 PG, so `+3V3` (nRF9151 VDD_GPIO) rises 12-41 ms after `+VBAT_LTE` -- HDG needs >= 6 ms (`regulation_notes.md` section 4) | Placed; DNP R305 restores EN-to-`+VSYS` |

## TI TPS63802DLAR (bay-station buck-boost, U40, `+VBAT_LTE` for nRF9151 VDD)

Real datasheet SLVSEU9D. Detail: `bay-station/regulation_notes.md` section 2.

| Passive | Value | Role | Status |
|---|---|---|---|
| L300 | 0.47uH, Coilcraft XFL4020-471MEC | Sec 8.3: 0.47 uH nominal, 0.37-0.57 uH effective. Isat 4.6 A. TI Table 10-2 lists XFL4015-471ME; XFL4020 used for its KiCad footprint | Placed |
| C300 | 10uF 0805 10V | Input -- "A 10 uF input capacitor is recommended" (Sec 10.2.2.4) | Placed |
| C301 | 22uF 0805 10V | Output -- single 22 uF for VO <= 3.6 V (Sec 10.2.2.3) | Placed |
| C302 | 22uF, **DNP** | Second output cap, TI's recommendation above 3.6 V or for droop | DNP |
| R306 / R307 | 562k / 91k | FB, VFB 500 mV -> 3.588 V (Table 10-5 pair for 3.6 V) | Placed |
| R308 / R309 | 191k / 100k | EN as a precise UVLO: off < 2.91 V, on > 3.20 V `+VSYS` (Sec 8.5 thresholds) | Placed |
| R311 / R312 | 0R / 0R **DNP** | MODE strap: GND = power-save (default), `+VSYS` = forced PWM. "It must not be left floating" (Table 7-1) | Placed / DNP |
| R310 | 0R **DNP** | EN to `+VSYS` (always on) rework option | DNP |

The nRF9151's own VDD bank sits downstream of the R302 break, at the SiP
(section above); TPS63802 has no upper limit on output capacitance.

## Rakon RPT1490LN TCXO + TI LMK1C1104 buffer (bay-station clock_dist, U30/U31) -- PROPOSED

Detail: `bay-station/clock_dist_notes.md`. Rakon gives no decoupling
guidance; the buffer follows TI SNAS791D Fig 11-1.

| Passive | Value | Role | Status |
|---|---|---|---|
| R225 / R226 | 0R 0603 | `+3V3` -> `+3V3_TCXO` / `+3V3_CLKBUF`; current-measure links whose pads take a low-DCR bead (TI s11 recommends, not requires; no bead PN chosen) | Placed |
| C210 / C211 | 10uF / 100nF | TCXO supply | Placed (judgement, no Rakon figure) |
| C212 / C213 / C214 | 10uF / 1uF / 100nF | Buffer VDD: board side, then at the pin (SNAS791D Fig 11-1) | Placed |
| R227 / R228 / C215 | 10k / 8.2k / 100nF | TCXO Vc divider -> 1.49 V (Rakon tuning reference 1.5 V; Vc input >= 1 MOhm) | Placed |
| R229 | 10k | Buffer 1G pull-up -- outputs always on | Placed |
| R230, R231-R234 | 22R | Series source terminations TCXO->CLKIN and Yn->AC cap. Starting value (ROUT ~50 ohm); tune at XTI. **R231-R234 must stay equal** | Placed |
| C24-C27 | 2200pF | AC coupling into each XTI -- "2200 pF is recommended" (DW3000 Table 10) | Placed, at each XTI |
| C28-C31 | 1pF 0402 | XTO to GND, external-clock case (DW3000 v1.3 XTO row) | **Moved to `uwb_array`** 2026-11-17, at pin 22 |

## ST LIS3MDL + LIS2DH (bay-station orientation, U10/U11)

From the ST datasheets (LIS3MDL DocID024204 Rev 4; LIS2DH Doc ID 022516 Rev 1
-- both read from mirrors, ST's site refused the download). Both sensors run
from `+3V3_SNS` behind the R411 current break.

| Passive | Value | Role | Status |
|---|---|---|---|
| C400 | 100nF | LIS3MDL C1 (pin 4) -- mandatory (Table 2 / sec 4.1) | Placed |
| C35 + C401 | 100nF + 1uF | LIS3MDL Vdd (sec 4.1 / Figure 5) | Placed |
| C402 | 100nF | LIS3MDL Vdd_IO -- extra, not in Figure 5 | Placed, DNP-able |
| C36 + C403 | 100nF + 10uF | LIS2DH Vdd at pin 8 (sec 3: "100 nF ceramic, 10 uF aluminum"); 10 uF X5R ceramic used -- check DC-bias derating | Placed |
| C404 | 100nF | LIS2DH Vdd_IO -- extra | Placed, DNP-able |
| R412 / R413 | 0R / 0R DNP | LIS3MDL SA1 strap: GND = 0x1C (DNP high = 0x1E), sec 5.1.1 | Placed |
| R414 / R415 | 0R / 0R DNP | LIS2DH SA0 strap: high = 0x19 (DNP GND = 0x18), sec 5.1.1 / Table 14 | Placed |
| R407-R410 | 0R | Per-sensor SCL/SDA isolation links | Placed |

## Status LEDs (bay-station indicators, D4-D7, D400, D401)

Series resistors computed from each Kingbright datasheet's VF at IF = 2 mA and
the real drive rail (replaces the indicative 1k); reasoning in `decisions.md`,
"Status LED drive rails". All 0603 1 %.

| Passive | Value | Drive | Current |
|---|---|---|---|
| R29 / R30 | 1.5k | `+VSYS` -> D4 / D5 -> MCP73871 STAT1 / STAT2 (open-drain sink) | ~2 mA on adapter, ~1.1 mA on battery |
| R31 | 1k | `+5V_IN` -> D6 -> ~PG. PG must not be pulled above VIN (DS20002090E sec 5.2.4) | ~2.2 mA |
| R32 / R400 / R401 | 1.2k | GPIO (nRF9151 P0.30 / P0.31, BT840 P0.02) -> R -> LED -> GND, active high | ~1.1 mA (0.7-1.5 mA); standard drive IOH >= 1 mA (nRF9151 PS *GPIO*) |

## Summary: what changed this pass

- **Added** (previously missing): 100kΩ IRQ/GPIO8 pulldowns on all 5 DWM3000
  instances (R9 wristband; R25-R28 bay-station), per Qorvo's own Figure 11.
- **Confirmed, not changed**: DWM3000's per-instance decoupling caps go
  beyond Qorvo's own minimal example circuit (which shows none) -- kept as
  reasonable conservative practice, documented rather than removed.
- **Confirmed, not changed**: DWM3000's GPIO5/6 external strap resistors are
  redundant with the chip's own internal default pulls, kept deliberately
  for tighter timing margin.
- Everything else in this document was already resolved and placed in
  earlier passes -- this compile just brings it all into one place and
  verifies nothing was missed against each chip's real reference design.
