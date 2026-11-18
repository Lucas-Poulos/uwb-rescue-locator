# UWB Rescue Locator

Repo: https://github.com/Lucas-Poulos/uwb-rescue-locator

A two-board UWB positioning system for a rescue/safety use case: a
**wristband** worn by a person, and a fixed **bay station** that locates it
in 3D from four anchor points and reports it over Bluetooth LE to a nearby
laptop (with an optional LTE-M uplink from the station).

Positioning is a **hybrid of two-way ranging and TDoA**, not symmetric
multilateration. A center anchor ranges to the tag for distance; three outer
anchors timestamp the same tag transmission and give direction from the
arrival-time differences. The four anchors are **not interchangeable** --
see [`docs/positioning.md`](docs/positioning.md), which is the document to
read first if you're working on anchors, clocking, coax, or connectors.

## Getting started (new contributor setup)

### 1. Install KiCad

The team standard is **KiCad 10.0.5** (see Toolchain below for why).

- **macOS**: `brew install --cask kicad` (Homebrew). If KiCad is already
  installed some other way, add `--force` to overwrite it.
- **Windows/Linux**: download the installer for your platform from
  https://www.kicad.org/download/.

You do **not** need to set any environment variables or configure library
paths yourself -- both boards' `fp-lib-table`/`sym-lib-table` use
`${KIPRJMOD}`-relative paths into this repo's own `shared/` and `libs/`
folders, so cloning the repo anywhere and opening a project just works.

The very first time you launch the KiCad GUI on a given machine, it may
offer to set up its own default global libraries (Device, Connector, etc.)
-- accept the defaults. This is a one-time, per-machine, KiCad-level setup
step, unrelated to this repo.

### 2. Get repo access and clone it

Ask whoever's administering the repo to add you as a collaborator (repo
link at the top of this file), then:

```
git clone git@github.com:Lucas-Poulos/uwb-rescue-locator.git
cd uwb-rescue-locator
```

(Use the HTTPS clone URL instead if you haven't set up an SSH key with
GitHub.)

### 3. Open a board

KiCad doesn't support one project spanning multiple PCBs, so open whichever
board you're working on directly -- there's no single top-level project
file for the whole repo:

```
open wristband/wristband.kicad_pro       # macOS; or just double-click the file
open bay-station/bay-station.kicad_pro
```

### 4. Sanity-check your setup

From a terminal, **outside** this repo (see the `kicad-cli` gotcha further
down for why):

```
cd /tmp
kicad-cli sch erc /path/to/uwb-rescue-locator/wristband/wristband.kicad_sch
```

If this reports a handful of known/expected items (see each board's sheet
table below) rather than a wall of "library not included in configuration"
errors, your KiCad install is set up correctly. If you do see that wall of
errors, see the per-major-version global library table note in Toolchain.

Before pushing anything, also read `CONTRIBUTING.md` -- branch off `main`,
don't edit a sheet someone else is actively working on, and PRs need review
(branch protection is on).

## Status (last updated 2026-11-17)

**Schematic capture is well along on the bay station and early on the
wristband.** On branch `redesign/nrf9151-host` every bay-station sheet has
been wired against one net contract (`docs/net-contract.md`). Neither board
is fab-ready: the bay station still has placeholder footprints on its two
biggest new parts (below). If you're an agent or a new teammate picking this
up cold, read this whole section before touching anything -- it's written to
be a complete handoff.

> ### Architecture change 2026-11-17: nRF9151 host
>
> The bay station's host moved from the Fanstel BT840 (nRF52840) to the
> **Nordic nRF9151** SiP -- LTE-M/NB-IoT modem, built-in GNSS and an
> application core. The nRF91 has no Bluetooth, so the **BT840 stays as a
> UART BLE bridge** to the laptop, and the **MAX-M10S GNSS is gone** (its
> sheet is now `orientation.kicad_sch`). Reasons and the full set of
> consequent calls are in `docs/decisions.md` ("nRF9151 host redesign").
>
> Unchanged, and still the core of the design: four discrete **DW3210**s on
> the one PCB sharing one 38.4 MHz TCXO through a 1:4 buffer, antennas remote
> on coax, A0 doing two-way ranging and A1-A3 TDoA against it
> (`docs/positioning.md`). **Target: 10-30 cm at ~10 m, Channel 5.** No FCC/CE
> work -- university prototype. The critical path is still **array
> calibration**, plus the multi-instance DW3000 driver.

