# UWB Rescue Locator

Repo: https://github.com/Lucas-Poulos/uwb-rescue-locator

A two-board UWB positioning system for a rescue/safety use case: a
**wristband** worn by a person, and a fixed **bay station** that locates it
in 3D from four anchor points and reports it over Bluetooth LE to a nearby
laptop.

Positioning is a **hybrid of two-way ranging and TDoA**, not symmetric
multilateration. A center anchor ranges to the tag for distance; three outer
anchors timestamp the same tag transmission and give direction from the
arrival-time differences. The four anchors are **not interchangeable** --
see [`docs/positioning.md`](docs/positioning.md), which is the document to
read first if you're working on anchors, clocking, coax, or connectors.

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

## Status (last updated 2026-09-19)

**Schematic capture is in progress on both boards. Nothing is wired yet
except each board's own Power/BMS sheet.** If you're an agent or a new
teammate picking this up cold, read this whole section before touching
anything -- it's written to be a complete handoff.

> ### Architecture change in flight: the bay station's anchors
>
> The positioning scheme was specified properly for the first time on
> 2026-09-19 (`docs/positioning.md`), and it invalidates how the bay
> station's UWB anchors are currently drawn. **Target: 10-30 cm accuracy at
> ~10 m, on Channel 5 (6489.6 MHz).**
>
> What the schematic gets wrong today:
>
> 1. **The four anchors are drawn as interchangeable peers.** They aren't --
>    one is a center anchor doing two-way ranging, three are outer anchors
>    doing TDoA against it.
> 2. **The antennas are on the board.** TDoA bearing accuracy scales with
>    baseline; a board-sized baseline gives ~17 degrees of bearing error.
>    The four antennas move onto ~1-2 m coax runs to a rigid frame.
> 3. **The DWM3000 module can't do TDoA in a multi-anchor array at all.** It
>    exposes no clock pin, so four of them cannot share a time base -- and
>    1 ns of clock error is 30 cm of position error.
>
> **The resolved architecture:** four discrete **DW3210** ICs on the one PCB,
> sharing a single 38.4 MHz TCXO through a 1:4 low-skew buffer, with the four
> antennas remote on coax. This makes synchronization *structurally absent*
> rather than solved -- no drift model, no sync firmware -- and moves the cost
> into the RF path, where CH5's ~17 dB of link margin absorbs it.
>
> Going discrete adds an RF front-end and a controlled-impedance stackup. It
> also loses the module's pre-certified status -- which **does not matter
> here**: this is a university prototype, not marketed or sold, so it doesn't
> go through FCC/CE testing. That was the single largest cost of going
> discrete, and it's now off the table. See `docs/decisions.md`.
>
> The remaining critical-path item is **array calibration**, which the design
> genuinely does not close without.
>
> **The wristband is unaffected by the clock problem** -- a single transceiver
> has nothing to synchronize against. It has separately consolidated onto a
> single DWM3001C; see its own README.

### What exists, per board

The wristband has 7 hierarchical sheets, the bay station 10. Reference designators are
project-wide unique per board (checked, no collisions) -- see each
`libs/components.csv` for the full part-by-part BOM.

**Wristband** (`wristband/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels, no drawn wires), ERC clean (0 errors, 1 cosmetic warning) | JST-PH battery -> AO3401A reverse-polarity FET -> TVS -> DW01A+FS8205A protection -> MCP73831 charger (USB-C in) |
| Radio MCU | Placement only, not wired | DWM3001C (U3) + decoupling. One module: DW3110 UWB + nRF52833 MCU + accelerometer + both antennas |
| Mechanical | Placement only | 4x M2 mounting holes |
| Regulation | Placement only, not wired | MCP1700T-3302E/TT LDO (3.3V) -- battery hits 4.2V, DWM3001C tops out at 3.6V |
| Programming/Debug | Placement only, not wired | ARM Cortex Debug SWD header, targeting the nRF52833 inside U3 |
| Indicators | Placement only | Status LEDs: D2 charge (MCP73831 STAT) + D3 system (nRF52833 GPIO) |
| Test Points | Placement only, **new** | TP1-TP5: both rails, 2x GND, firmware timing marker |

**Bay Station** (`bay-station/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels), ERC has 8 known/expected items (see `power_bms_notes.md`) | Barrel jack + USB-C power-only input -> MCP73871 power-path charger -> MAX17048 fuel gauge; separate backup-battery input with its own AO3401A reverse-polarity FET + TVS |
| Connectivity | Placement only, not wired | Fanstel BT840 (U3, nRF52840) + decoupling. Symbol authored from the real datasheet |
| UWB Array | Placement only, not wired | 4x DW3210 (U4=A0 center, U5-U7=A1-A3 outer) + GPIO5/6 straps (R10-R17) + IRQ pulldowns (R25-R28) |
| Mechanical | Placement only | 4x M3 mounting holes |
| Regulation | Placement only, not wired | TPS62A02PDDCR buck converter -- steps the unregulated `+VSYS` rail down to a safe ~3.3V for the BT840 host and the DW3210 anchors |
| Clock Distribution | Placement only, **new** | Shared 38.4MHz reference for the 4x DW3210 array: AC-coupling + XTO caps placed, TCXO/buffer TBD |
| Indicators | Placement only | Status LEDs: D4 charging, D5 charge-done, D6 power-good (all MCP73871), D7 system (host GPIO) |
| Test Points | Placement only | TP1-TP14: rails, 2x GND, TCXO + 4x anchor clock, SPI, IRQ, reset |
| GNSS / Orientation | Placement only, **new** | MAX-M10S GNSS (U9) + LIS3MDL magnetometer (U10) + LIS2DH accelerometer (U11) -- georeferences the array |
| Programming/Debug | Placement only | **Rebuilt for Nordic**: SWD header (J3) + RESET button (SW2). ESP32 circuitry and the second USB-C deleted |

