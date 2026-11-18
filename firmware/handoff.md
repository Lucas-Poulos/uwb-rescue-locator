# Firmware agent handoff (nRF9151 redesign)

Branch `worktree-agent-a8583ed9f321e13ef`, based on `redesign/nrf9151-host`
(fast-forwarded to pick up `docs/net-contract.md`). No `.kicad_*` file was
touched. Nothing was built with `west` -- no NCS in this environment.

## What changed

- `firmware/common/`: bridge protocol (COBS + CRC-16/CCITT-FALSE), raw
  measurement record, calibration table, host unit test (passes).
- `firmware/boards/`: HWMv2 boards `bay_station_lte` (nRF9151, secure + ns)
  and `bay_station_ble` (BT840). One `*_pins.h` per MCU, all `PIN_TBD`,
  `#error` until filled. `dtc`-parsed against stub SoC nodes only.
- `firmware/dts/bindings/`: `uwbrl,dw3210-anchor` (with `anchor-role`),
  `uwbrl,uwb-array-ctrl`, `uwbrl,bridge-ctrl`, `uwbrl,gpio-set`.
- `firmware/bay-station/nrf9151-app/`, `ble-bridge/`: NCS skeletons +
  `bringup` shell.
- Docs: `firmware/README.md`, `firmware/CLAUDE.md`,
  `firmware/bay-station/README.md`, `wristband/README.md`, `tools/README.md`,
  new `docs/verification-plan.md`.

## Proposed `docs/decisions.md` entries (ready to paste)

Move from Open -> Resolved:

```markdown
- **Toolchain: nRF Connect SDK v3.4.x (LTS) for every image** (resolved
  2026-11-17, replacing the open "nRF5 SDK vs. Zephyr / NCS" item). Forced by
  the nRF9151 host: Nordic describes the nRF5 SDK as the "Software
  development kit for the nRF52 Series and nRF51 Series SoCs", "in
  maintenance mode", and recommends NCS "for new projects" (nRF5 SDK product
  page); the nRF9151 download page lists only NCS. The BT840 bridge and the
  wristband's nRF52833 follow for one toolchain. Pin generated form is
  therefore a devicetree, filled from one `*_pins.h` per MCU under
  `firmware/boards/`. See `firmware/bay-station/README.md`, "Toolchain".
- **nRF9151 modem firmware pinned at 2.0.4 with NCS 3.4.x** (2026-11-17).
  Nordic's nRF9151 compatibility matrix (Table 1) lists mfw 2.0.4 against
  NCS 3.1.0-3.4.0 LTS. Modem FW is changed only together with NCS, logged in
  every test result, and checked by the app at boot via `AT+CGMR`.
```

New Resolved (firmware architecture calls; one-line reasons):

```markdown
- **nRF9151 <-> BT840 link is our own framed relay, not HCI-over-UART and
  not a transparent NUS pipe** (2026-11-17). COBS + CRC-16 frames at 1 Mbaud
  with RTS/CTS; the BT840 forwards end-to-end frames verbatim to/from BLE
  NUS. Keeps the BLE host stack off the chip running the modem and the UWB
  exchange (HCI would put it there), and unlike Nordic's connectivity
  bridge it carries message boundaries, integrity and link state. Defined
  in `firmware/common/include/uwbrl/bridge_proto.h`.
- **Raw timestamps end to end; laptop solve is authoritative** (2026-11-17).
  The station streams 40-bit DW3000 timestamps with the calibration
  table's CRC, not corrected values; the laptop applies calibration and
  solves. The station runs a quick-look solve only for LTE reports. Raw logs
  stay re-processable with a better calibration.
- **All antenna/cable delay lives in the calibration table; DW3000
  antenna-delay registers fixed (proposed 0) on all four anchors**
  (2026-11-17). Prevents a delay being applied twice. A0 absolute and
  A1-A3 relative delays are separate fields.
- **GNSS first, then LTE; steady state LTE in PSM with GNSS in idle windows;
  A-GNSS optional** (2026-11-17). `%XSYSTEMMODE=1,0,1,1` (LTE-M + GNSS, no
  NB-IoT -- revisit if coverage needs NB-IoT). GNSS priority mode only after
  repeated `NOT_ENOUGH_WINDOW_TIME` flags, per Nordic's GNSS API guidance.
- **nRF9151 serial instances: UARTE0 = DBG_UART, UARTE1 = bridge, TWIM2 =
  sensors, SPIM3 = UWB** (2026-11-17). All four instances used; TF-M log
  UART silenced in `/ns` builds because it defaults to UARTE1.
```