### What exists, per board

The wristband has 7 hierarchical sheets, the bay station 10. Reference designators are
project-wide unique per board (checked 2026-11-17 on the bay station, no
collisions) -- see each `libs/components.csv` for the full part-by-part BOM.

**Wristband** (`wristband/`):
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** (global labels, no drawn wires), ERC clean (0 errors, 1 cosmetic warning) | JST-PH battery -> AO3401A reverse-polarity FET -> TVS -> DW01A+FS8205A protection -> MCP73831 charger (USB-C in) |
| Radio MCU | Placement only, not wired | DWM3001C (U3) + decoupling. One module: DW3110 UWB + nRF52833 MCU + accelerometer + both antennas |
| Mechanical | Placement only | 4x M2 mounting holes |
| Regulation | Placement only, not wired | TPS7A0233PDBVR LDO (3.3V) -- battery hits 4.2V, DWM3001C tops out at 3.6V |
| Programming/Debug | Placement only, not wired | ARM Cortex Debug SWD header, targeting the nRF52833 inside U3 |
| Indicators | Placement only | Status LEDs: D2 charge (MCP73831 STAT) + D3 system (nRF52833 GPIO) |
| Test Points | Placement only, **new** | TP1-TP5: both rails, 2x GND, firmware timing marker |

**Bay Station** (`bay-station/`) -- per-sheet detail in each
`bay-station/*_notes.md`; sheet-by-sheet summary in `bay-station/README.md`:
| Sheet | Status | Contents |
|---|---|---|
| Power BMS | **Wired** | Barrel jack + USB-C -> MCP73871 power-path charger -> MAX17048 fuel gauge; backup cell with AO3401A + TVS. THERM window sized for cold-charge cutoff |
| Regulation | **Wired** | U8 TPS62A02 -> `+3V3`; **U40 TPS63802 buck-boost -> `+VBAT_LTE`** (nRF9151 VDD, 3.59 V); `+3V3` sequenced >= 6 ms after it; PPK2 break links on both rails |
| Connectivity | **Wired** | **nRF9151 (U20)** host with Nordic's HDG decoupling, LTE + GNSS (BGA524N6 LNA) on u.FL, nano-SIM (+ DNP eSIM); **BT840 (U3)** as UART BLE bridge |
| UWB Array | **Wired** | 4x DW3210 (U4=A0 center, U5-U7=A1-A3 outer), Qorvo Fig 32 decoupling, per-anchor 0R rework links, pi-match pads, SMA J20-J23 (proposed CONSMA020.042-G) |
| Clock Distribution | **Wired** | Proposed Rakon RPT1490LN TCXO -> TI LMK1C1104 1:4 buffer -> 2200 pF -> each XTI |
| Orientation (was GNSS / Orientation) | **Wired** | LIS3MDL magnetometer (U10, 0x1C) + LIS2DH accelerometer (U11, 0x19) |
| Indicators | **Wired** | D4-D6 charger status, D7 `LED_SYS`, D400 `LED_LTE`, D401 `LED_LINK`, resistors computed per rail |
| Programming/Debug | **Wired** | J3 nRF9151 SWD, J32 BT840 SWD, DNP Tag-Connect pads, J33 debug UART, SW2/SW11 resets, SW12 user button |
| Test Points | **Wired** | 65 pads covering every net-contract net (+ local pads on each sheet); index in `docs/verification-plan.md` |
| Mechanical | Placement only | 4x M3 mounting holes, 3 fiducials |

