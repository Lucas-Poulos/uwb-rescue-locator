# Bay station firmware

Two MCUs, three images:

| Image | Runs on | Source | Owner |
|---|---|---|---|
| **Host app** | nRF9151 application core (Cortex-M33) | `nrf9151-app/` | us |
| **Modem firmware** | nRF9151 modem core | Nordic binary (`mfw_nrf91x1_*.zip`), never built here | Nordic; we pin and track the version |
| **BLE bridge app** | Fanstel BT840 (nRF52840) | `ble-bridge/` | us |

The nRF9151 owns everything precision-critical: the four DW3210 anchors,
the exchange, timestamp collection, the calibration table, the sensors and
the modem (LTE-M + GNSS). The BT840 is demoted to a BLE bridge to the
laptop over UART -- the same split as Nordic's Thingy:91 X (nRF9151 +
nRF5340). The nRF9151 has no Bluetooth radio, which is why the BT840 stays.

Board definitions: `../boards/uwbrl/bay_station_lte/` (nRF9151),
`../boards/uwbrl/bay_station_ble/` (BT840). Pins are filled in exactly once,
in each board's `*_pins.h`, from `bay-station/connectivity_notes.md`; until
then the build stops with `#error`. Net names are `docs/net-contract.md`.

**Nothing here has been built.** No nRF Connect SDK was installed where this
was written. What has been run: the shared protocol code's host unit test
(`make -C ../common/test`), and a `dtc` parse of the board devicetrees
against stub SoC nodes (`../boards/README.md`).

## Toolchain: nRF Connect SDK, v3.4.x LTS

Settled by the part, not by preference. Nordic's nRF5 SDK is the
"Software development kit for the nRF52 Series and nRF51 Series SoCs", is
"in maintenance mode", and Nordic says "For new projects, we recommend the
nRF Connect SDK" (nRF5 SDK product page, nordicsemi.com, read 2026-11-17).
The nRF9151 is neither nRF52 nor nRF51, and the nRF9151 download page lists
only nRF Connect SDK software alongside the modem firmware. So the station's
host is NCS (Zephyr) by necessity, and the BT840 goes NCS too so the station
has one toolchain.

Pin **NCS v3.4.x (LTS)** with **modem firmware 2.0.4**: Nordic's nRF9151
compatibility matrix ("nRF9151 modem firmware and nRF Connect SDK versions",
Table 1) lists mfw 2.0.4 against NCS 3.1.0, 3.2.0, 3.3.0 and 3.4.0 LTS. The
matrix also ties modem firmware to the SiP **build code** (A0A shipped with
2.0.1) -- check the build code printed on the parts we actually receive.

Wristband consequence: see `../wristband/README.md` -- recommend NCS there
too, so the whole project is one toolchain.

## Responsibilities

### nRF9151 host app (`nrf9151-app/`)

- DW3210 x4 over SPIM3: multi-instance driver, configuration (CH5),
  exchange scheduling, timestamp collection.
- Calibration table: store, ship to laptop, stamp every record with its CRC.
- Sensors on one I2C bus: IIS2MDC (heading), IIS2DLPC (tilt, knock
  detect on `ACC_INT1`), MAX17048 (battery).
- Modem: LTE-M attach / PSM, GNSS fixes in LTE idle windows, survey-in
  averaging.
- Bridge link to the BT840 (`BRIDGE_*`), `RESET_BLE_N` control.
- `bringup` shell on `DBG_UART` (see "Bring-up shell").

### Modem firmware (Nordic binary)

Not ours to build, but ours to manage. It is flashed separately from the
app (nRF Util / nRF Connect Programmer), it is version-coupled to the NCS
release, and it changes radio behaviour. Requirements:

1. **Pin the version in this file** (above: 2.0.4) and change it only
   alongside an NCS bump, re-checked against the compatibility matrix.
2. The host app reads `AT+CGMR` at boot, logs it, and reports it in
   `UWBRL_T_STATUS`; a mismatch with the pinned version is a visible
   warning, not a silent run. (`bringup modem` prints it today.)
3. Record the modem FW version in every bring-up and RF test log
   (`docs/verification-plan.md`) -- RF results are only comparable across
   the same modem FW.
4. Production test uses Nordic's **separate PTI modem firmware**, not the
   LTE firmware (see `docs/verification-plan.md`, RF tests). Re-flash the
   LTE firmware afterwards and verify with `AT+CGMR`.
5. Field updates: modem delta/full FOTA exists in NCS but needs the LTE
   link and flash budget; deferred (milestone fw-m10).

### BLE bridge app (`ble-bridge/`)

