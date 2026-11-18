/*
 * Inter-chip protocol: nRF9151 (host) <-> BT840 (BLE bridge) over UART, and
 * end-to-end through the bridge to the laptop.
 *
 * Single source of truth for both images and for the laptop-side decoder in
 * firmware/tools/. Design rationale lives in firmware/bay-station/README.md
 * ("Inter-chip protocol"). Summary:
 *
 *   wire frame  = COBS( header | payload | crc16 ) 0x00
 *   header      = 6 bytes, little-endian, see struct uwbrl_hdr
 *   crc16       = CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect,
 *                 no xorout) over header+payload, appended little-endian.
 *                 Check value for "123456789" is 0x29B1 -- the host test in
 *                 firmware/common/test/ asserts it.
 *
 * Message types < 0x40 are LINK-LOCAL: consumed by whichever chip receives
 * them (ping, hello, BLE link control). Types >= 0x40 are END-TO-END: the
 * bridge forwards the whole frame, unchanged, between UART and the BLE NUS
 * byte stream, so the laptop decodes exactly the same framing. The bridge
 * never needs to understand an end-to-end payload, which keeps the BT840
 * image stable when the measurement format changes.
 *
 * Everything here is plain C99 with no SDK dependency, so it compiles on
 * the host for unit tests.
 */
#ifndef UWBRL_BRIDGE_PROTO_H_
#define UWBRL_BRIDGE_PROTO_H_

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UWBRL_PROTO_VERSION 1u

/*
 * Max payload. Chosen so a worst-case encoded frame (6 hdr + 232 payload +
 * 2 crc = 240 bytes, +1 COBS overhead byte, +1 delimiter = 242) fits in one
 * BLE notification at an ATT MTU of 247 (244-byte NUS payload). NUS is
 * treated as a byte stream anyway, so this is an efficiency choice, not a
 * correctness requirement.
 */
#define UWBRL_MAX_PAYLOAD     232u
#define UWBRL_HDR_LEN         6u
#define UWBRL_CRC_LEN         2u
#define UWBRL_MAX_RAW_FRAME   (UWBRL_HDR_LEN + UWBRL_MAX_PAYLOAD + UWBRL_CRC_LEN)
/* COBS adds at most 1 byte per 254 plus 1; +1 for the 0x00 delimiter. */
#define UWBRL_MAX_WIRE_FRAME  (UWBRL_MAX_RAW_FRAME + (UWBRL_MAX_RAW_FRAME / 254u) + 2u)

/* Header flags */
#define UWBRL_F_ACK_REQ   0x01u /* receiver must answer with UWBRL_T_ACK */
#define UWBRL_F_IS_RETRY  0x02u /* retransmission of an earlier seq */

/* ---- Link-local types (< 0x40) ---------------------------------------- */
enum uwbrl_link_type {
	UWBRL_T_HELLO       = 0x01, /* boot announce: struct uwbrl_hello */
	UWBRL_T_PING        = 0x02, /* payload echoed back in PONG */
	UWBRL_T_PONG        = 0x03,
	UWBRL_T_ACK         = 0x04, /* struct uwbrl_ack */
	UWBRL_T_BLE_STATE   = 0x10, /* bridge -> host: struct uwbrl_ble_state */
	UWBRL_T_BLE_CTRL    = 0x11, /* host -> bridge: struct uwbrl_ble_ctrl */
};

/* ---- End-to-end types (>= 0x40), forwarded verbatim by the bridge ------ */
enum uwbrl_e2e_type {
	UWBRL_T_MEAS_RAW    = 0x40, /* struct uwbrl_meas_v1 (uwbrl/meas.h) */
	UWBRL_T_STATUS      = 0x41, /* struct uwbrl_station_status */
	UWBRL_T_GEOREF      = 0x42, /* struct uwbrl_georef */
	UWBRL_T_CALIB_TABLE = 0x43, /* struct uwbrl_calib_table (uwbrl/calib.h) */
	UWBRL_T_LOG         = 0x44, /* UTF-8 text, not NUL-terminated */
	UWBRL_T_CMD         = 0x50, /* laptop -> station: struct uwbrl_cmd */
	UWBRL_T_CMD_RESP    = 0x51,
};

#define UWBRL_TYPE_IS_E2E(t) ((t) >= 0x40u)

