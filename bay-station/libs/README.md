# Bay-station-only libraries

Symbols/footprints used **only** on the bay station board. If a part is also
used on the wristband it belongs in `../../shared/` instead -- though as of
2026-09-19 nothing is actually shared between the boards any more, so in
practice every bay-station part lives here or in a KiCad default library.
See `../../shared/README.md`.

See `components.csv` for the full part-by-part mapping (part -> symbol ->
footprint -> datasheet URL -> verification notes).

## What's in here

```
bay_station.kicad_sym   # 10 hand-authored symbols: DW3210, BT840, MAX17048G+T10, nRF9151,
                        #   BGA524N6, TPS7A0228PDBVR, eSIM_MFF2, TPS63802, LMK1C1104PW, RPT1490LN
bay_station.pretty/     # 9 footprints -- 4 still *_PLACEHOLDER (MAX17048 TDFN8, Rakon RPT1490LN,
                        #   Linx SMA edge launch, eSIM MFF2). Built from vendor files 2026-11-18:
                        #   Nordic_nRF9151_LGA-113 (Nordic DK PcbDoc), Fanstel_BT840_Module
                        #   (Fanstel BT840.lbr), TI_DLA0010A (TI rendered land-pattern page);
                        #   also Infineon_TSNP-6-2 (BGA524N6), verified
sym-lib-table           # project-local library registration (symbols) -- not touched here
fp-lib-table            # project-local library registration (footprints) -- not touched here
components.csv          # BOM -> symbol/footprint mapping + verification notes
```

Everything else this board needs -- the
MCP73871 charge-management IC, the DC barrel jack, USB-C receptacle, battery
connector/holder, protection diodes, LEDs, and passives -- matched something
already in KiCad's own bundled default libraries (after checking pin-by-pin
against the real datasheets), so nothing extra for those was added here. See
`components.csv` for exactly which `library:part` to use for each, and the
"What I found" table below for the verification details.

## Fix applied to the library file wrapper (inherited from before this task)

`bay_station.kicad_sym` started out as an empty stub using `(kicad_sym ...)`
as the root element, which is **not valid** -- real KiCad 8 symbol libraries
use `(kicad_symbol_lib ...)`. This was already corrected before this task
started (the sibling wristband project's `README.md` flagged the same bug
and fixed it there too); confirmed still correct here via
`kicad-cli sym upgrade` (see Validation below).

## Verification pass (done against real datasheets, not just search snippets)

Every part below was checked against a primary-source datasheet PDF --
downloaded and read directly (pin tables/diagrams), not taken from
search-result summaries or secondary "pinout" blog pages.

| Part | What I found | What I did |
|---|---|---|
| **ESP32-S3-WROOM-1** *(historical -- superseded by the Fanstel BT840, see `../../docs/decisions.md`)* | Went in assuming a 44-pin module per the task brief. The real Espressif datasheet v1.8 (Table 3-1, Section 3 "Pin Definitions") says the module has **41 pins**, and KiCad's own bundled `RF_Module:ESP32-S3-WROOM-1` symbol already matches all 41 pin names/numbers exactly, including the two footnoted Octal-PSRAM-shared pins and both GND/EPAD pins. | Reused KiCad's default symbol + footprint unmodified after the full pin-by-pin check. Chose the plain (non-`-U`) on-board-antenna variant over `ESP32-S3-WROOM-1U` since the bay station is a fixed unit with room for the on-board PCB antenna and no need for an external one. |
| **MCP73871** | Assumed we'd need to hand-author this (QFN-20, no obvious default). KiCad's `Battery_Management.kicad_sym` already has a full `MCP73871` symbol. | Checked its 21 pin assignments (20 leads + EP) against the real Microchip datasheet DS20002090E page 2 pinout diagram -- all match exactly. Its assigned default footprint (`Package_DFN_QFN:QFN-20-1EP_4x4mm_P0.5mm_EP2.5x2.5mm`) uses a conservative EP size (2.5x2.5mm) versus Microchip's own nominal EP dimension (2.70x2.70mm, range 2.60-2.80mm per the datasheet's mechanical table) -- not wrong, just conservative; `Package_DFN_QFN:QFN-20-1EP_4x4mm_P0.5mm_EP2.7x2.7mm` (also a KiCad default) is available if an exact-nominal match is preferred. Reused as-is, not duplicated. |
| **MAX17048** | No KiCad default symbol exists anywhere (checked `Battery_Management.kicad_sym` and others). Also discovered it ships in two very different packages. | Hand-authored `MAX17048G+T10` (the 8-pin **TDFN-EP**, 2x2mm variant) after reading the real Maxim/ADI datasheet 19-6171 Rev 2 (8/12), page 6 "Pin/Bump Configurations"/"Pin/Bump Descriptions" tables, which show both TDFN-pin and WLP-bump numbering side by side. Deliberately avoided the alternate **WLP** package (`MAX17048X+T10`, 0.9x1.7mm, 8-bump) confirmed on datasheet page 18's Ordering Information table -- WLP is not practical to hand-solder/rework on a bench-built board. Noteworthy pin nuance carried into the symbol description: pin 2 (CELL) is explicitly "Not internally connected" on the single-cell MAX17048 (it's only wired up on the dual-cell MAX17049), and pin 3 (VDD) does double duty as both the power input *and* the actual cell-voltage-sense input for the single-cell part. |

