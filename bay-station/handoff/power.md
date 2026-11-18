# Handoff: power agent (power_bms, regulation, programming_debug)

Branch `worktree-agent-ac7d58e612def7be5`, based on `redesign/nrf9151-host`
(merged `2ea1810`, net contract). Per-sheet detail lives in
`regulation_notes.md`, `power_bms_notes.md`, `programming_debug_notes.md`.

## 1. Summary of changes

### regulation.kicad_sch (fully wired)

- **U8 TPS62A02 -> `+3V3`.** VIN on `+VSYS`; FB divider R8/R9 453k/100k
  re-checked against TI SLUSEG9E Eq. 2 (VFB 600 mV) = 3.318 V. EN is driven
  by a delay network (R303 100k / C303 1 uF / R304 4.7k from U40 PG) so
  `+3V3` (= nRF9151 `VDD_GPIO`) rises 12-41 ms after `+VBAT_LTE` and falls
  first -- Nordic HDG *VDD_GPIO* requires >= 6 ms. DNP R305 restores the
  old EN-to-`+VSYS`. PG to TP405 with R301 pull-up; gates nothing.
- **Bug fixed: C22 (120 pF feedforward) was wired `+3V3`-to-GND**, not
  across R8 as its description said. Moved across R8, made DNP (TI's 120 pF
  is for 1.8 V; unverified at 3.3 V).
- **L1 now has a footprint**: Coilcraft XFL4020-102MEC (1.0 uH, Isat 4.5 A,
  Coilcraft doc 745-1) on `Inductor_SMD:L_Coilcraft_XxL4020`, replacing the
  footprint-less XGL3520-102MEC.
- **New U40 TPS63802DLAR buck-boost -> `+VBAT_LTE` (3.588 V)** for nRF9151
  `VDD`. Reasoning in Sec 3 below. L300 XFL4020-471MEC, C300 10 uF, C301
  22 uF (+ DNP C302), FB 562k/91k (TI Table 10-5), EN UVLO divider
  191k/100k (off < 2.91 V / on > 3.20 V `+VSYS`), MODE strap 0R to GND (PSM)
  with DNP forced-PWM option.
- **Current break points**: R300 (`+3V3`) and R302 (`+VBAT_LTE`), 0R 0805,
  each with a DNP 2-pin 2.54 mm header (J30, J31) for a PPK2. Feedback,
  PG pull-up and EN pull-up all on the regulator side of the link.
- **Test pads TP400-TP413** on both rails (both sides of each link), SW,
  FB, EN, PG of both converters, U40 L1/L2 and MODE. Switch-node pads carry
  a "pad on existing copper or leave unplaced" layout note.
- New symbol `bay_station:TPS63802` (lib + embedded); new footprint
  `bay_station:TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm_PLACEHOLDER`.

### power_bms.kicad_sch

- `FG_SCL` -> **`I2C_SCL`**, `FG_SDA` -> **`I2C_SDA`** (contract Sec 4).
  `FG_ALRT` unchanged. Nothing else in the wired circuit touched.
- Test pads TP414 `+5V_IN`, TP415 `VBATT_PROT`, TP416 `THERM`, TP417
  `BATT_RAW`.
- **THERM cold-charge cutoff sized** (MCP73871 DS20002090E Sec 1.0): a plain
  10k NTC with B25/50 = 3380-3435 K stops charging between +1.1 and +5.3 C
  cold and +40 and +49 C hot across all ITHERM/VT1/VT2 tolerances. **No trim
  resistors needed.** The NTC must be on the cell (3-wire pack NTC). TH1's
  part is not changed (pack not chosen).

### programming_debug.kicad_sch (rebuilt, A4 -> A3)

- **J3** (existing) = nRF9151 SWD (`SWDIO_MCU`, `SWDCLK_MCU`, nRESET via
  R313 1k to `RESET_MCU_N`), VTref `+3V3`, GND on 3/5/9, 6/7/8 NC.
