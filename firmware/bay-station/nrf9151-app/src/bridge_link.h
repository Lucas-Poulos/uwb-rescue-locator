/* nRF9151 side of the BT840 bridge link (firmware/common/include/uwbrl/bridge_proto.h). */
#ifndef BRIDGE_LINK_H_
#define BRIDGE_LINK_H_

#include <stdint.h>
#include "uwbrl/bridge_proto.h"

int bridge_link_init(void);
int bridge_send(uint8_t type, uint8_t flags, const void *payload, uint16_t len);
/* PING with a payload, wait for the matching PONG. Returns round-trip us or <0. */
int bridge_ping(const void *payload, uint16_t len, int timeout_ms);
int bridge_reset_ble(void);       /* pulse RESET_BLE_N */
int bridge_irq_level(void);       /* BRIDGE_IRQ */
void bridge_stats(uint32_t *ok, uint32_t *crc_err, uint32_t *cobs_err, uint32_t *len_err);

#endif /* BRIDGE_LINK_H_ */
