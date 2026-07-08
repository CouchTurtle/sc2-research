# SC2 haptic + audio output reports (0x80–0x89)

> This document is a **cross-reference, not original work.** The haptic/audio output protocol was reverse-engineered by [`iczero/steam-controller-stuff`](https://github.com/iczero/steam-controller-stuff) (a Wireshark dissector + Rust audio player) and corroborated by the [`mwdmwd/sc26re`](https://github.com/mwdmwd/sc26re) firmware. This repo focuses on the input/firmware-update side and didn't investigate haptic output; it's summarised here so the picture is complete. Report IDs `0x80`–`0x85` are named in SDL3's `ValveTritonOutReportMessageIDs`; the field layouts, side enums, gain range, the `0x86`–`0x89` audio-stream reports, and the script table are **not** in SDL3 and come from iczero's RE.

All are **output** reports on the interrupt endpoint. Byte 0 = report ID; multi-byte fields are little-endian. Gain fields are `int8` **dB**, clamped to **−23…24**.

## Actuator "side" enum

Most reports take a `side` byte. It is **not consistent across reports**:

| Report | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| `0x81` pulse | TP_RIGHT | TP_LEFT | TP_BOTH | INT_LEFT | INT_RIGHT | INT_BOTH | — | — |
| `0x82` command | TP_LEFT | TP_RIGHT | TP_BOTH | — | — | — | — | — |
| `0x83`/`0x84`/`0x85` | TP_LEFT | TP_RIGHT | TP_BOTH | INT_LEFT | INT_RIGHT | INT_BOTH | =2 | =4 |

`TP_*` = trackpad actuators, `INT_*` = internal LRA motors. (Firmware treats side 6/7 the same as 2/4.)

## Reports 0x80–0x85 (SDL3-named)

| ID | Name | Body |
|---|---|---|
| `0x80` | HAPTIC_RUMBLE | `type` u8, `intensity` u16, `left_speed` u16, `left_gain` i8 dB, `right_speed` u16, `right_gain` i8 dB (no side field — explicit L/R) |
| `0x81` | HAPTIC_PULSE | `side` u8, `on_us` u16, `off_us` u16, `repeat` u16 |
| `0x82` | HAPTIC_COMMAND | `side` u8, `command` u8 (0=STOP_ALL, 1=CLICK, 2=CLICK_STRONG), `gain` i8 dB |
| `0x83` | HAPTIC_LFO_TONE | `side` u8, `gain` i8 dB, `frequency` u16 Hz, `duration` u16, `lfo_freq` u16 Hz, `lfo_depth` u8 |
| `0x84` | HAPTIC_LOG_SWEEP | `side` u8, `gain` i8 dB, `duration` u16, `start_freq` u16 Hz, `end_freq` u16 Hz |
| `0x85` | HAPTIC_SCRIPT | `side` u8, `script_id` u8 (see below), `gain` i8 dB |

Note: SteamHapticsSinger's "Note-On `0x83`" is `HAPTIC_LFO_TONE`; its "Note-Off `0x81`" is `HAPTIC_PULSE`.

### Script IDs (0x85)

`0x01` CONTROLLER_ON · `0x02` CONTROLLER_VERY_ON · `0x03` TRILL_UP · `0x04` TRILL_DOWN · `0x05` CONTROLLER_OFF · `0x06` UP_FIVE · `0x07` DOWN_FIVE · `0x08` UP_SIX · `0x09` DOWN_SIX · `0x0a` WHOOP_UP_3 · `0x0b` WHOOP_DOWN · `0x0c` PHONE_RINGING_1 (the "Ping" in Identify Controller) · `0x0d` RINGBACK_TONE · `0x0e` PHONE_RINGING_2 · `0x0f` PHONE_RINGING_3 · `0x10` WILHELM_SCREAM (played when you drop the controller).

## Reports 0x86–0x89 — audio streaming (not in SDL3)

The actuators can play arbitrary PCM/u-law audio. `0x86` configures a stream; `0x87`/`0x88`/`0x89` push sample data.

- **`0x86` STREAM_CONFIGURE**: `operation` u8 (1=STOP, 2=CONFIGURE), `target` u8 (0=INT_LEFT, 1=INT_RIGHT, 2=INT_BOTH, 3=TP_LEFT, 4=TP_RIGHT, 5=TP_BOTH), `param` u8 (format, table below; CONFIGURE only).
- **`0x87` STREAM_PUSH_DATA_FULL**: `target` u8, then up to 62 data bytes.
- **`0x88` STREAM_PUSH_DATA_INT_2CH**: `length` u8, then a 31-byte left slot + a 31-byte right slot (INT_LEFT + INT_RIGHT).
- **`0x89` STREAM_PUSH_DATA_PARTIAL**: `length` u8, `target` u8, then `length` data bytes (like `0x87` but with an explicit length).

Stream format (`param` value):

| param | rate | coding | | param | rate | coding |
|---|---|---|---|---|---|---|
| 0 | 8 kHz | 16-bit PCM | | 6 | 2 kHz | 8-bit PCM |
| 1 | 4 kHz | 16-bit PCM | | 7 | 1 kHz | 8-bit PCM |
| 2 | 2 kHz | 16-bit PCM | | 8 | 8 kHz | 8-bit u-law |
| 3 | 1 kHz | 16-bit PCM | | 9 | 4 kHz | 8-bit u-law |
| 4 | 8 kHz | 8-bit PCM | | 10 | 2 kHz | 8-bit u-law |
| 5 | 4 kHz | 8-bit PCM | | 11 | 1 kHz | 8-bit u-law |

The 8 kHz variants (param 0/4/8) are only valid on the internal motors — the trackpad actuators top out at 4 kHz. The puck's ~500 Hz USB poll rate can't sustain stereo 16-bit; wired (1 kHz) or a lower-bandwidth format is needed.

## Report 0x44 — audio buffer feedback (input)

`ID_TRITON_AUDIO_BUFFER_FEEDBACK`. Body: `actuator` u8 (0=INT_LEFT, 1=INT_RIGHT, 3=TP_LEFT, 4=TP_RIGHT), `status` u8 bitfield:

| bit | meaning |
|---|---|
| 0 | buffer overrun |
| 1 | stream stopped (possible underrun) |
| 2 | needs more data |
| 3 | has enough data |
| 4 | config rejected (invalid) |
| 5 | config accepted |
| 6 | config rejected (already running) |

This is the flow-control channel a host uses to pace `0x87`/`0x88`/`0x89` pushes.