- **J32** (new) = BT840 SWD (`SWDIO_BLE`, `SWDCLK_BLE`, `RESET_BLE_N`).
- **J34 / J35**: DNP Tag-Connect TC2030-IDC-NL footprints for each target.
  Pinout verified from the Tag-Connect TC2030-CTX datasheet.
- **R313 1k** series on the nRF9151 reset path: Nordic HDG *nRESET*
  (13k internal pull-up to 2.2 V, "External pull-up is not allowed",
  ~1k series + bypass cap recommended).
- **SW2** (nRF9151 reset, existing), **SW11** (BT840 reset), **SW12**
  (`BTN_USER`): all Omron B3U-1000P, footprint
  `Button_Switch_SMD:SW_SPST_B3U-1000P`. **SW2's footprint gap is closed.**
  DNP R315 pull-up / C304 debounce on `BTN_USER`.
- **J33** debug UART 1x4 2.54 mm: GND, `DBG_UART_TX`, `DBG_UART_RX`,
  `DBG_VREF` (isolated from `+3V3` unless DNP R314 fitted, so a cable's 5 V
  VCC cannot back-feed). No USB-UART bridge (not trivial: J2 is power-only).

### ERC (kicad-cli 10, `bay-station.kicad_sch`, run from scratch dir)

| | Before | After |
|---|---|---|
| Total violations | 596 | 586 |
| /Regulation/ | 4 (2 pin_not_connected, 1 pin_not_driven, 1 power_pin_not_driven) | **0** |
| /Programming / Debug/ | 10 (8 pin_not_connected, 1 pin_not_driven, 1 power_pin_not_driven) | **0** |
| /Power BMS/ | 1 (U2 SCL pin_not_driven) | 1 (same; clears when connectivity drives `I2C_SCL`) |
| Root-level warnings | 6 isolated_pin_label, 9 lib_symbol_mismatch, 1 lib_symbol_issues | 9 isolated_pin_label (+`DBG_UART_TX/RX`, `RESET_MCU_N`: single-ended until connectivity wires them), 10 lib_symbol_mismatch (+J32, same embedded Cortex symbol as J3), 1 lib_symbol_issues (U8, long-standing) |
| Components (netlist) | ~145 | 194 -- non-zero, no `extends` failure |

## 2. components.csv rows

Header: `Reference/Role,Part,Symbol lib:name,Footprint lib:name,Datasheet URL,Notes/confidence`

**Change** (replace the existing L1 row and the NTC row):

```csv
"Power inductor (regulation.kicad_sch, L1)","Coilcraft XFL4020-102MEC, 1.0uH",Device:L (KiCad default),Inductor_SMD:L_Coilcraft_XxL4020 (KiCad default),https://www.coilcraft.com/pdfs/xfl4020.pdf,"Replaces XGL3520-102MEC (no KiCad footprint). Coilcraft Doc 745-1 (rev 03/10/26): DCR 10.80/11.90 mOhm, Isat 4.5 A (10% drop) / 5.1 A (20%), Irms 5.4 A (20 C rise). Above TPS62A02 IHS(OC) 3.4 A max (SLUSEG9E Table 6.5). 1uH/22uF is the '++' pair in Table 8-3. Confidence: high."
NTC thermistor (MCP73871 THERM pin),"10k NTC, B25/50 3380-3435 K, thermally bonded to the cell (prefer the battery pack's own NTC); e.g. Murata NCP18XH103F03RB (B25/50 3380 K) if board-mounted",Device:Thermistor_NTC (KiCad default),Resistor_SMD:R_0603_1608Metric,https://www.murata.com/en-us/products/productdetail?partno=NCP18XH103F03RB,"Sized 2026-11-17 from MCP73871 DS20002090E Sec 1.0 (ITHERM 47/50/53 uA, VT1 1.20/1.24/1.26 V, VT2 0.23/0.25/0.27 V): cold cut-off +1.1..+5.3 C, hot +40..+49 C, no trim resistors. NCP18XH103F03RB B value read from a Murata-generated sheet (TI E2E copy), not Murata's own PDF; DigiKey marks it Not For New Designs -- re-check whatever part is bought. power_bms_notes.md 'THERM cold-charge window'."
```

**Add:**

