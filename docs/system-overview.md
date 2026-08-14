# System overview

## Concept

A worn **wristband** tag is located in 3D space by a fixed **bay station**
using ultra-wideband (UWB) ranging from four anchor points (multilateration /
TDoA-style positioning). The bay station uploads position data to the
internet. Intended use: a safety/rescue tracking system.

## Boards

| | Wristband | Bay Station |
|---|---|---|
| Role | Worn tag | Fixed reference station |
| UWB | 1x UWB IC/module (TBD) | 4x UWB IC (one per anchor) |
| MCU/radio | u-blox NINA-B1 (confirmed) | ESP32 or discrete BLE + dual-band WiFi IC (TBD) |
| Power | Single-cell battery + BMS, sized for just enough runtime -- core function takes priority over battery life | Battery + BMS optimized for longevity, not size |
| Connectivity to internet | None (talks only to the bay station over UWB) | WiFi and/or BLE/cellular uplink (TBD) |

## Interface between the boards

There is **no physical connector** between the wristband and the bay
station -- the only link is the UWB radio (ranging + whatever small data
payload rides along with it, e.g. a tag ID). Once the UWB IC/module and
ranging protocol are chosen, document here:

- UWB channel, PRF, data rate
- Ranging scheme (e.g. two-way ranging vs. TDoA) and update rate
- Tag ID / payload format, if any data rides on top of ranging
- Anchor placement assumptions the triangulation math depends on

## Bay station -> internet

Once the connectivity part is chosen, document here: uplink type (WiFi
vs. BLE-to-phone vs. cellular), backend protocol (e.g. MQTT/HTTP), and
what's actually sent (raw ranges vs. computed position).

## Open decisions

See `decisions.md`.
