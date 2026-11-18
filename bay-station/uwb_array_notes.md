# uwb_array.kicad_sch -- notes

Four Qorvo DW3210 (QFN40, non-PDoA) on one board, one shared clock, four
remote antennas on coax. **U4 = A0 is the CENTER anchor** (two-way ranging
with the tag, gives range). **U5-U7 = A1-A3 are the OUTER anchors** (TDoA
against A0 on the same tag frame, gives direction). Index `n` means anchor
`An` everywhere: `UWB_CSn_N`, `UWB_IRQn`, `UWB_CLKn`, `J2n`, `+3V3_An`.

Sources, all read from the PDF this pass unless stated:

- **DS v1.1** = Decawave/Qorvo *DW3000 Datasheet* Version 1.1 (2020), local
  copy. Pin table read with `pdftotext -raw` (Table 2); numeric tables with
  `-layout`; Figure 32 read by rendering page 43.
- **v1.3** of the same datasheet is what `docs/positioning.md` cites. It
  could not be re-downloaded this session (qorvo.com returned HTTP 429), so
  the one v1.3-only fact used here -- XTO "Requires 1pF to the ground, only
  if external clock is used" -- is carried over from positioning.md, not
  re-verified. v1.1's XTO row just says "Reference crystal output."
- The **DW3000 User Manual** was not obtained (Qorvo download rate-limited;
  no manufacturer mirror found). It is the source for SYNC/OSTR.

Sheet is now A2 so the four anchor blocks sit side by side and are drawn
identically.

## Pin-by-pin

| Pin | Name | Connection | Why / source |
|---|---|---|---|
| 1 | IRQ | 100k to GND (R25-R28) + 0R (R208-R211) -> `UWB_IRQn` | DS v1.1 Table 2: floats in SLEEP/DEEPSLEEP, "100kΩ recommended" pull-down. Active high by default. |
| 2 | GPIO6/SPIPHA | 10k to GND (R11/13/15/17) | SPI mode strap, see below |
| 5 | GPIO5/SPIPOL | 10k to GND (R10/12/14/16) | SPI mode strap |
| 3,4,6,7,8 | GPIO0-4 | test pads | Spare; configurable as RXOK/SFD/RX/TX/EXTPA strobes. DS Table 2 note 2: not for driving LEDs. Default input with internal pull-down (s4.9.5), so no external termination needed. |
| 9 | GPIO7/SYNC | DNP 0R (R216-R219) -> `UWB_SYNC` | See SYNC below. "This pin is internally pulled down." |
| 13 | RF2 | 49R9 to GND (R33-R36) | Non-PDoA: "should be grounded with 50 Ω. A 50 Ω PCB trace ... is also required" (Table 2; Fig 32 DW3110 inset R1 49R9). |
| 18 | RF1 | RF chain, below | "50 Ω single ended ... A 2pF is required on the pin." |
| 21 | XTI | `UWB_CLKn` (2200pF AC cap on clock_dist) | Table 10 external reference; "external reference overdrive pin" (Table 2). |
| 22 | XTO | 1pF to GND (C28-C31) | v1.3 pin table (see above). Moved from clock_dist to this sheet so it sits at the pin. |
| 23/26/29 | VDD2b / VDD3 / VDD1 | `+3V3_An` | 3.3V is inside all three ranges (Table 4). |
| 28 | VDD2a | FB1-FB4 from `+3V3_An` | "F-15 requires isolation with a ferrite from B-15" (Table 2); Fig 32 FB1 = BLM03PG330SN1D. |
| 27 | VTX_D | 220nF to GND (C45/53/61/69) | Decoupling only (Fig 32 C9). |
| 38 | VIO_D | 100nF to GND (C46/54/62/70) | Decoupling only (Fig 32 C21). |
| 31 | EXTON | test pad | Output; nothing on this board needs it. |
| 32 | WAKEUP | shared `UWB_WAKEUP`, 100k pull-down R224 | Active high; "should be connected to ground if not used". Pull-down keeps it low while the host pin is Hi-Z. |
| 33 | RSTn | 0R (R212-R215) -> shared `UWB_RST_N` | "May be pulled low by external open drain driver ... Must not be pulled high by external source." No pull-up anywhere. |
| 34-36 | SPICLK/MOSI/MISO | shared `UWB_SCK/MOSI/MISO` | |
| 37 | SPICSn | 0R (R204-R207) -> `UWB_CSn_N` | Internal pull-up (s4.9.5): an opened link leaves the anchor deselected. |
| 10-12,14-17,19,20,24,25,30,39,40 | GND/VSS* | GND | |

