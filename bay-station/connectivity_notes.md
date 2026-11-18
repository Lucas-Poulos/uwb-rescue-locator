# Connectivity sheet notes (nRF9151 host + BT840 BLE bridge)

Sheet: `connectivity.kicad_sch`. Host MCU is the Nordic **nRF9151 SiP (U20)**.
The Fanstel **BT840 (U3)** is now only a UART BLE bridge to the laptop. Net
names are the ones in `docs/net-contract.md`. **Section 2 below is the single
source of truth for nRF9151 pin assignments.**

## 1. Sources and how far they were verified

The Nordic PDFs could not be downloaded. docs.nordicsemi.com and
nordicsemi.com serve a Cloudflare challenge to scripted clients, and the
Mouser and DigiKey mirrors were blocked or held only a 5-page stub. All
Nordic facts below therefore come from **Nordic's own HTML renditions**,
read through a fetch tool that returns extracted text. These are the same
documents, but they were not read with `pdftotext -layout/-raw`. Any
**figure** (pinout drawing, reference schematic, package drawing) was not
readable at all. Treat the Nordic rows as "primary source, HTML, re-check
against the PDF before fab".

| Doc | Used for |
|---|---|
| nRF9151 Product Specification v1.0 (4512_092, 2024-07-29), HTML `docs.nordicsemi.com/bundle/ps_nrf9151` | Pin assignments table (all 113 pins), Operating conditions, GPIO electrical spec, Peripheral instances, Mechanical specification table, Ordering information |
| nRF9151 Hardware Design Guidelines (HDG), HTML bundle `nwp_056` | Schematic design BOM (C1-C8, FB1, R1, R2), VDD, VDD_GPIO, ENABLE, ENABLE sequence, DEC0, nRESET, UICC, ANT, GNSS, COEX, MAGPIO, GPIOs, Maximum output power, TX current tables, Footprint |
| nRF9151 DK User Guide, HTML `ug_nrf9151_dk` | GNSS (LNA U2 enabled by COEX0), SIM and eSIM (nano-SIM J5 + unpopulated MFF2), Antenna interfaces |
| Nordic nrfx MDK `bsp/stable/mdk/nrf91/nrf9120/nrf9120_peripherals.h` + `_bitfields.h` (GitHub, raw) | `SPIM0..3_MAX_DATARATE 8`, `SPIM_FREQUENCY_FREQUENCY_M8` = 8 Mbps is the top setting. The nRF9151 uses the nRF9120 die in nrfx. |
| Infineon BGA524N6 Data Sheet Rev 3.5, 2021-08-31 (PDF; third-party mirror static.chipdip.ru, because the infineon.com link could not be resolved) | Pinout (Table 1, `-raw` and `-layout` agree), VCC/PON/AI limits, application BOM (Table 6), TSNP-6-2 outline and land pattern (Figures 5 and 7, rendered and read as images) |
| TI TPS22917 SLVSDW8B (Dec 2021) | DBV pinout. **`-raw` scrambles Figure 6-1** (it reads "1 VOUT 2 QOD..."); `-layout` and Table 6-1 agree on 1 VIN 2 GND 3 ON 4 CT 5 QOD 6 VOUT |
| TI TPS7A02 SBVS277C (Sep 2022) | DBV pinout (Table 5-1), CIN/COUT, VEN thresholds, orderable TPS7A0228PDBVR (Active) |
| TI TPD3F303 SLVSAM5A (Apr 2016) | Pin functions, Figure 6 orientation (socket on OUT, controller on IN), orderable TPD3F303DPVR |
| GCT SIM8060 drawing (rev A6, 2025-01-21) | Ordering grid -> SIM8060-6-0-14-00-A = 6 contacts, no switch, 1.43 mm, T&R; contact map C1/C2/C3/C5/C6/C7 |
| Fanstel BT840/F/E/X/XE Ver 1.15 (Sep 2019) | BT840 pins (existing symbol). The model summary lists the plain BT840's 32.768 kHz crystal as **External**, so no LF crystal is fitted on-module. |

**Orderable nRF9151 part number** (PS *Ordering information*):
`nRF9151-LACA-R` (reel, MOQ 2000) and **`nRF9151-LACA-R7`** (MOQ 100). The
schematic uses `-R7`.

