# UWB Rescue Locator

Repo: https://github.com/Lucas-Poulos/uwb-rescue-locator

A two-board UWB positioning system for a rescue/safety use case: a **wristband**
worn by a person, and a fixed **bay station** that ranges to it from four
anchor points to triangulate its 3D position and upload it to the internet.

## Status (last updated 2026-08-15)

**Schematic capture is in progress on both boards. Nothing is wired yet
except each board's own Power/BMS sheet.** If you're an agent or a new
teammate picking this up cold, read this whole section before touching
anything -- it's written to be a complete handoff.

### What exists, per board

Both boards now have 4 hierarchical sheets each (Root -> Power BMS -> ...).
Reference designators are project-wide unique per board (checked, no
collisions) -- see each `libs/components.csv` for the full part-by-part BOM.

**Wristband** (`wristband/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels, no drawn wires), ERC clean (0 errors, 1 cosmetic warning) | JST-PH battery -> AO3401A reverse-polarity FET -> TVS -> DW01A+FS8205A protection -> MCP73831 charger (USB-C in) |
| Radio MCU | Placement only, not wired | NINA-B111 (U3) + DWM3000 (U4) + decoupling caps (values are generic defaults, not datasheet-confirmed yet) |
| Mechanical | Placement only | 4x M2 mounting holes |

**Bay Station** (`bay-station/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels), ERC has 8 known/expected items (see `power_bms_notes.md`) | Barrel jack + USB-C power-only input -> MCP73871 power-path charger -> MAX17048 fuel gauge; separate backup-battery input with its own AO3401A reverse-polarity FET + TVS |
| Connectivity | Placement only, not wired | ESP32-S3-WROOM-1 (U3) + decoupling |
| UWB Anchors | Placement only, not wired | 4x DWM3000 (U4-U7), one per anchor, individually labeled + decoupled |
| Mechanical | Placement only | 4x M3 mounting holes |

"Placement only" sheets deliberately show a lot of ERC "not connected"/"not
driven" warnings -- that's expected, not a bug, until they get wired.

### Confirmed component choices (all sourced against real datasheets, not guessed)

- Wristband MCU/radio: **u-blox NINA-B111**
- Shared UWB module (wristband + x4 on bay station): **Qorvo DWM3000** (footprint flagged `_PLACEHOLDER`, one land-pattern dimension needs re-checking before fab -- see `shared/README.md`)
- Wristband charge/protection: **MCP73831** + **DW01A**/**FS8205** ("FS8205A" as commonly sold is actually named "FS8205" at the manufacturer -- see `wristband/libs/README.md`)
- Bay station connectivity: **ESP32-S3-WROOM-1** (KiCad default symbol/footprint, pin-verified)
- Bay station charge/power-path + fuel gauge: **MCP73871** (KiCad default) + **MAX17048** (hand-authored, footprint flagged `_PLACEHOLDER`)
- Reverse-battery-polarity protection (both boards): P-MOSFET "ideal diode" (**AO3401A**), not a series diode -- no continuous voltage-drop loss
- TVS protection: **onsemi ESD5B5.0ST1G** on battery/power-input lines on both boards
- Standard passive size for this whole project: **0603** for R/C/L (0-ohm 0603 link/jumper resistors are documented as a standard available option in each `components.csv`, not yet placed on any sheet -- no specific strap/bridge need identified yet)

Full reasoning/history for every choice above is in `docs/decisions.md`.

### Known gotchas for whoever (human or agent) works on this next

- **kicad-cli silently fails on `extends`-based symbols.** Any cached
  schematic symbol using KiCad's `extends` mechanism (e.g. the default
  `AO3401A extends TP0610T`) makes `kicad-cli` fail to load the *entire
  file* and silently report it as empty (0 components, 0 ERC violations)
  rather than erroring loudly. Both boards work around this by embedding a
  flattened, non-`extends` copy of AO3401A. If a future sheet adds another
  `extends`-based part and ERC suspiciously shows 0 violations, check this
  first.
- **Always run `kicad-cli` from a scratch directory, never from inside a
  git repo.** It writes `.rpt` report files to the current working
  directory as a side effect; running it from inside a repo pollutes that
  repo's working tree with stray files.
- **KiCad's global library table is per-major-version and doesn't
  auto-populate from `kicad-cli` alone** -- see the Toolchain section below.
- **Don't leave a KiCad GUI window open on a project while also editing its
  files by hand/via script.** This happened once already: a background GUI
  session silently resaved `bay-station/power_bms.kicad_sch` in KiCad 10
  format while a concurrent edit was adding new sheets to the root file. No
  data was lost (verified via a reference-designator diff before
  committing), but it could have silently clobbered the newer edits if the
  stale window had been saved again afterward. Close/reload any open KiCad
  windows before doing further programmatic edits, and vice versa.
- The sibling project at `~/kicad-projects/wristband-alarm` (a *different*,
  unrelated wristband-alarm concept, also using NINA-B111) has its own
  long-standing uncommitted working-tree state -- don't touch it, don't
  assume its README reflects its actual working tree.

### Not done yet (in rough next-up order)

1. Wire the 3 placement-only sheets (net labels between MCU/radio pins and
   their decoupling, power-rail connections in from Power BMS).
2. Design the bay station's missing 3.3V regulation -- `power_bms`
   currently only produces an unregulated `+VSYS` rail; the ESP32-S3 and
   DWM3000 anchors need a real regulated 3.3V supply that doesn't exist yet.
3. Confirm/re-verify decoupling cap values placed on `radio_mcu.kicad_sch`
   and `uwb_anchors.kicad_sch` against each part's exact datasheet
   application circuit (current values are reasonable generic defaults).
4. Anchor placement/enclosure geometry (open decision, `docs/decisions.md`).
5. Bay station uplink backend/protocol (open decision).
6. PCB footprint placement + layout (nothing placed on either `.kicad_pcb`
   yet -- this has all been schematic-only so far).

## System overview

```
 ┌─────────────┐   UWB ranging (wireless)   ┌───────────────────┐
 │  Wristband   │ ─────────────────────────▶│    Bay Station     │
 │  (worn tag)  │◀───────────────────────── │ (4x UWB anchors)   │
 └─────────────┘                            └─────────┬──────────┘
                                                        │ WiFi/BT (ESP32-S3)
                                                        ▼
                                                    Internet / backend (TBD)
```

- **Wristband**: NINA-B111 (BLE MCU/radio) + Qorvo DWM3000 (UWB module) +
  a compact BMS (MCP73831 charger + DW01A/FS8205 protection + AO3401A
  reverse-polarity protection). Design compromises favor small size and
  just enough battery life to get core functionality working.
- **Bay station**: 4x DWM3000 (one per anchor, for multilateration/TDoA-style
  3D positioning) + ESP32-S3-WROOM-1 (WiFi/BLE connectivity) + a BMS
  designed for long runtime rather than small size (MCP73871 power-path
  charger + MAX17048 fuel gauge), since the bay station isn't worn.

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
