/*
 * 'bringup' shell: one command per board block, used step-by-step by
 * docs/verification-plan.md (stage 6, per-block functional tests).
 *
 * Every expected value is cited or marked UNVERIFIED. A test that prints
 * "UNVERIFIED" is reporting what it read, not judging it.
 */
#include <stdlib.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "bridge_link.h"
#include "lte_gnss.h"
#include "uwb_array.h"

/* ------------------------------------------------------------------ I2C */

static const struct device *const i2c = DEVICE_DT_GET(DT_NODELABEL(i2c2));

#define LIS3MDL_ADDR  DT_REG_ADDR(DT_NODELABEL(lis3mdl))
#define LIS2DH_ADDR   DT_REG_ADDR(DT_NODELABEL(lis2dh))
#define MAX17048_ADDR DT_REG_ADDR(DT_NODELABEL(max17048))

/* LIS3MDL WHO_AM_I @0x0F = 0x3D: ST DocID024204 Rev 4, s7.1 Table 17 and
 * Table 16 register map. VERIFIED from the PDF. */
#define LIS3MDL_REG_WHO_AM_I 0x0F
#define LIS3MDL_WHO_AM_I     0x3D
/* LIS2DH WHO_AM_I @0x0F: register exists (ST Doc ID 022516 Rev 1, s7.4,
 * listed in the contents), but the copy we could obtain was truncated
 * before the register pages. 0x33 is UNVERIFIED -- do not "fix" a board
 * that reads something else until the full PDF is checked. */
#define LIS2DH_REG_WHO_AM_I  0x0F
#define LIS2DH_WHO_AM_I_UNVERIFIED 0x33
/* MAX17048: VERSION and VCELL register addresses and scaling are
 * UNVERIFIED (datasheet 19-6171 download was blocked). The values below
 * are placeholders to be confirmed before trusting any pass/fail. */
#define MAX17048_REG_VCELL_PLACEHOLDER   0x02
#define MAX17048_REG_VERSION_PLACEHOLDER 0x08

static int i2c_rd8(uint16_t addr, uint8_t reg, uint8_t *v)
{
	return i2c_write_read(i2c, addr, &reg, 1, v, 1);
}

static int i2c_rd16be(uint16_t addr, uint8_t reg, uint16_t *v)
{
	uint8_t b[2];
	int err = i2c_write_read(i2c, addr, &reg, 1, b, 2);

	*v = (uint16_t)((b[0] << 8) | b[1]);
	return err;
}

static int cmd_i2c_scan(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	int found = 0;

	/* 1-byte read probe: TWIM does not do zero-length transfers well.
	 * A read is harmless for all three devices on this bus. */
	for (uint16_t a = 0x08; a < 0x78; a++) {
		uint8_t b;

		if (i2c_read(i2c, &b, 1, a) == 0) {
			shell_print(sh, "  0x%02x ACK", a);
			found++;
		}
	}
	shell_print(sh, "%d device(s); expect 3 (LIS3MDL 0x%02x, LIS2DH 0x%02x, MAX17048 0x%02x)",
		    found, LIS3MDL_ADDR, LIS2DH_ADDR, MAX17048_ADDR);
	return found == 3 ? 0 : -EIO;
}

static int cmd_i2c_id(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	uint8_t v;
	uint16_t w;
	int fails = 0;

	if (i2c_rd8(LIS3MDL_ADDR, LIS3MDL_REG_WHO_AM_I, &v) == 0) {
		bool ok = v == LIS3MDL_WHO_AM_I;

		shell_print(sh, "LIS3MDL  WHO_AM_I=0x%02x %s", v, ok ? "PASS" : "FAIL (want 0x3D)");
		fails += !ok;
	} else {
		shell_error(sh, "LIS3MDL  no response at 0x%02x", LIS3MDL_ADDR);
		fails++;
	}
	if (i2c_rd8(LIS2DH_ADDR, LIS2DH_REG_WHO_AM_I, &v) == 0) {
		shell_print(sh, "LIS2DH   WHO_AM_I=0x%02x (UNVERIFIED expectation 0x%02x)", v,
			    LIS2DH_WHO_AM_I_UNVERIFIED);
	} else {
		shell_error(sh, "LIS2DH   no response at 0x%02x", LIS2DH_ADDR);
		fails++;
	}
	if (i2c_rd16be(MAX17048_ADDR, MAX17048_REG_VERSION_PLACEHOLDER, &w) == 0) {
		shell_print(sh, "MAX17048 VERSION(?)=0x%04x (register + value UNVERIFIED)", w);
	} else {
		shell_error(sh, "MAX17048 no response at 0x%02x", MAX17048_ADDR);
		fails++;
	}
	return fails ? -EIO : 0;
}