## 2. nRF9151 GPIO allocation (single source of truth)

Every net in net-contract sections 2, 4, 5, 6 and 7 is listed here.
Section 3 (`TCXO_EN`) was not in scope and is not routed.

**Peripheral instances.** nRF9151 SPIM/SPIS/TWIM/TWIS/UARTE share four IDs.
ID 8 = *0, ID 9 = *1, ID 10 = *2, ID 11 = *3 (PS *Peripheral instances*),
so only one of the five can run per ID. SPIM also requires every other
peripheral on its ID to be disabled (PS *SPIM, Shared resources*). Four
serial functions are needed, so **all four IDs are used**:

| ID | Instance | Function | Note |
|---|---|---|---|
| 8 | UARTE0 | Debug/log UART (`DBG_UART_*`) | Zephyr/NCS default console |
| 9 | UARTE1 | BLE bridge (`BRIDGE_*`, RTS/CTS) | NCS puts UART **modem trace** on UARTE1 by default. Use the RTT trace backend instead, or give up the bridge while tracing. |
| 10 | TWIM2 | `I2C_SCL/SDA` | 100/400 kHz |
| 11 | SPIM3 | UWB bus to 4x DW3210 | **8 MHz max on every nRF91 SPIM instance**, and there is no faster instance (nrfx `SPIMn_MAX_DATARATE 8`). The DW3000 accepts up to 36 MHz (docs/system-overview.md), so the nRF9151 is the limit. Chip selects are GPIO: SPIM has no CSN (PS *SPIM*). Any GPIO can carry SPIM signals (PSEL), so no pin is special for the 8 MHz rate. **SPI mode 0** (CPOL 0, CPHA 0): the DW3210 straps on the uwb sheet select it (uwb agent). `TCXO_EN` was dropped (the TCXO has no enable), so it gets no GPIO. |

**Pins that are not GPIO and are not used:** COEX0 (pin 52) is the GNSS LNA
enable. COEX1 (53) = GNSS 1PPS and COEX2 (54) = RF-activity indicator, both
to test pads. MAGPIO0-2 (21-23) are 1.8 V and modem-timed, used for antenna
tuners; no tuner is fitted, so they are open. MIPI RFFE SDATA/SCLK/VIO
(27-29) are open. SIM_DET (26) must float (PS footnote). AUX (37) is open
(HDG *AUX*). RESERVED 31-33 are soldered with no net; RESERVED 81-104 are
not connected.

**Pins near the radio.** Neither the PS nor the HDG names individual GPIOs
to avoid. They only say to avoid high-drive, high-frequency, high-capacitance
outputs and fast edges, and to route GPIOs away from RF (PS *Operating
conditions* note, HDG *GPIOs*). The pinout figure that would show physical
adjacency could not be read. Pin **numbers** 44-50 (P0.26-P0.31) follow GPS
(42), so I assumed they sit nearest the RF corner and put only static or
slow signals there. The 8 MHz SPI went to P0.13-P0.15 (pins 73-75), which
I assumed is the far side. **Re-check against the PS pinout figure.**

**Not enough pins.** 35 GPIO-type signals compete for 32 P0 pins. Following
the priority order, the three charger-status nets `nSTAT1_LBO`, `nSTAT2`
and `nPG` were dropped. They go to LEDs only (indicators sheet). They also
must not touch a GPIO directly: they are open-drain with LEDs pulled to
+VSYS/+5V_IN, so the off-state node sits near +VSYS, above VDD_GPIO
(io agent). Charge state is still visible through the MAX17048 on I2C.
`LED_LINK` is on the BT840, per the contract. **One spare GPIO remains (P0.24, freed 2026-11-18 by the IIS2MDC re-pick)**, and
the ETM trace pins (P0.21-P0.25) are used as GPIO, so trace is SWO/RTT only.

