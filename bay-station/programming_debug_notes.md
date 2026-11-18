# programming_debug.kicad_sch -- design notes

Hierarchical sub-sheet "Programming / Debug" (sheet-symbol uuid
`883ff08c-ad9f-4863-b9db-49772b53748e`). Rebuilt 2026-11-17 for the nRF9151
host redesign: two SWD targets (nRF9151 host, BT840 BLE bridge), a debug
UART header, and three buttons. Paper size raised A4 -> A3 to keep it
readable. Nets follow `docs/net-contract.md` Sec 5-6.

## Sources

- Tag-Connect **TC2030-CTX** datasheet
  (`https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/TC2030-CTX_1.pdf`),
  "Connections" table: 10-pin Cortex 1 VCC, 2 SWDIO/TMS, 3 GND, 4 SWCLK/TCK,
  5 GND, 6 SWO/TDO, 7 NC/RTCK, 8 NC/TDI, 9 GNDDetect, 10 nRESET; TC2030 6-pin
  1 VCC, 2 SWDIO, 3 nRESET, 4 SWCLK, 5 GND (also GNDDetect), 6 SWO. KiCad's
  `Connector:Conn_ARM_JTAG_SWD_10` and `Connector:Conn_ARM_SWD_TagConnect_TC2030`
  symbols match these pin-for-pin.
- Nordic **nRF9151 Hardware Design Guidelines** (nwp_056), pages *nRESET*,
  *nRESET circuit example*, *ENABLE* -- HTML on docs.nordicsemi.com (PDF
  blocked by a Cloudflare challenge; no revision number available).
- Omron **B3U** catalogue (`https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3u.pdf`):
  B3U-1000P = top-actuated, without ground terminal, 1.5 N, tape/reel.

## Parts

| Ref | Part | Footprint | Nets / notes |
|---|---|---|---|
| J3 | ARM Cortex 10-pin 1.27 mm (Samtec FTSH-105 style) | `Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical` | **nRF9151.** 1 `+3V3` (VTref = nRF9151 `VDD_GPIO`), 2 `SWDIO_MCU`, 4 `SWDCLK_MCU`, 10 -> `RST_MCU_DBG` -> R313 -> `RESET_MCU_N`, 3/5/9 GND, 6/7/8 NC. Existing part, re-wired. |
| J34 | Tag-Connect TC2030-NL pads, **DNP** | `Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical` | nRF9151 alternate: 1 `+3V3`, 2 `SWDIO_MCU`, 3 `RST_MCU_DBG`, 4 `SWDCLK_MCU`, 5 GND, 6 NC. "NL" = no-legs footprint (no retaining-clip holes). |
| R313 | 1k 0603 | R_0603 | Series between every nRF9151 reset source (J3.10, J34.3, SW2) and `RESET_MCU_N`. |
| SW2 | Omron B3U-1000P | `Button_Switch_SMD:SW_SPST_B3U-1000P` | nRF9151 reset: `RST_MCU_DBG` to GND. **Footprint gap closed** (decisions.md Open). |
| J32 | ARM Cortex 10-pin 1.27 mm | as J3 | **BT840.** 1 `+3V3`, 2 `SWDIO_BLE`, 4 `SWDCLK_BLE`, 10 `RESET_BLE_N`, 3/5/9 GND, 6/7/8 NC. |
| J35 | TC2030-NL pads, **DNP** | as J34 | BT840 alternate, same pin map with `*_BLE` nets and `RESET_BLE_N`. |
| SW11 | Omron B3U-1000P | as SW2 | BT840 reset: `RESET_BLE_N` to GND. |
| J33 | 1x4 2.54 mm header | `Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical` | Debug UART: 1 GND, 2 `DBG_UART_TX` (nRF9151 TX -> cable RXD), 3 `DBG_UART_RX` (cable TXD -> nRF9151 RX), 4 `DBG_VREF`. |
| R314 | 0R 0603, **DNP** | R_0603 | `DBG_VREF` -> `+3V3`. |
| SW12 | Omron B3U-1000P | as SW2 | `BTN_USER` to GND, active low. |
| R315 | 10k, **DNP** | R_0603 | `BTN_USER` external pull-up to `+3V3`. |
| C304 | 100 nF, **DNP** | C_0603 | `BTN_USER` debounce (1 ms with R315). |

`SWO` (Cortex pin 6, TC2030 pin 6) is left unconnected on both targets:
the net contract has no SWO net. If trace output is wanted later, it is one
GPIO on each chip plus one label here.

## nRF9151 reset -- what Nordic actually says

