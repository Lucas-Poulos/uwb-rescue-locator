# Handoff: uwb agent (uwb_array + clock_dist)

Branch `worktree-agent-a380306122f5a7a70` (from `redesign/nrf9151-host`,
`docs/net-contract.md` merged in). Detail lives in
`bay-station/uwb_array_notes.md` and `bay-station/clock_dist_notes.md`; this
file is what the coordinator needs to merge.

## 1. Summary

**uwb_array.kicad_sch** (A4 -> A2, four identical anchor blocks):
- U4-U7 fully wired, every one of the 40 pins, against the contract nets.
  U4 is labelled **A0 CENTER (TWR -> range)** in a caption, a `Role` field and
  its Description; U5-U7 are labelled A1-A3 OUTER (TDoA).
- Per-anchor 0R links: +3V3 (R200-R203, current break -> `+3V3_An`), CS
  (R204-R207), IRQ (R208-R211), RSTn to the shared `UWB_RST_N` (R212-R215).
  SYNC through **DNP** 0R (R216-R219). WAKEUP shared, 100k pull-down R224.
- Existing parts wired, not changed: R10-R17 are GPIO5/6 10k **pull-downs =
  SPI mode 0** (DS v1.1 Table 20); R25-R28 IRQ pull-downs; C40-C74, FB1-FB4,
  R33-R36 as placed from Fig 32. Each decoupling cap gained a `Placement`
  field naming its pin.
- RF per anchor: RF1 -> 2.0pF (existing C47/55/63/71) -> DNP shunt
  (C200/202/204/206) -> 0R series (R220-R223) -> DNP shunt (C201/203/205/207)
  -> SMA J20-J23 (Linx/TE CONSMA020.042-G). RF parts 0402 (in-track pads).
- XTI <- `UWB_CLKn`. XTO 1pF C28-C31 **moved here from clock_dist** (same refs).
- A0-only DNP fallback crystal Y1 (TXC 8Y38472012) + C208/C209.
- Test pads TP500-TP527 (+3V3_An, EXTON, GPIO0-4 per anchor). PWR_FLAGs on
  the local rails.
- DW3210 symbol: SPIMISO pin type `output` -> `tri_state` (DS Table 19 t6),
  in both the embedded copy and `libs/bay_station.kicad_sym`.

**clock_dist.kicad_sch** (A4 -> A3): PROPOSED U30 Rakon RPT1490LN TCXO ->
R230 22R -> `TCXO_OUT` -> PROPOSED U31 TI LMK1C1104PWR -> R231-R234 22R ->
existing C24-C27 2200pF -> `UWB_CLK0..3`. Own rails `+3V3_TCXO` (R225 0R)
and `+3V3_CLKBUF` (R226 0R), 0603 pads take a bead; decoupling C210-C214;
Vc divider R227/R228 + C215; 1G pull-up R229; TP528-TP530.

**Library:** new symbols `bay_station:LMK1C1104PW`, `bay_station:RPT1490LN`;
new footprints `Rakon_RPT1490LN_14.5x9.5mm_PLACEHOLDER`,
`SMA_Linx_CONSMA020.042-G_EdgeMount_PLACEHOLDER`.

**ERC** (kicad-cli 10.0.5, whole project):
- Before: **596** total; UWB Array 370, Clock Distribution 16.
- After: **220** total; my two sheets **10**: 2 `pin_not_driven` (UWB_SCK and
  UWB_MOSI have no driver until connectivity wires the nRF9151) and 8
  `isolated_pin_label` (UWB_CS0..3_N / UWB_IRQ0..3 waiting on connectivity /
  testpoints). Clock sheet 0.
- Component count: 145 -> 234 in the exported netlist (no silent drop);
  netlist spot-checked net by net for U4/U7, the clock tree, UWB_* shared nets.

## 2. components.csv

Change (replace the existing rows of the same role):

