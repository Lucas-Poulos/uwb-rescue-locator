# Positioning scheme

How the bay station works out where the wristband is. This is the design
this hardware exists to serve -- read it before changing anything in the
anchor, clock, coax, or connector path.

## Requirements

Set 2026-09-19. Everything below is derived from these, so changing them
changes the design.

| | |
|---|---|
| **Accuracy target** | 10-30 cm |
| **At range** | ~10 m |
| **UWB channel** | Channel 5, 6489.6 MHz |
| **Baseline** | ~1 m as set. Worth revisiting: the limit is frame size, not cable loss, and 3 m would meet the 10 cm target without averaging (see "Baseline sets everything") |

## The measurement

Four UWB receivers, in **two different roles**:

| Role | Count | Measures | Contributes |
|---|---|---|---|
| **Center anchor** (A0) | 1 | Two-way ranging (ToF) with the wristband | **Range** -- how far the tag is |
| **Outer anchors** (A1-A3) | 3 | Time *difference* of arrival vs. A0, on the same wristband transmission | **Direction** -- where the tag is |

Writing `p` for the unknown tag position and `a_i` for antenna positions:

```
ToF  (center):   |p - a0|                = c * t_flight
TDoA (outer i):  |p - a_i| - |p - a0|    = c * dt_i        for i = 1, 2, 3
```

The ToF equation is a **sphere** centered on A0. Each TDoA equation is one
sheet of a **hyperboloid** with foci at A0 and A_i. The tag sits where all
four surfaces meet. Three unknowns against four equations, so the system is
overdetermined by one -- use the residual as a live quality metric, not just
a solved position.

### Why this and not plain multilateration

Pure TDoA gives no absolute scale from a single burst. Pure two-way ranging
from four anchors needs four bidirectional exchanges, costing air time and
tag battery -- and the wristband is the power-constrained side.

This hybrid needs **one** transmission from the tag: A0 completes the ranging
exchange, A1-A3 listen to the same packet and timestamp it. One exchange,
four measurements, minimum tag energy.

## Physical architecture

**All four DW3000 transceivers are on the one bay-station PCB, sharing a
single reference clock. The four antennas are remote**, on ~1-2 m coax runs
to a rigid frame.

This is the specific arrangement that makes the scheme work, and it was
chosen over three alternatives (all recorded in `decisions.md`):

- Four DWM3000 modules on one PCB -- impossible, the module exposes no clock
  pin, and a board-sized baseline gives ~17 deg of bearing error.
- Four discrete anchors on satellite boards with clock distributed over the
  harness -- works, but pushes the clock problem into cables.
- Wireless clock-calibration-packet sync between independent anchors -- works,
  keeps the modules, but moves everything into firmware.

Putting all four receivers on one board makes synchronization **structurally
absent rather than solved**: one oscillator, one set of short matched traces,
no drift model, no sync firmware. The cost moves to the RF path instead,
where it is a link-budget problem rather than a timing problem.

### Baseline sets everything

Angular error is `c * sigma_dt / B`, where `B` is the A0-to-outer-antenna
spacing. Lateral error at the tag is roughly `range * angle`. At the chosen
1 m baseline:

**1 cm of differential path error = 0.57 deg of bearing = 10 cm of position
error at 10 m.**

That is the exchange rate that governs this whole design. Memorize it.

| Baseline | Bearing error at 100 ps jitter | Lateral error at 10 m | Cable cost, RG-402 |
|---|---|---|---|
| 0.1 m (all on one PCB) | ~17 deg | ~3 m | -- |
| **1 m (chosen)** | **~1.7 deg** | **~30 cm** | ~0.9 dB |
| 2 m | ~0.86 deg | ~15 cm | ~1.8 dB |
| 3 m | ~0.57 deg | ~10 cm | ~2.7 dB |
| 5 m | ~0.34 deg | ~6 cm | ~4.5 dB |

**Bigger is close to free -- the limit is mechanical, not electrical.** The
link budget has ~17 dB of margin at 10 m (see Link budget below), and decent
coax at CH5 costs on the order of 1 dB per metre. Even a 5 m baseline spends
under a third of the available margin. Cable loss does not become the binding
constraint at any baseline this product would plausibly have.

