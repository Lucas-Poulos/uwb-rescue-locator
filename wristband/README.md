# Wristband

The worn tag. Open `wristband.kicad_pro` in KiCad.

## Scope

- **MCU/radio**: u-blox NINA-B1 (confirmed)
- **UWB IC/module**: TBD -- see `../docs/decisions.md`. Once chosen, its
  symbol/footprint go in `../shared/`, not here, since the bay station uses
  it too.
- **BMS**: sized for "just enough" runtime to make core functionality work --
  size/weight compromises take priority over battery life here (contrast
  with the bay station, which optimizes for longevity instead).

## Status

Blank project -- no schematic capture yet. When that starts, add
hierarchical sheets from the KiCad GUI rather than hand-editing files; see
root `CONTRIBUTING.md` for the suggested sheet breakdown
(`power_bms`, `radio_mcu`, `mechanical`, ...) and keep this file's sheet
list in sync as sheets get added.

## Libraries

- `libs/` -- wristband-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
