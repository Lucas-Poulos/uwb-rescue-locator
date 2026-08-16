# UWB Rescue Locator

Repo: https://github.com/Lucas-Poulos/uwb-rescue-locator

A two-board UWB positioning system for a rescue/safety use case: a **wristband**
worn by a person, and a fixed **bay station** that ranges to it from four
anchor points to triangulate its 3D position and upload it to the internet.

## Getting started (new contributor setup)

### 1. Install KiCad

The team standard is **KiCad 10.0.5** (see Toolchain below for why).

- **macOS**: `brew install --cask kicad` (Homebrew). If KiCad is already
  installed some other way, add `--force` to overwrite it.
- **Windows/Linux**: download the installer for your platform from
  https://www.kicad.org/download/.

You do **not** need to set any environment variables or configure library
paths yourself -- both boards' `fp-lib-table`/`sym-lib-table` use
`${KIPRJMOD}`-relative paths into this repo's own `shared/` and `libs/`
folders, so cloning the repo anywhere and opening a project just works.

The very first time you launch the KiCad GUI on a given machine, it may
offer to set up its own default global libraries (Device, Connector, etc.)
-- accept the defaults. This is a one-time, per-machine, KiCad-level setup
step, unrelated to this repo.

### 2. Get repo access and clone it

Ask whoever's administering the repo to add you as a collaborator (repo
link at the top of this file), then:

```
git clone git@github.com:Lucas-Poulos/uwb-rescue-locator.git
cd uwb-rescue-locator
```

(Use the HTTPS clone URL instead if you haven't set up an SSH key with
GitHub.)

### 3. Open a board

KiCad doesn't support one project spanning multiple PCBs, so open whichever
board you're working on directly -- there's no single top-level project
file for the whole repo:

```
open wristband/wristband.kicad_pro       # macOS; or just double-click the file
open bay-station/bay-station.kicad_pro
```

### 4. Sanity-check your setup

From a terminal, **outside** this repo (see the `kicad-cli` gotcha further
down for why):

```
cd /tmp
kicad-cli sch erc /path/to/uwb-rescue-locator/wristband/wristband.kicad_sch
```

If this reports a handful of known/expected items (see each board's sheet
table below) rather than a wall of "library not included in configuration"
errors, your KiCad install is set up correctly. If you do see that wall of
errors, see the per-major-version global library table note in Toolchain.

Before pushing anything, also read `CONTRIBUTING.md` -- branch off `main`,
don't edit a sheet someone else is actively working on, and PRs need review
(branch protection is on).

## Status (last updated 2026-08-15, revised same day)

**Schematic capture is in progress on both boards. Nothing is wired yet
except each board's own Power/BMS sheet.** If you're an agent or a new
teammate picking this up cold, read this whole section before touching
anything -- it's written to be a complete handoff.

### What exists, per board

Both boards now have 7 hierarchical sheets each. Reference designators are
project-wide unique per board (checked, no collisions) -- see each
`libs/components.csv` for the full part-by-part BOM.

**Wristband** (`wristband/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels, no drawn wires), ERC clean (0 errors, 1 cosmetic warning) | JST-PH battery -> AO3401A reverse-polarity FET -> TVS -> DW01A+FS8205A protection -> MCP73831 charger (USB-C in) |
| Radio MCU | Placement only, not wired | NINA-B111 (U3) + DWM3000 (U4) + decoupling caps + GPIO5/6 strapping pull-downs for DWM3000's SPI mode |
| Mechanical | Placement only | 4x M2 mounting holes |
| Regulation | Placement only, not wired | MCP1700T-3302E/TT LDO (3.3V) -- steps the protected battery rail down to a safe voltage for NINA-B111/DWM3000 (see "Confirmed chips" below for why this exists) |
| Antenna | Placement only, not wired | ProAnt InSide-2400 BLE antenna (U.FL) + DNP 0603 L/C matching network (values pending RF tuning) |
| Programming/Debug | Placement only, not wired | ARM Cortex Debug SWD header for NINA-B111 |

**Bay Station** (`bay-station/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels), ERC has 8 known/expected items (see `power_bms_notes.md`) | Barrel jack + USB-C power-only input -> MCP73871 power-path charger -> MAX17048 fuel gauge; separate backup-battery input with its own AO3401A reverse-polarity FET + TVS |
| Connectivity | Placement only, not wired | ESP32-S3-WROOM-1 (U3) + decoupling |
| UWB Anchors | Placement only, not wired | 4x DWM3000 (U4-U7), one per anchor, individually labeled + decoupled, each with its own GPIO5/6 SPI-mode strapping pull-downs |
| Mechanical | Placement only | 4x M3 mounting holes |
| Regulation | Placement only, not wired | TPS62A02PDDCR buck converter -- steps the unregulated `+VSYS` rail down to a safe ~3.3V for ESP32-S3/DWM3000 anchors |
| Programming/Debug | Placement only, not wired | ESP32-S3 boot-strap resistors + EN RC delay + BOOT/RESET buttons + a second, data-capable USB-C for native-USB flashing (see "Not done yet" -- this duplicate-USB-C situation is a flagged open item) |

