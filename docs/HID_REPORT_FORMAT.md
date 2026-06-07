# SC2 Puck — HID report format

> Mostly a verification doc. The wire format is in SDL3's [`controller_structs.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_structs.h) (`TritonMTUFull_t` / `TritonMTUNoQuat_t`). Beyond that, this doc covers the puck's full USB-interface topology, observed Lizard-mode reactivation timing, the `0x7b` puck-side status report (not in SDL3), and a few SteamOS access notes. For everything that's already in SDL3, see [`SDL3_REFERENCE.md`](SDL3_REFERENCE.md).

Hardware under test: SC2 puck (Valve, USB `28de:1304`, FCC `2AES41002`) on a Steam Deck running SteamOS, pre-update firmware baseline.

**Privacy note:** the USB `iSerial` string is device-unique and should be stripped from any captures you publish. The 0x1e..0x35 IMU block, despite looking like a static per-device constant in idle captures, is not PII — it just reads constant because IMU is OFF by default (see Finding #3 below).

## USB layout

Composite device with 7 interfaces:

| iface | class      | EP IN  | EP OUT | poll  | role                                |
|------:|------------|--------|--------|-------|-------------------------------------|
| 0     | CDC ACM    | (ctrl) | (ctrl) | —     | virtual serial — purpose TBD        |
| 1     | CDC Data   | EP×    | EP×    | —     | serial data (EACCES even as root)   |
| 2     | HID        | 0x83   | 0x02   | 2 ms  | controller slot 0 (active = `hidraw9` here) |
| 3     | HID        | 0x84   | 0x03   | 2 ms  | controller slot 1                   |
| 4     | HID        | 0x85   | 0x04   | 2 ms  | controller slot 2                   |
| 5     | HID        | 0x86   | 0x05   | 2 ms  | controller slot 3                   |
| 6     | HID        | 0x87   | 0x06   | 32 ms | dongle status channel               |

Configuration descriptor sets the Remote-Wakeup capability bit.

The puck supports up to 4 concurrent paired controllers, one per HID slot
(`esb-controller@0..3` per Proteus-firmware strings — 0-indexed). With one
controller paired, only slot 0 (`hidraw9` on this Deck) sees state traffic;
slots 1..3 (`hidraw10..12`) are silent. `hidraw13` (iface 6) is also silent
in normal use.

Proteus firmware confirms this mapping: it has a `hid_proxy` module with
endpoint names `HID_PROXY_0..3` (one per ESB slot) plus a `hid-puck` DT-node
for the puck's own status / control channel. So `hidraw9..12` correspond to
the four `HID_PROXY_N` endpoints, and `hidraw13` corresponds to `hid-puck`.
See `FIRMWARE_PROTOCOL.md` §"HID-proxy architecture" for details.

## Report-ID multiplexing (slot endpoint, HID iface 2)

The slot endpoint multiplexes multiple Report IDs on a single stream. The
report descriptor (372 bytes) defines the following:

| Report ID | Direction | Size (incl. ID) | Purpose                          |
|----------:|-----------|----------------:|----------------------------------|
| `0x40`    | Input     | 6 B             | Lizard-mode mouse (no-Steam fallback) |
| `0x41`    | Input     | 9 B             | Lizard-mode keyboard                  |
| `0x42`    | Input     | 54 B            | **Primary controller state** = `ID_TRITON_CONTROLLER_STATE` per SDL3 |
| `0x43`    | Input     | 15 B            | **`ID_TRITON_BATTERY_STATUS`** per SDL3 (`TritonBatteryStatus_t`, ~0.4 Hz on this device) |
| `0x44`    | Input     | 6 B             | In descriptor; never observed; not in SDL3 enum |
| `0x45`    | Input     | 46 B            | `ID_TRITON_CONTROLLER_STATE_BLE` per SDL3 — state report routed via Bluetooth LE; never seen in our Puck-only captures |
| `0x46`    | Input     | 2 B             | `ID_TRITON_WIRELESS_STATUS_X` per SDL3 (variant); never observed |
| `0x79`    | Input     | 2 B             | `ID_TRITON_WIRELESS_STATUS` per SDL3 (`TritonWirelessStatus_t`, 1-byte state); never observed in steady state |
| `0x7b`    | Input     | 13 B            | **Not in SDL3's enum** — observed at ~2 Hz, likely a Proteus-side puck status report (link quality / paired-slot status); contents are our genuine novel-find. See section below. |
| `0x80..0x85` | Output | 4–10 B          | Haptic output reports (Rumble / Pulse / Command / LFO_Tone / Log_Sweep / Script) per SDL3 `ValveTritonOutReportMessageIDs` |
| Feature   | Bi-dir    | 64 B            | `FeatureReportMsg` — get/set settings, attributes, audio, etc. (full enum in [`SDL3_REFERENCE.md`](SDL3_REFERENCE.md)) |

When Steam is running, the stream consists almost entirely of `0x42` reports
(at ~266 Hz) with `0x7b` reports interleaved every ~500 ms and `0x43`
reports every ~2.5 s. Reports `0x40`/`0x41` (Lizard-mode mouse/kbd) do *not*
appear while Steam is in control — Steam suppresses them.

## Report `0x42` — controller state (54 bytes = `TritonMTUFull_t`)

The layout below is **verbatim from SDL3's `controller_structs.h`** (`TritonMTUFull_t`). `#pragma pack(1)` is active — fields are tight, no padding. We're including the table here for convenience and because it has been byte-by-byte checked against ~9000 captured frames on this device.

| Raw offset | Size | Field name              | Notes                                        |
|------------|------|-------------------------|----------------------------------------------|
| `0x00`     | 1 B  | Report ID `0x42`        | constant                                     |
| `0x01`     | 1 B  | `seq_num`               | linear +1 per frame, wraps at 0xff           |
| `0x02..0x05` | 4 B | **`buttons`** (uint32 LE) | 30 bit-flags — see TritonButtons table below |
| `0x06..0x07` | 2 B | `sTriggerLeft`  (int16) | Hall-effect analog                           |
| `0x08..0x09` | 2 B | `sTriggerRight` (int16) | Hall-effect analog                           |
| `0x0a..0x0b` | 2 B | `sLeftStickX`   (int16) | TMR stick                                    |
| `0x0c..0x0d` | 2 B | `sLeftStickY`   (int16) | TMR stick                                    |
| `0x0e..0x0f` | 2 B | `sRightStickX`  (int16) | TMR stick                                    |
| `0x10..0x11` | 2 B | `sRightStickY`  (int16) | TMR stick                                    |
| `0x12..0x13` | 2 B | `sLeftPadX`     (int16) | trackpad position                            |
| `0x14..0x15` | 2 B | `sLeftPadY`     (int16) | **Y is flipped** (SDL3 PR #15528)            |
| `0x16..0x17` | 2 B | `sPressureLeft` (uint16)| trackpad pressure                            |
| `0x18..0x19` | 2 B | `sRightPadX`    (int16) | trackpad position                            |
| `0x1a..0x1b` | 2 B | `sRightPadY`    (int16) | trackpad position                            |
| `0x1c..0x1d` | 2 B | `sPressureRight`(uint16)| trackpad pressure                            |
| `0x1e..0x21` | 4 B | `imu.timestamp` (uint32)| HW timestamp — **frozen unless IMU enabled** |
| `0x22..0x27` | 6 B | `imu.Accel X/Y/Z`       | 3× int16 — IMU OFF by default                |
| `0x28..0x2d` | 6 B | `imu.Gyro X/Y/Z`        | 3× int16 — IMU OFF by default                |
| `0x2e..0x35` | 8 B | `imu.Quat W/X/Y/Z`      | 4× int16 — Full variant only, OFF by default |

**Frame-size check:** 54 B = `TritonMTUFull_t` (with quat). 46 B would be `TritonMTUNoQuat_t`. If you see anything else, you're on the wrong interface or report type.

### TritonButtons (bytes 0x02-0x05 as Uint32 LE)

| Byte 0x02 (bits 0-7) | Byte 0x03 (bits 0-7) | Byte 0x04 (bits 0-7) | Byte 0x05 (bits 0-5) |
|---|---|---|---|
| 0: A         | 0: R5         | 0: **Steam** ✓  | 0: LStick_Touch |
| 1: B         | 1: RB         | 1: L4          | 1: LPad_Touch   |
| 2: X         | 2: DPad_Down  | 2: L5          | 2: LPad_Click   |
| 3: Y         | 3: DPad_Right | 3: LB          | 3: LTrig_Click  |
| 4: QAM       | 4: DPad_Left  | 4: RStick_Touch| 4: RGrip_Touch  |
| 5: R3        | 5: DPad_Up    | 5: RPad_Touch  | 5: LGrip_Touch  |
| 6: View      | 6: Menu       | 6: RPad_Click  | (6-7 unused)    |
| 7: R4        | 7: L3         | 7: RTrig_Click |                 |

### Critical empirical findings

1. **IMU is OFF by default.** Verified across 9k+ idle frames AND a deliberate shake-capture: `timestamp`, all 3 accel, all 3 gyro and all 4 quat fields stayed **bitwise identical**. To get motion data, send `SETTING_IMU_MODE = SEND_RAW_GYRO/ACCEL` via Feature-Report. Our 9k captures are pure button/stick/pad data; IMU work is gated.

2. **Sticks work as SDL specifies — full int16 range on deflection.**  Idle bias is small (~±300, e.g. LStickX hovering at 231 at rest). On full deflection the values reach ±32767. Verified: capture 22 showed LStickX 0..32767, capture 23 showed RStickY -32767..32767. The earlier "sticks only go to ±700" claim was an artifact of looking at captures where the stick wasn't actually being moved.

3. **The "per-device constant" myth.** Earlier captures showed bytes 0x1e-0x35 as invariant 24-byte data and we mis-labelled it as device serial/calibration (and recommended PII redaction). It's actually the IMU+Quat section frozen because IMU was OFF. **Update your privacy stance:** redact `iSerial` from USB descriptors, but the 0x1e-0x35 bytes are not PII once IMU is on — they're motion sensor data.

4. **InHand-flag mystery is resolved.** Byte 0x0b bit 1 (our "InHand" flag, 0% idle → 100% active) is **not in the TritonButtons enum**. Byte 0x0b is the **high byte of `sLeftStickX`** (raw 0x0a-0x0b, int16 LE). Empirically: at rest LStickX is ~89..289 (high byte 0x00 or 0x01); when the controller is held LStickX drifts to ~520..690 (high byte 0x02), which sets bit 1 of byte 0x0b to 1. **Our "InHand" detection is actually "left-stick value crossed into the 512-767 range" because the controller is being held and the stick is biased.** Useful heuristic, but not a real capacitive flag. The real `LStick_Touch` capacitive bit lives in byte 0x05 bit 0.

## Lizard-Mode reports (0x40, 0x41) — only when Steam is dead

Per SDL3, Steam sends a periodic `SETTING_LIZARD_MODE = OFF` setting to suppress the controller's built-in mouse/keyboard emulation. The controller has a watchdog: if the setting isn't refreshed, Lizard-Mode reactivates automatically.

Empirically verified (2026-05-19):
- After `kill -9` of all Steam processes, Lizard reactivates within ~8 seconds
- First reports are **initial-state** (all zero): `410000000000000000` (keyboard, 9B) + `400000000000` (mouse, 6B)
- Further Lizard reports are **change-based** — only when buttons are actually pressed
- As soon as Steam restarts, Lizard is suppressed again within seconds (no further 0x40/0x41)

The reports use the standard HID boot-keyboard / boot-mouse layouts (per descriptor).

## hidraw13 (interface 6) — initial pairing only

Across 180+ seconds of monitoring including a full Steam-stop cycle and idle: **0 bytes ever read from hidraw13**. The vendor interface 6 (32 ms polling) appears to only become active during initial puck↔controller pairing, not for ongoing connect/disconnect events. When a paired controller goes off/on, the host learns about it only through the absence of data on hidraw9-12 (slot-specific timeout), not via an explicit event report.

## Report `0x7b` — puck-side status (13 bytes, ~2 Hz)

**Not present in SDL3's `ETritonReportIDTypes` enum** — SDL3 only knows 0x42, 0x43, 0x45, 0x46, 0x79. So `0x7b` is genuinely undocumented by Valve in the open-source code. Our hypothesis: it's a Proteus-side status report (link statistics / pairing slot info) that the puck firmware emits but SDL3 doesn't consume because it isn't needed for the controller-as-joystick abstraction.

(Earlier drafts of this doc labelled `0x7b` as the battery report — that was wrong; battery is `0x43` per SDL3.)

Tentative byte interpretation based on 30+ samples across multiple captures:

| offset | sample values             | likely meaning                          |
|--------|---------------------------|-----------------------------------------|
| `0x00` | `7b`                      | Report ID                               |
| `0x01` | `f5..f9`                  | rolling counter or noise                |
| `0x02` | `85` or `86`              | status flag                             |
| `0x03` | `00`                      | constant                                |
| `0x04` | `00..01`                  | sparse 1-bit indicator                  |
| `0x05` | `00`                      | constant                                |
| `0x06` | `03..05`                  | small counter                           |
| `0x07` | `00`                      | constant                                |
| `0x08` | `ba..c8`                  | **varies per session** — battery/voltage candidate (idle 0xc2, after activity 0xba-0xc8) |
| `0x09` | `00`                      | constant                                |
| `0x0a` | `3c, 4c, 4e`              | **varies per session** — RSSI / link quality candidate |
| `0x0b` | `ff`                      | constant `0xff`                         |

## Report `0x43` — battery status (15 bytes, ~0.4 Hz)

Per SDL3 (`controller_structs.h:648`) this is `ID_TRITON_BATTERY_STATUS` carrying a `TritonBatteryStatus_t` payload:

```c
typedef struct {
    uint8_t  ucChargeState;     // EChargeState: 0=Reset, 1=Discharging, 2=Charging, 3=SrcValidate, 4=ChargingDone
    uint8_t  ucBatteryLevel;    // 0..100? — SDL passes to SDL_SendJoystickPowerInfo as-is
    uint16_t sBatteryVoltage;
    uint16_t sSystemVoltage;
    uint16_t sInputVoltage;
    uint16_t sCurrent;
    uint16_t sInputCurrent;
    uint16_t sTemperature;
} TritonBatteryStatus_t;  // 14 bytes payload + 1 report-ID byte = 15 bytes total
```

Our 30+ samples show the 5-byte tail (`0x09..0x0e`) varying between captures — that's `sCurrent`, `sInputCurrent`, and `sTemperature`, which makes sense (the controller's load varies). Earlier drafts labelled this as "telemetry, not yet parsed" — the SDL3 reference resolves it. To map byte offsets to fields:

| offset (incl. ID) | size | field |
|---|---|---|
| `0x00` | 1 | Report ID `0x43` |
| `0x01` | 1 | `ucChargeState` |
| `0x02` | 1 | `ucBatteryLevel` |
| `0x03..0x04` | 2 | `sBatteryVoltage` (LE) |
| `0x05..0x06` | 2 | `sSystemVoltage` |
| `0x07..0x08` | 2 | `sInputVoltage` |
| `0x09..0x0a` | 2 | `sCurrent` |
| `0x0b..0x0c` | 2 | `sInputCurrent` |
| `0x0d..0x0e` | 2 | `sTemperature` |

## Verified behaviours

- **Steam button visible to userspace** while Steam runs. Steam doesn't consume the bit client-side; byte `0x04` bit 0 stays set for the whole press in the HID stream.
- **Sequence number** at byte `0x01` increments by exactly +1 per `0x42` frame across all 9k+ captured frames (no skips, no resets).
- **Frame rate** for `0x42`: ~266 Hz (= ~3.76 ms period) — matches the `frame_rate` attribute (tag 11) returned by `attr_query.py`. Reviewers typically cite **~250 Hz** ([PC Gamer](https://www.pcgamer.com/hardware/game-pads/steam-controller-2026-review/), [DropReference](https://dropreference.com/en/blog/news/steam-controller-2026-price-release-date-specs-reviews)), matching the SDL3 source comment "actually about 4 ms". Our measurement refines that to the firmware's self-reported 266 Hz.
- **Stick bias drift as a proxy for "in hand"**: `sLeftStickX` typically idles in 89..289 and drifts into 520..690 while the controller is being gripped, which flips the high byte (`0x0b`) between `0x01` and `0x02`. Practically useful as a power-state heuristic, but it isn't a dedicated capacitive flag — the real `LStick_Touch` bit lives at byte `0x05` bit 0 (see Finding #4).

## Open questions

1. Full IMU semantics — once IMU is enabled via `SETTING_IMU_MODE`, the
   scale factor and axis orientation need an empirical pass (controller
   deliberately tilted along each axis, gyro spin).
2. Report `0x44`, `0x45`, `0x79` triggers — present in the HID descriptor,
   never seen in any of our 9k+ captures. Plausible triggers: pairing
   events on hidraw13, charge-done, firmware-update completion.
3. CDC ACM interfaces 0+1 on the puck blocked by SteamOS MAC policy — getting
   in would require a custom kernel or running outside the standard userland.
   Not pursued.

## SteamOS access notes

`/dev/hidraw9` (and the other puck hidraw nodes, plus `/dev/ttyACM1`) appear
as `crw-rw----+ 1 nobody nogroup`. The `+` indicates an extended POSIX ACL
which grants the `deck` user read access. Root is **not** in the ACL and the
mode bits do not give root any precedence, so `sudo cat /dev/hidraw9` fails
with `EACCES` while a plain `cat /dev/hidraw9` succeeds as `deck`.

Lessons:
- Always run the tools in this directory as the `deck` user, never with
  sudo.
- When `cat`-capturing, use simple shell redirect (`timeout 5 cat /dev/hidraw9
  > foo.bin`) — no sudo needed.
- Python `open()`/`os.open()` works identically: no sudo.

## Live-stream gotcha: short reads with stdio buffering

When reading from hidraw, do **not** use `file.read(1)` followed by
`file.read(size-1)` to assemble a report. Python's buffered IO interprets a
1-byte read from a hidraw device as a partial-result and the subsequent reads
can return `b""`, which looks like EOF. The kernel hidraw driver actually
delivers exactly one report per `os.read()` call, regardless of buffer size,
so the idiomatic pattern is:

```python
import os
fd = os.open('/dev/hidraw9', os.O_RDONLY)
while True:
    report = os.read(fd, 64)   # exactly one HID report
    if not report:
        break
    process(report)
```

`sc2.iter_reports_live(fd)` (from the library) does this for you.

## Related tools

- [`sc2/decoder.py`](../sc2/decoder.py) — Python library: stream parser + Report-0x42 decoder.
- [`tools/live_monitor.py`](../tools/live_monitor.py) — CLI live observer; shows button transitions in real time.
- [`tools/event_logger.py`](../tools/event_logger.py) — parallel logger across hidraw9-13; report-ID histogram per interface.
- [`tools/attr_query.py`](../tools/attr_query.py) — Feature-Report attribute queries via `ioctl` (see `FIRMWARE_PROTOCOL.md §Live Feature-Report Channels`).

## Capture filename convention

- `idle_*.bin` — controller laid flat, untouched
- `<button>_*.bin` — repeated presses of the named button only
- `<button>_still_*.bin` — same, with deliberate effort to keep the
  controller motionless (avoids the stick-bias drift described in Finding #4
  showing up as background noise in unrelated bytes)
- `<motion>_*.bin` — controller deliberately moved/tilted (only meaningful
  once IMU has been enabled via `SETTING_IMU_MODE`; otherwise the IMU bytes
  stay constant regardless of motion)

Always include the source `hidrawN` in the filename to keep slots separable.