static int cmd_rails(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	uint16_t w;
	char resp[64];

	/* No rail-sense net exists in docs/net-contract.md, so the host can
	 * only see rails indirectly. Measure rails with a DMM at the test pads
	 * (verification-plan stage 4); these are cross-checks. */
	if (i2c_rd16be(MAX17048_ADDR, MAX17048_REG_VCELL_PLACEHOLDER, &w) == 0) {
		shell_print(sh, "MAX17048 VCELL raw=0x%04x (scale UNVERIFIED -- see 19-6171)", w);
	}
	/* Modem's own view of VBAT (= +VBAT_LTE). TODO(fw-m1): confirm
	 * %XVBAT in the nRF91x1 AT reference for the pinned modem FW. */
	if (modem_at("AT%XVBAT", resp, sizeof(resp)) == 0) {
		shell_print(sh, "+VBAT_LTE (modem): %s", resp);
	}
	/* TODO(fw-m1): SAADC on an internal VDD channel, if the nRF9151 SAADC
	 * offers one (check PS SAADC input list) -- otherwise propose a
	 * VSYS_SENSE divider net (handoff.md). */
	return 0;
}

/* ------------------------------------------------------------------ UWB */

/*
 * DEV_ID: RIDTAG 0xDECA in [31:16], MODEL [15:8], VER [7:4], REV [3:0]
 * (dw3000_deca_regs.h DEV_ID_* masks, dwt_uwb_driver 08.02.02).
 * Non-PDoA DW3000 = 0xDECA0302 (deca_device_api.h DWT_DW3000_DEV_ID). The
 * DW3210 is the non-PDoA QFN part (DW3000 Datasheet Table 1). Not checked
 * against the DW3000 User Manual (not obtained). REV is compared loosely
 * so a silicon revision bump reads as WARN, not FAIL.
 */
#define DW3000_DEV_ID_NONPDOA 0xDECA0302u
#define DW3000_DEV_ID_REV_MASK 0x0000000Fu

static int cmd_uwb_id(const struct shell *sh, size_t argc, char **argv)
{
	unsigned int lo = 0, hi = UWBRL_N_ANCHORS - 1;
	int fails = 0;

	if (argc > 1) {
		lo = hi = (unsigned int)strtoul(argv[1], NULL, 0);
	}
	for (unsigned int i = lo; i <= hi; i++) {
		uint32_t id = 0;
		int err = uwb_read_dev_id_raw(i, &id);
		const char *role = uwb_anchor_role(i) == UWB_ROLE_CENTER ? "center" : "outer";

		if (err) {
			shell_error(sh, "A%u (%s) SPI error %d", i, role, err);
			fails++;
		} else if (id == DW3000_DEV_ID_NONPDOA) {
			shell_print(sh, "A%u (%s) DEV_ID=0x%08x PASS", i, role, id);
		} else if ((id & ~DW3000_DEV_ID_REV_MASK) ==
			   (DW3000_DEV_ID_NONPDOA & ~DW3000_DEV_ID_REV_MASK)) {
			shell_warn(sh, "A%u (%s) DEV_ID=0x%08x WARN (rev differs)", i, role, id);
		} else {
			/* 0x00000000 / 0xFFFFFFFF: MISO stuck, CS not reaching, no
			 * power, held in reset. */
			shell_error(sh, "A%u (%s) DEV_ID=0x%08x FAIL", i, role, id);
			fails++;
		}
	}
	shell_print(sh, "note: DEV_ID works on the RC oscillator; it does NOT prove the TCXO. Use 'bringup uwb clock'.");
	return fails ? -EIO : 0;
}

static int cmd_uwb_reset(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	shell_print(sh, "UWB_RST_N pulse: %d", uwb_array_reset());
	return 0;
}

static int cmd_uwb_irq(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	for (unsigned int i = 0; i < UWBRL_N_ANCHORS; i++) {
		shell_print(sh, "UWB_IRQ%u = %d", i, uwb_irq_level(i));
	}
	return 0;
}

