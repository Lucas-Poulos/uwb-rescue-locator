/*
 * Bay station host (nRF9151). Skeleton: brings up each block and leaves the
 * bring-up shell running on DBG_UART. The exchange scheduler, timestamp
 * collection, calibration store and uplink policy are milestones fw-m4..m8
 * in firmware/README.md and are deliberately absent, not stubbed to look
 * done.
 */
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "bridge_link.h"
#include "lte_gnss.h"
#include "uwb_array.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

static const struct gpio_dt_spec led_sys = GPIO_DT_SPEC_GET(DT_ALIAS(led_sys), gpios);

int main(void)
{
	int err;

	gpio_pin_configure_dt(&led_sys, GPIO_OUTPUT_ACTIVE);

	/* Each block reports and carries on: on a new board we want the shell
	 * up even if half the blocks are dead. */
	err = uwb_array_init();
	LOG_INF("uwb_array_init: %d", err);

	err = bridge_link_init();
	LOG_INF("bridge_link_init: %d", err);

	err = lte_gnss_init();
	LOG_INF("lte_gnss_init: %d", err);

	LOG_INF("bay station up; 'bringup' shell on DBG_UART");

	for (;;) {
		gpio_pin_toggle_dt(&led_sys); /* heartbeat */
		k_sleep(K_MSEC(500));
	}
	return 0;
}
