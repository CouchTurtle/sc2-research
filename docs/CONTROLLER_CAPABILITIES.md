# Steam Controller 2 (Triton) — Hardware & Feature Inventory

> Research as of 2026-05-19. Codename "Triton" (per SDL3 source). Released 2026-05-04, $99.

## TL;DR

Symmetrical gamepad form factor with Steam-Deck DNA: **TMR sticks, Hall-effect triggers, two haptic trackpads, 4 LRA motors, capacitive grip sensors, 6-axis IMU, and 18 IR LEDs for Steam Frame tracking**. Three connectivity modes (wired USB-C, 2.4 GHz via puck dongle, Bluetooth). Valve-internal codename: **Triton**.

## Table of Contents

- [1. Input Hardware](#1-input-hardware)
- [2. Output Hardware](#2-output-hardware)
- [3. Connectivity](#3-connectivity)
- [4. Battery & Power](#4-battery--power)
- [5. HID Reports & Commands](#5-hid-reports--commands)
- [6. Body & Physical](#6-body--physical)
- [7. Quirks & Gotchas](#7-quirks--gotchas)
- [8. What the Controller Does NOT Have](#8-what-the-controller-does-not-have)
- [9. Open Questions](#9-open-questions)
- [10. Sources](#10-sources)

## 1. Input Hardware

Everything that writes data into the HID report.

### 1.1 Buttons (digital, all as bit-flags inside a uint32)

Confirmed from SDL3 source (`SDL_hidapi_steam_triton.c`, enum `TritonButtons`):

| Bit mask | Symbol | Description |
|---|---|---|
| `0x00000001` | `TRITON_LBUTTON_A` | A |
| `0x00000002` | `TRITON_LBUTTON_B` | B |
| `0x00000004` | `TRITON_LBUTTON_X` | X |
| `0x00000008` | `TRITON_LBUTTON_Y` | Y |
| `0x00000010` | `TRITON_HBUTTON_QAM` | Quick Access Menu |
| `0x00000020` | `TRITON_LBUTTON_R3` | Right Stick Click |
| `0x00000040` | `TRITON_LBUTTON_VIEW` | View (Select) |
| `0x00000080` | `TRITON_HBUTTON_R4` | Back Paddle R4 |
| `0x00000100` | `TRITON_LBUTTON_R5` | Back Paddle R5 |
| `0x00000200` | `TRITON_LBUTTON_R` | RB (Right Bumper) |
| `0x00000400` | `TRITON_LBUTTON_DPAD_DOWN` | D-Pad Down |
| `0x00000800` | `TRITON_LBUTTON_DPAD_RIGHT` | D-Pad Right |
| `0x00001000` | `TRITON_LBUTTON_DPAD_LEFT` | D-Pad Left |
| `0x00002000` | `TRITON_LBUTTON_DPAD_UP` | D-Pad Up |
| `0x00004000` | `TRITON_LBUTTON_MENU` | Menu (Start) |
| `0x00008000` | `TRITON_LBUTTON_L3` | Left Stick Click |
| `0x00010000` | `TRITON_LBUTTON_STEAM` | Steam Logo Button |
| `0x00020000` | `TRITON_HBUTTON_L4` | Back Paddle L4 |
| `0x00040000` | `TRITON_LBUTTON_L5` | Back Paddle L5 |
| `0x00080000` | `TRITON_LBUTTON_L` | LB (Left Bumper) |
| `0x00100000` | `TRITON_RIGHT_JOYSTICK_TOUCH` | Right Stick — Touch (capacitive) |
| `0x00200000` | `TRITON_RIGHT_TOUCHPAD_TOUCH` | Right Trackpad — Touch |
| `0x00400000` | `TRITON_RIGHT_TOUCHPAD_CLICK` | Right Trackpad — Click (haptic) |
| `0x00800000` | `TRITON_RIGHT_TRIGGER_CLICK` | Right Trigger Full-Click |
| `0x01000000` | `TRITON_LEFT_JOYSTICK_TOUCH` | Left Stick — Touch (capacitive) |
| `0x02000000` | `TRITON_LEFT_TOUCHPAD_TOUCH` | Left Trackpad — Touch |
| `0x04000000` | `TRITON_LEFT_TOUCHPAD_CLICK` | Left Trackpad — Click |
| `0x08000000` | `TRITON_LEFT_TRIGGER_CLICK` | Left Trigger Full-Click |
| `0x10000000` | `TRITON_RIGHT_GRIP_TOUCH` | Right Grip Sense (capacitive) |
| `0x20000000` | `TRITON_LEFT_GRIP_TOUCH` | Left Grip Sense (capacitive) |

**30 bit flags allocated**, the rest (up to bit 31) reserved/unused. The `HBUTTON` vs `LBUTTON` prefix is presumably a High/Low byte split (no semantic relevance).

### 1.2 Analog axes

| Field | Range | Source |
|---|---|---|
| `sLeftStickX`, `sLeftStickY` | signed int16 (−32768..32767) | TMR sensor (K-Silver JS13 family) |
| `sRightStickX`, `sRightStickY` | signed int16 | TMR sensor (K-Silver JS13 family) |
| `sTriggerLeft`, `sTriggerRight` | signed, SDL scales `×2 −32768` (= unsigned 16-bit input) | Hall-effect sensors |
| `sLeftPadX`, `sLeftPadY` | 0..65536 | 34.5 mm haptic trackpad |
| `sRightPadX`, `sRightPadY` | 0..65536 | 34.5 mm haptic trackpad |
| `sPressureLeft`, `sPressureRight` | SDL divides by 32768.0 → probably unsigned 16-bit | Pressure sensor below trackpad |

### 1.3 IMU (6-axis)

| Field | Description |
|---|---|
| `imu.timestamp` | Hardware timestamp |
| `imu.sGyroX/Y/Z` | 3-axis gyroscope |
| `imu.sAccelX/Y/Z` | 3-axis accelerometer |

**No magnetometer documented.** Nominal polling interval is 1 kHz per USB descriptor, real value is ~4 ms (250 Hz). SDL comment: *"Always 1kHz according to USB descriptor, but actually about 4 ms"*.

IMU can be switched via `SETTING_IMU_MODE`:
- `SETTING_GYRO_MODE_OFF`
- `SETTING_GYRO_MODE_SEND_RAW_ACCEL`
- `SETTING_GYRO_MODE_SEND_RAW_GYRO`

Two report variants exist: **`TritonMTUFull_t`** (with quaternion) and **`TritonMTUNoQuat_t`** (without). The controller does its own sensor fusion and exposes a quaternion — host doesn't need to compute it.

### 1.4 IR tracking (for Steam Frame VR)

- **18 IR LEDs** per controller, distributed across front, grip, and base
- Tracked by Steam Frame headset cameras (SLAM-style 6DoF)
- Activation reduces battery life
- Likely no direct HID output — read passively by the headset

## 2. Output Hardware

What we can control.

### 2.1 Actuators

**4× LRA (Linear Resonant Actuator) motors:**
- 2× under the trackpads (for click haptics & rumble)
- 2× in the grips (back rumble)

Decoded from SteamHapticsSinger `main.cpp` — actuator IDs in byte 1 of the `0x83` command: `{0, 1, 3, 4}` (value 2 unclear, possibly reserved). Mapping (without swap):
- 0 = Left Back Grip
- 1 = Right Back Grip
- 3 = Left Front Trackpad
- 4 = Right Front Trackpad
- 2 = ??? (open — possibly center/notification?)

### 2.2 Rumble watchdog

**Hardware safety timeout ~50 ms** — rumble stops automatically if not refreshed. SDL3 resends every 40 ms.

### 2.3 Lizard-mode watchdog

**Lizard mode is automatically re-enabled by the controller** if not active. Drivers must periodically refresh `SETTING_LIZARD_MODE = LIZARD_MODE_OFF` to keep it disabled.

## 3. Connectivity

| Mode | Latency (measured) | Notes |
|---|---|---|
| **Wired USB-C** | **19 ms** click-to-photon (σ=3.1 ms) | Lowest latency, no battery use |
| **Puck (2.4 GHz proprietary)** | **21.6 ms** | Range ~44.5 m line-of-sight |
| **Bluetooth** | **37.3 ms** | Higher latency, longer range |

### Puck specifics
- **VID/PID: 0x28DE / 0x1304**
- **5 HID interfaces** (all 5 exposed as `/dev/hidrawX` on Linux)
- **Puck holds up to 4 controllers**
- **Controller remembers 2 puck pairings**
- Doubles as magnetic USB-C charging dock

### Wired SC2
- **VID/PID: 0x28DE / 0x1302**

### Bluetooth
- Own report type: **`ID_TRITON_CONTROLLER_STATE_BLE`** (instead of the standard `ID_TRITON_CONTROLLER_STATE`)

## 4. Battery & Power

| Metric | Value |
|---|---|
| Capacity | 8.39 Wh Li-ion |
| Runtime (Valve claim) | 35+ hours |
| Runtime (GamersNexus test) | ~73 hours |
| Charge time (full) | 3 h 26 min |
| Peak charge power | 2.65 W |
| Charge states | `Discharging`, `Charging`, `ChargingDone` |

Battery status arrives via a separate report type: **`ID_TRITON_BATTERY_STATUS`** with `TritonBatteryStatus_t` structure.

## 5. HID Reports & Commands

What we see on hidraw.

### Input reports (Controller → Host)

| Report ID | Structure | When |
|---|---|---|
| `ID_TRITON_CONTROLLER_STATE` | `TritonMTUFull_t` / `TritonMTUNoQuat_t` | Normal over USB / puck |
| `ID_TRITON_CONTROLLER_STATE_BLE` | as above (likely more compact) | over Bluetooth |
| `ID_TRITON_BATTERY_STATUS` | `TritonBatteryStatus_t` | Battery update |
| `ID_TRITON_WIRELESS_STATUS` / `_X` | `TritonWirelessStatus_t` | Connect/disconnect |

### Output reports (Host → Controller)

| Report ID | Use |
|---|---|
| `ID_OUT_REPORT_HAPTIC_RUMBLE` | Standard rumble + haptics |
| (Feature-Report) `ID_SET_SETTINGS_VALUES` | Set configuration |

### Settings (via `ID_SET_SETTINGS_VALUES`)

| Setting | Values |
|---|---|
| `SETTING_LIZARD_MODE` | `LIZARD_MODE_OFF` (and implicitly ON) |
| `SETTING_IMU_MODE` | `OFF`, `SEND_RAW_ACCEL`, `SEND_RAW_GYRO` |

## 6. Body & Physical

| Spec | Value |
|---|---|
| Dimensions | 111 × 159 × 57 mm (4.4 × 6.3 × 2.2 in) |
| Weight | 292 g (10.3 oz) |
| Screws | Non-security Torx (T6 external, T5 internal) |
| Construction | No clips, no glue |
| TMR sticks | **soldered** (not socketed / not user-replaceable) |

## 7. Quirks & Gotchas

Critical for RE work:

1. **Lizard-mode watchdog**: Controller automatically re-enables mouse/keyboard emulation. To get raw gamepad data, explicitly disable Lizard mode and refresh the setting periodically.
2. **Rumble timeout 50 ms**: Rumble commands must be repeated every ~40 ms or they stop.
3. **Note-Off before Note-On** (SteamHapticsSinger finding): Consecutive haptic "notes" without a stop in between can drive the controller into drift **or, on back-rumble actuators, reboot the controller**.
4. **Polling mismatch**: USB descriptor says 1 kHz, real value is ~4 ms (250 Hz). Plan for 250 Hz when writing timing-critical code.
5. **5 hidraw interfaces on the puck**: not all of them are the gamepad interface. Steam grabs probably only 1-2 of them exclusively (contrary to early assumption that all 5 were blocked).
6. **TritonMTUFull vs NoQuat**: two report layouts exist. We need to clarify which is active by default and how/whether to switch.
7. **Actuator ID 2 missing** in the SteamHapticsSinger mapping (they use 0, 1, 3, 4) — either an unused slot or a 5th actuator not yet discovered. Watch for it in the status report.

## 8. What the Controller Does NOT Have

For clarity:

- **No magnetometer** documented (6-axis IMU only)
- **No mechanical trackpad clicks** — the "click" is purely haptic via LRA
- **No replaceable sticks** — TMR is soldered
- **No display** (unlike the Steam Deck)
- **No buttons on the grip surfaces** other than the 4 paddles (L4/L5/R4/R5)
- **No RGB lighting** (only functional LEDs for status / Steam Frame IR)

## 9. Open Questions

1. **Which of the 5 hidraw interfaces is which?** (mouse, keyboard, gamepad, Steam vendor, ???)
2. **Which report type is the default?** Full with quaternion, or NoQuat?
3. **How do we switch between Quat / NoQuat?** (Settings Feature-Report?)
4. **What does `ID_TRITON_WIRELESS_STATUS_X`** (the "_X" variant) send — alternate format? Multi-controller info?
5. **Actuator ID 2:** used or gap?
6. **Trackpad pressure vs `TRITON_*_TOUCHPAD_CLICK` bit**: is Click the threshold crossing of pressure, or a separate sensor?
7. **Pairing protocol Puck ↔ Controller**: how is pairing done? Reverse engineering helps for an own puck replacement.
8. **IR-LED timing**: synced with camera frames? Controllable?

## 10. Sources

### Primary (technical)
- [SDL3 SDL_hidapi_steam_triton.c (raw)](https://raw.githubusercontent.com/libsdl-org/SDL/main/src/joystick/hidapi/SDL_hidapi_steam_triton.c) — official HID code from Valve via SDL3
- [SDL SDL_hidapi.h header](https://github.com/libsdl-org/SDL/blob/main/include/SDL3/SDL_hidapi.h)
- [SteamHapticsSinger GitHub](https://github.com/CrazyCritic89/SteamHapticsSinger) — output RE reference, BSD-3-Clause
- [SDL Discourse: Triton copyright fix](https://discourse.libsdl.org/t/sdl-fixed-copyright-on-sdl-hidapi-steam-triton-c/67600)

### Secondary (specs & reviews)
- [Wikipedia: Steam Controller (2nd gen)](https://en.wikipedia.org/wiki/Steam_Controller_(2nd_generation))
- [Wikipedia: Steam Frame](https://en.wikipedia.org/wiki/Steam_Frame) — controller-tracking context
- [GamersNexus latency/battery review](https://gamersnexus.net/handheld-pcs-peripherals/valve-steam-controller-review-latency-benchmarks-battery-life)
- [PC Gamer teardown](https://www.pcgamer.com/hardware/game-pads/steam-controller-teardown-simple-to-open-easy-to-fix/)
- [PC Gamer review (2026)](https://www.pcgamer.com/hardware/game-pads/steam-controller-2026-review/)
- [HLPlanet: TMR sticks soldered](https://www.hlplanet.com/steam-controller-2026/)
- [PCGamingWiki: SC2 controller profile](https://www.pcgamingwiki.com/wiki/Controller:Steam_Controller_(2nd_generation))
- [Tom's Hardware: Valve dev interview](https://www.tomshardware.com/peripherals/controllers-gamepads/valve-steam-controller-developer-interview)
- [9to5Linux release coverage](https://9to5linux.com/valve-officially-releases-new-steam-controller-with-35-hour-battery-grip-sense)
- [Geeky Gadgets: Grip Sense feature](https://www.geeky-gadgets.com/steam-controller-features-explained/)
- [PC Gamer: Grip Sense origin](https://www.pcgamer.com/hardware/controllers/how-gyro-support-was-added-into-the-new-steam-controller-is-a-typical-valve-story/)
- [Aftermath: Living-room PC use case](https://aftermath.site/steam-controller-review-living-room-pc/)
- [Automaton: Dev interview](https://automaton-media.com/en/interviews/spending-time-getting-comfy-with-the-steam-controllers-advanced-inputs-can-yield-drastic-performance-improvements-compared-to-traditional-stick-only-devices/)

### Community
- [GitHub: ValveSoftware/steam-for-linux Issue #13185](https://github.com/ValveSoftware/steam-for-linux/issues/13185) — Linux setup details
- [SteamHapticsSinger Discord](https://discord.gg/TWpvAxX5GW) — community hub
