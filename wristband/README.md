# Wristband

The worn tag. Open `wristband.kicad_pro` in KiCad.

## Scope

Deliberately minimal: **battery management plus one UWB module, and not much
else.** The tag's only job is to take part in a two-way ranging exchange with
the bay station's center anchor. Everything not needed for that is gone.

- **UWB + MCU**: Qorvo **DWM3001C** (resolved 2026-09-19) -- one module
  containing the DW3110 UWB transceiver, a Nordic nRF52833 MCU, an ST
  LIS2DH12 accelerometer, the UWB and Bluetooth antennas, power management
  and the 38.4 MHz crystal. Its datasheet states it *"requires no RF design
  as the antenna and associated analog and RF components are on the module"*.
- **BLE and the accelerometer are unused.** The tag talks only over UWB. Both
  are silicon inside a module bought for its Cortex-M4 and its UWB radio --
  they cost nothing to leave idle: no external parts, no wiring, no firmware.
  See "Worth revisiting" below.
- **BMS**: sized for "just enough" runtime -- size and weight take priority
  over battery life here, in contrast with the bay station.

Why the tag transmits once per fix: the bay station's center anchor completes
the ranging exchange, and the three outer anchors timestamp that *same*
transmission. One transmission, four measurements -- deliberately, because
the tag is the power-constrained side. See `../docs/positioning.md`.

## Status

Seven hierarchical sheets, all registered in `wristband.kicad_pro`'s `sheets`
list and wired into `wristband.kicad_sch` as sheet symbols.

| Sheet | Status | Contents |
|---|---|---|
| `power_bms` | **Wired** (global labels, no drawn wires), ERC clean | Full battery/charging/protection chain |
| `radio_mcu` | Placement only | DWM3001C (U3) + decoupling |
| `regulation` | Placement only | MCP1700T-3302E/TT LDO -> 3.3V |
| `programming_debug` | Placement only | ARM Cortex Debug SWD header |
| `indicators` | Placement only | Status LEDs D2 (charge) + D3 (system) |
| `testpoints` | Placement only, **new** | TP1-TP5: both rails, 2x GND, firmware timing marker |
| `mechanical` | Placement only | 4x M2 mounting holes |

**"Placement only" means components are instantiated and laid out, but
nothing is wired** -- no drawn wires, no global labels, no net identity.

**ERC, run 2026-09-19 with kicad-cli 10.0.6: 104 violations, ZERO errors.**
All warnings, and all the expected unwired-sheet state: 80 pin_not_connected,
10 power_pin_not_driven, 3 pin_not_driven, plus 11 lib_symbol_mismatch from
the embedded 8.0-format symbol copies differing from the 10.x libraries
(pre-existing and by design -- see the flattened-copy workaround in
`../CLAUDE.md`). DRC reports one violation per board, `invalid_outline`,
because no board outline is drawn yet.

### Sheet detail

- **`power_bms.kicad_sch`** -- the complete battery chain: 2-pin JST-PH
  battery input (`BT1`); AO3401A P-MOSFET reverse-polarity "ideal diode"
  (`Q1`, `R1`); battery-rail TVS ESD5B5.0ST1G (`D1`); DW01A + FS8205A
  single-cell overcharge/overdischarge/overcurrent protection wired per
  Fortune Semiconductor's own DW01A typical application circuit (`U1`, `Q2`,
  `R2`, `R3`, `C1`); MCP73831 Li-Po charger with power-only USB-C input, PROG
  resistor sized for ~147mA charge current, and datasheet-recommended
  input/output caps (`U2`, `J1`, `R4`, `C2`, `C3`, `R5`, `R6`); bulk/bypass
  decoupling on the protected `VBAT` rail (`C4`, `C5`).

  Net identity is carried entirely by global labels placed on top of each
  pin. ERC: 0 errors, 1 harmless documented warning. Full rationale in
  `power_bms_notes.md`.

- **`radio_mcu.kicad_sch`** -- one `wristband:DWM3001C` (`U3`) plus VDD
  decoupling (`C6` 100nF, `C7` 10uF). That is the entire sheet.

  Pin data verified against the real Qorvo DWM3001C Data Sheet Rev B (May
  2022), Table 2. One caveat carried in the symbol: **pin 18 is not
  documented in that table** (it lists 1-17 and 19-48), so it is modelled as
  a passive NC and needs confirming against the land-pattern figure.

  Decoupling values are conservative standard practice, *not*
  datasheet-specified -- the module has on-board power management and Qorvo
  publishes no external application circuit for it.

  Two real layout requirements are recorded in the sheet's own notes: the
  **10 mm antenna keep-out** (Section 7.1) and **keeping the module at least
  1 cm from the PCB edge** (Section 7.2), which reduces the horizontally
  polarized radiation component and improves multipath resilience.

- **`regulation.kicad_sch`** -- Microchip **MCP1700T-3302E/TT** LDO (`U5`,
  SOT-23, 3.3V fixed, 250mA, 1.6uA typ Iq) steps the protected `VBAT` rail
  (up to 4.2V at full charge) down to `+3V3`. Still required: the DWM3001C's
  operating maximum is 3.6V (Table 4), well under a full battery. The load is
  now much lighter than it was -- see `regulation_notes.md`.

- **`programming_debug.kicad_sch`** -- ARM Cortex Debug SWD connector (`J3`,
  `Connector:Conn_ARM_JTAG_SWD_10`, 2x5 1.27mm). Now targets the nRF52833
  inside U3, via `SWD_CLK` (pin 2) and `SWD_DIO` (pin 3).

- **`indicators.kicad_sch`** -- status LEDs. `D2`/`R10` is charge status from
  MCP73831 `STAT` (U2 pin 1, `power_bms.kicad_sch`). `D3`/`R11` is system
  status on an nRF52833 GPIO. 0603 parts, indicative 1k series resistors,
  low-current by design since the tag runs off a small cell.

- **`testpoints.kicad_sch`** *(new)* -- `TP1` +3V3, `TP2` VBAT, `TP3`/`TP4`
  ground, `TP5` a firmware timing marker on a spare nRF52833 GPIO so tag-side
  exchange timing is visible on a scope. Deliberately minimal: the DWM3001C's
  internals are unreachable and SWD already comes out on `J3`. `TP2` matters
  because there is no power switch -- it is the only way to check the battery
  chain without disconnecting the cell.

- **`mechanical.kicad_sch`** -- 4x M2 mounting holes (`H1`-`H4`).

### Next up

1. **Get U3's footprint.** Do not hand-author it -- import from a vendor
   library. Qorvo supplies DWM3001C footprint/symbol files (Altium format)
   via their UWB tech forum, and SnapMagic/SnapEDA lists a Qorvo-provided
   set. Check pad naming matches this symbol's 1-48 numbering. Blocks layout.
2. Wire the six placement-only sheets: the `VBAT` -> `+3V3` rail handoff,
   SWD to U3, the LED drives. There is no MCU-to-transceiver SPI to wire any
   more -- that link is inside the module.

### Worth revisiting

**Motion-gating the UWB.** The LIS2DH12 accelerometer inside the DWM3001C is
unused, but the tag is the power-constrained side of the whole system. Only
ranging when the wearer actually moves is the largest battery lever available
and costs nothing in hardware -- the accelerometer is already on the module's
I2C bus (pins 14/15). Worth doing once basic ranging works.

## Libraries

- `libs/` -- wristband-only symbols/footprints, including the hand-authored
  `DWM3001C` symbol
- `../shared/` -- still registered via `fp-lib-table`/`sym-lib-table`, but
  this board no longer uses anything from it (see `../shared/README.md`)