What actually caps the baseline is **how large a rigid frame you are willing
to build and handle**, since the frame is what keeps the geometry fixed and
the calibration valid (see Mechanical, below).

That is worth weighing against the target: at 1 m, hitting 10 cm depends on
averaging. At 3 m it falls out of a single shot. If the frame can be made
larger, that is the cheapest accuracy in the design -- no part changes, no
firmware, just geometry.

### Error budget at 1 m baseline, 10 m range

| Source | Differential path error | Lateral error at 10 m | Notes |
|---|---|---|---|
| Timestamp jitter, per shot | ~1.4 cm | ~14 cm | Improves as sqrt(N) with averaging |
| Cable length mismatch (1 cm unmatched) | ~1.4 cm | ~14 cm | Calibrates out |
| Generic ranging calibration residual | ~8.5 cm | ~85 cm | **Must be beaten -- see below** |

The jitter figure is derived, not quoted: Table 14 gives 1.5 cm ranging
standard deviation at -85 dBm with DS-TWR, implying roughly 1 cm
single-timestamp jitter, and a TDoA differences two timestamps so it grows
by sqrt(2). Verify against measurement during bring-up.

**Conclusion: 30 cm at 10 m is comfortable. 10 cm requires averaging** --
roughly 10 samples takes ~14 cm down to ~4 cm, which is trivial at any sane
update rate provided the target is not moving fast.

### Calibration is a deliverable, not a bring-up nicety

Table 14 gives ranging accuracy as **+/-6 cm after calibration, approximately
+/-15 cm without**. At a 1 m baseline a +/-6 cm residual would put you at
~85 cm of position error -- three times worse than the loosest target.

That +/-6 cm is the figure for a device calibrated as a *generic ranging
node*. This is a fixed array, so calibrate the **array**: place the tag at
surveyed positions, measure the actual timestamps, and store per-anchor
delay corrections covering antenna delay plus cable delay together. Done
properly this is far tighter than +/-6 cm, and the design does not close
without it.

Because a rigid frame fixes the geometry and the cable lengths, this
calibration can be done **once at manufacture** rather than at every install.

#### A0 and the outer anchors need different calibrations

These are not the same quantity, and conflating them will produce a procedure
that silently misses half the problem.

| | What is being calibrated | Error maps to | Sensitivity |
|---|---|---|---|
| **A0** | **Absolute** antenna + cable delay | Radial (nearer/further) | **1:1** |
| **A1-A3** | Delay **relative to A0** | Tangential (side to side) | **amplified by `range / B`** |

A0's delay sets the range scale: get it wrong by 1 cm of equivalent path and
every fix sits 1 cm too near or too far. Straightforward, and forgiving.

An outer anchor's *relative* delay is a different story. An error of 1 cm in
the differential path becomes `1 cm / B` of bearing error, which at range `r`
becomes `(r/B) x 1 cm` of lateral error. **At r = 10 m and B = 1 m that is a
10x amplification** -- the same "1 cm = 10 cm" exchange rate quoted at the top
of this document, now attributed where it actually comes from.

The practical consequence, which is useful to know before building a fixture:

- **Outer-anchor relative delays must be calibrated ~10x more tightly than
  A0's absolute delay.** For a 10 cm target, A0 needs roughly 10 cm of
  equivalent path accuracy (~330 ps); each outer anchor needs roughly 1 cm
  (~33 ps).
- They can also be measured differently. A0's absolute term needs a *known
  true distance* to the tag. The outer anchors' relative terms do not -- they
  only need the same signal observed simultaneously, so any stable tag
  position works, and errors in knowing where the tag actually is largely
  cancel.

That second point matters: the harder-to-hit calibration is also the one that
does not require an accurate distance reference. Design the fixture around
that.

### Mechanical: build a rigid frame

At 1-2 m spacing the four antennas belong on one rigid structure -- a cross
or triangle -- not as separately installed anchors. Consequences, all good:

- Geometry is fixed at manufacture to sub-millimetre, so **no install-time
  survey**. Anchor position error otherwise feeds into tag position error
  one-for-one.
