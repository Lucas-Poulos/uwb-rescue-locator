# power_bms.kicad_sch -- design notes

Hierarchical sub-sheet covering the bay station's external power input,
reverse-battery protection, MCP73871 charge/power-path circuit, and MAX17048
fuel gauge. Wired into `bay-station.kicad_sch` as sheet "Power BMS"
(sheet-symbol uuid `b2362bec-be69-491d-a07e-a9d16de4ad17`) and registered in
`bay-station.kicad_pro`'s `sheets` list. Schematic-capture only: no
footprints placed on the PCB, no wires drawn -- every net is carried by
`global_label`s, matching the convention in the sibling wristband project.

## Scope decisions

- **No ESP32-S3-WROOM-1 or DWM3000 instances on this sheet.** This sheet's
  job is the input protection / charge / fuel-gauge circuitry; the MCU and
  UWB anchor modules belong on their own future `connectivity` /
  `uwb_anchors` sheets where their own datasheet-specific decoupling will be
  added (per each part's own supply-pin requirements -- ESP32-S3-WROOM-1
  needs several caps across multiple 3V3 pins per Espressif's hardware
  design guidelines; DWM3000 needs its own decoupling per the Qorvo
  datasheet). This sheet only decouples the rails it directly produces
  (`+VSYS`, `VBATT_PROT`) at the point they leave the IC, for whatever loads
  attach downstream.
