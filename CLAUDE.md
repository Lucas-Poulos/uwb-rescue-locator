# CLAUDE.md

Guidance for Claude Code / other coding agents working in this repo. Read
this before touching anything. Human-facing setup and status live in
`README.md`; this file is the working rules.

## What this project is

A two-board UWB positioning system. A worn **wristband** tag is located in
3D by a fixed **bay station** that owns four UWB anchors.

The wristband is deliberately minimal: **battery management plus a single
Qorvo DWM3001C**, which contains the UWB transceiver, the nRF52833 host MCU,
an accelerometer and both antennas. Its BLE radio and accelerometer are
unused -- do not add parts to "use" them, and do not reintroduce a separate
MCU or an external antenna. Both were removed deliberately (`docs/decisions.md`).

The positioning scheme is **not** symmetric multilateration, and this is the
single most misread thing about the project:

- **One center anchor** does two-way ranging (ToF) with the wristband. That
  yields a **range** `r` -- how far away the tag is.
- **Three outer anchors** measure **TDoA relative to the center anchor** on
  the same wristband transmission. Those three differences yield the
  **direction** to the tag.
- Range + direction = 3D position. See `docs/positioning.md` for the full
  scheme, the error budget, and why the clock architecture follows from it.

Consequences an agent must not "simplify" away:

- The four anchors are **not interchangeable peers**. The center anchor (A0)
  has a distinct role and must be identified as such in schematics and docs.
- **All four transceivers sit on the one bay-station PCB, sharing a single
  clock. It is the four antennas that are remote**, on ~1-2 m coax runs to a
  rigid frame. Do not "tidy" this into four identical on-board anchors, and
  do not turn it into four satellite anchor boards -- both were considered
  and rejected for reasons recorded in `docs/decisions.md`.
- TDoA is measured in nanoseconds against the speed of light: **1 ns ≈ 30 cm**
  of position error. At the chosen 1 m baseline the exchange rate is harsher
  still -- **1 cm of differential path error ≈ 10 cm of position error at 10 m
  range**. Anything touching the clock path, the coax, the connectors, or
  timestamp handling is precision-critical, not incidental.
- **Both boards are Nordic.** Bay station: Fanstel **BT840** (nRF52840).
  Wristband: nRF52833 inside the DWM3001C. One toolchain for the project.
  The station links to a **laptop over BLE** -- there is no WiFi and no
  internet uplink, and that is deliberate (it is what allowed the move off
  the ESP32-S3). Both parts are now placed on the bay-station schematic with
  hand-authored, datasheet-verified symbols; their footprints are still
  outstanding.
- **The bay station is deployed OUTDOORS and moved between sites**, and
  georeferences itself: MAX-M10S GNSS for position, LIS3MDL magnetometer for
  heading, LIS2DH accelerometer for tilt compensation (`gnss.kicad_sch`).
  **Position and heading are both required** -- the array reports bearing
  relative to its own frame, so a GNSS fix without heading gives a circle of
  possible tag locations, not a point. Do not drop the magnetometer as
  redundant. Absolute accuracy is sub-metre via host-side survey-in
  averaging, deliberately coarser than the 10-30 cm relative fix.

  The station sits in an **enclosure**, which settles ingress and
  weatherproofing -- don't reopen those. Two things a box does not fix, both
  still open: the enclosure **must pass RF**, because the BT840's BLE antenna
  is printed on the module and therefore inside it (a metal box kills the
  laptop link); and **most Li-Ion cells must not be charged below 0 degC**,
  which an unheated enclosure does nothing about -- the MCP73871 has a THERM
  NTC but it has not been sized for a cold-charge cutoff.
- **Channel 5 (6489.6 MHz) is chosen.** It sets antenna selection, cable-loss
  budget, and connector rating. Connectors on the UWB path must be SMA --
  U.FL/MMCX are rated only to 6 GHz and CH5 is above that. The wristband has
  no RF connectors at all -- the DWM3001C carries both antennas on-module.

## Hard rules

