# Regulation / Antenna / Programming-Debug -- design notes

This covers the three new **placement-only** hierarchical sheets added in this
pass -- `regulation.kicad_sch`, `antenna.kicad_sch`, `programming_debug.kicad_sch`
-- plus the two GPIO strapping resistors (`R7`, `R8`) added directly onto the
already-existing `radio_mcu.kicad_sch`. As with `radio_mcu.kicad_sch` and
`mechanical.kicad_sch` before them, **no wires or global labels are drawn on
any of these sheets** -- components are instantiated and laid out only.
`kicad-cli sch erc` therefore reports the expected pile of
`pin_not_connected` / `pin_not_driven` / `power_pin_not_driven` items on these
sheets, same convention already established by `radio_mcu.kicad_sch` and
`mechanical.kicad_sch` (see `README.md`'s Status section and
`power_bms_notes.md`).

## Why this pass exists: the hardware gap

Confirmed against real datasheets before touching any files:

- **NINA-B111 absolute max VCC = 3.9V** (u-blox NINA-B1 series datasheet
  UBX-15019243-R15, Table 8 "Absolute maximum ratings").
- **DWM3000 absolute max VDD3V3/VDD1 = 4.0V** (Qorvo DWM3000 Data Sheet Rev B,
  Table 9 "DWM3000 Absolute Maximum Ratings").
- A single-cell LiPo sits at **4.20V fully charged** (matches this board's
  MCP73831-**2** charger regulation voltage, already placed on
  `power_bms.kicad_sch`).

Both parts are currently planned to connect straight to the protected `VBAT`
global label on `power_bms.kicad_sch` with **no regulator** -- at full charge
this exceeds both parts' absolute maximum ratings. Per the task decision:
**the wristband gets a simple LDO** (not a switching buck -- that's the bay
station's job, out of scope here) between `VBAT` and a new regulated rail.
Two further real gaps were also confirmed and fixed in this pass: NINA-B111
needs a real external antenna from u-blox's own approved list (it's the
external-antenna-pin variant, unlike B112 which has an integrated antenna),
and DWM3000's own power-up timing diagram requires defined GPIO5/GPIO6 levels
to select SPI mode at boot, and NINA-B111 needs an SWD header to be
programmable at all.

---

## 1. LDO: Microchip MCP1700T-3302E/TT

**Chosen part**: `MCP1700T-3302E/TT`, SOT-23-3, fixed 3.3V output, 250mA max,
1.6uA typical quiescent current. Datasheet: Microchip DS20001826E/F "MCP1700
Low Quiescent Current LDO".

### Why 3.3V output (not 3.0V)

| Rail comparison | NINA-B111 | DWM3000 |
|---|---|---|
| Absolute max | 3.9V (Table 8) | 4.0V (Table 9) |
| Operating max | 3.6V (Table 11, "Supply/Power pins") | 3.6V (Table 4, "Nominal Operating Conditions") |
| Chosen +3V3 rail | **3.3V** | **3.3V** |
| Margin under operating max | 0.3V | 0.3V |
| Margin under absolute max | 0.6V | 0.7V |

3.3V sits comfortably inside **both** parts' own operating-condition maximums
(not just under the absolute-max ratings, which would be the bare minimum
bar) -- real margin on both counts, using a single standard LDO output option
that both parts commonly run at in existing reference designs.

### Current budget (why 250mA-class, not a smaller/simpler part)

Real per-IC current draw pulled from each part's own datasheet, not guessed:

- **NINA-B111**: Table 12 "Module VCC current consumption" (software-agnostic)
  gives Radio TX-only +0dBm typical **5.3mA**, Radio RX-only **5.4mA**. But
  Table 13 "Current consumption during typical use cases" (real
  u-connectXpress software, +4dBm output -- this module's actual max rated
  output power per Table 14) gives the realistic worst case: **peak 12mA**
  @3.3V VCC, either "Active, advertising" or "Connected as peripheral,
  connection events" scenarios. **12mA** is the number used for budgeting.
