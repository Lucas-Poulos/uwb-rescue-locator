# Bay-station verification plan

Board-level verification for the nRF9151-host bay station, staged so each
step protects the next: nothing gets power until it has been looked at,
nothing gets firmware until its rails are right, nothing gets RF-tested
until its digital side answers. Firmware hooks are the `bringup` shell
(`firmware/bay-station/README.md`, "Bring-up shell").

Pass/fail criteria cite their source. Where the source is engineering
judgement rather than a datasheet, it says so. Where the datasheet value is
not yet in hand, the criterion is a `PLACEHOLDER` -- fill it before the test
is run, do not run the test against a guess.

**Record with every result:** board serial + revision, git hash of the
firmware, NCS version, **modem firmware version (`AT+CGMR`)**, nRF9151 build
code from the package marking, test-equipment model + cal date, ambient
temperature. RF numbers taken on different modem FW are not comparable.

## Stage 0 -- Visual and assembly inspection (unpowered)

| Check | Pass |
|---|---|
| Polarity / pin-1 of every IC, LED, diode, cell connector | Matches assembly drawing |
| nRF9151 (LGA) and DW3210 x4 (QFN40 EP) solder joints | X-ray if available: no bridges, EP voids within the assembler's IPC class; otherwise optical at the edges + Stage 1 resistance checks |
| SMA connectors (UWB x4, GNSS, LTE) | Centre pin soldered, body grounded, no flux on dielectric |
| DNP parts actually not placed (pi-match shunts, alternates) | Matches BOM `DNP` flags |
| RF series 0R / steering links in the intended position | Matches assembly drawing |

## Stage 1 -- Unpowered resistance

Meter on resistance, board unpowered, battery disconnected.

| Measure | Pass |
|---|---|
| Each rail (`+VSYS`, `+3V3`, `+VBAT_LTE`, every local rail) to `GND` | Not a short. **< 10 ohm = stop.** Record the value; compare board to board -- an outlier is the finding even if it is not a short (judgement, not datasheet) |
| Rail to rail | Not shorted to each other |
| Each UWB SMA centre to GND | DC open or the expected DC path of the match (2 pF series cap blocks DC -- `docs/positioning.md`) |
| Continuity: each test pad to its net | Per Test-point index below |

## Stage 2 -- Current-limited power-up

Bench supply into the main input, **current limit set low** (start at
100 mA -- judgement), all rail break points (0R / solder jumpers) **open**.

1. Power the input only. Current should be the charger/power-path quiescent
   draw. Any limit hit = stop.
2. Close break points **one rail at a time**: `+3V3`, then `+VBAT_LTE`, then
   local rails. Watch current at each step; raise the limit only as each
   rail proves sane.
3. Thermal check by touch / IR camera after 30 s: nothing warm that should
   not be (a hot DW3210 at idle means a solder fault).

## Stage 3 -- Rails

DMM at the rail test pads, oscilloscope for ripple and start-up.

| Rail | Pass | Source |
|---|---|---|
| `+3V3` | 3.22-3.38 V at no load and at full load (all four DW3210 in RX) | TPS62A02 VFB 591-609 mV (TI SLUSEG9E, s6.5, PWM mode) = +/-1.5 %, plus ~+/-1 % for the 1 % feedback divider. Load range must also sit inside DW3000 VDD1 1.62-3.6 V and VDD2a/b 2.4-3.6 V (DW3000 Datasheet v1.1, Table 4) |
| `+3V3` ripple | `PLACEHOLDER` -- set from the DW3210 supply guidance on the uwb sheet | DW3000 DS v1.1 power section (to cite when set) |
| `+VBAT_LTE` | Inside the nRF9151 VBAT operating range, **including during LTE TX peaks** (scope, trigger on drop during `bringup modem` attach) | `PLACEHOLDER` -- nRF9151 PS "Operating conditions" (PDF not obtained by the firmware agent) |
| `+VSYS` | Tracks the MCP73871 power-path behaviour | `bay-station/power_bms_notes.md` |
| Start-up sequence | No rail overshoot above the abs-max of any load; nRF9151 and BT840 come out of reset | Load datasheets' abs-max tables |

Current-measurement break point on `+VBAT_LTE`: insert an ammeter / current
probe here for all modem characterisation in Stage 6.

## Stage 4 -- Programming each MCU

| Step | Pass |
|---|---|
| nRF9151 SWD (`SWDIO_MCU`, `SWDCLK_MCU`, `RESET_MCU_N`) | Debugger connects, reads device info |
| Flash **modem firmware** (pinned version, `firmware/bay-station/README.md`) | `bringup modem` -> `AT+CGMR` reports it |
| Flash `nrf9151-app` (`bay_station_lte/nrf9151` for first bring-up) | Shell prompt on `DBG_UART`, `LED_SYS` heartbeat |
| BT840 SWD (`SWDIO_BLE`, `SWDCLK_BLE`, `RESET_BLE_N`) | Debugger connects |
| Flash `ble-bridge` | RTT log shows HELLO sent; laptop sees advertiser |

## Stage 5 -- Per-block functional tests

