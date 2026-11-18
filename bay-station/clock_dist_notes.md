# clock_dist.kicad_sch -- notes

One 38.4 MHz reference for all four DW3210s. This is the block that makes
TDoA possible: one oscillator, four matched copies, no sync firmware.

```
+3V3 -R225 0R-> +3V3_TCXO --- U30 RPT1490LN --R230 22R--> TCXO_OUT --> U31 LMK1C1104 CLKIN
+3V3 -R226 0R-> +3V3_CLKBUF --- U31 VDD
U31 Y0 -R231 22R- C24 2200pF -> UWB_CLK0 -> A0 XTI     (Y1->A1, Y2->A2, Y3->A3)
```

XTO 1pF caps C28-C31 moved to uwb_array (they belong at the XTO pin).

## Requirement (DW3000 Datasheet v1.1, Table 10, "External Reference")

| Parameter | Limit |
|---|---|
| Frequency | 38.4 MHz |
| Amplitude | 0.8 V to VDD2, Vpp |
| Coupling | Must be AC coupled; 2200 pF recommended |
| SSB phase noise | -132 dBc/Hz @ 1 kHz, -145 dBc/Hz @ 10 kHz |
| Duty cycle | 40-60 % |

## PROPOSED parts

### U30 -- Rakon RPT1490LN, 38.4 MHz (PROPOSED)

Rakon datasheet "Pluto+ Ultra-Low Noise TCXO RPT1490LN", Issue B, 21 Oct 2024
(rakon.com):

- 10-50 MHz, **"Standard frequency 38.4 MHz"**; 3.3 V ±5 %; 10 mA typ, 15 mA max.
- **CMOS output**, VOL ≤ 0.4 V, VOH ≥ 2.7 V, 15 pF load, rise/fall 1-2 ns,
  **duty 49-51 %**.
- Phase noise, page 2 plot "38.4 MHz RPT1490LN TCXO phase noise with CMOS
  Output", analyser markers: **-151.3 dBc/Hz @ 1 kHz, -165.7 @ 10 kHz**,
  -175.5 @ 100 kHz. These are **typical** (25 °C) plot readings, not
  guaranteed limits -- ~19-20 dB of margin to Table 10.
- ±0.3 ppm over -40..95 °C, ±1 ppm calibration. Vc 0.5-2.5 V (input ≥ 1 MΩ),
  ±6..±10 ppm tuning referenced to Vc = 1.5 V. Pins: 1 Vc, 2/3 GND, 4 RF out,
  5 do not connect, 6 Vcc. 14.5 x 9.5 x 6.0 mm.

**Risks:** it is large and almost certainly expensive, and I could not
confirm a catalogue ordering code for the 38.4 MHz variant -- one distributor
lists it as Rakon **E8246LF** with zero stock and RFQ only. Treat it as
quote-only until Rakon confirms. The footprint is `_PLACEHOLDER` (the "7.9 mm"
row dimension is read as centre-to-centre; the bottom view's 6.3 mm could make
it 8.1 mm).

Vc: R227 10k / R228 8.2k from `+3V3_TCXO` = 1.49 V, the 1.5 V reference
point. C215 100 nF (modulation bandwidth is 3.5 Hz). TP430 lets you
over-drive Vc on the bench (lift R228) to trim the array's frequency.

**Why not the TCXOs Qorvo lists (DS v1.1 Table 22: TXC 7Z38470005, Rakon
IT2200K):** TXC's own 7Z series sheet gives "Phase Noise at 1 kHz offset -130
dBc/Hz", which is **2 dB worse than Table 10 in the same Qorvo datasheet**,
and a 0.8 Vpp clipped-sine output. Raltron RTX-2520AF31-S-38.400 is the same
(-130 @ 1 kHz, -145 @ 10 kHz typ, clipped sine). The clipped-sine parts are
also incompatible with the LMK1C1104 input (VIH 0.7 x VDD / VIL 0.3 x VDD).
Abracon ASTX-H11 (HCMOS) gives -130 @ 1 kHz as well. A CMOS-output 38.4 MHz
TCXO that meets Table 10 was surprisingly hard to find; the RPT1490LN is the
only one I verified from a datasheet. Worth one more search for a smaller
CMOS TCXO with a guaranteed 1 kHz figure before ordering.

If a small clipped-sine TCXO is preferred anyway (Qorvo-tested, cheap): pair
it with a universal-input buffer such as TI **LMK00105** (SNAS579G: CLKin
single-ended AC-coupled 0.3-2 Vpp; 1:5; 6 ps output skew) and accept that TI
says a slew rate below ~2 V/ns "will degrade the noise floor" (s8.1.1).
Not drawn.

