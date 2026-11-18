# Handoff: mcu agent (connectivity sheet)

Branch `worktree-agent-a9777b372b04937a7`, based on `redesign/nrf9151-host`
(merged at 2ea1810, which added `docs/net-contract.md`). Per-sheet detail and
every citation are in `bay-station/connectivity_notes.md`.

## 1. Summary

**`connectivity.kicad_sch`** was rebuilt. The paper size changed from A4 to A2.
Every pin is either wired to a label with a short wire or flagged no-connect.
A netlist cross-check, comparing intended (ref, pin) -> net against the
kicad-cli netlist, gives 0 mismatches.

- **U20 nRF9151-LACA-R7** (orderable code per PS *Ordering information*;
  `nRF9151-LACA-R` is the 2000-MOQ reel). The flattened symbol has 113 pins.
  GPIO is on the right side. Power, control, SIM, RF and COEX are on the
  left. RSVD 81-104 run along the top and bottom edges as individual pins,
  each no-connect. All GND pins are stacked.
- **Decoupling** is exactly the HDG *Schematic design* BOM:
  - VDD bank on `+VBAT_LTE`: FB10 BLM18SD220SN1 (FB1), C100/C101 1 uF
    (C1/C2), C102 47 uF (C3), C103 10 uF (C4).
  - ENABLE: R101 10k from VDD (R1), plus C104 100 nF.
  - VDD_GPIO: C107 4.7 uF (C6) and C108 100 nF (C5).
  - DEC0: C109 4.7 uF (C7).
  - nRESET: C110 100 nF (C8) at the pin. Nordic's R2 1k is R313 on
    programming_debug, and there is no pull-up.
- **VDD_GPIO** = `+3V3` through R104 (a 0R current-measure link) and R103
  0R. This relies on the power agent's +3V3 delay. A DNP fallback
  load-switch option is laid out: U21 TPS22917 with R102/C105/C106/R155.
- **LTE**: pi pads C130/R130/C131 -> J10 u.FL. Optional steering R131 -> J13
  (DNP test port). D101 is a DNP ESD footprint.
- **GNSS**: J11 u.FL -> DC-block C123 -> L101 8.2 nH -> U24 BGA524N6 LNA ->
  R123 -> pi pads C124/R125/C125 -> GPS pin.
  - U25 TPS7A0228PDBVR (2.8 V), enabled by COEX0, powers the LNA (DK-style).
  - DNP bias-tee for an active antenna: R122/L100/C122.
  - DNP LNA bypass: R124.
  - DNP ESD footprint D100 and shunt C126.
- **SIM**: U22 TPD3F303DPVR ESD/EMI filter, J12 GCT SIM8060-6-0-14-00-A
  nano-SIM, C111 100 nF on SIM_1V8. DNP eSIM/MFF2 U23 is selected by 0R
  steering (R106-R109 fitted, R110-R113 DNP).
- **BT840 U3** is now the bridge:
  - UART with the cross-over done on this sheet, through R140-R144 0R.
  - SWD to `SWDIO_BLE`/`SWDCLK_BLE`. Pin 14 to `RESET_BLE_N`. LED_LINK on
    P0.02 (pin 5).
  - VDD/VDDH on +3V3. C5/C6/C7 kept.
- **Series links on the nRF side**: R150-R152 (UWB SPI), R153/R154 (I2C),
  R145 (RESET_BLE_N).
- **R37/R38 changed 2.2k -> 3.3k.** The nRF9151 standard-drive IOL is
  1 mA min. R39 stays 2.2k. They connect to `I2C_SDA`/`I2C_SCL`/`FG_ALRT`.
- **Libraries**: `bay_station.kicad_sym` gained nRF9151, BGA524N6,
  TPS7A0228PDBVR and eSIM_MFF2. `bay_station.pretty` gained:
  - `Infineon_TSNP-6-2_0.7x1.1mm_P0.4mm` (verified)
  - `Nordic_nRF9151_LGA-113_12.1x11.1mm_PLACEHOLDER` (**pad map is fake,
    do not fab**)
  - `eSIM_MFF2_PLACEHOLDER`
