/*
 * COBS framing + CRC-16/CCITT-FALSE for the bay-station bridge protocol.
 * See include/uwbrl/bridge_proto.h. Plain C99, no SDK dependency.
 */
#include "uwbrl/bridge_proto.h"

#include <string.h>

uint16_t uwbrl_crc16_ccitt_false(uint16_t crc, const uint8_t *data, size_t len)
{
	/* Bitwise on purpose: frames are short, and this avoids a 512-byte table
	 * on the BT840. Swap for Zephyr's crc16_itu_t() if profiling says so --
	 * same polynomial, non-reflected; confirm the seed convention matches
	 * against the 0x29B1 check value before switching.
	 */
	for (size_t i = 0; i < len; i++) {
		crc ^= (uint16_t)data[i] << 8;
		for (int b = 0; b < 8; b++) {
			crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
					      : (uint16_t)(crc << 1);
		}
	}
	return crc;
}

size_t uwbrl_cobs_encode(const uint8_t *src, size_t len, uint8_t *dst)
{
	size_t code_idx = 0;
	size_t out = 1;
	uint8_t code = 1;

	for (size_t i = 0; i < len; i++) {
		if (src[i] == 0) {
			dst[code_idx] = code;
			code_idx = out++;
			code = 1;
		} else {
			dst[out++] = src[i];
			code++;
			if (code == 0xFF) {
				dst[code_idx] = code;
				code_idx = out++;
				code = 1;
			}
		}
	}
	dst[code_idx] = code;
	return out;
}

size_t uwbrl_cobs_decode(const uint8_t *src, size_t len, uint8_t *dst)
{
	size_t in = 0;
	size_t out = 0;

	while (in < len) {
		uint8_t code = src[in++];

		if (code == 0) {
			return 0; /* delimiter inside a frame: malformed */
		}
		if (in + (size_t)(code - 1) > len) {
			return 0; /* run overflows input */
		}
		for (uint8_t i = 1; i < code; i++) {
			dst[out++] = src[in++];
		}
		if (code != 0xFF && in < len) {
			dst[out++] = 0;
		}
	}
	return out;
}

size_t uwbrl_frame_build(uint8_t type, uint8_t seq, uint8_t flags,
			 const void *payload, uint16_t payload_len, uint8_t *out)
{
	uint8_t raw[UWBRL_MAX_RAW_FRAME];
	struct uwbrl_hdr hdr = {
		.ver = UWBRL_PROTO_VERSION,
		.type = type,
		.seq = seq,
		.flags = flags,
		.len = payload_len, /* LE: all targets (Cortex-M, x86/arm64 host) are LE */
	};

	if (payload_len > UWBRL_MAX_PAYLOAD) {
		return 0;
	}
	memcpy(raw, &hdr, UWBRL_HDR_LEN);
	if (payload_len) {
		memcpy(raw + UWBRL_HDR_LEN, payload, payload_len);
	}
	size_t n = UWBRL_HDR_LEN + payload_len;
	uint16_t crc = uwbrl_crc16_ccitt_false(0xFFFFu, raw, n);

	raw[n++] = (uint8_t)(crc & 0xFF);
	raw[n++] = (uint8_t)(crc >> 8);

	size_t w = uwbrl_cobs_encode(raw, n, out);

	out[w++] = 0x00;
	return w;
}

void uwbrl_rx_init(struct uwbrl_rx *rx)
{
	memset(rx, 0, sizeof(*rx));
}

int uwbrl_rx_feed(struct uwbrl_rx *rx, uint8_t byte,
		  struct uwbrl_hdr *hdr, const uint8_t **payload)
{
	if (byte != 0x00) {
		if (rx->n < sizeof(rx->buf)) {
			rx->buf[rx->n++] = byte;
		} else {
			rx->overflow = 1;
		}
		return 0;
	}

	/* Delimiter: try to close a frame, then always resync. */
	size_t n = rx->n;
	uint8_t ovf = rx->overflow;

	rx->n = 0;
	rx->overflow = 0;

	if (n == 0) {
		return 0; /* back-to-back delimiters are legal idle fill */
	}
	if (ovf) {
		rx->n_len_err++;
		return -UWBRL_E_LEN;
	}
	size_t d = uwbrl_cobs_decode(rx->buf, n, rx->buf);

	if (d < UWBRL_HDR_LEN + UWBRL_CRC_LEN) {
		rx->n_cobs_err++;
		return -UWBRL_E_COBS;
	}
	uint16_t got = (uint16_t)rx->buf[d - 2] | ((uint16_t)rx->buf[d - 1] << 8);

	if (uwbrl_crc16_ccitt_false(0xFFFFu, rx->buf, d - 2) != got) {
		rx->n_crc_err++;
		return -UWBRL_E_CRC;
	}
	memcpy(hdr, rx->buf, UWBRL_HDR_LEN);
	if (hdr->ver != UWBRL_PROTO_VERSION) {
		return -UWBRL_E_VER;
	}
	if ((size_t)hdr->len + UWBRL_HDR_LEN + UWBRL_CRC_LEN != d) {
		rx->n_len_err++;
		return -UWBRL_E_LEN;
	}
	*payload = rx->buf + UWBRL_HDR_LEN;
	rx->n_ok++;
	return 1;
}