```csv
"Buck converter, +VSYS -> +3V3 (regulation.kicad_sch, U8)",TI TPS62A02PDDCR,Regulator_Switching:TPS62A02PDDCR (flattened embedded copy -- see decisions.md),Package_TO_SOT_SMD:SOT-23-6 (KiCad default),https://www.ti.com/lit/gpn/tps62a02,"Missing row (decisions.md Open). 2.5-5.5 V in, 2 A, VFB 600 mV; pins 1 EN 2 GND 3 SW 4 VIN 5 PG 6 FB (SLUSEG9E Table 5-1). FB 453k/100k -> 3.318 V. EN delayed after U40 PG for nRF9151 VDD_GPIO sequencing. Confidence: high."
"Buck-boost, +VSYS -> +VBAT_LTE / nRF9151 VDD (regulation.kicad_sch, U40)",TI TPS63802DLAR,bay_station:TPS63802 (hand-authored),bay_station:TI_DLA0010A_VSON-HR-10_2x3mm_P0.5mm_PLACEHOLDER,https://www.ti.com/lit/gpn/tps63802,"SLVSEU9D (rev Jan 2021): VIN 1.3-5.5 V, VOUT 1.8-5.2 V, 2 A out for VI >= 2.3 V at 3.3 V, VFB 500 mV, IQ 11 uA. Pins (Table 7-1) 1 EN 2 MODE 3 AGND 4 FB 5 PG 6 VOUT 7 L2 8 GND 9 L1 10 VIN. FB 562k/91k -> 3.588 V (Table 10-5). FOOTPRINT IS A PLACEHOLDER (DLA0010A land pattern not resolved from text) -- verify before fab."
"Buck-boost inductor (regulation.kicad_sch, L300)","Coilcraft XFL4020-471MEC, 0.47uH",Device:L (KiCad default),Inductor_SMD:L_Coilcraft_XxL4020 (KiCad default),https://www.coilcraft.com/pdfs/xfl4020.pdf,"TPS63802 needs 0.47 uH (0.37-0.57 effective, SLVSEU9D Sec 8.3). Coilcraft 745-1: DCR 4.40/5.10 mOhm, Isat 4.6 A (10%) / 6.6 A (20%), Irms 7.5 A. TI Table 10-2 lists XFL4015-471ME; XFL4020 used for its KiCad footprint. Confidence: high."
"Regulator bulk caps (regulation.kicad_sch, C300 10uF, C301/C302 22uF, C303 1uF)","Generic X5R/X7R ceramic: 10uF 0805 10V, 22uF 0805 10V (C302 DNP), 1uF 0603",Device:C (KiCad default),Capacitor_SMD:C_0805_2012Metric / C_0603_1608Metric,n/a (generic passive),"C300/C301 per SLVSEU9D Sec 10.2.2.3-10.2.2.4 (10uF in, single 22uF out for VO <= 3.6 V); 0805/10 V for DC-bias derating at ~5 V. C303 = EN_3V3 delay cap (tau 100 ms with R303)."
"Current-measurement break links (regulation.kicad_sch, R300 +3V3, R302 +VBAT_LTE)",0R jumper 0805,Device:R (KiCad default),Resistor_SMD:R_0805_2012Metric,n/a (generic),"Remove to insert a PPK2 (ampere-meter mode, 1 A max) across J30/J31. 0805 for ~2 A jumper rating (check the chosen part); +VBAT_LTE carries 0.5 A TX subframes."
"PPK2 / ammeter headers (regulation.kicad_sch, J30, J31) -- DNP",1x2 2.54 mm pin header,Connector_Generic:Conn_01x02 (KiCad default),Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical,n/a (generic),"DNP footprints across R300/R302. Pin 1 = regulator side (PPK VIN), pin 2 = load side (PPK VOUT)."
"Local test pads (regulation TP400-TP413, power_bms TP414-TP417)",Bare copper test pad,Connector:TestPoint (KiCad default),TestPoint:TestPoint_Pad_D1.0mm,n/a,"Rails both sides of each break link, FB/EN/PG/SW of U8 and U40, MCP73871 THERM, +5V_IN, VBATT_PROT, BATT_RAW. Switch-node pads (TP402/411/412) only if they can sit on existing copper."
"SWD headers (programming_debug.kicad_sch, J3 nRF9151, J32 BT840)",ARM Cortex 10-pin 2x05 1.27 mm header (Samtec FTSH-105 series or equivalent -- pick PN at BOM time),Connector:Conn_ARM_JTAG_SWD_10 (KiCad default),Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical,https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/TC2030-CTX_1.pdf,"J3 had no row (decisions.md Open). Pinout per the Tag-Connect TC2030-CTX datasheet Cortex column. VTref = +3V3."
"Tag-Connect SWD footprints (programming_debug.kicad_sch, J34, J35) -- DNP",Tag-Connect TC2030-IDC-NL footprint (no part fitted; cable TC2030-CTX-NL),Connector:Conn_ARM_SWD_TagConnect_TC2030 (KiCad default),Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical (KiCad default),https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/TC2030-CTX_1.pdf,"Pinout verified: 1 VCC 2 SWDIO 3 nRESET 4 SWCLK 5 GND 6 SWO. Pads only -- nothing to buy for the board."
"Debug UART header (programming_debug.kicad_sch, J33)",1x4 2.54 mm pin header,Connector_Generic:Conn_01x04 (KiCad default),Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical,n/a (generic),"1 GND, 2 DBG_UART_TX, 3 DBG_UART_RX, 4 DBG_VREF (to +3V3 only via DNP R314). 3.3 V logic."
"Push buttons (programming_debug.kicad_sch, SW2 nRF9151 reset, SW11 BT840 reset, SW12 BTN_USER)",Omron B3U-1000P,Switch:SW_Push (KiCad default),Button_Switch_SMD:SW_SPST_B3U-1000P (KiCad default),https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3u.pdf,"SW2 had no footprint and no row (decisions.md Open) -- resolved. B3U-1000P: top-actuated, no ground terminal (Omron B3U catalogue)."
"nRF9151 reset series resistor (programming_debug.kicad_sch, R313)",1k 0603,Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric,n/a (generic),"Nordic nRF9151 HDG nRESET: ~1 kOhm series, no external pull-up (13k internal to 2.2 V)."
```

