# UWB Rescue Locator

Repo: https://github.com/Lucas-Poulos/uwb-rescue-locator

A two-board UWB positioning system for a rescue/safety use case: a **wristband**
worn by a person, and a fixed **bay station** that ranges to it from four
anchor points to triangulate its 3D position and upload it to the internet.

## Status

Infrastructure only, right now. This repo has the project layout, the KiCad
project files for both boards, shared-library wiring, and docs -- no
schematic capture or part placement has started yet. See `docs/decisions.md`
for the open component/architecture calls the team still needs to make.

## System overview

```
 ┌─────────────┐   UWB ranging (wireless)   ┌───────────────────┐
 │  Wristband   │ ─────────────────────────▶│    Bay Station     │
 │  (worn tag)  │◀───────────────────────── │ (4x UWB anchors)   │
 └─────────────┘                            └─────────┬──────────┘
                                                        │ WiFi/BT (TBD)
                                                        ▼
                                                    Internet / backend
```

- **Wristband**: NINA-B1 (BLE MCU/radio) + a UWB IC/module (TBD -- see
  `docs/decisions.md`) + a compact BMS. Design compromises favor small size
  and just enough battery life to get core functionality working.
- **Bay station**: 4x UWB ICs (one per anchor, for multilateration/TDoA-style
  3D positioning) + a connectivity MCU (ESP32, or a discrete BLE/dual-band
  WiFi IC -- TBD) + a BMS designed for long runtime rather than small size,
  since the bay station isn't worn.

There's no physical connector between the two boards -- their only interface
is the UWB radio link, documented in `docs/system-overview.md`.

## Repo layout

```
shared/                      # symbols/footprints/3D models used on BOTH boards (e.g. the UWB IC)
  symbols/                   # shared .kicad_sym library
  footprints/                # shared .pretty footprint library
  3dmodels/                  # shared .step/.wrl models
wristband/                   # KiCad project: the wearable tag
  wristband.kicad_pro/sch/pcb
  libs/                      # wristband-only symbols/footprints
bay-station/                 # KiCad project: the fixed 4-anchor station
  bay-station.kicad_pro/sch/pcb
  libs/                      # bay-station-only symbols/footprints
docs/
  system-overview.md         # block diagram + RF/data interface between the boards
  decisions.md                # open component/architecture decisions log
```

Each board is its own KiCad project (KiCad doesn't support one project
spanning multiple PCBs), but both live in this one repo so shared parts,
docs, and history stay in one place. Each project's `fp-lib-table` /
`sym-lib-table` reference the `shared/` libraries via `${KIPRJMOD}` relative
paths, so this works regardless of where the repo is cloned -- no per-machine
setup needed.

## Toolchain

Files are currently in **KiCad 8.0** format, originally authored/verified
against KiCad 8.0.6. As of 2026-08-14 this machine has been upgraded to
**KiCad 10.0.5** (the actual current stable -- confirmed as the team's
standard, superseding an earlier, since-corrected plan to target KiCad 9.x).
All existing files were re-checked with
`kicad-cli` under 10.0.5 (`sch erc`/`pcb drc`) and open/parse cleanly with no
new issues -- opening a file in the newer GUI and re-saving is still a
one-way, zero-cost upgrade whenever the team wants to bump the file format
itself; nothing has been re-saved yet, so the files on disk are still 8.0
format.

Note for anyone else upgrading KiCad's major version: `kicad-cli` alone
won't auto-populate the new version's global symbol/footprint library table
(`~/Library/Preferences/kicad/<version>/sym-lib-table` /`fp-lib-table`) --
that normally happens the first time you launch the actual KiCad GUI and it
offers to migrate/create settings. If you only ever use `kicad-cli`
headlessly without opening the GUI first, you may see a wall of spurious
"library not included in configuration" ERC errors -- just launch KiCad.app
once (or copy the two `*-lib-table` files from
`.../KiCad.app/Contents/SharedSupport/template/`) to fix it.

## Contributing

See `CONTRIBUTING.md` for the git workflow (branching, hierarchical-sheet
conventions to avoid merge conflicts, pre-push checks).
