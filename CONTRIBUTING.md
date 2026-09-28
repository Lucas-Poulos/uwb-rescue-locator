# Contributing

## KiCad version

Everyone should use the **same major KiCad version**. The team standard is
**KiCad 10.0.5** -- see root `README.md` for install instructions.

Note the distinction: 10.0.5 is the *tool* everyone runs, but the files on
disk are still in **KiCad 8.0 format** (nobody has re-saved them under 10
yet, and they open and ERC cleanly as-is). Opening a project in the newer
version and saving bumps the file format for everyone else. That's a
one-way, zero-cost upgrade whenever the team wants it -- but do it as its own
commit with a clear message, never mixed into a feature change.

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

Both boards already have their sheet breakdown in place (7 sheets each -- see
each board's `README.md` for the current list and status). Prefer adding
components to an existing sheet over creating a new one; add a new sheet only
when a genuinely separate functional block appears.

When you do add one, create it from the KiCad GUI (Place > Sheet) rather than
hand-editing files, and keep the board-level `README.md` sheet table in sync.

## Shared vs. board-local libraries

- If a part is used on **both** boards (the DWM3000 UWB module is the
  obvious one), its symbol/footprint goes in `shared/`, not duplicated per
  board.
- Board-specific parts go in that board's `libs/` folder.
- Never point a footprint/symbol at a system/global KiCad library path --
  always add it to one of the project's own lib tables so it resolves the
  same way for every collaborator.

## Decisions

Component and architecture calls live in `docs/decisions.md` -- open ones at
the top, resolved ones below with their reasoning. Update it when a call gets
made, with a one-line reason, so we don't relitigate it later. Move items
from Open to Resolved rather than deleting them.

The biggest open cluster right now is the move from the DWM3000 module to a
discrete DW3210 on the bay station, which the TDoA scheme forces. If you're
picking up work, start there and in `docs/positioning.md`.

## Firmware

Firmware lives in this repo, alongside the boards, in `firmware/`. That's
deliberate: the pin map, the message formats in `firmware/common/`, and the
per-anchor calibration table are all shared between the hardware and the
code, and splitting them across two repos is how they drift apart. It also
means an agent reading this repo sees both halves at once.

A few things differ from the hardware side:

- **The KiCad caution about two people not editing the same file does not
  apply to source.** That rule exists because `.kicad_sch`/`.kicad_pcb` are
  large single-file blobs that merge badly. Normal parallel work on source
  files is fine.
- **Branch naming follows the same shape**: `firmware/<area>`, e.g.
  `firmware/dw3000-driver`, `firmware/calibration-tool`. Still no direct
  commits to `main`.
- **ERC/DRC is not your pre-PR gate** -- build the thing instead. Don't
  claim a firmware change is "ERC-clean"; that's a schematic check.
- **Never commit build output or an SDK tree.** `.gitignore` covers `build/`,
  west workspaces and `.venv`, but the underlying rule is that the SDK is
  fetched, not vendored. A PR that adds thousands of files is a mistake, not
  a big contribution.

Two open items gate most firmware work, and both are hardware calls rather
than coding ones:

1. **Toolchain** -- nRF5 SDK vs. Zephyr / nRF Connect SDK, one choice for
   both boards. Open in `docs/decisions.md`.
2. **Pin assignments don't exist yet.** No GPIO on either MCU is wired to a
   function in the schematic -- a netlist export shows every BT840 and
   DW3210 pin unconnected, and on the wristband only power, SWD, `RESET_N`,
   `VBAT_SENSE` and one button are tied. Don't guess them into firmware;
   raise them as decisions. `firmware/CLAUDE.md` explains why this
   particular shortcut is expensive.

## Working with an agent

If you're using Claude Code or a similar agent on this repo, `CLAUDE.md` at
the root holds the working rules (datasheet-verification discipline, the
`kicad-cli` gotchas, file-format conventions, and which docs have to stay in
sync). Keep it current -- it's the file that stops the same mistakes being
rediscovered.

Context is layered by directory: an agent working under `firmware/` picks up
`firmware/CLAUDE.md` in addition to the root file, so firmware sessions get
firmware rules without every schematic session paying for them. If a rule
only matters in one subtree, put it in that subtree's `CLAUDE.md` rather than
growing the root one.