```csv
"Shared reference oscillator (clock_dist.kicad_sch, U30)",Rakon RPT1490LN 38.4MHz -- PROPOSED (ordering code TBC; distributor lists E8246LF),bay_station:RPT1490LN (hand-authored),bay_station:Rakon_RPT1490LN_14.5x9.5mm_PLACEHOLDER (hand-authored PLACEHOLDER),https://www.rakon.com/hubfs/Files/Product%20datasheets/TCXO/TCXO%20RPT1490LN.pdf,"PROPOSED. Verified against Rakon datasheet Issue B (21 Oct 2024): 38.4MHz listed as standard frequency; CMOS out (VOL<=0.4V VOH>=2.7V); 3.3V +-5%, 10mA typ; duty 49-51%; typ phase noise at 38.4MHz from the page-2 plot markers -151.3 dBc/Hz @1kHz and -165.7 @10kHz vs DW3000 DS Table 10 limits -132/-145 (typical, not guaranteed). Pins 1 Vc, 2/3 GND, 4 RF out, 5 DNC, 6 Vcc. Vc biased to 1.49V (reference 1.5V). RISKS: 14.5x9.5x6mm, likely costly, availability not confirmed (quote-only?). Qorvo-listed TCXOs were rejected: TXC 7Z series sheet gives -130 dBc/Hz @1kHz, 2dB outside Table 10, and clipped-sine output. Footprint row spacing (7.9mm) read as centre-to-centre -- verify."
"Clock fan-out buffer (clock_dist.kicad_sch, U31)",TI LMK1C1104PWR -- PROPOSED,bay_station:LMK1C1104PW (hand-authored),Package_SO:TSSOP-8_4.4x3mm_P0.65mm (KiCad default),https://www.ti.com/lit/ds/symlink/lmk1c1104.pdf,"PROPOSED. Verified against TI SNAS791D (rev Feb 2022): 1:4 LVCMOS, PW pinout 1 CLKIN 2 1G 3 Y0 4 GND 5 Y2 6 VDD 7 Y3 8 Y1 (Fig 6-4/Table 6-1); at 3.3V output-output skew 25ps typ/50ps max, ODC 45-55%, ROUT 50 ohm, additive jitter 8fs typ; LMK1C1104PWR Active in orderable addendum. Run at 3.3V: Fig 10-3 shows no measurable close-in phase-noise degradation (1.8V shows a hump). XTI amplitude >=2.6Vpp, near the top of DW3000's 0.8V..VDD2 window."
"Clock AC-coupling caps (clock_dist.kicad_sch, C24-C27)",Generic 2200pF 0603 ceramic (C0G preferred),Device:C (KiCad default),Capacitor_SMD:C_0603_1608Metric (KiCad default),n/a (generic passive),"Value is datasheet-specified: DW3000 Datasheet Table 10 'Must be AC coupled. A coupling capacitor value of 2200 pF is recommended.' One per anchor, between the buffer's 22R series termination and UWB_CLKn. Place at the DW3210 XTI pin."
"XTO ground caps (uwb_array.kicad_sch, C28-C31 -- moved from clock_dist)",Generic 1pF 0402 C0G,Device:C (KiCad default),Capacitor_SMD:C_0402_1005Metric (KiCad default),n/a (generic passive),"DW3000 Datasheet v1.3 XTO row 'Requires 1pF to the ground, only if external clock is used' (v1.3 not re-read in the 2026-11-17 pass -- Qorvo download rate-limited; v1.1 omits the note). Moved to uwb_array so the cap sits at pin 22. 0402 because it is a 1pF RF-adjacent part."
"UWB antenna connectors (uwb_array.kicad_sch, J20-J23)",Linx (TE) CONSMA020.042-G -- PROPOSED,Connector:Conn_Coaxial (KiCad default),bay_station:SMA_Linx_CONSMA020.042-G_EdgeMount_PLACEHOLDER (hand-authored PLACEHOLDER),https://www.te.com/usa-en/product-CONSMA020.042-G.html,"PROPOSED. Verified against Linx datasheet DS21264: SMA jack, PCB edge mount for 0.042in boards (this board 1.048mm), 0-18GHz, 50 ohm; Table 3 5-7.125GHz band IL 0.23dB max, VSWR 1.1 max (covers CH5 6489.6MHz). Footprint from DS21264 Fig 2 (top 3 pads at 4.24mm, bottom 2 GND pads 8.48mm apart, 1.52x5.08mm). Centre pad 1.52mm is far wider than the 50 ohm line: launch taper/ground cut-back needs EM simulation. Also the conducted-test port."
"DW3210 RF1 series DC block (uwb_array.kicad_sch, C47/C55/C63/C71)",2.0pF C0G/NP0 ceramic 0402,Device:C (KiCad default),Capacitor_SMD:C_0402_1005Metric (KiCad default),"n/a (generic passive -- value is simulation-derived, see Notes)","Series on RF1 (pin 18). Qorvo: 'C2 and C3 are not only a DC blocking capacitor, these capacitors are a part of the RF transmission line ... value was chosen as the result of the simulation.' Do not substitute. Pads embedded in the 50 ohm track at track width (DS s7.3). Source: DW3000 Datasheet v1.1 Figure 32 (rendered image). Footprint now assigned."
"DW3210 RF2 termination (uwb_array.kicad_sch, R33-R36)",49.9 ohm 1% 0402,Device:R (KiCad default),Resistor_SMD:R_0402_1005Metric (KiCad default),n/a (generic passive),"RF2 (pin 13) unused on the non-PDoA DW3210: DS v1.1 Table 2 'should be grounded with 50 ohm. A 50 ohm PCB trace from the RF2 port to the termination resistor is also required'. Fig 32 DW3110 inset R1 = 49R9. Footprint now assigned."
```

