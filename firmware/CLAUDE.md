# CLAUDE.md -- firmware

Rules for agents working anywhere under `firmware/`. The root `CLAUDE.md`
still applies and is not repeated here: read it first for what the project
*is*, the positioning scheme, and the hard rules on verifying datasheet
facts. This file covers only what changes when the work is code instead of
schematics.

## Read this before writing any code

**The hardware/firmware interface does not exist yet.** As of this writing
no GPIO on either MCU is assigned to a function in the schematic --
`kicad-cli sch export netlist` on `main` reports every BT840 and DW3210 pin
on an `unconnected-(...)` net, and on the wristband branch only power, GND,
SWD, `RESET_N`, `VBAT_SENSE` and one button are wired.

The practical consequence, and the single easiest way to waste a week here:

- **Do not invent pin assignments.** Not "SPI on P0.06-P0.08 as is
  conventional", not a mapping copied from the DWM3001CDK, not one inferred
  from a Qorvo example. Nobody has made these calls yet. Code written
  against a guessed pin map is worse than no code, because it looks
  finished.
- If you need a pin to write against, **that is a hardware decision to
  raise**, not a detail to fill in. Open it in `../docs/decisions.md` under
  Open, with the constraint that forces it (e.g. "four CS lines plus four
  IRQ lines, and the SPI instance must be one that can run at the DW3000's
  rated clock").
- Write against a named constant from `common/`, never a bare pin number,
  so that the day the schematic settles there is exactly one place to change.

This is the firmware analogue of the root file's "never invent a part
number", and it exists for the same reason.

## Verify, don't recall

Root rule 1 (verify datasheet facts from the actual PDF) applies unchanged to
register names, bit fields, timing parameters, and API signatures. Qorvo's
DW3000 register set and the nRF52 peripheral docs are both large enough that
plausible-sounding recall is frequently wrong.

- Cite document, revision, and section/table when you record a register or
  timing fact, same as the hardware side does.
- If you can't resolve something, name it `*_PLACEHOLDER` or mark it TODO
  with the open question -- don't smooth it over.
- The DW3000 driver most people land on
  ([br101/dw3000-decadriver-source](https://github.com/br101/dw3000-decadriver-source))
  was trimmed to a single DW3000 per board; this design has four. Restoring
  multi-instance support gates everything else on the station. See
  `README.md` in this directory.

## Precision is the product

The root file's arithmetic -- 1 ns is about 30 cm, and at the 1 m baseline
1 cm of differential path error is about 10 cm of position error at 10 m --
is a firmware constraint, not just a layout one. Anything on the timestamp
path is precision-critical:

- Don't reorder, buffer, or "tidy" timestamp capture and readback without
  saying what it does to the differential error.
- Keep raw device timestamp units end-to-end and convert once, at the point
  of use. Round-tripping through floating-point seconds midway is how
  resolution quietly disappears.
- The four anchors are **not interchangeable peers** (root file). A0 does
  two-way ranging; A1-A3 timestamp the same transmission. Any abstraction
  that makes them uniform is wrong.
- Per-anchor calibration offsets are a deliverable, not bring-up polish.
  Firmware must load a table rather than bake constants in.

## Toolchain

**Not yet decided** -- nRF5 SDK vs. Zephyr / nRF Connect SDK, one choice for
both boards (`README.md`, "Not yet decided"). Don't pick unilaterally by
committing a project skeleton that assumes one; raise it in
`../docs/decisions.md` and let the team settle it.

Whichever wins: **the SDK does not get vendored into this repo.** No `west`
workspace, no SDK tree, no toolchain tarball. `.gitignore` already excludes
the usual suspects (`build/`, `west.yml`-managed trees, `.venv`). If you
find yourself about to add several thousand files, stop.

## What this repo is not

Hardware rules that do **not** apply here, so you don't over-apply them:

- The "two people must not edit the same file" caution is about KiCad's
  single-blob `.kicad_sch`/`.kicad_pcb` files. Source files merge fine;
  normal parallel work is expected.
- The 0603-passives and refdes conventions are schematic conventions.
- `kicad-cli` ERC/DRC is not a firmware gate. Don't claim a firmware change
  is "ERC-clean".

## Keep these in sync

- `../docs/decisions.md` -- any protocol, toolchain, or on-device
  vs. server-side call, with a one-line reason.
- `README.md` in this directory -- the task breakdown, as items land.
- `common/` -- if a message format or constant changes, it changes for both
  boards at once. That shared definition is the main reason firmware lives
  in this repo rather than its own.

## Style

Same as the root file: explain *why*, cite the source, admit what's
unverified. No breathless summaries, no restating one fact in five files.