- **DWM3000**: Table 5 "DWM3000 DC Characteristics" -- total current drawn
  from all supplies (VDD1+VDD3V3 combined): CH5 TX 40mA typ, CH9 TX 45mA typ,
  CH5 RX 50mA typ, **CH9 RX 55mA typ** (worst case of the four rows). **55mA**
  is the number used for budgeting (Channel 9/7987.2MHz, receiver active).

**Combined peak draw: 12mA + 55mA = 67mA.** Against the MCP1700's 250mA max
output rating, that's **~3.7x headroom** -- comfortable margin for two ICs
that will rarely peak simultaneously in practice (BLE advertising and UWB
ranging are not typically driven at the exact same instant in a duty-cycled
tag), without over-provisioning into a needlessly large/expensive part.

### Why this part over MCP1802 or a bigger buck/LDO

- **Low Iq matters here**: this is a battery-powered wristband where the
  radios themselves duty-cycle down to low-power sleep between
  advertising/ranging events (see NINA-B1's own Sleep-mode current: 300nA-620nA,
  Table 12). An LDO burning meaningful quiescent current between those events
  would dominate the sleep-mode battery budget. MCP1700's **1.6uA typical /
  4uA max Iq** (DC Characteristics table) is negligible next to that --
  MCP1802 is a reasonable alternative (adds power-good output, SOT-23-5,
  ~contact-Iq in a similar low range) but adds a 5-pin package and a feature
  (power-good) this design doesn't use; MCP1700's simpler 3-pin SOT-23 with
  no unused pins is the better fit.
- **Dropout**: DC Characteristics table, "Dropout Voltage, VR>2.5V": typical
  178mV / max 350mV **at IL=250mA** -- our actual worst-case load (~67mA) is
  well under that test current, so real dropout at our load is lower still.
  Even at the datasheet's own worst-case 350mV number, VBAT only needs to
  stay above ~3.65V for full-accuracy regulation; below that the output
  droops gracefully (this LDO's output floor is governed by
  VIN - dropout, not a hard cutoff) rather than failing outright, which is
  an acceptable, expected behavior near end-of-discharge for a battery
  product (see "Open concerns" below).
- **VIN range**: 2.3V-6.0V operating (6.5V absolute max) comfortably spans
  the whole VBAT range (~3.0-4.2V, per `power_bms.kicad_sch`'s DW01A
  overdischarge/MCP73831 charge-voltage limits).

### Capacitors: C11 (Cin), C12 (Cout)

Both **1uF X7R ceramic, 0603** -- taken directly from the datasheet's own
"Typical Application Circuit" (page 2: `C_IN` 1uF ceramic, `C_OUT` 1uF
ceramic) and DC Characteristics table conditions (`C_OUT = 1uF (X7R)`,
`C_IN = 1uF (X7R)`), not a generic guess. The datasheet states the LDO "is
stable with only 1uF output capacitance" using ceramic, tantalum, or
aluminum electrolytic -- 1uF X7R ceramic 0603 was chosen to match every
other passive already on this board (see `components.csv`).

### Pin mapping (verified against the real datasheet's own package diagram)

3-Pin SOT-23: **pin 1 = GND, pin 2 = VOUT, pin 3 = VIN** (datasheet page 1,
"3-Pin SOT-23" package diagram). Matches this project's placed symbol exactly.

### A note on the embedded symbol (same documented pattern as AO3401A)