A framed relay between the nRF9151's UART and the laptop's BLE link, plus
link-local housekeeping (ping, BLE state, `LED_LINK`, `BRIDGE_IRQ`). It does
not interpret measurement payloads, so it rarely needs re-flashing. Logs go
over SEGGER RTT on the BT840 SWD header -- the contract gives the BT840 no
debug UART.

## Peripheral instances (nRF9151)

nRF91 UARTE/SPIM/TWIM share serial instances 0-3, and this board needs four
serial buses, so **all four are used and none is spare**:

| Instance | Use | Nets |
|---|---|---|
| UARTE0 | shell + log | `DBG_UART_TX/RX` |
| UARTE1 | BLE bridge, 1 Mbaud, RTS/CTS | `BRIDGE_TXD/RXD/RTS/CTS` |
| TWIM2 | sensors | `I2C_SCL/SDA` |
| SPIM3 | four DW3210 | `UWB_SCK/MOSI/MISO`, `UWB_CS0_N..CS3_N` |

TF-M's own log UART defaults to UARTE1 (upstream `nrf9151dk_nrf9151_ns.dts`
disables `uart1` "because it is used by default in TF-M"), so the `/ns`
build silences TF-M logging (`nrf9151-app/boards/*_ns.conf`). PSEL lets any
instance use any GPIO, so this table does not constrain the pin map.

**SPI clock: 8 MHz ceiling.** The DW3000 runs SPI to 36 MHz, but only
7 MHz in INIT_RC (DW3000 Datasheet v1.1 Table 21, "SPI comms @ 7MHz"). The
nRF9151 caps every SPIM instance at 8 MHz -- unlike the nRF52840's 32 MHz
SPIM3 that the old README relied on. Source: the nrfx MDK
(`SPIMn_MAX_DATARATE 8`, `bay-station/connectivity_notes.md` section 2); the
PS SPIM table itself is still to be read from the PDF. It costs readout time
(update rate, A0 reply delay), not precision: timestamps are latched in
silicon.

## Inter-chip protocol (nRF9151 <-> BT840 <-> laptop)

### Options considered

| Option | What it is | For | Against |
|---|---|---|---|
| **HCI over UART** | BT840 runs a controller-only image; the BLE host stack runs on the nRF9151. Nordic's pattern on the nRF9160 DK: the `hci_lpuart` sample on the nRF52840 ("based on the HCI UART" sample, using the low-power UART driver; NCS 3.4.x docs, supports `nrf9160dk/nrf52840` and Thingy:91), paired with the `lte_ble_gateway` host app on the nRF9160 | Nordic-maintained both ends; one app owns all logic | Puts the BLE host stack, its RAM and its timing on the chip that runs the modem library and the UWB exchange; HCI is chatty; any laptop-protocol change is a host-image change; no channel for our own side-band messages. Sample support lists the nRF9160 DK, not a custom nRF9151 board |
| **Transparent NUS bridge** | Nordic's Connectivity Bridge app (Thingy:91 X, on the nRF5340): UART <-> USB CDC, with an optional BLE NUS bridge on UART_0 | Nordic-maintained; zero framing work | Raw byte pipe: no message boundaries, no integrity check, no way for the bridge to tell the host "BLE disconnected". And Nordic ships its BLE side off: "By default, the Bluetooth LE interface is off, as the connection is not encrypted or authenticated" (NCS Connectivity bridge docs) |
| **Framed relay (recommended)** | Our own small protocol: COBS + CRC-16 frames over UART; the BT840 forwards end-to-end frames verbatim to/from NUS and handles a few link-local types itself | BLE stack isolated on the BT840; the nRF9151 only does UART; message boundaries and CRC end to end; one decoder on the laptop; bridge image stable | We maintain ~200 lines of framing code (`../common/`), already unit-tested |

**Recommendation: framed relay, starting the BT840 app from NCS's
Peripheral UART (NUS) sample.** The deciding argument is isolation: the
nRF9151 is already juggling the modem library and four transceivers'
interrupts, and HCI would add a full BLE host to it for no gain over a
byte stream. The HCI route stays a fallback if the BT840 ever needs to go.

### Framing (`../common/include/uwbrl/bridge_proto.h`)

```
wire  = COBS( hdr[6] | payload[0..232] | crc16_le[2] ) 0x00
hdr   = ver u8 | type u8 | seq u8 | flags u8 | len u16le
crc16 = CRC-16/CCITT-FALSE over hdr+payload (check "123456789" = 0x29B1)
```