- **No dedicated 3.3V buck/LDO regulator on this sheet.** MCP73871's `OUT`
  power-path pin is *not* a regulated 3.3V rail -- it tracks close to
  whichever of (current-limited `IN`, `VBAT`) has priority, i.e. roughly
  system-input-minus-ideal-diode-drop when external power is present, or the
  raw single-cell Li-Ion range (~3.0-4.4V) when running from battery alone.
  Naming this net `+3V3` (as the task brief's example suggested) would assert
  a regulation guarantee that doesn't exist yet. It's named **`+VSYS`**
  instead, and a separate buck/LDO stage (sized once the ESP32-S3 +
  4x-DWM3000 load budget is known) is left as an explicit open item for a
  future sheet -- selecting/verifying that regulator IC against a real
  datasheet was out of this task's enumerated circuit list (items 1-7).
- **Status LEDs (PG/STAT1/STAT2) omitted.** Microchip's typical application
  circuit (DS20002090E, page 2) also shows 3 LEDs + 470Ω resistors on these
  open-drain status outputs. Not one of the 7 enumerated circuit items for
  this task, and adding them meaningfully increases part count/coordinate
  surface for no functional benefit at this stage. The three pins are still
  brought out via global labels (`nPG`, `nSTAT2`, `nSTAT1_LBO`) so a future
  sheet can add LEDs or read them into a host MCU without any rework here.
- **MAX17048 ALRT/SCL/SDA have no pull-ups on this sheet.** ALRT is
  open-drain and SCL/SDA need I2C pull-ups per the datasheet, but the
  correct pull-up rail is whatever logic-level supply the future I2C host
  (ESP32-S3, on the not-yet-built connectivity sheet) actually uses -- not
  necessarily the raw ~3.0-4.4V `VBATT_PROT` rail present on this sheet
  (MAX17048's own VDD). Pulling SCL/SDA/ALRT up to `VBATT_PROT` now would be
  a guess that could exceed a 3.3V-only MCU GPIO's absolute max rating at
  high state-of-charge. All three are brought out as bare global labels
  (`FG_ALRT`, `FG_SCL`, `FG_SDA`) for the connectivity sheet to terminate
  correctly once the host's supply rail is defined. See "Known ERC finding"
  below for the one ERC error this produces.
- **Barrel jack and USB-C share one `+5V_IN` net.** Per
  `libs/components.csv`, the USB-C receptacle is documented as an
  *alternate* continuous-power input to the barrel jack, not a simultaneous
  second source, so both are simply tied to the same post-protection node
  feeding MCP73871's `IN` pins. One shared TVS (`D2`) protects both physical
  connectors; the barrel jack additionally gets its own series Schottky
  (`D1`) for reverse-polarity protection (a barrel jack has no polarity
  keying; USB-C does, so it doesn't need one).
- **MCP73871 SEL is hard-wired high (AC-DC adapter mode, 1.8A input limit)**,
  not USB current-limited mode -- appropriate for a wall/USB-brick-powered,
  continuously-running base station rather than a laptop-USB-port-powered
  device. See MCP73871 section below.

## Components placed

| Ref | Part | lib_id | Datasheet | Notes |
|---|---|---|---|---|
| J1 | Barrel jack (e.g. CUI PJ-063AH) | `Connector:Barrel_Jack` | n/a (generic) | Continuous wall power input. Pin 1 = tip/+, pin 2 = sleeve/GND, per KiCad default symbol. |
| D1 | Schottky, MBRA140T3G | `Device:D_Schottky` | https://www.onsemi.com/pdf/datasheet/mbra140t3-d.pdf | 1A/40V SMA Schottky in series with J1's + pin only (barrel jacks have no polarity keying). 40V/1A rating gives huge margin over the ~6V/≤1.8A input budget; low Vf minimizes the drop ahead of MCP73871's `VREG+0.3V` minimum `IN` requirement. |
| J2 | USB-C power-only receptacle (e.g. GCT USB4125) | `Connector:USB_C_Receptacle_PowerOnly_6P` | https://www.usb.org/document-library/usb-type-cr-cable-and-connector-specification | Alternate continuous power input, shares `+5V_IN` with J1 (see scope decisions). CC1/CC2 each get a 5.1k pulldown (R6, R7) to GND -- the standard minimum so any USB-C source (host or PD adapter in default 5V mode) will enable VBUS; no PD negotiation IC is present, so only default-current (5V) operation is assumed. |
| R6, R7 | 5.1k 0603 | `Device:R` | -- | CC1/CC2 pulldowns, matches USB-C spec + sibling wristband project convention. |
| D2 | TVS, ESD5B5.0ST1G | `Device:D_TVS` | https://www.onsemi.com/pdf/datasheet/esd5b5.0st1-d.pdf | 5V standoff (min breakdown 5.8V, clamp 5.8V typ, 50W peak pulse), SOD-523. Shared across the barrel-jack/USB-C `+5V_IN` node. Clamp voltage (5.8V) stays comfortably under MCP73871's 7.0V absolute-max `IN` rating. Already the part suggested in `libs/components.csv` for USB VBUS; reused here rather than sourcing a second part. |
| D3 | TVS, ESD5B5.0ST1G (same part as D2) | `Device:D_TVS` | (same as D2) | Battery-line protection. 5V standoff comfortably exceeds the single-cell Li-Ion's 3.0-4.4V normal range (~14%+ margin at 4.4V) while still clamping well below MCP73871's abs-max `VDD` rating. Reusing the identical part as D2 for BOM commonality rather than sourcing a battery-specific TVS. |
| Q1 | P-MOSFET, AO3401A | `Transistor_FET:AO3401A` | http://www.aosmd.com/pdfs/datasheet/AO3401A.pdf | Reverse-battery-polarity "ideal diode": source = BT1 `+` (`BATT_RAW`), gate pulled to GND through R1 (100k), drain feeds `VBATT_PROT`. -4.0A / -30V SOT-23 (AOS datasheet, already the exact part in KiCad's own `Transistor_FET.kicad_sym`, verified pinout 1=G/2=S/3=D against the datasheet's own SOT-23 pin diagram). -4A rating gives ~3-4x headroom over the expected combined charge (500 mA) + system-load (~1A peak, ESP32-S3 Wi-Fi TX bursts + 4x DWM3000) current, without stepping up to a larger SO-8 part -- SOT-23 was judged sufficient rather than "size for size's sake." **Cache note:** this symbol's embedded `lib_symbols` copy is a flattened, self-contained duplicate of KiCad's real `Transistor_FET:AO3401A` (which normally uses `(extends "TP0610T")`), not the extends-based original -- see "AO3401A extends-symbol issue" below. |
| R1 | 100k 0603 | `Device:R` | -- | Q1 gate-to-GND bias resistor. Gate leakage is negligible, so any value in the 100k-1M range works; 100k chosen as a common, unremarkable value. |
| BT1 | 3.7V Li-Ion cell, JST-PH pigtail | `Device:Battery_Cell` | n/a (generic) | Backup/topped-off single-cell Li-Ion. JST-PH chosen over the 18650-holder alternative noted in `libs/components.csv` for consistency with the wristband project's existing convention; either is compatible with MCP73871/MAX17048's single-cell (3.0-4.4V) assumptions. |
| U1 | MCP73871 | `Battery_Management:MCP73871` | https://ww1.microchip.com/downloads/en/DeviceDoc/MCP73871-Data-Sheet-20002090E.pdf | Charge management + power-path IC. See dedicated section below. |
| R2 | 2.00k 0603 (PROG1) | `Device:R` | -- | Sets fast-charge current. See math below. |
| R3 | 20.0k 0603 (PROG3) | `Device:R` | -- | Sets termination current. See math below. |
| R4 | 330k 0603 (VPCC divider, top) | `Device:R` | -- | VPCC power-path-priority divider, values taken directly from the datasheet's own Section 3.3 worked example (assumes ~5V nominal input, which matches this design's `+5V_IN`). |
| R5 | 110k 0603 (VPCC divider, bottom) | `Device:R` | -- | See R4. |
| TH1 | 10k NTC | `Device:Thermistor_NTC` | n/a (generic, pick exact curve at BOM time) | MCP73871 THERM battery-temperature bias, 10k per the datasheet's typical application circuit. |
| C1 | 10uF 0603 | `Device:C` | -- | MCP73871 `IN` decoupling, value from the datasheet's typical application circuit (page 2 diagram) -- note Section 3.1's *minimum* is 4.7uF; 10uF is the diagram's actual shown value. See "open concerns" re: 10uF in a 0603 case. |
| C2 | 4.7uF 0603 | `Device:C` | -- | MCP73871 `OUT` decoupling / `+VSYS` rail bulk cap, per datasheet typical application circuit. |
| C3 | 4.7uF 0603 | `Device:C` | -- | MCP73871 `VBAT`/`VBATT_PROT` decoupling, per datasheet typical application circuit. |
| U2 | MAX17048G+T10 | `bay_station:MAX17048G+T10` | https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf | Fuel gauge, hand-authored symbol already in `libs/bay_station.kicad_sym` (not modified by this task). |
| C4 | 0.1uF 0603 | `Device:C` | -- | MAX17048 VDD decoupling, the standard value from Maxim/ADI's typical operating circuit for this part. |
| #FLG01, #FLG02 | `power:PWR_FLAG` | n/a | -- | Not physical parts (`in_bom no`, `on_board no`). Asserts to ERC that `GND` and `+5V_IN` are legitimately externally-sourced nets (from the connectors/battery) even though no placed symbol has a `power_out`-type pin on those specific nets -- the standard KiCad mechanism for exactly this situation. `VBATT_PROT` and `+VSYS` don't need one: MCP73871's `VBAT` (pins 14/15) and `OUT` (pins 1/20) pins are themselves `power_out` type and already satisfy ERC for those two nets. |

## MCP73871 charge + power-path circuit

Built from Microchip's real typical application circuit (DS20002090E,
page 2 diagram) and Sections 3-5 (pin descriptions / functional
description), fetched and read directly from
`https://ww1.microchip.com/downloads/en/DeviceDoc/MCP73871-Data-Sheet-20002090E.pdf`
-- not guessed.

**Strap pins** (tied per Section 5.2.2, "AC-DC Adapter and USB Port Power
Source Regulation Select"):
- `SEL` (pin 3) -> `+5V_IN` (logic high): selects **AC-DC adapter mode**
  (1.8A total input current limit, charge current set solely by PROG1)
  rather than USB current-limited mode. Chosen because this is a
  continuously-running, wall/USB-brick-powered base station, not a
  laptop-USB-port-powered device -- USB's 100/500mA presets would needlessly
  cap the whole system+charge budget.
- `PROG2` (pin 4) -> `GND` (logic low): unused in SEL=high mode (its
  function is "USB port input current limit selection when SEL=Low" per the
  pin table), but the datasheet explicitly warns input pins "must not allow
  floating," so it's tied low as a defined default.
- `TE` (pin 9) -> `+5V_IN` (logic high): **disables the internal safety
  timer**. Section 5.2.5 explicitly recommends this for exactly this
  design's use case: "The TE input can be used to disable the timer when
  the charger is supplying current to charge the battery and power the
  system load" -- i.e. power-path/system-load-sharing operation, where a
  fluctuating system load can slow the apparent charge-voltage rise enough
  to false-trigger a fixed safety timeout even though charging is still
  legitimately progressing.
- `CE` (pin 17) -> `+5V_IN` (logic high): always-enabled charging.

**Charge current (PROG1, pin 13, R2 = 2.00k):** per Equation 4-1,
`IREG[mA] = 1000 / RPROG1[kΩ]`. Chose IREG = 500 mA (top of the task's
suggested 300-500mA "longevity-focused" range, and it lands on a clean
standard resistor value): `RPROG1 = 1000 / 500 = 2.00 kΩ`, within the
datasheet's recommended 1-20kΩ PROG1 range.

**Termination current (PROG3, pin 12, R3 = 20.0k):** per Equation 4-2,
`ITERMINATION[mA] = 1000 / RPROG3[kΩ]`. Chose 10% of the 500 mA fast-charge
current (50 mA), matching the ratio implicit in the datasheet's own DC
electrical-characteristics example (PROG3=10k -> 100mA termination at an
assumed 1A/PROG1=1k fast-charge, i.e. also a 10:1 ratio):
`RPROG3 = 1000 / 50 = 20.0 kΩ`, within the recommended 5-100kΩ PROG3 range.

**Power-path priority (VPCC, pin 2, R4/R5 = 330k/110k divider from
`+5V_IN`):** Section 3.3 "Voltage Proportional Charge Control" is the
datasheet's specific power-path-priority mechanism (reduces battery charge
current, giving the system load priority, if the input sags under load).
Reused the datasheet's own worked numeric example verbatim (assumes a
~5V-class nominal input, matching this design's `+5V_IN`): R1(=R4 here,
330k) from input to VPCC, R2(=R5 here, 110k) from VPCC to GND, giving
VPCC = 5V x 110k/(330k+110k) = 1.23V, the datasheet's stated threshold.