Add:

```csv
"UWB pi-match series links (uwb_array.kicad_sch, R220-R223)",0R 0402,Device:R (KiCad default),Resistor_SMD:R_0402_1005Metric (KiCad default),n/a (generic passive),"Series element of the per-anchor pi-match between the 2pF and the SMA. 0402 so the pads can be embedded in the 50 ohm track (DS v1.1 s7.3). Fitted 0R until VNA tuning."
"UWB pi-match shunts (uwb_array.kicad_sch, C200-C207)",DNP 0402 footprint,Device:C (KiCad default),Capacitor_SMD:C_0402_1005Metric (KiCad default),n/a (DNP),"Two shunt pads per anchor (chip side, connector side). DNP; tune after measurement. The connector-side pad is also the landing for an 0402 RF ESD diode if needed -- Qorvo Fig 32 shows no ESD part and none is chosen."
"Per-anchor rework links (uwb_array.kicad_sch, R200-R215)",0R 0603,Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive),"R200-R203 +3V3 -> +3V3_An (current-measure break / isolate an anchor); R204-R207 CS; R208-R211 IRQ; R212-R215 RSTn -> shared UWB_RST_N."
"UWB SYNC links (uwb_array.kicad_sch, R216-R219)",DNP 0R 0603,Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (DNP),"GPIO7/SYNC -> UWB_SYNC, not fitted: OSTR need is unresolved (DW3000 User Manual not obtained). Unfitted the pin is held low by its internal pull-down (DS v1.1 Table 2)."
"UWB_WAKEUP pull-down (uwb_array.kicad_sch, R224)",100k 0603,Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive),"WAKEUP is active high and 'should be connected to ground if not used' (DS v1.1 Table 2); keeps all four low while the host pin is Hi-Z."
"A0 fallback crystal (uwb_array.kicad_sch, Y1) -- DNP",TXC 8Y38472012 38.4MHz,Device:Crystal_GND24 (KiCad default),Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm (KiCad default),https://www.txccorp.com,"DNP. Crystal shown in DW3000 DS v1.1 Figure 32 (X1) and listed in Table 22. Lets A0 range on its own crystal if the shared clock misbehaves (remove C24 and C28, fit Y1/C208/C209). TXC's own datasheet for this PN NOT pulled -- verify package/pinout before fitting."
"A0 fallback crystal load caps (uwb_array.kicad_sch, C208-C209) -- DNP",3.3pF C0G 0402 (DNP),Device:C (KiCad default),Capacitor_SMD:C_0402_1005Metric (KiCad default),n/a (DNP),"Fig 32 C100/C101 = 3.3pF; trim for actual crystal and layout."
"Clock-tree supply links (clock_dist.kicad_sch, R225-R226)",0R 0603 (pads accept an 0603 ferrite bead),Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive),"+3V3 -> +3V3_TCXO and +3V3 -> +3V3_CLKBUF. 0R/bead option and current-measure point. TI SNAS791D s11 recommends (not requires) a low-DCR bead for the buffer; no bead PN chosen."
"Clock-tree decoupling (clock_dist.kicad_sch, C210-C215)","10uF, 100nF, 10uF, 1uF, 100nF, 100nF ceramic 0603",Device:C (KiCad default),Capacitor_SMD:C_0603_1608Metric (KiCad default),n/a (generic passive),"C210/C211 TCXO; C212 board-side 10uF, C213 1uF, C214 0.1uF at buffer VDD per TI SNAS791D Fig 11-1; C215 TCXO Vc filter."
"Clock-tree resistors (clock_dist.kicad_sch, R227-R234)","10k, 8.2k, 10k, 22R x5",Device:R (KiCad default),Resistor_SMD:R_0603_1608Metric (KiCad default),n/a (generic passive),"R227/R228 TCXO Vc divider -> 1.49V (Rakon tuning reference 1.5V); R229 buffer 1G pull-up (outputs always enabled); R230 TCXO->buffer and R231-R234 Yn series source terminations, 22R starting value, tune at bring-up; R231-R234 must stay equal."
"UWB/clock test pads (TP500-TP530)",Test pad,Connector:TestPoint (KiCad default),TestPoint:TestPoint_Pad_D1.0mm (KiCad default),n/a,"Local nets only: per anchor +3V3_An, EXTON, GPIO0-4 (TP500-TP527); +3V3_TCXO, +3V3_CLKBUF, TCXO_VC (TP528-TP530). Refs are outside the agent block table -- renumber if preferred."
```

