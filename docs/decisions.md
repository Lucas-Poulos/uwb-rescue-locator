# Decision log

Open calls first, resolved calls below with the reasoning, so we don't
relitigate them. Keep this updated as the team decides things.

## Open

- **Bay station uplink backend**: what protocol/service position data gets
  sent to.
- **Anchor placement / enclosure** for the bay station's 4 UWB anchors
  (fixed relative geometry matters for triangulation accuracy).
- **PCB layer count / stackup** for each board -- not set yet; likely needs
  4-layer on at least the wristband for RF (UWB + BLE) given board size
  constraints, but that's a layout-phase call.
- **DWM3000 antenna keep-out area** (all 5 placements, both boards) --
  confirmed real requirement from the datasheet (Section 6.1/Figure 10): no
  metal above/below/beside the antenna within ~10mm for best RF performance.
  Nothing actionable until PCB layout starts on either board -- see
  `shared/README.md` for the full detail.
- **UWB antenna matching network values** on both boards -- the wristband's
  BLE antenna is now chosen (see Resolved), with a DNP-placeholder 0603 L/C
  network reserved on `wristband/antenna.kicad_sch`, but actual values
  depend on prototype RF tuning, set at layout/bring-up time.
- **Bay station: two USB-C connectors instead of one.** Building the
  programming/flashing sheet surfaced that the existing power-input USB-C
  (`power_bms.kicad_sch`, power-only, no D+/D-) can't also be used to flash
  the ESP32-S3 over native USB, so a second, data-capable USB-C was added on
  `programming_debug.kicad_sch` instead of consolidating into one connector.
  Revisit whether one connector should be swapped for a data-capable variant
  instead of running two.
- **Bay station L1 (buck converter inductor) footprint**: the specific part
  chosen (Coilcraft XGL3520-102MEC) has no matching footprint in KiCad's
  default libraries -- pick/verify a real footprint at BOM time (see
  `bay-station/regulation_notes.md`).

## Resolved

- **Wristband MCU/radio**: u-blox NINA-B111 (specific NINA-B1-series variant
  with external-antenna pin, no on-module antenna). Symbol + real footprint
  (sourced from u-blox's own official Eagle library) added in
  `wristband/libs/`. Datasheet: UBX-15019243-R15.
- **UWB IC/module**: Qorvo/Decawave **DWM3000** (bare UWB transceiver module,
  no onboard host MCU -- the NINA-B111 is the SPI host on the wristband; the
  bay station's 4 anchors use it the same way against the ESP32-S3).
  Note: an earlier pass of this doc and the initial library work briefly
  used the incorrect name "DWM3000C", which isn't a real Qorvo part number --
  see `shared/README.md` for the full correction writeup. Symbol added to
  `shared/symbols/` (fully verified against Qorvo DWM3000 Data Sheet Rev B,
  May 2021); footprint is a flagged `DWM3000_PLACEHOLDER` pending one
  land-pattern dimension that didn't cleanly resolve from the datasheet
  figure -- verify before fab.
- **Wristband BMS**: MCP73831 (LiPo linear charger) + DW01A/FS8205
  protection pair -- same proven pattern as the team's other wristband
  project (alarm-band). Symbols added to `wristband/libs/`; battery
  connector and USB-C charging receptacle reuse KiCad's own default
  libraries (no custom parts needed -- see `wristband/libs/components.csv`).
- **Bay station connectivity**: ESP32-S3-WROOM-1 module (built-in BLE +
  2.4GHz WiFi, single part instead of discrete BLE+WiFi ICs). Note: WiFi is
  2.4GHz only, not dual-band 5GHz -- revisit if that turns out to matter.
- **Bay station BMS**: MCP73871 (charge + power-path management, so the
  station can run continuously on external power while its battery
  tops off in the background) + MAX17048 fuel gauge (same part already
  proven on alarm-band).
- **Repo structure**: monorepo, two KiCad projects (`wristband/`,
  `bay-station/`) + a `shared/` library folder. Reason: KiCad has no native
  multi-board project, and a monorepo keeps shared parts/docs/history in one
  place for a small team.
- **Voltage regulation** (a gap found by checking real datasheets: NINA-B111
  abs-max VCC is 3.9V, DWM3000 abs-max VDD3V3 is 4.0V, but a charged LiPo
  hits 4.2V -- both ICs were about to be fed straight off the unregulated
  battery/system rail with no margin against permanent damage):
  - Wristband: **Microchip MCP1700T-3302E/TT** LDO (fixed 3.3V, low-Iq),
    `wristband/regulation.kicad_sch`. Current budget: NINA-B111 (~12mA) +
    DWM3000 (~55mA) vs. the part's 250mA rating, ~3.7x headroom.
  - Bay station: **TI TPS62A02PDDCR** buck converter (2A, single-cell-Li-Ion
    input range), `bay-station/regulation.kicad_sch`. Current budget:
    ESP32-S3-WROOM-1 (~355mA peak TX) + 4x DWM3000 (~55mA each) = ~575mA
    vs. 2A rating, ~3.5x headroom.
  - Both sheets are placement-only (not wired) like everything else at this
    stage -- see each board's `regulation_notes.md`.
- **Wristband antenna**: ProAnt InSide-2400 patch antenna, pulled from
  u-blox's own NINA-B1 series approved-antenna list (Section 7.2) --
  chosen since it's the one entry meant for mounting inside a plastic
  enclosure (the rest are rigid external monopoles). U.FL connector,
  `wristband/antenna.kicad_sch`. (DWM3000 needs no external antenna -- it
  has its own onboard ceramic antenna, confirmed in its datasheet.)
- **DWM3000 GPIO5/GPIO6 SPI-mode strapping**: both ICs' power-up sequence
  requires these sampled at boot (per Qorvo's own timing diagrams) --
  10k pull-downs added per instance (`wristband/radio_mcu.kicad_sch`;
  `bay-station/uwb_anchors.kicad_sch` x4, one set per anchor).
- **ESP32-S3-WROOM-1 boot-strapping + programming**: pull resistors on
  GPIO0/3/45/46 per Espressif's real hardware design guidelines, an EN
  RC-delay network, BOOT/RESET buttons, and a native-USB flashing interface
  -- `bay-station/programming_debug.kicad_sch`. Surfaced a real
  inconsistency in doing so -- see the "two USB-C connectors" open item
  above.
- **NINA-B111 programming**: standard 2x5 1.27mm ARM Cortex Debug SWD
  header, `wristband/programming_debug.kicad_sch`.
- **KiCad version**: team standardizes on **KiCad 10.0.5** (current stable;
  supersedes an earlier, since-corrected plan to target 9.x). Files on disk
  are still KiCad 8.0 format for now (nobody's re-saved them under 10 yet) --
  re-checked and confirmed clean under 10.0.5 via `kicad-cli` on 2026-08-14.
  See root `README.md`'s Toolchain section.
- **Passives audit against every chip's real reference design**: compiled
  in `docs/passives-reference.md`. Found and fixed one real gap (100k
  IRQ/GPIO8 pulldowns were missing on all 5 DWM3000 instances, per Qorvo's
  own Figure 11 -- added as R9 on the wristband, R25-R28 on the bay
  station). Also documented, not changed: DWM3000's placed decoupling caps
  exceed what Qorvo's own minimal application circuit shows (kept as
  reasonable conservative practice), and its GPIO5/6 external strap
  resistors are redundant with the chip's own internal default pulls (kept
  deliberately for tighter timing margin).
