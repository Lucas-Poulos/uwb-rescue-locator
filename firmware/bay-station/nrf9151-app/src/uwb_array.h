/*
 * Four DW3210 anchors on one SPI bus. This is the seam where the
 * multi-instance DW3000 driver goes (bay-station/README.md, fw-m3).
 *
 * The Qorvo dwt_uwb_driver API as trimmed by br101 is implicitly
 * single-instance: dwt_readdevid(void), dwt_check_dev_id(void) etc. take no
 * chip handle and act on a global context (deca_device_api.h, 08.02.02).
 * uwb_anchor_select() is where that context gets switched, under a mutex,
 * so nothing above this file ever talks to "the" DW3000.
 */
#ifndef UWB_ARRAY_H_
#define UWB_ARRAY_H_

#include <stdbool.h>
#include <stdint.h>

#include "uwbrl/meas.h"

enum uwb_role {
	UWB_ROLE_CENTER, /* A0 only */
	UWB_ROLE_OUTER,  /* A1-A3 */
};

int  uwb_array_init(void);
int  uwb_array_reset(void);           /* pulse shared UWB_RST_N */
int  uwb_tcxo_enable(bool on);        /* TCXO_EN, -ENOTSUP if not fitted */
enum uwb_role uwb_anchor_role(unsigned int idx);

/*
 * Raw DEV_ID read, no driver involved: short-addressed read of register
 * file 0x00 (header octet 0x00 -- DW3000 Datasheet v1.1 s4.9.4, Figure 16),
 * 4 bytes little-endian, at UWBRL_UWB_SPI_SLOW_HZ. Works in INIT_RC, i.e.
 * WITHOUT the shared reference clock -- so it proves SPI + CS + power +
 * reset, but NOT that the TCXO reaches the chip.
 */
int  uwb_read_dev_id_raw(unsigned int idx, uint32_t *dev_id);

/*
 * Reference-clock check: bring the anchor to IDLE_PLL, which needs the
 * external 38.4 MHz reference (Table 21: "clocked from the PLL"), and read
 * the PLL-lock status. TODO(fw-m3): needs the driver; bit names must come
 * from dwt_uwb_driver source, not memory.
 */
int  uwb_clock_check(unsigned int idx, bool *pll_locked);

int  uwb_irq_level(unsigned int idx);

#endif /* UWB_ARRAY_H_ */