| nRF9151 pin | Port | Net (contract) | Dir | Peripheral / config | Notes |
|---|---|---|---|---|---|
| 56 | P0.00 | `BRIDGE_TXD` | out | UARTE1 TXD | -> R140 -> BT840 P0.26 (RX) |
| 57 | P0.01 | `BRIDGE_RXD` | in | UARTE1 RXD | <- R141 <- BT840 P0.27 (TX); enable pull-up (BT840 may be in reset) |
| 58 | P0.02 | `BRIDGE_RTS` | out | UARTE1 RTS | -> R143 -> BT840 P1.00 (CTS) |
| 59 | P0.03 | `BRIDGE_CTS` | in | UARTE1 CTS | <- R142 <- BT840 P0.11 (RTS); pull-up |
| 61 | P0.04 | `BRIDGE_IRQ` | in | GPIOTE | <- R144 <- BT840 P0.13; pull-down/up per protocol |
| 62 | P0.05 | `I2C_SCL` | od | TWIM2 SCL | via R153 0R; pull-up R37/R38 3.3k |
| 63 | P0.06 | `I2C_SDA` | od | TWIM2 SDA | via R154 0R |
| 64 | P0.07 | `ACC_INT1` | in | GPIOTE | IIS2DLPC INT1 (knock/move) |
| 67 | P0.08 | `UWB_IRQ0` | in | GPIOTE | A0 centre (TWR) |
| 68 | P0.09 | `UWB_IRQ1` | in | GPIOTE | A1 |
| 69 | P0.10 | `UWB_IRQ2` | in | GPIOTE | A2 |
| 70 | P0.11 | `UWB_IRQ3` | in | GPIOTE | A3 |
| 72 | P0.12 | `UWB_RST_N` | od | GPIO, S0D1 | **open-drain only** (DW3210 RSTn must not be driven high) |
| 73 | P0.13 | `UWB_SCK` | out | SPIM3 SCK | via R150 (0R; 33-100R option) |
| 74 | P0.14 | `UWB_MOSI` | out | SPIM3 MOSI | via R151 |
| 75 | P0.15 | `UWB_MISO` | in | SPIM3 MISO | via R152 |
| 77 | P0.16 | `UWB_CS0_N` | out | GPIO | A0 centre |
| 78 | P0.17 | `UWB_CS1_N` | out | GPIO | A1 |
| 79 | P0.18 | `UWB_CS2_N` | out | GPIO | A2 |
| 80 | P0.19 | `UWB_CS3_N` | out | GPIO | A3 |
| 2 | P0.20 | `UWB_WAKEUP` | out | GPIO | shared |
| 5 | P0.21 | `UWB_SYNC` | out | GPIO (/TIMER+PPI) | shared SYNC/OSTR |
| 6 | P0.22 | `DBG_UART_TX` | out | UARTE0 TXD | log/shell |
| 8 | P0.23 | `DBG_UART_RX` | in | UARTE0 RXD | pull-up |
| 11 | P0.24 | -- spare -- | -- | no-connect flag on the sheet | was `MAG_DRDY`; freed 2026-11-18 (the IIS2MDC has one INT/DRDY pin) |
| 12 | P0.25 | `MAG_INT` | in | GPIOTE | IIS2MDC INT/DRDY |
| 44 | P0.26 | `ACC_INT2` | in | GPIOTE | IIS2DLPC INT2 |
| 45 | P0.27 | `FG_ALRT` | in | GPIOTE | MAX17048 ALRT, pull-up R39 2.2k |
| 47 | P0.28 | `RESET_BLE_N` | od | GPIO, S0D1 | via R145 0R; **open-drain only** (SW11 + BT840 header share it) |
| 48 | P0.29 | `BTN_USER` | in | GPIOTE | active low; internal pull-up unless programming_debug fits one |
| 49 | P0.30 | `LED_SYS` | out | GPIO | active high, ~1.1 mA via 1.2k (io) |
| 50 | P0.31 | `LED_LTE` | out | GPIO | active high, ~1.1 mA via 1.2k (io) |
| 4 | SWDIO | `SWDIO_MCU` | io | debug | J3 |
| 3 | SWDCLK | `SWDCLK_MCU` | in | debug | J3 |
| 9 | nRESET | `RESET_MCU_N` | io | reset | C110 100 nF at pin; 1k series is R313 (programming_debug); **no pull-up** |
| 52 | COEX0 | (local `GNSS_LNA_EN`) | out | `AT%XCOEX0` | GNSS LNA LDO enable, active high |
| 53 | COEX1 | (local, TP44) | out | modem | GNSS 1PPS |
| 54 | COEX2 | (local, TP45) | out | modem | LTE/GNSS RF-activity indicator |
| -- | -- | `nSTAT1_LBO`, `nSTAT2`, `nPG` | -- | **not routed** | LEDs only (out of pins; also over-voltage) |
| BT840 pin 5 | P0.02 | `LED_LINK` | out | BT840 GPIO | active high |

