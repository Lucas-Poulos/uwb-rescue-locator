# Wristband

The worn tag. Open `wristband.kicad_pro` in KiCad.

## Scope

- **MCU/radio**: u-blox NINA-B1 (confirmed)
- **UWB IC/module**: TBD -- see `../docs/decisions.md`. Once chosen, its
  symbol/footprint go in `../shared/`, not here, since the bay station uses
  it too.
- **BMS**: sized for "just enough" runtime to make core functionality work --
  size/weight compromises take priority over battery life here (contrast
  with the bay station, which optimizes for longevity instead).

## Status

First hierarchical sheet added: **`power_bms.kicad_sch`** ("Power BMS"),
wired into `wristband.kicad_sch` as a sheet symbol and registered in
`wristband.kicad_pro`'s `sheets` list. It covers the wristband's complete
battery/charging/protection chain:

- 2-pin JST-PH battery input (`BT1`)
- P-MOSFET (AO3401A) reverse-battery-polarity "ideal diode" protection (`Q1`,
  `R1`)
- Battery-rail TVS (ESD5B5.0ST1G) (`D1`)
- DW01A + FS8205A single-cell overcharge/overdischarge/overcurrent
  protection, wired per Fortune Semiconductor's own DW01A typical
  application circuit (`U1`, `Q2`, `R2`, `R3`, `C1`)
- MCP73831 Li-Po charger with a USB-C (power-only) input, PROG resistor sized
  for ~147mA charge current, and datasheet-recommended input/output caps
  (`U2`, `J1`, `R4`, `C2`, `C3`, `R5`, `R6`)
- Bulk/bypass decoupling on the protected `VBAT` output rail (`C4`, `C5`) --
  see `power_bms_notes.md` for why NINA-B111/DWM3000 themselves (and their
  own per-IC decoupling) are deferred to a future `radio_mcu` sheet instead
  of being placed here.

No wires are drawn -- net identity is carried entirely by global labels
placed exactly on top of each pin, matching the sibling wristband-alarm
project's convention. `kicad-cli sch erc` on the whole project reports
0 errors (1 harmless, documented warning -- see notes file). Full
component-by-component documentation, datasheet citations, and design-choice
rationale (PROG resistor math, TVS/MOSFET part selection, etc.) is in
`power_bms_notes.md`.

Second and third hierarchical sheets added: **`radio_mcu.kicad_sch`** ("Radio
MCU") and **`mechanical.kicad_sch`** ("Mechanical"), both wired into
`wristband.kicad_sch` as sheet symbols and registered in
`wristband.kicad_pro`'s `sheets` list. Both are **placement-only** passes --
components are instantiated and laid out for visual organization, but nothing
is wired yet (no drawn wires, no global labels/net identity). `kicad-cli sch
erc` therefore reports the expected pile of "pin not connected" / "input pin
not driven" warnings on these two sheets only; the existing `Power BMS`
sheet's own ERC-clean result is unchanged.

- `radio_mcu.kicad_sch`: `wristband:NINA-B111` BLE MCU (`U3`) and
  `uwb_rescue_locator_shared:DWM3000` UWB transceiver module (`U4`), each with
  generic 0603 100nF decoupling capacitors placed near their power pins
  (`C6`/`C7` near NINA-B111's `VCC`/`VCC_IO`; `C8`-`C10` near DWM3000's
  `VDD1`/`VDD3V3`/`VDD3V3`) -- values are a standard placeholder default, not
  yet cross-checked against either part's exact application-circuit numbers.
- `mechanical.kicad_sch`: 4x M2 mounting holes (`H1`-`H4`), KiCad's stock
  unconnected `Mechanical:MountingHole` symbol with
  `MountingHole:MountingHole_2.2mm_M2` footprint, one per PCB corner.

Still TBD: wiring both of the above (nets, decoupling values verified against
datasheets, SPI/GPIO hookup between NINA-B111 and DWM3000), plus any other
sheets from root `CONTRIBUTING.md`'s suggested breakdown. Add them from the
KiCad GUI rather than hand-editing files where practical, and keep this
section in sync as sheets get added.

## Libraries

- `libs/` -- wristband-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