Symbol change: **SPIMISO retyped `output` -> `tri_state`** in both the
embedded and library DW3210. Four push-pull outputs on one net is an ERC
error, and it is also wrong: Table 19 t6 is "SPICSn deasserted high to CDO
tristate".

## SPI mode (R10-R17)

DS v1.1 s4.9.3 / Table 20: GPIO5 = SPIPOL, GPIO6 = SPIPHA, sampled at power-up
(Fig 21 "Sample GPIOs 5&6 to set SPI mode"). 0/0 = mode 0. The pins are
"internally pulled low to configure a default SPI mode 0"; any other mode
needs a pull-up of at most 10k to VIO_D. R10-R17 are 10k **pull-downs**, so
they select **mode 0** and only make it deterministic.

**Firmware must run the anchor bus in SPI mode 0 (CPOL=0, CPHA=0).** Limit:
36 MHz in mode 0, 20 MHz in CRC mode (Table 19). The host is the limit
instead: every nRF9151 SPIM instance caps at 8 MHz (`connectivity_notes.md`
section 2, from the nrfx MDK).

## Power

"Lowest BOM" scheme of Fig 32: VDD1, VDD2 and VDD3 all from one 3.3V supply.
Per anchor: `+3V3` -> **R200-R203 0R** -> `+3V3_An`. That 0R is the
current-measure break point and the way to isolate a dead anchor. Decoupling
values are the ones already placed from Fig 32; each cap now has a
`Placement` field naming its pin, because VDD1, VDD2b and VDD3 share a net
here and the schematic cannot show that on its own. C72-C74 (Fig 32
C6/C7/C8) are the shared bank at the array entry.

DS v1.1 s6: VDD2a/b and VDD3 must be stable within 10 ms of VDD1. On one
rail this is automatic.

## RF front end (per anchor, identical)

```
RF1 --[C47 2.0pF]--+--[R220 0R]--+-- J20 SMA
                 C200 DNP      C201 DNP
                   |             |
                  GND           GND
```

- **Single-ended 50 Ω, no balun** (Table 2). No filter: the Fig 32 note says a
  BPF "may be required for certification in some regions that mandate
  conducted testing", which does not apply to this prototype; the pi pads
  can host one later.
- The 2.0pF is part of Qorvo's simulated line ("C2 and C3 are not only a DC
  blocking capacitor ... this capacitance value was chosen as the result of
  the simulation"). Do not change it.
- **ESD:** Qorvo shows none. The connector-side shunt (C201/203/205/207) is
  the landing pad for an 0402 RF ESD diode if one proves necessary. No part
  chosen.
- **0402 on the RF path**, not the repo's 0603: an 0402 pad is close to the
  ~0.45 mm 50 Ω track width on this stackup, so it can be "embedded into the
  track (have the same width)" as s7.3 requires. Exact track width comes from
  the stackup calculator at layout.
- **SMA:** Linx (TE) **CONSMA020.042-G**, PCB edge-mount SMA jack for 0.042 in
  (1.07 mm) boards; this board is 1.048 mm (Fig 35 stackup). Linx datasheet
  DS21264: 0-18 GHz; Table 3, 5-7.125 GHz band: insertion loss 0.23 dB max,
  VSWR 1.1 max -- that band contains CH5 (6489.6 MHz). Footprint
  `SMA_Linx_CONSMA020.042-G_EdgeMount_PLACEHOLDER` from DS21264 Fig 2; the
  centre pad is drawn 1.52 mm wide as the figure shows, which is far wider
  than the 50 Ω line and needs a tapered launch / ground cut-back sized by EM
  simulation at 6.5 GHz. PROPOSED.
- **Conducted test:** the SMA is the conducted port. A u.FL/MMCX tap is not
  allowed on this path (rated to 6 GHz).

### Length matching -- precision-critical

At the 1 m baseline, **1 cm of differential path is ~10 cm of position error
at 10 m** (positioning.md). For layout:

1. RF1 -> SMA: same geometry, same length, same via count, same component
   orientation on all four. Fixed mismatch calibrates out, but only if it is
   stable; small and identical is the goal.
2. `UWB_CLK0..3` buffer -> XTI: equal length (clock_dist_notes.md).
3. Coax + antenna assemblies: a matched, captive set.

Stackup and keep-outs: s7.3 (50 Ω lines, ground removed under the chip on
F.Cu and In1.Cu, first solid ground on In2.Cu).

