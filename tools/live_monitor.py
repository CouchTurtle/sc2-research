#!/usr/bin/env python3
"""
Live state-change observer for the Steam Controller 2 Puck.

Usage:
    python3 tools/live_monitor.py [--device /dev/hidraw9] [--show-imu]

On SteamOS the `deck` user already has ACL-granted read access to hidraw
nodes — do NOT prefix with sudo (root is actually blocked here).

Reads from /dev/hidraw9 and prints:
  - Button transitions (down/up) for known buttons
  - Sub-report arrivals (0x43, 0x7b — for protocol exploration)
  - "Unknown bit changed" events for unmapped regions, helping you discover
    which byte/bit a new button or sensor uses

Stop with Ctrl+C.
"""

from __future__ import annotations
import argparse
import errno
import os
import signal
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sc2.decoder import (  # noqa: E402
    INPUT_REPORT_SIZES,
    KNOWN_BUTTON_BITS,
    ANALOG_FIELDS,
    STATE_REPORT_ID,
    decode_state,
    diff_unknown,
)

MAX_REPORT_SIZE = max(INPUT_REPORT_SIZES.values())


def open_hidraw(path: str) -> int:
    try:
        return os.open(path, os.O_RDONLY)
    except PermissionError:
        sys.stderr.write(
            f"Permission denied on {path}.\n"
            f"On SteamOS run as the 'deck' user (NOT root/sudo) — the ACL grants\n"
            f"access to the deck user but blocks root.\n"
        )
        sys.exit(1)
    except FileNotFoundError:
        sys.stderr.write(f"{path} does not exist — is the puck plugged in?\n")
        sys.exit(1)


def read_one_report(fd: int) -> bytes | None:
    try:
        data = os.read(fd, MAX_REPORT_SIZE)
    except OSError as e:
        if e.errno in (errno.ENODEV, errno.EIO):
            return None
        raise
    return data if data else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="/dev/hidraw9")
    ap.add_argument("--show-imu", action="store_true",
                    help="also print IMU values (noisy)")
    ap.add_argument("--show-seq", action="store_true",
                    help="also print sequence number on every event")
    args = ap.parse_args()

    print(f"Opening {args.device}. Press buttons / move sticks / touch trackpads.")
    print("Ctrl+C to stop.\n")

    fd = open_hidraw(args.device)

    # State for diffing
    prev_buttons: dict[str, bool] = {k: False for k in KNOWN_BUTTON_BITS}
    prev_state_raw: bytes | None = None
    prev_imu: tuple[int, int, int, int] | None = None
    sub_report_counts: dict[int, int] = {}
    start = time.monotonic()
    frame_count = 0

    def on_sigint(signum, frame):
        elapsed = time.monotonic() - start
        rate = frame_count / elapsed if elapsed > 0 else 0
        print(f"\n\nStopped. {frame_count} state frames in {elapsed:.1f}s ({rate:.0f} Hz).")
        if sub_report_counts:
            print("Sub-reports seen:")
            for rid, cnt in sorted(sub_report_counts.items()):
                print(f"  0x{rid:02x}: {cnt}")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)

    while True:
        rep = read_one_report(fd)

        if rep is None:
            sys.stderr.write("\nStream ended. Bailing.\n")
            sys.exit(2)

        rid = rep[0]
        if rid not in INPUT_REPORT_SIZES:
            print(f"[?] unknown Report ID 0x{rid:02x} ({len(rep)}B): {rep.hex()}")
            continue
        if rid != STATE_REPORT_ID:
            sub_report_counts[rid] = sub_report_counts.get(rid, 0) + 1
            print(f"[sub] Report 0x{rid:02x} ({len(rep)}B): {rep.hex()}")
            continue

        frame_count += 1
        fr = decode_state(rep)

        # Button transitions
        for name, now in fr.buttons.items():
            if now != prev_buttons[name]:
                arrow = "DOWN" if now else "UP  "
                suffix = f"  [seq={fr.seq}]" if args.show_seq else ""
                print(f"[btn] {name:>8s} {arrow}{suffix}")
                prev_buttons[name] = now

        # Unknown bit changes
        if prev_state_raw is not None:
            for byte, bit, old, new in diff_unknown(prev_state_raw, rep):
                print(f"[??]  byte 0x{byte:02x} bit {bit}: {old} -> {new}  "
                      f"(full byte 0x{rep[byte]:02x})")
        prev_state_raw = rep

        # IMU (optional, requires SETTING_IMU_MODE enabled)
        if args.show_imu and prev_imu is not None:
            delta = max(abs(a - b) for a, b in zip(fr.imu, prev_imu))
            if delta > 50:
                print(f"[imu] gyro {fr.imu[:3]}")
        prev_imu = fr.imu

        # Active analog fields — only print fields that meaningfully moved
        active_analog = []
        for off, fmt, fname in ANALOG_FIELDS:
            if off >= 0x1e:  # skip IMU section (OFF by default)
                continue
            val = struct.unpack_from(fmt, rep, off)[0]
            # Skip if zero (resting state for triggers and pads)
            if val == 0:
                continue
            # Sticks at rest hover ~±300; only print when clearly outside that
            if "Stick" in fname and abs(val) < 800:
                continue
            # Triggers: only show meaningful pulls
            if "Trig" in fname and val < 2000:
                continue
            active_analog.append(f"{fname}={val}")
        if active_analog:
            print(f"[an]  {' '.join(active_analog)}")


if __name__ == "__main__":
    main()
