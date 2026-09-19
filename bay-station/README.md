# Bay Station

The fixed reference station. Open `bay-station.kicad_pro` in KiCad.

## Scope

- **UWB anchors**: four DW3210 transceivers, all on this PCB sharing one
  38.4 MHz TCXO, in two distinct roles -- one **center** anchor (A0) that
  does two-way ranging with the wristband, and three **outer** anchors that
  measure TDoA against it. Range plus direction gives a 3D fix. The four
  **antennas** are remote, on ~1-2 m SMA coax runs to a rigid frame. Read
  `../docs/positioning.md` before touching anything in the anchor, clock,
  coax, or connector path.
- **Host MCU + link**: Fanstel **BT840** (Nordic nRF52840, resolved
  2026-09-19) -- drives the four DW3210s and reports position over **BLE to a
  nearby laptop**. There is no internet uplink; that was dropped deliberately,
  and dropping it is what allowed the move off the ESP32-S3 to Nordic. See
  `../docs/decisions.md`.
- **BMS**: optimized for longevity rather than size, since this board isn't
  worn (contrast with the wristband's compromise-heavy BMS).

Target performance: **10-30 cm at ~10 m, on Channel 5 (6489.6 MHz)**.

> **The anchor design is mid-change.** The schematic currently shows four
> DWM3000 **modules**, all treated as interchangeable peers with on-board
> antennas. That's wrong on three counts: the modules can't share a reference
> clock (no clock pin is exposed, so TDoA across them is impossible), the
> anchors have distinct center/outer roles, and the antennas belong ~1-2 m
> off-board or the baseline is far too short to give a useful bearing.
>
> The resolved design is four discrete **DW3210** ICs on this board sharing
> one TCXO through a 1:4 low-skew buffer, with the antennas on coax. See
> `../docs/decisions.md` -- the open items under "Critical path for the bay
> station" gate this work, and **array calibration is a deliverable, not a
> bring-up nicety**: the design does not close without it.

## Status

Nine hierarchical sheets, all registered in `bay-station.kicad_pro`'s
`sheets` list and wired into `bay-station.kicad_sch` as sheet symbols.

| Sheet | Status | Contents |
|---|---|---|
| `power_bms` | **Wired** (global labels), 8 known/expected ERC items | Barrel jack + USB-C in -> MCP73871 power-path -> MAX17048 gauge |
| `connectivity` | Placement only | **BT840 (U3) placed** + C5/C6/C7 decoupling. Symbol authored; footprint still needed |
| `uwb_array` | Placement only | **4x DW3210 placed** (U4=A0 center, U5-U7=A1-A3 outer) + R10-R17 straps + R25-R28 IRQ pulldowns |
| `regulation` | Placement only | TPS62A02PDDCR buck -> +3V3_SYS |
| `programming_debug` | Placement only | **Rebuilt for Nordic**: SWD header (J3) + RESET button (SW2). ESP32 circuitry and the second USB-C deleted |
| `clock_dist` | Placement only, **new** | Shared 38.4MHz reference: AC-coupling + XTO caps placed, TCXO/buffer TBD |
| `indicators` | Placement only, **new** | Status LEDs D4-D7 (charge, charge-done, power-good, system) |
| `testpoints` | Placement only, **new** | TP1-TP14: rails, 2x GND, TCXO + 4x anchor clock, SPI, IRQ, reset |
| `mechanical` | Placement only | 4x M3 mounting holes |

**"Placement only" means components are instantiated but nothing is wired**
-- no wires, no global labels. KiCad's ERC doesn't flag isolated unwired
symbols, so these sheets contribute no "not connected" findings yet. That
wiring pass is still to come.

### Sheet detail

- **`power_bms.kicad_sch`** -- external power input via DC barrel jack
  (`Connector:Barrel_Jack`, series Schottky reverse-polarity diode) and a
  power-only USB-C receptacle (`Connector:USB_C_Receptacle_PowerOnly_6P`,
  CC1/CC2 5.1k pulldowns), both feeding a shared `+5V_IN` net with its own
  TVS. Backup Li-Ion cell gets an AO3401A P-MOSFET reverse-polarity "ideal
  diode" plus its own TVS. MCP73871 charge-management/power-path IC wired per
  Microchip's typical application circuit (DS20002090E) in
  AC-DC-adapter/power-path mode (SEL=high), PROG1/PROG3 set for a 500mA
  fast-charge / 50mA termination profile, plus the VPCC power-path-priority
  divider, THERM NTC, and IN/OUT/VBAT decoupling. MAX17048 fuel gauge
  (`bay_station:MAX17048G+T10`) with VDD decoupling, CTG/QSTRT tied per
  datasheet, ALRT/SCL/SDA brought out via global labels.

  ERC-clean except one deliberately-deferred finding (MAX17048 SCL has no
  driver until the I2C host on `connectivity` is wired). See
  `power_bms_notes.md`.

- **`connectivity.kicad_sch`** -- Fanstel **BT840** (`U3`, nRF52840) plus
  `C5`/`C6`/`C7` supply decoupling. Symbol hand-authored: all 65 pins (16
  castellated, 49 LGA) from the real Fanstel datasheet Ver 1.15 Pin Function
  table. GND verified on 10/A0/B0/C0/D0/F0-F3, VDD on 9.

  The sheet notes carry what the wiring pass needs: use **SPIM3** for the
  anchor bus (the only high-speed SPI instance on the nRF52840), and avoid
  B4/B5/C3/D2 if the design might ever move to a BT840X/XE, where those are
  PA-control pins.

  Footprint still outstanding, and the datasheet contradicts itself on LGA
  count (summary says 45, its own table lists 49) -- reconcile both against
  the mechanical drawing.

- **`uwb_array.kicad_sch`** -- four `uwb_rescue_locator_shared:DWM3000`
  instances (`U4`-`U7`), each labeled "Anchor 1".."Anchor 4", each with its
  own decoupling set (100nF at VDD1, 100nF at VDD3V3, 1uF bulk on VDD3V3,
  `C8`-`C19`), 10k GPIO5/GPIO6 SPI-mode strap pull-downs (`R10`-`R17`), and a
  100k IRQ/GPIO8 pulldown (`R25`-`R28`, per Qorvo's Figure 11, "to prevent
  spurious interrupts").

  **Now four real DW3210s**, `U4`-`U7`, labelled A0-A3 on the sheet. `U4` is
  the **center anchor** and does the two-way ranging; `U5`-`U7` are the outer
  anchors that timestamp the same transmission for TDoA. Symbol hand-authored
  from the real DW3000 Datasheet v1.3 Table 2.

  Kept from the module revision, because both survive the module-to-IC move
  unchanged (same DW3000 core) and both were datasheet-verified findings:
  - `R10`-`R17`, the 10k GPIO5/GPIO6 SPI-mode straps (two per anchor).
  - `R25`-`R28`, the 100k IRQ pull-downs from Qorvo Figure 11 -- a real gap
    the passives audit originally caught. Not losing it twice.

  Deleted with the modules: `C8`-`C19`. Those were sized for a single VDD3V3
  module rail and do not map onto a bare DW3210, which has VDD1 (pin 29, main
  + I/O), VDD2a/VDD2b (28/23) and VDD3 (26), **plus two decoupling-only pins**
  -- VTX_D (27) and VIO_D (38) -- that each need their own cap to ground and
  must not be tied to a rail. Decoupling is deliberately not yet placed;
  re-derive it from the IC datasheet at wiring time.

- **`regulation.kicad_sch`** -- TI `TPS62A02PDDCR` synchronous buck (`U8`,
  2.5-5.5V in / 2A, datasheet SLUSEG9E) stepping `+VSYS` down to `+3V3_SYS`.
  Chosen over the TPS563201/TPS563200 family specifically because its
  2.5-5.5V input range covers the single-cell-Li-Ion-only `+VSYS` condition
  that the 4.5V-minimum TPS563201 cannot. Includes the datasheet-recommended
  1uH inductor (`L1`), input/output caps (`C20`/`C21`), feedforward cap
  (`C22`), and feedback divider (`R8`=453k/`R9`=100k, targeting 3.318V).
  Budget re-run twice on 2026-09-19 and now ~347mA against the 2A rating
  (~5.8x) -- dropping WiFi removed the largest single load. Deliberately
  oversized and staying that way; see `regulation_notes.md`.

- **`programming_debug.kicad_sch`** *(rebuilt)* -- collapsed to what a Nordic
  part actually needs: `J3`, a 2x5 1.27mm ARM Cortex Debug SWD header, and
  `SW2`, the RESET button. Deliberately the **same debug connector as the
  wristband**, so one probe and one cable serve the whole project.

  Deleted as ESP32-specific: `R18`-`R21` (GPIO0/3/45/46 boot straps -- Nordic
  has no equivalent), `R22`+`C23` (EN reset RC -- the nRF52840 has internal
  POR), `SW1` (BOOT button -- no boot-mode pin), and `J3`+`R23`/`R24` (the
  data-capable USB-C, which existed only for ESP32-S3 native-USB flashing).

  **That last deletion resolves the two-USB-C open item** -- by removal
  rather than by choosing between connectors. The board is back to one USB-C:
  the power-only `J2` on `power_bms.kicad_sch`.

  Exact BT840 pin numbers for SWDIO/SWCLK/RESET are not filled in yet, for
  the same reason as `connectivity`.

- **`clock_dist.kicad_sch`** *(new)* -- the defining block of this board's
  architecture. Holds the shared 38.4 MHz reference network that makes TDoA
  across four receivers possible at all. Topology is TCXO -> 1:4 low-skew
  fan-out buffer -> 2200 pF AC coupling -> each DW3210's XTI, with 1 pF from
  each XTO to ground.

  Placed: `C24`-`C27` (2200 pF AC coupling) and `C28`-`C31` (1 pF XTO-to-GND)
  -- the passives whose values the DW3000 datasheet actually specifies. The
  **TCXO and buffer parts are not yet selected** (open item); the sheet
  carries the full Table 10 selection spec as an in-schematic note so
  whoever picks them has it to hand.

- **`indicators.kicad_sch`** *(new)* -- status LEDs. Before this sheet the
  bay station had no user-visible indication of any kind, which is a poor
  property for a device whose job is locating someone in trouble.
  `D4`/`R29` from MCP73871 `STAT1` (charging), `D5`/`R30` from `STAT2`
  (charge complete), `D6`/`R31` from `~PG` (external power good) -- all
  three charger outputs were previously unconnected -- plus `D7`/`R32` on an
  BT840 GPIO for firmware-driven system status. 0805 LEDs, 0603 series
  resistors at an indicative 1k.

- **`testpoints.kicad_sch`** *(new)* -- 14 probe points, chosen against this
  board's real risks rather than sprinkled evenly. `TP5` on the TCXO and
  `TP6`-`TP9` on each DW3210 XTI cover the shared clock, which is the signal
  that silently produces nonsense rather than failing loudly if it is missing
  at one anchor. `TP10`-`TP12` (SPI) plus `TP13` (A0 IRQ) and `TP14` (anchor
  reset) serve the multi-instance driver bring-up. `TP1`/`TP2` are the rails.

  **Two grounds, deliberately.** `TP3` is sited next to the clock points so a
  scope can use a short ground spring -- at 38.4 MHz a flying clip lead's
  inductance distorts what you are trying to measure. `TP4` is general
  purpose, elsewhere on the board.

  **Layout caveat on the sheet:** a test point on the clock network is a stub,
  and stubs degrade exactly the signal integrity this design depends on. Keep
  `TP5`-`TP9` minimal and on the existing routing; if layout cannot take all
  four anchor clock points, keep `TP6`/`TP7` and drop the rest -- two is
  enough to compare skew.

- **`mechanical.kicad_sch`** -- four `Mechanical:MountingHole` instances
  (`H1`-`H4`, M3 clearance, no electrical connection) at placeholder
  positions. Final positions depend on the enclosure and on the anchor
  topology, neither finalized.

### Next up

1. **Author footprints for BT840 and DW3210.** Both symbols are done and
   placed; neither footprint is. This now blocks layout, not schematic work.
2. Select the TCXO and 1:4 fan-out buffer, and place them on `clock_dist`.
   Add the four SMA antenna connectors to `uwb_array`.
3. Wire the remaining placement-only sheets (power rails from `power_bms`,
   SPI/GPIO between U3 and the anchors).
4. Work through the open items in `../docs/decisions.md` -- cable loss,
   TCXO/buffer selection, and array calibration all gate layout. (No FCC/CE
   work: university prototype, not certified.)

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