- Cable lengths are fixed, so the delay calibration stays valid.
- The product is one unit rather than an installation job.

**Offset A0 out of the plane of A1-A3** -- even 20-30 cm forward on a
standoff. Four coplanar antennas have a mirror ambiguity about that plane and
degrade badly in elevation for targets near it. Breaking coplanarity is free
at design time and impossible to retrofit.

## The clock

All four transceivers share one reference. Verified against the **Qorvo /
Decawave DW3000 Datasheet, Version 1.3 (2020)**:

- **Table 10, Section 3.5:** *"A 38.4 MHz signal can be provided from an
  external reference in place of a crystal if desired."*
- **XTI (QFN pin 21):** *"Reference crystal input or external reference
  overdrive pin."*
- **XTO (QFN pin 22):** *"Reference crystal output. Requires 1pF to the
  ground, only if external clock is used, otherwise leave empty."*

### You cannot share a passive crystal

Each chip's XTI/XTO pair forms *its own* oscillator around a crystal -- four
chips would be four oscillators, which is the problem, not the solution. The
actual implementation is:

1. **One active 38.4 MHz TCXO** (not a bare crystal)
2. **One low-skew 1:4 fan-out buffer**
3. **2200 pF AC coupling** into each chip's XTI
4. **1 pF from each chip's XTO to ground**

Buffer output skew is a *fixed* per-chip offset and calibrates out with
everything else. Only skew *stability* matters, which on-board is negligible.

### TCXO selection spec

From Table 10, "External Reference (For example a TCXO)":

| Parameter | Spec |
|---|---|
| Amplitude | 0.8 V to VDD2, Vpp |
| Coupling | Must be AC coupled; 2200 pF recommended |
| SSB phase noise | -132 dBc/Hz @ 1 kHz offset |
| SSB phase noise | -145 dBc/Hz @ 10 kHz offset |
| Duty cycle | 40-60 % |

## The RF path

### Variant: DW3210

Per **Table 1, "DW3000 variants"**:

| Variant | Package | Pins/balls | PDoA |
|---|---|---|---|
| DW3110 | WLCSP | 52 | No |
| DW3120 | WLCSP | 52 | Yes |
| **DW3210** | **QFN40 (5x5mm)** | **40** | No |
| DW3220 | QFN40 | 40 | Yes |

**DW3210** is correct here: QFN40 is hand-assemblable where the 3.1 x 3.5 mm
WLCSP is not, and the non-PDoA variant avoids the PDoA switch's insertion
loss (1.2 dB at CH5 on both TX power and RX sensitivity). Note the DWM3000
module is built on the **DW3110** -- don't order that part by reflex.

Accepted tradeoff: QFN variants output about **2 dB less maximum TX power**
than WLCSP.

### Required passives and layout

- **2 pF series capacitor on RF1** (pin 18) -- always required.
- RF2 (pin 13) is unused on the non-PDoA variant: no cap, but it **must be
  terminated into 50 ohm through a 50 ohm PCB trace**.
- **Section 7.3**: RF1/RF2 must be 50 ohm impedance-controlled; ground removed
  from under the chip on the top layer and inner layer 1; first solid ground
  copper at least 0.25 mm below the top layer. This forces a
  controlled-impedance stackup of **at least 4 layers**.

### Connectors: SMA on the UWB path

CH5 at 6489.6 MHz is **above** the DC-6 GHz rating of U.FL, W.FL, MMCX and
MCX. Use **SMA** (DC-18 GHz). SMB (DC-4 GHz) is also out.

The wristband has no RF connectors at all any more: the DWM3001C carries both
its UWB and Bluetooth antennas on-module, so the U.FL and its matching network
were deleted along with `antenna.kicad_sch`.

Two related calls worth making early:

- Prefer antennas with **integral pigtails** over a connector at each end.
  Every mated pair costs ~0.1-0.3 dB at 6.5 GHz plus a small reflection.
- Consider making the antenna-plus-cable assembly **captive rather than
  user-detachable**. A swapped or shortened cable silently invalidates the
  delay calibration, which is the tightest constraint in the whole design.

