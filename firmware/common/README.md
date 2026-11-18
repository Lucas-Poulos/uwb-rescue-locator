# Shared definitions

Protocol and message definitions used by more than one image -- the
nRF9151 host app, the BT840 bridge app, the wristband, and the laptop-side
tools. Keep this the single source of truth rather than duplicating struct
definitions on each side.

Plain C99, no SDK dependency, so it compiles and is unit-tested on the host.

| File | What |
|---|---|
| `include/uwbrl/bridge_proto.h`, `src/bridge_proto.c` | nRF9151 <-> BT840 <-> laptop framing: COBS + CRC-16/CCITT-FALSE, message types, link-control structs. Rationale in `../bay-station/README.md`, "Inter-chip protocol". |
| `include/uwbrl/meas.h` | Raw measurement record (one per tag exchange). Raw 40-bit DW3000 timestamps, calibration **not** applied. |
| `include/uwbrl/calib.h` | Array calibration table: A0 absolute delay and A1-A3 relative delays as separate fields, antenna positions. |
| `test/` | Host unit test. `make -C firmware/common/test` (prints `bridge_proto: OK`). |

Not here yet: the UWB over-the-air frame formats (POLL / RESP / FINAL
payloads, tag ID). They belong here, shared by the wristband and the
station, and land with milestone fw-m5 in `../README.md`.

Zephyr apps pull these sources in directly
(`target_sources(app PRIVATE ../../common/src/bridge_proto.c)`) rather than
through a Zephyr module, which is not worth the ceremony for one `.c` file.