#if defined(__GNUC__)
#define UWBRL_PACKED __attribute__((packed))
#else
#error "UWBRL_PACKED: add your compiler's packed attribute"
#endif

struct uwbrl_hdr {
	uint8_t  ver;   /* UWBRL_PROTO_VERSION */
	uint8_t  type;  /* enum uwbrl_link_type / uwbrl_e2e_type */
	uint8_t  seq;   /* per-sender, per-direction, wraps. PONG and ACK echo the seq they answer. */
	uint8_t  flags; /* UWBRL_F_* */
	uint16_t len;   /* payload length, <= UWBRL_MAX_PAYLOAD */
} UWBRL_PACKED;

struct uwbrl_hello {
	uint8_t  role;          /* 1 = nRF9151 host, 2 = BT840 bridge, 3 = laptop */
	uint8_t  proto_ver;
	uint16_t max_payload;
	uint32_t fw_build_id;   /* git short hash or build counter */
} UWBRL_PACKED;

struct uwbrl_ack {
	uint8_t  acked_seq;
	uint8_t  acked_type;
	uint8_t  status;        /* 0 = ok, else enum uwbrl_err */
} UWBRL_PACKED;

struct uwbrl_ble_state {
	uint8_t  connected;
	uint8_t  security_level; /* Zephyr bt_security_t value at the bridge */
	uint16_t att_mtu;
	uint32_t e2e_frames_dropped; /* frames the bridge discarded: BLE slower than UART */
} UWBRL_PACKED;

struct uwbrl_ble_ctrl {
	uint8_t  op;            /* 1 = advertise on, 2 = advertise off, 3 = disconnect */
	uint8_t  led_link_mode; /* 0 = auto (follow connection), 1 = off, 2 = on, 3 = blink */
} UWBRL_PACKED;

enum uwbrl_err {
	UWBRL_OK = 0,
	UWBRL_E_CRC = 1,
	UWBRL_E_COBS = 2,
	UWBRL_E_LEN = 3,
	UWBRL_E_VER = 4,
	UWBRL_E_TYPE = 5,
	UWBRL_E_BUSY = 6,
};

/* ---- API ---------------------------------------------------------------- */

uint16_t uwbrl_crc16_ccitt_false(uint16_t crc, const uint8_t *data, size_t len);

/*
 * COBS encode src[0..len) into dst. dst must hold len + len/254 + 1 bytes.
 * Does NOT append the 0x00 delimiter. Returns encoded length.
 */
size_t uwbrl_cobs_encode(const uint8_t *src, size_t len, uint8_t *dst);

/*
 * COBS decode src[0..len) (delimiter already stripped) into dst (may alias
 * src). Returns decoded length, or 0 on malformed input.
 */
size_t uwbrl_cobs_decode(const uint8_t *src, size_t len, uint8_t *dst);

/*
 * Build a complete wire frame (COBS + trailing 0x00) into out, which must
 * hold UWBRL_MAX_WIRE_FRAME bytes. Returns wire length, or 0 if
 * payload_len > UWBRL_MAX_PAYLOAD.
 */
size_t uwbrl_frame_build(uint8_t type, uint8_t seq, uint8_t flags,
			 const void *payload, uint16_t payload_len, uint8_t *out);

/*
 * Streaming receiver. Feed bytes as they arrive; when a delimiter completes
 * a valid frame, uwbrl_rx_feed() returns 1 and fills *hdr / *payload
 * (pointing into the rx struct's buffer, valid until the next feed).
 * Returns 0 if more bytes are needed, negative enum uwbrl_err on a bad
 * frame (the receiver has already resynchronised on the delimiter).
 */
struct uwbrl_rx {
	uint8_t  buf[UWBRL_MAX_WIRE_FRAME];
	size_t   n;
	uint8_t  overflow;
	uint32_t n_ok, n_crc_err, n_cobs_err, n_len_err;
};

void uwbrl_rx_init(struct uwbrl_rx *rx);
int  uwbrl_rx_feed(struct uwbrl_rx *rx, uint8_t byte,
		   struct uwbrl_hdr *hdr, const uint8_t **payload);

#ifdef __cplusplus
}
#endif

#endif /* UWBRL_BRIDGE_PROTO_H_ */