- **ERC, whole project:** before **596** violations (Connectivity 90),
  after **536** (Connectivity **3**). All 3 remaining are cross-sheet
  drivers:
  - U20 SWDCLK input not driven: the J3 header is passive.
  - U3 SWDCLK not driven: same reason.
  - U3 VDD power_in: `+3V3` has no power_out on this branch's regulation
    sheet.

  Root isolated-label warnings went from 6 to 33, because the other sheets
  have not wired their ends yet. lib_symbol_mismatch is unchanged at 9.
- **Component count:** 145 -> 228 in the netlist. Connectivity has 90
  parts, so no part was silently dropped.
- **How the sheet was produced:** a generator script in my scratchpad
  (`/private/tmp/claude-501/-Users-lucaspoulos/dd400aaa-ed37-42a6-ac0b-1e8712b55e20/scratchpad/mcu/gen/gen.py`,
  not committed). The sheet is plain KiCad and can be hand-edited from here.

## 2. components.csv rows

Remove the BT840 row's "host for the 4x DW3210" wording (now BLE bridge).
Add:

```csv
Host MCU + LTE-M/NB-IoT modem + GNSS (connectivity U20),Nordic nRF9151-LACA-R7,bay_station:nRF9151 (hand-authored),bay_station:Nordic_nRF9151_LGA-113_12.1x11.1mm_PLACEHOLDER (PLACEHOLDER),https://docs.nordicsemi.com/bundle/ps_nrf9151/page/pin.html,"Order code from nRF9151 PS v1.0 Ordering information (nRF9151-LACA-R MOQ 2000 / -R7 MOQ 100). 113-pin map transcribed from the PS Pin assignments table, HTML rendition (PDF blocked by Cloudflare) -- re-check against the PDF. FOOTPRINT PAD MAP IS NOT NORDIC GEOMETRY: replace from HDG Footprint figures / Nordic reference layout before fab."
nRF9151 VDD ferrite bead (FB10),Murata BLM18SD220SN1,Device:FerriteBead (KiCad default),Inductor_SMD:L_0603_1608Metric,https://www.murata.com/en-us/products/productdetail?partno=BLM18SD220SN1%23,"Named by nRF9151 HDG Schematic design BOM as FB1 (22 ohm@100 MHz, 6 A, 8 mOhm). Murata datasheet not separately downloaded."
"nRF9151 decoupling (C100-C104, C107-C110)","1 uF x2, 47 uF 0805, 10 uF, 100 nF x3, 4.7 uF x2 X5R",Device:C,Capacitor_SMD:C_0603_1608Metric / C_0805_2012Metric (C102),n/a,"Values = nRF9151 HDG Schematic design BOM C1-C8 (Nordic examples are Murata GRM 0201/0402; 0603/0805 used per repo standard -- HDG allows it with similar DCR/frequency behaviour). C104 = ENABLE cap per HDG ENABLE."
nRF9151 ENABLE series resistor (R101),10k 0603,Device:R,Resistor_SMD:R_0603_1608Metric,n/a,"HDG BOM R1; HDG ENABLE: tie ENABLE to VDD through a series resistor. Power sequencing (+3V3 after +VBAT_LTE) assumes this."
"VDD_GPIO links (R104 current-measure 0R, R103 0R bypass)",0R 0603,Device:R,Resistor_SMD:R_0603_1608Metric,n/a,"R103 fitted because regulation delays +3V3 12-41 ms after +VBAT_LTE (HDG ENABLE sequence >= 6 ms)."
"DNP VDD_GPIO sequencing switch (U21 + R102/C105/C106/R155, all DNP)",TI TPS22917DBVR,Power_Management:TPS22917DBV (KiCad default),Package_TO_SOT_SMD:SOT-23-6,https://www.ti.com/lit/ds/symlink/tps22917.pdf,"Rework fallback only. Pinout verified SLVSDW8B Fig 6-1/Table 6-1 with pdftotext -layout (-raw scrambles it): 1 VIN 2 GND 3 ON 4 CT 5 QOD 6 VOUT. TPS22917DBVR Active in the packaging addendum."
GNSS LNA (U24),Infineon BGA524N6 (distributor OPN BGA524N6E6327XTSA1),bay_station:BGA524N6 (hand-authored),bay_station:Infineon_TSNP-6-2_0.7x1.1mm_P0.4mm (hand-authored),https://www.infineon.com/part/BGA524N6,"Data Sheet Rev 3.5 2021-08-31 (read from a third-party mirror copy; infineon.com PDF link not resolvable). Pins Table 1: 1 GND 2 VCC 3 AO 4 GND 5 AI 6 PON. Footprint from Fig 5/Fig 7 (0.25 mm pads, 0.4 mm grid) -- verified. The OPN with E6327/XTSA1 suffix was seen at element14/LCSC only; confirm on infineon.com before ordering."
GNSS LNA input match + DC block (L101 / C123),8.2 nH 0402 Murata LQW / 1 nF 0402,Device:L / Device:C,Inductor_SMD:L_0402_1005Metric / Capacitor_SMD:C_0402_1005Metric,n/a,"BGA524N6 DS Table 6 L1 and C1. C123 is mandatory here (AI abs max 0.9 V, bias-tee option). L101 exact LQW15 MPN not yet chosen."
GNSS LNA LDO (U25),TI TPS7A0228PDBVR,bay_station:TPS7A0228PDBVR (hand-authored),Package_TO_SOT_SMD:SOT-23-5 (KiCad default),https://www.ti.com/lit/ds/symlink/tps7a02.pdf,"SBVS277C Table 5-1 DBV: 1 IN 2 GND 3 EN 4 NC 5 OUT. 2.8 V, EN from nRF9151 COEX0 (HDG COEX: GNSS LNA control, active high). Orderable listed Active. DK uses the same LDO-switched-by-COEX0 scheme."
SIM ESD/EMI filter (U22),TI TPD3F303DPVR,Power_Protection:TPD3F303DPV (KiCad default),Package_SON:Texas_R-PUSON-N8_USON-8-1EP_1.6x2.1mm_P0.5mm_EP0.4x1.7mm (KiCad default),https://www.ti.com/lit/ds/symlink/tpd3f303.pdf,"Named by nRF9151 HDG UICC. Pins SLVSAM5A match the KiCad symbol; Fig 6 orientation: socket on OUT side (DATA1=RST, DATA2=I/O)."
Nano-SIM holder (J12),GCT SIM8060-6-0-14-00-A,Connector:SIM_Card_Shielded (KiCad default),Connector_Card:nanoSIM_GCT_SIM8060-6-0-14-00 (KiCad default),https://gct.co/files/drawings/sim8060.pdf,"Verified on GCT drawing rev A6 (2025-01-21) ordering grid: 6 contacts, no detect switch, 1.43 mm, tape & reel. Hinged type."
DNP eSIM MFF2 (U23) + steering 0R (R106-R113),DNP / 0R 0603,bay_station:eSIM_MFF2 (hand-authored),bay_station:eSIM_MFF2_PLACEHOLDER,n/a,"Option mirrors nRF9151 DK unpopulated MFF2 footprint. Pad map NOT verified (ETSI TS 102 671)."
"RF connectors LTE / GNSS / LTE test (J10, J11, J13 DNP)",Hirose U.FL-R-SMT-1(10),Connector:Conn_Coaxial (KiCad default),Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical (KiCad default),https://www.hirose.com/product/series/U.FL,"Hirose PDF not downloaded (fetch failed) -- verify MPN and footprint. LTE/GNSS only (< 6 GHz); UWB CH5 stays SMA."
"RF pi/steering pads (C124-C126, C130, C131, R123-R125, R130, R131) and DNP ESD (D100, D101) and DNP bias tee (L100, R122, C122)",0R / DNP 0402,Device:R / Device:C / Device:D_TVS / Device:L,*_0402_1005Metric,n/a,"0402 on RF paths (smaller discontinuity than 0603 at 0.7-2.2 GHz). HDG ANT/GNSS: >=3-component match, extra ESD recommended. ESD and bias-tee part values not chosen (estimates)."
"Bridge / host series links (R140-R145, R150-R154)",0R 0603,Device:R,Resistor_SMD:R_0603_1608Metric,n/a,"Rework links; R150/R151 can become 33-100R edge-rate resistors (HDG GPIOs)."
"Local test pads (TP40-TP50, TP52, TP53)",test pad,Connector:TestPoint,TestPoint:TestPoint_Pad_D1.0mm,n/a,"Sheet-local nets only (SIM, COEX1/2, LNA rail/enable, NRF_VDD, VDD_GPIO, ENABLE, DEC0, VGPIO_IN)."
```