static int cmd_uwb_clock(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	for (unsigned int i = 0; i < UWBRL_N_ANCHORS; i++) {
		bool locked;
		int err = uwb_clock_check(i, &locked);

		shell_print(sh, "A%u PLL lock: %s (err %d)", i,
			    err ? "n/a" : (locked ? "PASS" : "FAIL"), err);
	}
	shell_print(sh, "TODO(fw-m3): needs the driver. Until then: scope TCXO_OUT and UWB_CLK0..3 test pads.");
	return 0;
}

/* --------------------------------------------------------------- bridge */

static int cmd_bridge_ping(const struct shell *sh, size_t argc, char **argv)
{
	int n = argc > 1 ? atoi(argv[1]) : 10;
	int ok = 0;
	uint8_t pat[64];

	for (size_t i = 0; i < sizeof(pat); i++) {
		pat[i] = (uint8_t)(i * 37u); /* includes 0x00 -> exercises COBS */
	}
	for (int i = 0; i < n; i++) {
		int us = bridge_ping(pat, sizeof(pat), CONFIG_UWBRL_BRIDGE_PING_TIMEOUT_MS);

		if (us >= 0) {
			ok++;
			shell_print(sh, "ping %d: %d us", i, us);
		} else {
			shell_error(sh, "ping %d: %d", i, us);
		}
	}
	uint32_t f_ok, f_crc, f_cobs, f_len;

	bridge_stats(&f_ok, &f_crc, &f_cobs, &f_len);
	shell_print(sh, "%d/%d ok; rx frames ok=%u crc=%u cobs=%u len=%u; BRIDGE_IRQ=%d",
		    ok, n, f_ok, f_crc, f_cobs, f_len, bridge_irq_level());
	return ok == n ? 0 : -EIO;
}

static int cmd_bridge_reset(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	shell_print(sh, "RESET_BLE_N pulse: %d (expect a HELLO from the BT840)", bridge_reset_ble());
	return 0;
}

/* ---------------------------------------------------------------- modem */

static int cmd_modem_check(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	/* Modem FW version first: the app is only valid against the modem FW
	 * versions listed in Nordic's nRF9151 compatibility matrix. */
	static const char *const cmds[] = {
		"AT+CGMR", "AT%XSYSTEMMODE?", "AT+CFUN?", "AT%XMONITOR", "AT+CEREG?",
	};
	char resp[256];

	for (size_t i = 0; i < ARRAY_SIZE(cmds); i++) {
		int err = modem_at(cmds[i], resp, sizeof(resp));

		shell_print(sh, "%s -> %s", cmds[i], err ? "ERROR" : resp);
	}
	return 0;
}

static int cmd_gnss(const struct shell *sh, size_t argc, char **argv)
{
	int timeout = argc > 1 ? atoi(argv[1]) : 300;
	struct gnss_snapshot s;

	shell_print(sh, "GNSS-only (LTE off), cold start, up to %d s, needs sky view...", timeout);
	int err = gnss_bringup_fix(timeout, &s);

	shell_print(sh, "tracked=%u best_cn0=%u.%u dB-Hz (unit UNVERIFIED)", s.n_tracked,
		    s.best_cn0_dbhz_x10 / 10, s.best_cn0_dbhz_x10 % 10);
	if (!err) {
		shell_print(sh, "FIX %.6f, %.6f alt %.1f m acc %.1f m", s.lat_deg, s.lon_deg,
			    (double)s.alt_m, (double)s.accuracy_m);
	} else {
		shell_error(sh, "no fix: %d", err);
	}
	return err;
}

/* -------------------------------------------------------- LEDs, button */

static const struct gpio_dt_spec led_sys = GPIO_DT_SPEC_GET(DT_ALIAS(led_sys), gpios);
static const struct gpio_dt_spec led_lte = GPIO_DT_SPEC_GET(DT_ALIAS(led_lte), gpios);
static const struct gpio_dt_spec btn = GPIO_DT_SPEC_GET(DT_ALIAS(btn_user), gpios);

static int cmd_led(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 3) {
		shell_error(sh, "usage: bringup led <sys|lte> <on|off>");
		return -EINVAL;
	}
	const struct gpio_dt_spec *l = strcmp(argv[1], "lte") == 0 ? &led_lte : &led_sys;

	gpio_pin_configure_dt(l, GPIO_OUTPUT);
	return gpio_pin_set_dt(l, strcmp(argv[2], "on") == 0);
}

