#!/usr/bin/env python3
"""
Static analysis of an ARM Cortex-M firmware blob (IBEX/PROTEUS).

Without an external disassembler this script does:
  1) Parse the 32-byte header (magic, payload_size, checksum)
  2) Decode the Cortex-M vector table (Initial SP, Reset, exceptions, IRQs)
  3) Count function prologs (PUSH instructions) to estimate function counts
  4) Decode BL (Branch-with-Link) targets to identify common call sites
  5) Locate the .rodata section by ASCII density
  6) Extract real strings (length >= 8, in the rodata region)

Usage:
    tools/analyze_fw.py [path...]
    tools/analyze_fw.py --diff <fw_old> <fw_new>
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from collections import Counter
from pathlib import Path


CORTEX_M_EXCEPTIONS = [
    "Initial SP", "Reset", "NMI", "HardFault", "MemManage", "BusFault",
    "UsageFault", "Reserved_7", "Reserved_8", "Reserved_9", "Reserved_10",
    "SVCall", "DebugMonitor", "Reserved_13", "PendSV", "SysTick",
]


def is_thumb_push_prolog_16(b: bytes) -> bool:
    """PUSH {rN..rM, LR} 16-bit Thumb: 0xB5xx (LE: xx B5)."""
    return len(b) >= 2 and b[1] == 0xB5


def is_thumb_push_prolog_32(b: bytes) -> bool:
    """PUSH.W {r4-r11, LR} Thumb-2 32-bit: high-half 0xE92D."""
    if len(b) < 4:
        return False
    hh = b[0] | (b[1] << 8)
    return hh == 0xE92D


def find_bl_targets(code: bytes, base_address: int):
    """Decode all BL (32-bit Thumb-2) instructions, returning [(off, target)]."""
    targets = []
    i = 0
    n = len(code)
    while i < n - 3:
        hh = code[i] | (code[i + 1] << 8)
        lh = code[i + 2] | (code[i + 3] << 8)
        if (hh & 0xF800) == 0xF000 and (lh & 0xD000) == 0xD000:
            S = (hh >> 10) & 1
            imm10 = hh & 0x3FF
            J1 = (lh >> 13) & 1
            J2 = (lh >> 11) & 1
            imm11 = lh & 0x7FF
            I1 = (~(J1 ^ S)) & 1
            I2 = (~(J2 ^ S)) & 1
            imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1)
            if S:
                imm32 -= (1 << 25)
            target = (base_address + i + 4) + imm32
            targets.append((i, target))
            i += 4
        else:
            i += 2
    return targets


def parse_header(data: bytes):
    if len(data) < 32:
        return None
    magic, payload_size, checksum = struct.unpack_from("<3I", data, 0)
    reserved = struct.unpack_from("<5I", data, 12)
    return {
        "magic": magic,
        "payload_size": payload_size,
        "checksum": checksum,
        "reserved": reserved,
    }


def parse_vector_table(code: bytes, n_irqs: int = 64):
    initial_sp = struct.unpack_from("<I", code, 0)[0]
    sys_exc = []
    for i in range(1, 16):
        v = struct.unpack_from("<I", code, i * 4)[0]
        sys_exc.append((CORTEX_M_EXCEPTIONS[i], v))
    irqs = []
    for i in range(16, min(16 + n_irqs, len(code) // 4)):
        v = struct.unpack_from("<I", code, i * 4)[0]
        irqs.append((i - 16, v))
    return {
        "initial_sp": initial_sp,
        "reset_handler": sys_exc[0][1],
        "sys_exc": sys_exc,
        "irqs": irqs,
    }


def find_function_starts(code: bytes):
    """Find offsets where Thumb function prologs (PUSH ..., LR) appear."""
    starts = []
    i = 0
    while i < len(code) - 1:
        if is_thumb_push_prolog_16(code[i : i + 2]):
            starts.append(i)
            i += 2
        elif is_thumb_push_prolog_32(code[i : i + 4]):
            starts.append(i)
            i += 4
        else:
            i += 2
    return starts


def find_rodata_region(code: bytes, window: int = 256, threshold_pct: float = 50.0):
    """Find the longest contiguous block where ASCII-printable density >= threshold."""
    n = len(code)
    if n < window:
        return None
    cnt = sum(1 for b in code[:window] if 32 <= b < 127)
    starts_end = []  # [(start, end)] of all blocks
    in_block = False
    block_start = None
    for i in range(n - window):
        if i > 0:
            if 32 <= code[i + window - 1] < 127:
                cnt += 1
            if 32 <= code[i - 1] < 127:
                cnt -= 1
        rich = cnt >= (threshold_pct / 100.0) * window
        if rich and not in_block:
            in_block = True
            block_start = i
        elif not rich and in_block:
            starts_end.append((block_start, i + window))
            in_block = False
    if in_block:
        starts_end.append((block_start, n))
    if not starts_end:
        return None
    return max(starts_end, key=lambda x: x[1] - x[0])


def extract_strings(buf: bytes, min_len: int = 8, only_in_range=None):
    out = []
    i = 0
    n = len(buf)
    while i < n:
        if 32 <= buf[i] < 127:
            start = i
            while i < n and 32 <= buf[i] < 127:
                i += 1
            if i - start >= min_len:
                if only_in_range is None or (only_in_range[0] <= start <= only_in_range[1]):
                    out.append((start, buf[start:i].decode("ascii", errors="replace")))
        else:
            i += 1
    return out


def analyze(path: Path):
    data = path.read_bytes()
    h = parse_header(data)
    code = data[32:]
    vt = parse_vector_table(code)
    funcs = find_function_starts(code)
    bls = find_bl_targets(code, 0x0000_0000)
    rodata = find_rodata_region(code)
    strings = extract_strings(code, min_len=8, only_in_range=rodata)

    print(f"\n{'=' * 70}")
    print(f"  {path.name}  ({len(data):,} bytes)")
    print(f"{'=' * 70}")

    print(f"\nHeader:")
    print(f"  magic         = 0x{h['magic']:08X}")
    print(f"  payload_size  = {h['payload_size']:,}  (matches file: {h['payload_size'] + 32 == len(data)})")
    print(f"  checksum      = 0x{h['checksum']:08X}")

    print(f"\nVector Table:")
    print(f"  Initial SP    = 0x{vt['initial_sp']:08X}  (≈ {vt['initial_sp'] - 0x2000_0000:,} bytes into SRAM)")
    print(f"  Reset Handler = 0x{vt['reset_handler']:08X}  (offset 0x{(vt['reset_handler'] & ~1):X} in flash)")
    distinct_irq = len({v for _, v in vt["irqs"] if v != 0 and v != vt["initial_sp"]})
    print(f"  Distinct IRQ handlers in first 64: {distinct_irq}")

    print(f"\nCode analysis ({len(code):,} bytes of payload):")
    print(f"  Function prologs found:  ~{len(funcs):,}  (upper bound; some are false positives in data)")
    print(f"  BL call sites:            {len(bls):,}")

    call_target_counter = Counter(t for _, t in bls)
    print(f"  Top 5 most-called targets:")
    for target, count in call_target_counter.most_common(5):
        print(f"    0x{target:08X}  ←  {count:>4d} calls")

    print(f"\nrodata region (longest ASCII-rich block):")
    if rodata:
        ro_start, ro_end = rodata
        print(f"  Payload range: 0x{ro_start:X}..0x{ro_end:X}")
        print(f"  File range:    0x{ro_start + 32:X}..0x{ro_end + 32:X}")
        print(f"  Size:          {ro_end - ro_start:,} bytes")
    else:
        print(f"  (none found)")

    print(f"\nStrings (length >= 8, inside rodata): {len(strings)}")
    for off, s in strings[:30]:
        print(f"  @ 0x{off + 32:06X}: {s!r}")
    if len(strings) > 30:
        print(f"  ... ({len(strings) - 30} more)")

    return {
        "path": path,
        "header": h,
        "vector_table": vt,
        "function_count": len(funcs),
        "bl_count": len(bls),
        "rodata": rodata,
        "strings": strings,
    }


def diff_analyses(a, b):
    print(f"\n{'=' * 70}")
    print(f"  DIFF: {a['path'].name}  →  {b['path'].name}")
    print(f"{'=' * 70}")
    print(f"  payload_size:    {a['header']['payload_size']:>8,}  →  {b['header']['payload_size']:>8,}  (Δ {b['header']['payload_size'] - a['header']['payload_size']:+,})")
    print(f"  function prologs:{a['function_count']:>8,}  →  {b['function_count']:>8,}  (Δ {b['function_count'] - a['function_count']:+,})")
    print(f"  BL call sites:   {a['bl_count']:>8,}  →  {b['bl_count']:>8,}  (Δ {b['bl_count'] - a['bl_count']:+,})")
    print(f"  Reset handler:   0x{a['vector_table']['reset_handler']:08X}  →  0x{b['vector_table']['reset_handler']:08X}")

    a_strs = {s for _, s in a["strings"]}
    b_strs = {s for _, s in b["strings"]}
    added = b_strs - a_strs
    removed = a_strs - b_strs
    print(f"\n  Strings added in newer FW: {len(added)}")
    for s in sorted(added)[:10]:
        print(f"    + {s!r}")
    print(f"  Strings removed:           {len(removed)}")
    for s in sorted(removed)[:10]:
        print(f"    - {s!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--diff", nargs=2, type=Path, metavar=("OLD", "NEW"))
    args = parser.parse_args()

    if args.diff:
        diff_analyses(analyze(args.diff[0]), analyze(args.diff[1]))
        return

    files = args.files
    if not files:
        # Default: look in the standard Steam path
        default_dir = Path("/home/deck/.local/share/Steam/bin/hardwareupdater")
        if default_dir.exists():
            files = sorted(default_dir.glob("*.fw"))
    if not files:
        print("No .fw files. Pass paths as args.", file=sys.stderr)
        sys.exit(1)

    results = [analyze(f) for f in files]

    # Auto-diff per-codename pairs
    by_codename = {}
    for r in results:
        cn = r["path"].name.split("_")[0]
        by_codename.setdefault(cn, []).append(r)
    if any(len(v) >= 2 for v in by_codename.values()):
        print(f"\n{'=' * 70}")
        print(f"  Auto-diff per codename")
        print(f"{'=' * 70}")
        for cn, items in by_codename.items():
            if len(items) >= 2:
                items.sort(key=lambda x: x["path"].name)
                diff_analyses(items[0], items[-1])


if __name__ == "__main__":
    main()
