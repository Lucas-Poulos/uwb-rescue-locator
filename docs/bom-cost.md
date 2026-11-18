# BOM cost estimate

Rough build cost for **one prototype pair** (one wristband + one bay station),
at quantity-one hobbyist pricing. Compiled 2026-09-19; bay station revised
2026-11-17 for the nRF9151 host.

## How to read this

Each board's authoritative part-by-part BOM is its own
`<board>/libs/components.csv` -- part numbers, symbols, footprints, datasheet
URLs, and verification notes. **This document is the money view only**, and it
deliberately does not duplicate that detail.

Prices are marked:

- **[V]** verified against a distributor listing, with the date
- **[E]** estimate -- order of magnitude, for planning only
- **[--]** not priced yet -- no estimate made; excluded from the total

Nobody should order from this table. It exists so the team knows whether this
is a $100 project or a $1000 one before committing, and so the expensive
lines are visible early.

## Wristband

| Item | Qty | Unit | Ext | |
|---|---|---|---|---|
| Qorvo DWM3001C module | 1 | $38 | $38 | [E] -- replaces NINA-B111 + DWM3000 + antenna |
| LiPo cell | 1 | $8 | $8 | [E] |
| PCB, 4-layer, small, qty-5 order | 1 | $10 | $10 | [E] |
| SWD header, 2x5 1.27mm | 1 | $1.50 | $1.50 | [E] |
| MCP73831 charger | 1 | $0.70 | $0.70 | [E] |
| MCP1700T-3302E/TT LDO | 1 | $0.50 | $0.50 | [E] |
| DW01A + FS8205 protection pair | 2 | $0.30 | $0.60 | [E] |
| AO3401A, ESD5B5.0ST1G | 2 | $0.35 | $0.70 | [E] |
| USB-C receptacle, JST-PH | 2 | $0.65 | $1.30 | [E] |
| Status LEDs 0603 (D2, D3) | 2 | $0.15 | $0.30 | [E] |
| Passives, ~25x 0603 | 25 | $0.05 | $1.25 | [E] |
| | | | **~$67** | |

## Bay station

| Item | Qty | Unit | Ext | |
|---|---|---|---|---|
| **Coax assemblies, 1-2 m, SMA both ends** | 4 | $15 | **$60** | [E] -- see note |
| Qorvo DW3210 (DW3210TR13) | 4 | $10.45 | $41.80 | **[V]** DigiKey, Sept 2026 |
| PCB, 4-layer **controlled impedance**, qty-5 | 1 | $40 | $40 | [E] |
| UWB antennas (Taoglas UWC.01 class) | 4 | $8 | $32 | [E] |
| Rigid antenna frame (fabrication) | 1 | $30 | $30 | [E] |
| SMA board connectors | 4 | $2.50 | $10 | [E] |
| Li-Ion cell | 1 | $10 | $10 | [E] |
| Nordic nRF9151 SiP (host, LTE-M + GNSS) | 1 | -- | -- | [--] |
| Fanstel BT840 (nRF52840), now the BLE bridge | 1 | $6.88 | $6.88 | **[V]** Fanstel, Sept 2026 -- replaced ESP32-S3-WROOM-1 (~$3.50) |
| MAX17048 fuel gauge | 1 | $3 | $3 | [E] |
| 38.4 MHz TCXO, Rakon RPT1490LN (proposed) | 1 | -- | -- | [--] -- looks quote-only; likely far above the old $3 guess |
| 1:4 clock buffer, TI LMK1C1104 (proposed) | 1 | $2.50 | $2.50 | [E] |
| MCP73871 power-path charger | 1 | $2 | $2 | [E] |
| TPS62A02PDDCR + XFL4020 inductor | 2 | $1.20 | $2.40 | [E] |
| TPS63802 buck-boost + XFL4020 inductor | 2 | -- | -- | [--] |
| Barrel jack, USB-C | 2 | $1 | $2 | [E] |
| AO3401A, 2x ESD5B5.0ST1G | 3 | $0.35 | $1.05 | [E] |
| Tactile buttons (SW2, SW11, SW12) | 3 | $0.30 | $0.90 | [E] |
| Status LEDs 0805 (D4-D7, D400, D401) | 6 | $0.15 | $0.90 | [E] |
| GNSS antenna, u.FL pigtail | 1 | $10 | $10 | [E] -- not yet selected |
| LTE-M antenna, u.FL pigtail | 1 | -- | -- | [--] -- not yet selected |
| GNSS LNA + LDO, SIM holder + ESD filter, 2x U.FL | 6 | -- | -- | [--] |
| LIS3MDL magnetometer + LIS2DH accelerometer | 2 | $2 | $4 | [E] |
| Passives, ~55x 0603/0805 | 55 | $0.05 | $2.75 | [E] -- now well over 55; recount from `components.csv` |
| | | | **~$263 + [--] rows** | |