KiCad's own real `Regulator_Linear.kicad_sym` defines `MCP1700x-330xxTT` via
`(extends "MCP1700x-300xxTT")`. Exactly as already documented in
`power_bms_notes.md` (item 5, AO3401A/`Transistor_FET`), `kicad-cli` only
resolves `extends` through the project's own `sym-lib-table`, which
intentionally does not register a `Regulator_Linear` nickname (out of scope
per this task's constraints). So `regulation.kicad_sch`'s cached copy of
`Regulator_Linear:MCP1700x-330xxTT` is embedded fully self-contained --
graphics + all 3 pins inlined directly from the real `MCP1700x-300xxTT` base
symbol (pin-for-pin identical), with only the 330-variant's own
Value/Footprint/Description/Datasheet properties applied. This is the same
legitimate, zero-electrical-impact deviation already established in this
repo, not a new pattern -- it shows up in ERC as one more
`lib_symbol_mismatch` warning (see Validation below), same category as the
existing AO3401A/Battery_Cell/USB_C_Receptacle_PowerOnly_6P/MountingHole
warnings.

### Intended (not yet wired) net names

- LDO input (pin 3, VI): intended to pick up the existing `VBAT` global
  label already used on `power_bms.kicad_sch` (protected battery rail).
- LDO output (pin 2, VO): intended new rail, **`+3V3`** -- not yet placed as
  a label anywhere (per this task's placement-only rule). This is the rail
  `radio_mcu.kicad_sch`'s NINA-B111 `VCC`/`VCC_IO` pins and DWM3000's
  `VDD1`/`VDD3V3`/`VDD3V3` pins should pick up when wiring is added, and the
  rail `programming_debug.kicad_sch`'s `VTref` pin should also reference.

---

## 2. Antenna: ProAnt InSide-2400 + U.FL feed + L/C match placeholder

### Real part, from the real approved list

Fetched and read u-blox's own NINA-B1 series datasheet
(UBX-15019243-R15, 5-Aug-2021), **Section 7 "Antennas" / 7.2 "Approved
antennas"** directly (not guessed, not taken from a secondary summary).
That section lists, for the NINA-B1 series' external-antenna-pin variant:

| Antenna | Type | Size | Connector | Comment |
|---|---|---|---|---|
| NINA-B112 (u-blox LILY) | PIFA, SMD | 3.0x3.8x9.9mm | (on-module) | **Not applicable** -- this is B112's own integrated antenna, not usable with B111. |
| GW.26.0111 (Taoglas) | Monopole | O7.9x30.0mm | SMA(M) | Rigid external "stick" antenna. |
| Ex-It 2400 28 RP-SMA (ProAnt) | Monopole | O12x28mm | RP-SMA | Needs a metal ground plane; rigid. |
| **Ex-It 2400 28 U.FL-100 (ProAnt)** | Monopole | O12x28mm | U.FL, 100mm cable | Needs a metal ground plane; rigid. |
| Ex-It 2400 Foldable RP-SMA (ProAnt) | Monopole | O10x83mm | RP-SMA | Rigid, largest of the set. |
| **InSide-2400 (ProAnt)** | Patch | 27x12mm (triangular) | U.FL, 100mm cable | *"Part of this antenna should be attached to a plastic enclosure for best performance."* |
| FlatWhip-2400 RP-SMA (ProAnt) | Monopole | O50x30mm | RP-SMA | EOL, not for new products. |

**Chosen: InSide-2400 (ProAnt).** It's the only entry in the real approved
list whose own datasheet comment explicitly calls out mounting inside a
**plastic enclosure** -- a direct match for a wearable wristband's case,
versus every other option in the list being a rigid external monopole
"stick" (7.9-50mm diameter, several explicitly requiring a metal ground
plane) sized for boxier/metal-enclosure products. It's flexible (100mm U.FL
pigtail), small (27x12mm triangular patch), +3.0dBi gain, 50 ohm, and
approved across FCC/IC/RED/MIC/NCC/KCC/ANATEL/ACMA/ICASA -- global-ish
regulatory coverage out of the box.

### How it's represented on the schematic

The real antenna body mounts **off-board**, connected via its own 100mm U.FL
pigtail cable -- there's no PCB footprint for the antenna element itself.
So `antenna.kicad_sch` places:

- **AE1**: KiCad's own generic `Device:Antenna` symbol (confirmed present in
  the default `Device.kicad_sym` before assuming a hand-authored part was
  needed) as a schematic placeholder for the real InSide-2400, with its
  Value/Description citing the real chosen part.
- **J2**: `Connector:Conn_Coaxial` symbol with footprint
  `Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical` -- both confirmed
  present in KiCad's own default libraries (the `Conn_Coaxial` symbol's own
  `ki_fp_filters` property literally includes `*U.FL*`, confirming this is
  the intended standard pairing). This is the real PCB-side U.FL receptacle
  the InSide-2400's pigtail plugs into -- added because a real design needs
  a real attachment point, not just a floating antenna placeholder.
