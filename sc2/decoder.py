"""
Steam Controller 2 Puck HID stream decoder.

The puck (USB 28de:1304) exposes a vendor-defined HID endpoint that multiplexes
several Report IDs on the same stream. Report 0x42 carries the main controller
state at ~266 Hz; other IDs appear sporadically.

Confirmed mappings (validated against ~9k captured Report-0x42 frames):
  byte 0x00     Report ID (always 0x42 for state frames)
  byte 0x01     Sequence number — monotonic +1 per frame, wraps at 0xff
  byte 0x02:0   A button
  byte 0x02:1   B button
  byte 0x04:0   Steam button
  byte 0x0b:1   Capacitive "controller-in-hand" flag (sticky-ish)
  byte 0x0a..0x11   IMU: 4× int16 little-endian (gyro most likely; small range)
  byte 0x12..0x19   Sticks/touchpads (zero on every still-controller capture so far)
  byte 0x1e..0x35   24-byte per-device constant (serial/calibration — PII; do not publish)

Everything else in bytes 0x03, 0x05..0x09, and the high bits of 0x02/0x04 is
unmapped. Use SC2Decoder.diff_unknown() during live captures to surface bit
changes outside the known mappings.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import Iterator, Optional


INPUT_REPORT_SIZES: dict[int, int] = {
    0x40: 6,    # Lizard-mode mouse (only when Steam not running)
    0x41: 9,    # Lizard-mode keyboard
    0x42: 54,   # Controller state — primary report
    0x43: 15,   # Sub-status (purpose TBD — battery? events?)
    0x44: 6,
    0x45: 46,
    0x79: 2,
    0x7b: 13,   # Sub-status (rarely seen; periodic)
}

STATE_REPORT_ID = 0x42
STATE_REPORT_SIZE = INPUT_REPORT_SIZES[STATE_REPORT_ID]


KNOWN_BUTTON_BITS: dict[str, tuple[int, int]] = {
    "A":            (0x02, 0),
    "B":            (0x02, 1),
    "X":            (0x02, 2),
    "Y":            (0x02, 3),
    "QAM":          (0x02, 4),
    "R3":           (0x02, 5),
    "View":         (0x02, 6),
    "R4":           (0x02, 7),
    "R5":           (0x03, 0),
    "RB":           (0x03, 1),
    "DPad_Down":    (0x03, 2),
    "DPad_Right":   (0x03, 3),
    "DPad_Left":    (0x03, 4),
    "DPad_Up":      (0x03, 5),
    "Menu":         (0x03, 6),
    "L3":           (0x03, 7),
    "Steam":        (0x04, 0),
    "L4":           (0x04, 1),
    "L5":           (0x04, 2),
    "LB":           (0x04, 3),
    "RStick_Touch": (0x04, 4),
    "RPad_Touch":   (0x04, 5),
    "RPad_Click":   (0x04, 6),
    "RTrig_Click":  (0x04, 7),
    "LStick_Touch": (0x05, 0),
    "LPad_Touch":   (0x05, 1),
    "LPad_Click":   (0x05, 2),
    "LTrig_Click":  (0x05, 3),
    "RGrip_Touch":  (0x05, 4),
    "LGrip_Touch":  (0x05, 5),
}

# Analog fields per SDL3 controller_structs.h. (offset, format, name)
ANALOG_FIELDS: list[tuple[int, str, str]] = [
    (0x06, "<h", "TrigL"),
    (0x08, "<h", "TrigR"),
    (0x0a, "<h", "LStickX"),
    (0x0c, "<h", "LStickY"),
    (0x0e, "<h", "RStickX"),
    (0x10, "<h", "RStickY"),
    (0x12, "<h", "LPadX"),
    (0x14, "<h", "LPadY"),
    (0x16, "<H", "LPress"),
    (0x18, "<h", "RPadX"),
    (0x1a, "<h", "RPadY"),
    (0x1c, "<H", "RPress"),
    (0x1e, "<I", "IMU_ts"),
    (0x22, "<h", "AccelX"),
    (0x24, "<h", "AccelY"),
    (0x26, "<h", "AccelZ"),
    (0x28, "<h", "GyroX"),
    (0x2a, "<h", "GyroY"),
    (0x2c, "<h", "GyroZ"),
    (0x2e, "<h", "QuatW"),
    (0x30, "<h", "QuatX"),
    (0x32, "<h", "QuatY"),
    (0x34, "<h", "QuatZ"),
]


@dataclass
class ControllerFrame:
    """Decoded snapshot of one Report 0x42 frame."""
    seq: int
    buttons: dict[str, bool]
    imu: tuple[int, int, int, int]
    sticks_raw: bytes
    raw: bytes = field(repr=False)

    def pressed(self, name: str) -> bool:
        return self.buttons.get(name, False)


def decode_state(report: bytes) -> ControllerFrame:
    if len(report) != STATE_REPORT_SIZE or report[0] != STATE_REPORT_ID:
        raise ValueError(f"not a 0x42 state report: id=0x{report[0]:02x} len={len(report)}")
    buttons = {name: bool(report[byte] & (1 << bit))
               for name, (byte, bit) in KNOWN_BUTTON_BITS.items()}
    # Use the SDL-spec gyro position for the imu tuple. IMU stays OFF
    # by default; you'll see constant values unless SETTING_IMU_MODE is enabled.
    imu = struct.unpack_from("<hhh", report, 0x28)  # GyroX, Y, Z
    return ControllerFrame(
        seq=report[1],
        buttons=buttons,
        imu=imu + (0,),
        sticks_raw=bytes(report[0x0a:0x12]),  # 4× int16: LX, LY, RX, RY
        raw=bytes(report),
    )


def iter_reports(stream) -> Iterator[bytes]:
    """Yield one HID report per iteration from a file-like or path.

    Accepts a path string, an open binary file, or a raw bytes buffer.
    Handles variable-size reports by dispatching on the first byte (Report ID).

    For live hidraw devices, prefer iter_reports_live() — kernel hidraw delivers
    one report per read() and short reads can confuse the read(1) approach.
    """
    if isinstance(stream, str):
        f = open(stream, "rb")
        owns = True
    elif isinstance(stream, bytes):
        return _iter_from_buffer(stream)
    else:
        f = stream
        owns = False

    try:
        while True:
            head = f.read(1)
            if not head:
                return
            rid = head[0]
            size = INPUT_REPORT_SIZES.get(rid)
            if size is None:
                # unknown report id — drop one byte and try to resync
                continue
            rest = f.read(size - 1)
            if len(rest) < size - 1:
                return  # truncated tail
            yield head + rest
    finally:
        if owns:
            f.close()


def iter_reports_live(fd: int) -> Iterator[bytes]:
    """Yield one HID report per iteration from a raw hidraw file descriptor.

    Use this for live captures from /dev/hidrawN. The kernel hidraw driver
    returns exactly one report per read(); we ask for MAX_REPORT_SIZE and
    take what we get. This avoids the partial-read pitfalls of stdio-buffered
    read(1).
    """
    import os
    max_size = max(INPUT_REPORT_SIZES.values())
    while True:
        data = os.read(fd, max_size)
        if not data:
            return
        yield data


def _iter_from_buffer(buf: bytes) -> Iterator[bytes]:
    i = 0
    while i < len(buf):
        rid = buf[i]
        size = INPUT_REPORT_SIZES.get(rid)
        if size is None:
            i += 1
            continue
        if i + size > len(buf):
            return
        yield buf[i : i + size]
        i += size


def iter_state_frames(stream) -> Iterator[ControllerFrame]:
    for rep in iter_reports(stream):
        if rep[0] == STATE_REPORT_ID:
            yield decode_state(rep)


# Bytes that are known/expected to change frame-to-frame and should not be
# flagged as "unknown bits changed". Used by diff_unknown().
# Per SDL3 wire format: seq + analog axes + IMU all vary continuously.
_NOISE_BYTES = set(range(0x01, 0x02)) | set(range(0x06, 0x36))

_KNOWN_BITS = {(byte, bit) for byte, bit in KNOWN_BUTTON_BITS.values()}


def diff_unknown(prev: bytes, curr: bytes) -> list[tuple[int, int, int, int]]:
    """Return (byte, bit, old, new) tuples for bit changes outside known regions.

    Skips: sequence number, IMU bytes, the per-device-constant region
    (0x1e..0x35), and bits that already correspond to a known button.
    Highlights changes in bytes 0x02..0x09 and 0x12..0x1d.
    """
    out: list[tuple[int, int, int, int]] = []
    for i in range(len(curr)):
        if i in _NOISE_BYTES or 0x1e <= i <= 0x35:
            continue
        if prev[i] == curr[i]:
            continue
        for bit in range(8):
            if (i, bit) in _KNOWN_BITS:
                continue
            mask = 1 << bit
            if (prev[i] & mask) != (curr[i] & mask):
                out.append((i, bit, (prev[i] >> bit) & 1, (curr[i] >> bit) & 1))
    return out
