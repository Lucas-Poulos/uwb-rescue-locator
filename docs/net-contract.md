# Bay-station net contract (nRF9151 host redesign)

Global-label names every bay-station sheet wires against. It exists so the
sheets can be wired in parallel: a sheet that emits a signal and the sheet
that consumes it agree on the **name** here, and the **pin** is assigned in
exactly one place: **`bay-station/connectivity_notes.md` section 2**, the
nRF9151 GPIO allocation table (pin, port, peripheral instance and drive
mode for every net below).

Decided 2026-11-17 (see `decisions.md`):

- **Host MCU: Nordic nRF9151 SiP** (LTE-M/NB-IoT modem + GNSS + Cortex-M33
  application core). It has **no Bluetooth radio**.
- **The Fanstel BT840 (nRF52840) stays, demoted to a BLE bridge** to the
  laptop over UART, the same split as Nordic's Thingy:91 X (nRF9151 +
  nRF5340). The laptop link survives; LTE-M is added on top.
- **MAX-M10S removed** (its sheet is now `orientation.kicad_sch`). The
  nRF9151's built-in GNSS replaces it. GNSS is
  time-shared with LTE (fixes only while LTE is idle / PSM / eDRX), which is
  acceptable for a stationary station doing survey-in averaging. The
  LIS3MDL magnetometer and LIS2DH accelerometer stay -- heading is still
  required.

Rules:

- Names are exact and case-sensitive. `_N` suffix = active low.
- A sheet must not invent a cross-sheet net that is not listed here. If you
  need one, add it to this file in the same change and say so.
- Every net in sections 2-7 gets a test pad on `testpoints.kicad_sch`.
- Direction column is from the nRF9151's point of view unless stated.

## 1. Rails

| Net | Source sheet | Notes |
|---|---|---|
| `GND` | -- | Single ground. |
| `+VSYS` | power_bms (MCP73871 OUT) | Unregulated system rail, existing. |
| `+5V_IN` | power_bms (barrel jack / USB-C input) | MCP73871 IN. Also the D6 (`nPG`) LED rail on indicators, because PG must not be pulled above VIN (MCP73871 DS20002090E sec 5.2.4). 0 V on battery. |
| `+3V3` | regulation (U8 TPS62A02) | DW3210 x4, clock tree, BT840, sensors, and nRF9151 **`VDD_GPIO`** (1.7-3.6 V, PS *Operating conditions*). Comes up >= 6 ms after `+VBAT_LTE` and goes first (U8 EN gated by U40 PG; nRF9151 HDG *ENABLE sequence*). The nRF9151's `VIO` pin (29) is a different thing -- a 1.8 V MIPI RFFE output, unused. Break point R300/J30. |
| `+VBAT_LTE` | regulation (U40 TPS63802 buck-boost, 3.59 V) | nRF9151 **`VDD`** pin 14 (3.0-5.5 V including ripple and spikes; ~500 mA peak at 3.7 V, 505 mA worst-case TX subframe; nRF9151 HDG) and, through R101 10k, ENABLE. Net name kept although the pin is `VDD`, not VBAT. Break point R302/J31. Why a regulator and not a jumper: `regulation_notes.md` section 1. |

**Sheet-local rails** (not contract nets, listed so nobody re-invents them):
`+3V3_SNS` (orientation, after the R411 break), `+3V3_TCXO` and `+3V3_CLKBUF`
(clock_dist, after R225/R226), `+3V3_A0`..`+3V3_A3` (uwb_array, after
R200-R203), `NRF_VDD` (connectivity, `+VBAT_LTE` after FB10), and the
regulator-side `+3V3_REG` / `+VBAT_LTE_REG` (regulation, before the break
links).

## 2. UWB array (uwb_array <-> connectivity)

