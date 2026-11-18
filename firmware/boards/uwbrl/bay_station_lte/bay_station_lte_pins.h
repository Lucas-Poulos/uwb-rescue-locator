/*
 * nRF9151 pin map for the bay station -- THE ONE PLACE pins get filled in.
 *
 * Every name below is a net from docs/net-contract.md. The pin each net
 * lands on is decided in exactly one hardware document:
 *     bay-station/connectivity_notes.md, "nRF9151 GPIO allocation"
 * Copy the numbers from there, flip UWBRL_LTE_PINS_ASSIGNED to 1, and the
 * devicetree (pinctrl + GPIO phandles) picks them up. Nothing else in
 * firmware/ names a pin number.
 *
 * Until then this header deliberately breaks the build: a skeleton that
 * compiles against guessed pins looks finished and is not
 * (firmware/CLAUDE.md, "Do not invent pin assignments").
 *
 * The nRF9151 exposes a single GPIO port (gpio0), so these are pin numbers
 * on gpio0 only -- confirm against the nRF9151 Product Specification pin
 * assignment table when filling them in.
 *
 * Included by the .dts (C preprocessor), so: #defines only, no C code.
 */
#ifndef BAY_STATION_LTE_PINS_H_
#define BAY_STATION_LTE_PINS_H_

#define UWBRL_LTE_PINS_ASSIGNED 0

#if !UWBRL_LTE_PINS_ASSIGNED
#error "nRF9151 pins not assigned: fill firmware/boards/uwbrl/bay_station_lte/bay_station_lte_pins.h from bay-station/connectivity_notes.md"
#endif

/* ---- net-contract s2: UWB array, one SPI bus (SPIM3) ------------------- */
#define PIN_UWB_SCK      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_MOSI     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_MISO     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_CS0_N    PIN_TBD /* A0 center (TWR). PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_CS1_N    PIN_TBD /* A1 outer.  PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_CS2_N    PIN_TBD /* A2 outer.  PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_CS3_N    PIN_TBD /* A3 outer.  PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_IRQ0     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_IRQ1     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_IRQ2     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_IRQ3     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_RST_N    PIN_TBD /* open-drain, shared. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_WAKEUP   PIN_TBD /* shared. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_UWB_SYNC     PIN_TBD /* shared SYNC/OSTR. PIN_TBD: see bay-station/connectivity_notes.md */

/* ---- net-contract s3: clock ------------------------------------------- */
/* Set to 0 if the chosen TCXO has no enable and TCXO_EN is omitted. */
#define HAS_TCXO_EN      1
#define PIN_TCXO_EN      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */

/* ---- net-contract s4: sensors (TWIM2) --------------------------------- */
#define PIN_I2C_SCL      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_I2C_SDA      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_MAG_DRDY     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_MAG_INT      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_ACC_INT1     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_ACC_INT2     PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_FG_ALRT      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */

/*
 * 7-bit I2C addresses. Set by address-strap pins on the orientation sheet,
 * not by firmware. Values per datasheet once the strap is known:
 *   LIS3MDL: 0x1C (SDO/SA1 = GND) or 0x1E (SDO/SA1 = VDD)
 *            -- ST DocID024204 Rev 4, Section 5.1.1 (I2C operation)
 *   LIS2DH:  0x18 (SA0 = GND) or 0x19 (SA0 = VDD)
 *            -- ST Doc ID 022516 Rev 1, Section 5.1.1
 *   MAX17048: fixed address; NOT yet verified from the datasheet (PDF
 *            download was blocked) -- confirm from 19-6171 before trusting.
 */
/* Devicetree needs each address twice: as a cell (0x..) and as the node's
 * unit address (bare hex). Keep each pair in step. */
#define I2C_ADDR_LIS3MDL  ADDR_TBD /* ADDR_TBD: SDO/SA1 strap on the orientation sheet */
#define I2C_UNIT_LIS3MDL  ADDR_TBD
#define I2C_ADDR_LIS2DH   ADDR_TBD /* ADDR_TBD: SDO/SA0 strap on the orientation sheet */
#define I2C_UNIT_LIS2DH   ADDR_TBD
#define I2C_ADDR_MAX17048 ADDR_TBD /* ADDR_TBD: verify from MAX17048 datasheet 19-6171 */
#define I2C_UNIT_MAX17048 ADDR_TBD

/* ---- net-contract s5: BLE bridge (UARTE1) ----------------------------- */
#define PIN_BRIDGE_TXD   PIN_TBD /* nRF9151 TX -> BT840 RX. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_RXD   PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_RTS   PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_CTS   PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_IRQ   PIN_TBD /* BT840 -> nRF9151. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_RESET_BLE_N  PIN_TBD /* open-drain. PIN_TBD: see bay-station/connectivity_notes.md */

/* ---- net-contract s6: debug (UARTE0 = shell/log) ---------------------- */
#define PIN_DBG_UART_TX  PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_DBG_UART_RX  PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BTN_USER     PIN_TBD /* active low. PIN_TBD: see bay-station/connectivity_notes.md */

/* ---- net-contract s7: status ------------------------------------------ */
#define PIN_LED_SYS      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_LED_LTE      PIN_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
/* MCP73871 status: routed to the host only "if pins allow" (net-contract s7). */
#define HAS_CHG_STATUS   0
#define PIN_nSTAT1_LBO   PIN_TBD
#define PIN_nSTAT2       PIN_TBD
#define PIN_nPG          PIN_TBD

/* LED polarity depends on the indicators sheet (sink vs source). */
#define LED_ACTIVE_FLAGS GPIO_ACTIVE_HIGH /* VERIFY against indicators.kicad_sch */

#endif /* BAY_STATION_LTE_PINS_H_ */
