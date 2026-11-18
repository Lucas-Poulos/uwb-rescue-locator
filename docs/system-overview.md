# System overview

## Concept

A worn **wristband** tag is located in 3D space by a fixed **bay station**
with four UWB anchors. The bay station reports **over Bluetooth LE to a
nearby laptop** (the primary path) and can also send reports over **LTE-M**,
and it georeferences itself with GNSS plus a magnetometer so those positions
can be given as world coordinates. Intended use: an outdoor safety/rescue
tracking system.

History: the original concept uploaded to the internet over WiFi; that was
dropped on 2026-09-19 for a BLE-only laptop link, which is what moved the
host to Nordic. On 2026-11-17 the host became the **nRF9151** SiP, which adds
LTE-M and built-in GNSS but has no Bluetooth, so the BT840 stays on as a BLE
bridge. The station must still run fully with no SIM. See `decisions.md`.

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
   ┌─────────────┐           \      ┌────────────────────────────┐
   │  Wristband   │  UWB       ○────│  Bay Station (ONE PCB)     │
   │  (worn tag)  │ ═════════▶ A0   │  4x DW3210, one TCXO       │
   └─────────────┘  one TX    / \   │  nRF9151 host (LTE-M+GNSS) │
                             /   \  │  BT840 BLE bridge (UART)   │
                           A2     A3└──────┬──────────────┬──────┘
                      antennas on ~1-2 m   │ Bluetooth LE │ LTE-M
                      coax, rigid frame    ▼              ▼ (optional)
                                         Laptop        network

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
| MCU/radio | Nordic nRF52833, inside the DWM3001C (resolved) | Nordic nRF9151 SiP host (LTE-M + GNSS); Fanstel BT840 (nRF52840) as BLE bridge (resolved 2026-11-17) |
| Power | Single-cell battery + BMS, sized for just enough runtime -- core function takes priority over battery life | Battery + BMS optimized for longevity, not size |
| Link to the outside | None (talks only to the bay station over UWB) | BLE to a nearby laptop (primary); LTE-M reports when a SIM is fitted |
| Georeferencing | n/a | nRF9151 GNSS (time-shared with LTE) + LIS3MDL magnetometer + LIS2DH accelerometer. Position AND heading are both needed to place a frame-relative bearing on a map |

## UWB part status

The bay station uses four discrete **DW3210** ICs (QFN40) on the one PCB,
sharing a single 38.4 MHz TCXO, with the antennas remote on coax -- wired on
`uwb_array.kicad_sch`. The DWM3000 module was dropped because it exposes no
clock pin, so four of them cannot share a time base, and TDoA needs one. See
`decisions.md` and `positioning.md` for the datasheet evidence.

The wristband is unaffected -- a single transceiver has nothing to
synchronize against, and it uses the DWM3001C module.

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

- **4x DW3210 -> nRF9151**: one shared SPI bus (MOSI/MISO/SCLK, mode 0) with
  four chip selects, plus per-chip IRQ and a shared open-drain reset. The
  DW3000 runs to 36 MHz, but **every nRF9151 SPIM instance caps at 8 MHz**, so
  the host sets the rate. Pins and instance: `bay-station/connectivity_notes.md`
  section 2.
- **nRF9151 <-> BT840**: UART at 1 Mbaud with RTS/CTS plus an attention line,
  carrying our own framed relay protocol (`decisions.md`).
- **Clock**: one 38.4 MHz TCXO -> 1:4 low-skew fan-out buffer -> each chip's
  XTI via 2200 pF AC coupling, with 1 pF from each XTO to ground.
- **Antennas**: four SMA coax runs, ~1-2 m, to a rigid frame. CH5 is above
  U.FL's 6 GHz rating, so SMA is required. Cable loss at 6.5 GHz is the last
  unverified number, though it does not gate baseline length -- the size of
  the rigid antenna frame does. See `positioning.md`.

## Bay station -> laptop / network

Bluetooth LE from the BT840, which relays frames from the nRF9151 to a NUS
GATT service (Nordic parts are BLE-only -- no Classic, so no SPP). The
station sends **raw timestamps** and the laptop solve is authoritative; the
station's own quick-look solve is only for LTE reports (`decisions.md`).

Still open: BLE link security level, and the LTE-M side -- endpoint,
SIM/operator and data budget.

## Open decisions

See [`decisions.md`](decisions.md).