**LED drive check (io agent asked).** VDD_GPIO = +3V3, so GPIO high is
3.3 V. Standard drive guarantees IOH >= 1 mA at VDD-0.4 V (typ 2 mA; PS
GPIO *IOH,SD*). The io sheet's ~1.1 mA through 1.2k is at the edge of the
guaranteed minimum and is fine with the typical value. If the LEDs look
dim, configure P0.30/P0.31 as high drive (H0H1: IOH >= 6 mA at
VDD >= 2.7 V). Both are static outputs, so the HDG concern about
high-drive fast edges does not apply. The BT840 (nRF52840) has the same
standard/high drive split for LED_LINK.

## 3. Power, decoupling, reset (values = HDG *Schematic design* BOM)

| Ref | Value | HDG item | Where |
|---|---|---|---|
| FB10 | BLM18SD220SN1 (22R@100 MHz, 6 A, 8 mOhm, 0603) | FB1 | `+VBAT_LTE` -> `NRF_VDD` (HDG *VDD*: "highly recommended", DCR < 0.1 ohm) |
| C100, C101 | 1 uF | C1, C2 (optional) | `+VBAT_LTE`, source side of FB10 |
| C102 | 47 uF 0805 | C3 | VDD pin 14 |
| C103 | 10 uF | C4 | VDD pin 14 |
| R101 | 10k | R1 | ENABLE series from `NRF_VDD` (= `+VBAT_LTE` via FB10) |
| C104 | 100 nF | -- | ENABLE decoupling (HDG *ENABLE*: recommended) |
| C107 | 4.7 uF | C6 | VDD_GPIO pin 65 (HDG *VDD_GPIO*: minimum) |
| C108 | 100 nF | C5 | VDD_GPIO pin 65 |
| C109 | 4.7 uF | C7 | DEC0 pin 24 (HDG *DEC0*) |
| C110 | 100 nF | C8 | nRESET pin 9 (HDG *nRESET*) |
| (R313, programming_debug) | 1k | R2 | nRESET series, header side |

Nordic's example parts are 0201/0402 Murata GRM. This board uses
0603/0805 per the repo standard. The HDG allows other packages if the DC
resistance and frequency characteristics stay close and VDD stays >= 3.0 V
under load.

**Supply facts for the power agent** (also in the handoff):

- VDD is 3.0-5.5 V, including drop, ripple and spikes (PS *Operating
  conditions*; HDG *VDD*). VDD_GPIO is 1.7-3.6 V, so **+3V3 is allowed**.
- Peak current is about **500 mA at 3.7 V** (HDG *Maximum output power*).
  Average TX-subframe current, LTE-M PC3 at 23 dBm, is up to **505 mA at
  3.0 V/85 C/VSWR 3:1** (B1) and 345 mA at 3.7 V/25 C/50 ohm. The worst
  NB-IoT figure is 455 mA (HDG *TX current, Power Class 3*). Bursts
  contain microsecond peaks above these averages, with no number given.
- VDD supply impedance should stay < 0.2 ohm from 10 to 50 kHz (HDG *VDD
  supply impedance*).
- **Sequencing:** VDD_GPIO must come >= 6 ms after VDD and ENABLE and go
  first at power-down. If ENABLE is low, VDD_GPIO must be low too (HDG
  *ENABLE sequence*). The regulation sheet does this: +3V3 rises 12-41 ms
  after +VBAT_LTE (power handoff). So R103 0R ties +3V3 straight to
  VDD_GPIO. The DNP fallback is U21 TPS22917 with an RC-delayed ON
  (R102 100k / C105 1 uF from NRF_VDD; R155 QOD tie; C106 CIN). The
  estimated delay with the 750k smart pull-down is ~10-12 ms to VIL(max)
  0.35 V and ~30 ms to VIH(min) 1.0 V (TI SLVSDW8B VIH/VIL/RPD). That
  estimate is not simulated.
