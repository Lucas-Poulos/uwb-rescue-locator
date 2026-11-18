/*
 * Array calibration table. Produced by firmware/tools/ (array calibration),
 * stored on the station, shipped to the laptop on connect, and identified in
 * every measurement record by its CRC.
 *
 * Two different quantities, per docs/positioning.md "A0 and the outer
 * anchors need different calibrations":
 *  - A0: ABSOLUTE antenna+cable delay. Sets range scale, error maps 1:1
 *    into radial error. Needs a known true distance to measure.
 *  - A1-A3: delay RELATIVE TO A0. Sets bearing, error amplified by range/B
 *    (10x at 10 m on a 1 m baseline), so it needs ~10x tighter accuracy
 *    (~33 ps for a 10 cm target). Does not need a known distance.
 * They are separate fields on purpose -- do not fold them into one array.
 *
 * Units: signed DW3000 device time units (~15.65 ps, see meas.h), so the
 * table never round-trips through floating-point seconds.
 *
 * The DW3000's own antenna-delay registers are programmed to a fixed known
 * value (proposed: 0) on every anchor, and ALL delay correction lives here.
 * Otherwise the same delay gets subtracted twice -- once in silicon, once
 * in the solve -- and nobody can tell from a log which happened.
 */
#ifndef UWBRL_CALIB_H_
#define UWBRL_CALIB_H_

#include <stdint.h>
#include "uwbrl/bridge_proto.h"

#define UWBRL_CALIB_MAGIC   0x4C414355u /* "UCAL" little-endian */
#define UWBRL_CALIB_VERSION 1u

struct uwbrl_calib_table {
	uint32_t magic;
	uint16_t version;
	uint16_t reserved;
	uint32_t created_unix;     /* when the fixture run produced it */
	uint32_t frame_serial;     /* antenna frame / cable set it belongs to */

	int32_t  a0_abs_delay_dtu;       /* A0 absolute antenna+cable delay */
	int32_t  outer_rel_delay_dtu[3]; /* A1..A3 delay minus A0 delay */

	/* Antenna phase-centre positions in the frame's own coordinates, mm.
	 * Index 0 = A0. Fixed at manufacture by the rigid frame. */
	int32_t  antenna_pos_mm[4][3];

	uint32_t crc32;            /* over all preceding bytes; algorithm TBD in fw-m6 */
} UWBRL_PACKED;

_Static_assert(sizeof(struct uwbrl_calib_table) <= UWBRL_MAX_PAYLOAD,
	       "calib table must fit one bridge frame");

#endif /* UWBRL_CALIB_H_ */