## PLACEHOLDER flag: MAX17048 footprint

`MAX17048_TDFN8-EP_PLACEHOLDER` is flagged the same way the shared
`DWM3000_PLACEHOLDER` footprint is flagged, and for the same category of
reason: the **body size (2.0x2.0mm) and pin arrangement** (4 pins along the
bottom edge, 4 along the top edge, per the real Pin/Bump Configurations
diagram) are real and confirmed from the primary datasheet. The **individual
terminal-pad and exposed-pad dimensions**, however, are industry-typical
estimates for a TDFN-8 2x2mm 0.5mm-pitch part, not Maxim's own numbers --
Maxim's package-outline PDF (`21-0168`) and land-pattern PDF (`90-0065`) were
both found at the correct `analog.com/media/en/package-pcb-resources/` URLs
(cited directly in the datasheet's own "Package Information" table on page
18) but **timed out on every fetch attempt** (5+ tries across two tool
calls), so their exact dimension tables could not be read. Verify against
those two documents -- or against Maxim/ADI's own KiCad or Ultra Librarian
footprint, if one is published -- before sending this board to fab.

## Confidence summary

| Status | Parts |
|---|---|
| **Hand-authored, fully verified pinout against a real datasheet table** | `MAX17048G+T10` |
| **Hand-authored footprint, real body size + pin arrangement, PLACEHOLDER pad geometry** | `MAX17048_TDFN8-EP_PLACEHOLDER` |
| **Reused unmodified from KiCad's own default libraries, pin-by-pin verified against the real datasheet** | ~~`ESP32-S3-WROOM-1`~~ (superseded by BT840), `MCP73871` (symbol; footprint reused as-is, slightly conservative EP size noted above) |
| **Reused unmodified from KiCad's own default libraries (generic parts, not IC-pinout-sensitive)** | `Barrel_Jack` + CUI PJ-063AH footprint, `USB_C_Receptacle_PowerOnly_6P` + GCT USB4125 footprint, `D_Schottky` + SMA, `D_TVS` + SOD-523, `Battery_Cell` + JST-PH or 18650 holder, `LED` + 0805, `R`/`C`/`Thermistor_NTC` |
| **Hand-authored 2026-09-19, all pins from the real datasheet via `pdftotext -raw`** | `DW3210` (40 pins, DW3000 Datasheet v1.3 Table 2 -- NOTE `-layout` mangles that table), `BT840` (65 pins, Fanstel Ver 1.15 Pin Function table) |
| **Footprints built from vendor files, 2026-11-18** | `Fanstel_BT840_Module_14x16mm_16Cast_49LGA`, `Nordic_nRF9151_LGA-113_12.1x11.1mm_P0.5mm`, `TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm` -- see the next section |
| **Footprints still open** | `DW3210` uses `Qorvo_DW3210_QFN-40_5x5mm_P0.4mm_NoEP_PLACEHOLDER` (no exposed pad, DW3000 DS v1.1 Fig. 38; terminal pads are KiCad's generic QFN-40 values, not Qorvo's). FB1-FB4 use stock `Inductor_SMD:L_0201_0603Metric`; Murata's BLM03PG land table was not obtainable |