**System total: roughly $330 for one prototype pair, before the unpriced
rows** -- the nRF9151 and the Rakon TCXO are the two that could move it
materially. The MAX-M10S (~$12) is gone.

## Wristband consolidation (2026-09-19)

The wristband line above is one module where it used to be four items. Moving
to the DWM3001C removed NINA-B111 (~$12), DWM3000 ($28.34 [V]), the ProAnt
antenna (~$5) and the U.FL connector (~$1) -- about **$46** -- and added one
module estimated at **$38**. Roughly a wash on cost, and that is the point:
the saving was never the argument. What it actually bought was one part
instead of four, two fewer schematic sheets, no inter-chip SPI to design, no
RF matching network to tune, a free accelerometer, and Qorvo reference
firmware for the exact module.

**The $38 is an estimate and the weakest number in this document** -- I could
not find qty-1 pricing. Get a real quote before planning around it.

## Georeferencing (2026-09-23, revised 2026-11-17)

Originally a MAX-M10S GNSS, magnetometer, accelerometer and an antenna, about
**$26**. Since 2026-11-17 the GNSS receiver is inside the nRF9151, so the
georeferencing-only cost is the two ST sensors, the GNSS antenna and the
small LNA chain in front of the nRF9151's GPS pin -- about $14 plus the
unpriced LNA parts.

## Two things the table makes obvious

**The RF interconnect is the single biggest cost, not the silicon.** Coax,
antennas, SMA connectors and the frame come to about **$132** -- more than
half the bay station, and over five times what the four transceivers cost.
That is the real price of the architecture, and it is worth knowing before
anyone optimises a $0.05 passive. It also means the coax choice is a genuine
cost/performance decision, not just an electrical one.

**Going discrete made the silicon cheaper, not more expensive.** This is
counterintuitive and worth recording:

| | Unit | x4 |
|---|---|---|
| DWM3000 module | $28.34 **[V]** | $113.36 |
| DW3210 IC | $10.45 **[V]** | $41.80 |
| | | **saves $71.56** |

So the discrete decision costs roughly $132 in RF interconnect and ~$30 in
extra PCB, offset by ~$72 saved on transceivers. Net, call it **$90 extra**
for a design that can actually do TDoA -- against a module-based design that
provably cannot, at any price.

And because this is a **university prototype with no certification
requirement** (see `decisions.md`), the item that would normally dominate
this comparison -- FCC/CE testing for an intentional radiator -- is simply
not a line item.

## Not costed here

- **Dev kits.** Strongly recommended and not in the table above. An nRF9151
  DK (host, modem, GNSS -- also the reference for the GNSS C/N0 test in
  `verification-plan.md`), an nRF52840 DK (BLE bridge) and a DWM3001CDK would
  cover tag and station firmware before any custom board exists.
- **Assembly.** Assumes hand assembly. The DW3210 is QFN40 at 0.4 mm pitch --
  doable with a stencil and hot plate, but it is the hardest part on either
  board, and a reflow failure on a $10.45 part that then needs rework is a
  real cost in time.
- **Iteration.** First boards are rarely the last. Budget at least two spins.
- **Test equipment.** Array calibration needs a way to place the tag at
  surveyed positions to better than the accuracy you are trying to achieve.
  Depending on how that is done it could be free or could dominate everything
  above.
- **Enclosure.** Decided 2026-09-23 but neither selected nor costed. It has
  to be RF-transparent or it blocks the BT840 on-module BLE antenna (and the
  LTE-M/GNSS antennas, unless those mount outside), which rules out the cheap
  metal-box option. Plus the antenna frame beyond it, and
  cabling/PSU odds and ends.

## Before ordering

Every **[E]** row needs a real quote. The two that matter most, because they
are big and because the estimates behind them are the weakest:

1. **Coax assemblies** -- $60 is a guess, and the same guess drives the
   loss-per-metre figure that sets how much link margin you spend. Price and
   loss-spec these together. Note a longer baseline costs little electrically
   (~1 dB/m against ~17 dB of margin) but buys accuracy directly -- if the
   frame can be larger, the cable line item is the wrong place to economise.
2. **Controlled-impedance 4-layer PCB** -- $40 for a qty-5 order varies a lot
   by vendor and by stackup. DW3000 Section 7.3 constrains the stackup (see
   `positioning.md`), and as of 2026-09-23 it is set in the board file:
   35um copper throughout, 254um prepreg / 400um core / 254um prepreg,
   **1.048 mm finished**. That is deliberately the datasheet's own figure and
   **not a catalogue thickness** -- fabs quote 1.0 or 1.2 mm 4-layer, so
   expect to work to their nearest stackup and re-solve the 50 ohm trace
   widths against their real dielectric numbers. Get quotes against the
   actual spec, not a generic 4-layer, and ask for the impedance-control
   surcharge separately.
