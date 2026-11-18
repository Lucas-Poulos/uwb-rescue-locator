# regulation.kicad_sch -- design notes

Hierarchical sub-sheet "Regulation" (sheet-symbol uuid
`5c2a31d1-5b69-4a48-a195-eba324445020`). Two converters, both fed from
`+VSYS` (MCP73871 `OUT`, `power_bms.kicad_sch`):

| Rail | Converter | Loads | Nominal |
|---|---|---|---|
| `+3V3` | U8, TI TPS62A02PDDCR buck | 4x DW3210, BT840, nRF9151 `VDD_GPIO`, LIS3MDL/LIS2DH, TCXO + fan-out buffer, LEDs, I2C pull-ups | 3.318 V |
| `+VBAT_LTE` | U40, TI TPS63802DLAR buck-boost | nRF9151 `VDD` only | 3.588 V |

**Wired 2026-11-17** (nRF9151 host redesign). Every pin now lands on a wire
and a label; the sheet is ERC-clean apart from the long-standing U8
`lib_symbol_issues` warning (see "Symbol note"). The ESP32-era programming
section that used to live in this file moved to
`programming_debug_notes.md` (history section).

Sources read for this pass (PDF/HTML actually opened, not recalled):

- TI **TPS62A02** datasheet SLUSEG9E (Dec 2021, rev. June 2024), `https://www.ti.com/lit/gpn/tps62a02`.
- TI **TPS63802** datasheet SLVSEU9D (Nov 2018, rev. Jan 2021), `https://www.ti.com/lit/gpn/tps63802`.
- Nordic **nRF9151 Product Specification**, "Recommended operating conditions" page, and the
  **nRF9151 Hardware Design Guidelines** (bundle nwp_056) pages *Operating conditions*,
  *Schematic design*, *VDD_GPIO*, *ENABLE*, *nRESET*, *nRESET circuit example*,
  *VDD supply impedance*, *LTE-M and NB-IoT TX current consumption for Power Class 3*,
  *LTE-M and NB-IoT RX*. Read as HTML on docs.nordicsemi.com; **the PS and HDG PDFs are
  behind a Cloudflare challenge and could not be downloaded**, so no PDF revision number is
  quoted. Re-check against the PDF revision before fab.
- Qorvo **DW3000 Datasheet Version 1.1** (Decawave 2020), Table 4 and Table 5.
- Nordic **nRF52840 Product Brief v2.3** (radio current only).
- Microchip **MCP73871** DS20002090E (BAT-to-OUT and IN-to-OUT RDS_ON).
- Coilcraft **XFL4020** Document 745-1 (revised 03/10/26).

## 1. Why `+VBAT_LTE` is its own regulator, not a jumper off `+VSYS`

nRF9151 `VDD` limits (PS, Recommended operating conditions): **3.0 V min,
3.7 V nom, 5.5 V max**, "includes voltage drop, ripple, and spikes". The HDG
*Operating conditions* page adds: "The LTE and DECT NR+ transceiver requires
a minimum voltage of 3.0 V" and "For optimal RF performance in LTE, a
minimum operating voltage of 3.2 V is recommended." HDG *VDD supply
impedance*: "keep supply network impedance at the VDD pin below 0.2 Ohm from
3.75 kHz to 50 kHz."

On battery, `+VSYS` = cell - Q1 drop - MCP73871 BAT-to-OUT pass FET. That FET
is **200 mOhm typ** (DS20002090E Sec 1.0, at VDD 4.5 V, 105 C); Q1 adds tens
of mOhm. At the ~1.2 A worst-case board peak (Sec 3) the path drops ~0.3 V,
so a 3.4 V cell -- still ~10-15% capacity on a typical Li-ion curve -- puts
`+VSYS` near **3.1 V during each TX burst, under the 3.2 V recommendation**,
and a 3.3 V cell crosses the 3.0 V floor. The path impedance alone
(0.2 + Q1 + cell ESR) is already above Nordic's 0.2 Ohm target. A jumper
from `+VSYS` would therefore work on wall power and fail at the low end of
the battery, which is exactly the condition the outdoor station is built to
survive.

At the top end `+VSYS` is the input (<= 5.25 V USB / ~5 V barrel), inside
5.5 V but with only ~0.25 V margin against a high USB source plus ringing.
A regulator removes that concern too.