**VBAT/VBAT_SENSE (pins 14/15/16):** grouped onto one node (`VBATT_PROT`,
downstream of the reverse-protection FET) with a single 4.7uF cap, matching
the datasheet's own typical-circuit simplification (no separate Kelvin-sense
resistor).

**Decoupling:** IN = 10uF (C1), OUT = 4.7uF (C2), VBAT = 4.7uF (C3) --
exact values shown in the datasheet's typical application circuit diagram.

## MAX17048 fuel gauge

Per the datasheet already cited/verified in `libs/README.md` and
`libs/components.csv` (pin functions already fully verified there; not
re-verified here). CTG (pin 1) -> GND per its description ("connect to
ground"). QSTRT (pin 6) -> GND ("tie to GND if unused"). VDD (pin 3, also
the cell-voltage-sense input) -> `VBATT_PROT`, i.e. connected *downstream*
of the reverse-protection FET rather than directly to BT1+, so the fuel
gauge is covered by the same reverse-battery protection as the rest of the
circuit -- accepted trade-off: the FET's Rds(on) introduces a small IR drop
under charge/discharge current that the fuel gauge will see as a
(consistent, small) sensing offset; MAX17048 draws only micro-amps itself,
so its own contribution to that drop is negligible. C4 (0.1uF) on VDD is
the datasheet's typical operating circuit decoupling value. CELL (pin 2) is
correctly left with no connection at all (the symbol's own pin electrical
type is already `no_connect` for this single-cell part).

