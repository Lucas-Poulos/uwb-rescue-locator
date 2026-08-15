# regulation.kicad_sch + programming_debug.kicad_sch -- design notes

Two new hierarchical sub-sheets fixing three confirmed hardware gaps on the bay
station: (1) no regulated 3.3V rail for the ESP32-S3-WROOM-1 / 4x DWM3000 loads
(they were tracking the unregulated `+VSYS` rail directly, up to ~4.2V+), (2)
floating DWM3000 GPIO5/GPIO6 SPI-mode-strapping pins, (3) missing ESP32-S3
boot-strapping pulls, reset/boot buttons, and a flashing interface. Wired into
`bay-station.kicad_sch` as sheets "Regulation" (sheet-symbol uuid
`5c2a31d1-5b69-4a48-a195-eba324445020`) and "Programming / Debug" (sheet-symbol
uuid `883ff08c-ad9f-4863-b9db-49772b53748e`), registered in
`bay-station.kicad_pro`'s `sheets` list. **Placement only, same as
`connectivity`/`uwb_anchors`/`mechanical`: no wires, no global labels.**

## 1. Buck converter selection: TI TPS62A02 (TPS62A02PDDCR)

### The problem being fixed

`power_bms.kicad_sch`'s `+VSYS` rail (MCP73871's power-path `OUT` pin) is
explicitly documented in `power_bms_notes.md` as **not regulated**: it tracks
close to whichever of (current-limited `IN`, `VBAT`) has priority -- i.e.
roughly the ~5V-class input when external power is present, or the raw
single-cell Li-Ion range (~3.0-4.4V) when running from battery alone. Both the
ESP32-S3-WROOM-1 and the DWM3000 need a real regulated ~3.3V supply that can't
exceed their absolute-maximum ratings:

- **DWM3000 abs-max VDD3V3/VDD1: -0.3V to 4.0V.** Verified directly from the
  real Qorvo DWM3000 Data Sheet Rev B, May 2021, Table 9 "DWM3000 Absolute
  Maximum Ratings" (`https://download.mikroe.com/documents/datasheets/DWM3000_datasheet.pdf`,
  already the datasheet URL cited in `libs/components.csv`/`uwb_anchors.kicad_sch`).
- **ESP32-S3-WROOM-1 abs-max VDD33: -0.3V to 3.6V.** Verified directly from the
  real Espressif ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8, Table 6-1
  "Absolute Maximum Ratings" (`https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf`,
  already the datasheet URL cited in `libs/components.csv`/`connectivity.kicad_sch`).

An unregulated ~4.2V+ rail directly violates the ESP32-S3's 3.6V abs-max (and
gets uncomfortably close to the DWM3000's 4.0V abs-max too, with essentially no
margin once any ripple/tolerance is considered). The user decided this needs a
**switching buck converter** (not the wristband's LDO), consistent with the bay
station's longevity/efficiency-focused design philosophy (see `README.md`).

### Current-draw budget (real datasheet numbers, not estimates)

- **ESP32-S3-WROOM-1 peak current: 355 mA.** Real Espressif ESP32-S3-WROOM-1
  Datasheet v1.8, Section 6.4.1 "Current Consumption in Active Mode", Table
  6-4 "Current Consumption for Wi-Fi (2.4 GHz) in Active Mode": the highest
  listed peak is 802.11b, 1 Mbps, @20.5 dBm TX = **355 mA** (the Bluetooth LE
  TX table peaks lower, at 344 mA @20.0 dBm, so Wi-Fi TX is the worst case).
- **DWM3000 worst-case current: 55 mA each.** Real Qorvo DWM3000 Data Sheet
  Rev B, Table 5 "DWM3000 DC Characteristics" (`Tamb=25C`, "Total current drawn
  from all supplies"): CH9 RX = 55 mA typ (the highest single figure in the
  table; CH9 TX = 45 mA, CH5 RX = 50 mA, CH5 TX = 40 mA, IDLE modes 12-20 mA).
  Worst-case simultaneous 4-anchor RX: **4 x 55 mA = 220 mA.**
- **Combined worst-case peak (conservative, assumes simultaneous ESP32-S3 TX
  burst + all 4 anchors in RX):** 355 mA + 220 mA = **575 mA.**

This is a genuinely conservative stack-up (in practice the anchor array is
unlikely to have all 4 units in RX at the exact same instant as an ESP32-S3
Wi-Fi TX burst), but it's the right number to size against.

### Part chosen and why

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
fail if the input creeps toward that ceiling). **2A rated output gives ~3.5x
headroom** over the 575 mA worst-case combined peak budget above -- chosen
deliberately generous since this board isn't size-constrained, prioritizing a
modern, well-documented TI part with a straightforward datasheet-verified
design over the smallest/cheapest option.

