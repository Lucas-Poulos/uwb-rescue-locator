# Wristband-only libraries

Symbols/footprints used **only** on the wristband board. If a part is also
used on the bay station (e.g. the UWB module), it belongs in `../../shared/`
instead -- that's why the DWM3000 UWB module is *not* in this folder even
though it's used on this board too; see `../../shared/README.md`.

See `components.csv` for the full part-by-part mapping (part -> symbol ->
footprint -> datasheet URL -> verification notes).

## What's in here

```
wristband.kicad_sym    # 7 hand-authored symbols: DWM3001C, TPS7A0233PDBVR, NINA-B400 (legacy), NINA-B111 (legacy), MCP73831-2-OT, DW01A, FS8205A
wristband.pretty/      # 3 custom footprints: DWM3001C_PLACEHOLDER, NINA-B400-55_PLACEHOLDER, NINA111-42 (real u-blox Eagle-lib pad data)
sym-lib-table          # project-local library registration (symbols) -- not touched here
fp-lib-table           # project-local library registration (footprints) -- not touched here
components.csv         # BOM -> symbol/footprint mapping + verification notes
```

The other parts needed for this board (LiPo battery connector, USB-C
charging receptacle, TVS diode, LEDs, passives) all matched something
already in KiCad's own bundled default libraries, so nothing extra for
those was added here -- see `components.csv` for exactly which
`library:part` to use for each.


## DWM3001C (added 2026-09-23)

`DWM3001C` is wristband-only -- the bay station still uses the bare `DWM3000`
from `../../shared/` -- so per this repo's own rule it lives here, not there.

Symbol: all 48 pins taken from the real **Qorvo DWM3001C Data Sheet Rev B,
May 2022**, Figure 1 "DWM3001C Pin Diagram" cross-checked against Table 2
"DWM3001C Pin Functions". Two datasheet inconsistencies are worth knowing:

- **Pin 18 (`VUSB`) is missing from Table 2 entirely** -- it appears only in
  Figure 1. The symbol includes it, typed as a power input.
- **Pins 44/45 are named inconsistently**: Table 2 calls them
  `DW_GPIO3`/`DW_GPIO2`, Figure 1 calls them `DW_GP3`/`DW_GP2`. The symbol
  uses the Figure 1 names, for consistency with `DW_GP0/1/5/6`.