"Placement only" sheets deliberately show a lot of ERC "not connected"/"not
driven" warnings -- that's expected, not a bug, until they get wired.

### Confirmed chips/ICs (all sourced against real datasheets, not guessed)

| Part number | Role | Board(s) | Qty |
|---|---|---|---|
| u-blox **NINA-B111** | BLE MCU/radio | Wristband | 1 |
| Qorvo **DWM3000** | UWB transceiver module (shared part, lives in `shared/`) | Wristband (1) + Bay Station (4, one per anchor) | 5 |
| Microchip **MCP73831** | LiPo linear battery charger | Wristband | 1 |
| Fortune Semiconductor **DW01A** | Battery protection IC | Wristband | 1 |
| Fortune Semiconductor **FS8205** (commonly sold as "FS8205A" -- see `wristband/libs/README.md`) | Protection dual MOSFET, DW01A's partner IC | Wristband | 1 |
| AOS **AO3401A** | Reverse-battery-polarity protection P-MOSFET ("ideal diode") | Wristband + Bay Station | 2 |
| onsemi **ESD5B5.0ST1G** | TVS diode, battery/power-input protection | Wristband (1) + Bay Station (2) | 3 |
| Espressif **ESP32-S3-WROOM-1** | WiFi/BLE connectivity MCU | Bay Station | 1 |
| Microchip **MCP73871** | Charge management + power-path IC | Bay Station | 1 |
| Maxim/Analog Devices **MAX17048** | Battery fuel gauge (SOC monitor) | Bay Station | 1 |
| Microchip **MCP1700T-3302E/TT** | LDO regulator (3.3V) -- battery rail can hit 4.2V, which exceeds NINA-B111/DWM3000's absolute max voltage without this | Wristband | 1 |
| TI **TPS62A02PDDCR** | Buck (switching) regulator -- same voltage-safety role as the wristband's LDO, sized for the bay station's higher combined load current | Bay Station | 1 |
| ProAnt **InSide-2400** | BLE patch antenna (NINA-B111 needs an external one; DWM3000 has its own onboard antenna already) | Wristband | 1 |

Footprint caveats: DWM3000 and MAX17048 are both flagged `_PLACEHOLDER` in
their footprint files -- pin/electrical data is fully verified, but one
land-pattern dimension on each needs re-checking against the real datasheet
figure before fab (see `shared/README.md` and `bay-station/libs/README.md`).

Standard passive size for this whole project: **0603** for R/C/L (0-ohm
0603 link/jumper resistors are documented as a standard available option in
each `components.csv`, not yet placed on any sheet -- no specific
strap/bridge need identified yet).

Full reasoning/history for every choice above, plus the still-open
decisions (anchor placement, uplink backend, etc.), is in
`docs/decisions.md`.

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

1. Wire all placement-only sheets (net labels between MCU/radio pins, their
   decoupling, the new regulator outputs, and power-rail connections in
   from Power BMS).
2. **Bay station: resolve the two-USB-C-connector situation** -- the
   original power-input USB-C has no data pins, so a second, data-capable
   USB-C got added for ESP32-S3 flashing rather than consolidating into
   one. Decide whether to swap the power-only connector for a data-capable
   one instead of running two (`docs/decisions.md`).
3. **Bay station: source a real footprint for L1** (the buck converter's
   inductor, Coilcraft XGL3520-102MEC) -- no KiCad-default match exists yet.
4. Confirm/re-verify decoupling cap values placed on `radio_mcu.kicad_sch`
   and `uwb_anchors.kicad_sch` against each part's exact datasheet
   application circuit (current values are reasonable generic defaults).
5. Antenna matching-network values on `wristband/antenna.kicad_sch` (parts
   are DNP placeholders pending prototype RF tuning).
6. Anchor placement/enclosure geometry (open decision, `docs/decisions.md`).
7. Bay station uplink backend/protocol (open decision).
8. PCB footprint placement + layout (nothing placed on either `.kicad_pcb`
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

## Using Claude Code (or another coding agent) on this project

KiCad's file formats (`.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `.kicad_sym`,
`.kicad_mod`) are plain text (S-expression or JSON) -- an agent can read and
edit them directly like any other source file, no special MCP server or
plugin required. Everything in this repo so far was built that way. A few
things make it work reliably, several of them learned the hard way in this
repo's own history:

