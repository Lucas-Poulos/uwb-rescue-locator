# Custom boards (Zephyr hardware model v2)

Out-of-tree board definitions for the bay station's two MCUs. Applications
find them by adding `firmware/` to `BOARD_ROOT` (and to `DTS_ROOT` for the
project bindings in `../dts/bindings/`) in their `CMakeLists.txt`, before
`find_package(Zephyr)`.

| Board | Target(s) | MCU |
|---|---|---|
| `uwbrl/bay_station_lte/` | `bay_station_lte/nrf9151` (secure-only, bring-up), `bay_station_lte/nrf9151/ns` (TF-M, production) | nRF9151 SiP |
| `uwbrl/bay_station_ble/` | `bay_station_ble/nrf52840` | Fanstel BT840 (nRF52840) |

Layout follows the Zephyr Board Porting Guide (mandatory `board.yml`,
`Kconfig.<board>`, `<board>_<qualifiers>.dts`) and is modelled file-for-file
on upstream `boards/nordic/nrf9151dk/` and `boards/nordic/nrf52840dk/`
(Zephyr `main`, read 2026-11-17). `vendor: others` is the Porting Guide's
fallback for vendors not in `vendor-prefixes.txt`; the subdirectory name
`uwbrl/` is free-form for out-of-tree boards.

**Re-diff against the pinned NCS release before first build.** Upstream
`main` is mid-migration on SoC include paths (`<nordic/...>` vs
`<arm/nordic/...>`) and these files copy whichever `main` used on that day.

## Pins: one file per MCU

- `bay_station_lte/bay_station_lte_pins.h`
- `bay_station_ble/bay_station_ble_pins.h`

Each `#define` is a `docs/net-contract.md` net set to `PIN_TBD`, with the
source document named (`bay-station/connectivity_notes.md`). Both headers
`#error` until a `*_PINS_ASSIGNED` flag is flipped, so the build cannot
silently succeed against guessed pins. Nothing else in the tree contains a
pin number.

## What has been checked

No NCS/Zephyr SDK is installed where this was written, so **nothing here has
been built with `west`**. What was checked: host `clang -E` + `dtc` over all
three `.dts` files against stub SoC nodes, with dummy pin numbers -- the trees
parse and every label resolves, and with the real (unassigned) headers both
stop at the `#error`. That proves syntax only, not that properties match the
real Nordic SoC dtsi or the bindings.
