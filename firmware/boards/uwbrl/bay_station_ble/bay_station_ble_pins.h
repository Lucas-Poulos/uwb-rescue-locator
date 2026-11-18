/*
 * BT840 (nRF52840) pin map for the bay station's BLE bridge -- the one
 * place its pins get filled in, from bay-station/connectivity_notes.md
 * (BT840 GPIO allocation). Same rules as bay_station_lte_pins.h: names are
 * docs/net-contract.md nets; numbers come from the schematic.
 *
 * The nRF52840 has two GPIO ports, so each net needs PORT and PIN.
 * Net directions below are as seen from the nRF9151 (net-contract s5), so
 * BRIDGE_TXD is the BT840's *RX* and BRIDGE_RTS is the BT840's *CTS*.
 *
 * RESET_BLE_N is not here: it lands on BT840 pad 14, P0.18/RESET -- the
 * nRF52840's fixed pin-reset pin. It only acts as a reset once UICR
 * PSELRESET[0..1] are programmed to P0.18 (CONFIG_GPIO_AS_PINRESET=y);
 * until then SW11, the J32 header and the nRF9151 cannot reset the BT840.
 *
 * Filled 2026-11-17 and cross-checked against the merged schematic netlist.
 */
#ifndef BAY_STATION_BLE_PINS_H_
#define BAY_STATION_BLE_PINS_H_

#define UWBRL_BLE_PINS_ASSIGNED 1

#if !UWBRL_BLE_PINS_ASSIGNED
#error "BT840 pins not assigned: fill firmware/boards/uwbrl/bay_station_ble/bay_station_ble_pins.h from bay-station/connectivity_notes.md"
#endif

/* BRIDGE_TXD: nRF9151 TX -> BT840 RX */
#define PORT_BRIDGE_TXD  0 /* P0.26 */
#define PIN_BRIDGE_TXD   26
/* BRIDGE_RXD: BT840 TX -> nRF9151 RX */
#define PORT_BRIDGE_RXD  0 /* P0.27 */
#define PIN_BRIDGE_RXD   27
/* BRIDGE_RTS: nRF9151 RTS -> BT840 CTS */
#define PORT_BRIDGE_RTS  1 /* P1.00 */
#define PIN_BRIDGE_RTS   0
/* BRIDGE_CTS: BT840 RTS -> nRF9151 CTS */
#define PORT_BRIDGE_CTS  0 /* P0.11 */
#define PIN_BRIDGE_CTS   11
/* BRIDGE_IRQ: BT840 -> nRF9151 attention line (output here) */
#define GPIO_BRIDGE_IRQ  gpio0    /* P0.13 */
#define PIN_BRIDGE_IRQ   13
/* LED_LINK: BLE link LED */
#define GPIO_LED_LINK    gpio0    /* P0.02 */
#define PIN_LED_LINK     2
#define LED_LINK_FLAGS   GPIO_ACTIVE_HIGH /* sourced via 1.2k (indicators.kicad_sch) */

#endif /* BAY_STATION_BLE_PINS_H_ */