"Placement only" sheets deliberately show a lot of ERC "not connected"/"not
driven" warnings -- that's expected, not a bug, until they get wired.

### Confirmed chips/ICs (all sourced against real datasheets, not guessed)

| Part number | Role | Board(s) | Qty |
|---|---|---|---|
| Qorvo **DWM3001C** | UWB transceiver + nRF52833 MCU + LIS2DH12 accelerometer + both antennas, one module. Replaced NINA-B111 + DWM3000 + the antenna sheet | Wristband | 1 |
| Qorvo **DW3210** | Discrete UWB transceiver IC, QFN-40 5x5mm. One per anchor (U4=A0 center, U5-U7=A1-A3 outer). Chosen over the DWM3000 module because the module exposes no clock pin, and a shared reference is what makes the TDoA array work -- see `docs/positioning.md` | Bay Station | 4 |
| Qorvo **DWM3000** | UWB transceiver module. **No longer used on either board** -- the wristband moved to the DWM3001C and the bay station to discrete DW3210. Symbol and footprint are retained in `shared/` for reference only | -- | 0 |
| Microchip **MCP73831** | LiPo linear battery charger | Wristband | 1 |
| Fortune Semiconductor **DW01A** | Battery protection IC | Wristband | 1 |
| Fortune Semiconductor **FS8205** (commonly sold as "FS8205A" -- see `wristband/libs/README.md`) | Protection dual MOSFET, DW01A's partner IC | Wristband | 1 |
| AOS **AO3401A** | Reverse-battery-polarity protection P-MOSFET ("ideal diode") | Wristband + Bay Station | 2 |
| onsemi **ESD5B5.0ST1G** | TVS diode, battery/power-input protection | Wristband (1) + Bay Station (2) | 3 |
| Fanstel **BT840** (Nordic nRF52840) | Host MCU + BLE link to a laptop. Replaced ESP32-S3-WROOM-1 once the WiFi/internet requirement was dropped | Bay Station | 1 |
| Microchip **MCP73871** | Charge management + power-path IC | Bay Station | 1 |
| Maxim/Analog Devices **MAX17048** | Battery fuel gauge (SOC monitor) | Bay Station | 1 |
| Microchip **MCP1700T-3302E/TT** | LDO regulator (3.3V) -- battery rail can hit 4.2V, which exceeds the DWM3001C's 3.6V operating max without this | Wristband | 1 |
| TI **TPS62A02PDDCR** | Buck (switching) regulator -- same voltage-safety role as the wristband's LDO, sized for the bay station's higher combined load current | Bay Station | 1 |

Footprint caveats: MAX17048 is flagged `_PLACEHOLDER` in its footprint file
-- pin/electrical data is fully verified, but one land-pattern dimension
needs re-checking against the real datasheet figure before fab (see
`bay-station/libs/README.md`). The same caveat applies to the DWM3000
footprint retained in `shared/`, though nothing uses it now.

**No footprint assigned yet**: `U3` on both boards (BT840, 65 pins; and
DWM3001C, 48 pins), plus bay-station `L1` (1uH inductor -- no exact KiCad
default matches the XGL3520, pick at BOM time) and `SW2`. Not blocking
while both `.kicad_pcb` files are still empty, but it blocks layout.

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
  unrelated wristband-alarm concept, also u-blox NINA-based) has its own
  long-standing uncommitted working-tree state -- don't touch it, don't
  assume its README reflects its actual working tree.

### Not done yet (in rough next-up order)

1. **Bay station: rework the anchor design** for four discrete DW3210s on
   one board sharing a TCXO, with the antennas on coax. Blocked behind the
   open items in `docs/decisions.md` (cable loss, TCXO/buffer selection,
   array calibration) -- this is the project's critical path.
