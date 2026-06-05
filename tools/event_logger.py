#!/usr/bin/env python3
"""
Parallel event logger for hidraw9 (state) + hidraw13 (status channel).

Records every report from both interfaces for a fixed duration, then prints
a summary of unique report types seen and where. The 0x42 state reports
from hidraw9 are saved raw but suppressed from the text log to keep noise down.

Usage:
    python3 tools/event_logger.py [seconds]   # default 60s

Device paths are hardcoded to /dev/hidraw9..13 (the typical puck enumeration
on a fresh Steam Deck where the puck is the only USB-HID block after the
internal devices). Adjust the DEVICES list below if your enumeration differs.
"""
import os
import sys
import time
import threading

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0

DEVICES = ["/dev/hidraw9", "/dev/hidraw10", "/dev/hidraw11",
           "/dev/hidraw12", "/dev/hidraw13"]

OUTDIR = "event_log"
os.makedirs(OUTDIR, exist_ok=True)
LOG = open(f"{OUTDIR}/events.log", "w", buffering=1)
RAW_FILES = {}
for dev in DEVICES:
    name = dev.split("/")[-1]
    RAW_FILES[dev] = open(f"{OUTDIR}/{name}.bin", "wb", buffering=0)
LOCK = threading.Lock()

START = time.monotonic()
report_counts = {}


def log_event(source: str, data: bytes, t: float):
    if not data:
        return
    rid = data[0]
    with LOCK:
        report_counts[(source, rid)] = report_counts.get((source, rid), 0) + 1
        # Suppress the noisy 0x42 state spam — count it but don't print every one
        if source == "hidraw9" and rid == 0x42:
            return
        LOG.write(f"[t+{t - START:6.2f}s] {source} rid=0x{rid:02x} "
                  f"({len(data)}B): {data.hex()}\n")


def loop(device: str):
    source = device.split("/")[-1]
    raw_file = RAW_FILES[device]
    try:
        fd = os.open(device, os.O_RDONLY)
    except OSError as e:
        with LOCK:
            LOG.write(f"!! {source}: open failed: {e}\n")
        return
    try:
        while True:
            try:
                data = os.read(fd, 256)
            except OSError as e:
                with LOCK:
                    LOG.write(f"!! {source}: read failed: {e}\n")
                return
            t = time.monotonic()
            raw_file.write(data)
            log_event(source, data, t)
    finally:
        os.close(fd)


print(f"Logging {len(DEVICES)} hidraw devices for {DURATION}s …", flush=True)
print(f"Devices: {', '.join(DEVICES)}")
print(f"Output dir: {OUTDIR}/")
print()

for dev in DEVICES:
    threading.Thread(target=loop, args=(dev,), daemon=True).start()
time.sleep(DURATION)

print()
print(f"=== Summary ({DURATION:.0f}s) ===")
for (src, rid), n in sorted(report_counts.items()):
    print(f"  {src:>10s}  rid=0x{rid:02x}  count={n}")
print()
print(f"Full text log: {OUTDIR}/events.log")
print(f"Raw streams:   {OUTDIR}/hidraw9.bin, {OUTDIR}/hidraw13.bin")

LOG.close()
for f in RAW_FILES.values():
    f.close()
