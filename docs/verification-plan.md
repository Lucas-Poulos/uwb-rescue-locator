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
| SMA connectors (UWB x4) and u.FL (J10 LTE, J11 GNSS, J13 DNP) | Centre pin soldered, body grounded, no flux on dielectric |
| DNP parts actually not placed (pi-match shunts, alternates) | Matches BOM `DNP` flags |
| RF series 0R / steering links in the intended position | Matches assembly drawing |

## Stage 1 -- Unpowered resistance

Meter on resistance, board unpowered, battery disconnected.

| Measure | Pass |
|---|---|
| Each rail (`+VSYS`, `+3V3`, `+VBAT_LTE`, every local rail) to `GND` | Not a short. **< 10 ohm = stop.** Record the value; compare board to board -- an outlier is the finding even if it is not a short (judgement, not datasheet) |
| Rail to rail | Not shorted to each other |
| Each UWB SMA centre to GND | DC open or the expected DC path of the match (2 pF series cap blocks DC -- `docs/positioning.md`) |
| J10 (LTE) centre to GND | **Low ohms is correct**: the nRF9151 ANT pin is DC grounded (HDG *ANT*) and R130 is a 0R |
| J11 (GNSS) centre to GND | DC open (C123 1 nF DC block ahead of the LNA), unless the DNP bias tee is fitted |
| Continuity: each test pad to its net | Per Test-point index below. For a net whose pad was cut, probe the pin or header named in "Cut pads and why" |

## Stage 2 -- Current-limited power-up

Bench supply into the main input, **current limit set low** (start at
100 mA -- judgement), the two rail break links **R300 (`+3V3`) and R302
(`+VBAT_LTE`) removed**, J30/J31 fitted with nothing. Step-by-step regulator
bring-up with expected values: `bay-station/handoff/power.md`, "Bring-up
tests".

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
| `+VBAT_LTE` | 3.55-3.62 V at rest; **>= 3.2 V during LTE TX bursts** (scope, AC-coupled single-shot, trigger on the drop during `bringup modem` attach), and never below the 3.0 V absolute floor | U40 FB 562k/91k with VFB 500 mV +/-1 % (TI SLVSEU9D Table 10-5). nRF9151 `VDD` 3.0-5.5 V "including all voltage drops, ripple, and spikes", 3.2 V recommended for LTE (nRF9151 PS *Operating conditions* / HDG *VDD*, **HTML renditions** -- PDF not obtained) |
| `+VBAT_LTE` current | TX subframe average <= 505 mA worst case (LTE-M PC3 23 dBm, B1, 3.0 V, 85 C, VSWR 3:1); ~345 mA at 3.7 V / 25 C / 50 ohm; peak about 500 mA at 3.7 V; LTE-M RX 41 mA | nRF9151 HDG *TX current consumption, Power Class 3*, *Maximum output power*, RX table (HTML) |
| `+VSYS` | Tracks the MCP73871 power-path behaviour | `bay-station/power_bms_notes.md` |
| Start-up sequence | `+3V3` (= nRF9151 `VDD_GPIO`) starts rising **>= 6 ms** after `+VBAT_LTE` is in regulation (expect 12-41 ms) and falls first at power-down; no overshoot above 3.6 V on either rail; nRF9151 and BT840 come out of reset | nRF9151 HDG *ENABLE sequence* (HTML); `bay-station/regulation_notes.md` section 4; load abs-max tables |
| UVLO | Both rails off below `+VSYS` 2.82-3.00 V, back on above 3.11-3.29 V (battery input, slow ramp) | TPS63802 EN thresholds (TI SLVSEU9D s8.5) with R308/R309 191k/100k |

Current-measurement break point on `+VBAT_LTE` is R302 (PPK2 across J31,
pin 1 regulator side); `+3V3` is R300/J30. Use them for all modem and anchor
current characterisation in Stage 6. The PPK2's ammeter mode tops out at
1 A, which covers both rails.

## Stage 4 -- Programming each MCU