Whole-project ERC after the merge (2026-11-17, `kicad-cli` 10.0.5,
`--severity-all`): **7 warnings, 0 errors**, down from 596, with 432
components loaded (so not the silent `extends` failure). All 7 are
library-copy warnings, none connectivity: six `lib_symbol_mismatch` on
flattened stock symbols (BT1, Q1, J2, TH1, J3, J32) and the known U8
`TPS62A02PDDCR` lib_id (see `docs/decisions.md`). The 97 `unconnected-*` nets
in the netlist are deliberate no-connect flags (spare BT840 GPIOs, nRF9151
reserved/MAGPIO pins, unused header pins). Per-sheet before/after counts are
in `bay-station/handoff/`.

### Confirmed chips/ICs (all sourced against real datasheets, not guessed)

| Part number | Role | Board(s) | Qty |
|---|---|---|---|
| Qorvo **DWM3001C** | UWB transceiver + nRF52833 MCU + LIS2DH12 accelerometer + both antennas, one module. Replaced NINA-B111 + DWM3000 + the antenna sheet | Wristband | 1 |
| Qorvo **DW3210** | Discrete UWB transceiver IC, QFN-40 5x5mm. One per anchor (U4=A0 center, U5-U7=A1-A3 outer). Chosen over the DWM3000 module because the module exposes no clock pin, and a shared reference is what makes the TDoA array work -- see `docs/positioning.md` | Bay Station | 4 |
| Qorvo **DWM3000** | UWB transceiver module. **No longer used on either board** -- the wristband moved to the DWM3001C and the bay station to discrete DW3210. Symbol and footprint are retained in `shared/` for reference only | -- | 0 |
| Microchip **MCP73831** | LiPo linear battery charger | Wristband | 1 |
| Fortune Semiconductor **DW01A** | Battery protection IC | Wristband | 1 |
| Fortune Semiconductor **FS8205** (commonly sold as "FS8205A" -- see `wristband/libs/README.md`) | Protection dual MOSFET, DW01A's partner IC | Wristband | 1 |
| AOS **AO3401A** | Reverse-battery-polarity protection P-MOSFET ("ideal diode") | Wristband + Bay Station | 2 |
| onsemi **ESD5B5.0ST1G** | TVS diode, battery/power-input protection | Wristband (1) + Bay Station (2) | 3 |
| Nordic **nRF9151** (nRF9151-LACA-R7) | Host SiP: LTE-M/NB-IoT modem + GNSS + Cortex-M33. Replaced the BT840 as host 2026-11-17. **Footprint is a PLACEHOLDER with invented pads** | Bay Station | 1 |
| Fanstel **BT840** (Nordic nRF52840) | UART BLE bridge to the laptop (host until 2026-11-17; replaced ESP32-S3-WROOM-1 before that) | Bay Station | 1 |
| Microchip **MCP73871** | Charge management + power-path IC | Bay Station | 1 |
| Maxim/Analog Devices **MAX17048** | Battery fuel gauge (SOC monitor) | Bay Station | 1 |
| TI **TPS7A0233PDBVR** | LDO regulator (3.3V) -- battery rail can hit 4.2V, which exceeds the DWM3001C's 3.6V operating max without this. Replaced the MCP1700 on 2026-09-23 | Wristband | 1 |
| TI **TPS62A02PDDCR** | Buck regulator, `+VSYS` -> `+3V3` | Bay Station | 1 |
| TI **TPS63802DLAR** | Buck-boost, `+VSYS` -> `+VBAT_LTE` (nRF9151 VDD). Footprint PLACEHOLDER | Bay Station | 1 |
| ST **LIS3MDL** / **LIS2DH** | Magnetometer (heading) / accelerometer (tilt, knock). LIS2DH may be EOL -- check | Bay Station | 1 + 1 |
| Infineon **BGA524N6** + TI **TPS7A0228** | GNSS LNA and its COEX0-switched 2.8 V LDO, as on the nRF9151 DK | Bay Station | 1 + 1 |
| TI **TPD3F303** | SIM ESD/EMI filter | Bay Station | 1 |
| Rakon **RPT1490LN** / TI **LMK1C1104** | 38.4 MHz CMOS TCXO / 1:4 clock buffer -- **PROPOSED**; the TCXO looks quote-only | Bay Station | 1 + 1 |