All from the `bringup` shell. Run in this order; each row depends on the
ones above it.

| Block | Command | Pass | Source / status |
|---|---|---|---|
| LEDs, button | `bringup led sys on`, `led lte on`, `btn` | Visual; press detected | -- |
| Sensor lines | `bringup lines` | Idle levels sane (e.g. `FG_ALRT` high via R39 pull-up) | -- |
| I2C | `bringup i2c scan` | Exactly 3 ACKs, at the strapped addresses | LIS3MDL 0x1C/0x1E (ST DocID024204 Rev 4, s5.1.1); LIS2DH 0x18/0x19 (ST Doc ID 022516 Rev 1, s5.1.1); MAX17048 `PLACEHOLDER` |
| I2C IDs | `bringup i2c id` | LIS3MDL WHO_AM_I = 0x3D | Verified: DocID024204 Rev 4, s7.1 Table 17 |
| | | LIS2DH WHO_AM_I = 0x33 | **UNVERIFIED** -- copy obtained was truncated before the register pages |
| | | MAX17048 VERSION | **UNVERIFIED** -- datasheet 19-6171 not obtained |
| Rails x-check | `bringup rails` | Gauge VCELL and modem VBAT agree with the DMM within the gauge's spec | MAX17048 accuracy `PLACEHOLDER` |
| UWB SPI | `bringup uwb id` | All four anchors 0xDECA0302 | `DWT_DW3000_DEV_ID`, Qorvo dwt_uwb_driver 08.02.02; not cross-checked against the DW3000 User Manual. Proves SPI/CS/power/reset only -- runs on the RC oscillator |
| UWB IRQ, reset | `bringup uwb irq`, `uwb reset` | IRQ lines low at idle; DEV_ID reads again after reset | -- |
| Reference clock | Scope `TCXO_OUT` and each `UWB_CLKn` pad; `bringup tcxo off/on` | 38.4 MHz present at every anchor, amplitude 0.8 V to VDD2 Vpp, duty 40-60 % | DW3000 DS Table 10 via `docs/positioning.md` ("TCXO selection spec") |
| | `bringup uwb clock` | PLL locked on all four | TODO in firmware (fw-m3) |
| Bridge | `bringup bridge ping 1000` | 1000/1000, 0 CRC/COBS/len errors | Protocol: `firmware/common/include/uwbrl/bridge_proto.h` |
| | `bringup bridge reset` | BT840 re-sends HELLO | -- |
| Modem | `bringup modem` | `+CGMR` = pinned FW; `%XSYSTEMMODE` = 1,0,1,1; with SIM: registers (`+CEREG` 1 or 5), `%XMONITOR` shows a cell | nRF91x1 AT Commands Reference |
| GNSS | `bringup gnss 600` outdoors | Fix within the timeout, LTE off | C/N0 criteria in Stage 6 |
| BLE | Laptop connects; `LED_LINK` on | BLE_STATE reports connected; laptop decodes STATUS frames | -- |

## Stage 6 -- RF tests

### LTE-M conducted

The normal LTE modem firmware is not a test firmware. Nordic ships a
separate **Production Test Image (PTI)** modem firmware for the nRF9151
("for production test only, with no protocol signaling"; nRF9151 Download
page, PTI 2.3.8 at time of writing), and its **`%XRFTEST`** command family
(nRF91x1 Production Test AT Commands, v1.1) covers RX power measurement at
the antenna port, TX enable with internal power measurement, RX SNR, AFC,
and a GNSS SNR test. **These commands exist only on the PTI firmware.** One
DevZone report has the TX form returning `ERROR` on an nRF91x1 -- so try TX
early and do not plan the schedule around it working. (The PTI PDF itself
was not downloadable from this environment; the above is from Nordic's
online PTI pages as indexed -- read the PDF before writing the procedure.)

| Test | Setup | Pass |
|---|---|---|
| Conducted TX power, per band used | LTE port via the conducted-test option -> attenuator -> power meter / spectrum analyser; PTI `%XRFTEST` TX, or a call-box connection on LTE FW | Within the nRF9151 PS TX power spec for that band, minus measured path loss: `PLACEHOLDER` (PS not obtained) |
| RX chain sanity | CW generator at a known level into the LTE port, PTI `%XRFTEST` RX | Reported antenna power within `PLACEHOLDER` dB of the injected level |
| Sensitivity (true, 3GPP-style) | Cellular call box | Meets the PS sensitivity figure for LTE-M: `PLACEHOLDER`. Only if a call box is available; otherwise rely on the RX sanity check + field attach |
| Match tuning | VNA on the LTE port with the pi-match pads | Return loss target `PLACEHOLDER` (antenna datasheet) across the bands used |

Re-flash the LTE modem FW afterwards and confirm with `AT+CGMR`.

### GNSS C/N0

| Test | Setup | Pass |
|---|---|---|
| C/N0 with a known antenna | Station and an **nRF9151 DK** side by side, same antenna model, same sky, same time; `bringup gnss` (and PTI GNSS SNR test if used) | Mean C/N0 of the strongest 4-6 satellites within 2 dB of the DK (judgement: a relative test, because no absolute C/N0 spec was obtained) |
| LTE/GNSS interaction | GNSS running with LTE in PSM vs LTE off | Time-to-fix and C/N0 not degraded beyond `PLACEHOLDER` |