- **ENABLE thresholds**: high >= 0.89xVDD, low <= 0.18xVDD (HDG *ENABLE*).
  Do not drive ENABLE from a 3.3 V GPIO.
- **nRESET**: 13k internal pull-up to 2.2 V, external pull-up not allowed,
  hold low >= 5 us (HDG *nRESET*). The SWD probe can still start 100-500 ms
  after ENABLE (HDG *ENABLE*).

## 4. RF front ends

**LTE (ANT pin 35).** The pin is 50 ohm and DC grounded (HDG *ANT*). The
chain is pi pads C130 (DNP) / R130 (0R) / C131 (DNP), then J10 u.FL to the
antenna pigtail. HDG *ANT* says a matching network of at least three
components is typically needed close to the antenna, tuned per design.
**Place the pi at J10.** For conducted test, J10 itself serves, or move
R130 to R131 to steer to J13 (DNP). D101 is a DNP ESD footprint (HDG *ANT*
recommends extra ESD; no part chosen). The 0402 RF parts give a smaller
pad discontinuity on a 50-ohm line than 0603.

**GNSS (GPS pin 42).** The pin is 50 ohm and DC grounded. Its line loss
must stay <= 0.5 dB, and HDG *GNSS* recommends ESD beyond the on-chip
protection. The design copies the nRF9151 DK, where an external LNA is
enabled from COEX0 (DK UG *GNSS*). HDG *COEX* says COEX0 can drive an
external GNSS LNA, active high, configured with `AT%XCOEX0`.

- **U24 Infineon BGA524N6**: 19.6 dB gain, 0.55 dB NF, 2.5 mA, VCC
  1.5-3.3 V (DS rev 3.5).
- **AI is 0.9 V abs max**, so **C123 1 nF DC block** is required (DS
  Table 6 C1). Without it, the bias-tee option would put DC on the LNA
  input. L101 is 8.2 nH 0402 Murata LQW (DS Table 6 L1; exact MPN still
  open). C129 1 uF VCC bypass (DS Table 6 C2).
- **Supply:** U25 TPS7A0228PDBVR, 2.8 V, EN = COEX0. It is needed because
  BGA524N6 PON is limited to VCC+0.3 V, so COEX0 at 3.3 V cannot drive PON
  on a 2.8 V LNA directly, and VCC max is 3.3 V. PON is tied to VCC. The
  DK also powers its LNA from an LDO switched by COEX0. The power appears
  only during GNSS reception.
- **Bias-tee for an active antenna (DNP):** R122 10R feed from the 2.8 V
  LNA rail, L100 choke, C122 bypass. The DK feeds an external active
  antenna 3.0 V through J2. My choke and resistor values are estimates,
  not from a Nordic BOM.
- **LNA bypass:** fit R124 and remove R123. The tap is after C123, so no
  bias reaches the DC-grounded GPS pin. Then the GPS pin sees the antenna
  passively, or the active antenna's own LNA.
- **Pi pads** C124/R125/C125 sit at the GPS pin, plus shunt C126 at J11.
  D100 is a DNP ESD footprint.
- **Open risk (no pre-filter):** HDG *GNSS* warns that a coupled cellular
  TX signal can damage an external LNA and recommends a filter before the
  LNA. BGA524N6 RF input is 0 dBm abs max. With external antennas, keep
  LTE-to-GNSS antenna isolation high, or prefer an active GNSS antenna
  with an integrated SAW (then bypass U24). A SAW footprint was not added
  because no part was verified.

**SIM.** Per HDG *UICC*: ESD/EMI filtering between the slot and the
nRF9151 is recommended, the interface is 1.8 V Class C, SIM_1V8 can take
100-220 nF, and SIM_RST/CLK/IO should have test pads.

- U22 TPD3F303DPVR is one of the two integrated parts Nordic names. TI
  SLVSAM5A Fig. 6 puts the socket on the OUT side, so DATA1 = RST and
  DATA2 = I/O.
