# System overview

## Concept

A worn **wristband** tag is located in 3D space by a fixed **bay station**
with four UWB anchors. The bay station reports position **over Bluetooth LE
to a nearby laptop**. Intended use: a safety/rescue tracking system.

Note this is narrower than the original concept, which had the station
uploading to the internet. That was dropped deliberately on 2026-09-19 once
the team confirmed a laptop will always be present -- and it is what allowed
the host MCU to move to Nordic. See `decisions.md`.

Positioning is a **hybrid of two-way ranging and TDoA**: a center anchor
ranges to the tag for distance, and three outer anchors measure arrival-time
differences against that center anchor for direction. Target is **10-30 cm
at ~10 m on Channel 5 (6489.6 MHz)**. The full scheme, its error budget, and
the clock architecture it forces are in [`positioning.md`](positioning.md) --
read that one first if you're touching anchors, clocking, coax, or
connectors.

```
                         A1 ← antenna on coax
                            \
   ┌─────────────┐           \      ┌───────────────────────────┐
   │  Wristband   │  UWB       ○────│  Bay Station (ONE PCB)     │
   │  (worn tag)  │ ═════════▶ A0   │  4x DW3210, one TCXO       │
   └─────────────┘  one TX    / \   │  BT840 (nRF52840) host     │
                             /   \  └───────────┬────────────────┘
                           A2     A3            │ Bluetooth LE
                      antennas on ~1-2 m        ▼
                      coax, rigid frame       Laptop

   A0     two-way ranging  -> range to tag
   A1-A3  TDoA vs. A0      -> direction to tag

   All four transceivers share one clock on the board.
   Only the antennas are remote.
```

## Boards

| | Wristband | Bay Station |
|---|---|---|
| Role | Worn tag | Fixed reference station |
| UWB | 1x DWM3001C module (UWB + MCU + antennas in one part) | 4x DW3210 IC, all on one PCB; 1 center + 3 outer roles, antennas remote on coax |
| MCU/radio | Nordic nRF52833, inside the DWM3001C (resolved) | Nordic nRF52840, in a Fanstel BT840 module (resolved) |
| Power | Single-cell battery + BMS, sized for just enough runtime -- core function takes priority over battery life | Battery + BMS optimized for longevity, not size |
| Link to the outside | None (talks only to the bay station over UWB) | BLE to a nearby laptop. No internet uplink -- see note above |

## UWB part status

**The bay station's schematic is out of date.** It currently shows four
**DWM3000** modules; the resolved design is four discrete **DW3210** ICs
(QFN40) on the one PCB sharing a single 38.4 MHz TCXO, with the antennas
remote on coax. The module exposes no clock pin, so four of them cannot share
a time base, and TDoA needs one. See `decisions.md` and `positioning.md` for
the datasheet evidence and the full cost of the change.

The wristband is unaffected -- a single transceiver has nothing to
synchronize against, so the DWM3000 module stays the right fit there.

## Interface between the boards

There is **no physical connector** between the wristband and the bay
station -- the only link is the UWB radio. Still to be specified:

- **Channel 5 (6489.6 MHz)** -- resolved, see `decisions.md`
- PRF, preamble, and data rate
- Ranging exchange format and update rate
- Tag ID / payload format riding on the ranging frames
- Multi-tag support: how many, and how they're scheduled

## Bay station internal interfaces

All on-board, and part of the bay station's own design:

- **4x DW3210 -> BT840**: one shared SPI bus (MOSI/MISO/SCLK) with four chip
  selects, plus per-chip IRQ. DW3000 runs to 36 MHz; note **SPIM3 is the only
  high-speed SPI instance on the nRF52840** (32 MHz; the others cap at 8 MHz),
  so the anchor bus must use it -- and check the silicon revision against
  Nordic's erratum on SPIM rates above 8 MHz.
- **Clock**: one 38.4 MHz TCXO -> 1:4 low-skew fan-out buffer -> each chip's
  XTI via 2200 pF AC coupling, with 1 pF from each XTO to ground.
- **Antennas**: four SMA coax runs, ~1-2 m, to a rigid frame. CH5 is above
  U.FL's 6 GHz rating, so SMA is required. Cable loss at 6.5 GHz is the last
  unverified number, though it does not gate baseline length -- the size of
  the rigid antenna frame does. See `positioning.md`.

## Bay station -> laptop

Bluetooth LE from the BT840. Nordic parts are BLE-only -- no Bluetooth
Classic, so no SPP -- which means a GATT service rather than a virtual COM
port. USB-CDC over a cable is the simpler alternative and worth considering,
since the station is wired for power anyway.

Still open: the protocol itself, and whether the station sends raw timestamps
for a host-side solve or a position it computed itself.

## Open decisions

See [`decisions.md`](decisions.md).