Footprint caveats: MAX17048 is flagged `_PLACEHOLDER` in its footprint file
-- pin/electrical data is fully verified, but one land-pattern dimension
needs re-checking against the real datasheet figure before fab (see
`bay-station/libs/README.md`). The same caveat applies to the DWM3000
footprint retained in `shared/`, though nothing uses it now. On the bay
station, **the nRF9151 (U20) and TPS63802 (U40) footprints are
placeholders** -- the nRF9151 one has made-up pad positions and must not go
to fab -- and so are the Rakon TCXO, the SMA edge launch (needs EM
simulation) and the DNP eSIM.

**No footprint assigned yet**: `U3` on both boards (BT840, 65 pins; and
DWM3001C, 48 pins), and bay-station FB1-FB4 (Murata BLM03 case size
unresolved). L1 and SW2 were closed on 2026-11-17. Not blocking while both
`.kicad_pcb` files are still empty, but it blocks layout.

Standard passive size for this whole project: **0603** for R/C/L (0-ohm
0603 link/jumper resistors are documented as a standard available option in
each `components.csv`, not yet placed on any sheet -- no specific
strap/bridge need identified yet).

Full reasoning/history for every choice above, plus the still-open
decisions (anchor placement, uplink backend, etc.), is in
`docs/decisions.md`.

### Known gotchas for whoever (human or agent) works on this next

- **kicad-cli silently fails on `extends`-based symbols.** Any cached
  schematic symbol using KiCad's `extends` mechanism (e.g. the default
  `AO3401A extends TP0610T`) makes `kicad-cli` fail to load the *entire
  file* and silently report it as empty (0 components, 0 ERC violations)
  rather than erroring loudly. Both boards work around this by embedding a
  flattened, non-`extends` copy of AO3401A. If a future sheet adds another
  `extends`-based part and ERC suspiciously shows 0 violations, check this
  first.
- **Always run `kicad-cli` from a scratch directory, never from inside a
  git repo.** It writes `.rpt` report files to the current working
  directory as a side effect; running it from inside a repo pollutes that
  repo's working tree with stray files.
- **KiCad's global library table is per-major-version and doesn't
  auto-populate from `kicad-cli` alone** -- see the Toolchain section below.
- **Don't leave a KiCad GUI window open on a project while also editing its
  files by hand/via script.** This happened once already: a background GUI
  session silently resaved `bay-station/power_bms.kicad_sch` in KiCad 10
  format while a concurrent edit was adding new sheets to the root file. No
  data was lost (verified via a reference-designator diff before
  committing), but it could have silently clobbered the newer edits if the
  stale window had been saved again afterward. Close/reload any open KiCad
  windows before doing further programmatic edits, and vice versa.
- The sibling project at `~/kicad-projects/wristband-alarm` (a *different*,
  unrelated wristband-alarm concept, also u-blox NINA-based) has its own
  long-standing uncommitted working-tree state -- don't touch it, don't
  assume its README reflects its actual working tree.

### In-flight work on GitHub (as of 2026-11-06)

Merged into `main` today: this Design Specifications section, the bay
station's power/regulation/programming-debug wiring pass, the decision not
to add an external wristband IMU (`docs/decisions.md` -- the DWM3001C's
built-in LIS2DH12 covers it), PR #9 (the bay station's missing I2C pull-ups,
R37-R39), and PR #8 (the full per-anchor DW3210 decoupling set, C40-C74 +
FB1-FB4 + R33-R36, from Qorvo's own reference design).

#8 and #9 both textually conflicted with the power-wiring pass on
`bay-station/connectivity.kicad_sch` and `uwb_array.kicad_sch` respectively,
because those files got reserialized to KiCad 10 format in between. Each was
hand-ported onto the reserialized files rather than text-merged -- see
`b7ab51f` and `4ef1099` for exactly what that involved and how it was
verified (balanced parens, no duplicate references, ERC recognizing every
new component with precisely the expected violation delta). This is the one
case where resolving a KiCad schematic conflict by hand was done carefully
and checked, not the norm -- `CONTRIBUTING.md`'s warning about silent
corruption from hand-resolving `.kicad_sch` conflicts still stands for
anything less thoroughly verified.