Change: the I2C pull-up row for **R37/R38 becomes 3.3k** (reason: nRF9151
PS GPIO IOL,SD min 1 mA at 0.4 V gives Rp(min) 2.9k). R39 stays 2.2k.

## 3. decisions.md entries

Resolved:

- **nRF9151 GPIO allocation** is fixed in `connectivity_notes.md` section 2.
  The four serial IDs: UARTE0 debug, UARTE1 bridge, TWIM2 I2C, SPIM3 UWB.
  The charger STAT/PG nets go to LEDs only; the chip is out of pins and the
  nodes idle near +VSYS.
- **UWB SPI is 8 MHz max.** That is every nRF91 SPIM instance (nrfx MDK
  nrf9120 `SPIMn_MAX_DATARATE 8`). The 32 MHz/SPIM3 note in
  `docs/positioning.md` and `docs/system-overview.md` was for the nRF52840
  and is now stale. Rewrite it.
- **GNSS front end copies the nRF9151 DK.** BGA524N6 LNA, its TPS7A02 LDO
  switched by COEX0, DNP bias-tee for an active antenna, DNP LNA bypass.
- **SIM**: TPD3F303 + GCT SIM8060 nano-SIM, with a DNP MFF2 eSIM.
- **I2C pull-ups 3.3k** (was 2.2k).

