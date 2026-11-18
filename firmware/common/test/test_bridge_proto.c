/*
 * Host-side unit test for the bridge framing. No SDK needed:
 *   make -C firmware/common/test
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "uwbrl/bridge_proto.h"
#include "uwbrl/calib.h"
#include "uwbrl/meas.h"

static int feed_all(struct uwbrl_rx *rx, const uint8_t *w, size_t n,
		    struct uwbrl_hdr *h, const uint8_t **p)
{
	int r = 0;

	for (size_t i = 0; i < n; i++) {
		r = uwbrl_rx_feed(rx, w[i], h, p);
		if (r != 0) {
			return r;
		}
	}
	return r;
}

int main(void)
{
	/* CRC-16/CCITT-FALSE catalogue check value. */
	const uint8_t check[] = "123456789";

	assert(uwbrl_crc16_ccitt_false(0xFFFF, check, 9) == 0x29B1);

	/* COBS round trip incl. zeros and a >254-byte zero-free run. */
	uint8_t src[300], enc[310], dec[310];

	for (size_t i = 0; i < sizeof(src); i++) {
		src[i] = (uint8_t)((i % 17) ? i : 0);
	}
	memset(src + 20, 0xAA, 260);
	size_t e = uwbrl_cobs_encode(src, sizeof(src), enc);

	for (size_t i = 0; i < e; i++) {
		assert(enc[i] != 0);
	}
	assert(uwbrl_cobs_decode(enc, e, dec) == sizeof(src));
	assert(memcmp(src, dec, sizeof(src)) == 0);

	/* Frame round trip through the streaming receiver. */
	struct uwbrl_meas_v1 m;

	memset(&m, 0, sizeof(m));
	m.meas_seq = 0x01020304;
	m.poll_rx[UWBRL_ANCHOR_A0].b[0] = 0x00; /* zeros on purpose */
	m.poll_rx[UWBRL_ANCHOR_A3].b[4] = 0xFF;

	uint8_t wire[UWBRL_MAX_WIRE_FRAME];
	size_t wn = uwbrl_frame_build(UWBRL_T_MEAS_RAW, 7, 0, &m, sizeof(m), wire);

	assert(wn > 0 && wn <= UWBRL_MAX_WIRE_FRAME);
	assert(wire[wn - 1] == 0);

	struct uwbrl_rx rx;
	struct uwbrl_hdr h;
	const uint8_t *p = NULL;

	uwbrl_rx_init(&rx);
	assert(feed_all(&rx, wire, wn, &h, &p) == 1);
	assert(h.type == UWBRL_T_MEAS_RAW && h.seq == 7 && h.len == sizeof(m));
	assert(memcmp(p, &m, sizeof(m)) == 0);

	/* Corrupt one byte: CRC (or COBS) error, then clean resync. */
	wire[3] ^= 0x01;
	if (wire[3] == 0) {
		wire[3] = 0x02;
	}
	int r = feed_all(&rx, wire, wn, &h, &p);

	assert(r == -UWBRL_E_CRC || r == -UWBRL_E_COBS || r == -UWBRL_E_LEN);
	wire[3] ^= 0x01;
	wn = uwbrl_frame_build(UWBRL_T_PING, 8, UWBRL_F_ACK_REQ, "hi", 2, wire);
	assert(feed_all(&rx, wire, wn, &h, &p) == 1 && h.type == UWBRL_T_PING);

	/* Max payload builds; one over is refused. */
	uint8_t big[UWBRL_MAX_PAYLOAD + 1];

	memset(big, 0, sizeof(big));
	assert(uwbrl_frame_build(UWBRL_T_LOG, 0, 0, big, UWBRL_MAX_PAYLOAD, wire) <=
	       UWBRL_MAX_WIRE_FRAME);
	assert(uwbrl_frame_build(UWBRL_T_LOG, 0, 0, big, UWBRL_MAX_PAYLOAD + 1, wire) == 0);

	printf("bridge_proto: OK (meas_v1 = %zu bytes, calib = %zu bytes, max wire = %u)\n",
	       sizeof(struct uwbrl_meas_v1), sizeof(struct uwbrl_calib_table),
	       (unsigned)UWBRL_MAX_WIRE_FRAME);
	return 0;
}