One PR needs a **team decision, not a merge**: **#7**
`feat/bay-station-wifi` adds an ESP32-C5 Wi-Fi co-processor and explicitly
reopens part of the 2026-09-19 "no WiFi" call (see `docs/decisions.md`,
"Bay-station Wi-Fi uplink"). Its own GPIO allocation table is marked
"PROPOSED, needs team sign-off" -- read that section before merging it.

### Not done yet (in rough next-up order)

1. **Replace the nRF9151 placeholder footprint** with Nordic's real land
   pattern, and re-verify every Nordic fact against the PDFs -- so far they
   were read only from Nordic's HTML pages (`docs/decisions.md`, Open).
2. **Import the BT840 and DWM3001C footprints** from vendor libraries
   (check pad naming), and resolve the U40, FB1-FB4, TCXO and SMA
   footprint items.
3. **Close the redesign's open risks** in `docs/decisions.md`: TCXO
   availability, GNSS LNA pre-filter, DW3210 exposed-pad net, LIS2DH
   lifecycle, the 8 MHz SPI budget, zero spare GPIOs.
4. **Array calibration procedure and fixture** -- the project's critical
   path; drafted in `docs/verification-plan.md`.
5. **Firmware**: the NCS skeletons exist but have never been built; the
   multi-instance DW3000 driver is the gating task (`firmware/README.md`).
6. Wire the wristband's placement-only sheets (independent of everything
   above).
