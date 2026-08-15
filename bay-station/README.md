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

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