- **L1 / C13**: generic 0603 `Device:L` / `Device:C`, **Value set to "DNP --
  match network placeholder"**, matching what `components.csv` already
  documented ("Inductors (if needed for antenna matching) ... Exact
  matching-network values depend on the chosen antennas/layout, set at
  schematic time") -- a classic single-L/single-C L-match topology (series L
  from NINA-B111's `ANT` pin, shunt C to `GND`) between the module and the
  U.FL connector. Real values need on-board network-analyzer tuning once a
  prototype exists (antenna matching is layout- and stack-up-dependent, not
  something to guess numerically here), hence DNP (do-not-populate) rather
  than an invented value.

Intended (not yet wired) signal flow: NINA-B111 `ANT` pin (U3, already
placed on `radio_mcu.kicad_sch`) -> L1 (series) -> C13 (shunt to GND) -> J2
(U.FL) -> off-board InSide-2400 antenna cable assembly (AE1).

---

## 3. Programming/Debug: ARM Cortex Debug (SWD) connector, J3

**Chosen part**: KiCad's own default `Connector:Conn_ARM_JTAG_SWD_10` --
confirmed present in the default `Connector.kicad_sym` before assuming a
custom part was needed. This is the real, industry-standard 10-pin, 2x5
1.27mm-pitch "ARM Cortex Debug" connector (the same connector standard used
by Segger J-Link, ST-Link, Black Magic Probe, and most other Cortex-M debug
probes) -- exactly the kind of "2x5 1.27mm header" this task suggested,
found as a real default part rather than hand-authored. Footprint:
`Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical` (also a real
KiCad default, registered under the global `Connector_PinHeader_1.27mm`
footprint library nickname).

### NINA-B111 pin mapping (U3, already placed on `radio_mcu.kicad_sch` --
### not re-placed here, per this task's constraints)

Verified against the same u-blox NINA-B1 datasheet Table 6 pinout already
cited for U3:

| J3 (Conn_ARM_JTAG_SWD_10) pin | Signal | Intended NINA-B111 (U3) connection |
|---|---|---|
| 1 | VTref | Intended: `+3V3` regulated rail (see `regulation.kicad_sch`) -- lets a debug probe's level-shifters reference the correct I/O voltage. |
| 2 | SWDIO/TMS | U3 pin 15, `SWDIO` |
| 3, 5, 9 | GND / GNDDetect | U3 GND pins (6, 12, 14, 26, or 30) |
| 4 | SWCLK/TCK | U3 pin 11, `SWDCLK` |
| 6 | SWO/TDO | U3 pin 8, `SWO/GPIO_8` (optional -- trace output) |
| 7 | KEY (no_connect) | n/a -- mechanical keying pin only |
| 8 | NC/TDI | n/a -- NINA-B111's nRF52-series MCU is SWD-only for debug (no JTAG), matches this connector's standard "SWD-only subset" usage pattern |
| 10 | ~RESET | U3 pin 19, `RESET_N` |

None of this is wired yet (placement-only, per this task's constraints) --
documented here so the intended hookup is clear when wiring is added later.

---

## 4. DWM3000 GPIO5/GPIO6 SPI-mode strapping: R7, R8

### The real requirement (from Qorvo's own datasheet, not inferred)

Fetched and read the real Qorvo DWM3000 Data Sheet (Rev B, May 2021)
directly. **Figure 1 "Timing diagram for cold start POR"** and **Figure 2
"Timing diagram for warm start"** both explicitly label a step during the
`WAKEUP` phase, before the digital core reaches `INIT_RC`: **"Sample GPIOs
5&6 to set SPI mode"**. Per Table 2 ("DWM3000 Pin Functions"):

- **Pin 9 = GPIO6 / EXTRXE / SPIPHA** -- "On power-up it acts as the SPIPHA
  (SPI phase selection) pin for configuring the SPI mode of operation. After
  power-up, the pin will default to a General Purpose I/O pin."
- **Pin 10 = GPIO5 / EXTTXE / SPIPOL** -- same wording, for SPIPOL (SPI
  polarity).

If these float at the exact instant the DW3110 IC samples them during
power-up, the resulting SPI mode (CPOL/CPHA) the chip locks into for its
whole active session is undefined/non-deterministic -- exactly the kind of
floating-critical-strap-pin problem this task flagged.

### Why external resistors, given DWM3000 already has internal pulls

Section 6.3 ("GPIO and SPI I/O Internal Pull Up / Down") of the same
datasheet states all GPIO pins have a **software-controllable** internal
pull up/down resistor (10-30kOhm range, scales with VDD1), defaulting to
**enabled and pull-down** (except SPICSn, which defaults pull-up). In
principle this alone would already bias GPIO5/GPIO6 low at cold boot.
However, relying solely on an internal pull that the datasheet itself
describes as *software controllable* for a strap sampled by hardware **before**
any firmware has run is exactly the fragile assumption Qorvo's own related
DW1000 application guidance warns against for these shared
GPIO-pin/RF-switch-control lines (recommending external pull resistors in
the 1-10kOhm range when these pins do double duty). Adding deterministic
external pull-downs removes any dependency on internal pull-config state
(which could plausibly be left in some other configuration by prior
firmware/OTP content, or during any brief window where the internal pull
isn't yet active) for a pin sampled at the earliest, most safety-critical
moment of the chip's boot sequence.

### Values chosen

**R7 = 10k&Omega;, 0603, DWM3000 GPIO5/SPIPOL pull-down to GND.**
**R8 = 10k&Omega;, 0603, DWM3000 GPIO6/SPIPHA pull-down to GND.**

Both pull to `GND` (not VDD) so that, sampled at power-up, **SPIPOL=0 /
SPIPHA=0 -> SPI Mode 0 (CPOL=0, CPHA=0)** -- the conventional default SPI
mode used by essentially all SPI host MCUs (including the nRF52-series core
inside NINA-B111), and the same mode implied by DW3000's own SPI transfer
protocol diagrams (Figure 5, "DW3000 SPIPHA=0 Transfer Protocol"). 10k&Omega;
was chosen as a standard, low-power value sitting at the **low end** of the
same 10-30kOhm range the datasheet itself uses for its own internal pulls
(Section 6.3) -- strong enough to dominate any leakage/floating condition,
without wasting meaningful current (10k&Omega; at 3.3V is only ~0.33mA, and
that only flows if the pin is ever actively driven high against the
pull-down, which it isn't during the sampling window).

Placed on `radio_mcu.kicad_sch` (not a new sheet, per this task's
instructions) -- an *addition* to that existing file, not a change to
anything already there. Not yet wired to U4's actual GPIO5/GPIO6 pins
(pins 10 and 9) or to `GND`, per this task's placement-only constraint;
documented here so the intended connection is unambiguous.

---

## Reference designator bookkeeping

Used in this pass (continuing from the task's given "next available"
starting points, since multiple parts of the same class were needed):

| Ref | Part | Sheet |
|---|---|---|
| U5 | MCP1700T-3302E/TT | `regulation.kicad_sch` |
| C11 | 1uF (LDO Cin) | `regulation.kicad_sch` |
| C12 | 1uF (LDO Cout) | `regulation.kicad_sch` |
| L1 | DNP match-network inductor | `antenna.kicad_sch` |
| C13 | DNP match-network capacitor | `antenna.kicad_sch` |
| J2 | U.FL connector (Conn_Coaxial) | `antenna.kicad_sch` |
| AE1 | InSide-2400 antenna placeholder | `antenna.kicad_sch` |
| J3 | Conn_ARM_JTAG_SWD_10 | `programming_debug.kicad_sch` |
| R7 | 10k GPIO5/SPIPOL pull-down | `radio_mcu.kicad_sch` (addition) |
| R8 | 10k GPIO6/SPIPHA pull-down | `radio_mcu.kicad_sch` (addition) |

`Q3`, `D2`, `H5`, `BT2`, `TH1` (also given as "next available" in the task)
were **not** needed for this pass and remain available for future work. Next
available going forward: `U6`, `C14`, `R9`, `AE2`, `L2`, `J4` (plus the
still-unused `Q3`/`D2`/`H5`/`BT2`/`TH1`).

## Validation

`kicad-cli sch erc wristband/wristband.kicad_sch` (run from a scratch cwd,
per this environment's convention): **128 violations, all in the same
categories already established by the existing placement-only sheets** --
`pin_not_connected` (91), `power_pin_not_driven` (20), `lib_symbol_mismatch`
(11 -- the 7 pre-existing ones from `power_bms.kicad_sch`/`mechanical.kicad_sch`
plus 4 new ones: `MCP1700x-330xxTT`, `Conn_ARM_JTAG_SWD_10`, `Conn_Coaxial`,
and `Antenna` -- all from the same deliberate embedded-symbol-with-
customized-properties pattern already documented for AO3401A, not a new kind
of issue), `pin_not_driven` (6). No errors from malformed files, no
duplicate references (checked directly against the ERC report and a
`kicad-cli sch export bom` run, which lists all 10 new parts correctly with
no duplicates), no library-lookup failures. `power_bms.kicad_sch`'s own
ERC-clean result (0 errors, 1 warning) is unchanged, since that file was not
touched.

**One real bug caught and fixed during this pass, worth flagging:** the
first draft of `antenna.kicad_sch` accidentally named its embedded
`Device:Antenna` symbol's two unit sub-symbols `Device:Antenna_0_1` /
`Device:Antenna_1_1` (wrongly including the library prefix, inconsistent
with every other embedded symbol in this repo, e.g. `NINA-B111_0_1` not
`wristband:NINA-B111_0_1`). This didn't throw a parse error -- instead,
exactly as already documented in `power_bms_notes.md` item 5 for a different
failure mode, `kicad-cli` silently treated the entire `antenna.kicad_sch`
sheet as **empty** (0 components in BOM/ERC output for that sheet, no
error), even though the parent hierarchy and sheet name still resolved
correctly. Caught by cross-checking `kicad-cli sch export bom` output against
the expected 10 new reference designators -- 4 were silently missing. Fixed
by renaming the sub-symbols to the correct bare `Antenna_0_1` / `Antenna_1_1`
form; re-running both ERC and BOM export confirmed all 4 parts (`AE1`, `L1`,
`C13`, `J2`) now appear correctly. Worth remembering: a hierarchical sheet
that silently fails to load reports **zero** violations for itself, which
can look deceptively like a clean result if you don't cross-check the BOM
too.

## Open concerns

1. **LDO end-of-discharge behavior**: as VBAT sags toward end-of-discharge
   (DW01A's own overdischarge cutoff on `power_bms.kicad_sch` is 2.4V, release
   3.0V), the LDO will fall out of full-accuracy regulation once VBAT drops
   below roughly 3.3V + dropout (~3.5-3.65V worst case) before the BMS itself
   cuts off around 2.4V -- output droops gracefully rather than failing
   outright, which is normal/expected for a battery product, but worth
   knowing when characterizing real low-battery behavior on a prototype.
2. **Antenna matching network values are DNP placeholders.** Real L/C values
   depend on final board stack-up, ground-plane geometry near the U.FL
   connector, and the specific InSide-2400 unit's own impedance at the
   chosen mounting location -- these need real network-analyzer tuning on a
   built prototype, not a datasheet lookup, hence left unpopulated by design
   (matches the "if needed" framing already in `components.csv`).
3. **VTref wiring choice**: per the ARM Cortex Debug connector's own
   convention, `VTref` (pin 1) should pick up the regulated `+3V3` rail (not
   raw `VBAT`) once wiring is added, so an external debug probe references
   the same voltage domain NINA-B111 actually runs its I/O at.
4. **J2 (U.FL) mechanical placement** will need to respect antenna
   keep-out-area guidance during PCB layout (a concern for the *DWM3000's*
   on-module ceramic antenna specifically, per that datasheet's Figure 10 --
   not NINA-B111's antenna directly, but the same general principle -- no
   metal/ground copper directly under either RF antenna's near-field --
   applies and is worth carrying into the eventual PCB layout pass for
   *this* antenna too).