| Step | Pass |
|---|---|
| nRF9151 SWD on J3 (`SWDIO_MCU`, `SWDCLK_MCU`, `RESET_MCU_N`) | Debugger connects, reads device info. Allow 100-500 ms after power before SWD answers (HDG *ENABLE*) |
| Flash **modem firmware** (pinned version, `firmware/bay-station/README.md`) | `bringup modem` -> `AT+CGMR` reports it |
| Flash `nrf9151-app` (`bay_station_lte/nrf9151` for first bring-up) | Shell prompt on `DBG_UART`, `LED_SYS` heartbeat |
| BT840 SWD on J32 (`SWDIO_BLE`, `SWDCLK_BLE`, `RESET_BLE_N`) | Debugger connects. SW11 resets the BT840 only once the bridge firmware has set UICR.PSELRESET |
| Flash `ble-bridge` | RTT log shows HELLO sent; laptop sees advertiser |

## Stage 5 -- Per-block functional tests

All from the `bringup` shell. Run in this order; each row depends on the
ones above it.

| Block | Command | Pass | Source / status |
|---|---|---|---|
| LEDs, button | `bringup led sys on`, `led lte on`, `btn` | Visual; press detected | -- |
| Sensor lines | `bringup lines` | Idle levels sane (e.g. `FG_ALRT` high via R39 pull-up) | -- |
| I2C | `bringup i2c scan` | Exactly 3 ACKs: 0x1E, 0x19, 0x36 | IIS2MDC 0x1E fixed (ST DocID030986 Rev 1, Table 21); IIS2DLPC 0x19 as strapped (SA0 high via R414; ST DocID031788 Rev 4, "SAD ... 001100xb"); MAX17048 fixed (19-6171 Rev 7, "Slave Address") |
| I2C IDs | `bringup i2c id` | IIS2DLPC WHO_AM_I = 0x44 | Verified: DocID031788 Rev 4, s8.3 |
| | | IIS2MDC WHO_AM_I = 0x40 | **UNVERIFIED** -- the copy obtained stops before the register pages; 0x40 is the LIS2MDL value (DocID030621 Rev 5) |
| | | MAX17048 VERSION | **UNVERIFIED** -- datasheet 19-6171 not obtained |
| Rails x-check | `bringup rails` | Gauge VCELL and modem VBAT agree with the DMM within the gauge's spec | MAX17048 accuracy `PLACEHOLDER` |
| UWB SPI | `bringup uwb id` | All four anchors 0xDECA0302 | `DWT_DW3000_DEV_ID`, Qorvo dwt_uwb_driver 08.02.02; not cross-checked against the DW3000 User Manual. Proves SPI/CS/power/reset only -- runs on the RC oscillator |
| UWB IRQ, reset | `bringup uwb irq`, `uwb reset` | IRQ lines low at idle; DEV_ID reads again after reset | -- |
| Reference clock | Fit R402 and R403, scope `TCXO_OUT` (TP5) and `UWB_CLK0` at A0 (TP6) | 38.4 MHz at the TCXO and at A0's XTI, amplitude 0.8 V to VDD2 Vpp, duty 40-60 % (A1-A3 clock presence is covered by `bringup uwb clock`, PLL lock on all four -- the per-anchor scope pads TP7-TP9 were cut 2026-11-18) | DW3000 DS Table 10 via `docs/positioning.md` ("TCXO selection spec"). There is no `TCXO_EN`, so no `tcxo off/on` test: the RPT1490LN has no enable |
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
| Power-cycle, `UWB_SYNC` toggling (if R216-R219 fitted) | No step change in mean `dt_i` | -- |

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
| Cold charge | Charging suspended on the way down between +1.1 and +5.3 degC (THERM 1.20-1.26 V, NTC 22.6-26.8k), i.e. never below 0 degC; resumes on warming. Requires the NTC on the cell | MCP73871 DS20002090E sec 1.0; `bay-station/power_bms_notes.md`, "THERM cold-charge window" |

## Test-point index