## Known ERC finding (not fixed, by design)

`kicad-cli sch erc` on `bay-station.kicad_sch` reports **1 error, 7
warnings**, all understood and left as-is:

- **1 error** -- `pin_not_driven` on U2 (MAX17048) pin 7, `SCL`. SCL is an
  `input`-type pin (the fuel gauge is always an I2C slave) tied to global
  label `FG_SCL`, which currently has no other member anywhere in the
  hierarchy (no host MCU sheet exists yet) -- so nothing drives it. This is
  **not** a dangling/unconnected pin (a `no_connect` marker would be wrong
  here and would actually conflict with the global label already present on
  that pin); it is a deliberately deferred connection, per the "no
  ESP32-S3/DWM3000 on this sheet" scope decision above. It will resolve
  itself once a future connectivity sheet places the I2C host and drives
  SCL. SDA doesn't trigger the equivalent check because its pin type is
  `bidirectional`, which KiCad's ERC doesn't subject to the same
  must-be-driven rule.
- **6 warnings** -- `global_label_dangling` on `FG_ALRT`, `FG_SDA`, `nPG`,
  `nSTAT2`, `nSTAT1_LBO` (and `FG_SCL`, alongside its error above): each is
  a single-member net by design (brought out for a future sheet), so KiCad
  correctly flags them as "not connected anywhere else in the schematic" --
  a soft warning, not an error, and expected until those future sheets
  exist.
