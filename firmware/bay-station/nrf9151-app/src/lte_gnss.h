/*
 * Modem: LTE-M uplink and built-in GNSS, time-shared on one radio.
 * Plan in bay-station/README.md "Modem and GNSS time-sharing".
 */
#ifndef LTE_GNSS_H_
#define LTE_GNSS_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

int lte_gnss_init(void);                       /* nrf_modem_lib_init + system mode */
int modem_at(const char *cmd, char *resp, size_t resp_len);

struct gnss_snapshot {
	bool     fix_valid;
	double   lat_deg, lon_deg;
	float    alt_m, accuracy_m;
	uint8_t  n_tracked;
	uint16_t best_cn0_dbhz_x10; /* as reported by the modem, 0.1 dB-Hz -- verify unit */
};

/* Start GNSS with LTE off (AT+CFUN=31 path) and wait up to timeout_s. */
int gnss_bringup_fix(int timeout_s, struct gnss_snapshot *out);

#endif /* LTE_GNSS_H_ */
