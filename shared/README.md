# Shared libraries

Symbols, footprints, and 3D models used on **both** the wristband and the bay
station -- the clearest example is whatever UWB IC/module gets chosen, since
it appears on both boards.

- `symbols/uwb_rescue_locator_shared.kicad_sym`
- `footprints/uwb_rescue_locator_shared.pretty/`
- `3dmodels/`

Both board projects register this library in their `fp-lib-table` /
`sym-lib-table` under the nickname `uwb_rescue_locator_shared`, referenced
via `${KIPRJMOD}/../shared/...` so it resolves correctly no matter where the
repo is cloned.

If a part is only used on one board, put it in that board's own `libs/`
folder instead -- don't add it here.

## Components

| Reference/Role | Part | Symbol lib:name | Footprint lib:name | Datasheet URL | Notes/confidence |
|---|---|---|---|---|---|
| UWB transceiver module | Qorvo/Decawave DWM3000 | `uwb_rescue_locator_shared:DWM3000` | `uwb_rescue_locator_shared:DWM3000_PLACEHOLDER` | https://download.mikroe.com/documents/datasheets/DWM3000_datasheet.pdf | Pin table and package size are fully verified against the real Qorvo DWM3000 Data Sheet Rev B (May 2021), Table 2 and Figure 8. Footprint is a **PLACEHOLDER**: body size (13x23x2.9mm) and pad layout/count (24 pins: 8 left edge + 8 right edge + 8 bottom edge, none on top) are real/confirmed, but individual pad width/height are estimates, not independently measured off the datasheet's Figure 14 land-pattern drawing -- see below. |

### Part number resolved: DWM3000 (not DWM3000C, which doesn't exist)

While sourcing this part, no exact "DWM3000C" SKU turned up in Qorvo's
current catalog (checked their product pages and several distributor
listings) -- an earlier version of this doc used that name by mistake.
Qorvo's real lineup has two different, non-interchangeable parts that
could have been meant:

- **DWM3000** (confirmed choice) -- a bare UWB transceiver module (no
  onboard host MCU), 24-pin 1.4mm-pitch side-castellated package,
  23x13x2.9mm, based on the DW3110 IC. Architecturally consistent with
  this project, since the wristband already has a separate NINA-B111 BLE
  MCU to act as the SPI host.
- **DWM3001C** (not used) -- a larger, different module that additionally
  integrates its own nRF52833 BLE SoC, a planar antenna, and an
  accelerometer. Using this alongside a separate NINA-B111 would be
  redundant (two BLE radios on one board) and it's a different footprint
  entirely.

All data in the `DWM3000` symbol (pin names/numbers, package dimensions)
was pulled from the real **Qorvo DWM3000 Data Sheet Rev B, May 2021**.
See `../docs/decisions.md`, where this is now marked resolved.

### Footprint verification detail

The datasheet's own Figure 14 "Module Land Pattern" gives some real,
legible numbers (overall width 13.00mm, overall land-pattern span 22.7mm,
1.00mm gap from the top edge, a 2.50mm side-pad dimension, and
2.45mm/1.40mm/1.43mm bottom-row spacing figures) but one key number doesn't
cleanly resolve: the side castellation column's stated total length
(12.925mm for 8 pads) doesn't divide out evenly against the product
brief's own stated "1.4mm pitch side castellation" spec for 8 pins. Rather
than silently pick one interpretation and present it as exact, this
footprint is named `DWM3000_PLACEHOLDER` per this project's convention
(matching how the sibling wristband-alarm project flagged its own
uncertain footprints, e.g. `PUIAudio_SMT-1341-TW-HT-R_PLACEHOLDER`) --
body outline and pad count/layout are trustworthy, individual pad
width/height are reasonable estimates only. Verify against the real
Figure 14 drawing (page 22 of the datasheet above) before fab.

### PCB layout requirement: antenna keep-out area (not yet actioned -- PCB layout hasn't started)

DWM3000 has its own onboard ceramic UWB antenna (confirmed -- no external
antenna/matching network needed for the UWB radio itself, unlike NINA-B111's
BLE antenna). The datasheet's Section 6.1 "Application Board Layout
Guidelines" (Figure 10, "Application Board Keep-Out Areas") is explicit:
ground copper should be flooded everywhere on the application board *except*
in a keep-out zone directly around the antenna, where there must be no metal
on either side, above, or below (e.g. don't place the battery under the
antenna) -- flooding metal there degrades RF performance. The keep-out
distance `d` should ideally be **10mm** from the antenna edge for the most
vertically-polarized radiation pattern; increasing `d` beyond 10mm reduces
that polarization. This applies on **both boards**, at all 5 DWM3000
placements (wristband + 4 bay-station anchors). Nothing to do about this
yet since PCB layout hasn't started on either board -- flagging it here now
so it isn't rediscovered/relearned when that phase begins.