### U31 -- TI LMK1C1104PWR (PROPOSED)

TI datasheet SNAS791D (Dec 2019, rev. Feb 2022):

- 1:4 LVCMOS, TSSOP-8 (PW). Pinout Fig 6-4 / Table 6-1: 1 CLKIN, 2 1G,
  3 Y0, 4 GND, 5 Y2, 6 VDD, 7 Y3, 8 Y1. Orderable LMK1C1104PWR (Active).
- At 3.3 V: **output-output skew 25 ps typ / 50 ps max**, part-to-part 250 ps,
  propagation 1.5-2 ns, ROUT 50 Ω, additive jitter 8 fs typ (12 k-20 MHz),
  **ODC 45-55 % with 50 % input**, VOH ≥ 2.8 V / VOL ≤ 0.2 V @ 1 mA.
- CLKIN is LVCMOS, 3.3 V tolerant at every VDD, VIH 0.7 x VDD, slew ≥ 0.1 V/ns.
  The RPT1490LN's 1-2 ns edges are ~1.3-2.6 V/ns.
- Phase noise: Fig 10-2 (source) vs Fig 10-3 (3.3 V output) at 156.25 MHz
  show no measurable close-in degradation (~-141 @ 1 kHz, ~-151 @ 10 kHz on
  both). The 1.8 V curve (Fig 10-5) shows a close-in hump -- **run it at 3.3 V**.
- 1G pulled up (R229 10k): outputs always on.

**Amplitude at XTI:** 3.3 V LVCMOS through 2200 pF gives ≥ 2.6 Vpp, up to
~3.3 Vpp -- inside "0.8 V to VDD2", but close to the top when VDD2 = 3.3 V.
If XTI shows over-drive symptoms, the cheap experiment is to lift R226 and
supply the buffer at 2.5 V through TP429 (still above its 2.375 V minimum,
CLKIN stays 3.3 V tolerant). If that fixes it, the permanent fix is a 2.5 V
LDO for the buffer.

### TCXO_EN

Omitted, as the contract allows: the RPT1490LN has no enable, and gating
U31 would stop all four DW3210 cores (they stall without a clock).

## Supplies

Each part has its own rail through a 0603 0R (R225, R226) -- the "0R/bead
option": fitted 0R, the pads take a low-DCR 0603 bead if the TCXO or buffer
supply noise shows up as phase-noise spurs (TI SNAS791D s11 recommends but
does not require a bead). No bead part number chosen. Both 0Rs double as
current-measure break points. Test pads: TP428 `+3V3_TCXO`, TP429
`+3V3_CLKBUF`. Decoupling per TI Fig 11-1 (10 µF board side, 1 µF + 0.1 µF
at the pin); TCXO 10 µF + 100 nF (Rakon gives no decoupling guidance).

## Terminations

R230 (TCXO -> CLKIN) and R231-R234 (Yn -> AC cap) are 22R series
source terminations. With ROUT ≈ 50 Ω the ideal on a 50 Ω line is near 0R;
22R is a starting value to tune with a scope at XTI. **All four R231-R234
must stay equal.** Put R231-R234 at the buffer pins and C24-C27 at each XTI.

## Layout

- `UWB_CLK0..3` from Yn to XTI: **equal length**, same layer, same via
  count, away from SPI and RF. Skew (≤ 50 ps) is fixed and calibrates out;
  what has to be avoided is a long or unequal run whose delay moves with
  temperature.
- Clock test pads (TP5-TP9 on testpoints) are stubs: smallest pad, on the
  trace.

## Bring-up tests for this sheet

1. `+3V3_TCXO` / `+3V3_CLKBUF` at TP428/TP429; TCXO current by lifting R225
   (~10 mA typ).
2. `TCXO_OUT` (testpoints TP5): 38.4 MHz on a counter, within the ±1 ppm
   calibration plus reflow shift; duty ~50 %.
3. Each `UWB_CLKn` at the XTI side of its cap: same amplitude on all four,
   within 0.8 V..VDD2 Vpp, duty 45-55 %, no ringing.
4. Skew UWB_CLK0 vs 1/2/3 on a two-channel scope with matched probes and the
   short ground spring (TP3). Record it: it is part of the calibration
   baseline, and re-measuring it hot and cold is the cheapest check that the
   clock tree is not adding temperature-dependent skew.
5. Phase noise at TCXO_OUT and at one XTI if an analyser is available;
   compare against -132 / -145 dBc/Hz.
