# Passive components reference, per chip

Compiled from each chip's own datasheet reference/typical-application
circuit -- not guessed. This is the definitive cross-reference for "what
does this IC need around it and why"; per-sheet component tables in each
board's `*_notes.md` are the more detailed originals this was compiled from.
All passives are standard **0603** (`R_0603_1608Metric` / `C_0603_1608Metric`
/ `L_0603_1608Metric`) unless noted otherwise.

## u-blox NINA-B400 (wristband, U3)

*Migrated from NINA-B111 on 2026-09-15 — see `decisions.md`.*

The module carries its own integrated DC/DC converter (NINA-B4 system
integration manual UBX-19052230 R13 §2.2.1), so there is nothing external to
add for its internal supply rails. u-blox's guidance on external capacitance is
deliberately loose: *"It is best practice to include bypass capacitors on the
supply rails close to the NINA-B4 series module. Depending on the design of the
power routing on the host system, capacitance might not be needed."* (§2.2.3.1)

| Passive | Value | Role | Status |
|---|---|---|---|
| C6, C7 | 100nF | VCC (pin 10) / VCC_IO (pin 9) bypass | Placed (`radio_mcu.kicad_sch`). Standard practice; u-blox mandates no specific value. **Note pin 9 VCC_IO must be tied to VCC** — data sheet UBX-19049405 R09 Table 6 says "Must be connected to VCC", and §2.2.2 confirms VCC_IO is internally bonded to VCC. Both are wired to `+3V3`. |
| Y1 | 32.768 kHz (Epson FC-135, `Q13FC13500004`) | LFXO low-power clock on XL1/XL2 (pins 2/3) | **Added 2026-09-15.** Required for low sleep current — SIM §1.9: *"To reach the lowest sleep current consumption of the NINA-B4 module, an external crystal or external clock source shall be used."* Meets every line of data sheet Table 14: ±20 ppm vs ±500 ppm max, CL 12.5 pF vs 12.5 pF max, ESR 70 kΩ vs 100 kΩ max. Without it the module falls back to its internal RC oscillator at higher sleep current — and Table 6 would then require XL1/XL2 be grounded rather than left floating. |
| C14, C15 | 18pF C0G (`CL10C180JB8NNNC`) | Y1 load capacitors | **Added 2026-09-15.** Derived, not guessed: each leg needs Ca = 2 × CL = 25 pF; subtracting the module's own 5 pF XL1/XL2 pin capacitance (Table 14, `Cpin`) and ~2 pF PCB stray gives 18 pF. Re-check once the real stackup exists. C0G dielectric is required for oscillator stability over temperature. |
| SW1 | — (Panasonic `EVQPUA02K`) | SOS / user button on GPIO_21 | **Added 2026-09-15.** Pulls the GPIO low when pressed; uses the nRF52833's internal pull-up, so no external pull resistor part is needed. Debounce in firmware. Actuation force (2.2 N) should be re-checked for gloved/cold-weather use — this is a rescue device. |
| R11, R12 | 1M / 1M (`RC0603FR-071ML`) | Battery-voltage sense divider to GPIO_23 (analog-capable) | **Added 2026-09-15.** Halves VBAT's 4.2 V full-charge to 2.1 V, inside SAADC range at a 3.3 V reference. **Tradeoff:** 4.2 V / 2 MΩ ≈ 2.1 µA continuous, comparable to the module's own ~2.6 µA System-ON sleep current (Table 12) — this roughly doubles standby drain. Gate the low side with a FET and sample on demand if runtime matters more than always-on reporting. |
| C16 | 100nF | SAADC sampling reservoir across R12 | **Added 2026-09-15.** The divider's ~500 kΩ source impedance is high for the SAADC; this cap plus a long acquisition-time setting in firmware is what makes the reading accurate. |

External **antenna required** (B400 has no on-module antenna — it has an
on-module U.FL connector instead, so no PCB-side connector or matching network
is needed). Resolved: Abracon PRO-IS-237, see `decisions.md`.

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

## Espressif ESP32-S3-WROOM-1 (bay-station connectivity, U3)

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

## Microchip MCP1700T-3302E/TT (wristband LDO, U5)

Real datasheet "Typical Application Circuit," page 2.

| Passive | Value | Role | Status |
|---|---|---|---|
| C11 (Cin) | 1uF X7R | Input decoupling (datasheet's exact shown value; the part is stable with only 1uF) | Placed (`regulation.kicad_sch`) |
| C12 (Cout) | 1uF X7R | Output decoupling (same) | Placed |

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
