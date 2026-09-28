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

Replaced the ESP32-S3-WROOM-1 on 2026-09-19. The BT840 is a certified module
with on-board DC-DC and its own antenna, so there is no external application
circuit to work from -- C5/C6/C7 on `connectivity.kicad_sch` are conservative
3V3 supply decoupling, not datasheet-specified values.

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

Real datasheet Table 8-2/8-3 component recommendations + Eq. 2 for the
feedback divider.

| Passive | Value | Role | Status |
|---|---|---|---|
| L1 | 1uH | Power inductor (Table 8-3) | Placed (`regulation.kicad_sch`) -- **no KiCad-default footprint exists** for the chosen Coilcraft XGL3520-102MEC; source a real footprint at BOM time (open item, `docs/decisions.md`) |
| C20 (Cin) | 4.7uF, 0805 | Input decoupling (Table 8-2, sized up from 0603 for DC-bias derating) | Placed |
| C21 (Cout) | 22uF, 0805 | Output decoupling (Table 8-3's recommended pair for VOUT>=1.8V) | Placed |
| C22 | 120pF | Optional feedforward cap across R8, reduces PSM ripple (datasheet's own note) | Placed |
| R8 | 453k | FB divider top -- sets VOUT=3.318V (Eq. 2 math, nearest E96 value) | Placed |
| R9 | 100k | FB divider bottom -- at the datasheet's own stated ceiling for acceptable noise sensitivity | Placed |

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
