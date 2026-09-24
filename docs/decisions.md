# Decision log

Open calls first, resolved calls below with the reasoning, so we don't
relitigate them. Keep this updated as the team decides things.

## Open

- **Bay station uplink backend**: what protocol/service position data gets
  sent to.
- **Anchor placement / enclosure** for the bay station's 4 UWB anchors
  (fixed relative geometry matters for triangulation accuracy).
- **PCB layer count / stackup** -- *wristband decided, bay station still open.*
  `wristband/wristband.kicad_pcb` is now set to **4 copper layers** with a
  45 x 35 mm board outline on Edge.Cuts (2026-09-15). Intended stackup, noted
  on `Cmts.User` in the board file: F.Cu signal / In1.Cu solid GND plane /
  In2.Cu power / B.Cu signal — the solid In1.Cu reference under both the
  DWM3000 UWB section and the NINA-B400 BLE section is the reason for going
  to 4 layers. **Board size is a starting point, not a decision** — confirm
  against the real enclosure and strap geometry before layout. The bay
  station's layer count is still unset.
- **DWM3000 antenna keep-out area** (all 5 placements, both boards) --
  confirmed real requirement from the datasheet (Section 6.1/Figure 10): no
  metal above/below/beside the antenna within ~10mm for best RF performance.
  Nothing actionable until PCB layout starts on either board -- see
  `shared/README.md` for the full detail.
- **UWB antenna matching network values** -- *bay station only now.* The
  wristband no longer has any host-PCB RF trace to match: moving to
  NINA-B400 (on-module U.FL) removed the PCB-side U.FL (`J2`) and the
  DNP L/C network (`L1`/`C13`) entirely. u-blox additionally requires their
  U.FL reference design be followed to retain FCC/IC modular approval, so
  nothing should be added into that path. The bay station's UWB anchors are
  unaffected by this and still need their own tuning at bring-up.
- **Bay station: two USB-C connectors instead of one.** Building the
  programming/flashing sheet surfaced that the existing power-input USB-C
  (`power_bms.kicad_sch`, power-only, no D+/D-) can't also be used to flash
  the ESP32-S3 over native USB, so a second, data-capable USB-C was added on
  `programming_debug.kicad_sch` instead of consolidating into one connector.
  Revisit whether one connector should be swapped for a data-capable variant
  instead of running two.
- **Bay station L1 (buck converter inductor) footprint**: the specific part
  chosen (Coilcraft XGL3520-102MEC) has no matching footprint in KiCad's
  default libraries -- pick/verify a real footprint at BOM time (see
  `bay-station/regulation_notes.md`).

## Resolved

- **Wristband low-power clock (LFXO)**: Epson **FC-135** 32.768 kHz crystal
  (`Q13FC13500004`, LCSC C32346) plus 18 pF C0G load caps, on NINA-B400
  pins 2/3. Added 2026-09-15 to close a real gap: the NINA-B4 system
  integration manual (UBX-19052230 R13 §1.9) states an external crystal
  **shall** be used to reach the module's lowest sleep current, and the
  board had neither a crystal nor the grounded XL1/XL2 that Table 6 requires
  as the alternative. Load-cap value derived from Table 14 (CL 12.5 pF,
  Cpin 5 pF), not guessed. See `passives-reference.md`.
- **Wristband SOS/user button**: Panasonic **EVQPUA02K** SMD tactile switch
  (`SW1`) on GPIO_21, using the nRF52833's internal pull-up. Added
  2026-09-15 — a rescue locator with no way for the wearer to signal was a
  functional gap. Actuation force for gloved use is still worth confirming.
- **Wristband battery monitoring**: 1M/1M divider (`R11`/`R12`) plus a 100 nF
  SAADC reservoir (`C16`) into GPIO_23. Added 2026-09-15. Accepted tradeoff:
  ~2.1 uA continuous, which roughly doubles standby drain against the
  module's ~2.6 uA System-ON sleep figure — gate the divider with a FET if
  runtime later matters more than always-on reporting.
- **Wristband charge-status LED**: `D2` (Lite-On LTST-C191KGKT) + `R10` (1k)
  off the MCP73831 STAT pin. Added 2026-09-15; the part was documented in
  `components.csv` but had never been placed, leaving STAT floating.
