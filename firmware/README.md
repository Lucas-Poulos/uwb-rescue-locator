# Firmware

**Firmware is on the critical path**, not a phase that starts after the
boards come back. The hardware only meets its 10-30 cm target if the
software half exists -- the array calibration in particular is a
deliverable, not a bring-up nicety (`../docs/positioning.md`).

Toolchain: **nRF Connect SDK v3.4.x (LTS)** for every image. The bay
station's nRF9151 forces it (the nRF5 SDK covers only nRF51/nRF52);
see `bay-station/README.md`, "Toolchain".

**Status: skeletons only, never built** (no SDK installed where they were
written). The shared protocol code has a passing host unit test
(`make -C common/test`). Pins are unassigned by design -- each board's
`*_pins.h` is the one place they get filled in, and the build stops until
it is.

## Layout

```
firmware/
  bay-station/
    nrf9151-app/   nRF9151 host: 4x DW3210, exchange, timestamps, calibration,
                   sensors, LTE-M + GNSS, 'bringup' shell
    ble-bridge/    BT840 (nRF52840): framed UART <-> BLE NUS relay to the laptop
    (modem FW)     Nordic binary, version-pinned -- see bay-station/README.md
  wristband/       nRF52833 inside the DWM3001C -- the tag
  common/          protocol + record + calibration-table definitions, host-tested
  boards/          Zephyr HWMv2 board definitions (bay_station_lte, bay_station_ble)
  dts/bindings/    project devicetree bindings (anchor role, shared UWB lines, bridge)
  tools/           laptop side: decoder, solver, calibration, analysis
```

## Milestones, in bring-up order

Each one is usable on its own and unblocks the next. "DK" work can start
before boards exist.

| # | Milestone | Needs | Done when |
|---|---|---|---|
| fw-m0 | NCS v3.4.x installed; both skeletons build for **DK targets** (`nrf9151dk/nrf9151/ns`, `nrf52840dk/nrf52840`) with a DK overlay | nothing | `west build` clean; host test passes in CI |
| fw-m1 | Board bring-up shell on real hardware: rails cross-check, I2C scan + IDs, LEDs, button, sensor lines | pins filled in; board stage 5 of `../docs/verification-plan.md` | every `bringup` command in stage 6 runs |
| fw-m2 | Bridge link: nRF9151 <-> BT840 framing, BT840 NUS relay, laptop decoder in `tools/` | fw-m1 | `bringup bridge ping 1000` = 1000/1000; laptop receives STATUS frames |
| fw-m3 | **Multi-instance DW3000 driver**: DEV_ID x4, init to IDLE_PLL (clock check), CH5 config per anchor | fw-m1 | `bringup uwb id` and `uwb clock` pass on all four |
| fw-m4 | Timestamp collection: one frame, four RX timestamps, `uwbrl_meas_v1` assembled; first inter-anchor skew measurement | fw-m3 | skew test in verification plan runs |
| fw-m5 | Exchange: POLL/RESP/FINAL with the wristband; OTA frame formats in `common/`; DS-TWR range at A0 | fw-m4 + wristband fw | range to a tag at a taped distance |
| fw-m6 | Calibration: table store on station, fixture procedure + table generator in `tools/` | fw-m5 | table loaded, CRC in every record |
| fw-m7 | Laptop solve (sphere + 3 hyperboloids, residual as quality) + logging | fw-m6 | position at surveyed points within target |
| fw-m8 | Georeferencing: GNSS survey-in in LTE idle windows, LIS3MDL heading with LIS2DH tilt compensation, hard/soft-iron cal, knock detect | fw-m1 | station reports lat/lon/heading with a settled/unsettled flag |
| fw-m9 | LTE-M uplink: attach, PSM, status + quick-look positions | fw-m7, fw-m8, SIM | report received at the endpoint |
| fw-m10 | Power management, multi-tag scheduling, FOTA (app + modem) | all | battery-life target met (target still to be set) |

## Wristband

The tag is deliberately simple: transmit, participate in the ranging
exchange with A0, sleep. See `wristband/README.md`. Its first real dependency
on the station is fw-m5 (shared OTA frame formats).

## Tools

The laptop side owns the authoritative position solve and the array
calibration. See `tools/README.md`.

## Still open

- Update rate and multi-tag scheduling.
- BLE link security level (Nordic ships its own NUS bridge with BLE off by
  default for want of authentication) -- `handoff.md`.
- LTE endpoint, SIM/operator, data budget -- `handoff.md`.

Calls made here are proposed as `../docs/decisions.md` entries in
`handoff.md`; the coordinator merges them.