- **`kicad-cli` is the fast headless sanity check.** After any edit, run
  `kicad-cli sch erc <board>.kicad_sch` and `kicad-cli pcb drc
  <board>.kicad_pcb` before trusting a change.
  - **macOS**: a Homebrew install symlinks it onto `PATH` automatically
    (`/opt/homebrew/bin/kicad-cli`); otherwise it's inside the app bundle at
    `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
  - **Windows**: the official installer puts it on `PATH` automatically; if
    not, it's at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`.
  - **Linux**: on `PATH` automatically via most package managers (apt,
    dnf, etc.) or the official AppImage/flatpak.
- **Always run `kicad-cli` from a scratch/temp directory, never from
  inside this repo.** It writes `.rpt` report files to the current working
  directory as a side effect -- running it from inside a git repo (this
  one or any other) pollutes the working tree with stray files. This has
  actually happened once already, to an unrelated sibling project, from a
  leftover `cd`.
- **`kicad-cli` silently fails on `extends`-based symbols.** A cached
  schematic symbol using KiCad's `extends` mechanism (e.g. the default
  library's `AO3401A extends TP0610T`) makes `kicad-cli` fail to load the
  *entire file* and report it as empty (0 components, 0 ERC violations)
  instead of erroring loudly -- a suspiciously clean ERC run is a red flag,
  not necessarily good news. This repo works around it everywhere by
  embedding flattened, non-`extends` copies of any such symbols (see
  `docs/decisions.md` and the various `*_notes.md` files for examples).
- **Use an existing sheet/symbol/footprint as the format template before
  writing a new one.** Every file in this repo was built by reading a
  known-good file first -- either one already in this repo, or one of
  KiCad's own bundled default libraries -- and matching its exact
  structure, rather than freehand-authoring the s-expression format from
  memory. This repo uses literal tab characters for indentation, not
  spaces; match that.
- **Don't run scripted file edits at the same time as a live KiCad GUI
  session has the same project open.** A background GUI window doesn't
  know about changes made outside it, and saving from a stale window can
  silently overwrite newer edits -- this already caused one near-miss on
  the bay station board (see "Known gotchas" above). Close/reload any open
  KiCad windows before scripted edits, and vice versa. A lock file at
  `<board>/~<board>.kicad_pro.lck` means a GUI session currently has that
  project open.
- **Verify real datasheet facts (pinouts, voltage ratings, current draw)
  by actually fetching and reading the datasheet PDF**, not from memory or
  a search-result summary -- several real bugs/gaps in this repo were only
  caught this way (e.g. the wristband's missing voltage regulator, a
  part-number that doesn't actually exist, a mislabeled SOT-23-6 part).
- **pcbnew's Python bindings** are available for programmatic
  footprint/board work (generating a blank `.kicad_pcb`, loading a
  footprint to sanity-check its pad count, etc.) via KiCad's own bundled
  Python interpreter -- **not** your system Python, which won't have the
  `pcbnew` module installed:
  - **macOS**: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
  - **Windows**: typically `C:\Program Files\KiCad\10.0\bin\python.exe`
  - **Linux**: usually just your system `python3` if KiCad was installed via
    a package manager that wires up the `pcbnew` module for it; otherwise
    check your distro's KiCad packaging docs.

## Will this work on both Mac and Windows?

Yes, and this has actually been checked, not just assumed:

- No absolute Mac-specific paths are baked into any `.kicad_pro`/`.kicad_sch`/
  `.kicad_pcb`/library file (`git grep`-checked) -- all cross-file/library
  references use `${KIPRJMOD}`-relative paths, which KiCad resolves
  identically on every OS.
- No filenames in this repo use characters or reserved names that are
  illegal on Windows (`: * ? " < > |`, or `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/
  `LPT1-9`), and no path exceeds even a fraction of Windows' historical
  260-character path limit (longest path in this repo is 80 characters).
- All tracked files use consistent LF line endings, and `.gitattributes`
  normalizes this going forward so a Windows contributor's git config
  (which sometimes auto-converts line endings on checkout) can't silently
  turn KiCad files into CRLF and create noisy diffs or merge pain.

What differs by platform is purely the install step and a couple of tool
paths (both covered above/in Getting Started) -- KiCad itself, the file
formats, and this repo's structure are fully cross-platform.

## Contributing

See `CONTRIBUTING.md` for the git workflow (branching, hierarchical-sheet
conventions to avoid merge conflicts, pre-push checks).
