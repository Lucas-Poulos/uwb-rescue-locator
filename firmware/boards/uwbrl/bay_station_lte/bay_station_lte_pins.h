/*
 * nRF9151 pin map for the bay station -- THE ONE PLACE pins get filled in.
 *
 * Every name below is a net from docs/net-contract.md. The pin each net
 * lands on is decided in exactly one hardware document:
 *     bay-station/connectivity_notes.md, "nRF9151 GPIO allocation"
 * Filled 2026-11-17 from that table, and cross-checked pin by pin against
 * `kicad-cli sch export netlist` of the merged schematic (every nRF9151 GPIO
 * lands on the net named here, some through 0R rework links). If the
 * schematic moves a pin, change it there first, then here. Nothing else in
 * firmware/ names a pin number.
 *
 * The nRF9151 exposes a single GPIO port (gpio0), so these are pin numbers
 * on gpio0 only -- confirm against the nRF9151 Product Specification pin
 * assignment table when filling them in.
 *
 * Included by the .dts (C preprocessor), so: #defines only, no C code.
 */
#ifndef BAY_STATION_LTE_PINS_H_
#define BAY_STATION_LTE_PINS_H_

#define UWBRL_LTE_PINS_ASSIGNED 1

#if !UWBRL_LTE_PINS_ASSIGNED
#error "nRF9151 pins not assigned: fill firmware/boards/uwbrl/bay_station_lte/bay_station_lte_pins.h from bay-station/connectivity_notes.md"
#endif

/* ---- net-contract s2: UWB array, one SPI bus (SPIM3) ------------------- */
#define PIN_UWB_SCK      13      /* P0.13 */
#define PIN_UWB_MOSI     14      /* P0.14 */
#define PIN_UWB_MISO     15      /* P0.15 */
#define PIN_UWB_CS0_N    16      /* P0.16 -- A0 center (TWR). */
#define PIN_UWB_CS1_N    17      /* P0.17 -- A1 outer. */
#define PIN_UWB_CS2_N    18      /* P0.18 -- A2 outer. */
#define PIN_UWB_CS3_N    19      /* P0.19 -- A3 outer. */
#define PIN_UWB_IRQ0     8       /* P0.08 */
#define PIN_UWB_IRQ1     9       /* P0.09 */
#define PIN_UWB_IRQ2     10      /* P0.10 */
#define PIN_UWB_IRQ3     11      /* P0.11 */
#define PIN_UWB_RST_N    12      /* P0.12 -- open-drain, shared. */
#define PIN_UWB_WAKEUP   20      /* P0.20 -- shared. */
#define PIN_UWB_SYNC     21      /* P0.21 -- shared SYNC/OSTR. */

/* ---- net-contract s3: clock ------------------------------------------- */
/* TCXO_EN omitted: the RPT1490LN has no enable pin (clock_dist_notes.md). */
#define HAS_TCXO_EN      0

/* ---- net-contract s4: sensors (TWIM2) --------------------------------- */
#define PIN_I2C_SCL      5       /* P0.05 */
#define PIN_I2C_SDA      6       /* P0.06 */
#define PIN_MAG_DRDY     24      /* P0.24 */
#define PIN_MAG_INT      25      /* P0.25 */
#define PIN_ACC_INT1     7       /* P0.07 */
#define PIN_ACC_INT2     26      /* P0.26 */
#define PIN_FG_ALRT      27      /* P0.27 */

/*
 * 7-bit I2C addresses. Set by address-strap pins on the orientation sheet,
 * not by firmware. Values per datasheet once the strap is known:
 *   LIS3MDL: 0x1C (SDO/SA1 = GND) or 0x1E (SDO/SA1 = VDD)
 *            -- ST DocID024204 Rev 4, Section 5.1.1 (I2C operation)
 *   LIS2DH:  0x18 (SA0 = GND) or 0x19 (SA0 = VDD)
 *            -- ST Doc ID 022516 Rev 1, Section 5.1.1
 *   MAX17048: 0x36 fixed -- Maxim 19-6171 Rev 7, "Slave Address"
 */
/* Devicetree needs each address twice: as a cell (0x..) and as the node's
 * unit address (bare hex). Keep each pair in step. */
#define I2C_ADDR_LIS3MDL  0x1c /* SDO/SA1 -> GND via R412 (orientation sheet) */
#define I2C_UNIT_LIS3MDL  1c
#define I2C_ADDR_LIS2DH   0x19 /* SDO/SA0 -> Vdd_IO via R414 (orientation sheet) */
#define I2C_UNIT_LIS2DH   19
#define I2C_ADDR_MAX17048 0x36 /* fixed, 19-6171 Rev 7 "Slave Address" 0110110 (io handoff) */
#define I2C_UNIT_MAX17048 36

/* ---- net-contract s5: BLE bridge (UARTE1) ----------------------------- */
#define PIN_BRIDGE_TXD   0       /* P0.00 -- nRF9151 TX -> BT840 RX. */
#define PIN_BRIDGE_RXD   1       /* P0.01 */
#define PIN_BRIDGE_RTS   2       /* P0.02 */
#define PIN_BRIDGE_CTS   3       /* P0.03 */
#define PIN_BRIDGE_IRQ   4       /* P0.04 -- BT840 -> nRF9151. */
#define PIN_RESET_BLE_N  28      /* P0.28 -- open-drain. */

/* ---- net-contract s6: debug (UARTE0 = shell/log) ---------------------- */
#define PIN_DBG_UART_TX  22      /* P0.22 */
#define PIN_DBG_UART_RX  23      /* P0.23 */
#define PIN_BTN_USER     29      /* P0.29 -- active low. */

/* ---- net-contract s7: status ------------------------------------------ */
#define PIN_LED_SYS      30      /* P0.30 */
#define PIN_LED_LTE      31      /* P0.31 */
/* MCP73871 status: LEDs only, never a GPIO -- all 32 GPIOs are used, and the
 * open-drain LED nodes idle near +VSYS (connectivity_notes.md s2). */
#define HAS_CHG_STATUS   0

/* LED polarity depends on the indicators sheet (sink vs source). */
#define LED_ACTIVE_FLAGS GPIO_ACTIVE_HIGH /* GPIO sources ~1.1 mA via 1.2k (indicators.kicad_sch) */

#endif /* BAY_STATION_LTE_PINS_H_ */
