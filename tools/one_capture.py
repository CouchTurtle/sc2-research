#!/usr/bin/env python3
"""
Single targeted capture for SC2 mapping.

Usage:
    python3 tools/one_capture.py <name>

Workflow:
  1. you run the command in YOUR terminal
  2. it prints "READY — press Enter when you're holding/pressing the action"
  3. you press Enter — capture starts immediately
  4. capture runs 3 seconds while you keep performing the action
  5. result is saved and a diff vs baseline is printed inline

No countdowns, no background nonsense. Run as the `deck` user (NOT sudo).
"""

from __future__ import annotations
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sc2.decoder import (
    INPUT_REPORT_SIZES,
    KNOWN_BUTTON_BITS,
    ANALOG_FIELDS,
    iter_state_frames,
)
import struct

OUTDIR = Path(__file__).parent / "mapping"
BASELINE = OUTDIR / "00_baseline_idle.bin"
MAX_REPORT_SIZE = max(INPUT_REPORT_SIZES.values())
CAPTURE_SECONDS = 3.0


def capture_to(path: Path, seconds: float):
    fd = os.open("/dev/hidraw9", os.O_RDONLY)
    deadline = time.monotonic() + seconds
    buf = bytearray()
    last_tick = time.monotonic()
    print("  ", end="", flush=True)
    try:
        while time.monotonic() < deadline:
            data = os.read(fd, MAX_REPORT_SIZE)
            buf.extend(data)
            now = time.monotonic()
            if now - last_tick >= 0.5:
                remaining = deadline - now
                print(f"●", end="", flush=True)
                last_tick = now
    finally:
        os.close(fd)
    # Bell + visible end-marker
    print(f" \a\n  ━━━ FERTIG ━━━ (Taste loslassen)", flush=True)
    path.write_bytes(bytes(buf))


def quick_diff(name: str):
    if not BASELINE.exists():
        print("  (no baseline at mapping/00_baseline_idle.bin — skipping diff)")
        return
    base = list(iter_state_frames(str(BASELINE)))
    act = list(iter_state_frames(str(OUTDIR / f"{name}.bin")))
    if not act:
        print("  (capture is empty)")
        return

    findings = []

    # 1. SDL named buttons — % pressed in action vs baseline
    for btn_name, (byte_i, bit_i) in KNOWN_BUTTON_BITS.items():
        base_p = 100 * sum(1 for f in base if f.raw[byte_i] & (1<<bit_i)) / max(1, len(base))
        act_p  = 100 * sum(1 for f in act  if f.raw[byte_i] & (1<<bit_i)) / max(1, len(act))
        delta = act_p - base_p
        if abs(delta) >= 15:
            findings.append(("BTN", abs(delta), btn_name, f"{base_p:>3.0f}% → {act_p:>3.0f}%"))

    # 2. SDL named analog fields — range expansion
    for off, fmt, fname in ANALOG_FIELDS:
        try:
            bvals = [struct.unpack_from(fmt, f.raw, off)[0] for f in base]
            avals = [struct.unpack_from(fmt, f.raw, off)[0] for f in act]
        except struct.error:
            continue
        b_range = max(bvals) - min(bvals) if bvals else 0
        a_range = max(avals) - min(avals) if avals else 0
        # Significant expansion: range grew by >100 AND >3× baseline
        if a_range > 100 and a_range > b_range * 3:
            findings.append(("AN", a_range,  fname,
                            f"baseline {min(bvals)}..{max(bvals)} → action {min(avals)}..{max(avals)}"))

    findings.sort(key=lambda x: -x[1])
    print()
    print(f"  Diff vs baseline ({len(act)} frames):")
    if not findings:
        print("    (no significant changes — re-try the action)")
        return
    for kind, sev, fname, detail in findings[:12]:
        prefix = "BTN " if kind == "BTN" else "AN  "
        print(f"    {prefix}{fname:<14s} {detail}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 tools/one_capture.py <name>")
        print("  python3 tools/one_capture.py <name1> <name2> <name3> ...")
        print()
        print("Examples:")
        print("  python3 tools/one_capture.py X")
        print("  python3 tools/one_capture.py X Y LB RB L4 L5 R4 R5")
        sys.exit(1)

    OUTDIR.mkdir(exist_ok=True)
    names = sys.argv[1:]

    print(f"\n=== Multi-Capture: {len(names)} Aktion(en) ===")
    print(f"Pro Aktion: {CAPTURE_SECONDS}s Capture.")
    print(f"OPTIMAL bei jedem Schritt:")
    print(f"  1. Aktion AUSFÜHREN (Taste drücken/halten)")
    print(f"  2. Enter mit anderer Hand → ● ● ● ● ● ● erscheinen je 0.5s")
    print(f"  3. 'FERTIG' kommt + Piepton → Taste loslassen")
    print()

    for i, name in enumerate(names, 1):
        path = OUTDIR / f"{name}.bin"
        print(f"────────────────────────────────────")
        print(f"  [{i}/{len(names)}]  Aktion: {name}")
        print(f"────────────────────────────────────")
        try:
            input(f"→ Taste DRÜCKEN, dann Enter  (Ctrl+C = Abbruch): ")
        except (KeyboardInterrupt, EOFError):
            print("\nAbgebrochen.")
            sys.exit(0)
        capture_to(path, CAPTURE_SECONDS)
        print(f"  Saved {path.name} ({path.stat().st_size} B)")
        quick_diff(name)
        print()

    print(f"\n═══ Alle {len(names)} Captures fertig ═══")


if __name__ == "__main__":
    main()
