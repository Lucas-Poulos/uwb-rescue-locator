# Wristband firmware

Nordic nRF52833, inside the DWM3001C. The tag: participates in the two-way
ranging exchange with the bay station's center anchor, then sleeps.

Deliberately minimal -- the wristband is the power-constrained side, which is
why the positioning scheme is built around one transmission per fix.

## Toolchain: recommend nRF Connect SDK, same release as the station

The station's nRF9151 can only be built with nRF Connect SDK
(`../bay-station/README.md`, "Toolchain"). The nRF52833 *could* still use
the nRF5 SDK, but Nordic lists that SDK as "in maintenance mode" and
recommends NCS for new projects (nRF5 SDK product page). One toolchain for
the project means one install, one CI image, and `../common/` compiled the
same way on both boards. **Recommend NCS v3.4.x for the wristband too.**

What that means for the DW3110 inside the DWM3001C:

- Upstream Zephyr has a `decawave_dwm3001cdk` board, but (per community
  reports on Qorvo's forum) it does not declare the on-module DW3110, so an
  overlay is needed. Our own board will need its own definition anyway.
- The same Qorvo `dwt_uwb_driver` 08.02.02 source the station uses
  (br101's Zephyr packaging) supports one chip per board -- which is
  exactly the wristband's case, so the wristband is the *easier* place to
  bring the driver up first.
- Qorvo publishes no Zephyr/NCS support for the DWM3001CDK that could be
  found (2026-11-17); its DW3_QM33 SDK lists the DWM3001CDK as a platform
  without naming an RTOS. Treat Qorvo's examples as reference, not as a
  base to build on.

## First dependency

fw-m5 in `../README.md`: the POLL/RESP/FINAL frame formats, which will live
in `../common/` and be shared with the station.

## Check before you build on the accelerometer

The module's `I2C0_SDA`/`I2C0_SCL` (pins 14/15) are unconnected in the
schematic, and whether the on-module LIS2DH12 is reachable with no external
parts depends on whether Qorvo put pull-ups inside the module. That is an
open item in `../../docs/decisions.md`. Motion-gating -- the largest battery
lever on this board -- depends on it.
