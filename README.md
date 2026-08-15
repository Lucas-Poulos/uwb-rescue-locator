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

Built and verified against **KiCad 8.0.6** (`kicad-cli`), since that's what's
currently installed on the machine this was scaffolded on. Opening these
files in KiCad 9 and re-saving is a one-way, zero-cost upgrade -- do that
once the whole team is on KiCad 9, and update this note.

## Contributing

See `CONTRIBUTING.md` for the git workflow (branching, hierarchical-sheet
conventions to avoid merge conflicts, pre-push checks).