## SYNC / OSTR

The user manual, which documents one-shot timebase reset, was not available.
With a genuinely shared clock the timebases do not drift; what OSTR would add
is a common *zero*, which the array calibration also absorbs (per-anchor
offsets are measured anyway). So: route `UWB_SYNC` (contract), but fit
nothing. R216-R219 are **DNP 0R**; unfitted, GPIO7/SYNC sits low on its
internal pull-down. Fit them only after reading the user manual's OSTR
section, and only on the anchors that need it.

## A0 fallback crystal (DNP)

Y1 (TXC 8Y38472012, the crystal in Fig 32 and DS Table 22) with C208/C209
(Fig 32: 3.3 pF) sits across A0's XTI/XTO. To use it: remove C24 (the AC cap
from the buffer) and C28 (the XTO 1pF), fit Y1, C208, C209. A0 then ranges on
its own crystal and can trim it (Table 10, ±20 ppm trim). TWR range still
works; **TDoA does not** (A0 no longer shares a timebase). It exists so range
bring-up is not blocked if the shared clock misbehaves. A0 only: an outer
anchor on its own crystal has nothing to offer. Cost: one 2016 footprint and
two 0402 pads as stubs on A0's XTI/XTO; keep them tight to the pins.

## Test pads and rework

TP500-TP527: per anchor `+3V3_An`, EXTON, GPIO0-GPIO4. These refs are
outside the agent block table in the brief (io owns TP100-TP399; no TP block
was given to uwb) -- renumber at merge if wanted. Contract nets
(CS/IRQ/SPI/RST/CLK) get their pads on testpoints.kicad_sch (io).

## Open / not verified

- **DW3210 has no exposed pad** (DW3000 DS v1.1 Fig. 38, Table 2; resolved
  2026-11-18, `docs/decisions.md`). The footprint is now the 40-pad no-EP
  `Qorvo_DW3210_QFN-40_5x5mm_P0.4mm_NoEP_PLACEHOLDER`. At layout, follow Fig. 35:
  no copper under the body on Top and Inner Layer 1, first solid ground on Inner
  Layer 2. The terminal land length is still unverified.
- **Shared RSTn contention.** RSTn is "O-H" (driven high after reset) on
  every chip and they are tied together. If one chip is still in POR (holding
  RSTn low) while another drives it high, they fight. On one rail they should
  come up together; the 0R links let one be isolated. Check on the first
  board; if it is a problem, give each anchor its own reset GPIO.
- **FB1-FB4 footprint left blank.** Murata's BLM03 prefix is the 0201 (0603
  metric) size by Murata naming; components.csv says 0402. Not resolved from
  a Murata PDF this pass (the Murata site returned an empty page).
- **XTO 1pF** is a v1.3 fact not re-read this pass (see top).
- **XTI amplitude** sits near the top of the 0.8 V..VDD2 window with the
  buffer at 3.3 V -- see clock_dist_notes.md.

## Bring-up tests for this sheet

1. **Rails:** `+3V3_An` at TP500/TP507/TP514/TP521. Idle current per anchor
   by lifting R200-R203 (DS Table 5: ~18 mA IDLE on CH5).
2. **Clock first:** 38.4 MHz present at every XTI (testpoints TP6-TP9)
   before expecting SPI -- "the DW3000 digital core will be held in reset
   until the crystal oscillator is stable" (s6). No clock = no DEV_ID.
3. **SPI DEV_ID per anchor:** one CS at a time, mode 0, start at 2 MHz and
   step up to the host maximum. A wrong mode shows as the same shifted value
   on all four.
4. **IRQ/RST:** with all chips idle each `UWB_IRQn` sits low (R25-R28);
   pulse `UWB_RST_N` and confirm all four re-enumerate. Repeat with each
   R212-R215 open to prove per-anchor isolation.
5. **Conducted TX power:** continuous-frame TX test mode on each anchor in
   turn into a spectrum analyser at its SMA. All four within ~1 dB; a
   lagging one points at its pi network or SMA launch.
6. **Loopback:** An TX -> 30-40 dB attenuator -> Am RX by cable, for each
   pair. Confirms every RX path and gives a first RX power comparison.
7. **Inter-anchor timestamp skew:** one tag at a fixed, surveyed position;
   log RX timestamps of the same frames on all four for a few thousand
   frames. The per-anchor offsets are the calibration; what must be true is
   that they are **stable** (target well under ~33 ps, i.e. the 1 cm
   outer-anchor budget) over time and board temperature.