- **1 warning** -- `lib_symbol_issues`, "Symbol 'AO3401A' has been modified
  in library 'Transistor_FET'". See next section.

## AO3401A extends-symbol issue (found and worked around)

KiCad's own default `Transistor_FET:AO3401A` symbol is defined as
`(extends "TP0610T")` (it inherits TP0610T's graphics/pins, overriding only
its properties). While building this sheet, `kicad-cli sch erc` /
`kicad-cli sch export bom` **failed to load the schematic at all**
("Failed to load schematic file") whenever the embedded `lib_symbols` cache
contained an `extends`-based symbol pair, even though the pair parsed as
balanced, well-formed S-expressions and even though the *real* committed
sibling-project file (`wristband-alarm/power.kicad_sch`, which also embeds
an `extends` pair, `AP2112K-3.3` extending `AP2204K-1.5`) exhibits the exact
same standalone-load failure when tested the same way. This appears to be a
real limitation of kicad-cli's headless schematic loader resolving
`extends` inheritance from a cached `lib_symbols` block outside a fully live
project/library context, not a bug specific to this file.

**Workaround:** this sheet's cached copy of `Transistor_FET:AO3401A` is
flattened -- its graphics and pins are duplicated directly from TP0610T
(same pinout: 1=G, 2=S, 3=D) with no `(extends ...)` -- rather than mirroring
KiCad's live library structure exactly. This loads and validates cleanly.
The `lib_symbol_issues` ERC warning above is the expected, benign
consequence (KiCad's live-library reconciliation sees the cache differs
from the real library's `extends`-based definition); it's cosmetic and
would clear itself the next time the schematic is saved from the KiCad GUI
with the real library available. The `lib_id` is still
`Transistor_FET:AO3401A` (KiCad's real default part is still what's
referenced/ordered), only the embedded cache representation differs.

## Open concerns / not fully confident about

- **10uF in a 0603 case (C1):** a 10uF/6.3V-or-higher X7R/X5R 0603 ceramic
  is at the edge of what's commonly available (significant DC-bias
  derating at that case size); verify a real part exists at BOM time, or
  bump C1 to 0805 if not.
- **MCP73871 ordering code / VREG option** not chosen (this sheet uses the
  generic `MCP73871` symbol matching `libs/components.csv`, not a specific
  `-#XX` suffix). The regulation-voltage option (4.10/4.20/4.35/4.40V) needs
  to be picked at BOM time; none of this sheet's math (PROG1/PROG3/VPCC)
  depends on which one is chosen.
- **Barrel jack input voltage** is assumed ~5V-class (to stay within
  MCP73871's `VIN` <= 6V recommended / 7V absolute-max rating, and to match
  the VPCC divider's 5V-nominal assumption) -- flag this explicitly on the
  BOM/silkscreen so nobody plugs in a 9V/12V wall-wart barrel adapter, which
  would exceed MCP73871's input rating.
- **Downstream 3.3V regulation** for the ESP32-S3/DWM3000 loads is not yet
  designed (see "No dedicated 3.3V buck/LDO regulator" above) -- needed
  before those sheets can be built.
- **MAX17048 ALRT/SCL/SDA pull-ups** deferred to the connectivity sheet (see
  scope decisions above) -- don't forget them when that sheet is built.