The remaining small resistors (R301, R303-R312, R314, R315) and C304 are
covered by the existing generic `Resistors` / capacitor rows.

## 3. decisions.md entries

**Move Open -> Resolved** (the "U8 lib_symbol_issues / missing BOM rows"
item -- keep its U8-symbol paragraph Open, resolve the rest):

```markdown
- **SW2 footprint, and BOM rows for U8 / SW2 / J3** -- resolved 2026-11-17.
  SW2 is an Omron B3U-1000P on `Button_Switch_SMD:SW_SPST_B3U-1000P`; rows
  for U8, J3 and the new buttons/headers were added to `components.csv`.
  **L1's footprint gap is also closed**: L1 is now a Coilcraft XFL4020-102MEC
  (KiCad `L_Coilcraft_XxL4020`) instead of the footprint-less XGL3520.
  The U8 flattened-symbol warning itself is unchanged and stays Open.
```

```markdown
- **Li-Ion charging below 0 degC (MCP73871 THERM)** -- resolved 2026-11-17.
  With the MCP73871's own tolerances (DS20002090E Sec 1.0: ITHERM
  47-53 uA, VT1 1.20-1.26 V, VT2 0.23-0.27 V) a plain 10k NTC with
  B25/50 = 3380-3435 K suspends charging below +1.1..+5.3 C and above
  +40..+49 C. No trim resistors. The remaining requirement is mechanical:
  the NTC must sit on the cell (use the pack's NTC). See
  `bay-station/power_bms_notes.md`.
```

