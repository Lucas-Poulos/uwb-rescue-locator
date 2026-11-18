#include "lte_gnss.h"

#include <errno.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <modem/nrf_modem_lib.h>
#include <nrf_modem_at.h>
#include <nrf_modem_gnss.h>

LOG_MODULE_REGISTER(lte_gnss, LOG_LEVEL_INF);

static K_SEM_DEFINE(pvt_sem, 0, 1);

static void gnss_evt(int event)
{
	if (event == NRF_MODEM_GNSS_EVT_PVT) {
		k_sem_give(&pvt_sem);
	}
}

int lte_gnss_init(void)
{
	int err = nrf_modem_lib_init();

	if (err) {
		LOG_ERR("nrf_modem_lib_init: %d", err);
		return err;
	}
	/*
	 * %XSYSTEMMODE=<LTE-M>,<NB-IoT>,<GNSS>,<pref>: LTE-M + GNSS, no NB-IoT,
	 * prefer LTE-M. "Allowed only before activating the modem using
	 * +CFUN=1" (nRF91x1 AT Commands Reference, %XSYSTEMMODE set command).
	 * NB-IoT off is a proposal, not a decision -- see handoff.md.
	 */
	err = nrf_modem_at_printf("AT%%XSYSTEMMODE=1,0,1,1");
	if (err) {
		LOG_ERR("XSYSTEMMODE: %d", err);
	}
	return err;
}

int modem_at(const char *cmd, char *resp, size_t resp_len)
{
	return nrf_modem_at_cmd(resp, resp_len, "%s", cmd);
}

int gnss_bringup_fix(int timeout_s, struct gnss_snapshot *out)
{
	struct nrf_modem_gnss_pvt_data_frame pvt;
	int err;

	memset(out, 0, sizeof(*out));
	/* GNSS-only functional mode, LTE stays off: the bring-up case where the
	 * antenna and front end are tested without the time-sharing question.
	 * TODO(fw-m8): confirm CFUN=31 semantics in the nRF91x1 AT reference. */
	err = nrf_modem_at_printf("AT+CFUN=31");
	if (err) {
		return err;
	}
	nrf_modem_gnss_event_handler_set(gnss_evt);
	nrf_modem_gnss_fix_interval_set(1); /* continuous */
	err = nrf_modem_gnss_start();
	if (err) {
		return err;
	}

	int64_t deadline = k_uptime_get() + (int64_t)timeout_s * 1000;

	while (k_uptime_get() < deadline) {
		if (k_sem_take(&pvt_sem, K_SECONDS(2))) {
			continue;
		}
		if (nrf_modem_gnss_read(&pvt, sizeof(pvt), NRF_MODEM_GNSS_DATA_PVT)) {
			continue;
		}
		out->n_tracked = 0;
		out->best_cn0_dbhz_x10 = 0;
		for (size_t i = 0; i < NRF_MODEM_GNSS_MAX_SATELLITES; i++) {
			if (pvt.sv[i].sv == 0) {
				continue;
			}
			out->n_tracked++;
			if (pvt.sv[i].cn0 > out->best_cn0_dbhz_x10) {
				out->best_cn0_dbhz_x10 = pvt.sv[i].cn0;
			}
		}
		if (pvt.flags & NRF_MODEM_GNSS_PVT_FLAG_FIX_VALID) {
			out->fix_valid = true;
			out->lat_deg = pvt.latitude;
			out->lon_deg = pvt.longitude;
			out->alt_m = pvt.altitude;
			out->accuracy_m = pvt.accuracy;
			break;
		}
	}
	nrf_modem_gnss_stop();
	return out->fix_valid ? 0 : -ETIMEDOUT;
}
