# Bay Station

The fixed reference station. Open `bay-station.kicad_pro` in KiCad.

## Scope

- **UWB anchors**: four DW3210 transceivers, all on this PCB sharing one
  38.4 MHz TCXO, in two distinct roles -- one **center** anchor (A0) that
  does two-way ranging with the wristband, and three **outer** anchors that
  measure TDoA against it. Range plus direction gives a 3D fix. The four
  **antennas** are remote, on ~1-2 m SMA coax runs to a rigid frame. Read
  `../docs/positioning.md` before touching anything in the anchor, clock,
  coax, or connector path.
- **Host MCU + links**: Nordic **nRF9151** SiP (U20, resolved 2026-11-17)
  -- drives the four DW3210s, reads the sensors, and has an LTE-M modem and
  GNSS built in. It has no Bluetooth, so the Fanstel **BT840** (U3,
  nRF52840) stays as a **UART BLE bridge** to a nearby laptop, which remains
  the primary link; LTE-M is optional (the station must work with no SIM).
  See `../docs/decisions.md`, "nRF9151 host redesign".
- **Georeferencing**: nRF9151 GNSS for position, IIS2MDC + IIS2DLPC for heading
  and tilt (`orientation.kicad_sch`).
- **BMS**: optimized for longevity rather than size, since this board isn't
  worn (contrast with the wristband's compromise-heavy BMS).

Target performance: **10-30 cm at ~10 m, on Channel 5 (6489.6 MHz)**.

> **Every sheet is wired against `../docs/net-contract.md`; layout has not
> started, and the board is not fab-ready.** The nRF9151, BT840 and TPS63802
> footprints now come from vendor files (2026-11-18; `libs/README.md`). Still
> blocking fab: the TCXO, SMA-launch, MAX17048 and DNP eSIM footprints are
> placeholders, FB1-FB4's land pattern is unverified, and all Nordic facts
> were read from Nordic's HTML pages, not the PDFs. Full list:
> `../docs/decisions.md`, Open.
>
> **Array calibration is a deliverable, not a bring-up nicety** -- the design
> does not meet its accuracy target without it. See `../docs/decisions.md`.

## Status

Ten hierarchical sheets, all registered in `bay-station.kicad_pro`'s
`sheets` list and wired into `bay-station.kicad_sch` as sheet symbols. Each
sheet's detail, citations and bring-up tests live in its `*_notes.md`; this
table is the summary. Pins are assigned in one place:
`connectivity_notes.md` section 2.

| Sheet | Status | Contents | Notes |
|---|---|---|---|
| `power_bms` | **Wired** | Barrel jack + USB-C in (`+5V_IN`) -> MCP73871 power-path -> `+VSYS`; MAX17048 gauge on `I2C_SCL/SDA`; backup cell with AO3401A + TVS; THERM window sized (+1..+5 degC cold cutoff) | `power_bms_notes.md` |
| `regulation` | **Wired** | U8 TPS62A02 -> `+3V3`; U40 TPS63802 buck-boost -> `+VBAT_LTE` 3.59 V (nRF9151 VDD); `+3V3` sequenced >= 6 ms after it; UVLO 2.91 V; R300/R302 PPK2 break links | `regulation_notes.md` |
| `connectivity` | **Wired** | U20 nRF9151 + HDG decoupling; LTE (J10) and GNSS (J11, BGA524N6 LNA) on u.FL; nano-SIM + DNP eSIM; U3 BT840 bridge; I2C pull-ups R37/R38 3.3k, R39 2.2k | `connectivity_notes.md` |
| `uwb_array` | **Wired** | 4x DW3210 (U4 = A0 center, U5-U7 = A1-A3 outer), Fig 32 decoupling, per-anchor 0R links, SPI-mode-0 straps, pi-match pads, SMA J20-J23, XTO caps C28-C31, DNP A0 fallback crystal | `uwb_array_notes.md` |
| `clock_dist` | **Wired** | Proposed RPT1490LN TCXO -> LMK1C1104 -> 22R -> 2200 pF -> `UWB_CLK0..3`; no `TCXO_EN` | `clock_dist_notes.md` |
| `orientation` (was `gnss`) | **Wired** | IIS2MDC (U10, 0x1E) + IIS2DLPC (U11, 0x19) on `+3V3_SNS`; MAX-M10S removed | sheet notes; `components.csv` |
| `indicators` | **Wired** | D4/D5 (STAT1/STAT2, from `+VSYS`), D6 (PG, from `+5V_IN`), D7 `LED_SYS`, D400 `LED_LTE`, D401 `LED_LINK` | `../docs/decisions.md`, LED drive rails |
| `programming_debug` | **Wired** | J3 nRF9151 SWD, J32 BT840 SWD, DNP Tag-Connect J34/J35, J33 debug UART, SW2/SW11 resets, SW12 `BTN_USER` | `programming_debug_notes.md` |
| `testpoints` | **Wired** | 64 pads on every net-contract net, GND spring pairs; clock pads behind DNP 0R | `../docs/verification-plan.md`, Test-point index |
| `mechanical` | Placement only | H1-H4 (M3, NPTH), FID1-FID3 | grounding the holes is Open |

**ERC.** Each sheet owner ran `kicad-cli` ERC on the whole project during
the 2026-11-17 redesign and recorded before/after counts in
`handoff/*.md` (596 before; 0-10 per redesigned sheet afterwards, the rest
cross-sheet items waiting on the other branches). A
whole-project count for the merged branch has not been recorded here yet --
re-run it before quoting a number. U8's lib_id was renamed to `TPS62A02PDDC`
on 2026-11-18, so its warning is now a `lib_symbol_mismatch`
(`../docs/decisions.md`).

### The PCB

`bay-station.kicad_pcb` now carries the **4-layer controlled-impedance
stackup** (F.Cu / prepreg 254um / In1.Cu / core 400um / In2.Cu / prepreg
254um / B.Cu, 35um copper throughout, 1.048mm finished), taken from DW3000
Datasheet v1.3 Section 7.3.2 Figure 35. Until 2026-09-23 the file was an
empty 2-layer default stub, which contradicted a decision the docs had
already recorded as settled. The rest of Section 7.3 -- 50 ohm RF1/RF2,
ground cutouts under each DW3210, group separation -- is written as a note
on the board's `Cmts.User` layer, where layout will actually see it.

The dielectric numbers (er 4.5, tan d 0.02) are KiCad's FR4 defaults, not
datasheet values. Controlled impedance means the fab's stackup wins.

**Nothing else is on the board.** No footprints are placed and no outline is
drawn. With the sheets now wired there is a real netlist to import, so the
blocker has moved from wiring to the footprints below.

Every part now has a footprint (U3, U20, U40 and FB1-FB4 were assigned
2026-11-18). Placeholders that must be replaced before fab: **U30** (Rakon
TCXO), **J20-J23** (SMA launch, needs EM simulation), **U23** (DNP eSIM),
the MAX17048 fuel gauge. FB1-FB4 use stock 0201 pads pending Murata's land table.
See `../docs/decisions.md`.

### Sheet detail

Moved into the per-sheet notes files listed in the Status table, which are
kept current with each change; the earlier prose summaries here had gone
stale (they still described the BT840 as host). Two pieces of history worth
keeping in view:

- `programming_debug` was rebuilt for Nordic on 2026-09-19, deleting the
  ESP32-S3 boot straps, EN RC, BOOT button and the data USB-C -- which is why
  the board has a single, power-only USB-C (`J2`).
- `uwb_array` kept R10-R17 (GPIO5/6 SPI-mode straps) and R25-R28 (IRQ
  pull-downs, Qorvo Figure 11) through the module-to-IC move, because both
  are DW3000-core requirements; the module-era C8-C19 were deleted.

### Next up

1. **Replace the nRF9151 footprint** with Nordic's real land pattern and
   re-verify the Nordic facts against the PDFs.
2. **Import the BT840 footprint**; resolve U40, FB1-FB4, TCXO and SMA
   footprints; design the SMA launch.
3. **Re-run whole-project ERC** on the merged branch and record it above.
4. **Draw the board outline** -- no dimensions have been decided anywhere,
   so this is a decision to make rather than a task to do.
5. Work through the Open items in `../docs/decisions.md` -- TCXO
   availability, GNSS pre-filter, cable loss, array
   calibration. (No FCC/CE work: university prototype, not certified.)

## Libraries

- `libs/` -- bay-station-only symbols/footprints
- `../shared/` -- parts used on both boards (registered via
  `fp-lib-table`/`sym-lib-table`)
