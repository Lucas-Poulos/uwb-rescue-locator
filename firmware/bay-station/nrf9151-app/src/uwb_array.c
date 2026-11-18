#include "uwb_array.h"

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/byteorder.h>

LOG_MODULE_REGISTER(uwb_array, LOG_LEVEL_INF);

#define A_NODE(i) DT_NODELABEL(uwb_a##i)
#define CTRL_NODE DT_NODELABEL(uwb_ctrl)

/* The anchors are not peers. Enforce the role map from devicetree at build
 * time: A0 (reg 0, CS0) must be the one and only "center". */
BUILD_ASSERT(DT_ENUM_IDX(A_NODE(0), anchor_role) == 0, "uwb_a0 must be anchor-role = \"center\"");
BUILD_ASSERT(DT_ENUM_IDX(A_NODE(1), anchor_role) == 1, "uwb_a1 must be \"outer\"");
BUILD_ASSERT(DT_ENUM_IDX(A_NODE(2), anchor_role) == 1, "uwb_a2 must be \"outer\"");
BUILD_ASSERT(DT_ENUM_IDX(A_NODE(3), anchor_role) == 1, "uwb_a3 must be \"outer\"");
BUILD_ASSERT(DT_REG_ADDR(A_NODE(0)) == 0 && DT_REG_ADDR(A_NODE(3)) == 3,
	     "anchor index must equal CS index");

/* NOTE: newer Zephyr dropped SPI_DT_SPEC_GET's delay argument; drop the
 * trailing 0 if the pinned NCS release complains. */
#define SPI_OP (SPI_OP_MODE_MASTER | SPI_WORD_SET(8) | SPI_TRANSFER_MSB) /* DW3000 SPI mode 0 */

static const struct spi_dt_spec anchors[UWBRL_N_ANCHORS] = {
	SPI_DT_SPEC_GET(A_NODE(0), SPI_OP, 0),
	SPI_DT_SPEC_GET(A_NODE(1), SPI_OP, 0),
	SPI_DT_SPEC_GET(A_NODE(2), SPI_OP, 0),
	SPI_DT_SPEC_GET(A_NODE(3), SPI_OP, 0),
};

static const struct gpio_dt_spec irqs[UWBRL_N_ANCHORS] = {
	GPIO_DT_SPEC_GET(A_NODE(0), irq_gpios),
	GPIO_DT_SPEC_GET(A_NODE(1), irq_gpios),
	GPIO_DT_SPEC_GET(A_NODE(2), irq_gpios),
	GPIO_DT_SPEC_GET(A_NODE(3), irq_gpios),
};

static const struct gpio_dt_spec rst_n = GPIO_DT_SPEC_GET(CTRL_NODE, reset_gpios);
static const struct gpio_dt_spec wakeup = GPIO_DT_SPEC_GET(CTRL_NODE, wakeup_gpios);
#if DT_NODE_HAS_PROP(CTRL_NODE, tcxo_en_gpios)
static const struct gpio_dt_spec tcxo_en = GPIO_DT_SPEC_GET(CTRL_NODE, tcxo_en_gpios);
#endif

static K_MUTEX_DEFINE(bus_lock);

enum uwb_role uwb_anchor_role(unsigned int idx)
{
	return idx == UWBRL_ANCHOR_A0 ? UWB_ROLE_CENTER : UWB_ROLE_OUTER;
}

int uwb_array_init(void)
{
	if (!gpio_is_ready_dt(&rst_n) || !gpio_is_ready_dt(&wakeup)) {
		return -ENODEV;
	}
	/* RSTn: "May be pulled low by external open drain driver to reset the
	 * DW3000. Must not be pulled high by external source." (DW3000
	 * Datasheet v1.1, pin description table, RSTn row). GPIO_OPEN_DRAIN in the
	 * devicetree makes "inactive" mean high-Z. */
	gpio_pin_configure_dt(&rst_n, GPIO_OUTPUT_INACTIVE);
	gpio_pin_configure_dt(&wakeup, GPIO_OUTPUT_INACTIVE);
#if DT_NODE_HAS_PROP(CTRL_NODE, tcxo_en_gpios)
	gpio_pin_configure_dt(&tcxo_en, GPIO_OUTPUT_ACTIVE);
#endif
	for (unsigned int i = 0; i < UWBRL_N_ANCHORS; i++) {
		if (!spi_is_ready_dt(&anchors[i]) || !gpio_is_ready_dt(&irqs[i])) {
			return -ENODEV;
		}
		gpio_pin_configure_dt(&irqs[i], GPIO_INPUT);
	}
	return 0;
}

int uwb_array_reset(void)
{
	gpio_pin_set_dt(&rst_n, 1);
	k_msleep(1);
	gpio_pin_set_dt(&rst_n, 0);
	/* TODO(fw-m3): replace with the cold/warm-start timing from DW3000
	 * Datasheet v1.1 Figures 21/22 (or poll SPIRDY via the driver). */
	k_msleep(5);
	return 0;
}

int uwb_tcxo_enable(bool on)
{
#if DT_NODE_HAS_PROP(CTRL_NODE, tcxo_en_gpios)
	return gpio_pin_set_dt(&tcxo_en, on ? 1 : 0);
#else
	ARG_UNUSED(on);
	return -ENOTSUP;
#endif
}

int uwb_read_dev_id_raw(unsigned int idx, uint32_t *dev_id)
{
	if (idx >= UWBRL_N_ANCHORS) {
		return -EINVAL;
	}
	struct spi_dt_spec slow = anchors[idx];

	slow.config.frequency = CONFIG_UWBRL_UWB_SPI_SLOW_HZ;

	/* Short-addressed read, base 0x00, RD: header octet 0x00. */
	uint8_t tx[5] = { 0x00, 0, 0, 0, 0 };
	uint8_t rx[5] = { 0 };
	const struct spi_buf txb = { .buf = tx, .len = sizeof(tx) };
	const struct spi_buf rxb = { .buf = rx, .len = sizeof(rx) };
	const struct spi_buf_set txs = { .buffers = &txb, .count = 1 };
	const struct spi_buf_set rxs = { .buffers = &rxb, .count = 1 };

	k_mutex_lock(&bus_lock, K_FOREVER);
	int err = spi_transceive_dt(&slow, &txs, &rxs);

	k_mutex_unlock(&bus_lock);
	if (err) {
		return err;
	}
	*dev_id = sys_get_le32(&rx[1]);
	return 0;
}

int uwb_clock_check(unsigned int idx, bool *pll_locked)
{
	ARG_UNUSED(idx);
	*pll_locked = false;
	return -ENOSYS; /* TODO(fw-m3): needs the multi-instance driver */
}

int uwb_irq_level(unsigned int idx)
{
	return idx < UWBRL_N_ANCHORS ? gpio_pin_get_dt(&irqs[idx]) : -EINVAL;
}