- **COBS** rather than SLIP: fixed worst-case overhead (1 byte per 254)
  instead of SLIP's up-to-2x on binary data full of escape bytes, and the
  0x00 delimiter makes resync after a corrupt byte trivial.
- **CRC-16** per frame. UART on-board is clean, but the same frames cross
  BLE to the laptop and get logged; the CRC is what lets a log be trusted.
- **Max payload 232** so a worst-case frame (242 B on the wire) fits one
  BLE notification at ATT MTU 247. NUS is still treated as a byte stream.
- **Types < 0x40 are link-local** (HELLO, PING/PONG, ACK, BLE_STATE,
  BLE_CTRL); **types >= 0x40 are end-to-end** (MEAS_RAW, STATUS, GEOREF,
  CALIB_TABLE, LOG, CMD/CMD_RESP) and the bridge forwards them unchanged.
- `seq` is per-sender, per-direction; PONG and ACK echo the seq they
  answer. `UWBRL_F_ACK_REQ` for commands; the measurement stream is
  unacknowledged and gaps show up in `meas_seq`.

### Flow control

- **Hardware RTS/CTS** on the UART (`BRIDGE_RTS/CTS`), 1 Mbaud. One
  104-byte measurement record is ~113 B on the wire, so the UART alone
  carries ~880 records/s -- far above any exchange rate this system runs.
  (1 Mbaud is a standard nRF UARTE rate; confirm in both PSes.)
- **`BRIDGE_IRQ`** is asserted by the BT840 while it is sending to the
  host, so the nRF9151 may keep its UARTE RX disabled otherwise (power),
  re-enabling on the edge. Unused in v1 (RX always on), wired for v2.
- **BLE is the bottleneck.** When a notification cannot be queued the
  bridge drops the frame and counts it (`uwbrl_ble_state.e2e_frames_dropped`);
  nothing back-pressures the UWB exchange, which must never stall on BLE.

## Modem and GNSS time-sharing

The nRF9151 has one radio front end for LTE and GNSS; GNSS runs only when
LTE is not using it. That is acceptable here because the station is
stationary and its absolute position is an average anyway.

- **System mode**: `AT%XSYSTEMMODE=1,0,1,1` (LTE-M on, NB-IoT off, GNSS on,
  prefer LTE-M), set before `+CFUN=1` -- the command "is allowed only before
  activating the modem using the +CFUN=1 command" (nRF91x1 AT Commands,
  %XSYSTEMMODE set). NB-IoT off is a proposal (smaller scan, LTE-M has the
  latency we want); revisit if coverage requires it.
- **At power-on / new site**: GNSS first, LTE later. Run GNSS with LTE
  deactivated until the survey-in average has enough fixes, then attach.
  Cold-start time without assistance is the cost; the operator UI must show
  "survey-in in progress" (open item in `docs/decisions.md`).
- **Steady state**: LTE in **PSM** (or long eDRX) between uplinks, GNSS
  fixes in the idle windows. Nordic's GNSS API notes that long enough eDRX
  cycles or PSM give better behaviour for both, and that GNSS priority mode
  should be used only when fixes are being blocked by LTE idle-mode
  activity, flagged as `NOT_ENOUGH_WINDOW_TIME` in the PVT flags
  (nrfxlib `nrf_modem_gnss_prio_mode_enable()` docs). So: enable priority
  only after several consecutive PVT frames carry that flag.
- **A-GNSS: optional.** It needs LTE up and an assistance source (e.g.
  nRF Cloud), which a remote rescue site may not have. Survey-in does not
  need it. Treat it as a time-to-first-fix improvement, not a dependency.
- **Knock invalidates everything.** `ACC_INT1` (IIS2DLPC) during averaging
  restarts survey-in and heading calibration.

## DW3210 multi-instance driver

