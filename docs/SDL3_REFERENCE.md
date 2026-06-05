# SDL3 Public Reference — Everything Triton-Related

A consolidated reference of what SDL3's open-source code publicly says about the Steam Controller 2 ("Triton") and its dongles. Everything here is in the public Valve commit `1998b6504` (Sam Lantinga, Nov 12 2025) and the longer-standing shared headers from Valve.

Cited from a fresh clone of [`libsdl-org/SDL`](https://github.com/libsdl-org/SDL) `main`, May 2026.

If something in this doc surprises you, you can verify it yourself by `grep`ing the SDL repo. Several of our own earlier "first publicly documented" claims turned out to be in here — this reference file is the cross-check so we don't make that mistake again.

## Files of interest

| File | What it contains |
|---|---|
| `src/joystick/hidapi/SDL_hidapi_steam_triton.c` | 627-line driver. Polling loop, IMU axis swizzle, scaling, rumble output, Lizard-mode refresh. |
| `src/joystick/hidapi/steam/controller_structs.h` | 667 lines, `#pragma pack(1)`. Triton-specific input/output structs, report IDs, MTU layouts, battery+wireless status structs, output haptic message types. |
| `src/joystick/hidapi/steam/controller_constants.h` | 588 lines. Shared (SC1+Deck+Triton) constants: 80+ settings IDs, 60+ feature-report IDs, attribute and audio enums. |
| `src/joystick/usb_ids.h` | The `USB_PRODUCT_VALVE_STEAM_{PROTEUS,NEREID}_DONGLE` defines. |
| `src/joystick/controller_list.h` | Maps `28DE:1302..1305` to `k_eControllerType_SteamControllerTriton`. |

## All Triton input report IDs (`ETritonReportIDTypes`, `controller_structs.h:553`)

```c
enum ETritonReportIDTypes
{
    ID_TRITON_CONTROLLER_STATE     = 0x42,
    ID_TRITON_BATTERY_STATUS       = 0x43,
    ID_TRITON_CONTROLLER_STATE_BLE = 0x45,
    ID_TRITON_WIRELESS_STATUS_X    = 0x46,
    ID_TRITON_WIRELESS_STATUS      = 0x79,
};
```

| ID | SDL3 name | Payload struct | Total bytes (incl. ID) |
|---|---|---|---|
| `0x42` | `CONTROLLER_STATE` | `TritonMTUFull_t` or `TritonMTUNoQuat_t` (driver parses NoQuat) | 54 (Full) or 46 (NoQuat) |
| `0x43` | `BATTERY_STATUS` | `TritonBatteryStatus_t` (14 bytes) | 15 |
| `0x45` | `CONTROLLER_STATE_BLE` | same MTU structs, BLE-routed | 54 / 46 |
| `0x46` | `WIRELESS_STATUS_X` | `TritonWirelessStatus_t` (1 byte) | 2 |
| `0x79` | `WIRELESS_STATUS` | `TritonWirelessStatus_t` | 2 |

Reports in the HID descriptor that are **not** in this enum:
- `0x40`, `0x41` (Lizard-mode mouse/keyboard) — standard HID boot-protocol, suppressed when SDL3 is in control
- `0x44` (6 B) — present in descriptor, never observed; SDL3 doesn't handle it
- `0x7b` (13 B) — observed at ~2 Hz, not in SDL3 enum, **genuinely undocumented** (we hypothesize a Proteus-side puck status report)

## All Triton output report IDs (`ValveTritonOutReportMessageIDs`, `controller_structs.h:225`)

```c
typedef enum
{
    ID_OUT_REPORT_HAPTIC_RUMBLE   = 0x80,
    ID_OUT_REPORT_HAPTIC_PULSE    = 0x81,
    ID_OUT_REPORT_HAPTIC_COMMAND  = 0x82,
    ID_OUT_REPORT_HAPTIC_LFO_TONE = 0x83,
    ID_OUT_REPORT_HAPTIC_LOG_SWEEP= 0x84,
    ID_OUT_REPORT_HAPTIC_SCRIPT   = 0x85,
} ValveTritonOutReportMessageIDs;
```

**Implication for SteamHapticsSinger:** their "Note-On" (0x83) is the public `HAPTIC_LFO_TONE` (continuous-tone generator at a given frequency), and "Note-Off" (0x81) is `HAPTIC_PULSE`. Functional naming for a MIDI-player use case, but canonically these are the LFO-tone and pulse haptic-message types. Their `byte[1] = actuator_id` corresponds to the `side` field in the struct (per controller_structs.h: `0x01 = L, 0x02 = R, 0x03 = Both` — though SteamHapticsSinger's empirical IDs 0/1/3/4 suggest the Triton firmware uses `side` as a per-actuator index, not L/R/Both).

Full message structs at `controller_structs.h:163-223`. The most powerful is `MsgHapticLfoTone` (10 bytes payload + report ID):

```c
typedef struct {
    uint8_t  side;
    int8_t   gain_db;
    uint16_t frequency;
    uint16_t duration_ms;
    uint16_t lfo_freq;
    uint8_t  lfo_depth;
} MsgHapticLfoTone;
```

The full haptic API also exposes `MsgHapticLogSweep`, `MsgHapticScript` (with `script_id`), and a multi-mode `MsgTriggerHaptic` with 8 sub-modes (TICK / CLICK / TONE / RUMBLE / NOISE / SCRIPT / LOG_SWEEP / OFF). Most of these are unexplored from a higher-level RE angle.

## Wire format — main state report (`TritonMTUFull_t`, `controller_structs.h:596`)

Already covered in [HID_REPORT_FORMAT.md](HID_REPORT_FORMAT.md). The complete struct is `#pragma pack(1)`:
- 1 B seq_num
- 4 B buttons (uint32 LE, `TritonButtons` enum)
- 2 B sTriggerLeft / Right (effectively uint15 stored in signed int16; SDL maps to SDL trigger axis via `raw * 2 − 32768`)
- 2 B × 4 sticks (LX/LY/RX/RY, signed int16)
- 2 B × 4 + 2 × 2 trackpads (X/Y + pressure, X/Y signed, pressure unsigned)
- 4 B IMU timestamp
- 6 B accel (3× int16)
- 6 B gyro (3× int16)
- 8 B quaternion (4× int16) — Full variant only

**Note: the SDL driver parses with `TritonMTUNoQuat_t` and silently ignores the trailing 8 quaternion bytes if the report is `Full` (54 B vs. 46 B).**

## How SDL3 transforms the raw values (driver lines 220-279)

This is publicly documented in the driver — listed here so we don't claim to have figured it out:

**Trigger** (line 222):
```c
SDL_SendJoystickAxis(..., SDL_GAMEPAD_AXIS_LEFT_TRIGGER,
                    (int)pTritonReport->sTriggerLeft * 2 - 32768);
```

**Sticks** — Y is negated (lines 229, 233):
```c
SDL_SendJoystickAxis(..., SDL_GAMEPAD_AXIS_LEFTY, -pTritonReport->sLeftStickY);
SDL_SendJoystickAxis(..., SDL_GAMEPAD_AXIS_RIGHTY, -pTritonReport->sRightStickY);
```

**Gyro** — axis swizzle and ±2000 °/s scale (lines 240-242):
```c
values[0] = (pTritonReport->imu.sGyroX / 32768.0f) * (2000.0f * (SDL_PI_F / 180.0f));  // X
values[1] = (pTritonReport->imu.sGyroZ / 32768.0f) * (2000.0f * (SDL_PI_F / 180.0f));  // Y ← raw Z
values[2] = (-pTritonReport->imu.sGyroY / 32768.0f) * (2000.0f * (SDL_PI_F / 180.0f)); // Z ← raw -Y
```

The quaternion fields (`sGyroQuatW/X/Y/Z`) come **directly from the IMU chip's on-board Smart Fusion Engine** (ST LSM6DSV16X — confirmed in `FIRMWARE_PROTOCOL.md` §"External I2C peripherals"). The host doesn't need to fuse gyro+accel itself.

**Accel** — same swizzle, ±2 g scale (lines 245-247):
```c
values[0] = (pTritonReport->imu.sAccelX / 32768.0f) * 2.0f * SDL_STANDARD_GRAVITY;
values[1] = (pTritonReport->imu.sAccelZ / 32768.0f) * 2.0f * SDL_STANDARD_GRAVITY;
values[2] = (-pTritonReport->imu.sAccelY / 32768.0f) * 2.0f * SDL_STANDARD_GRAVITY;
```

**Trackpad** — Y is flipped, normalize to [0,1] (lines 257-258):
```c
ctx->left_touch_x =  pTritonReport->sLeftPadX / 65536.0f + 0.5f;
ctx->left_touch_y = -pTritonReport->sLeftPadY / 65536.0f + 0.5f;
```

**Trackpad pressure** — normalize to [0,1] (line 265):
```c
pTritonReport->sPressureLeft / 32768.0f
```

## Timing constants (driver and structs)

| Constant | Value | Source |
|---|---|---|
| `TRITON_SENSOR_UPDATE_INTERVAL_US` | 4032 | Driver, line 36 — "Always 1kHz according to USB descriptor, but actually about 4 ms" → ~248 Hz nominal. (Our `frame_rate=11` attribute reads ~266 Hz on the device; minor discrepancy.) |
| `TRITON_RUMBLE_RESEND_INTERVAL_MS` | 40 | Driver, line 39 — "Steam Controller hardware safety timeout is around 50ms, so we resend rumble every 40ms" |
| Lizard refresh period | 3000 ms | Driver, line 427 — `(now - ctx->last_lizard_update) >= 3000` |

## Charge states (`controller_structs.h:639`)

```c
enum EChargeState
{
    k_EChargeStateReset,         // 0
    k_EChargeStateDischarging,   // 1
    k_EChargeStateCharging,      // 2
    k_EChargeStateSrcValidate,   // 3
    k_EChargeStateChargingDone,  // 4
};
```

(Our earlier docs listed only 3 — Reset and SrcValidate were missing.)

## Wireless states (`controller_structs.h:562`)

```c
enum ETritonWirelessState
{
    k_ETritonWirelessStateDisconnect = 1,
    k_ETritonWirelessStateConnect = 2,
};
```

## Battery struct (`controller_structs.h:648`)

```c
typedef struct
{
    unsigned char  ucChargeState;   // EChargeState
    unsigned char  ucBatteryLevel;  // 0..100? (SDL passes it as-is)
    unsigned short sBatteryVoltage;
    unsigned short sSystemVoltage;
    unsigned short sInputVoltage;
    unsigned short sCurrent;
    unsigned short sInputCurrent;
    unsigned short sTemperature;
} TritonBatteryStatus_t;  // 14 bytes; report 0x43 is 15 total including the ID byte
```

## Feature-report IDs (`controller_constants.h:55`)

The `FeatureReportMessageIDs` enum is shared between SC1, Deck, and Triton. The most relevant entries (60+ defined; Triton uses only a subset):

| Hex | Symbol | Notes |
|---|---|---|
| `0x80` | `SET_DIGITAL_MAPPINGS` | (note: shares value space with output-report IDs; feature reports use a different transport) |
| `0x83` | `GET_ATTRIBUTES_VALUES` | The opcode we send to query the 31-tag attribute table — confirmed our usage |
| `0x86` | `FACTORY_RESET` | ⚠️ |
| `0x87` | `SET_SETTINGS_VALUES` | What SDL3 uses to disable Lizard mode and set IMU mode |
| `0x89` | `GET_SETTINGS_VALUES` | Read current setting values |
| `0x8B` | `GET_SETTINGS_MAXS` | Read setting max values |
| `0x8C` | `GET_SETTINGS_DEFAULTS` | Read setting defaults |
| `0x8D` | `SET_CONTROLLER_MODE` | Switch between gamepad/keyboard-mouse modes |
| `0x8F` | `TRIGGER_HAPTIC_PULSE` | SC1-era haptic; not used on Triton |
| `0x9F` | `TURN_OFF_CONTROLLER` | Power-off command |
| `0xA1` | `GET_DEVICE_INFO` | Basic device info |
| `0xA7` | `CALIBRATE_TRACKPADS` | |
| `0xA9` | `SET_SERIAL_NUMBER` | |
| `0xAA` | `GET_TRACKPAD_CALIBRATION` | |
| `0xAB` | `GET_TRACKPAD_FACTORY_CALIBRATION` | |
| `0xAC` | `GET_TRACKPAD_RAW_DATA` | Raw image from trackpad! |
| `0xAD` | `ENABLE_PAIRING` | Puck-pairing command |
| `0xAE` | `GET_STRING_ATTRIBUTE` | Serial number / board serial |
| `0xAF` | `RADIO_ERASE_RECORDS` | ESB pairing-records erase |
| `0xB0` | `RADIO_WRITE_RECORD` | Write a new pairing |
| `0xB1` | `SET_DONGLE_SETTING` | Configure puck-side settings |
| `0xB2` | `DONGLE_DISCONNECT_DEVICE` | Force-disconnect a paired controller |
| `0xB3` | `DONGLE_COMMIT_DEVICE` | Save pairing |
| `0xB4` | `DONGLE_GET_WIRELESS_STATE` | Query puck's wireless state |
| `0xB5` | `CALIBRATE_GYRO` | |
| `0xB6` | `PLAY_AUDIO` | Trigger a built-in sound (see `ControllerAudio` enum) |
| `0xB7..B9` | `AUDIO_UPDATE_*` | Update sound bank |
| `0xBA` | `GET_CHIPID` | Read silicon ID |
| `0xBF` | `CALIBRATE_JOYSTICK` | |
| `0xC0` | `CALIBRATE_ANALOG_TRIGGERS` | |
| `0xC4` | `DONGLE_GET_CONNECTED_SLOTS` | Which of the 4 puck slots have controllers? |
| `0xCE` | `RESET_IMU` | |

## Settings of interest (subset of 80+ in `ControllerSettings`)

| # | Symbol | Notes |
|---|---|---|
| 9 | `SETTING_LIZARD_MODE` | What SDL3 toggles. 0 = off, 1 = on. |
| 25 | `SETTING_STEAMBUTTON_POWEROFF_TIME` | How long to hold Steam to power off |
| 48 | `SETTING_IMU_MODE` | Bit-flags: OFF=0, STEERING=1, TILT=2, ORIENTATION=4, RAW_ACCEL=8, RAW_GYRO=16. SDL3 uses `SEND_RAW_ACCEL \| SEND_RAW_GYRO = 0x18`. |
| 50 | `SETTING_SLEEP_INACTIVITY_TIMEOUT` | Idle-to-sleep delay |
| 60 | `SETTING_PRESSURE_MODE` | Trackpad pressure mode |
| 62 | `SETTING_TRIGGER_MODE` | Analog vs. digital trigger behaviour |
| 64 | `SETTING_FRAME_RATE` | The controller's reporting rate — settable! |
| 70 | `SETTING_HAPTICS_ENABLED` | Master haptic on/off |
| 71 | `SETTING_STEAM_WATCHDOG_ENABLE` | The Lizard-reactivation watchdog itself |
| 76 | `SETTING_HAPTIC_MASTER_GAIN_DB` | Global haptic gain |
| 79 | `SETTING_HAPTIC_INTENSITY` | |

To send a setting value via SDL3's pattern: build a `FeatureReportMsg` with `header.type = ID_SET_SETTINGS_VALUES` (0x87), `header.length = sizeof(ControllerSetting) = 3 bytes per setting`, then one or more `ControllerSetting{settingNum, settingValue}` entries. Send as a 64-byte Feature Report.

## Audio playback enum (`ControllerAudio`, `controller_constants.h:571`)

Triton firmware retains slots for built-in audio cues:

| Slot | Symbol |
|---|---|
| 0 | `AUDIO_STARTUP` |
| 1 | `AUDIO_SHUTDOWN` |
| 2 | `AUDIO_PAIR` |
| 3 | `AUDIO_PAIR_SUCCESS` |
| 4 | `AUDIO_IDENTIFY` |
| 5 | `AUDIO_LIZARDMODE` |
| 6 | `AUDIO_NORMALMODE` |
| 7..15 | Reserved |

Trigger via `ID_PLAY_AUDIO` (0xB6). Whether the SC2 actually has a speaker / piezo or these are routed through the haptic actuators as audio-frequency vibration is unconfirmed. Worth probing.

## Trackpad modes (`TrackpadDPadMode`, `controller_constants.h:401`)

Nine modes. The trackpad can be configured per-pad as: absolute-mouse, relative-mouse, 4-way dpad (discrete or overlap), 8-way dpad, radial, absolute-dpad, none, or gesture-keyboard.

## What the SDL3 driver does NOT yet support

- **LED control** — `SetJoystickLED` returns `SDL_Unsupported()`. The Steam logo lights up but isn't programmatically controlled via SDL.
- **Trigger rumble** — `RumbleJoystickTriggers` returns `SDL_Unsupported()`. Trigger haptics (if any) aren't exposed.
- **Sensor reads in `Triton_BLE` mode** — driver only sends sensors when in non-BLE mode (`report_sensors` check).
- **The `SendJoystickEffect` pass-through** — accepts arbitrary 64-byte Feature Reports, so advanced clients can inject their own raw commands. This is the documented escape hatch for haptic-API users.

## Implications for our own RE

Now-recognised-as-public facts (we should not claim as novel):

1. **Output haptic report IDs 0x80-0x85** — SDL3 has the full enum and structs.
2. **Battery struct** (`TritonBatteryStatus_t`, 14 bytes, 8 fields) — SDL3-public.
3. **5 charge states** (we listed 3; SDL3 has 5).
4. **Wireless status struct** (1 byte: state, with two values) — SDL3-public.
5. **Setting IDs and their numeric values** — all in `controller_constants.h`.
6. **`SETTING_IMU_MODE = 48` and bit-flags including raw_accel/raw_gyro** — SDL3-public.
7. **IMU axis swizzle and ±2000°/s, ±2g scaling** — SDL3 driver lines 240-248.
8. **Stick Y inversion** — SDL3 driver lines 229, 233.
9. **Trackpad Y flip and normalization** — SDL3 driver lines 257-258.
10. **Trigger scaling formula** — SDL3 driver line 222.
11. **Lizard-mode refresh interval of 3000 ms** — SDL3 driver line 427.
12. **Rumble report = 10 bytes** — `controller_structs.h` `HID_RUMBLE_OUTPUT_REPORT_BYTES = 10`.
13. **`HID_FEATURE_REPORT_BYTES = 64`** — `controller_structs.h:26`.
14. **The full `FeatureReportMessageIDs` enum** of 60+ command IDs.
15. **The `ControllerAudio` enum** — controller has audio-cue slots.

Still genuinely first-publicly-documented in this project (cross-checked against SDL3):

- `hardwareupdater.x86_64` as Steam-bundled PyInstaller goldmine
- Bootloader CDC ACM PIDs `0x1005` (Triton-BL) and `0x1007` (Proteus-BL) — not in SDL3
- HDLC framing constants `0xAD/0xAE/0xAC` and the escape table
- Update-protocol message IDs `0x1234..0x1238`
- Firmware file header layout (32 bytes: magic + size + checksum + 20 reserved)
- Firmware magics `0xD2D86467` (Triton) and `0x2E795631` (Proteus)
- The `EDeviceType` enum with 7 entries (Triton_BL/USB/BLE/ESB, Proteus_BL/USB, Nereid_USB) — semantic mapping from `hardwareupdater.py`
- Live-feature-report routing (`fr_id=2, op=0x83` for puck, `fr_id=1, op=0x81` for controller via ESB) — these are wrappers around the public `ID_GET_ATTRIBUTES_VALUES` opcode but the multi-device routing pattern wasn't documented
- 31-tag Triton-specific attribute taxonomy (the shared `ControllerAttributes` enum only has ~13 entries — our additional tags are Triton-only)
- Firmware-string analysis: MP2733 charger, fuel-gauge IC, RGBW LEDs, Zephyr RTOS markers, ARM GCC 14 toolchain
- ESB `esb-controller@0..3` slot strings as proof of the 4-slot architecture
- The unobserved `0x7b` (13 B) report — not in SDL3's enum, ~2 Hz, likely Proteus-side puck status
- Frame-rate refinement to ~266 Hz via the `frame_rate=11` attribute query (vs. SDL3's commented "~4 ms" approximation)
- Firmware build-identifier at offset `0x012C` cross-referenced with the `"GIT_SHA_%s"` boot banner

## How to reproduce this cross-check

```bash
git clone --depth=1 --filter=blob:none https://github.com/libsdl-org/SDL.git
cd SDL
grep -rn 'Triton\|Proteus\|Nereid' src/joystick/
```

The driver and structs files are around 1900 lines total — entirely readable in one sitting.