- **Wristband USB VBUS ESD protection**: `D3` (onsemi ESD5B5.0ST1G, SOD-523)
  across VBUS at `J1`. Added 2026-09-15 — same part as the battery-line TVS
  `D1`, closing a gap both the analyzer (UC-002) and `components.csv` had
  already flagged as "not yet placed".
- **Wristband connectivity method**: sheets are connected with **global
  labels and no drawn wire segments**, matching the convention `power_bms`
  already used. All six sheets are now connected this way (2026-09-15).

- **Wristband MCU/radio**: u-blox **NINA-B400-00B** (NINA-B4 series, Nordic
  nRF52833, Bluetooth 5.1, 512 kB flash / 128 kB RAM, +8 dBm). Symbol added in
  `wristband/libs/` -- all 55 pins + EGP + EAGP verified against the real
  NINA-B40 data sheet UBX-19049405 R09 Table 6 and Figure 3.
  Datasheet: UBX-19049405-R09.
  - *Migrated from NINA-B111 (nRF52832) on 2026-09-15.* Note the B111 already
    had a Nordic part inside -- the upgrade is nRF52832 -> nRF52833: BLE 5.1
    with direction finding (which pairs naturally with this project's UWB
    ranging), 2x the RAM, IEEE 802.15.4, and native USB.
  - **B400 chosen over B401 and B406.** B400 puts a U.FL connector *on the
    module*, so the external antenna plugs straight in. That deleted the
    PCB-side U.FL receptacle (J2) and the L/C matching network (L1/C13) from
    `wristband/antenna.kicad_sch` -- retiring the project's only open
    RF-tuning risk (both were DNP pending network-analyzer work that is now
    unnecessary). B401 (RF pin) is smaller at 10.0 x 11.6 mm vs 10.0 x 15.0 mm
    but keeps that match network; B406's internal PCB trace antenna would
    detune against the wearer's body.
  - **Footprint is an open item.** NINA-B4 is pin/mechanically compatible with
    **NINA-B3, not NINA-B1** (data sheet sect. 1.2), so the existing 42-pad
    `NINA111-42` land pattern does *not* carry over. No official source exists:
    u-blox's own Eagle library (`ubloxLib.lbr`) ships only NINA111-42 /
    NINA112-42, and neither KiCad's bundled nor upstream `RF_Module` library
    has a NINA-B3/B4 part. `wristband:NINA-B400-55_PLACEHOLDER` is therefore a
    flagged placeholder -- body outline, pad count and rank arrangement are
    confirmed, individual pad X/Y are derived estimates. **Must be replaced
    before fabrication** -- see the footprint's own `descr` field.
  - **No power-design impact.** NINA-B4 abs-max VCC is 3.9 V, identical to
    NINA-B111, so the MCP1700 3.3 V LDO decision below stands unchanged. Budget
    moves from ~12 mA to 15.5 mA typ (TX @ +8 dBm); with DWM3000 that is
    ~70 mA against 250 mA, still ~3.5x headroom.
  - **SWD pinout is unchanged**: SWDCLK=11, SWDIO=15, RESET_N=19, SWO=8 on both
    B111 and B400, so the `programming_debug.kicad_sch` mapping carries over.
  - **Entire NINA-B400 entry superseded 2026-09-23** — `U3` was deleted when the
    wristband moved to the DWM3001C, whose own nRF52833 is now the host MCU.
    The LDO still stands but the ceiling is tighter (3.6 V, not 3.9 V) and the
    budget smaller (45 mA, not ~70 mA); the SWD pinout did finally move, to
    SWD_CLK=2, SWD_DIO=3, RESET=47, SWO=28. Kept as the historical record of
    the B111→B400 reasoning. See the UWB IC/module entry below.