### Antennas

Candidates covering CH5, verified to exist with these bands from vendor
product pages (full datasheets not yet pulled -- confirm before BOM):

- **Taoglas UWC.01** -- SMD chip antenna, 6-8 GHz, 4 dBi peak
- **Taoglas ILA.68** -- LTCC, 6-8.5 GHz, compact
- **Taoglas UWCCP.01** -- circularly polarized, aimed at ToA/AoA localization

Abracon's ACR1004U is 3-6 GHz and **does not cover CH5** -- don't reach for
it by reflex.

Note there is no lambda/2 spacing constraint here. That applies to PDoA,
which measures phase modulo 2pi; TDoA measures absolute time and has no
wrapping ambiguity, so the baseline can be any length.

### Link budget

Table 12 gives 86 dB at CH5 (850 kbps, 1024-symbol preamble). Free-space
loss at 10 m and 6489.6 MHz is 68.7 dB, leaving **~17 dB of margin**. Cable
loss of 2-5 dB is easily absorbed. Range is not the binding constraint at
this target; baseline and calibration are.

**TX-side cable loss is free.** Table 11 gives max output PSD as -31 dBm/MHz
(-33 for QFN variants) against a -41.3 dBm/MHz EIRP regulatory limit, so a
normal design is already backing off ~8 dB. Cable attenuation eats into that
back-off rather than the link budget.

**RX-side cable loss is not recoverable** -- it comes straight off SNR, and
UWB timestamp precision is SNR-dependent. All four anchors receive, so this
is the loss that actually costs you something.

**But it is not what limits baseline length.** ~17 dB of margin against
roughly 1 dB/m for decent coax means several metres of cable before it
matters -- further than the frame will practically extend. An earlier
revision of this document claimed cable loss capped the baseline; that was
wrong, and it had the effect of discouraging the cheapest accuracy
improvement available. The real cap is the mechanical frame. See "Baseline
sets everything" above.

**Still worth verifying:** the actual loss-per-metre of the chosen cable at
6.5 GHz. Every figure quoted here is an estimate. It is no longer a gating
number for the baseline decision, but it does set how much of the 17 dB you
are spending, and it matters directly for timestamp precision -- lower SNR
means noisier leading-edge detection, which is the top line of the error
budget.

## Host interface

Fanstel **BT840** (Nordic nRF52840). Four DW3210s share MOSI/MISO/SCLK with
four chip-select lines -- the DW3000 is a standard non-daisy-chain SPI
peripheral running to **36 MHz** (20 MHz in CRC mode).

**Use SPIM3 for the anchor bus.** It is the only high-speed SPI instance on
the nRF52840 (32 MHz; the others cap at 8 MHz), and 32 MHz is comfortably
inside the DW3000's 36 MHz ceiling. Check the silicon revision against
Nordic's erratum on SPIM rates above 8 MHz.

**MCU timing jitter does not affect accuracy.** Timestamps are latched in
hardware at packet reception and read over SPI afterwards, and delayed-TX
schedules transmissions in the chip rather than the MCU. FreeRTOS and WiFi
latency affect update rate, not precision.

Driver: Qorvo's own reference stack targets nRF52840, so start there rather
than from the community ESP-IDF port. **Caveat either way:** the widely used
community driver ([br101/dw3000-decadriver-source](https://github.com/br101/dw3000-decadriver-source))
was trimmed to support only one DW3000 per board. Multi-instance support
exists upstream and needs restoring -- a bounded integration task.

## Open questions

Tracked in `decisions.md`; listed here so the technical context stays in one
place.

- Cable loss per metre at 6.5 GHz for the chosen coax -- affects SNR and so
  timestamp precision. Does NOT gate the baseline; the frame size does.
- TCXO and 1:4 buffer part selection against the Table 10 spec above.
- Whether SYNC/OSTR is needed at all now that the clock is genuinely shared.
  The DW3000 **User Manual** (not the datasheet) is the source.
- Array calibration procedure and fixture.
- Update rate, multi-tag scheduling, and where the solve happens (on the
  BT840 or host-side from raw timestamps).