7. PCB layout. The bay station's `.kicad_pcb` has its **4-layer
   controlled-impedance stackup** set from DW3000 Section 7.3.2 Figure 35
   (1.048mm finished) but is otherwise empty: 0 footprints, no outline.
   **The wristband's `.kicad_pcb` is not an empty stub** -- it already carries
   36 footprints, a routed board outline, and real DRC findings from the
   DWM3001C migration (PR #5); U3 (the DWM3001C) still has no footprint.

Done since the last update, for the record: the anchor rework onto four
discrete DW3210s, the decoupling audit (`docs/passives-reference.md`), the
two-USB-C item (deleted with the ESP32), the antenna-matching task (deleted
with the wristband's antenna sheet), the L1 and SW2 footprints, the
cold-charge THERM sizing, and the bay station's GPIO allocation.

## System overview

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

- **Wristband**: one Qorvo DWM3001C (UWB + nRF52833 MCU + antennas) +
  a compact BMS (MCP73831 charger + DW01A/FS8205 protection + AO3401A
  reverse-polarity protection). Design compromises favor small size and
  just enough battery life to get core functionality working. In the
  positioning scheme its job is simply to transmit -- one transmission
  yields all four measurements, deliberately, because the tag is the
  power-constrained side.
- **Bay station**: four UWB receivers in two roles (one center, three outer)
  on a single PCB sharing one TCXO, an nRF9151 host (LTE-M + GNSS) with a
  Fanstel BT840 bridging to a laptop over BLE, and a BMS designed for long
  runtime rather than small size (MCP73871 power-path charger + MAX17048 fuel
  gauge), since the bay station isn't worn. The four antennas sit on ~1-2 m coax runs to a rigid frame --
  that's what buys the baseline the bearing measurement needs.

There's no physical connector between the wristband and the bay station --
their only interface is the UWB radio link. The bay station's own antennas
are wired to it over SMA coax (CH5 at 6489.6 MHz is above U.FL's 6 GHz
rating). See `docs/system-overview.md` and `docs/positioning.md`.

## Design specifications

Quick-reference only -- full reasoning, error budgets, and datasheet
citations live in `docs/positioning.md` (RF/clock/mechanical) and
`docs/decisions.md` (every component/architecture call). Anything not listed
here as resolved is still an open decision; check there before assuming a
number is final.

**Performance target**
| | |
|---|---|
| Accuracy | 10-30 cm |
| Range | ~10 m |
| Baseline (A0-to-outer-antenna spacing) | ~1 m as built; frame size is the real limit, not cable loss |

**RF**
| | |
|---|---|
| UWB channel | Channel 5, 6489.6 MHz |
| UWB IC, bay station | 4x Qorvo DW3210 (QFN40, non-PDoA) -- U4=A0 center, U5-U7=A1-A3 outer |
| UWB IC, wristband | Qorvo DW3110 (WLCSP), inside the DWM3001C module |
| UWB connectors | SMA -- CH5 is above U.FL/W.FL/MMCX/MCX's 6 GHz rating and SMB's 4 GHz rating |
| Link budget | 86 dB available (CH5, 850 kbps, 1024-symbol preamble); ~17 dB margin at 10 m |
| Antennas (bay station) | Not yet selected -- candidates covering CH5: Taoglas UWC.01 / ILA.68 / UWCCP.01 |

**Clock (bay station array)**
| | |
|---|---|
| Reference | One 38.4 MHz TCXO -> 1:4 low-skew fan-out buffer -> all 4 DW3210 XTI pins |
| Coupling | 2200 pF AC-coupled into each XTI; 1 pF from each XTO to ground |
| TCXO spec | 0.8 V-VDD2 Vpp, -132 dBc/Hz @ 1 kHz, -145 dBc/Hz @ 10 kHz, 40-60% duty (DW3000 Datasheet Table 10) |
| TCXO + buffer part numbers | Rakon RPT1490LN + TI LMK1C1104 -- PROPOSED, TCXO availability open |

**Positioning architecture**
Hybrid two-way-ranging + TDoA, not symmetric multilateration -- see
`docs/positioning.md` for the full derivation.
| | |
|---|---|
| Center anchor (A0) | Two-way ranging with the wristband -> range |
| Outer anchors (A1-A3) | TDoA vs. A0 on the same tag transmission -> direction |
| System | 4 equations, 3 unknowns -- overdetermined by 1; use the residual as a quality metric |
| Mechanical | Rigid frame fixes geometry (no install-time survey); A0 offset 20-30 cm out of the A1-A3 plane to avoid a mirror ambiguity |
| Array calibration | Required, not optional (generic +/-6 cm spec is 3x too loose at this baseline); procedure/fixture still open |

**Power**
| | Wristband | Bay station |
|---|---|---|
| Regulator | TI TPS7A0233PDBVR LDO, 3.3V | TI TPS62A02PDDCR buck -> `+3V3`, 2A; TI TPS63802 buck-boost -> `+VBAT_LTE` 3.59 V, 2A |
| Load vs. rating | ~43 mA (4.6x headroom) | `+3V3` ~356 mA peak (~446 mA worst case); `+VBAT_LTE` 505 mA LTE TX subframe -- >= 4x headroom on both (`docs/decisions.md`) |
| Standby | ~2.7 uA | n/a -- BMS optimized for runtime, not size |

**Connectivity**
| | |
|---|---|
| Wristband <-> bay station | UWB only -- one tag transmission per exchange, no other radio link |
| Bay station -> laptop | Bluetooth LE via the BT840 bridge (NUS, framed relay, raw timestamps) -- primary path, no WiFi |
| Bay station -> network | LTE-M from the nRF9151, optional (station must work with no SIM); service still open |
| Georeferencing | nRF9151 GNSS (time-shared with LTE) + ST LIS3MDL magnetometer + ST LIS2DH accelerometer (bay station only; position + heading both required) |

**Cost** (one prototype pair, hobbyist qty-1 pricing -- see `docs/bom-cost.md`)
| | |
|---|---|
| Wristband | ~$67 |
| Bay station | ~$263 + unpriced rows (nRF9151, TCXO, ...) |
| Total | ~$330 + unpriced rows |

**Regulatory**
No FCC/CE certification -- university prototype, not sold or deployed as a
product. Revisit as a first-class schedule item if that ever changes.

**Toolchain**
| | |
|---|---|
| KiCad | 10.0.5 (files on disk still in 8.0 format) |
| MCUs | All Nordic -- nRF52833 (wristband, inside DWM3001C) / nRF9151 host + nRF52840 BLE bridge (bay station, the latter inside the Fanstel BT840) |
| Firmware SDK | nRF Connect SDK v3.4.x (LTS), all images; nRF9151 modem FW 2.0.4 |

## Repo layout

```
shared/                      # symbols/footprints/3D models used on BOTH boards (e.g. the UWB IC)
  symbols/                   # shared .kicad_sym library
  footprints/                # shared .pretty footprint library
  3dmodels/                  # shared .step/.wrl models
wristband/                   # KiCad project: the wearable tag
  wristband.kicad_pro/sch/pcb
  libs/                      # wristband-only symbols/footprints
bay-station/                 # KiCad project: the fixed 4-anchor station
  bay-station.kicad_pro/sch/pcb
  libs/                      # bay-station-only symbols/footprints
docs/
  positioning.md             # the ToF + TDoA scheme, error budget, clock architecture
  system-overview.md         # block diagram + RF/data interface between the boards
  decisions.md               # open + resolved component/architecture decisions log
  passives-reference.md      # every chip's reference-design passives, compiled per-chip
  bom-cost.md                # build cost estimate for one prototype pair
  net-contract.md            # bay-station cross-sheet net names
  verification-plan.md       # bay-station bring-up/test plan + test-point index
firmware/                    # NCS firmware (nRF9151 / BT840 / nRF52833) -- skeletons, never built
CLAUDE.md                    # working rules for Claude Code / other coding agents
CONTRIBUTING.md              # git workflow, sheet conventions, pre-push checks
```

Each board is its own KiCad project (KiCad doesn't support one project
spanning multiple PCBs), but both live in this one repo so shared parts,
docs, and history stay in one place. Each project's `fp-lib-table` /
`sym-lib-table` reference the `shared/` libraries via `${KIPRJMOD}` relative
paths, so this works regardless of where the repo is cloned -- no per-machine
setup needed.

## Toolchain

Files are currently in **KiCad 8.0** format, originally authored/verified
against KiCad 8.0.6. As of 2026-08-14 this machine has been upgraded to
**KiCad 10.0.5** (the actual current stable -- confirmed as the team's
standard, superseding an earlier, since-corrected plan to target KiCad 9.x).
All existing files were re-checked with
`kicad-cli` under 10.0.5 (`sch erc`/`pcb drc`) and open/parse cleanly with no
new issues -- opening a file in the newer GUI and re-saving is still a
one-way, zero-cost upgrade whenever the team wants to bump the file format
itself; nothing has been re-saved yet, so the files on disk are still 8.0
format.

Note for anyone else upgrading KiCad's major version: `kicad-cli` alone
won't auto-populate the new version's global symbol/footprint library table
(`~/Library/Preferences/kicad/<version>/sym-lib-table` /`fp-lib-table`) --
that normally happens the first time you launch the actual KiCad GUI and it
offers to migrate/create settings. If you only ever use `kicad-cli`
headlessly without opening the GUI first, you may see a wall of spurious
"library not included in configuration" ERC errors -- just launch KiCad.app
once (or copy the two `*-lib-table` files from
`.../KiCad.app/Contents/SharedSupport/template/`) to fix it.

## Using Claude Code (or another coding agent) on this project

**The working rules for agents live in [`CLAUDE.md`](CLAUDE.md)** -- Claude
Code picks that up automatically. This section is the human-readable version
of why those rules exist.

KiCad's file formats (`.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `.kicad_sym`,
`.kicad_mod`) are plain text (S-expression or JSON) -- an agent can read and
edit them directly like any other source file, no special MCP server or
plugin required. Everything in this repo so far was built that way. A few
things make it work reliably, several of them learned the hard way in this
repo's own history:

- **`kicad-cli` is the fast headless sanity check.** After any edit, run
  `kicad-cli sch erc <board>.kicad_sch` and `kicad-cli pcb drc
  <board>.kicad_pcb` before trusting a change.
  - **macOS**: a Homebrew install symlinks it onto `PATH` automatically
    (`/opt/homebrew/bin/kicad-cli`); otherwise it's inside the app bundle at
    `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
  - **Windows**: the official installer puts it on `PATH` automatically; if
    not, it's at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`.
  - **Linux**: on `PATH` automatically via most package managers (apt,
    dnf, etc.) or the official AppImage/flatpak.
- **Always run `kicad-cli` from a scratch/temp directory, never from
  inside this repo.** It writes `.rpt` report files to the current working
  directory as a side effect -- running it from inside a git repo (this
  one or any other) pollutes the working tree with stray files. This has
  actually happened once already, to an unrelated sibling project, from a
  leftover `cd`.
- **`kicad-cli` silently fails on `extends`-based symbols.** A cached
  schematic symbol using KiCad's `extends` mechanism (e.g. the default
  library's `AO3401A extends TP0610T`) makes `kicad-cli` fail to load the
  *entire file* and report it as empty (0 components, 0 ERC violations)
  instead of erroring loudly -- a suspiciously clean ERC run is a red flag,
  not necessarily good news. This repo works around it everywhere by
  embedding flattened, non-`extends` copies of any such symbols (see
  `docs/decisions.md` and the various `*_notes.md` files for examples).
- **Use an existing sheet/symbol/footprint as the format template before
  writing a new one.** Every file in this repo was built by reading a
  known-good file first -- either one already in this repo, or one of
  KiCad's own bundled default libraries -- and matching its exact
  structure, rather than freehand-authoring the s-expression format from
  memory. This repo uses literal tab characters for indentation, not
  spaces; match that.
- **Don't run scripted file edits at the same time as a live KiCad GUI
  session has the same project open.** A background GUI window doesn't
  know about changes made outside it, and saving from a stale window can
  silently overwrite newer edits -- this already caused one near-miss on
  the bay station board (see "Known gotchas" above). Close/reload any open
  KiCad windows before scripted edits, and vice versa. A lock file at
  `<board>/~<board>.kicad_pro.lck` means a GUI session currently has that
  project open.
- **Verify real datasheet facts (pinouts, voltage ratings, current draw)
  by actually fetching and reading the datasheet PDF**, not from memory or
  a search-result summary -- several real bugs/gaps in this repo were only
  caught this way (e.g. the wristband's missing voltage regulator, a
  part-number that doesn't actually exist, a mislabeled SOT-23-6 part).
- **pcbnew's Python bindings** are available for programmatic
  footprint/board work (generating a blank `.kicad_pcb`, loading a
  footprint to sanity-check its pad count, etc.) via KiCad's own bundled
  Python interpreter -- **not** your system Python, which won't have the
  `pcbnew` module installed:
  - **macOS**: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
  - **Windows**: typically `C:\Program Files\KiCad\10.0\bin\python.exe`
  - **Linux**: usually just your system `python3` if KiCad was installed via
    a package manager that wires up the `pcbnew` module for it; otherwise
    check your distro's KiCad packaging docs.

## Will this work on both Mac and Windows?

Yes, and this has actually been checked, not just assumed:

- No absolute Mac-specific paths are baked into any `.kicad_pro`/`.kicad_sch`/
  `.kicad_pcb`/library file (`git grep`-checked) -- all cross-file/library
  references use `${KIPRJMOD}`-relative paths, which KiCad resolves
  identically on every OS.
- No filenames in this repo use characters or reserved names that are
  illegal on Windows (`: * ? " < > |`, or `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/
  `LPT1-9`), and no path exceeds even a fraction of Windows' historical
  260-character path limit (longest path in this repo is 80 characters).
- All tracked files use consistent LF line endings, and `.gitattributes`
  normalizes this going forward so a Windows contributor's git config
  (which sometimes auto-converts line endings on checkout) can't silently
  turn KiCad files into CRLF and create noisy diffs or merge pain.

What differs by platform is purely the install step and a couple of tool
paths (both covered above/in Getting Started) -- KiCad itself, the file
formats, and this repo's structure are fully cross-platform.

## Contributing

See `CONTRIBUTING.md` for the git workflow (branching, hierarchical-sheet
conventions to avoid merge conflicts, pre-push checks).