From HDG *nRESET*: "The nRESET pin has a 13 kOhm internal pull-up resistor
that is always on", "connected to the nRF9151 internal voltage of 2.2 V";
"**External pull-up is not allowed in the nRESET pin.**"; "It is recommended
to add a bypass capacitor and series resistor in the range of 1 kOhm to the
nRESET routing"; "Place bypass capacitor ... close to the nRESET pin";
"Keep the nRESET pin low for at least 5 us"; reset is on the falling edge.
From *nRESET circuit example*: the series resistor sits between the SWD
tool and the pin, limits leakage caused by the tool's higher I/O voltage
(the pin's ESD diode conducts from ~2.8 V), and the pin must still reach
< 0.66 V (0.3 x 2.2 V).

Here: R313 = 1k on this sheet; low level = 2.2 V x 1k/(13k + 1k) = 0.16 V.
**The bypass capacitor must be at the nRF9151 pin on
`connectivity.kicad_sch`** (value per Nordic's reference schematic), and
nothing anywhere may pull `RESET_MCU_N` up -- that includes test-point
fixtures and any "helpful" 10k on another sheet. Do not add a second 1k at
the pin: two in series still work (2k -> 0.29 V) but it is redundant.

The HDG reset example's "always connected" variant (for a host MCU that
drives nRESET in normal operation) inverts the logic through a transistor.
Not needed: nothing on this board drives the nRF9151's reset except the
debugger and SW2, both through R313.

ENABLE timing (HDG *ENABLE*): "The start delay for Serial Wire Debug (SWD)
access is in the range of 100-500 ms from the time the ENABLE pin is pulled
high" -- configure the debugger with a connect-under-reset or a delay.

## BT840 reset

`RESET_BLE_N` goes straight to the BT840 (nRF52840 P0.18/nRESET) with no
series part. On the nRF52840 P0.18 acts as reset only after UICR.PSELRESET
is programmed (Zephyr `CONFIG_GPIO_AS_PINRESET`); until then SW11 and J32
pin 10 do nothing and the debugger must use a soft reset. This, and the
nRF52840's internal pull-up on that pin, were **not re-verified** in this
pass (nRF52840 PS PDF blocked by Cloudflare). The nRF9151 also drives
`RESET_BLE_N` (net contract): that GPIO must be configured open-drain.

## Debug UART

3.3 V logic (the nRF9151 `VDD_GPIO` rail). Compatible with any 3.3 V-logic
USB-UART cable -- connect GND, RXD, TXD only. Pin 4 (`DBG_VREF`) is
deliberately floating unless R314 is fitted, because common "3V3" cables
such as FTDI's TTL-232R-3V3 still put 5 V on their VCC wire. No USB-UART
bridge IC footprint was added: the board's USB-C (J2) is power-only, so a
bridge would also need a data-capable connector -- not trivial.

## Reference designators

J3, SW2 (existing); J32-J35, R313-R315, C304, SW11, SW12 (added 2026-11-17,
power block).

## Open items

- nRF9151 nRESET bypass-capacitor value and placement: connectivity sheet.
- nRF52840 PSELRESET / internal pull-up: verify against the nRF52840 PS.
- Cortex header part number (a Samtec FTSH-105-series part, the style the
  Tag-Connect datasheet names, or a keyed equivalent) to be picked and
  verified at BOM time; the KiCad footprint is the
  unshrouded THT 2x05.

## History: ESP32-S3-WROOM-1 boot-strapping, buttons, and flashing interface -- HISTORICAL

> **All of the circuitry in this section has been deleted from the schematic.**
> The BT840 programs over SWD, so the boot straps, the EN RC delay, the BOOT
> button and the data-capable USB-C are all gone -- which also resolved the
> two-USB-C open item. (The BT840-era sheet that replaced it was itself
> rebuilt on 2026-11-17 -- see the top of this file.) Kept below as a record
> of why each part was there.

#### Boot-strapping pull resistors

Per the real Espressif ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8 (already
cited above), Section 4 "Boot Configurations" and Table 4-1 "Default
Configuration of Strapping Pins":

| Ref | Pin (U3) | Direction | Value | Why |
|---|---|---|---|---|
| R18 | GPIO0 (pin 27) | pull-up to `+3V3_SYS` | 10k | GPIO0=1 selects SPI Boot (normal boot) per Table 4-3 "Chip Boot Mode Control". Default strap state is already weak-pull-up (Table 4-1, ~45k per Table 6-3's `RPU`), but the datasheet's own guidance ("It is recommended to place a pull-up resistor at the GPIO0 pin") is followed to make it explicit/robust. |
| R19 | GPIO3 (pin 15) | pull-down to GND | 10k | Section 4.4 "JTAG Signal Source Control" states verbatim: "This pin does not have any internal pull resistors and the strapping value must be controlled by the external circuit that cannot be in a high impedance state." Default eFuse JTAG-source config (Table 4-5, all-zero) ignores GPIO3 for source selection, so the pull *direction* isn't functionally critical yet, but an external pull is required by the datasheet's own text regardless of eFuse state. |
| R20 | GPIO45 (pin 26) | pull-down to GND | 10k | Table 4-4 "VDD_SPI Voltage Control": GPIO45=0 selects the 3.3V VDD3P3_RTC-derived SPI-flash voltage (matching this module's standard 3.3V-flash variant, not the `-N16R16VA` 1.8V variant). Matches GPIO45's own default weak-pull-down (Table 4-1), made explicit. |
| R21 | GPIO46 (pin 16) | pull-down to GND | 10k | Table 4-1 default is weak-pull-down; Espressif explicitly states the combination "GPIO46=1 with GPIO0=0 is invalid and may trigger unexpected behavior" -- pulling GPIO46 down guarantees a valid boot-mode strap combination alongside R18/SW1. |
| R22 + C23 | EN (pin 3) | RC delay: 10k pull-up to `+3V3_SYS` + 1uF to GND | 10k / 1uF | Not a strapping pin, but Espressif's real **ESP32-S3 Hardware Design Guidelines** (`docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html`, the "Schematic Checklist" section, distinct from the module datasheet) states verbatim: "The recommended setting for the RC delay circuit is usually R = 10 kOhm and C = 1 uF." |

#### Buttons

- **SW1 (BOOT):** momentary switch from GPIO0 to GND. Pulling GPIO0 low at
  reset enters Joint Download Boot mode (Table 4-3) for flashing -- standard
  practice on essentially every ESP32-S3 dev/breakout board.
- **SW2 (RESET):** momentary switch from EN to GND, alongside the R22/C23 RC
  delay -- standard manual-reset practice.

Both use KiCad's default `Switch:SW_Push` (a real, generic, 2-pin part already
in KiCad's bundled `Switch.kicad_sym`) -- footprint left blank, pick an exact
tactile-switch PN (e.g. Panasonic EVQ-PUJ or C&K PTS645-series) at BOM time,
matching this board's existing convention for generic connectors/passives
(see `libs/components.csv`).

#### Flashing/programming interface decision: native USB, with a caveat

**Chosen: native USB via the ESP32-S3's built-in USB-OTG peripheral**, not a
separate UART-to-USB bridge IC (e.g. CH340/CP2102). Reasoning, backed by the
real datasheet:

- Espressif ESP32-S3-WROOM-1 Datasheet v1.8, Section 5.2.1.7 "USB 2.0 OTG
  Full-Speed Interface" and 5.2.1.8 "USB Serial/JTAG Controller": the chip has
  a full-speed USB 2.0 OTG peripheral *and* a separate USB-Serial/JTAG
  controller with CDC-ACM (virtual serial port) emulation built in --
  "Internal PHY, so no or very few external components needed to connect to a
  host computer" and "CDC-ACM supports host controllable chip reset and entry
  into download mode."
- Table 4-3 "Chip Boot Mode Control" explicitly lists "USB-Serial-JTAG
  Download Boot" and "USB-OTG Download Boot" as supported Joint Download Boot
  methods -- flashing over native USB is a first-class, Espressif-supported
  path, not a hack.
- No extra bridge IC is needed, saving part count/cost/board area on a board
  that already has USB-C connectors for power.

**The caveat (a real finding, not glossed over):** the board's *existing*
USB-C receptacle (`J2` on `power_bms.kicad_sch`) is
`Connector:USB_C_Receptacle_PowerOnly_6P` -- **it has no D+/D- pins at all**,
so it physically cannot carry the native-USB data lines (U3's `USB_D-`/`USB_D+`
pins, pins 13/14 on `connectivity.kicad_sch`). Since `power_bms.kicad_sch` is
explicitly out of scope for this task (must not be edited), this sheet places
a **second, dedicated data-capable USB-C receptacle**:

| Ref | Part | Notes |
|---|---|---|
| J3 | `Connector:USB_C_Receptacle_USB2.0_14P` | Real KiCad-default part with D+/D- pins (A6/A7/B6/B7). Intended to carry U3's native USB (D+/D- to U3 pins 14/13) for programming/debug. |
| R23 | 5.1k, J3 CC1 to GND | Standard USB-C UFP-device pulldown, matching the identical R6/R7 convention already used for J2 on `power_bms.kicad_sch`. |
| R24 | 5.1k, J3 CC2 to GND | See R23. |

**Open concern, flagged rather than fixed:** this leaves the board with *two*
USB-C connectors (J2 for power-only, J3 for programming/debug) instead of one
combined connector. A future hardware revision could swap J2 for a
power+data-capable USB-C receptacle (e.g.
`Connector:USB_C_Receptacle_USB2.0_16P`) to consolidate to a single connector
and drop J3/R23/R24 entirely -- not done here since `power_bms.kicad_sch`
cannot be touched in this pass.
