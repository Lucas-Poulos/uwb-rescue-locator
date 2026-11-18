/*
 * Raw measurement record: one per wristband exchange, station -> laptop.
 *
 * Precision rules (firmware/CLAUDE.md, "Precision is the product"):
 *  - Every timestamp stays in RAW DW3000 device time units, 40 bits,
 *    little-endian, exactly as read from the chip. One unit is
 *    1 / (128 * 499.2 MHz) ~= 15.65 ps (Qorvo dwt_uwb_driver 08.02.02,
 *    deca_device_api.h, DWT_TIME_UNITS; not yet cross-checked against the
 *    DW3000 User Manual, which we do not have a copy of -- verify).
 *  - Calibration is NOT applied here. calib_crc names the table in force so
 *    the laptop can apply it (and re-apply a newer one to old logs).
 *  - The anchors are not peers: A0 fields and A1-A3 fields are named by
 *    role, not by an index loop, wherever the role differs.
 *
 * Exchange assumed (see bay-station/README.md "Exchange scheduling"):
 *   tag POLL -> A0 RESP (delayed TX) -> tag FINAL (carries tag timestamps)
 *   A0..A3 all timestamp the same POLL (TDoA sample 1) and the same FINAL
 *   (TDoA sample 2, free averaging). A0 additionally owns the DS-TWR set.
 */
#ifndef UWBRL_MEAS_H_
#define UWBRL_MEAS_H_

#include <stdint.h>
#include "uwbrl/bridge_proto.h" /* UWBRL_PACKED */

#define UWBRL_N_ANCHORS   4u
#define UWBRL_ANCHOR_A0   0u /* center: DS-TWR + TDoA reference */
#define UWBRL_ANCHOR_A1   1u /* outer: TDoA vs A0 */
#define UWBRL_ANCHOR_A2   2u
#define UWBRL_ANCHOR_A3   3u

struct uwbrl_ts40 {
	uint8_t b[5]; /* raw DW3000 40-bit timestamp, LSB first */
} UWBRL_PACKED;

/*
 * Per-anchor receive diagnostics. Deliberately opaque until the driver's
 * diagnostic API is read from source: the fields Qorvo exposes (first-path
 * index, first-path / CIR power, STS quality) and their scaling must be
 * taken from dwt_uwb_driver, not recalled. TODO(fw-m4).
 */
struct uwbrl_rxdiag {
	uint8_t raw[8];
} UWBRL_PACKED;

#define UWBRL_MEAS_F_POLL_VALID(i)   (1u << (i))       /* bits 0..3 */
#define UWBRL_MEAS_F_FINAL_VALID(i)  (1u << ((i) + 4)) /* bits 4..7 */

struct uwbrl_meas_v1 {
	uint32_t meas_seq;      /* station counter; gaps = drops anywhere en route */
	uint16_t tag_id;
	uint8_t  valid;         /* UWBRL_MEAS_F_* */
	uint8_t  flags;         /* bit0: station was moving (ACC_INT1) during exchange */
	uint32_t calib_crc;     /* CRC32 of the calibration table in force, NOT applied */

	/* Same POLL frame, all four anchors (shared clock => directly comparable). */
	struct uwbrl_ts40 poll_rx[UWBRL_N_ANCHORS];
	/* Same FINAL frame, all four anchors. */
	struct uwbrl_ts40 final_rx[UWBRL_N_ANCHORS];

	/* A0-only DS-TWR terms (station clock). */
	struct uwbrl_ts40 a0_resp_tx;
	/* Tag-side DS-TWR terms (tag clock), copied from the FINAL payload. */
	struct uwbrl_ts40 tag_poll_tx;
	struct uwbrl_ts40 tag_resp_rx;
	struct uwbrl_ts40 tag_final_tx;

	struct uwbrl_rxdiag diag_poll[UWBRL_N_ANCHORS];
} UWBRL_PACKED;

/* Keep under one frame. 104 bytes at time of writing (host test prints it). */
_Static_assert(sizeof(struct uwbrl_meas_v1) <= UWBRL_MAX_PAYLOAD,
	       "meas record must fit one bridge frame");

#endif /* UWBRL_MEAS_H_ */