Unchanged but note: FB1-FB4 (BLM03PG330SN1D) still have no footprint; the
csv's "0402 (per Murata BLM03 series)" conflicts with Murata's naming (BLM03 =
0201 imperial). Needs a Murata PDF read.

## 3. decisions.md

Move to Resolved (PROPOSED, pending availability):

```markdown
- **TCXO + 1:4 buffer: Rakon RPT1490LN (38.4MHz, CMOS) + TI LMK1C1104PWR,
  PROPOSED 2026-11-17.** Checked against DW3000 DS Table 10 from both PDFs:
  RPT1490LN typ -151 dBc/Hz @1kHz / -166 @10kHz (Rakon Issue B plot), duty
  49-51%; LMK1C1104 skew 50ps max, ODC 45-55%, no measurable close-in
  degradation at 3.3V (SNAS791D Fig 10-3). The Qorvo-listed TCXO (TXC 7Z,
  DS Table 22) was rejected: TXC's own sheet gives -130 dBc/Hz @1kHz, outside
  Table 10, and its clipped-sine output does not meet an LVCMOS buffer input.
  Open risk: the Rakon part looks quote-only and is 14.5x9.5x6mm. TCXO_EN
  omitted (no enable pin; stopping the clock stalls all four cores).
- **UWB SMA: Linx/TE CONSMA020.042-G edge-mount, PROPOSED.** 0-18GHz, rated
  IL 0.23dB / VSWR 1.1 over 5-7.125GHz (DS21264 Table 3), sized for 0.042in
  boards (this one is 1.048mm). Footprint PLACEHOLDER; launch needs EM sim.
- **DW3210 SPI mode: mode 0.** R10-R17 are pull-downs on GPIO5/SPIPOL and
  GPIO6/SPIPHA (DS v1.1 Table 20); firmware must use CPOL=0/CPHA=0.
```

Update Open:

