/*
 * BT840 BLE bridge: a framed relay between the nRF9151 (UART) and the
 * laptop (BLE Nordic UART Service), plus a few link-local messages.
 *
 *   UART frame, type >= 0x40  -> re-encoded unchanged onto NUS
 *   NUS frame,  type >= 0x40  -> re-encoded unchanged onto UART
 *   PING (either side)        -> answered here with PONG (same seq)
 *   BLE_CTRL (from host)      -> advertising / LED_LINK control
 *   connect / disconnect      -> BLE_STATE to the host
 *
 * The bridge never interprets an end-to-end payload, so measurement-format
 * changes never touch this image (bridge_proto.h).
 *
 * Skeleton: NUS API names follow NCS's subsys/bluetooth/services/nus
 * (bt_nus_init / bt_nus_send) -- confirm signatures on the pinned release.
 */
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/ring_buffer.h>
#include <bluetooth/services/nus.h>

#include "uwbrl/bridge_proto.h"

LOG_MODULE_REGISTER(ble_bridge, LOG_LEVEL_INF);

#define BRIDGE_NODE DT_NODELABEL(bridge_ctrl)

static const struct device *const uart = DEVICE_DT_GET(DT_PHANDLE(BRIDGE_NODE, uart));
static const struct gpio_dt_spec host_irq = GPIO_DT_SPEC_GET(BRIDGE_NODE, irq_gpios);
static const struct gpio_dt_spec led_link = GPIO_DT_SPEC_GET(DT_ALIAS(led_link), gpios);

RING_BUF_DECLARE(uart_rx_ring, 2048);
static K_SEM_DEFINE(work_sem, 0, 1);

static struct uwbrl_rx from_host;   /* frames arriving on UART */
static struct uwbrl_rx from_laptop; /* frames arriving on NUS */
static struct bt_conn *cur_conn;
static uint8_t seq_to_host, seq_to_laptop;
static uint32_t e2e_dropped;
/* to_host/to_laptop run from both the main loop and the BT RX thread. */
static K_MUTEX_DEFINE(host_tx_lock);
static K_MUTEX_DEFINE(laptop_tx_lock);

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

/* ---------------------------------------------------------- outputs */

static void to_host(uint8_t type, uint8_t seq, uint8_t flags, const void *p, uint16_t len)
{
	static uint8_t wire[UWBRL_MAX_WIRE_FRAME];

	k_mutex_lock(&host_tx_lock, K_FOREVER);
	size_t n = uwbrl_frame_build(type, seq, flags, p, len, wire);

	gpio_pin_set_dt(&host_irq, 1); /* BRIDGE_IRQ: "frame coming" */
	for (size_t i = 0; i < n; i++) {
		uart_poll_out(uart, wire[i]); /* CTS honoured by UARTE HW */
	}
	gpio_pin_set_dt(&host_irq, 0);
	k_mutex_unlock(&host_tx_lock);
}

static void to_laptop(uint8_t type, uint8_t seq, uint8_t flags, const void *p, uint16_t len)
{
	static uint8_t wire[UWBRL_MAX_WIRE_FRAME];

	if (!cur_conn) {
		e2e_dropped++;
		return;
	}
	k_mutex_lock(&laptop_tx_lock, K_FOREVER);
	size_t n = uwbrl_frame_build(type, seq, flags, p, len, wire);

	if (bt_nus_send(cur_conn, wire, n)) {
		/* BLE slower than UART: drop, count, report in BLE_STATE. The
		 * laptop sees the gap in meas_seq. TODO(fw-m2): small queue. */
		e2e_dropped++;
	}
	k_mutex_unlock(&laptop_tx_lock);
}

static void send_ble_state(void)
{
	struct uwbrl_ble_state st = {
		.connected = cur_conn != NULL,
		.security_level = cur_conn ? (uint8_t)bt_conn_get_security(cur_conn) : 0,
		.att_mtu = 0, /* TODO: bt_gatt_get_mtu(cur_conn) */
		.e2e_frames_dropped = e2e_dropped,
	};
	to_host(UWBRL_T_BLE_STATE, seq_to_host++, 0, &st, sizeof(st));
}

/* ---------------------------------------------------------- frame handlers */