New Open:

```markdown
- **nRF9151 SPIM maximum clock -- verify.** Believed 8 Mbps (vs the
  nRF52840's 32 MHz SPIM3 the old design leaned on); the nRF9151 PS SPIM
  page could not be read past the 500 kbps rows. Affects A0 reply-delay
  budget and update rate, not precision. Check the PS FREQUENCY register
  table before the DW3210 driver work.
- **BLE link security level.** Nordic's own connectivity bridge ships its
  BLE NUS side off by default because it "is not encrypted or
  authenticated". Skeleton requests encryption (L2) with bonding; decide
  whether L4 (authenticated, needs passkey/OOB with no display) is
  required for a rescue deployment.
- **LTE-M service: endpoint, SIM/operator, data budget.** The laptop stays
  primary; the station must run fully with no SIM. Who receives LTE
  reports, and what rate, is undecided.
- **No rail-sense ADC net in the contract.** Firmware can only see rails
  indirectly (MAX17048 VCELL, modem `%XVBAT`). Consider a `VSYS_SENSE`
  divider net into an nRF9151 AIN if pins allow (net-contract change).
- **Multi-instance DW3000 driver approach.** The trimmed Qorvo 08.02.02 API
  is implicitly single-instance. Find the per-chip selector in the untrimmed
  source, else wrap and swap the global context under a mutex. Qorvo
  publishes no Zephyr/NCS support and no TDoA reference for this use
  (staff reply on the Qorvo forum, 2026-08-10).
```

## net-contract.md changes requested

- None required. Optional: `VSYS_SENSE` (analog, power_bms -> connectivity)
  -- see Open above.
- Note for the mcu agent: `RESET_BLE_N` must land on the BT840's nRESET pad
  (fixed by the nRF52840, not a free GPIO) -- confirm the pad from the
  Fanstel BT840 datasheet.

## For other owners

- **mcu / connectivity**: when `connectivity_notes.md` has the GPIO table,
  copy it into `firmware/boards/uwbrl/bay_station_lte/bay_station_lte_pins.h`
  and `.../bay_station_ble/bay_station_ble_pins.h`, flip the `*_ASSIGNED`
  flag. The instance table above means every nRF9151 serial instance is
  used -- no spare SPI/UART for anything added later.
- **io (orientation)**: firmware needs the LIS3MDL SDO/SA1 and LIS2DH SA0
  strap levels to set the I2C addresses in the pins header.
- **io (indicators)**: LED polarity (sink vs source) sets `LED_ACTIVE_FLAGS`.
- **coordinator**: fill "Test-point index" in `docs/verification-plan.md`
  from the io agent's table. Root `CLAUDE.md` / `README.md` /
  `docs/system-overview.md` / `docs/positioning.md` still say BT840 host,
  MAX-M10S and "no internet uplink" -- not edited here (not mine).

## Unverified / risks

1. **Never built.** Kconfig symbol names (`CONFIG_AT_SHELL`,
   `CONFIG_TFM_LOG_LEVEL_SILENCE`, `CONFIG_BT_NUS`, ...), the
   `SPI_DT_SPEC_GET` arity, NUS callback signatures and SoC dtsi include
   paths are from docs/upstream `main`, not from a pinned NCS tree.
2. **LIS2DH WHO_AM_I (0x33) and every MAX17048 register/address** are
   unverified -- the full PDFs could not be downloaded (ST/ADI blocked or
   truncated mirrors). Marked UNVERIFIED in code and plan.
3. **DW3210 DEV_ID 0xDECA0302** is from Qorvo's driver source, not the
   DW3000 User Manual (not obtained). The repo's DW3000 datasheet citations
   elsewhere are v1.3; the copy read here is v1.1, so table numbers may
   differ.
4. **nRF9151 SPIM ceiling** (above). If it is 8 MHz, A0's reply delay and
   max update rate shrink; precision does not.
5. **`%XRFTEST` / PTI firmware** facts are from Nordic's online PTI pages as
   indexed, not the PDF (download 403). One DevZone report has the TX test
   failing on nRF91x1 mfw 2.0.2.
6. **nRF9151 PS** (VBAT range, TX power, sensitivity) not obtained: those
   pass/fail rows are PLACEHOLDERs.