```markdown
- **Is SYNC/OSTR needed at all?** Still open -- the DW3000 User Manual was
  not obtainable on 2026-11-17 (Qorvo rate-limited). Hardware hedge: UWB_SYNC
  is routed to every anchor through DNP 0R R216-R219; fit only after reading
  the OSTR section.
- **DW3210 exposed pad net.** QFN footprint has an EP, symbol has 40 pins, DS
  v1.1 Table 2 does not name the EP. Resolve from Fig 38 / Qorvo layout before
  layout (expected GND, unverified).
- **Shared RSTn contention.** Four O-H RSTn pins tied (via 0R) to one net;
  check on first boards that a chip still in POR does not fight the others.
- **XTI drive amplitude** with a 3.3V buffer is >=2.6Vpp, near the top of
  0.8V..VDD2. Bench test at 2.5V buffer supply (via TP529) before deciding
  whether a 2.5V LDO is needed.
```

## 4. net-contract.md changes

- None required. `TCXO_EN` is **unused** (contract allows omission) --
  please mark it "omitted: RPT1490LN has no enable".
- Rail used: `+3V3` (global label) for all four anchors and the clock tree.

## 5. For other owners

- **connectivity:** SPI bus runs in **mode 0**; the DW3000 allows 36 MHz
  (20 MHz with CRC). Please confirm the nRF9151 SPIM max rate (I believe the
  nRF91 SPIM is 8 Mbps but did not verify) and record it -- positioning.md's
  "SPIM3 at 32 MHz" was nRF52840-specific. Drive `UWB_RST_N` **open-drain
  only** (no push-pull high: DS Table 2). `UWB_WAKEUP` has a 100k pull-down
  here. `UWB_IRQn` are active-high with 100k pull-downs. Make `UWB_SYNC` a
  GPIO even though it is DNP-linked. No `TCXO_EN` pin needed.
- **testpoints (io):** existing TP5 = `TCXO_OUT`, TP6-TP9 = `UWB_CLK0..3`
  (XTI side of the AC caps), TP10-12 = UWB_SCK/MOSI/MISO, TP14 =
  `UWB_RST_N`, TP13/19-21 = `UWB_IRQ0..3`, TP15-18 = `UWB_CS0..3_N`. Also
  wanted: `UWB_WAKEUP`, `UWB_SYNC`. I used TP500-TP530 for local pads on my
  sheets (outside every block) -- renumber at merge if desired.
- **regulation/power:** the array + clock tree load on `+3V3`: four DW3210
  (DS Table 5: 18 mA IDLE CH5 each, TX/RX peaks higher) + TCXO 15 mA max +
  LMK1C1104 ~33 mA typ at 100 MHz (less at 38.4 MHz). Replaces the old
  ~2 mA TCXO / ~25 mA buffer estimates.
- **layout (later):** four RF paths and four UWB_CLK traces must be matched;
  see uwb_array_notes.md "Length matching".

## 6. Unverified items / risks

1. **Rakon RPT1490LN availability/cost** -- no catalogue ordering code
   found; may be quote-only. Phase-noise margin is from typical plot data.
2. **DW3000 v1.3 datasheet and User Manual not read this pass** (Qorvo
   HTTP 429). XTO 1pF is a v1.3 fact carried from positioning.md; SYNC
   decision is a hedge, not a resolution.
3. **DW3210 exposed pad** unassigned in the symbol.
4. **SMA launch at 6.5 GHz** -- footprint PLACEHOLDER, 1.52 mm centre pad
   needs EM-designed transition; connector rated for 1.07 mm vs 1.048 mm board.
5. **Shared RSTn** contention and **XTI amplitude near VDD2** -- both bench
   checks on first boards.
6. Minor: FB1-FB4 footprint blank (BLM03 case size); TXC 8Y38472012 (DNP)
   datasheet not pulled; LMK1C1104 phase noise only characterised at
   156.25 MHz; TP numbering outside the block table.

Datasheets used (scratchpad `datasheets/`): DW3000 DS v1.1 (local copy from
~/Downloads), TI SNAS791D, TI SNAS579G (LMK00105, alternative), Rakon
RPT1490LN Issue B, TXC 7Z series sheet, Raltron RTX-2520AF31-S-38.400,
Abracon ASTX-H11, ECS-TXO-2016, Linx DS21264, Samtec SMA-J-P-X-ST-EM1 print.
