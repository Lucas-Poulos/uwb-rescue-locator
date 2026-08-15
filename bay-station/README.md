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

Remaining sheets (`uwb_anchors`, `connectivity`, `mechanical`, ...) are not
started yet; add them from the KiCad GUI rather than hand-editing files, per
root `CONTRIBUTING.md`'s suggested sheet breakdown, and keep this file's
sheet list in sync as sheets get added.

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
