# SC2 hardware notes

> Not a spec sheet. Wikipedia, iFixit, and reviews cover the published specs (TMR sticks, Hall-effect triggers, 4× LRA motors, 6-axis IMU, 18 IR LEDs, 8.39 Wh battery, ~35-hour rated life, $99). This doc collects the bits that were actually needed for the RE work plus a handful of components surfaced by firmware-string analysis that aren't in any public teardown (MPS MP2733 charger, ST LSM6DSV16X IMU, Olympus trackpad IC, SLG4L48185 GreenPAK, Zephyr RTOS, ARM GCC 14 toolchain).

## Chip identification

**Both Triton (controller) and Proteus (puck) use the Nordic nRF52833** (512 KB flash, 128 KB RAM, GPIO ports P0+P1, I2S, USB) — matching the [iFixit and PC Gamer teardowns](https://www.ifixit.com/Device/Steam_Controller_%282nd_Generation%29), which read the chip markings as nRF52833.

An earlier version of this repo claimed nRF52840, treating the Device-Tree nodes `gpio@50000300` (GPIO Port P1) and `i2s@40025000` (I2S) in the firmware rodata as nRF52840-exclusive. **That was wrong.** The nRF52833 also has a second GPIO port (P1) and I2S ([Nordic nRF52833 Product Specification](https://docs.nordicsemi.com/bundle/ps_nrf52833/page/keyfeatures_html5.html)), so those nodes don't distinguish the two parts; the features that would (QSPI, CryptoCell, 1 MB flash, 256 KB RAM) never appear in the firmware. Independent confirmation: the [`mwdmwd/sc26re`](https://github.com/mwdmwd/sc26re) firmware-reimplementation project builds and flashes for `nrf52833` (512 KB / 128 KB) and uses the BBC micro:bit v2 — also an nRF52833 — as a same-SoC development target. Our own stack-pointer reads (~96 KB into SRAM) fit the 128 KB part.

See [`docs/FIRMWARE_PROTOCOL.md`](FIRMWARE_PROTOCOL.md) §"Hardware inference" for the DT-address breakdown.

Both firmwares built with **ARM GCC 14 + newlib** on Jenkins CI, running **Zephyr v3.7.99** (Git `93ba569c5b31`) on top of **Nordic nRF Connect SDK v2.9.0** (Git `d93dcad627bd`).

## External I2C peripherals (Triton)

| Addr | Chip | Function |
|---|---|---|
| `0x10` | **Renesas/Dialog SLG4L48185** GreenPAK | Programmable mixed-signal IC, used as I2C-controlled GPIO expander (driver `gpio_greenpak`) |
| `0x2C` | **Olympus** (Valve-internal codename) | Capacitive trackpad controller for both pads. `mwdmwd/sc26re` models it as a 32-bit register-mapped capacitive touch IC (vendor `0x0488`, product `0xd0c1`) — likely a custom or relabeled part. |
| `0x4B` | **MPS MP2733** | USB-PD-capable battery charger with **integrated fuel-gauge**, BC1.2-compliant. `mwdmwd`'s `battery.c` reads state-of-charge directly from the MP2733's registers — there is no separate fuel-gauge IC. |
| `0x6A` | **ST LSM6DSV16X** | 6-axis IMU (gyro + accel) with **on-chip Smart Fusion Engine** producing quaternions. Released by ST in 2024. This chip is what fills the `sGyroQuat*` fields in `TritonMTUFull_t.imu` — the SDL3 driver doesn't compute the quaternions in software, it just reads them from the chip. |

Proteus (puck) has a much simpler I2C bus — only a single `ec-button-interface@50` at address `0x50` (small Embedded Controller for puck button readout). No IMU, no battery charger, no trackpads on the puck side.

## USB topology (Puck = `28DE:1304`)

7 interfaces — full table in [`HID_REPORT_FORMAT.md`](HID_REPORT_FORMAT.md):
- 2× CDC ACM (iface 0+1) — accessible to neither `deck` nor `root` due to SteamOS MAC policy; purpose TBD
- 5× HID (iface 2-6) — 4 controller slots + 1 status channel (iface 6 / hidraw13). Each paired controller occupies one slot. Puck supports up to 4 simultaneous controllers.

Slot ↔ hidraw mapping confirmed empirically by the `esb-controller@0..3` strings in PROTEUS_FW.

## Haptic output — actuator sides

Valve's output haptic reports (`0x80`–`0x85`) address actuators by a "side" byte. The mapping (per [iczero's dissector](https://github.com/iczero/steam-controller-stuff) and the `mwdmwd/sc26re` firmware) is:

| Side | Actuator |
|---|---|
| 0 | Left trackpad (TP_LEFT) |
| 1 | Right trackpad (TP_RIGHT) |
| 3 | Left internal LRA motor (INT_LEFT) |
| 4 | Right internal LRA motor (INT_RIGHT) |
| 2 / 5 | "Both" (TP_BOTH / INT_BOTH), depending on report |

Side numbering is **not** consistent across reports — the `0x81` pulse report swaps 0/1 (0 = TP_RIGHT, 1 = TP_LEFT) relative to the others. See [`HAPTICS.md`](HAPTICS.md) for per-report detail.

(An earlier version of this table, taken from SteamHapticsSinger, labelled these as "back grips" with side 2 "unmapped" — that was incorrect. The SC2's four haptic actuators are the two trackpads and two internal motors.)

## Firmware string analysis — components not in any teardown

Found in IBEX_FW / PROTEUS_FW rodata via `tools/analyze_fw.py` (see `FIRMWARE_PROTOCOL.md §"Hardware components"`):

| String | Component |
|---|---|
| `"MP2733"` | MPS MP2733 USB-PD battery charger IC |
| `"BC1.2 result callback"` | USB Battery Charging Spec 1.2 capable |
| `"Fuel gauge device is not ready"` | The MP2733's **integrated** fuel-gauge (not a separate IC — see I2C table above) |
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
