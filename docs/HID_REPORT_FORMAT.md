# Steam Controller 2 Puck — HID Report Format (Work in Progress)

Reverse-engineered notes for the Steam Controller 2 "Vigor" wireless dongle
(Valve, USB `28de:1304`, FCC `2AES41002`). Firmware: `bcdDevice 0.02`
(pre-update baseline — no firmware update applied at the time of capture).

**Privacy warning:** the 24-byte per-device constant at offset `0x1e..0x35`
and the USB iSerial string are device-unique. Strip both before publishing
captures publicly.

## USB layout

Composite device with 7 interfaces:

| iface | class      | EP IN  | EP OUT | poll  | role                                |
|------:|------------|--------|--------|-------|-------------------------------------|
| 0     | CDC ACM    | (ctrl) | (ctrl) | —     | virtual serial — purpose TBD        |
| 1     | CDC Data   | EP×    | EP×    | —     | serial data (EACCES even as root)   |
| 2     | HID        | 0x83   | 0x02   | 2 ms  | controller slot 1 (active)          |
| 3     | HID        | 0x84   | 0x03   | 2 ms  | controller slot 2                   |
| 4     | HID        | 0x85   | 0x04   | 2 ms  | controller slot 3                   |
| 5     | HID        | 0x86   | 0x05   | 2 ms  | controller slot 4                   |
| 6     | HID        | 0x87   | 0x06   | 32 ms | dongle status channel               |

Configuration descriptor sets the Remote-Wakeup capability bit.

The puck supports up to 4 concurrent paired controllers, one per HID slot
(2..5). With one controller paired, only slot 1 (`hidraw9` on this Deck) sees
state traffic; slots 2..4 (`hidraw10..12`) are silent. `hidraw13` (iface 6) is
also silent while Steam runs.

## Report-ID multiplexing (slot endpoint, HID iface 2)

The slot endpoint multiplexes multiple Report IDs on a single stream. The
report descriptor (372 bytes) defines the following:

| Report ID | Direction | Size (incl. ID) | Purpose                          |
|----------:|-----------|----------------:|----------------------------------|
| `0x40`    | Input     | 6 B             | Lizard-mode mouse (no-Steam fallback) |
| `0x41`    | Input     | 9 B             | Lizard-mode keyboard                  |
| `0x42`    | Input     | 54 B            | **Primary controller state**          |
| `0x43`    | Input     | 15 B            | Periodic telemetry (rare, ~0.4 Hz)    |
| `0x44`    | Input     | 6 B             | Not yet seen in captures              |
| `0x45`    | Input     | 46 B            | Not yet seen in captures              |
| `0x79`    | Input     | 2 B             | Not yet seen in captures              |
| `0x7b`    | Input     | 13 B            | Battery/link status (~2 Hz)           |
| `0x80..0x86` | Output | 4–10 B          | Host→device control                   |
| `0x87..0x89` | Output | 64 B            | Larger host→device payloads           |
| `0x01,0x02`  | Feature | 64 B            | GET/SET configuration                 |

When Steam is running, the stream consists almost entirely of `0x42` reports
(at ~266 Hz) with `0x7b` reports interleaved every ~500 ms and `0x43`
reports every ~2.5 s. Reports `0x40`/`0x41` (Lizard-mode mouse/kbd) do *not*
appear while Steam is in control — Steam suppresses them.

## Report `0x42` — controller state (54 bytes = `TritonMTUFull_t`)

Authoritative source: SDL3 `src/joystick/hidapi/steam/controller_structs.h`.
`#pragma pack(1)` is active — fields are tight, no padding.

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

## Report `0x7b` — battery/link status (13 bytes, ~2 Hz)

Tentative interpretation based on 30+ samples across multiple captures:

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

## Report `0x43` — telemetry (15 bytes, ~0.4 Hz)

Largely constant payload, with a 5-byte tail (`0x09..0x0e`) that varies
between captures. Likely an internal heartbeat / telemetry packet. Not yet
parsed.

## Verified behaviours

- **Steam button is fully visible to userspace** while Steam is running. The
  Steam client does not consume it client-side; bit `0x04` bit 0 stays set
  for the full duration of the press in the HID stream. → Wake-trigger via
  long-press is viable.
- **Sequence number** at byte `0x01` increments by exactly +1 per `0x42`
  frame across all 9k+ captured frames (no skips, no resets).
- **Frame rate**: ~266 Hz for `0x42` reports (= ~3.76 ms period).
- **InHand bit (`0x0b` bit 1)** is a sticky "controller is actively held /
  awake" indicator. Goes 0→1 when the controller is picked up; stays 1
  through subsequent button activity. Useful as a power-state proxy.

## Open questions

1. Stick / trigger / touchpad layout in bytes `0x12..0x19` — needs fresh
   captures with motion.
2. Full IMU semantics (axes, scale factor, accel vs gyro split) — need a
   capture with the controller deliberately tilted along each axis.
3. Meaning of `0x0b` byte beyond bit 1 (high bits are non-zero in idle).
4. Report `0x44`, `0x45`, `0x79` triggers — never seen yet. Possibly fire on
   pairing, button-combos, or firmware events.
5. CDC ACM interface (`ttyACM1`) blocked by SteamOS MAC policy — getting in
   would require a custom kernel build or running outside the standard
   userland. Not pursued for now.

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

`sc2_decoder.iter_reports_live(fd)` does this for you.

## Tools in this directory

- `sc2_decoder.py` — Python module: stream parser + Report-0x42 decoder.
- `sc2_live_monitor.py` — CLI live observer; shows button transitions and
  unknown bit changes in real time.
- `sc2_wake_daemon.py` — wake-trigger prototype: Steam-button held ≥ N
  seconds fires a stub `WAKE TRIGGER FIRED` log line.

## Capture filename convention

- `idle_*.bin` — controller laid flat, untouched, lit-mode off
- `<button>_*.bin` — repeated presses of the named button only
- `<button>_still_*.bin` — same, with deliberate effort to keep the
  controller motionless (separates button bits from IMU drift)
- `<motion>_*.bin` — controller deliberately moved/tilted (for IMU work)

Always include the source `hidrawN` in the filename to keep slots separable.