| Net | Dir | Notes |
|---|---|---|
| `UWB_SCK`, `UWB_MOSI`, `UWB_MISO` | out/out/in | One shared SPI bus to all four DW3210. |
| `UWB_CS0_N` .. `UWB_CS3_N` | out | CS0 = A0 (center, TWR), CS1-3 = A1-A3 (outer, TDoA). |
| `UWB_IRQ0` .. `UWB_IRQ3` | in | One per anchor, same index mapping. |
| `UWB_RST_N` | od | Shared RSTn. Each anchor joins through its own 0R so one can be isolated during rework. Driven open-drain only -- the DW3210 RSTn must not be driven high. |
| `UWB_WAKEUP` | out | Shared. |
| `UWB_SYNC` | out | Shared SYNC/OSTR. Whether it is needed is still open (decisions.md); route it anyway, it is one pin. |

## 3. Clock (clock_dist <-> uwb_array)

| Net | Notes |
|---|---|
| `TCXO_OUT` | Raw TCXO output into the 1:4 buffer (test pad). |
| `UWB_CLK0` .. `UWB_CLK3` | Buffer outputs, one per anchor, after AC coupling. Precision-critical: equal-length. |
| ~~`TCXO_EN`~~ | **Omitted 2026-11-17**: the RPT1490LN TCXO has no enable pin (`clock_dist_notes.md`). No GPIO, no test pad. |

## 4. Sensors (orientation <-> connectivity, power_bms)

| Net | Dir | Notes |
|---|---|---|
| `I2C_SCL`, `I2C_SDA` | od | One bus: LIS3MDL 0x1C, LIS2DH 0x19, MAX17048 0x36. Replaces the old `FG_SCL`/`FG_SDA` names (done on power_bms). Pull-ups R37/R38 3.3k on connectivity (`decisions.md`, pull-ups). |
| `MAG_DRDY`, `MAG_INT` | in | LIS3MDL. |
| `ACC_INT1`, `ACC_INT2` | in | LIS2DH. INT1 = knock/move detect. |
| `FG_ALRT` | in | MAX17048 (existing name). |

## 5. BLE bridge (connectivity, nRF9151 <-> BT840)

| Net | Dir | Notes |
|---|---|---|
| `BRIDGE_TXD` | out | nRF9151 TX -> BT840 RX. |
| `BRIDGE_RXD` | in | BT840 TX -> nRF9151 RX. |
| `BRIDGE_RTS`, `BRIDGE_CTS` | out/in | Hardware flow control. |
| `BRIDGE_IRQ` | in | BT840 -> nRF9151 attention line. |
| `RESET_BLE_N` | od | nRF9151 can reset the BT840; also on the BT840 SWD header (J32) and SW11. Driven open-drain only. Lands on BT840 P0.18/RESET, which needs UICR.PSELRESET set in the bridge firmware. |

## 6. Debug / programming (programming_debug <-> connectivity)

| Net | Notes |
|---|---|
| `SWDIO_MCU`, `SWDCLK_MCU`, `RESET_MCU_N` | nRF9151 SWD (J3). `RESET_MCU_N`: **no pull-up anywhere** (HDG *nRESET*: external pull-up not allowed, 13k internal to 2.2 V); 1k series is R313 on programming_debug; 100 nF C110 at the pin on connectivity. |
| `SWDIO_BLE`, `SWDCLK_BLE` | BT840 SWD (reset is `RESET_BLE_N`). |
| `DBG_UART_TX`, `DBG_UART_RX` | nRF9151 log/shell UART to a header (TX from the nRF9151). |
| `BTN_USER` | User button, active low. |

## 7. Status (power_bms / indicators <-> connectivity)

| Net | Notes |
|---|---|
| `nSTAT1_LBO`, `nSTAT2`, `nPG` | MCP73871 (existing names). LEDs on indicators only -- **not routed to any GPIO** (out of pins, and the off-state node idles near `+VSYS`, above `VDD_GPIO`). |
| `LED_SYS` | nRF9151 status LED. |
| `LED_LINK` | BT840 BLE-link LED (BT840 GPIO). |
| `LED_LTE` | nRF9151 LTE status LED. |

Local to the connectivity sheet and **not** in this contract: the LTE and
GNSS antenna paths, the SIM interface, the nRF9151 COEX/MAGPIO lines that
drive any GNSS LNA, and nRF9151/BT840 decoupling.