### UWB conducted, per anchor (A0..A3)

Each anchor's SMA -> 6.5 GHz-rated attenuator -> spectrum analyser. UWB path
is SMA throughout (`docs/positioning.md`, connectors).

| Test | Setup | Pass | Source |
|---|---|---|---|
| Spectrum / centre | Continuous-frame test mode (driver function names to be taken from dwt_uwb_driver source) | Centre 6489.6 MHz, 499.2 MHz channel bandwidth | DW3000 DS v1.1 channel table |
| TX PSD | Same, RBW 1 MHz, average | Below -41.3 dBm/MHz EIRP after adding antenna gain and subtracting cable loss; max chip output -33 dBm/MHz for QFN | `docs/positioning.md` "Link budget" (Table 11). Regulatory mask itself: verify against the target region's rules before certification |
| Per-anchor match | VNA at each SMA, pi-match populated as needed | Four anchors within 1 dB of each other in return loss at 6.5 GHz (judgement) | -- |
| Relative RX sensitivity | Reference transmitter (wristband / eval board) -> step attenuator -> each anchor in turn; packet error rate vs attenuation | All four anchors within 1 dB of each other at 1 % PER (judgement) | -- |

### UWB inter-anchor timestamp skew

This is the measurement the architecture exists for (one clock, four
receivers). Uses fw-m4.

Setup: reference transmitter -> **1:4 RF splitter rated past 6.5 GHz** ->
four phase-matched cables -> A0..A3 SMA. Every anchor timestamps the same
frame; differences `dt_i = t_i - t_0` are pure fixed skew (buffer outputs +
traces + splitter + cables) plus noise.

| Measure | Pass | Source |
|---|---|---|
| Std of each `dt_i` over 1000 frames | <= ~50 ps (~1.4 cm) at a strong signal | `docs/positioning.md` error budget: ~1.4 cm differential jitter per shot |
| Mean `dt_i` stability: across power cycles, 30 min warm-up, and a cable swap | Change <= 33 ps (~1 cm) | `docs/positioning.md`: outer-anchor relative delay needs ~1 cm (~33 ps) for a 10 cm target |
| Cable swap (rotate cables between ports) | Separates cable from board skew; board part recorded per serial | -- |
| TCXO disable/enable, `UWB_SYNC` toggling | No step change in mean `dt_i` | -- |

A failing *stability* row is a hardware problem (clock distribution); a
failing *mean* is not a failure at all -- fixed skew calibrates out.

### Array calibration procedure

With the real antennas, cables and rigid frame (calibration belongs to that
set; `firmware/common/include/uwbrl/calib.h`, `frame_serial`):

1. **A1-A3 relative delays.** Tag at several stable positions (no known
   distance needed). Solve per-anchor relative delays from the measured
   TDoA against the frame's known geometry. Pass: residual per anchor
   <= 33 ps (~1 cm) -- `docs/positioning.md`.
2. **A0 absolute delay.** Tag at >= 2 surveyed distances (e.g. 5 m and
   10 m, measured independently to better than 1 cm). Pass: DS-TWR mean
   minus true distance <= 330 ps (~10 cm) -- `docs/positioning.md`.
3. Write the table, load it, confirm its CRC appears in every record.

## Stage 7 -- System tests

| Test | Pass | Source |
|---|---|---|
| Position at surveyed points, 10 m range | 30 cm single-shot; 10 cm with ~10-sample averaging | `docs/positioning.md` requirements + error budget |
| Residual metric | Rises when one antenna is deliberately obstructed | `docs/positioning.md` ("use the residual as a live quality metric") |
| Georeferencing | Survey-in average converges sub-metre against a surveyed mark; heading within `PLACEHOLDER` deg of a reference after hard/soft-iron cal *in the enclosure* | Root `CLAUDE.md`; `docs/decisions.md` (magnetometer calibration open item) |
| Knock detect | Tapping the station restarts survey-in and flags heading | `firmware/bay-station/README.md` |
| BLE link through the closed enclosure | Stable connection at the intended operator distance `PLACEHOLDER` | `docs/decisions.md` (enclosure must pass RF) |
| LTE attach + PSM | Attaches; PSM current on `+VBAT_LTE` break point within `PLACEHOLDER` | nRF9151 PS |
| LTE TX vs UWB | Skew and residual unchanged with LTE transmitting during exchanges | Judgement: rail/ground coupling check |
| Battery life | Meets target `PLACEHOLDER` (target not yet set) | -- |
| Cold charge | Charging inhibited below 0 degC | `docs/decisions.md` (NTC not yet sized) |

## Test-point index

_Placeholder -- the coordinator fills this from the io agent's test-point
table (`testpoints.kicad_sch`): one row per pad with refdes, net
(`docs/net-contract.md` name), expected value or signal, and the stage(s)
above that use it._

| TP | Net | Expect | Stage |
|---|---|---|---|
| | | | |
