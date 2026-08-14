# Decision log

Open calls first, resolved calls below with the reasoning, so we don't
relitigate them. Keep this updated as the team decides things.

## Open

- **UWB IC/module** (used on both boards -- goes in `shared/` once picked).
  Candidates to evaluate: Qorvo/Decawave DW3000-series (e.g. DWM3000 module)
  vs. DW1000. Affects: shared library, ranging protocol, antenna design on
  both boards.
- **Bay station connectivity**: ESP32 (module vs. bare SoC) vs. a discrete
  BLE IC + separate dual-band WiFi IC. Affects: bay station BOM, firmware
  stack, power budget (longevity-focused BMS sizing depends on this).
- **Bay station uplink backend**: what protocol/service position data gets
  sent to.
- **Wristband BMS specifics**: single-cell chemistry/capacity, charge IC,
  fuel gauge (if any) -- sized around "just enough for core function," not
  longevity.
- **Bay station BMS specifics**: chemistry/capacity, charge IC -- sized for
  long runtime, likely a materially different design from the wristband's.
- **Anchor placement / enclosure** for the bay station's 4 UWB anchors
  (fixed relative geometry matters for triangulation accuracy).
- **PCB layer count / stackup** for each board -- not set yet; likely needs
  4-layer on at least the wristband for RF (UWB + BLE) given board size
  constraints, but that's a layout-phase call.

## Resolved

- **Wristband MCU/radio**: u-blox NINA-B1. Reason: team standard, reuses
  existing firmware base from other projects.
- **Repo structure**: monorepo, two KiCad projects (`wristband/`,
  `bay-station/`) + a `shared/` library folder. Reason: KiCad has no native
  multi-board project, and a monorepo keeps shared parts/docs/history in one
  place for a small team.
- **KiCad version**: files are currently in KiCad 8.0 format (matches the
  installed toolchain as of 2026-08-14). Team wants to standardize on
  KiCad 9.x once everyone can upgrade -- see root `README.md`.