## Footprints built from vendor files (2026-11-18)

Rule: pad geometry only from a file the vendor publishes, confirmed against a
second artifact. SnapEDA / SnapMagic / Ultra Librarian / Flux were not used.
All three load in `pcbnew.FootprintLoad` and their pad names equal the symbol
pin numbers exactly (checked programmatically). Full reasoning is in
`../../docs/decisions.md`, Resolved, "Footprints from vendor sources".

| Footprint | Source | Cross-check |
|---|---|---|
| `Nordic_nRF9151_LGA-113_12.1x11.1mm_P0.5mm` | Nordic *nRF9151 DK Hardware files 1_0_0* (nordicsemi.com > nRF9151-DK > Download): `PCA10171.../Altium Designer files/400797.PcbDoc`, component `LGA50P1210X1110X130-113N` (M1), 270 degree placement undone | All 113 pad positions and sizes match flashes in the same ZIP's `400797.GTL` top-copper Gerber. GND/RSVD pad classes agree with the symbol. **Not compared with the PS land-pattern figure** (PDF unobtainable). Mask/paste not in the source. |
| `Fanstel_BT840_Module_14x16mm_16Cast_49LGA` | Fanstel `BT840.lbr` (Eagle), package `BT840`, 65 SMD pads, from fanstel.com/download-document | Reproduces the datasheet Ver 1.15 pp. 9-10 drawing dimensions (1.10 / 1.50 / 1.20 mm pitches, 3.625 / 2.25 mm F0-F3, 0.6 mm round pads, F6 square). Eagle names `P$A5` renamed to `A5`. |
| `TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm` | TI SLVSEU9D drawing 4223750/D "Example Board Layout" and "Example Stencil Design", read from the rendered PDF pages (the text layer drops the dimension leaders -- that is why the earlier version was an estimate) | Pin 8 is a 1.3 x 0.25 mm land with two 0.55 mm paste apertures; pins 1-5 0.6 x 0.25, pins 6/7/9/10 0.9 x 0.25. |

Not a footprint, but a lead: the nRF9151 DK ZIP also contains the DK's
unpopulated MFF2 eSIM footprint, which could replace `eSIM_MFF2_PLACEHOLDER`.

## Validation

- `bay_station.kicad_sym`: validated with
  `kicad-cli sym upgrade bay_station.kicad_sym -o <scratch-output>` from a
  scratch working directory (never inside a git repo, per project
  convention) -- printed `Symbol library was not updated`, confirming the
  file parsed successfully as a current-format (20231120) KiCad 8 symbol
  library.
- `MAX17048_TDFN8-EP_PLACEHOLDER.kicad_mod`: smoke-tested with
  `pcbnew.FootprintLoad(dir, name)` from a scratch working directory --
  loaded successfully with all 9 pads (1-8 + the EP as pad "9") present at
  their intended coordinates.
- `RF_Module:ESP32-S3-WROOM-1` and
  `Package_DFN_QFN:QFN-20-1EP_4x4mm_P0.5mm_EP2.5x2.5mm` (the two reused
  KiCad-default footprints referenced in `components.csv`) were also
  smoke-tested with `pcbnew.FootprintLoad()` directly from KiCad's own
  bundled footprint libraries, as an extra sanity check beyond just trusting
  the defaults -- both loaded (62 and 25 pads respectively).

## How to add this to your KiCad project

This is already wired up via this project's own `sym-lib-table` /
`fp-lib-table` (using `${KIPRJMOD}`-relative paths, so it works after
`git clone` on macOS or Windows without editing). If you're copying just
this folder into a different project, register `bay_station.kicad_sym` and
`bay_station.pretty/` the same way the sibling wristband project's `libs/`
folder documents.

## Licensing note

Parts reused from KiCad's official symbol/footprint libraries are CC-BY-SA
4.0; attribution: KiCad Contributors,
https://gitlab.com/kicad/libraries/kicad-symbols and kicad-footprints.