```markdown
- **Bay station power budget re-check** -- re-run 2026-11-17 for the
  nRF9151 architecture. `+3V3`: ~356 mA peak (~446 mA if the nRF9151
  VDD_GPIO hits Nordic's 100 mA momentary ceiling) vs TPS62A02 2 A.
  `+VBAT_LTE`: 505 mA LTE-M TX subframe (nRF9151 HDG, B1, 3.0 V, 85 C,
  VSWR 3:1) vs TPS63802 2 A. Still estimates: BT840 total, nRF9151
  VDD_GPIO, TCXO, fan-out buffer. Table in `bay-station/handoff/power.md`.
```

**New Resolved:**

```markdown
- **nRF9151 VDD gets its own buck-boost (`+VBAT_LTE`, TI TPS63802, 3.59 V)**
  -- 2026-11-17. On battery `+VSYS` is the cell minus Q1 and the MCP73871
  BAT-to-OUT FET (200 mOhm typ, DS20002090E), ~0.3 V at board peak, so a
  direct feed falls under Nordic's 3.2 V LTE recommendation (3.0 V floor
  "includes all voltage drops, ripple, and spikes", nRF9151 HDG) for the
  last part of the discharge, and the path impedance already exceeds the
  HDG's 0.2 Ohm (3.75-50 kHz) target. TPS63802 regulates through the whole
  2.9-5.25 V input range and its PG sequences `+3V3` (nRF9151 VDD_GPIO)
  >= 6 ms later. Rejected: direct jumper (above); TPS63000 (800 mA boost
  rating too close to 505 mA). `bay-station/regulation_notes.md` Sec 1.
- **Board-level battery UVLO at `+VSYS` = 2.91 V** (TPS63802 EN divider,
  191k/100k; on again at 3.20 V). Turns both rails off together.
```

**New Open:**

```markdown
- **U40 (TPS63802) footprint is a PLACEHOLDER** -- the DLA0010A land
  pattern did not extract cleanly; land sizes for pins 6-10 are estimated.
  Verify against the rendered SLVSEU9D page or TI's CAD model before fab.
- **Nordic PDFs not downloaded** (Cloudflare challenge). nRF9151 PS / HDG
  facts were read from docs.nordicsemi.com HTML pages; record the PDF
  revisions once fetched.
- **nRF9151 ENABLE assumed tied to `+VBAT_LTE`** (HDG ENABLE: series
  resistor + decoupling). The `VDD_GPIO`-after-VDD sequencing depends on it.
```

## 4. net-contract.md changes requested

- **`+VBAT_LTE` row**: the nRF9151 pin is named **`VDD`** (PS:
  "VDD -- Battery input voltage, 3.0 / 3.7 / 5.5 V"), not VBAT. Keep the net
  name; change the note to: "nRF9151 `VDD`. Source: U40 TPS63802 buck-boost,
  3.59 V (decided on regulation). Break point R302/J31."
- **`+3V3` row**: "nRF9151 VIO" should read **"nRF9151 `VDD_GPIO`
  (1.7-3.6 V, verified)"** -- the PS's `VIO` is an internal 1.8 V LDO
  output, a different thing. Add: "comes up >= 6 ms after `+VBAT_LTE`
  (U8 EN gated by U40 PG)".
- **`RESET_MCU_N`**: add "No pull-up anywhere (Nordic: external pull-up not
  allowed). 1k series is on programming_debug; bypass cap at the pin on
  connectivity."
- **`I2C_SCL`/`I2C_SDA`**: done on power_bms.
- `docs/passives-reference.md` (coordinator): add the U8 and U40 passive sets from `regulation_notes.md` Sec 2 and Sec 6 (C300-C303, L300, R301-R312; C22 now DNP, L1 part changed).
- No new cross-sheet nets. Local nets only (`+3V3_REG`, `+VBAT_LTE_REG`,
  `EN_3V3`, `PG_3V3`, `FB_3V3`, `SW_3V3`, `EN_LTE`, `PG_LTE`, `FB_LTE`,
  `L1_LTE`, `L2_LTE`, `MODE_LTE`, `RST_MCU_DBG`, `DBG_VREF`).

## 5. For other sheet owners