static void on_host_frame(const struct uwbrl_hdr *h, const uint8_t *p)
{
	if (UWBRL_TYPE_IS_E2E(h->type)) {
		to_laptop(h->type, h->seq, h->flags, p, h->len); /* verbatim */
		return;
	}
	switch (h->type) {
	case UWBRL_T_PING:
		to_host(UWBRL_T_PONG, h->seq, 0, p, h->len);
		break;
	case UWBRL_T_HELLO: {
		struct uwbrl_hello me = { .role = 2, .proto_ver = UWBRL_PROTO_VERSION,
					  .max_payload = UWBRL_MAX_PAYLOAD };
		to_host(UWBRL_T_HELLO, seq_to_host++, 0, &me, sizeof(me));
		send_ble_state();
		break;
	}
	case UWBRL_T_BLE_CTRL:
		/* TODO(fw-m2): advertise on/off, disconnect, LED_LINK mode */
		break;
	default:
		LOG_WRN("host type 0x%02x ignored", h->type);
	}
}

static void on_laptop_frame(const struct uwbrl_hdr *h, const uint8_t *p)
{
	if (UWBRL_TYPE_IS_E2E(h->type)) {
		to_host(h->type, h->seq, h->flags, p, h->len);
	} else if (h->type == UWBRL_T_PING) {
		to_laptop(UWBRL_T_PONG, h->seq, 0, p, h->len); /* laptop<->bridge check */
	}
}

/* ---------------------------------------------------------- inputs */

static void uart_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);
	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		if (uart_irq_rx_ready(dev)) {
			uint8_t b[32];
			int n = uart_fifo_read(dev, b, sizeof(b));

			if (n > 0) {
				ring_buf_put(&uart_rx_ring, b, n);
				k_sem_give(&work_sem);
			}
		}
	}
}

static void nus_received(struct bt_conn *conn, const uint8_t *const data, uint16_t len)
{
	ARG_UNUSED(conn);
	struct uwbrl_hdr h;
	const uint8_t *p;

	/* NUS is a byte stream: frames may span or share notifications. */
	for (uint16_t i = 0; i < len; i++) {
		if (uwbrl_rx_feed(&from_laptop, data[i], &h, &p) == 1) {
			on_laptop_frame(&h, p);
		}
	}
}

static struct bt_nus_cb nus_cb = { .received = nus_received };

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		return;
	}
	cur_conn = bt_conn_ref(conn);
	/* OPEN QUESTION: required level. L2 = encrypted, unauthenticated. */
	bt_conn_set_security(conn, BT_SECURITY_L2);
	gpio_pin_set_dt(&led_link, 1);
	send_ble_state();
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(reason);
	if (cur_conn == conn) {
		bt_conn_unref(cur_conn);
		cur_conn = NULL;
	}
	gpio_pin_set_dt(&led_link, 0);
	send_ble_state();
	/* TODO(fw-m2): restart advertising (needed on some Zephyr versions). */
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
};

int main(void)
{
	struct uwbrl_hdr h;
	const uint8_t *p;
	uint8_t byte;

	if (!device_is_ready(uart)) {
		LOG_ERR("bridge UART not ready");
		return 0;
	}
	gpio_pin_configure_dt(&host_irq, GPIO_OUTPUT_INACTIVE);
	gpio_pin_configure_dt(&led_link, GPIO_OUTPUT_INACTIVE);
	uwbrl_rx_init(&from_host);
	uwbrl_rx_init(&from_laptop);
	uart_irq_callback_user_data_set(uart, uart_isr, NULL);
	uart_irq_rx_enable(uart);

	if (bt_enable(NULL) == 0) {
		settings_load();
		bt_nus_init(&nus_cb);
		bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), NULL, 0);
	} else {
		LOG_ERR("bt_enable failed; UART side still answers PING");
	}

	struct uwbrl_hello me = { .role = 2, .proto_ver = UWBRL_PROTO_VERSION,
				  .max_payload = UWBRL_MAX_PAYLOAD };
	to_host(UWBRL_T_HELLO, seq_to_host++, 0, &me, sizeof(me));

	for (;;) {
		k_sem_take(&work_sem, K_FOREVER);
		while (ring_buf_get(&uart_rx_ring, &byte, 1) == 1) {
			int r = uwbrl_rx_feed(&from_host, byte, &h, &p);

			if (r == 1) {
				on_host_frame(&h, p);
			} else if (r < 0) {
				LOG_WRN("host frame error %d", r);
			}
		}
	}
	return 0;
}
