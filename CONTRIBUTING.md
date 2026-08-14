# Contributing

## KiCad version

Everyone should use the **same major KiCad version** (currently pinned to
8.0.6 in this repo -- see root `README.md`). Opening a project in a newer
version and saving bumps the file format for everyone else; if that's ever
intentional, do it as its own commit with a clear message, not mixed into a
feature change.

## Branching / PRs

- Don't commit directly to `main`. Branch per feature/sheet
  (`wristband/power-bms`, `bay-station/anchor-array`, etc.) and open a PR.
- Two people should not edit the *same* `.kicad_sch` file at the same time --
  KiCad schematic/PCB files are large single-file blobs and merge badly.
  That's the whole reason each board is split into hierarchical sheets: pick
  a sheet (or add a new one) that's yours for a given change, so parallel
  work mostly touches different files.
- Before opening a PR: run ERC/DRC and make sure violation count didn't go up
  unexpectedly (`kicad-cli sch erc <board>.kicad_sch`,
  `kicad-cli pcb drc <board>.kicad_pcb`).

## Adding a hierarchical sheet

When you start schematic capture on a board, add sheets from the KiCad GUI
(Place > Sheet) rather than hand-editing files -- e.g. for the wristband:
`power_bms`, `radio_mcu` (NINA-B1 + UWB module), `mechanical`; for the bay
station: `power_bms`, `uwb_anchors` (or one sheet per anchor), `connectivity`
(ESP32/WiFi/BT), `mechanical`. Keep sheet names and this list in the
board-level `README.md` in sync.

## Shared vs. board-local libraries

- If a part is used on **both** boards (the UWB IC/module is the obvious
  one), its symbol/footprint goes in `shared/`, not duplicated per board.
- Board-specific parts go in that board's `libs/` folder.
- Never point a footprint/symbol at a system/global KiCad library path --
  always add it to one of the project's own lib tables so it resolves the
  same way for every collaborator.

## Decisions

Component and architecture calls that are still open (UWB IC/module choice,
ESP32 vs. discrete BLE+WiFi, connector choices, etc.) live in
`docs/decisions.md`. Update it when a call gets made, with a one-line reason,
so we don't relitigate it later.
