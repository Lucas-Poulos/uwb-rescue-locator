# Bay-station net contract (nRF9151 host redesign)

Global-label names every bay-station sheet wires against. It exists so the
sheets can be wired in parallel: a sheet that emits a signal and the sheet
that consumes it agree on the **name** here, and the **pin** is assigned in
exactly one place (`connectivity_notes.md`, nRF9151 GPIO allocation table).

Decided 2026-11-17 (see `decisions.md`):

- **Host MCU: Nordic nRF9151 SiP** (LTE-M/NB-IoT modem + GNSS + Cortex-M33
  application core). It has **no Bluetooth radio**.
- **The Fanstel BT840 (nRF52840) stays, demoted to a BLE bridge** to the
  laptop over UART, the same split as Nordic's Thingy:91 X (nRF9151 +
  nRF5340). The laptop link survives; LTE-M is added on top.
- **MAX-M10S removed.** The nRF9151's built-in GNSS replaces it. GNSS is
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
| `+3V3` | regulation (TPS62A02) | DW3210 x4, BT840, sensors, nRF9151 VIO (if VIO range allows -- verify). |
| `+VBAT_LTE` | regulation | nRF9151 `VBAT` supply. Source (direct from `+VSYS` through a jumper/shunt, or its own regulator) is decided on the regulation sheet after checking the nRF9151 PS VBAT range and LTE peak current. Must have a current-measurement break point. |

## 2. UWB array (uwb_array <-> connectivity)

| Net | Dir | Notes |
|---|---|---|
| `UWB_SCK`, `UWB_MOSI`, `UWB_MISO` | out/out/in | One shared SPI bus to all four DW3210. |
| `UWB_CS0_N` .. `UWB_CS3_N` | out | CS0 = A0 (center, TWR), CS1-3 = A1-A3 (outer, TDoA). |
| `UWB_IRQ0` .. `UWB_IRQ3` | in | One per anchor, same index mapping. |
| `UWB_RST_N` | od | Shared RSTn. Each anchor joins through its own 0R so one can be isolated during rework. |
| `UWB_WAKEUP` | out | Shared. |
| `UWB_SYNC` | out | Shared SYNC/OSTR. Whether it is needed is still open (decisions.md); route it anyway, it is one pin. |

## 3. Clock (clock_dist <-> uwb_array)

| Net | Notes |
|---|---|
| `TCXO_OUT` | Raw TCXO output into the 1:4 buffer (test pad). |
| `UWB_CLK0` .. `UWB_CLK3` | Buffer outputs, one per anchor, after AC coupling. Precision-critical: equal-length. |
| `TCXO_EN` | Optional enable, from the host. Omit if the chosen TCXO has none. |

## 4. Sensors (orientation <-> connectivity, power_bms)

| Net | Dir | Notes |
|---|---|---|
| `I2C_SCL`, `I2C_SDA` | od | One bus: LIS3MDL, LIS2DH, MAX17048. Replaces the old `FG_SCL`/`FG_SDA` names. Pull-ups stay R37-R39 on connectivity (re-check value). |
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
| `RESET_BLE_N` | od | nRF9151 can reset the BT840; also on the BT840 SWD header. |

## 6. Debug / programming (programming_debug <-> connectivity)

| Net | Notes |
|---|---|
| `SWDIO_MCU`, `SWDCLK_MCU`, `RESET_MCU_N` | nRF9151 SWD. |
| `SWDIO_BLE`, `SWDCLK_BLE` | BT840 SWD (reset is `RESET_BLE_N`). |
| `DBG_UART_TX`, `DBG_UART_RX` | nRF9151 log/shell UART to a header (TX from the nRF9151). |
| `BTN_USER` | User button, active low. |

## 7. Status (power_bms / indicators <-> connectivity)

| Net | Notes |
|---|---|
| `nSTAT1_LBO`, `nSTAT2`, `nPG` | MCP73871 (existing names). LEDs on indicators; routed to a host GPIO only if pins allow. |
| `LED_SYS` | nRF9151 status LED. |
| `LED_LINK` | BT840 BLE-link LED (BT840 GPIO). |
| `LED_LTE` | nRF9151 LTE status LED. |

Local to the connectivity sheet and **not** in this contract: the LTE and
GNSS antenna paths, the SIM interface, the nRF9151 COEX/MAGPIO lines that
drive any GNSS LNA, and nRF9151/BT840 decoupling.