### Circuit built on `regulation.kicad_sch`

| Ref | Part | Value | Notes |
|---|---|---|---|
| U8 | TPS62A02PDDCR | -- | Buck converter, SOT-23-6. See "Symbol note" below. |
| L1 | Power inductor | 1uH | Between SW (pin 3) and the output node, per Table 8-3. No exact KiCad-default footprint for the Coilcraft XGL3520-102MEC (2A-rated) was found; pick footprint/PN at BOM time, same convention as this board's other generic parts. |
| C20 | Ceramic cap | 4.7uF | VIN decoupling, 0805 (per Table 8-2's Murata GRM21BR71A475KA73L) -- sized up from 0603 given the same DC-bias-derating concern already flagged for `power_bms.kicad_sch`'s C1. |
| C21 | Ceramic cap | 22uF | Output (`+3V3_SYS`) decoupling, 0805 (Murata GRM21BZ71A226KE15L), matching Table 8-3's recommended L=1uH/Cout=22uF pair for VOUT>=1.8V. |
| C22 | Ceramic cap | 120pF | Optional feedforward cap across R8, per the datasheet's own PSM-ripple-reduction note ("a 120pF capacitor is good for the 1.8V output typical application" -- reused here since this rail also runs PSM). |
| R8 | Resistor | 453k | FB divider top (VOUT to FB). See math below. |
| R9 | Resistor | 100k | FB divider bottom (FB to GND) -- at the datasheet's own stated ceiling ("R2 must not be higher than 100 kOhm to provide acceptable noise sensitivity"). |

**Output voltage math (Eq. 2):** `R1 = R2 x (VOUT/VFB - 1)`. Target VOUT =
3.3V, VFB = 0.6V typ, R2 = 100k (datasheet ceiling): `R1 = 100k x (3.3/0.6 - 1)
= 100k x 4.5 = 450k`. 453k is the nearest standard 1% E96 value (100k x 4.53),
giving `VOUT = 0.6V x (1 + 453k/100k) = 0.6V x 5.53 = 3.318V` -- within 0.5% of
the 3.3V target, and with comfortable margin under both abs-max ratings above
(0.28V margin to ESP32-S3's 3.6V, 0.68V margin to DWM3000's 4.0V).

**Intended rail names (not yet wired, per the placement-only rule):** input =
`+VSYS` (from `power_bms.kicad_sch`'s MCP73871 `OUT`/`VBATT_PROT` node, once a
future wiring pass connects the two sheets), output = **`+3V3_SYS`** (a new
regulated rail intended to feed U3 on `connectivity.kicad_sch` and U4-U7 on
`uwb_anchors.kicad_sch`). EN (pin 1) is left unconnected here -- it needs to be
tied to `+VSYS` (always-on) in a future wiring pass, since "EN must be
terminated and not left floating" per the datasheet. PG (pin 5, power-good) is
intentionally left unconnected/unused -- the datasheet explicitly allows this
("If not used, leave the power-good pin open or connect to GND").

### Symbol note (flattened cache, same precedent as AO3401A)

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

## 2. DWM3000 GPIO5/GPIO6 SPI-mode-strap pull resistors (uwb_anchors.kicad_sch)

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
internal, VDD1-dependent, software-configurable default across 4 separate
remote anchor boards.

**The fix:** 8 external 10k pull-down resistors added directly to
`uwb_anchors.kicad_sch` (not compacted into a shared note -- placed in full,
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

## 3. ESP32-S3-WROOM-1 boot-strapping, buttons, and flashing interface (programming_debug.kicad_sch)

### Boot-strapping pull resistors

Per the real Espressif ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8 (already
cited above), Section 4 "Boot Configurations" and Table 4-1 "Default
Configuration of Strapping Pins":

| Ref | Pin (U3) | Direction | Value | Why |
|---|---|---|---|---|
| R18 | GPIO0 (pin 27) | pull-up to `+3V3_SYS` | 10k | GPIO0=1 selects SPI Boot (normal boot) per Table 4-3 "Chip Boot Mode Control". Default strap state is already weak-pull-up (Table 4-1, ~45k per Table 6-3's `RPU`), but the datasheet's own guidance ("It is recommended to place a pull-up resistor at the GPIO0 pin") is followed to make it explicit/robust. |
| R19 | GPIO3 (pin 15) | pull-down to GND | 10k | Section 4.4 "JTAG Signal Source Control" states verbatim: "This pin does not have any internal pull resistors and the strapping value must be controlled by the external circuit that cannot be in a high impedance state." Default eFuse JTAG-source config (Table 4-5, all-zero) ignores GPIO3 for source selection, so the pull *direction* isn't functionally critical yet, but an external pull is required by the datasheet's own text regardless of eFuse state. |
| R20 | GPIO45 (pin 26) | pull-down to GND | 10k | Table 4-4 "VDD_SPI Voltage Control": GPIO45=0 selects the 3.3V VDD3P3_RTC-derived SPI-flash voltage (matching this module's standard 3.3V-flash variant, not the `-N16R16VA` 1.8V variant). Matches GPIO45's own default weak-pull-down (Table 4-1), made explicit. |
| R21 | GPIO46 (pin 16) | pull-down to GND | 10k | Table 4-1 default is weak-pull-down; Espressif explicitly states the combination "GPIO46=1 with GPIO0=0 is invalid and may trigger unexpected behavior" -- pulling GPIO46 down guarantees a valid boot-mode strap combination alongside R18/SW1. |
| R22 + C23 | EN (pin 3) | RC delay: 10k pull-up to `+3V3_SYS` + 1uF to GND | 10k / 1uF | Not a strapping pin, but Espressif's real **ESP32-S3 Hardware Design Guidelines** (`docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html`, the "Schematic Checklist" section, distinct from the module datasheet) states verbatim: "The recommended setting for the RC delay circuit is usually R = 10 kOhm and C = 1 uF." |

### Buttons

- **SW1 (BOOT):** momentary switch from GPIO0 to GND. Pulling GPIO0 low at
  reset enters Joint Download Boot mode (Table 4-3) for flashing -- standard
  practice on essentially every ESP32-S3 dev/breakout board.
- **SW2 (RESET):** momentary switch from EN to GND, alongside the R22/C23 RC
  delay -- standard manual-reset practice.

Both use KiCad's default `Switch:SW_Push` (a real, generic, 2-pin part already
in KiCad's bundled `Switch.kicad_sym`) -- footprint left blank, pick an exact
tactile-switch PN (e.g. Panasonic EVQ-PUJ or C&K PTS645-series) at BOM time,
matching this board's existing convention for generic connectors/passives
(see `libs/components.csv`).

### Flashing/programming interface decision: native USB, with a caveat

**Chosen: native USB via the ESP32-S3's built-in USB-OTG peripheral**, not a
separate UART-to-USB bridge IC (e.g. CH340/CP2102). Reasoning, backed by the
real datasheet:

- Espressif ESP32-S3-WROOM-1 Datasheet v1.8, Section 5.2.1.7 "USB 2.0 OTG
  Full-Speed Interface" and 5.2.1.8 "USB Serial/JTAG Controller": the chip has
  a full-speed USB 2.0 OTG peripheral *and* a separate USB-Serial/JTAG
  controller with CDC-ACM (virtual serial port) emulation built in --
  "Internal PHY, so no or very few external components needed to connect to a
  host computer" and "CDC-ACM supports host controllable chip reset and entry
  into download mode."
- Table 4-3 "Chip Boot Mode Control" explicitly lists "USB-Serial-JTAG
  Download Boot" and "USB-OTG Download Boot" as supported Joint Download Boot
  methods -- flashing over native USB is a first-class, Espressif-supported
  path, not a hack.
- No extra bridge IC is needed, saving part count/cost/board area on a board
  that already has USB-C connectors for power.

**The caveat (a real finding, not glossed over):** the board's *existing*
USB-C receptacle (`J2` on `power_bms.kicad_sch`) is
`Connector:USB_C_Receptacle_PowerOnly_6P` -- **it has no D+/D- pins at all**,
so it physically cannot carry the native-USB data lines (U3's `USB_D-`/`USB_D+`
pins, pins 13/14 on `connectivity.kicad_sch`). Since `power_bms.kicad_sch` is
explicitly out of scope for this task (must not be edited), this sheet places
a **second, dedicated data-capable USB-C receptacle**:

| Ref | Part | Notes |
|---|---|---|
| J3 | `Connector:USB_C_Receptacle_USB2.0_14P` | Real KiCad-default part with D+/D- pins (A6/A7/B6/B7). Intended to carry U3's native USB (D+/D- to U3 pins 14/13) for programming/debug. |
| R23 | 5.1k, J3 CC1 to GND | Standard USB-C UFP-device pulldown, matching the identical R6/R7 convention already used for J2 on `power_bms.kicad_sch`. |
| R24 | 5.1k, J3 CC2 to GND | See R23. |

**Open concern, flagged rather than fixed:** this leaves the board with *two*
USB-C connectors (J2 for power-only, J3 for programming/debug) instead of one
combined connector. A future hardware revision could swap J2 for a
power+data-capable USB-C receptacle (e.g.
`Connector:USB_C_Receptacle_USB2.0_16P`) to consolidate to a single connector
and drop J3/R23/R24 entirely -- not done here since `power_bms.kicad_sch`
cannot be touched in this pass.

## Reference designators used

`U8, L1, C20, C21, C22, R8, R9` (regulation.kicad_sch); `R10-R17`
(uwb_anchors.kicad_sch additions); `SW1, SW2, J3, R18-R24, C23`
(programming_debug.kicad_sch). All within the pre-cleared next-available
ranges for this board.

## Open concerns / not fully confident about

- **Two USB-C connectors** (J2 power-only, J3 data) instead of one combined
  connector -- see "flashing/programming interface" section above.
- **L1's exact footprint** (Coilcraft XGL3520-102MEC or equivalent 1uH/2A+
  shielded power inductor) has no exact match in KiCad's default
  `Inductor_SMD.pretty` library under that part number -- verify/source at BOM
  time, same spirit as this repo's other flagged footprint estimates.
- **EN (U8 pin 1) and PG (U8 pin 5) are unconnected** on this placement-only
  pass -- EN needs to be tied to `+VSYS` (always-on) in the future wiring
  pass, per the datasheet's "must be terminated and not left floating"
  requirement.
- **`+VSYS`'s exact worst-case high-side voltage** (when wall/USB power is
  present and MCP73871's power-path FETs are conducting) was not independently
  re-derived here -- it's assumed to stay within TPS62A02's 6.5V absolute-max
  VIN based on `power_bms_notes.md`'s existing "~5V-class input" assumption
  and MCP73871's own 7.0V IN absolute-max, but this chain of assumptions is
  worth double-checking against real measured `+VSYS` behavior once
  `power_bms.kicad_sch` is actually wired and prototyped.
- **GPIO3's pull direction** (chosen pull-down here) is not functionally
  forced by the datasheet's default eFuse JTAG-source configuration (which
  ignores GPIO3) -- it's a conservative "don't leave it floating" choice, not
  a datasheet-mandated direction; revisit if a future revision intentionally
  changes the JTAG-source eFuse configuration.