**Decision: U40 TPS63802 buck-boost, 3.59 V.** Reasons for the part
(SLVSEU9D): VIN 1.3-5.5 V (start-up > 1.8 V) covers both battery and wall
cases; "2-A output current for VI >= 2.3 V, VO = 3.3 V"; 11 uA IQ for LTE
PSM/eDRX idle; defined buck / buck-boost / boost transitions; PG output
usable for sequencing (Sec 9.3.10); true shutdown with load disconnect.
Output 3.59 V rather than 3.7 V so it stays in the single-22 uF case
(Sec 10.2.2.3: "a single 22 uF for all programmed output voltages <= 3.6 V")
and uses TI's own Table 10-5 divider (562k/91k), while keeping 0.39 V over
Nordic's 3.2 V LTE recommendation.

Rejected: KiCad-library TPS63000 (DRC0010J, verified footprint available) --
its datasheet quotes "up to 800-mA output current at 3.3 V in boost", too
close to the 505 mA LTE figure at low cell voltage.

## 2. `+VBAT_LTE` circuit (U40)

| Ref | Value | Why (citation) |
|---|---|---|
| U40 | TPS63802DLAR | Pins (Table 7-1, checked in `-raw` and `-layout`): 1 EN, 2 MODE, 3 AGND, 4 FB, 5 PG, 6 VOUT, 7 L2, 8 GND, 9 L1, 10 VIN. Abs max 6 V all pins (Sec 8.1). Symbol hand-authored in `libs/bay_station.kicad_sym`. Footprint `bay_station:TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm` (TI example land pattern), see Sec 8. |
| L300 | 0.47 uH, Coilcraft XFL4020-471MEC | L = 0.47 uH nominal, 0.37-0.57 uH effective (Sec 8.3, Table 10-1). XFL4020-471: DCR 4.40/5.10 mOhm, Isat 4.6 A (10%)/6.6 A (20%), Irms 7.5 A (Coilcraft 745-1). TI's Table 10-2 lists XFL4015-471ME; XFL4020 chosen because KiCad ships `Inductor_SMD:L_Coilcraft_XxL4020`. |
| C300 | 10 uF 0805 10 V | "A 10 uF input capacitor is recommended" (Sec 10.2.2.4); effective >= 4 uF (Sec 8.3). 0805/10 V because `+VSYS` sits at ~5 V on wall power. |
| C301 | 22 uF 0805 10 V | Single 22 uF for VO <= 3.6 V (Sec 10.2.2.3); effective >= 7 uF for VO > 2.3 V. |
| C302 | 22 uF, **DNP** | Second output cap, TI's recommendation above 3.6 V; fit if VOUT is raised or droop is high. |
| R306 / R307 | 562k / 91k | Eq. 3, VFB = 500 mV: VOUT = 0.5 x (1 + 562/91) = **3.588 V** (Table 10-5 lists this pair for 3.6 V). VFB +/-1% (PWM) -> 3.55-3.62 V. R2 <= 100k (Sec 10.2.2.5). |
| R308 / R309 | 191k / 100k | EN as a precise UVLO: EN rising 1.07/1.10/1.13 V, falling 0.97/1.00/1.03 V (Sec 8.5). Ratio 2.91: **off below +VSYS = 2.91 V (2.82-3.00), on above 3.20 V (3.11-3.29)**. 12 uA standing load. |
| R310 | 0R **DNP** | Rework: EN to +VSYS (always-on); remove R309 when fitted. |
| R311 / R312 | 0R / 0R **DNP** | MODE strap: R311 to GND = power-save mode (default); R312 to +VSYS = forced PWM. "It must not be left floating" (Table 7-1). |
| R302 + J31 | 0R 0805 + DNP 2-pin | Current break point, Sec 5. |

The nRF9151's own `VDD` bank (Nordic HDG *Schematic design* Table 1: C3
47 uF 0805, C4 10 uF 0603, C1/C2 1 uF, C6/C7 4.7 uF, C5/C8 0.1 uF, FB1
BLM18SD220SN1) belongs at the SiP on `connectivity.kicad_sch`, downstream
of R302. It is in addition to C301, and TPS63802 has no upper limit on
output capacitance (Sec 10.2.2.3).

