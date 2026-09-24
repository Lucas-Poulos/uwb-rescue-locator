# Firmware

Nothing is written yet. This tree exists so the work has a home and so the
scope is visible -- **firmware is on the critical path**, not a phase that
starts after the boards come back.

The hardware design only meets its 10-30 cm target if the software half
exists: the array calibration routine in particular is a deliverable, not a
bring-up nicety (see `../docs/positioning.md`).

## Layout

```
firmware/
  bay-station/   BT840 (nRF52840) -- drives 4x DW3210, runs the exchange, BLE to laptop
  wristband/     nRF52833 inside the DWM3001C -- the tag; transmits, and little else
  common/        shared protocol/message definitions used by both sides
  tools/         host-side: calibration, survey, analysis, test fixtures
```

## What has to get written

Roughly in dependency order.

### bay-station

1. **DW3000 driver with multi-instance support.** Qorvo's own reference stack
   targets nRF52840, so start there rather than from the ESP-IDF community
   port. **Known gap either way:** the widely used community driver
   ([br101/dw3000-decadriver-source](https://github.com/br101/dw3000-decadriver-source))
   was trimmed to one DW3000 per board and this design has four.
   Multi-instance support exists upstream and needs restoring. First task,
   and it gates everything else.
2. **Exchange scheduling.** A0 runs two-way ranging with the tag; A1-A3
   timestamp the same transmission. One tag TX, four measurements.
3. **Timestamp collection** across four chips over the shared SPI bus.
4. **Position solve** -- sphere from A0's range intersected with three
   hyperboloids from the TDoA differences. Overdetermined by one, so use the
   residual as a live quality metric. Decide on-device vs. server-side.
5. **Calibration table** -- load and apply per-anchor differential offsets.
6. **Georeferencing.** Average the MAX-M10S fix while stationary to reach
   sub-metre (host-side survey-in -- the M10 standard-precision line has no
   survey-in mode of its own). Read heading from the LIS3MDL, tilt-compensate
   it with the LIS2DH, and apply hard-iron/soft-iron calibration. Watch the
   accelerometer for the station being knocked, which invalidates both the
   fix and the heading. Note the averaging restarts at every new site.
7. **Uplink** over BLE to the laptop.

### wristband

The tag is deliberately simple: transmit, participate in the ranging
exchange with A0, sleep. It is the power-constrained side, so the whole
scheme is built around it transmitting once.

### tools

- **Array calibration.** Place the tag at surveyed positions, measure actual
  TDoA, solve for per-anchor differential offsets (antenna delay + cable
  delay together), emit the table the firmware loads. Without this the
  design does not hit its accuracy target -- Table 14 of the DW3000
  datasheet gives +/-6 cm for a *generically* calibrated node, which at a 1 m
  baseline is ~85 cm of position error.
- Analysis/plotting for bring-up measurements.

## Not yet decided

- **One** toolchain choice now, not two: both boards are Nordic (nRF52840 on
  the station, nRF52833 on the tag), so it is nRF5 SDK vs. Zephyr / nRF
  Connect SDK for the whole project. Note Qorvo publishes reference firmware
  for the DWM3001C via the DWM3001CDK, and its DW3000 reference stack targets
  nRF52840 -- start from both rather than from scratch.
- Whether the position solve runs on-device or server-side.
- Update rate and multi-tag scheduling.

Record these in `../docs/decisions.md` when they get made, same as hardware
calls.