- C111 100 nF.
- J12 is the GCT SIM8060-6-0-14-00-A nano-SIM, with the stock KiCad
  footprint `nanoSIM_GCT_SIM8060-6-0-14-00`. Its shell (SH) goes to GND.
- The DNP eSIM/MFF2 U23 is steered by R110-R113 instead of R106-R109; the
  DK has the same unpopulated MFF2 footprint. **The U23 footprint is a
  placeholder**: the MFF2 pad-to-contact map is unverified.

## 5. BT840 bridge

Pins: P0.26 RX, P0.27 TX, P0.11 RTS, P1.00 CTS, P0.13 IRQ out, P0.02
`LED_LINK`, P0.18/RESET = `RESET_BLE_N`, SWDCLK/SWDIO = `SWDCLK_BLE`/
`SWDIO_BLE`.

- Only castellated pins are used, so the bridge can be probed and reworked
  without X-ray. B4/B5/C3/D2 are still avoided (PA-control pins on
  BT840X/XE). P0.00/P0.01 are left free for an optional 32.768 kHz
  crystal; the plain BT840 has none on-module (DS model summary).
- Power is normal-voltage mode: VDDH (F4) is tied to VDD (+3V3). This is
  Nordic DevZone guidance that the nRF52840 PS shorts VDD/VDDH in normal
  mode; the nRF52840 PS page itself was too large to fetch.
- DCCH (F5) is open. VBUS, D+ and D- are open because USB is unused.
- C5/C6/C7 are kept: generic values, not from the Fanstel datasheet.
- R140-R144 are 0R series on all five bridge lines.
- The BT840 footprint was authored 2026-11-18 (`Fanstel_BT840_Module_14x16mm_16Cast_49LGA`, from Fanstel's own `BT840.lbr`; section 7).

## 6. I2C pull-ups (re-checked)

R37/R38 changed from 2.2k to **3.3k**. The nRF9151 standard-drive sink is
IOL,SD >= 1 mA at 0.4 V (PS *GPIO*), so Rp(min) = (3.3-0.4)/1 mA = 2.9k.
The old 2.2k was sized for the nRF52840 and would need high-drive TWIM
pins. With 3.3k, the rise-time budget (NXP UM10204, tr = 0.8473*Rp*Cb,
300 ns) allows about 107 pF at 400 kHz. If the bus measures above that,
run 100 kHz. R39 (FG_ALRT) stays 2.2k: the MAX17048 sinks it and the
nRF9151 only reads it.

## 7. Footprint status

| Footprint | Status |
|---|---|
| `bay_station:Nordic_nRF9151_LGA-113_12.1x11.1mm_P0.5mm` | **Real pads, 2026-11-18.** From Nordic's own nRF9151 DK hardware files (`400797.PcbDoc`, `LGA50P1210X1110X130-113N`); all 113 pad positions/sizes match the DK top-copper Gerber `400797.GTL`, and the pad numbering agrees with the symbol (GND on 1/20/41/60 and 105-113, RSVD 81-104). Edge pitch is 0.5 mm; the PS `e 0.55` is the inner RSVD pitch. Mask and paste are Altium rules, not in the data: reduce paste on the 1.6 mm ground pads. Still to do when the PS PDF is obtainable: compare with its land-pattern figure. |
| `bay_station:Fanstel_BT840_Module_14x16mm_16Cast_49LGA` | **Real pads, 2026-11-18.** From Fanstel's `BT840.lbr` (package `BT840`, 65 pads), matching the datasheet Ver 1.15 pp. 9-10 drawings. Pad names equal the symbol pin numbers (1-16, Z0-F6). |
| `bay_station:Infineon_TSNP-6-2_0.7x1.1mm_P0.4mm` | Verified against BGA524N6 DS Fig. 5 and Fig. 7 (0.25 mm pads on a 0.4 mm grid; pin 1 from the mirrored bottom view). Paste is KiCad-default square; the DS shows round 100 um stencil apertures. |
| `bay_station:eSIM_MFF2_PLACEHOLDER` | DNP part; pad map not verified. |
| U.FL (Hirose U.FL-R-SMT-1(10)), SIM8060, TPD3F303 USON-8, SOT-23-5/6 | Stock KiCad footprints. The Hirose PDF was not downloaded. |