2. Wire all placement-only sheets (net labels between MCU/radio pins, their
   decoupling, the new regulator outputs, and power-rail connections in
   from Power BMS). The wristband can proceed independently of item 1.
3. ~~**Bay station: resolve the two-USB-C-connector situation**~~ -- resolved
   by the move to Nordic. The second connector existed only for ESP32-S3
   native-USB flashing; the BT840 programs over SWD, so it goes away with the
   rest of the ESP32-specific circuitry.
4. **Bay station: source a real footprint for L1** (the buck converter's
   inductor, Coilcraft XGL3520-102MEC) -- no KiCad-default match exists yet.
5. ~~Confirm/re-verify decoupling cap values against each part's exact
   datasheet application circuit~~ -- done, see `docs/passives-reference.md`.
   One passive was found missing (100k IRQ/GPIO8 pulldowns, now added to all
   5 DWM3000 instances); DWM3000's own decoupling was confirmed to exceed
   what Qorvo's minimal example circuit actually calls for (kept anyway, not
   wrong, just more conservative than strictly required).
6. ~~Antenna matching-network values~~ -- gone. The DWM3001C carries both
   antennas on-module, so `antenna.kicad_sch` was deleted along with the
   tuning task.
7. ~~Anchor placement/enclosure geometry~~ -- topology resolved (all four
   transceivers on-board, antennas remote on coax to a rigid frame, see
   `docs/positioning.md`); the remaining piece is the frame's mechanical
   design, including A0's out-of-plane offset.
8. Bay station uplink protocol -- what the laptop actually receives over BLE
   (open decision). "Backend" no longer applies: there is no server, see
   `docs/system-overview.md`.
9. PCB layout. The bay station's `.kicad_pcb` now has its **4-layer
   controlled-impedance stackup** set from DW3000 Section 7.3.2 Figure 35
   (1.048mm finished) -- but nothing else: no footprints, no outline. The
   wristband's is still an empty stub. The blocker is upstream of layout:
   both boards are placement-only, so there are **zero nets** to import.

## System overview

```
                         A1 ← antenna on coax
                            \
   ┌─────────────┐           \      ┌───────────────────────────┐
   │  Wristband   │  UWB       ○────│  Bay Station (ONE PCB)     │
   │  (worn tag)  │ ═════════▶ A0   │  4x DW3210, one TCXO       │
   └─────────────┘  one TX    / \   │  BT840 (nRF52840) host     │
                             /   \  └───────────┬────────────────┘
                           A2     A3            │ Bluetooth LE
                      antennas on ~1-2 m        ▼
                      coax, rigid frame       Laptop

   A0     two-way ranging  -> range to tag
   A1-A3  TDoA vs. A0      -> direction to tag

   All four transceivers share one clock on the board.
   Only the antennas are remote.
```

- **Wristband**: one Qorvo DWM3001C (UWB + nRF52833 MCU + antennas) +
  a compact BMS (MCP73831 charger + DW01A/FS8205 protection + AO3401A
  reverse-polarity protection). Design compromises favor small size and
  just enough battery life to get core functionality working. In the
  positioning scheme its job is simply to transmit -- one transmission
  yields all four measurements, deliberately, because the tag is the
  power-constrained side.
- **Bay station**: four UWB receivers in two roles (one center, three outer)
  on a single PCB sharing one TCXO + a Fanstel BT840 (nRF52840) host, linking
  to a laptop over BLE + a BMS designed for long runtime rather than small size
  (MCP73871 power-path charger + MAX17048 fuel gauge), since the bay station
  isn't worn. The four antennas sit on ~1-2 m coax runs to a rigid frame --
  that's what buys the baseline the bearing measurement needs.

There's no physical connector between the wristband and the bay station --
their only interface is the UWB radio link. The bay station's own antennas
are wired to it over SMA coax (CH5 at 6489.6 MHz is above U.FL's 6 GHz
rating). See `docs/system-overview.md` and `docs/positioning.md`.

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
  positioning.md             # the ToF + TDoA scheme, error budget, clock architecture
  system-overview.md         # block diagram + RF/data interface between the boards
  decisions.md               # open + resolved component/architecture decisions log
  passives-reference.md      # every chip's reference-design passives, compiled per-chip
  bom-cost.md                # build cost estimate for one prototype pair
firmware/                    # nRF52840 / nRF52833 firmware -- skeleton only, nothing written
CLAUDE.md                    # working rules for Claude Code / other coding agents
CONTRIBUTING.md              # git workflow, sheet conventions, pre-push checks
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

**The working rules for agents live in [`CLAUDE.md`](CLAUDE.md)** -- Claude
Code picks that up automatically. This section is the human-readable version
of why those rules exist.

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
