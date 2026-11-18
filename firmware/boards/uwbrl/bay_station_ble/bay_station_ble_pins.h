/*
 * BT840 (nRF52840) pin map for the bay station's BLE bridge -- the one
 * place its pins get filled in, from bay-station/connectivity_notes.md
 * (BT840 GPIO allocation). Same rules as bay_station_lte_pins.h: names are
 * docs/net-contract.md nets, numbers are PIN_TBD, and the build stops
 * until someone fills them in.
 *
 * The nRF52840 has two GPIO ports, so each net needs PORT and PIN.
 * Net directions below are as seen from the nRF9151 (net-contract s5), so
 * BRIDGE_TXD is the BT840's *RX* and BRIDGE_RTS is the BT840's *CTS*.
 *
 * RESET_BLE_N is not here: it lands on the module's nRESET pad, which is
 * fixed by the nRF52840 silicon, not chosen. Confirm which BT840 pad that is
 * from the Fanstel BT840 datasheet when wiring.
 */
#ifndef BAY_STATION_BLE_PINS_H_
#define BAY_STATION_BLE_PINS_H_

#define UWBRL_BLE_PINS_ASSIGNED 0

#if !UWBRL_BLE_PINS_ASSIGNED
#error "BT840 pins not assigned: fill firmware/boards/uwbrl/bay_station_ble/bay_station_ble_pins.h from bay-station/connectivity_notes.md"
#endif

/* BRIDGE_TXD: nRF9151 TX -> BT840 RX */
#define PORT_BRIDGE_TXD  PORT_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_TXD   PIN_TBD
/* BRIDGE_RXD: BT840 TX -> nRF9151 RX */
#define PORT_BRIDGE_RXD  PORT_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_RXD   PIN_TBD
/* BRIDGE_RTS: nRF9151 RTS -> BT840 CTS */
#define PORT_BRIDGE_RTS  PORT_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_RTS   PIN_TBD
/* BRIDGE_CTS: BT840 RTS -> nRF9151 CTS */
#define PORT_BRIDGE_CTS  PORT_TBD /* PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_CTS   PIN_TBD
/* BRIDGE_IRQ: BT840 -> nRF9151 attention line (output here) */
#define GPIO_BRIDGE_IRQ  gpio0    /* gpio0 or gpio1. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_BRIDGE_IRQ   PIN_TBD
/* LED_LINK: BLE link LED */
#define GPIO_LED_LINK    gpio0    /* gpio0 or gpio1. PIN_TBD: see bay-station/connectivity_notes.md */
#define PIN_LED_LINK     PIN_TBD
#define LED_LINK_FLAGS   GPIO_ACTIVE_HIGH /* VERIFY against indicators.kicad_sch */

#endif /* BAY_STATION_BLE_PINS_H_ */
