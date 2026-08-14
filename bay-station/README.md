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

Blank project -- no schematic capture yet. When that starts, add
hierarchical sheets from the KiCad GUI rather than hand-editing files; see
root `CONTRIBUTING.md` for the suggested sheet breakdown
(`power_bms`, `uwb_anchors`, `connectivity`, `mechanical`, ...) and keep this
file's sheet list in sync as sheets get added.

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
