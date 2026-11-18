#include "bridge_link.h"

#include <errno.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>

LOG_MODULE_REGISTER(bridge_link, LOG_LEVEL_INF);

#define BRIDGE_NODE DT_NODELABEL(bridge_ctrl)

static const struct device *const uart = DEVICE_DT_GET(DT_PHANDLE(BRIDGE_NODE, uart));
static const struct gpio_dt_spec irq = GPIO_DT_SPEC_GET(BRIDGE_NODE, irq_gpios);
static const struct gpio_dt_spec rst = GPIO_DT_SPEC_GET(BRIDGE_NODE, reset_gpios);

RING_BUF_DECLARE(rx_ring, 1024);
static K_SEM_DEFINE(rx_sem, 0, 1);
static K_SEM_DEFINE(pong_sem, 0, 1);
static K_MUTEX_DEFINE(tx_lock);

static struct uwbrl_rx rx_state;
static uint8_t tx_seq;
static uint8_t ping_seq;
static uint8_t pong_buf[UWBRL_MAX_PAYLOAD];
static uint16_t pong_len;

static void uart_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);
	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		if (uart_irq_rx_ready(dev)) {
			uint8_t b[32];
			int n = uart_fifo_read(dev, b, sizeof(b));

			if (n > 0 && ring_buf_put(&rx_ring, b, n) < (uint32_t)n) {
				/* Ring full: RTS deasserts in HW before this in normal
				 * operation; count it if it ever happens. TODO(fw-m2). */
			}
			k_sem_give(&rx_sem);
		}
	}
}

static int send_seq(uint8_t type, uint8_t seq, uint8_t flags, const void *payload, uint16_t len);

static void handle_frame(const struct uwbrl_hdr *h, const uint8_t *p)
{
	switch (h->type) {
	case UWBRL_T_PONG:
		if (h->seq == ping_seq && h->len <= sizeof(pong_buf)) {
			memcpy(pong_buf, p, h->len);
			pong_len = h->len;
			k_sem_give(&pong_sem);
		}
		break;
	case UWBRL_T_PING:
		send_seq(UWBRL_T_PONG, h->seq, 0, p, h->len); /* PONG echoes PING's seq */
		break;
	case UWBRL_T_HELLO:
	case UWBRL_T_BLE_STATE:
		LOG_INF("bridge msg type 0x%02x len %u", h->type, h->len);
		/* TODO(fw-m2): track BLE state, drive LED / uplink policy */
		break;
	case UWBRL_T_CMD:
		/* TODO(fw-m7): laptop commands */
		break;
	default:
		LOG_WRN("unhandled bridge type 0x%02x", h->type);
	}
}

static void rx_thread(void *a, void *b, void *c)
{
	ARG_UNUSED(a); ARG_UNUSED(b); ARG_UNUSED(c);
	uint8_t byte;
	struct uwbrl_hdr h;
	const uint8_t *p;

	for (;;) {
		k_sem_take(&rx_sem, K_FOREVER);
		while (ring_buf_get(&rx_ring, &byte, 1) == 1) {
			int r = uwbrl_rx_feed(&rx_state, byte, &h, &p);

			if (r == 1) {
				handle_frame(&h, p);
			} else if (r < 0) {
				LOG_WRN("bridge rx frame error %d", r);
			}
		}
	}
}
K_THREAD_DEFINE(bridge_rx, 2048, rx_thread, NULL, NULL, NULL, 5, 0, 0);

int bridge_link_init(void)
{
	if (!device_is_ready(uart) || !gpio_is_ready_dt(&irq) || !gpio_is_ready_dt(&rst)) {
		return -ENODEV;
	}
	uwbrl_rx_init(&rx_state);
	gpio_pin_configure_dt(&irq, GPIO_INPUT);
	gpio_pin_configure_dt(&rst, GPIO_OUTPUT_INACTIVE);
	uart_irq_callback_user_data_set(uart, uart_isr, NULL);
	uart_irq_rx_enable(uart);

	struct uwbrl_hello hello = {
		.role = 1, .proto_ver = UWBRL_PROTO_VERSION,
		.max_payload = UWBRL_MAX_PAYLOAD, .fw_build_id = 0, /* TODO: git hash */
	};
	return bridge_send(UWBRL_T_HELLO, 0, &hello, sizeof(hello));
}

int bridge_send(uint8_t type, uint8_t flags, const void *payload, uint16_t len)
{
	return send_seq(type, tx_seq++, flags, payload, len);
}

static int send_seq(uint8_t type, uint8_t seq, uint8_t flags, const void *payload, uint16_t len)
{
	static uint8_t wire[UWBRL_MAX_WIRE_FRAME];

	k_mutex_lock(&tx_lock, K_FOREVER);
	size_t n = uwbrl_frame_build(type, seq, flags, payload, len, wire);

	if (n == 0) {
		k_mutex_unlock(&tx_lock);
		return -EMSGSIZE;
	}
	/* Polled TX is fine for bring-up; CTS is honoured by the UARTE in HW.
	 * TODO(fw-m2): move to async/DMA TX for the measurement stream. */
	for (size_t i = 0; i < n; i++) {
		uart_poll_out(uart, wire[i]);
	}
	k_mutex_unlock(&tx_lock);
	return 0;
}

int bridge_ping(const void *payload, uint16_t len, int timeout_ms)
{
	k_sem_reset(&pong_sem);
	ping_seq = tx_seq;
	int64_t t0 = k_uptime_ticks();
	int err = bridge_send(UWBRL_T_PING, 0, payload, len);

	if (err) {
		return err;
	}
	if (k_sem_take(&pong_sem, K_MSEC(timeout_ms))) {
		return -ETIMEDOUT;
	}
	if (pong_len != len || memcmp(pong_buf, payload, len) != 0) {
		return -EBADMSG;
	}
	return (int)k_ticks_to_us_floor64(k_uptime_ticks() - t0);
}

int bridge_reset_ble(void)
{
	gpio_pin_set_dt(&rst, 1);
	k_msleep(1);
	return gpio_pin_set_dt(&rst, 0);
}

int bridge_irq_level(void)
{
	return gpio_pin_get_dt(&irq);
}

void bridge_stats(uint32_t *ok, uint32_t *crc_err, uint32_t *cobs_err, uint32_t *len_err)
{
	*ok = rx_state.n_ok;
	*crc_err = rx_state.n_crc_err;
	*cobs_err = rx_state.n_cobs_err;
	*len_err = rx_state.n_len_err;
}