- **UWB IC/module**: now **two different parts, one per board** (changed
  2026-09-23; the wristband and bay station previously shared DWM3000).
  - **Wristband: Qorvo DWM3001C** (1x, `U4`). A fully integrated module --
    DW3110 UWB transceiver + Nordic nRF52833 BLE MCU + ST LIS2DH12
    accelerometer + UWB antenna + Bluetooth chip antenna + 38.4 MHz crystal +
    power management, 48-pin castellated 19.13 x 27.1 x 3.2 mm. **This
    replaced the NINA-B400 + DWM3000 pair outright**: the module's own
    nRF52833 is the host, so `U3` was deleted. Because the DW3110↔nRF52833
    SPI is internal to the module, the board-level UWB SPI bus
    (`UWB_CS/CLK/MOSI/MISO`), the `UWB_IRQ`/`UWB_RSTn`/`UWB_WAKEUP` control
    lines, the GPIO5/6 SPI-mode straps (`R7`/`R8`), the IRQ pull-down (`R9`),
    the external 32.768 kHz LFXO (`Y1`/`C14`/`C15`) and the off-board antenna
    (`AE1`) all disappeared with it. Single supply **VDD 2.5–3.6 V**, 4.0 V
    abs max; worst-case **45 mA** (CH9 TX/RX). Symbol and footprint are
    wristband-only, in `wristband/libs/`, built from the real **Qorvo
    DWM3001C Data Sheet Rev B, May 2022** (Figure 1, Tables 2/4/5/9).
    Footprint is a flagged `DWM3001C_PLACEHOLDER` -- see below.
  - **Bay station: Qorvo/Decawave DWM3000** (4x, one per anchor, bare UWB
    transceiver module with no onboard host MCU, SPI host is the ESP32-S3).
    Unchanged. Stays in `shared/symbols/` even though only one board now uses
    it, since moving it would churn four placements for no benefit.
  - Note: an earlier pass of this doc and the initial library work briefly
    used the incorrect name "DWM3000C", which isn't a real Qorvo part number
    -- see `shared/README.md` for the full correction writeup. That writeup
    also originally rejected DWM3001C as redundant, which was true only while
    the NINA-B400 was still on the board.
  - Both footprints are flagged `_PLACEHOLDER`. DWM3000's has one unresolved
    land-pattern dimension. DWM3001C's has two: Figure 5's 17.77 mm side-column
    span back-derives to a **1.06375 mm** pitch across 17 pads, which is not a
    round number and is unlikely to be Qorvo's intent; and the bottom pad row's
    individual pad width is never dimensioned, while a "3.10" annotation implies
    it is offset right rather than centred. **Verify both before fab.**
- **Wristband 3.3V LDO**: **TI TPS7A0233PDBVR** (SOT-23-5), replacing
  Microchip MCP1700T-3302E/TT on 2026-09-23. The regulator is still required
  (battery reaches 4.2V, DWM3001C tops out at 3.6V operating / 4.0V abs max),
  but the MCP1700's 1.6uA typ / 4uA max quiescent current had become the
  largest single standby draw on the board -- more than the DWM3001C's own
  850nA sleep. TPS7A02 is 25nA typ / 46nA max at 25C, 3nA shut down, and also
  improves accuracy to +/-1.5% over temperature. Board standby ~4.3uA ->
  ~2.7uA. Verified against TI SBVS277C. Trade-offs accepted: 200mA rating
  instead of 250mA (still 4.4x the 45mA load), ~$0.78 instead of ~$0.16, and
  a 5-pin package with an EN input that must be tied high (TPS7A02 is disabled
  when EN floats; it cannot be GPIO-driven because the MCU it powers cannot
  enable its own supply). A buck converter was considered and rejected -- at
  45mA it trades a few points of efficiency for an inductor, higher Iq and
  switching noise next to a UWB receiver. **Open follow-up:** the 2MOhm
  R11/R12 battery-sense divider (~1.85uA) is now the dominant standby term.
- **Wristband BMS**: MCP73831 (LiPo linear charger) + DW01A/FS8205
  protection pair -- same proven pattern as the team's other wristband
  project (alarm-band). Symbols added to `wristband/libs/`; battery
  connector and USB-C charging receptacle reuse KiCad's own default
  libraries (no custom parts needed -- see `wristband/libs/components.csv`).
- **Bay station connectivity**: ESP32-S3-WROOM-1 module (built-in BLE +
  2.4GHz WiFi, single part instead of discrete BLE+WiFi ICs). Note: WiFi is
  2.4GHz only, not dual-band 5GHz -- revisit if that turns out to matter.
- **Bay station BMS**: MCP73871 (charge + power-path management, so the
  station can run continuously on external power while its battery
  tops off in the background) + MAX17048 fuel gauge (same part already
  proven on alarm-band).
- **Repo structure**: monorepo, two KiCad projects (`wristband/`,
  `bay-station/`) + a `shared/` library folder. Reason: KiCad has no native
  multi-board project, and a monorepo keeps shared parts/docs/history in one
  place for a small team.