Start from Qorvo's `dwt_uwb_driver` 08.02.02 source, as packaged by
br101 for Zephyr (`zephyr-dw3000-decadriver`, "official source release of
the dwt_uwb_driver driver from Qorvo (version 08.02.02 from
DW3_QM33_SDK_1.0.2.zip)"). Its README says the Qorvo files "have been
modified to support only one DW3000 chip per board"; its sibling repo lists
Zephyr 3.6 / NCS v2.7.0 as the tested Zephyr target -- older than our NCS.

What Qorvo itself ships, as far as could be verified on 2026-11-17:

- The **DW3_QM33 SDK** (v1.0.2 announced 2024-09-11 on Qorvo's forum)
  lists DWM3001CDK, QM33120WDK1 and Murata Type2AB as platforms and the
  DW3210 among supported chips. The announcement names no RTOS; later
  community posts reference v1.1.1, and report nRF52840 support in 1.1.1
  limited to QM33 parts.
- **No Qorvo-published Zephyr/NCS support was found.** Forum threads in
  2026 are all community efforts (one reports the FiRa MAC ships as a
  precompiled `.a`; we do not want the FiRa MAC anyway -- the low-level
  driver is the part we need, and it is source).
- **TDoA: on our own.** A Qorvo staff reply (forum, 2026-08-10) says
  "Nothing is available from Qorvo for DWM3001C either publicly or through
  NDA" for TDoA reference code, pointing to an NDA-only QM33 UT-Tag SDK and
  FiRa DL-TDoA in the QM35 SDK. Our scheme is not FiRa DL-TDoA either.

Plan (fw-m3):

1. The trimmed API is implicitly single-instance: `dwt_readdevid(void)`,
   `dwt_check_dev_id(void)` and friends take no chip handle and act on a
   global context (`deca_device_api.h`). `struct dwt_probe_s` does carry
   `void *dw` and `void *spi` pointers, which suggests per-chip context
   exists upstream. **First task: read the untrimmed 08.02.02 source and
   find the per-chip selector.** If there is none, wrap the global context
   and swap it under a mutex in `uwb_anchor_select()` (`src/uwb_array.h`).
2. Our own binding (`uwbrl,dw3210-anchor`) replaces `decawave,dw3000`:
   per-anchor CS + IRQ + role; RST/WAKEUP/SYNC are shared and live in
   `uwbrl,uwb-array-ctrl`.
3. Start the bus at <=7 MHz until each chip leaves INIT_RC (Table 21),
   then raise to the SPIM ceiling.
4. Program every chip's antenna-delay registers to the same fixed value
   (proposed 0); all delay correction lives in the calibration table, so
   it is never applied twice.

## Exchange scheduling

Tag-initiated, because the tag is the power-constrained side and the whole
scheme exists to make it transmit as little as possible
(`docs/positioning.md`):

1. Tag wakes (motion-gated) and sends **POLL**.
2. All four anchors timestamp the POLL (TDoA sample 1; shared clock, so
   the four RX timestamps are directly comparable).
3. A0 replies **RESP** with delayed TX at a fixed reply time; A1-A3 stay in
   RX.
4. Tag sends **FINAL** carrying its POLL-TX / RESP-RX / FINAL-TX
   timestamps. All four anchors timestamp it (TDoA sample 2 -- free
   averaging); A0 completes DS-TWR.

Consequences: all four anchors are in RX whenever a tag might transmit
(the dominant station power draw -- measure it, see Power); the A0 reply
time must cover IRQ latency + A0's timestamp read + writing the delayed-TX
time over an 8 MHz bus -- **budget 1 ms to start, tighten after
measurement** (estimate, not derived). Multi-tag scheduling and update rate
remain open (`docs/decisions.md`).

## Timestamp collection

- On each anchor's RX-done IRQ: read that anchor's RX timestamp (40-bit,
  raw device units) and RX diagnostics, nothing else, then re-arm RX.
- **Read A0 first** on POLL (it has a reply deadline); A1-A3 in index order.
  Read order does not affect precision -- the timestamps are latched at
  reception -- only latency.
- Assemble one `uwbrl_meas_v1` per exchange, keyed by the frame's sequence
  number so a POLL heard by only some anchors produces a partial record
  with the `valid` bits saying which, rather than being silently mixed
  with the next exchange.
- **No conversion on the station.** Units stay at 1/(128 x 499.2 MHz)
  ~= 15.65 ps (`DWT_TIME_UNITS`, `deca_device_api.h`; User Manual not
  obtained to cross-check). Conversion happens once, in the solver.

## Calibration table

`../common/include/uwbrl/calib.h`. A0's **absolute** delay and A1-A3's
delays **relative to A0** are separate fields, because they are different
quantities with a 10x different accuracy requirement
(`docs/positioning.md`, "A0 and the outer anchors need different
calibrations"). Antenna positions in the frame's coordinates live in the
same table, since both are properties of one frame + cable set.

- Stored on the nRF9151 (NVS/settings, fw-m6); produced by
  `../tools/` from a fixture run.
- Sent to the laptop on connect (`UWBRL_T_CALIB_TABLE`); every measurement
  record carries the table's CRC, **not** the corrections applied. That
  keeps raw logs re-processable when a better table appears.
- No table (or a CRC mismatch) is reported in STATUS and on `LED_SYS`;
  the station still streams raw data.

## Position solve: where

**Recommendation: the laptop is authoritative, solving from raw
timestamps; the station also runs a quick-look solve for LTE reports.**

- The calibration tool needs raw timestamps anyway; solving on the laptop
  means one solver, re-runnable over logs with a newer calibration, with
  averaging/outlier logic that is easy to iterate.
- The Cortex-M33 can certainly run the 3-unknown, 4-equation least-squares
  (and the residual quality metric) -- compute is not the argument. The
  argument is that the raw stream must exist regardless, so the station
  solve is a *derived* product.
- The station needs its own solve only for LTE-M reports when no laptop
  is present (fw-m9). It uses the same table, and its output is labelled
  as quick-look.

## LTE-M vs BLE: what goes where

| | BLE (via BT840) | LTE-M |
|---|---|---|
| Role | Primary operator link, full rate | Remote / out-of-range visibility, low rate |
| Raw measurement stream | **Yes** (every exchange) | No |
| Positions | Laptop computes | Station quick-look, rate-limited |
| Station status, battery, georef, calibration ID | Yes | Yes, periodic + on change |
| Commands | Yes | Later, if ever |
| Time | -- | Network time (if available) for log timestamps |

This adds an internet uplink the project previously excluded on purpose
(`docs/system-overview.md`); the laptop stays the primary path and the
station must work fully with no SIM, no coverage and no subscription. The
cloud endpoint, SIM/operator and data budget are open questions
(`../handoff.md`).

## Power management

Measure before optimising; no current figures are claimed here.

- **Anchors in RX are expected to dominate** (four receivers). Levers, in
  order of cost: DEEPSLEEP all four when no tag has been heard for N
  seconds, waking on a slow beacon schedule (the TCXO has no enable, so it
  stays on -- about 10 mA typ);
  duty-cycle RX if the exchange becomes slotted.
- **Modem**: PSM between uplinks; LTE off entirely when no SIM / no
  coverage (do not let it scan forever); GNSS only during survey-in and
  occasional re-checks.
- **BT840**: slow advertising when disconnected; connection parameters
  relaxed when the laptop is idle.
- **Rails**: `+VBAT_LTE` has a current-measurement break point
  (net-contract) -- use it to separate modem current from everything else
  during characterisation (`docs/verification-plan.md`).

## Bring-up shell

`bringup` on `DBG_UART` (`nrf9151-app/src/bringup_shell.c`). One command
per block, in the order `docs/verification-plan.md` uses them:

| Command | Checks | Expected (source) |
|---|---|---|
| `bringup rails` | MAX17048 VCELL, modem `AT%XVBAT` | Cross-check only; DMM at test pads is the real test. MAX17048 registers **UNVERIFIED** |
| `bringup i2c scan` | ACKs on the sensor bus | 3 devices at the strapped addresses |
| `bringup i2c id` | WHO_AM_I / VERSION | IIS2DLPC 0x44 (ST DocID031788 Rev 4, s8.3, verified). IIS2MDC 0x40 **UNVERIFIED** (register pages missing from the copy obtained; the LIS2MDL, same family, reads 0x40 at 4Fh per DocID030621 Rev 5). MAX17048 VERSION **UNVERIFIED** |
| `bringup uwb id [n]` | Raw DEV_ID read per anchor | 0xDECA0302 (`DWT_DW3000_DEV_ID`, Qorvo driver 08.02.02; non-PDoA). Header octet 0x00 = short-addressed read of base 0 (DW3000 DS v1.1 s4.9.4, Figure 16). Works on the RC oscillator -- **does not prove the clock** |
| `bringup uwb clock` | PLL lock per anchor = reference clock present | TODO (needs driver). Until then, scope the clock test pads |
| `bringup uwb irq` / `uwb reset` | IRQ line levels, shared reset pulse | IRQ low at idle (pulldowns R25-R28) |
| `bringup bridge ping [n]` | UART framing both ways through the BT840 | n/n PONGs, 0 CRC/COBS errors |
| `bringup bridge reset` | `RESET_BLE_N` | BT840 re-sends HELLO |
| `bringup modem` | `AT+CGMR`, `%XSYSTEMMODE?`, `+CFUN?`, `%XMONITOR`, `+CEREG?` | Modem FW = pinned version |
| `bringup gnss [s]` | GNSS-only fix (`+CFUN=31`, LTE off), C/N0 | A fix outdoors with sky view; C/N0 criteria in the verification plan |
| `bringup led`, `bringup btn`, `bringup lines` | LEDs, `BTN_USER`, sensor interrupt lines | Visual / press seen / idle levels |

The NCS `at` shell command (`CONFIG_AT_SHELL`) is also enabled for raw AT
access.