The 62 test pads on the board after the 2026-11-18 cut (127 before; see
"Cut pads and why" at the end of this section). Compiled 2026-11-17 from the
sheet handoffs and notes, pruned 2026-11-18. The label in brackets after each
ref is the bottom-side silkscreen text (`scripts/layout/testpoint_labels.json`,
which also carries each pad's function-row group). Expected values are
**design targets** from each block's intent unless a source is named -- not
measured, and not datasheet guarantees (io handoff, "Unverified items"). Assume
adapter power unless noted. The clock pads TP5 and TP6 read nothing until
their DNP 0402 0R (R402, R403) is fitted. TP135 (`TCXO_EN`) no longer exists:
the TCXO has no enable.

### Contract nets (`testpoints.kicad_sch`, TP1-TP21, TP100-TP175, 42 pads)

The contract-net pads that survived the cut, plus far-end rail pads and GND
spring points. Contract nets without a row here are probed at a header, LED,
button or resistor pad instead ("Cut pads and why"). Rails/GND are D1.5 pads,
signals D1.0.

| TP | Net | Purpose | Expect | Stage |
|---|---|---|---|---|
| TP1 (3V3 MAIN) | `+3V3` | Main 3.3V rail from TPS62A02 (regulation). Check first when anything misbehaves. | 3.22-3.38 V (Stage 3); io design target ripple < 30 mVpp | 1, 3 |
| TP101 (3V3 UWB) | `+3V3` | +3V3 at the far end of the UWB array: IR drop across four DW3210. | within 50 mV of TP1 during TX bursts | 1, 3 |
| TP102 (3V3 HOST) | `+3V3` | +3V3 at the nRF9151 / BT840 end. | within 50 mV of TP1 | 1, 3 |
| TP2 (VSYS) | `+VSYS` | Unregulated system rail out of the MCP73871 power path (power_bms). | ~4.5-5.0 V on adapter; = VBAT (3.0-4.2 V) on battery | 1, 3 |
| TP103 (VSYS REG) | `+VSYS` | +VSYS at the regulator inputs: drop along the system feed. | within 100 mV of TP2 | 1, 3 |
| TP100 (VBAT LTE) | `+VBAT_LTE` | nRF9151 `VDD` supply, far-end pad. The break point R302/J31 and its pads TP406/TP407 are on regulation. | 3.55-3.62 V (U40 FB 562k/91k, VFB +/-1 %, TI SLVSEU9D); stays >= 3.2 V during LTE TX bursts (Nordic recommendation; 3.0 V floor incl. ripple, nRF9151 HDG *VDD*) -- scope single-shot | 1, 3 |
| TP104 (5V IN) | `+5V_IN` | Adapter / USB input = MCP73871 IN (also D6 PG LED rail). | 4.75-5.25 V with adapter, 0 V on battery | 1, 3 |
| TP3 (GND CLK1) | `GND` | Clock scope ground #1: short ground-spring next to TCXO/clock pads. | 0 V | 1, 3 (scope ground) |
| TP110 (GND CLK2) | `GND` | Clock scope ground #2: second spring point at the anchor clock pads. | 0 V | 1, 3 (scope ground) |
| TP111 (GND SPI) | `GND` | SPI scope ground: spring ground beside UWB_SCK / UWB_MISO. | 0 V | 1, 3 (scope ground) |
| TP113 (GND PWR) | `GND` | Ground: power_bms area. | 0 V | 1, 3 (scope ground) |
| TP114 (GND REG) | `GND` | Ground: regulation area. | 0 V | 1, 3 (scope ground) |
| TP115 (GND HOST) | `GND` | Ground: connectivity area (nRF9151 / BT840). | 0 V | 1, 3 (scope ground) |
| TP116 (GND UWB) | `GND` | Ground: UWB array area. | 0 V | 1, 3 (scope ground) |
| TP10 (SPI SCK) | `UWB_SCK` | Shared SPI clock to all four DW3210. | bursts at the configured rate, <= 8 MHz (nRF9151 SPIM max); idle low (SPI mode 0) | 5 |
| TP11 (SPI MOSI) | `UWB_MOSI` | Shared SPI MOSI to all four anchors. | data during CSn low | 5 |
| TP12 (SPI MISO) | `UWB_MISO` | Shared SPI MISO from all four anchors. | driven only while one CSn is low; DEV_ID 0xDECA0302 on each CSn (Stage 5; Qorvo driver source, unverified) | 5 |
| TP15 (A0 CSN) | `UWB_CS0_N` | Chip-select A0 (CENTER anchor, TWR). | idle 3.3 V; one low pulse per A0 transaction | 5 |
| TP16 (A1 CSN) | `UWB_CS1_N` | Chip-select A1 (outer, TDoA). | idle 3.3 V | 5 |
| TP17 (A2 CSN) | `UWB_CS2_N` | Chip-select A2 (outer, TDoA). | idle 3.3 V | 5 |
| TP18 (A3 CSN) | `UWB_CS3_N` | Chip-select A3 (outer, TDoA). | idle 3.3 V | 5 |
| TP13 (A0 IRQ) | `UWB_IRQ0` | IRQ from A0 (center): ranging exchange timing. | low idle (100k pull-down); high pulse per event | 5 |
| TP19 (A1 IRQ) | `UWB_IRQ1` | IRQ from A1: TDoA timestamp latch, independent of A0. | low idle; pulse on RX of the tag frame, within ns-us of TP13 | 5 |
| TP20 (A2 IRQ) | `UWB_IRQ2` | IRQ from A2. | as TP19 | 5 |
| TP21 (A3 IRQ) | `UWB_IRQ3` | IRQ from A3. | as TP19 | 5 |
| TP14 (UWB RSTN) | `UWB_RST_N` | Shared DW3210 RSTn (open-drain). | low during reset, then released high by the DW3210s | 5 |
| TP130 (UWB WAKE) | `UWB_WAKEUP` | Shared DW3210 WAKEUP. | low idle; high pulse to wake from sleep | 5 |
| TP140 (I2C SCL) | `I2C_SCL` | Shared I2C SCL (MAX17048 0x36, IIS2MDC 0x1E, IIS2DLPC 0x19). | idle 3.3 V; 100/400 kHz bursts; rise time < 300 ns @400k | 5 |
| TP141 (I2C SDA) | `I2C_SDA` | Shared I2C SDA. | idle 3.3 V; ACKs from 0x19, 0x1E, 0x36 on a bus scan | 5 |
| TP143 (MAG INT) | `MAG_INT` | IIS2MDC INT/DRDY (one pin; replaced `MAG_DRDY` + `MAG_INT`, TP142 deleted). | not driven until `INT_on_PIN` / `DRDY_on_PIN` is set in `CFG_REG_C` (62h), then push-pull | 5 |
| TP144 (ACC INT1) | `ACC_INT1` | IIS2DLPC INT1 (knock / move detect). | pulses when the board is tapped (after config) | 5 |
| TP145 (ACC INT2) | `ACC_INT2` | IIS2DLPC INT2. | low unless configured | 5 |
| TP146 (FG ALRT) | `FG_ALRT` | MAX17048 ALRT (open-drain, R39 pull-up). | idle 3.3 V; low on SOC/voltage alert | 5 |
| TP5 (TCXO OUT) | `TCXO_OUT` | Raw TCXO output before the 1:4 buffer. (behind DNP R402; net `Net-(R402-Pad1)`, not on the CLK-class net) | fit R402 first; 38.4 MHz CMOS, VOL <= 0.4 V / VOH >= 2.7 V, duty 49-51 % (Rakon RPT1490LN Issue B) | 5, 6 |
| TP6 (CLK A0) | `UWB_CLK0` | Buffer output to A0 (center) XTI, after AC coupling. (behind DNP R403; net `Net-(R403-Pad1)`) | fit R403 first; 38.4 MHz, 0.8 V to VDD2 Vpp at XTI (DW3000 DS Table 10) | 5, 6 |
| TP150 (BR TXD) | `BRIDGE_TXD` | nRF9151 TX -> BT840 RX. | idle high 3.3 V; UART frames at the bridge baud | 5 |
| TP151 (BR RXD) | `BRIDGE_RXD` | BT840 TX -> nRF9151 RX. | idle high 3.3 V | 5 |
| TP152 (BR RTS) | `BRIDGE_RTS` | Flow control, nRF9151 RTS out. | low = nRF9151 ready to receive | 5 |
| TP153 (BR CTS) | `BRIDGE_CTS` | Flow control, nRF9151 CTS in. | low = BT840 ready to receive | 5 |
| TP154 (BR IRQ) | `BRIDGE_IRQ` | BT840 -> nRF9151 attention line. | pulse when the BT840 has data / link event | 5 |
| TP155 (RST BLE) | `RESET_BLE_N` | BT840 reset (open-drain, from nRF9151 and SWD header). | idle 3.3 V; pull low with tweezers to GND pad TP115 to reset the BT840 | 5 |
| TP162 (RST MCU) | `RESET_MCU_N` | nRF9151 reset. | idle ~2.2 V -- the 13k internal pull-up goes to 2.2 V, not 3.3 V (nRF9151 HDG *nRESET*); never driven above 2.2 V; < 0.66 V with SW2 pressed | 4 |

### Regulation and power_bms local pads (TP400, TP403-TP406, TP408-TP410, TP415-TP417)

Source: `bay-station/regulation_notes.md` section 7, `power_bms_notes.md`,
and the bring-up steps in `bay-station/handoff/power.md`. Probe FB pads with
>= 10 MOhm. The switch-node pads TP402/TP411/TP412 were deleted 2026-11-18 (a pad on
a switch node is a stub on the noisiest copper); use a scope probe tip on the
inductor pad instead.

| TP | Net | Purpose | Expect | Stage |
|---|---|---|---|---|
| TP400 (3V3 REG) | `+3V3_REG` | U8 output, regulator side of the R300 break | 3.28-3.35 V unloaded | 3 |
| TP403 (FB 3V3) | `FB_3V3` | U8 feedback | 0.594-0.606 V (TI SLUSEG9E) | 3 |
| TP404 (EN 3V3) | `EN_3V3` | U8 enable, RC-delayed from `PG_LTE` | RC ramp after PG_LTE releases; `+3V3` must start >= 6 ms after `+VBAT_LTE` (expect 12-41 ms) | 3 |
| TP405 (PG 3V3) | `PG_3V3` | U8 power good (gates nothing) | high once `+3V3` >= 96 % | 3 |
| TP406 (VBAT REG) | `+VBAT_LTE_REG` | U40 output, regulator side of the R302 break | 3.55-3.62 V | 3 |
| TP408 (EN LTE) | `EN_LTE` | U40 EN = battery UVLO divider | `+VSYS` x 0.344 (~1.72 V at 5 V); rails off below `+VSYS` 2.82-3.00 V, on above 3.11-3.29 V | 3 |
| TP409 (PG LTE) | `PG_LTE` | U40 power good, releases `EN_3V3` | high once VOUT >= 95 % | 3 |
| TP410 (FB LTE) | `FB_LTE` | U40 feedback | 0.495-0.505 V (TI SLVSEU9D) | 3 |
| TP415 (VBAT PROT) | `VBATT_PROT` | Cell after the Q1 reverse-polarity FET | = cell voltage (3.0-4.2 V) | 3 |
| TP416 (THERM) | `THERM` | MCP73871 THERM / NTC | ~0.5 V at 25 C (10k x ~50 uA); charging stops at 1.20-1.26 V, i.e. +1.1..+5.3 C | 7 |
| TP417 (BATT RAW) | `BATT_RAW` | Raw cell at the connector | record at each UVLO event | 3 |

### Clock local pads (TP528-TP530)

Source: `bay-station/clock_dist_notes.md` ("Supplies", "Bring-up tests"). The 28
per-anchor pads TP500-TP527 (`+3V3_An`, `An_EXTON`, `An_GPIO0-4`) were deleted
2026-11-18: no stage below needs them. Per-anchor current is measured by lifting
the 0R link R200-R203 (probe its pads); the `+3V3` far end is TP101.

| TP | Net | Purpose | Expect | Stage |
|---|---|---|---|---|
| TP528 (3V3 TCXO) | `+3V3_TCXO` | TCXO rail after R225 | = `+3V3`; ~10 mA typ by lifting R225 (Rakon RPT1490LN Issue B: 10 mA typ, 15 mA max) | 3 |
| TP529 (3V3 CLKBUF) | `+3V3_CLKBUF` | Buffer rail after R226; also the bench 2.5 V injection point for the XTI-amplitude test | = `+3V3` | 3, 5 |
| TP530 (TCXO VC) | `TCXO_VC` | TCXO tuning voltage (R227/R228 divider) | ~1.49 V; lift R228 to over-drive for array frequency trim | 5 |

### Connectivity local pads (TP46-TP50)

Source: `bay-station/connectivity_notes.md` sections 3-4 and the pad
Descriptions on `connectivity.kicad_sch`. TP40-TP45, TP52 and TP53 were deleted 2026-11-18; TP51 never existed.

| TP | Net | Purpose | Expect | Stage |
|---|---|---|---|---|
| TP46 (LNA EN) | `GNSS_LNA_EN` | COEX0 -> U25 LDO enable | high only during GNSS reception (`AT%XCOEX0`) | 5 |
| TP47 (LNA VCC) | `GNSS_LNA_VCC` | BGA524N6 supply (U25 output) | 2.8 V during GNSS, else 0 V | 5 |
| TP48 (NRF VDD) | `NRF_VDD` | nRF9151 VDD after FB10 | = `+VBAT_LTE` minus the bead drop (FB10 8 mOhm DCR) | 3 |
| TP49 (VDD GPIO) | `NRF_VDD_GPIO` | nRF9151 VDD_GPIO pin side | = `+3V3`, rising >= 6 ms after `NRF_VDD` (HDG *ENABLE sequence*) | 3 |
| TP50 (NRF ENABLE) | `NRF_ENABLE` | ENABLE, R101 10k from `NRF_VDD` | = `NRF_VDD`; high threshold >= 0.89 x VDD (HDG *ENABLE*) | 3 |

### Orientation local pad

| TP | Net | Purpose | Expect | Stage |
|---|---|---|---|---|
| TP121 (3V3 SNS) | `+3V3_SNS` | Sensor rail after the R411 current break | = TP1 with R411 fitted; 0 V with R411 lifted | 3 |

### Cut pads and why (2026-11-18)

127 pads were more than the board can place and route well, so 65 were cut and 62
kept (counts by group: `scripts/layout/testpoint_labels.json`). Rule: a pad stays
if it is the only convenient probe of a rail, a verification-stage signal, an
interrupt/reset or a scope ground; it goes if another probe point on the same
net exists, or if no stage reads it. **No kept pad is on an RF50 or CLK-class net**
(`scripts/layout/hs_nets.json`): TP5/TP6 reach the clock only through DNP 0R
links. Refs of kept pads were not renumbered.

| Cut | Count | Probe it here instead |
|---|---|---|
| TP500-TP527: per-anchor `+3V3_An`, `An_EXTON`, `An_GPIO0-4` | 28 | Rail: lift R200-R203 and probe its pads, or TP101 at the array far end. EXTON/GPIO0-4 were unused spares (now no-connect flags); solder a wire to the DW3210 pin if a strobe is ever needed |
| TP7-TP9 `UWB_CLK1-3` (and their DNP links R404-R406) | 3 (+3 R) | `bringup uwb clock` (PLL lock on all four); scope XTI of A1-A3 at the 2200 pF series cap if needed. Removes three stubs from the clock nets |
| TP4, TP112, TP117, TP118, TP119: duplicate GND | 5 | TP3, TP110, TP111, TP113-TP116 (7 GND pads kept: clock x2, SPI, power, regulation, host, UWB) |
| TP160, TP161, TP163, TP164: SWD | 4 | SWD headers J3/J34 (nRF9151) and J32/J35 (BT840) |
| TP165, TP166: `DBG_UART_TX/RX` | 2 | Pins 2 and 3 of J33 |
| TP167 `BTN_USER` | 1 | The button pad (short to GND to fake a press) |
| TP170-TP172 `nSTAT1_LBO`, `nSTAT2`, `nPG` | 3 | Pad 1 of D4, D5, D6 (the LED pad on that net) |
| TP173-TP175 `LED_SYS/LTE/LINK` | 3 | Pad 1 of the series resistors R32, R400, R401 (LED anode side net) |
| TP131 `UWB_SYNC` | 1 | R216-R219 DNP link pads (use of SYNC still open, decisions.md) |
| TP401, TP407: load side of the R300/R302 breaks | 2 | J30 / J31 pin 2 (the PPK2 pins); same nets as TP1 and TP100 |
| TP414 `+5V_IN` (second pad) | 1 | TP104 |
| TP402, TP411, TP412 switch nodes; TP413 `MODE_LTE` | 4 | Inductor pads L1 / L300 and R311/R312 pads |
| TP40-TP43 `SIM_*` | 4 | J12 socket pads / U22 pins. HDG *UICC* asks for RST/CLK/IO pads; the socket pads are the probe points (not read from the HDG PDF, which was HTML only) |
| TP44, TP45 COEX1/COEX2 | 2 | None: both pins are now no-connect flags; no stage reads them |
| TP52 `NRF_DEC0`, TP53 `NRF_VGPIO_IN` | 2 | DEC0 is observe-only (C109 pad); R104 pads measure VDD_GPIO current |

Consequences to carry into layout: R404-R406 no longer exist (removed with their
pads), so only CLK0 carries an unfitted R403 pad -- the reroute must length-match
CLK0 to CLK1-CLK3 including that pad. Unresolved: TP5/TP6 are still the only
scope points on the clock, so the 38.4 MHz amplitude/overshoot check at A1-A3
XTI (decisions.md, "scope XTI (TP6-TP9)") now needs a probe tip on the XTI
series cap instead of a pad.
