# Host-side tools

Not firmware -- things that run on a laptop.

- **Frame decoder / logger.** Reads the BLE NUS byte stream, decodes the
  same COBS + CRC frames the station emits (`../common/include/uwbrl/`),
  and logs raw `uwbrl_meas_v1` records unmodified. Everything else
  consumes these logs.
- **Position solver (authoritative).** Sphere from A0's DS-TWR range
  intersected with three hyperboloids from the A1-A3 TDoA differences,
  overdetermined by one -- report the residual as a live quality metric.
  Applies the calibration table named by each record's `calib_crc`, and
  converts device time units to seconds exactly once, here. Rationale for
  solving here rather than on the station: `../bay-station/README.md`,
  "Position solve: where".
- **Array calibration**: the important one. Emits the per-anchor delay table
  (`../common/include/uwbrl/calib.h`) the station stores. The design does
  not meet its accuracy target without it.

  Two distinct jobs, with different requirements -- see
  `../../docs/positioning.md`:
  - A0's *absolute* antenna+cable delay, which sets the range scale. Maps
    1:1 into radial error, so ~10 cm of equivalent path accuracy is enough
    for a 10 cm target -- but it does need a known true distance.
  - A1-A3's delay *relative to A0*, which sets bearing. Amplified by
    `range/B` (10x at 10 m on a 1 m baseline), so needs to be ~10x tighter,
    around 1 cm. Does NOT need a known distance -- only the same signal
    observed simultaneously, so tag-position error largely cancels.
- Bring-up analysis and plotting (`../../docs/verification-plan.md`).

Empty.