**Operating point check.** Worst case: 0.505 A out at 3.59 V from
VIN = 2.9 V (just above UVLO). Boost duty D = 1 - 2.9/3.59 = 0.19; average
inductor current = 0.505 / (0.9 x 0.81) = 0.69 A, plus ripple -- around
1 A peak, far under L300's 4.6 A Isat and the 4-5.75 A boost current limit
(Sec 8.5). Input current at that point ~0.69 A.

## 3. Power budget

Full table (per load, typ/peak, rail, source) is in
`handoff/power.md`. Summary:

| Rail | Typical | Peak (design) | Regulator rating | Headroom |
|---|---|---|---|---|
| `+3V3` | ~325 mA (4 anchors in RX) | ~356 mA; ~446 mA with nRF9151 `VDD_GPIO` at its 100 mA momentary ceiling | TPS62A02 2 A | >= 4.5x |
| `+VBAT_LTE` | 41 mA LTE-M RX avg (3.7 V, 25 C) | 505 mA LTE-M TX subframe (B1, 3.0 V, 85 C, VSWR 3:1) | TPS63802 2 A (VI >= 2.3 V) | ~4x |
| `+VSYS` (input to both) | ~0.3 A at 5 V | ~1.2 A at 3.0 V battery / ~0.75 A at 5 V (both converters at peak, 90% efficiency assumed) | MCP73871 1.8 A input limit (SEL high) on wall power | OK; on battery the cell supplies it |

Which numbers are datasheet figures and which are allowances is marked
row by row in the handoff table. The four estimate rows are: BT840 total
(the Fanstel datasheet has no current table; 16.4 mA radio TX +8 dBm is
from the nRF52840 Product Brief v2.3), nRF9151 `VDD_GPIO` (Nordic gives
only the 100 mA ceiling), TCXO and fan-out buffer (not yet selected).

The previous "~358 mA vs 2 A" budget (2026-09-19) is superseded: the
MAX-M10S (~10 mA) is gone (GNSS moved into the nRF9151), and the nRF9151's
modem current is on its own rail instead of on `+3V3`.

## 4. Sequencing: `+3V3` after `+VBAT_LTE`

Nordic HDG *VDD_GPIO*: "VDD_GPIO should be applied at least 6 ms after
ENABLE and VDD have been supplied", "VDD_GPIO should be removed before
removing ENABLE or VDD", and "If the ENABLE pin is low, VDD_GPIO should also
be low"; violating it makes GPIO states undefined during boot ("short
high-state pulses"). `VDD_GPIO` is `+3V3`, which also powers everything the
nRF9151 talks to, so a glitch here would toggle UWB resets/chip-selects and
the BT840 reset at power-up.

Implementation (U8 EN, net `EN_3V3`):

- **R303 100k** from `+VBAT_LTE_REG` to `EN_3V3`, **C303 1 uF** to GND:
  tau = 100 ms.
- **R304 4.7k** from U40 PG to `EN_3V3`. While U40 PG is low, EN_3V3 =
  3.588 x 4.7/104.7 = 0.16 V, under U8's 0.4 V falling threshold
  (SLUSEG9E Table 6.5). Discharge current into PG <= 0.76 mA, inside its
  1 mA rating (SLVSEU9D Sec 9.3.10).