New Open:

- **nRF9151 footprint**: the real land pattern is still needed (HDG
  *Footprint* figures or Nordic reference layout). The current one is a
  placeholder.
- **GNSS LNA has no pre-filter.** HDG *GNSS* warns that LTE TX coupling can
  damage an external LNA. The decision is between an LTE-GNSS antenna
  isolation budget, a verified 1575 MHz SAW footprint, or an active antenna
  with LNA bypass.
- **The Nordic PS/HDG PDFs were read only as HTML**, because the PDF
  download was Cloudflare-blocked. Re-verify the pin table against the PDF
  with pdftotext -layout/-raw.
- The RF ESD diodes (D100/D101), the bias-tee values and the L101 MPN are
  still to be chosen.
- **Modem UART trace conflicts with the bridge UART** (UARTE1). Use the RTT
  trace backend instead.

## 4. net-contract.md changes

- **`+3V3` row**: "nRF9151 VIO" -> "nRF9151 **VDD_GPIO** (1.7-3.6 V, PS
  Operating conditions); must rise >= 6 ms after `+VBAT_LTE`/ENABLE and fall
  first (HDG ENABLE sequence)". The nRF9151 VIO pin (29) is a 1.8 V MIPI
  RFFE output, unused.
- **`+VBAT_LTE` row**: feeds nRF9151 **VDD** pin 14 (3.0-5.5 V incl. ripple,
  ~500 mA peak at 3.7 V) and, through R101, ENABLE.
- **`TCXO_EN`**: delete (the TCXO has no enable pin; uwb agent).
- **`RESET_MCU_N`**: "no pull-up anywhere (HDG nRESET); 1k series is R313;
  100 nF C110 at the pin".
- **`UWB_RST_N`, `RESET_BLE_N`**: "driven open-drain only".
- **Section 7 status nets**: "not routed to any GPIO (out of pins; nodes idle
  near +VSYS)".
- No new cross-sheet nets. I do not use `+5V_IN`.

## 5. For other sheet owners

