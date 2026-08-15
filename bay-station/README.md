# Bay Station

The fixed reference station. Open `bay-station.kicad_pro` in KiCad.

## Scope

- **UWB anchors**: 4x UWB IC, ranged against the wristband tag to
  triangulate its 3D position. Same UWB part as the wristband -- see
  `../shared/` once it's chosen (`../docs/decisions.md`).
- **Connectivity**: ESP32, or a discrete BLE IC + dual-band WiFi IC -- TBD,
  see `../docs/decisions.md`. Uploads computed/raw position data to the
  internet.
- **BMS**: optimized for longevity rather than size, since this board isn't
  worn (contrast with the wristband's compromise-heavy BMS).

## Status

First hierarchical sheet is in: `power_bms.kicad_sch`, wired into the root
sheet (`bay-station.kicad_sch`) as sheet "Power BMS" and registered in
`bay-station.kicad_pro`'s `sheets` list. It covers:

- External power input: DC barrel jack (`Connector:Barrel_Jack`) with a
  series Schottky reverse-polarity diode, and a USB-C power-only receptacle
  (`Connector:USB_C_Receptacle_PowerOnly_6P`, with CC1/CC2 5.1k pulldowns),
  both feeding a shared `+5V_IN` net with its own TVS.
- Reverse-battery-polarity protection on the backup Li-Ion cell: a P-channel
  MOSFET (AO3401A) "ideal diode" (source = battery+, gate pulled to GND
  through a resistor, drain feeds the protected `VBATT_PROT` rail), plus its
  own TVS on the battery line.
- MCP73871 charge-management/power-path IC, wired per Microchip's typical
  application circuit (DS20002090E) in AC-DC-adapter/power-path mode
  (SEL=high), with PROG1/PROG3 resistors setting a 500 mA fast-charge /
  50 mA termination profile, the VPCC power-path-priority divider, THERM
  NTC, and IN/OUT/VBAT decoupling.
- MAX17048 fuel gauge (`bay_station:MAX17048G+T10`), VDD decoupling cap,
  CTG/QSTRT tied per datasheet; ALRT/SCL/SDA brought out via global labels
  for a future connectivity sheet to terminate/pull up.
- No ESP32-S3-WROOM-1 or DWM3000 instances on this sheet -- see
  `power_bms_notes.md` for why, and what's deferred to future sheets
  (`uwb_anchors`, `connectivity`).

ERC-clean except one documented, deliberately-deferred finding (MAX17048
SCL has no driver yet, since the I2C host doesn't exist until the
connectivity sheet is built) -- see `power_bms_notes.md`.

Three more sheets are now in, wired into the root sheet and registered in
`bay-station.kicad_pro`'s `sheets` list, same as `power_bms`. **All three are
placement-only** -- components are instantiated but nothing is wired (no
wires, no global labels), so ERC correctly shows no "not connected"/"not
driven" findings on them yet (isolated, unwired symbols aren't flagged by
KiCad's ERC) -- that wiring pass is still to come:

- `connectivity.kicad_sch` -- one `RF_Module:ESP32-S3-WROOM-1` (U3) plus its
  0603 decoupling caps (C5 = 10uF bulk, C6/C7 = 100nF each) placed near the
  module's single exposed 3V3 pin, per Espressif's ESP32-S3-WROOM-1 hardware
  design guidelines (already cited in `libs/README.md`/`libs/components.csv`).
- `uwb_anchors.kicad_sch` -- four separate `uwb_rescue_locator_shared:DWM3000`
  instances (U4-U7), one per anchor, each labeled "Anchor 1".."Anchor 4" and
  given its own 0603 decoupling set (100nF near VDD1, 100nF near VDD3V3,
  1uF bulk on VDD3V3, C8-C19) -- a typical UWB-transceiver decoupling scheme,
  not independently re-verified against the DWM3000 datasheet's own
  application-circuit figure in this pass (see the sheet's own in-schematic
  note); verify before fab, same as this repo's other flagged estimates.
- `mechanical.kicad_sch` -- four `Mechanical:MountingHole` instances (H1-H4,
  M3 clearance, no electrical connection) at placeholder positions, plus an
  in-schematic note that anchor placement/enclosure geometry is still an open
  decision (`docs/decisions.md`).

All other sheets from `CONTRIBUTING.md`'s suggested breakdown are now
started; future work is wiring these three sheets up (power rails from
`power_bms`, SPI/GPIO between U3 and U4-U7) rather than adding new sheets.

Two more sheets are now in, wired into the root sheet and registered in
`bay-station.kicad_pro`'s `sheets` list, fixing three confirmed hardware gaps
(no regulated 3.3V rail for the ESP32-S3/DWM3000 loads, floating DWM3000
GPIO5/GPIO6 SPI-mode-strapping pins, and missing ESP32-S3 boot-strapping/
programming provisions). **Both are placement-only**, same convention as
`connectivity`/`uwb_anchors`/`mechanical` -- see `regulation_notes.md` for the
full current-draw math and datasheet citations:

- `regulation.kicad_sch` -- a TI `TPS62A02PDDCR` synchronous buck converter
  (U8, 2.5-5.5V in / 2A, real datasheet SLUSEG9E) stepping the unregulated
  `+VSYS` rail down to a new `+3V3_SYS` rail, sized with ~3.5x headroom over
  the real worst-case combined draw (ESP32-S3-WROOM-1 355mA peak TX + 4x
  DWM3000 55mA RX each, both from their real datasheets). Chosen over the
  higher-current TPS563201/TPS563200 family specifically because its
  2.5-5.5V input range covers this board's single-cell-Li-Ion-only `+VSYS`
  condition (which the 4.5V-minimum TPS563201 family cannot). Includes the
  datasheet-recommended 1uH inductor (L1), input/output caps (C20/C21),
  optional feedforward cap (C22), and feedback divider (R8=453k/R9=100k,
  targeting 3.318V).
- `uwb_anchors.kicad_sch` -- 8 new 10k pull-down resistors (R10-R17) added to
  the existing 4-anchor sheet, defining SPI mode 0 on each DWM3000's
  GPIO5/GPIO6 pins per the real Qorvo datasheet's "Sample GPIOs 5&6 to set SPI
  mode" power-up step. Placed explicitly for all 4 anchors (not compacted into
  a shared note), matching the sheet's existing per-anchor-explicit-component
  convention.
- `programming_debug.kicad_sch` -- ESP32-S3-WROOM-1 boot-strapping pull
  resistors (GPIO0 pull-up, GPIO3/GPIO45/GPIO46 pull-downs, all 10k, per the
  real Espressif datasheet's Table 4-1/4-3/4-4/4-5), an EN reset RC delay
  (10k + 1uF, per the real Espressif ESP32-S3 Hardware Design Guidelines'
  Schematic Checklist), BOOT and RESET tactile buttons (SW1/SW2), and a
  dedicated data-capable USB-C receptacle (J3 + CC1/CC2 pulldowns R23/R24) for
  native-USB flashing via the ESP32-S3's built-in USB-OTG peripheral --
  chosen over a UART-bridge IC since the datasheet confirms native
  USB-Serial-JTAG/USB-OTG download-boot support. Flags one open concern: the
  board's existing USB-C connector (J2, power_bms.kicad_sch) is power-only and
  can't carry the native-USB data lines, hence the second connector.

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