- When U40 reaches 95% of VOUT, PG releases and EN_3V3 charges. U8's EN
  rising threshold is **1.2 V** (Table 6.5; only one value is given):
  t = 100 ms x ln(3.588/2.388) = **40.7 ms**. If the real threshold were as
  low as the 0.4 V falling threshold, t = 11.8 ms. Either way >= 6 ms, then
  U8's 1 ms soft start. ENABLE of the nRF9151 is assumed tied to
  `+VBAT_LTE` (HDG *ENABLE*: "In products where nRF9151 is always enabled,
  the ENABLE pin can be connected to VDD ... with a series resistor") --
  **connectivity must do this**, or the 6 ms is measured from whatever
  drives ENABLE instead.
- Power-down: U40 PG drops when VOUT < 90% or when U40 EN goes low (Table
  9-1), discharging EN_3V3 through R304 in ~5 ms; U8 also has its own 2.3 V
  UVLO, while U40 keeps regulating down to 1.25 V in. `+3V3` therefore goes
  first.
- Rework: remove R304 and fit **R305 (DNP 0R)** to tie EN_3V3 to `+VSYS`
  -- the old always-on plan -- if U40 is not fitted or the delay is
  suspected.

Consequence of R308/R309: below `+VSYS` = 2.91 V the whole board shuts off
(U40 off -> PG low -> U8 off). That is intended: a flat cell browns out
cleanly instead of cycling through LTE-burst resets. It also means a cell
below ~3.2 V will not restart the board until external power returns.

**U8 PG** (net `PG_3V3`): open drain, R301 100k pull-up to `+3V3_REG`, to
TP405. **It gates nothing**: every `+3V3` consumer shares the one rail, so
there is no later rail to hold off, and the nRF9151 could only read it
while it is itself powered from `+3V3`. It is a bring-up observable.

## 5. Current-measurement break points

| Rail | Link | Header | Regulator side net | Load side net |
|---|---|---|---|---|
| `+3V3` | R300 0R 0805 | J30, DNP 1x2 2.54 mm | `+3V3_REG` | `+3V3` |
| `+VBAT_LTE` | R302 0R 0805 | J31, DNP 1x2 2.54 mm | `+VBAT_LTE_REG` | `+VBAT_LTE` |

Remove the 0R and connect a Nordic Power Profiler Kit II in ampere-meter
mode (VIN to pin 1 = regulator side, VOUT to pin 2 = load side). Both FB
dividers (R8/R9, R306/R307), U8's PG pull-up and the EN_3V3 pull-up are on
the **regulator side**, so removing a link never opens a control loop or
changes the sequencing. 0805 rather than the house 0603 because 0R jumpers
are rated ~2 A in 0805 against ~1 A in 0603 and `+VBAT_LTE` carries 0.5 A
TX subframes (check the chosen jumper's rating at BOM time). The PPK2's
1 A ampere-meter limit covers both rails' peaks. A `PWR_FLAG` sits on each
load-side net because the only `power_out` pin is behind the link.

## 6. +3V3 circuit (U8), as wired

| Ref | Part | Value | Notes |
|---|---|---|---|
| U8 | TPS62A02PDDCR | -- | SOT-23-6, pins 1 EN, 2 GND, 3 SW, 4 VIN, 5 PG, 6 FB (Table 5-1). VIN on `+VSYS`; EN on `EN_3V3` (Sec 4); PG on `PG_3V3`. |
| L1 | Coilcraft XFL4020-102MEC | 1.0 uH | **Footprint now assigned** (`Inductor_SMD:L_Coilcraft_XxL4020`). DCR 10.8/11.9 mOhm, Isat 4.5 A (10%), Irms 5.4 A (745-1) -- above the TPS62A02 3.4 A max high-side limit (Table 6.5). Replaces the footprint-less XGL3520-102MEC. Same 1 uH / 22 uF "++" pair from Table 8-3. |
| C20 | 4.7 uF 0805 X7R | -- | VIN (Table 8-2). |
| C21 | 22 uF 0805 X7R | -- | Output (Table 8-2/8-3). |
| C22 | 120 pF, **DNP** | -- | Feedforward across R8. **Bug fixed:** it was wired `+3V3`-to-GND, contradicting its own description. TI's 120 pF is for the 1.8 V example; at 3.3 V (R1 = 453k) the zero is at 2.9 kHz, unverified -- fit only after measuring PSM ripple. Table 8-3 note 4: requires Cout >= 22 uF (met). |
| R8 / R9 | 453k / 100k | -- | Eq. 2: VOUT = 0.6 x (1 + 4.53) = **3.318 V**; with VFB 594-606 mV (0-125 C) -> 3.285-3.351 V before resistor tolerance. Under the 3.6 V maxima of DW3210 VDD1/2/3 (DW3000 DS v1.1 Table 4), BT840 and nRF9151 `VDD_GPIO` (1.7-3.6 V). |
| R301 | 100k | -- | PG pull-up to `+3V3_REG`. |
| R303/C303/R304/R305 | 100k / 1 uF / 4.7k / 0R DNP | -- | EN_3V3 delay, Sec 4. |
| R300 + J30 | 0R 0805 + DNP header | -- | Break point, Sec 5. |

Low-battery behaviour: below ~3.45 V on `+VSYS` the TPS62A02 enters 100%
duty-cycle mode (SLUSEG9E Sec 7.3.2) and `+3V3` tracks `+VSYS` minus the
high-side FET (100 mOhm) and L1 DCR. At the 2.91 V UVLO point that is still
~2.8 V -- above the DW3210's 2.4 V VDD2 minimum (DW3000 DS v1.1 Table 4)
and the 1.7 V floors of the Nordic parts.

Footnote from SLUSEG9E Table 6.3: "Operating continuously at 2-A with
input voltages < 3.3V ... might result in thermal shutdown" -- irrelevant
at ~0.45 A.

## 7. Test pads (local nets, `TestPoint:TestPoint_Pad_D1.0mm`)

| TP | Net | Expect |
|---|---|---|
| TP400 | `+3V3_REG` | 3.32 V |
| TP401 | `+3V3` | 3.32 V (0 V with R300 removed) |
| TP402 | `SW_3V3` | 2.4 MHz switching (PWM) or bursts (PSM) |
| TP403 | `FB_3V3` | 0.600 V |
| TP404 | `EN_3V3` | RC ramp to 3.59 V, ~40 ms after PG_LTE |
| TP405 | `PG_3V3` | high once +3V3 >= 96% |
| TP406 | `+VBAT_LTE_REG` | 3.59 V |
| TP407 | `+VBAT_LTE` | 3.59 V (0 V with R302 removed) |
| TP408 | `EN_LTE` | +VSYS x 0.344 (1.72 V at 5 V) |
| TP409 | `PG_LTE` | high once VOUT >= 95% |
| TP410 | `FB_LTE` | 0.500 V |
| TP411 / TP412 | `L1_LTE` / `L2_LTE` | buck/boost switch nodes |
| TP413 | `MODE_LTE` | 0 V (PSM) |

**Layout rule for TP402/TP411/TP412 (switch nodes):** place the pad on the
existing switch-node copper with no stub; if that is not possible, leave
the pad off the board -- a stub on a switch node is an antenna. FB pads are
high impedance: probe with >= 10 MOhm.

## 8. U40 footprint -- resolved 2026-11-18

`libs/bay_station.pretty/TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm.kicad_mod`.
Package outline from SLVSEU9D drawing 4223750/D: 2.1/1.9 x 3.1/2.9 mm body,
5 pins per long side at 0.5 mm, pin 1 opposite pin 10, no exposed pad. The
land pattern is TI's "Example Board Layout" and the paste is TI's "Example
Stencil Design" (same drawing number, 03/2019), read from the *rendered* PDF
pages -- the earlier version was an estimate because `pdftotext` drops the
dimension leaders. Pins 1-5: 0.6 x 0.25 mm lands centred 0.9 mm left of the
package centreline; pins 6, 7, 9, 10: 0.9 x 0.25 mm centred 0.75 mm right;
**pin 8 (GND): a 1.3 x 0.25 mm land** (from 0.11 mm left of the centreline to
1.2 mm right), pasted with two 0.55 mm apertures. The "4X (0.75)" and
"4X (0.25)" that were unassigned before are the right-column centre offset and
land height. These are TI's example (non-solder-mask-defined, mask 0.07 mm
larger all around), not a mandate; fabs may adjust. TI also publishes a HotRod
QFN PCB-attachment application report (cited in SLVSEU9D Sec 13.2.1).

## 9. Why TPS62A02 for +3V3 (original selection, 2026-09)

Kept for the reasoning; the load figures in it are historical -- Sec 3 is current.

**U8 = TPS62A02PDDCR** (Texas Instruments), a 2.5V-5.5V input, 2A synchronous
step-down buck converter, SOT-23-6 (DDC package), PSM+PWM auto power-save
mode, adjustable output via external resistor divider. Real TI datasheet
SLUSEG9E (Dec 2021, revised June 2024), `https://www.ti.com/lit/gpn/tps62a02`
-- downloaded and read directly (not a search-snippet guess):

- Table 5-1 "Pin Functions" (SOT23-6 DDC package): 1=EN, 2=GND, 3=SW, 4=VIN,
  5=PG, 6=FB.
- Table 6.1 "Absolute Maximum Ratings": VIN -0.3V to **6.5V**.
- Table 6.3 "Recommended Operating Conditions": VIN **2.5V to 5.5V**, IOUT up
  to 2A (TPS62A02 variant).
- Table 6.5 "Electrical Characteristics": VFB = 600 mV typ (594-606 mV over
  0-125C), IQ(VIN) = 23 uA typ (non-switching).
- Section 8.2.2.1 "Setting the Output Voltage", Equation 2: `R1 = R2 x
  (VOUT/VFB - 1)`.
- Table 8-2 "List of Components" (typical application): C1=4.7uF/0805 X7R
  (Murata GRM21BR71A475KA73L), C2=22uF/0805 X7R (Murata GRM21BZ71A226KE15L),
  L1=1uH power inductor (Murata DFE252012F-1R0M for the 1A TPS62A01, or
  Coilcraft XGL3520-102MEC for the 2A TPS62A02), R1/R2 = 1% 0603 chip
  resistors, C3 = optional 120pF feedforward cap.
- Table 8-3 "Matrix of Output Capacitor and Inductor Combinations": for
  VOUT >= 1.8V (our 3.3V target), L=1uH with Cout=22uF is one of the "++"
  (proven-stable-by-simulation-and-lab-test) combinations.

**Why TPS62A02 over the higher-current TI TPS563201/TPS563200 family** (which
was the first candidate considered, since it's an extremely common,
well-documented, easy-to-source 3A SOT-23-6 buck): the TPS563201 family's
recommended VIN range is **4.5V-17V**. This board's `+VSYS` rail can sag to
~3.0-4.4V when running from the single-cell Li-Ion battery alone (no external
power connected) -- comfortably *below* the TPS563201's 4.5V minimum input.
TPS62A02's 2.5V-5.5V input range is explicitly designed for exactly this
single-cell-Li-Ion-powered scenario (TI markets the whole TPS62A0x family for
"Battery-powered applications"), while its 6.5V absolute-max VIN still gives
headroom over the documented ~5V-class wall/USB-present condition (and over
MCP73871's own 7.0V IN absolute-max, so the buck won't be the first thing to
fail if the input creeps toward that ceiling). **2A rated output gives ~5.6x
headroom** over the ~358 mA worst-case combined peak budget above -- chosen
deliberately generous since this board isn't size-constrained, prioritizing a
modern, well-documented TI part with a straightforward datasheet-verified
design over the smallest/cheapest option. That generosity is exactly what
absorbed three architecture changes without a respin: the load first grew
from 575 mA to 682 mA when the DWM3000 modules became discrete DW3210s with
a shared clock network, then fell to ~347 mA when the WiFi host was replaced
by a BLE one, then rose slightly to ~358 mA when the GNSS and orientation
sensors were added. Sizing generously up front is what let all three happen
for free.

## 10. U8 symbol note (flattened cache, same precedent as AO3401A)

KiCad's own default `Regulator_Switching:TPS62A02PDDCR` symbol is defined as
`(extends "TPS62A01PDDC")` (inherits the 1A variant's graphics/pins). Per the
exact same `kicad-cli` headless-loader limitation already discovered and
documented for `Transistor_FET:AO3401A` on `power_bms.kicad_sch` (see
`power_bms_notes.md`, "AO3401A extends-symbol issue"), this project's embedded
`lib_symbols` cache for U8 is a **flattened** copy (graphics/pins duplicated
directly from the real `TPS62A01PDDC` base, no `extends`) rather than KiCad's
live extends-based definition. `lib_id` is still
`Regulator_Switching:TPS62A02PDDCR` (the real default part is still what's
referenced/ordered) -- only the embedded cache representation differs. This
produces one expected, benign `lib_symbol_issues` ERC warning ("Symbol
'TPS62A02PDDCR' not found in symbol library 'Regulator_Switching'"), the same
category and cause as the existing AO3401A warning.

## 11. DWM3000 GPIO5/GPIO6 SPI-mode-strap pull resistors (uwb_array.kicad_sch)

**The gap:** the real Qorvo DWM3000 Data Sheet Rev B explicitly shows, in both
Figure 1 ("Timing diagram for cold start POR") and Figure 2 ("Timing diagram
for warm start"), a **"Sample GPIOs 5&6 to set SPI mode"** step during the AON
power-up sequence, before the digital core reaches its active states. Table 2
"DWM3000 Pin Functions" confirms: GPIO6/EXTRXE/SPIPHA (pin 9) and
GPIO5/EXTTXE/SPIPOL (pin 10) "act as the SPIPHA/SPIPOL pin for configuring the
SPI mode of operation" on power-up, defaulting to General Purpose I/O
afterward. Section 6.3 "GPIO and SPI I/O Internal Pull Up / Down" confirms all
GPIOs default to an internally SW-controllable pull-down (10k-30k, varying
with VDD1 per Figure 12), which already yields SPI mode 0 (SPIPOL=0, SPIPHA=0)
by default -- but the task explicitly calls for defined external pull
resistors rather than leaving these boot-sampled pins to rely solely on an
internal, VDD1-dependent, software-configurable default across all 4 anchor
instances.

**The fix:** 8 external 10k pull-down resistors added directly to
`uwb_array.kicad_sch` (not compacted into a shared note -- placed in full,
matching this sheet's existing per-anchor-explicit-component convention, where
each anchor already gets its own full decoupling set rather than an implied
shared passive):

| Ref | Anchor | Pin | Function |
|---|---|---|---|
| R10 | U4 | GPIO5/EXTTXE/SPIPOL (pin 10) | 10k to GND |
| R11 | U4 | GPIO6/EXTRXE/SPIPHA (pin 9) | 10k to GND |
| R12 | U5 | GPIO5/EXTTXE/SPIPOL (pin 10) | 10k to GND |
| R13 | U5 | GPIO6/EXTRXE/SPIPHA (pin 9) | 10k to GND |
| R14 | U6 | GPIO5/EXTTXE/SPIPOL (pin 10) | 10k to GND |
| R15 | U6 | GPIO6/EXTRXE/SPIPHA (pin 9) | 10k to GND |
| R16 | U7 | GPIO5/EXTTXE/SPIPOL (pin 10) | 10k to GND |
| R17 | U7 | GPIO6/EXTRXE/SPIPHA (pin 9) | 10k to GND |

Pulling both low explicitly defines **SPI mode 0** (SPIPOL=0, SPIPHA=0), which
is also what the DWM3000's own internal pull-down default already selects --
this reinforces/guarantees that default in hardware rather than leaving it to
chance.

## Reference designators

Regulation sheet: U8, L1, C20-C22, R8, R9 (existing); U40, L300, C300-C303,
R300-R312, J30, J31, TP400-TP413, #FLG300, #FLG301 (added 2026-11-17).
**TP4xx is outside the power block in the coordinator's designator table
(TP100-TP399 is io's); TP400-TP449 were used because the power block had
no TP range -- confirm with the coordinator.**

## Open concerns / not fully confident about

- ~~U40 footprint is a placeholder~~ -- resolved 2026-11-18 (Sec 8).
- **Nordic PDFs not opened.** All nRF9151 facts come from the
  docs.nordicsemi.com HTML pages (PS and HDG); the PDFs are behind a
  Cloudflare challenge. Quote the PDF revision once someone downloads it.
- **nRF9151 ENABLE wiring is assumed** (tied to `+VBAT_LTE` through a
  series resistor). If connectivity drives ENABLE from something else, the
  `VDD_GPIO` sequencing argument in Sec 4 must be redone.
- **U8 EN rising threshold** is given as a single 1.2 V figure; the delay
  is checked against both 1.2 V and 0.4 V to bracket it.
- **C22 value** at 3.3 V is not verified (DNP until measured).
- **UVLO at 2.91 V `+VSYS`** includes the BAT-to-OUT and Q1 drops, so the
  cell-side cut-off under LTE bursts is ~0.2-0.3 V higher (~3.1-3.2 V
  cell). Tune R308 once the cell and its protection IC are chosen.
- **`+VSYS` high side** still rests on the "~5 V-class input" assumption
  from `power_bms_notes.md`; both converters are 5.5 V-recommended / 6 V
  (TPS63802) or 6.5 V (TPS62A02) abs max.
- **0R jumper current rating** (0805, ~2 A typical) to be confirmed for
  the chosen part.