static int cmd_btn(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	gpio_pin_configure_dt(&btn, GPIO_INPUT);
	shell_print(sh, "BTN_USER now %d; press within 10 s...", gpio_pin_get_dt(&btn));
	for (int i = 0; i < 1000; i++) {
		if (gpio_pin_get_dt(&btn) == 1) {
			shell_print(sh, "BTN_USER pressed: PASS");
			return 0;
		}
		k_msleep(10);
	}
	shell_error(sh, "BTN_USER: no press seen");
	return -ETIMEDOUT;
}

#define SIRQ DT_NODELABEL(sensor_irqs)
#define SIRQ_SPEC(node, prop, idx) GPIO_DT_SPEC_GET_BY_IDX(node, prop, idx),
static const struct gpio_dt_spec sensor_lines[] = { DT_FOREACH_PROP_ELEM(SIRQ, gpios, SIRQ_SPEC) };
static const char *const sensor_names[] = DT_PROP(SIRQ, gpio_names);

static int cmd_lines(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	for (size_t i = 0; i < ARRAY_SIZE(sensor_lines); i++) {
		gpio_pin_configure_dt(&sensor_lines[i], GPIO_INPUT);
		shell_print(sh, "%-9s = %d", sensor_names[i], gpio_pin_get_dt(&sensor_lines[i]));
	}
	return 0;
}

/* ---------------------------------------------------------------- table */

SHELL_STATIC_SUBCMD_SET_CREATE(sub_i2c,
	SHELL_CMD(scan, NULL, "Probe 0x08-0x77 on I2C_SCL/I2C_SDA", cmd_i2c_scan),
	SHELL_CMD(id, NULL, "WHO_AM_I / VERSION for LIS3MDL, LIS2DH, MAX17048", cmd_i2c_id),
	SHELL_SUBCMD_SET_END);

SHELL_STATIC_SUBCMD_SET_CREATE(sub_uwb,
	SHELL_CMD_ARG(id, NULL, "[anchor] raw DEV_ID read per DW3210", cmd_uwb_id, 1, 1),
	SHELL_CMD(reset, NULL, "Pulse shared UWB_RST_N", cmd_uwb_reset),
	SHELL_CMD(irq, NULL, "Read UWB_IRQ0..3 levels", cmd_uwb_irq),
	SHELL_CMD(clock, NULL, "Reference-clock / PLL lock per anchor (TODO)", cmd_uwb_clock),
	SHELL_SUBCMD_SET_END);

SHELL_STATIC_SUBCMD_SET_CREATE(sub_bridge,
	SHELL_CMD_ARG(ping, NULL, "[n] PING/PONG over BRIDGE_* UART", cmd_bridge_ping, 1, 1),
	SHELL_CMD(reset, NULL, "Pulse RESET_BLE_N", cmd_bridge_reset),
	SHELL_SUBCMD_SET_END);

SHELL_STATIC_SUBCMD_SET_CREATE(sub_bringup,
	SHELL_CMD(rails, NULL, "Indirect rail readings (fuel gauge, modem VBAT)", cmd_rails),
	SHELL_CMD(i2c, &sub_i2c, "Sensor bus", NULL),
	SHELL_CMD(uwb, &sub_uwb, "DW3210 anchors", NULL),
	SHELL_CMD(bridge, &sub_bridge, "BT840 bridge link", NULL),
	SHELL_CMD(modem, NULL, "AT+CGMR, %XSYSTEMMODE?, +CFUN?, %XMONITOR, +CEREG?", cmd_modem_check),
	SHELL_CMD_ARG(gnss, NULL, "[timeout_s] GNSS-only fix + C/N0", cmd_gnss, 1, 1),
	SHELL_CMD_ARG(led, NULL, "<sys|lte> <on|off>", cmd_led, 3, 0),
	SHELL_CMD(btn, NULL, "Wait for BTN_USER press", cmd_btn),
	SHELL_CMD(lines, NULL, "Read MAG_DRDY, MAG_INT, ACC_INT1/2, FG_ALRT", cmd_lines),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(bringup, &sub_bringup, "Bay-station board bring-up tests", NULL);
