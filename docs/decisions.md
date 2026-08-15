# Decision log

Open calls first, resolved calls below with the reasoning, so we don't
relitigate them. Keep this updated as the team decides things.

## Open

- **Bay station connectivity IC**: ESP32-S3-WROOM-1 module chosen (see
  Resolved), but exact BOM/footprint sourcing is pending -- being added now.
- **Bay station uplink backend**: what protocol/service position data gets
  sent to.
- **Bay station BMS**: MCP73871 (charge + power-path) + MAX17048 fuel gauge
  chosen (see Resolved), but exact battery chemistry/capacity and BOM
  sourcing is pending -- being added now.
- **Anchor placement / enclosure** for the bay station's 4 UWB anchors
  (fixed relative geometry matters for triangulation accuracy).
- **PCB layer count / stackup** for each board -- not set yet; likely needs
  4-layer on at least the wristband for RF (UWB + BLE) given board size
  constraints, but that's a layout-phase call.
- **UWB antenna matching network values** on both boards -- generic 0603
  inductor/cap footprints are reserved in the wristband BOM
  (`wristband/libs/components.csv`), but values depend on the final antenna
  choice and PCB layout, set at schematic/layout time.

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
- **Repo structure**: monorepo, two KiCad projects (`wristband/`,
  `bay-station/`) + a `shared/` library folder. Reason: KiCad has no native
  multi-board project, and a monorepo keeps shared parts/docs/history in one
  place for a small team.
- **KiCad version**: files are currently in KiCad 8.0 format (matches the
  installed toolchain as of 2026-08-14). Team wants to standardize on
  KiCad 9.x once everyone can upgrade -- see root `README.md`.