- **power**: +VBAT_LTE and ENABLE are wired as you assumed. ENABLE is
  NRF_VDD (= +VBAT_LTE after FB10) through R101 10k + C104. No second 1k
  on nRESET. Figures you asked for, all from the HDG:
  - VDD 3.0-5.5 V.
  - Peak about 500 mA at 3.7 V (*Maximum output power*).
  - Worst average TX subframe 505 mA (LTE-M PC3, 23 dBm, B1, 3.0 V, 85 C,
    VSWR 3:1), 345 mA at 3.7 V/25 C/50 ohm.
  - Supply impedance < 0.2 ohm from 10 to 50 kHz.
  - VDD_GPIO current: the HDG says nothing more. Your 10 mA estimate is
    fine. My LNA LDO adds about 3 mA, plus an active antenna if fitted
    (~10-20 mA), on +3V3 only during GNSS.
- **uwb**: SPIM3, mode 0, **8 MHz max**. The DW3210 may need a slower rate
  until its PLL locks; firmware can start at 2 MHz. UWB_RST_N is driven
  open-drain. Pin numbers are in the table below.
- **io/indicators**: the LEDs at 1.1 mA are OK. Standard drive guarantees
  IOH >= 1 mA at VDD-0.4 V, typ 2 mA. Firmware may use H0H1 if they are dim.
  LED_LINK is on BT840 P0.02 (castellated pin 5). The status nets are not
  routed.
- **io/testpoints**: add pads for every contract net used here; I placed
  none on contract nets. **My local test pads are TP40, TP41, TP42, TP43,
  TP44, TP45, TP46, TP47, TP48, TP49, TP50, TP52, TP53** (TP51 unused). I
  had no TP block, so I chose TP40-TP59, clear of the existing TP1-TP21 and
  of TP100+. Renumber freely.
- **programming_debug**: J3 SWDCLK/SWDIO and RESET_MCU_N as you wired them.
  BTN_USER: the nRF9151 internal pull-up is assumed unless you fit one.
- **gnss/orientation**: MAG_DRDY P0.24, MAG_INT P0.25, ACC_INT1 P0.07,
  ACC_INT2 P0.26. I2C pull-ups are here (R37/R38).
- **firmware**: use the GPIO table below. TWIM pins S0D1. UWB_RST_N and
  RESET_BLE_N open-drain. COEX0: `AT%XCOEX0` LNA enable during GNSS. Do
  not use UART modem trace on UARTE1.

## 6. Unverified / risks

1. **The nRF9151 footprint is fake geometry.** It is the biggest blocker
   to fab.
2. **Nordic facts come from the HTML PS/HDG through a text-extraction fetch,
   not from PDFs.** The pin table was taken in two halves and the counts
   check out (113 unique pins, GND list consistent). Figures (pinout
   drawing, reference schematic) could not be seen. The "slow pins near the
   RF corner" choice rests on pin numbering only.
3. **GNSS LNA has no pre-filter.** There is a risk of LTE-TX damage or
   desense (HDG GNSS).
4. **Zero spare GPIOs.** Any new signal (e.g. a TCXO enable, a second
   button) needs a GPIO expander or must move to the BT840.
5. **Third-party sources**: the BGA524N6 datasheet copy came from a mirror,
   and its OPN was seen only at distributors. The Hirose U.FL datasheet was
   not read. The MFF2 pad map is unverified. The BT840 VDDH-to-VDD tie rests
   on Nordic DevZone answers, because the nRF52840 PS page was too large to
   fetch. The BT840 footprint is still missing (pre-existing).

## GPIO allocation table (copy of connectivity_notes.md section 2)

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
`LED_LINK` is on the BT840, per the contract. **No spare GPIOs remain**, and
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
| 64 | P0.07 | `ACC_INT1` | in | GPIOTE | LIS2DH INT1 (knock/move) |
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
| 11 | P0.24 | `MAG_DRDY` | in | GPIOTE | LIS3MDL |
| 12 | P0.25 | `MAG_INT` | in | GPIOTE | LIS3MDL |
| 44 | P0.26 | `ACC_INT2` | in | GPIOTE | LIS2DH INT2 |
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