- **connectivity (mcu):**
  - nRF9151 `VDD` on **`+VBAT_LTE`** with Nordic's VDD bank at the SiP
    (HDG *Schematic design* Table 1: 47 uF 0805, 10 uF 0603, 2x 4.7 uF,
    2x 1 uF, 0.1 uF, FB1 BLM18SD220SN1). `VDD_GPIO` on `+3V3` with its
    0.1 uF.
  - **Tie ENABLE to `+VBAT_LTE` through a series resistor + cap** (HDG
    *ENABLE*). If you want host control of ENABLE instead, tell me -- the
    `+3V3` delay is built on this assumption.
  - nRESET: bypass cap close to the pin, **no pull-up, no second 1k**
    (R313 on programming_debug is the series R).
  - `RESET_BLE_N` GPIO on the nRF9151: open-drain only.
  - BT840 firmware must set UICR.PSELRESET (P0.18) for SW11/J32 reset to work.
  - Rename your I2C labels to `I2C_SCL` / `I2C_SDA`; pull-ups R37-R39 stay
    on `+3V3`.
  - Route `SWDIO_MCU`/`SWDCLK_MCU`/`SWDIO_BLE`/`SWDCLK_BLE`/`DBG_UART_TX`/
    `DBG_UART_RX`/`BTN_USER` to the pins in your GPIO table.
- **testpoints (io):** rename the `+3V3_SYS` test pad to `+3V3`; add one on
  `+VBAT_LTE` if you want it on the TP sheet too (I placed TP401/TP407
  locally). **I used TP400-TP417** -- outside your TP100-TP399 block because
  the power block had no TP range; renumber if the coordinator prefers.
- **indicators (io):** MCP73871 status LEDs D4-D6 pull-up rail still open
  (`+3V3` vs `+VSYS`); either is fine for the budget (~1.3 mA each with 1k).
- **uwb / clock_dist:** send me the TCXO and fan-out buffer currents when
  chosen; they are the last estimate lines on `+3V3`.

## 6. Unverified items / risks

1. **U40 footprint placeholder** (DLA0010A HotRod land pattern partially
   estimated). Highest fab risk on these sheets.
2. **Nordic numbers come from HTML pages, not the PDFs** (Cloudflare).
   The figures used: VDD 3.0-5.5 V, VDD_GPIO 1.7-3.6 V, 3.2 V LTE
   recommendation, 505 mA max TX subframe, 41 mA LTE-M RX, nRESET 13k/2.2 V,
   VDD_GPIO 6 ms sequencing, <0.2 Ohm VDD impedance.
3. **Sequencing depends on connectivity tying ENABLE to `+VBAT_LTE`.**
4. **Estimated loads**: BT840 (~20 mA peak), nRF9151 VDD_GPIO (~10 mA design,
   100 mA ceiling), TCXO (~2 mA), fan-out buffer (~25 mA). LIS3MDL/LIS2DH
   values carried over from the previous notes, not re-read this pass.
   Headroom is >= 4x so none of these can flip the regulator choice.
5. **Low-battery behaviour**: UVLO trips at `+VSYS` 2.91 V, which under a
   ~1.2 A burst is a ~3.1-3.2 V cell. Fine for a Li-ion, but tune R308 when
   the cell/protection IC is chosen. C22 feedforward value unverified (DNP).
   nRF52840 reset-pin details not re-verified (PS blocked).

---

## Power budget

Sources: DW3000 Datasheet Version 1.1 (Decawave 2020) Table 5 (all
supplies 3.0 V, 25 C); nRF9151 HDG *LTE-M and NB-IoT TX current consumption
for Power Class 3* and *... RX*; nRF9151 HDG *VDD_GPIO*; nRF52840 Product
Brief v2.3. "est" = allowance, not a datasheet figure.

