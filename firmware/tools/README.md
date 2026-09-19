# Host-side tools

Not firmware -- things that run on a laptop.

- **Array calibration**: the important one. Emits the per-anchor delay table
  the bay-station firmware loads. The design does not meet its accuracy
  target without it.

  Two distinct jobs, and they have different requirements -- see
  `../../docs/positioning.md`:
  - A0's *absolute* antenna+cable delay, which sets the range scale. Maps
    1:1 into radial error, so ~10 cm of equivalent path accuracy is enough
    for a 10 cm target -- but it does need a known true distance.
  - A1-A3's delay *relative to A0*, which sets bearing. Amplified by
    `range/B` (10x at 10 m on a 1 m baseline), so needs to be ~10x tighter,
    around 1 cm. Does NOT need a known distance -- only the same signal
    observed simultaneously, so tag-position error largely cancels.
- Bring-up analysis and plotting.

Empty.