1. **Verify datasheet facts by reading the actual PDF.** Not from memory, not
   from a search-result summary, not from a distributor page. Several real
   bugs in this repo's history were caught only this way (a missing voltage
   regulator, a part number that doesn't exist, a mislabeled SOT-23-6, a
   WLCSP/QFN variant mixup). `pdftotext -layout file.pdf out.txt` then grep
   the result works well and is how the DW3000 facts in `docs/positioning.md`
   were established.

   **Try BOTH `pdftotext -layout` AND `pdftotext -raw` on any pin table.**
   This has now caused two near-misses and one wrong conclusion, so treat it
   as a rule rather than a tip. `-layout` scrambled DWM3001C Table 2, and it
   MANGLES DW3000 Table 2 outright -- rendering VDD1 as pin 24 "Ground return
   for VDD2", which is nonsense, when VDD1 is actually pin 29 and pin 24 is
   VSS2. `-raw` renders both correctly. `-layout` is still better for some
   numeric tables (DW3000 Table 5). **A table that looks scrambled is not
   evidence the data is unavailable -- it is evidence you used the wrong
   mode.** Always sanity-check known rows (GND/VDD positions, pin count,
   whether any description is self-contradictory) before trusting either.
2. **Cite the source inline** when you record a fact -- document name,
   revision, and section/table/figure number. Match the existing style in
   `docs/decisions.md` and the `*_notes.md` files.
3. **Flag uncertainty instead of smoothing it over.** If a dimension or value
   didn't cleanly resolve, say so and name the artifact `*_PLACEHOLDER`
   (footprints) or mark it as an estimate in the notes. This repo would
   rather carry an honest "verify before fab" than a confident guess.
4. **Never invent a part number.** If you can't find the exact SKU in the
   manufacturer's own catalog, that's a finding to report, not a gap to fill.
5. **Don't commit to `main`.** Branch per sheet/feature and open a PR. See
   `CONTRIBUTING.md`.

## KiCad mechanics

**KiCad may not be installed on the machine you're running on.** Check for
`kicad-cli` before promising to verify anything; if it's absent, say so
rather than claiming an edit is ERC-clean.

- `kicad-cli sch erc <board>.kicad_sch` / `kicad-cli pcb drc <board>.kicad_pcb`
  after any edit. Paths: Windows `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`
  (usually on PATH), macOS `/opt/homebrew/bin/kicad-cli` or inside
  `/Applications/KiCad/KiCad.app/Contents/MacOS/`, Linux on PATH.
- **Always run `kicad-cli` from a scratch directory, never from inside this
  repo.** It drops `.rpt` files in the working directory. This has already
  polluted a sibling repo once from a leftover `cd`.
- **A suspiciously clean ERC run is a red flag, not good news.** `kicad-cli`
  fails to load an entire file -- silently, reporting 0 components and 0
  violations -- if any cached symbol uses KiCad's `extends` mechanism (e.g.
  the stock `AO3401A extends TP0610T`). Both boards embed flattened,
  non-`extends` copies to work around this. If you add a part and ERC goes
  quiet, check this first.
- **Never edit files while a KiCad GUI has the project open.** A stale window
  saving over your edits already caused one near-miss on the bay station. A
  lock file at `<board>/~<board>.kicad_pro.lck` means a GUI holds it.
- **Indentation is literal tab characters, not spaces.** Match it.
- **Copy the format from a known-good file** -- one already in this repo or
  one of KiCad's bundled libraries -- rather than writing s-expressions from
  memory.
- Target **KiCad 10.0.5**. Files on disk are still 8.0 format; don't bump the
  format as a side effect of a content change.
- `pcbnew` Python bindings need KiCad's own bundled interpreter, not system
  Python: Windows `C:\Program Files\KiCad\10.0\bin\python.exe`, macOS
  `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.

## Where things go

- Part used on **both** boards -> `shared/`. One board only -> that board's
  `libs/`. Never point at a global/system KiCad library path; register
  everything in the project's own lib tables via `${KIPRJMOD}`-relative paths
  so it resolves for every contributor on every OS.
- Reference designators are unique **per board**, not across the repo.
- Standard passive size is **0603** for R/C/L.

## Keep these in sync when you change something

An edit is not done until the paper trail matches:

- `docs/decisions.md` -- any architecture/component call, with a one-line
  reason. Move items from Open to Resolved rather than deleting them.
- `<board>/libs/components.csv` -- the real BOM, with datasheet URL and a
  confidence note.
- `<board>/*_notes.md` -- per-sheet detail and math.
- `docs/passives-reference.md` -- if you touch passives around a chip.
- The board `README.md` and root `README.md` status tables.

When a sheet's in-schematic text note makes a claim ("not yet verified
against the datasheet"), and you then verify it, **update the note**. A stale
note is worse than no note.

## Style

Board and doc prose in this repo explains *why*, cites the source, and admits
what's unverified. Match that. Don't add breathless summaries, don't restate
the same fact in five files, and don't append a new "Update:" paragraph to a
doc when the right move is to rewrite the stale sentence.