| Load | Rail | Typ | Peak | Source / note |
|---|---|---|---|---|
| 4x DW3210, RX CH5 | `+3V3` | 4 x 72 = 288 mA while listening | 288 mA | DW3000 DS v1.1 Table 5 "Peak current continuous Tx/Rx, RX CH5 72 mA". All four anchors listen at once for TDoA. IDLE CH5 = 18 mA each (72 mA total) between frames. |
| DW3210 TX CH5 (A0 only, TWR) | `+3V3` | -- | 54 mA (29 VDD2 + 25 VDD3, max power) | Table 5. Not additive with A0's RX; covered by the RX line. |
| BT840 (nRF52840), BLE TX +8 dBm | `+3V3` | ~5 mA est (connected, idle) | ~20 mA est | 16.40 mA radio at +8 dBm DC/DC 3 V (nRF52840 PB v2.3) + CPU allowance. Fanstel datasheet has no current table. |
| nRF9151 `VDD_GPIO` | `+3V3` | ~2 mA est | 10 mA design / 100 mA ceiling | HDG *VDD_GPIO*: "momentary concurrent current consumption of all GPIOs should not peak higher than approximately 100 mA". |
| LIS3MDL | `+3V3` | 0.27 mA | 0.27 mA | Carried from previous `regulation_notes.md` (not re-read). |
| LIS2DH | `+3V3` | 0.011 mA | 0.011 mA | As above. |
| 38.4 MHz TCXO | `+3V3` | ~2 mA est | ~2 mA est | Not selected. |
| 1:4 clock fan-out buffer | `+3V3` | ~25 mA est | ~25 mA est | Not selected. |
| LEDs on indicators.kicad_sch (five LED symbols, 1k series) | `+3V3` (rail TBD for D4-D6) | 0-6.5 mA | 6.5 mA | (3.3 - ~2.0 V)/1k = 1.3 mA each, five LEDs. |
| I2C pull-ups R37-R39 (2.2k) | `+3V3` | ~0 | 4.5 mA | Only while a line is low. |
| U8 PG pull-up R301 | `+3V3_REG` | 0.03 mA | 0.03 mA | 3.3 V / 100k. |
| **`+3V3` total** | | **~325 mA** (anchors listening) / ~110 mA (anchors idle) | **~356 mA; ~446 mA at the VDD_GPIO ceiling** | TPS62A02: 2 A -> >= 4.5x headroom. |
| nRF9151 `VDD`, LTE-M TX (PC3, 23 dBm) | `+VBAT_LTE` | -- | 435 mA (B1, 50 Ohm); **505 mA** (B1, 3.0 V, 85 C, VSWR 3:1) | HDG PC3 TX table, "average current consumption during TX subframe" (Nordic: = the nRF9160's "peak"). |
| nRF9151 `VDD`, NB-IoT TX | `+VBAT_LTE` | -- | 390 mA (B8, 50 Ohm); 455 mA (B65, VSWR 3:1) | Same page, Table 2. |
| nRF9151 `VDD`, LTE-M RX | `+VBAT_LTE` | 41 mA | 41 mA | HDG RX table (3.7 V, 25 C, -90 dBm). NB-IoT 35 mA. |
| nRF9151 GNSS / PSM / app core | `+VBAT_LTE` | not read | -- | GNSS-only and PSM figures not fetched this pass; both well under TX. |
| U40 EN divider | `+VSYS` | 0.012 mA | 0.012 mA | 3.5 V / 291k. |
| **`+VBAT_LTE` total** | | 41 mA RX | **505 mA** | TPS63802: 2 A (VI >= 2.3 V) -> ~4x. |
| **`+VSYS` (both converters, eta 0.9)** | | ~0.3 A at 5 V | 0.75 A at 5 V; **1.2 A at 3.0 V battery** | (0.446 x 3.318 + 0.505 x 3.588) / 0.9 = 3.65 W. MCP73871 SEL-high input limit 1.8 A covers 0.75 A + 0.5 A charge on wall power; on battery the cell + Q1 (4 A) supply it. |

## Bring-up tests

Equipment: bench supply with current limit, DMM, scope (>= 100 MHz, short
ground spring), Nordic PPK2, J-Link (or nRF DK as debugger), 3.3 V USB-UART.

**0. Before power.** Fit nothing on J30/J31. Confirm R300, R302 fitted;
R305, R310, R312, R314, C22, C302 not fitted. Ohm-check `+3V3`,
`+VBAT_LTE`, `+VSYS`, `+5V_IN` to GND (no shorts; expect kOhm-range on the
regulator side from the FB dividers).

**1. Regulators unloaded.** Remove R300 and R302 (both loads disconnected).
Bench supply 5.0 V / 200 mA limit into the barrel jack (no cell).
- TP406 `+VBAT_LTE_REG` = 3.55-3.62 V; TP410 `FB_LTE` = 0.495-0.505 V;
  TP409 `PG_LTE` high; TP408 `EN_LTE` ~1.72 V; TP413 MODE = 0 V.
- TP400 `+3V3_REG` = 3.28-3.35 V; TP403 = 0.594-0.606 V; TP405 PG high.
- Input current with no load: a few mA at most (both converters in PSM).

**2. Power-up sequencing.** Scope CH1 TP406 (`+VBAT_LTE_REG`), CH2 TP409
(`PG_LTE`), CH3 TP404 (`EN_3V3`), CH4 TP400 (`+3V3_REG`); trigger on CH1,
switch the 5 V supply on.
- Pass: `+3V3_REG` starts rising **>= 6 ms** after `+VBAT_LTE_REG` reaches
  regulation (expect ~12-41 ms: EN_3V3 RC ramp from PG release, then 1 ms
  soft start). No overshoot above 3.6 V on either rail.
- Power-down: switch off; `+3V3_REG` must fall before `+VBAT_LTE_REG`
  (PG_LTE pulls EN_3V3 low).

**3. UVLO.** Battery input instead (bench supply on BT1 pads, 4.0 V, 1.5 A
limit, no 5 V). Ramp down slowly: both rails turn off at `+VSYS` (TP on
testpoints sheet) = 2.82-3.00 V. Ramp up: on at 3.11-3.29 V. Record the
cell-side voltage (TP417 `BATT_RAW`) at each event.

**4. Loaded rails.** Refit R300/R302. On 5 V input, then on 3.6 V battery:
- DC: TP401 `+3V3` and TP407 `+VBAT_LTE` within the step-1 limits.
- Ripple (20 MHz BW limit off, short ground spring at the output cap):
  `+3V3` with anchors in RX; `+VBAT_LTE` during an LTE attach. Record
  pk-pk in PSM. If `+VBAT_LTE` PSM ripple disturbs LTE/GNSS, swap R311 ->
  R312 (forced PWM) and repeat. If `+3V3` PSM ripple is high, fit C22 and
  tune.
- `+VBAT_LTE` droop during TX bursts at 3.3 V battery: TP406/TP407 must
  stay >= 3.2 V (Nordic recommendation) -- scope, AC-coupled, single-shot
  on the burst.

**5. PPK2 current profiles.** Remove one link, PPK2 ampere-meter mode, VIN
to J30/J31 pin 1, VOUT to pin 2.
- **`+3V3` (J30):** boot; all anchors IDLE (expect ~110 mA); all four in
  continuous RX (~325 mA); A0 TWR exchange (TX bursts on top); BLE
  advertising/connected (BT840 adds a few mA). Peak must stay < 0.5 A.
- **`+VBAT_LTE` (J31):** modem off; LTE-M attach; TX at max power
  (expect ~400-500 mA subframes); PSM floor (uA range); GNSS fix with LTE
  idle. Compare TX current against the HDG PC3 table for the band used.
- Refit the 0R after each measurement.

**6. Charger / THERM.** With a cell fitted and 5 V applied: TP416 `THERM`
~0.5 V at 25 C (10k NTC x 50 uA). Cool the NTC (freeze spray) until
charging stops (STAT LEDs / charge current); THERM should read 1.20-1.26 V
and the NTC 22.6-26.8k -- i.e. somewhere between +1 and +5 C.

**7. Debug.** J3: J-Link connects to the nRF9151 (allow 100-500 ms after
power for SWD, HDG ENABLE). SW2 resets it; with a scope on `RESET_MCU_N`
(at the SiP) confirm the low level < 0.66 V and nothing ever drives it
above 2.2 V. J32: connects to the BT840; SW11 resets it once PSELRESET is
set. J33: nRF9151 log output at 3.3 V logic with J33 pin 4 floating.