**Footprint `DWM3001C_PLACEHOLDER` -- VERIFY BEFORE FAB.** Pin count and edge
assignment are confirmed (17 pads left edge pins 1-17, 14 bottom edge pins
18-31, 17 right edge pins 32-48, none on the top edge, which carries the
module's antenna). Body and land envelope come straight off Figures 4 and 5
(19.13 x 27.1 x 3.2mm body; 19.10 x 27.10mm land; 16.27mm inner column gap;
0.75mm side pad height; 17.77mm side column span; 1.00mm bottom-row pitch;
1.15mm bottom pad length). **Two dimensions did not resolve:**

1. The side-column pitch back-derives to **1.06375mm** from the 17.77mm span
   across 17 pads. That is not a round number and is unlikely to be Qorvo's
   intent.
2. Figure 5's "3.10" annotation implies the bottom pad row is offset toward
   the right rather than centred, and the individual bottom pad width is never
   dimensioned at all. The footprint assumes 0.60mm, centred.

Same PLACEHOLDER convention as `DWM3000_PLACEHOLDER` and
`NINA-B400-55_PLACEHOLDER`.


## TPS7A0233PDBVR (added 2026-09-23)

Hand-authored and **self-contained on purpose**. KiCad ships no TPS7A02 symbol
at all, and every TPS7A05 sibling in `Regulator_Linear` is `extends`-based
(`TPS7A0533PDBV extends LP5907MFX-1.2`), which this repo forbids in anything
`kicad-cli` must load. Pin numbers, names and types come from TI SBVS277C
Table 5-1 "Pin Functions: DQN, DBV" and Figure 5-2: `1=IN 2=GND 3=EN 4=NC
5=OUT`. Footprint is KiCad's stock `Package_TO_SOT_SMD:SOT-23-5` — **not a
placeholder**, nothing to verify before fab.

Watch the `EN` pin: it has an internal pulldown and the regulator is *disabled*
when EN floats, so it must be driven high. On this board it ties to `VBAT`.

## Fix applied to the library file wrapper

Both `wristband.kicad_sym` and the shared symbol library started out as an
empty stub using `(kicad_sym ...)` as the root element. That token is
**not valid** -- real KiCad 8 symbol libraries use `(kicad_symbol_lib ...)`
(confirmed empirically: `kicad-cli sym upgrade` fails to load a file that
starts with `(kicad_sym`, and succeeds once it's `(kicad_symbol_lib`; the
sibling wristband-alarm project's populated library also uses
`kicad_symbol_lib`). This was corrected in both files this task touched.
**Heads up:** `bay-station/libs/bay_station.kicad_sym` has the identical
`(kicad_sym` bug and was *not* touched (out of scope for this task) -- it
will need the same one-line fix before anyone can add real symbols there.

## Verification pass (done against real datasheets, not just search snippets)

Every symbol here was checked against a primary-source datasheet PDF --
downloaded and read directly (pin tables, and in NINA-B111's case, an
official Eagle CAD library file), not taken from search-result summaries
or secondary "pinout" blog pages. Two parts turned up real naming/pinout
gotchas worth knowing about before you order:

| Part | What I found | What I did |
|---|---|---|
| **u-blox NINA-B111** | The sibling wristband-alarm project deliberately shipped this MCU with *no* footprint, because a castellated-edge LGA land pattern is easy to get wrong by eyeballing a mechanical drawing. | Found u-blox's own official Eagle library (`github.com/u-blox/CadSoft-Eagle-Library`, `ubloxLib.lbr`, package `NINA111-42`) and converted its exact pad coordinates (all 42 pads: 30 signal + 12 EGP thermal sub-pads) into a real KiCad footprint, cross-checked against the datasheet's own Table 19 mechanical dimensions (body size and two independent pin pitches matched exactly). Confident enough to ship without a PLACEHOLDER suffix. |
| **FS8205A** | Fortune Semiconductor's own part *literally* named "FS8205A" turned out to be a TSSOP-8 part, not the commonly-sold SOT-23-6 dual MOSFET everyone means by that name. | Found Fortune Semiconductor's real SOT-23-6 part, which is actually called **FS8205** (no trailing "A"), Rev 1.9 datasheet -- and independently cross-checked its pin diagram against Fuxinsemi's own separate "FS8205A" SOT-23-6 datasheet. Both show the identical physical pin arrangement, so the pinout used here (1=S1, 2=D12, 3=S2, 4=G2, 5=D12, 6=G1) is solid even though the exact part-number provenance is messier than it looks. Symbol kept named `FS8205A` to match what's actually stocked/ordered under that name. |

Also worth knowing: KiCad's own default libraries already include
`Connector:USB_C_Receptacle_PowerOnly_6P` (symbol) and
`Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal`
(footprint). The sibling wristband-alarm project's README claims it had to
hand-author that symbol because nothing suitable existed -- that's not
the case in this KiCad 8.0.6 install, so this project reuses the default
instead of duplicating it.

## Confidence summary

| Status | Parts |
|---|---|
| **Hand-authored, fully verified against a real numbered pin diagram** | `NINA-B111`, `MCP73831-2-OT`, `DW01A`, `FS8205A` |
| **Hand-authored footprint, built from a real manufacturer CAD library (not a placeholder)** | `NINA111-42` |
| **Reused unmodified from KiCad's own default libraries** | `Battery_Cell` + JST-PH footprint, `USB_C_Receptacle_PowerOnly_6P` + GCT USB4125 footprint, `D_TVS` + SOD-523, `LED` + 0805, `R`/`C`/`L` + 0603 |

Nothing in this folder is a PLACEHOLDER -- the one part on this board that
*is* flagged uncertain (the UWB module footprint) lives in `../../shared/`
because it's shared with the bay station; see that folder's README for the
full writeup.

## How to add this to your KiCad project

This is already wired up via this project's own `sym-lib-table` /
`fp-lib-table` (using `${KIPRJMOD}`-relative paths, so it works after
`git clone` on macOS or Windows without editing). If you're copying just
this folder into a different project, register `wristband.kicad_sym` and
`wristband.pretty/` the same way the sibling wristband-alarm project's
`libs/` folder documents.

## Licensing note

Parts reused from KiCad's official symbol/footprint libraries are CC-BY-SA
4.0; attribution: KiCad Contributors,
https://gitlab.com/kicad/libraries/kicad-symbols and kicad-footprints.
