# Steam Controller 2 (Triton) — Hardware Notes Relevant to the RE Work

> Not a general spec sheet. Wikipedia, iFixit, and reviews cover the headline hardware specs — this doc only contains the parts that were *needed for the RE work*, plus the items we extracted from firmware-string analysis that aren't in any public teardown (MPS MP2733 charger, fuel-gauge IC, Zephyr RTOS, ARM GCC 14 toolchain, ESB slot strings). The chip-identification section reconciles iFixit's nRF52833 reading with our static analysis.

The headline specs (TMR sticks, Hall-effect triggers, 4× LRA motors, 6-axis IMU, 18 IR LEDs, 8.39 Wh battery, ~35-hour rated life, $99 launch price) are correct as published; we confirmed them but they aren't novel here.

## Chip identification

**Both Triton (controller) and Proteus (puck) use the Nordic nRF52840** — the largest nRF52-series variant (256 KB SRAM / 1 MB Flash, dual GPIO ports, I2S peripheral).

[iFixit and PC Gamer teardowns](https://www.ifixit.com/Device/Steam_Controller_%282nd_Generation%29) read the controller's chip markings as nRF52833 with hedged language ("appears to be"). Our firmware analysis disagrees: IBEX_FW and PROTEUS_FW both contain Zephyr Device-Tree node addresses for **`gpio@50000300` (GPIO Port P1, only present on nRF52840) and `i2s@40025000` (I2S, exclusive to nRF52840)**. The firmware reads/writes those exact register addresses — the silicon must have those peripherals or the device wouldn't boot. Treating firmware-DT evidence as authoritative over hedged chip-marking reads.

See [`docs/FIRMWARE_PROTOCOL.md`](FIRMWARE_PROTOCOL.md) §"Hardware inference" for the full DT-address breakdown.

Both firmwares built with **ARM GCC 14 + newlib** on Jenkins CI, running **Zephyr v3.7.99** (Git `93ba569c5b31`) on top of **Nordic nRF Connect SDK v2.9.0** (Git `d93dcad627bd`).

## External I2C peripherals (Triton)

| Addr | Chip | Function |
|---|---|---|
| `0x10` | **Renesas/Dialog SLG4L48185** GreenPAK | Programmable mixed-signal IC, used as I2C-controlled GPIO expander (driver `gpio_greenpak`) |
| `0x2C` | **Olympus** (Valve-internal codename — custom/relabeled) | Trackpad controller for both left + right pads |
| `0x4B` | **MPS MP2733** | USB-PD-capable battery charger + integrated fuel-gauge, BC1.2-compliant |
| `0x6A` | **ST LSM6DSV16X** | 6-axis IMU (gyro + accel) with **on-chip Smart Fusion Engine** producing quaternions. Released by ST in 2024. This chip is what fills the `sGyroQuat*` fields in `TritonMTUFull_t.imu` — the SDL3 driver doesn't compute the quaternions in software, it just reads them from the chip. |

Proteus (puck) has a much simpler I2C bus — only a single `ec-button-interface@50` at address `0x50` (small Embedded Controller for puck button readout). No IMU, no battery charger, no trackpads on the puck side.

## USB topology (Puck = `28DE:1304`)

7 interfaces — full table in [`HID_REPORT_FORMAT.md`](HID_REPORT_FORMAT.md):
- 2× CDC ACM (iface 0+1) — accessible to neither `deck` nor `root` due to SteamOS MAC policy; purpose TBD
- 5× HID (iface 2-6) — 4 controller slots + 1 status channel (iface 6 / hidraw13). Each paired controller occupies one slot. Puck supports up to 4 simultaneous controllers.

Slot ↔ hidraw mapping confirmed empirically by the `esb-controller@0..3` strings in PROTEUS_FW.

## Haptic output — actuator IDs

From `SteamHapticsSinger/main.cpp` (BSD-3-Clause), `0x83`-command actuator byte:

| ID | Position |
|---|---|
| 0 | Left back grip |
| 1 | Right back grip |
| 3 | Left front trackpad |
| 4 | Right front trackpad |
| **2** | Unmapped — possibly a reserved slot or 5th actuator; not investigated |

## Firmware string analysis — components not in any teardown

Found in IBEX_FW / PROTEUS_FW rodata via `tools/analyze_fw.py` (see `FIRMWARE_PROTOCOL.md §"Hardware components"`):

| String | Component |
|---|---|
| `"MP2733"` | MPS MP2733 USB-PD battery charger IC |
| `"BC1.2 result callback"` | USB Battery Charging Spec 1.2 capable |
| `"Fuel gauge device is not ready"` | Separate fuel-gauge IC (likely TI BQ27xxx or MPS) |
| `"cal/rgbw_w"`, `"cal/rgbw_b/g/r"` | RGBW LEDs with per-channel calibration |
| `"grip touch threshold failed to retrieve"` | Capacitive grip sensors (corresponds to HID bits `0x10000000` / `0x20000000` in the buttons field) |

Not visible in any teardown photo at time of writing.

## Sources

Canonical specs (use these first):
- [Wikipedia: Steam Controller (2nd gen)](https://en.wikipedia.org/wiki/Steam_Controller_(2nd_generation))
- [iFixit: Steam Controller (2nd Generation)](https://www.ifixit.com/Device/Steam_Controller_%282nd_Generation%29) — chip identification
- [GamersNexus review](https://gamersnexus.net/handheld-pcs-peripherals/valve-steam-controller-review-latency-benchmarks-battery-life) — latency, battery measurements, internal chip notes
- [PC Gamer teardown (2026)](https://www.pcgamer.com/hardware/game-pads/steam-controller-2026-review/)
- [PCGamingWiki: SC2 profile](https://www.pcgamingwiki.com/wiki/Controller:Steam_Controller_(2nd_generation))

Project-specific:
- [`HID_REPORT_FORMAT.md`](HID_REPORT_FORMAT.md) — observed reports + USB topology table
- [`FIRMWARE_PROTOCOL.md`](FIRMWARE_PROTOCOL.md) — codenames, full firmware-string analysis, attribute table
- [`METHODOLOGY.md`](METHODOLOGY.md) — concrete RE lessons we hit