- **Voltage regulation** (a gap found by checking real datasheets: NINA-B400
  abs-max VCC is 3.9V (same as the NINA-B111 it replaced), DWM3000 abs-max
  VDD3V3 is 4.0V, but a charged LiPo hits 4.2V -- both ICs were about to be fed straight off the unregulated
  battery/system rail with no margin against permanent damage):
  - Wristband: **Microchip MCP1700T-3302E/TT** LDO (fixed 3.3V, low-Iq),
    `wristband/regulation.kicad_sch`. Current budget: NINA-B400 (~15.5mA) +
    DWM3000 (~55mA) = ~70.5mA vs. the part's 250mA rating, ~3.5x headroom.
  - Bay station: **TI TPS62A02PDDCR** buck converter (2A, single-cell-Li-Ion
    input range), `bay-station/regulation.kicad_sch`. Current budget:
    ESP32-S3-WROOM-1 (~355mA peak TX) + 4x DWM3000 (~55mA each) = ~575mA
    vs. 2A rating, ~3.5x headroom.
  - Both sheets are placement-only (not wired) like everything else at this
    stage -- see each board's `regulation_notes.md`.
- **Wristband antenna**: **Abracon PRO-IS-237** -- physically the same patch
  antenna previously specified here as the *ProAnt InSide-2400* (+3.0 dBi,
  50 ohm, 27 x 12 mm triangular, 100 mm U.FL cable). ProAnt was acquired by
  Abracon and u-blox now lists the part under the Abracon PN, so **order under
  PRO-IS-237**. Re-verified for NINA-B4 against the real u-blox NINA-B4 series
  certification application note UBX-20037320 R05, Section 3.2: still
  pre-approved, with FCC, IC, RED, UKCA, MIC, NCC, KCC, ANATEL, ACMA and ICASA.
  u-blox's own note on the entry -- "should be attached to a plastic enclosure
  or part for best performance" -- is the same wearable-enclosure reasoning that
  drove the original pick off the NINA-B1 list, so the choice survives the
  migration intact. It now plugs directly into the NINA-B400's on-module U.FL;
  there is no PCB-side connector or match network. u-blox requires their U.FL
  reference design be followed to keep FCC/IC modular approval.
  (DWM3000 still needs no external antenna -- it has its own onboard ceramic
  antenna, confirmed in its datasheet.)
- **DWM3000 GPIO5/GPIO6 SPI-mode strapping**: both ICs' power-up sequence
  requires these sampled at boot (per Qorvo's own timing diagrams) --
  10k pull-downs added per instance (`wristband/radio_mcu.kicad_sch`;
  `bay-station/uwb_anchors.kicad_sch` x4, one set per anchor).
- **ESP32-S3-WROOM-1 boot-strapping + programming**: pull resistors on
  GPIO0/3/45/46 per Espressif's real hardware design guidelines, an EN
  RC-delay network, BOOT/RESET buttons, and a native-USB flashing interface
  -- `bay-station/programming_debug.kicad_sch`. Surfaced a real
  inconsistency in doing so -- see the "two USB-C connectors" open item
  above.
- **NINA-B400 programming**: standard 2x5 1.27mm ARM Cortex Debug SWD
  header, `wristband/programming_debug.kicad_sch`.
- **KiCad version**: team standardizes on **KiCad 10.0.5** (current stable;
  supersedes an earlier, since-corrected plan to target 9.x). Files on disk
  are still KiCad 8.0 format for now (nobody's re-saved them under 10 yet) --
  re-checked and confirmed clean under 10.0.5 via `kicad-cli` on 2026-08-14.
  See root `README.md`'s Toolchain section.
- **Passives audit against every chip's real reference design**: compiled
  in `docs/passives-reference.md`. Found and fixed one real gap (100k
  IRQ/GPIO8 pulldowns were missing on all 5 DWM3000 instances, per Qorvo's
  own Figure 11 -- added as R9 on the wristband, R25-R28 on the bay
  station). Also documented, not changed: DWM3000's placed decoupling caps
  exceed what Qorvo's own minimal application circuit shows (kept as
  reasonable conservative practice), and its GPIO5/6 external strap
  resistors are redundant with the chip's own internal default pulls (kept
  deliberately for tighter timing margin).
