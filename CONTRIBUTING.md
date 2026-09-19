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

## Working with an agent

If you're using Claude Code or a similar agent on this repo, `CLAUDE.md` at
the root holds the working rules (datasheet-verification discipline, the
`kicad-cli` gotchas, file-format conventions, and which docs have to stay in
sync). Keep it current -- it's the file that stops the same mistakes being
rediscovered.
