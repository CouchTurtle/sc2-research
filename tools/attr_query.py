#!/usr/bin/env python3
"""
Live test: query device attributes via HID Feature-Reports.

Reverse-engineered from hardwareupdater.x86_64 (Steam's PyInstaller bundle).
Send a query like (fr_id, opcode) padded to 64 bytes via HIDIOCSFEATURE,
then read the response via HIDIOCGFEATURE.

Wire format (response):
  byte 0: report_id  (= fr_id)
  byte 1: report_type (= echo of opcode)
  byte 2: report_length
  byte 3..3+length: report_bytes

For opcode 0x83 (attribute values), report_bytes is a list of
<uint8 tag><uint32 LE value> entries (5 bytes each).

For opcode 0xAE / 0xA4 / 0xA6 (strings), it's a single null-terminated string
preceded by a skip byte.

This is READ-ONLY in effect — we don't change any persistent device state.
"""
from __future__ import annotations
import fcntl
import os
import struct
import sys

# Linux ioctl encoding (x86_64)
def _IOC(d, t, n, s):
    return (d << 30) | (s << 16) | (t << 8) | n

HIDIOCGRAWINFO = _IOC(2, ord("H"), 0x03, 8)
def HIDIOCSFEATURE(n): return _IOC(3, ord("H"), 0x06, n)
def HIDIOCGFEATURE(n): return _IOC(3, ord("H"), 0x07, n)

HID_LEN = 64

ATTR_NAMES = {
    0: "unique_id",
    1: "product_id",
    2: "capabilities",
    4: "build_timestamp",
    5: "radio_build_timestamp",
    9: "hw_id",
    10: "boot_build_timestamp",
    11: "frame_rate",
    12: "secondary_build_timestamp",
    13: "secondary_boot_build_timestamp",
    14: "secondary_hw_id",
    15: "data_streaming",
    16: "trackpad_id",
    17: "secondary_trackpad_id",
}


def get_raw_info(fd):
    buf = bytearray(8)
    fcntl.ioctl(fd, HIDIOCGRAWINFO, buf, True)
    bustype, vendor, product = struct.unpack("=ihh", bytes(buf))
    return bustype, vendor & 0xFFFF, product & 0xFFFF


def send_feature(fd, report: bytes):
    buf = bytearray(report)
    fcntl.ioctl(fd, HIDIOCSFEATURE(len(buf)), buf, True)


def get_feature(fd, fr_id: int, length: int = 65) -> bytes:
    buf = bytearray([fr_id] + [0] * (length - 1))
    n = fcntl.ioctl(fd, HIDIOCGFEATURE(length), buf, True)
    return bytes(buf[:n]) if n > 0 else bytes(buf)


def pad_hid_fr(blob: bytes) -> bytes:
    return blob + b"\x00" * (HID_LEN - len(blob))


def query_attributes(devpath: str, fr_id: int, opcode: int) -> tuple[bytes, dict] | None:
    """Send (fr_id, opcode) and read the 0x83-style attribute response."""
    fd = os.open(devpath, os.O_RDWR)
    try:
        bus, vid, pid = get_raw_info(fd)
        print(f"  {devpath}: bustype={bus:#x} vid={vid:#06x} pid={pid:#06x}")
        # Build query: [fr_id, opcode] padded to 64 bytes
        send_feature(fd, pad_hid_fr(bytes([fr_id, opcode])))
        # Read response: HID_LEN+1 bytes (1 report-id + 64 data)
        resp = get_feature(fd, fr_id, HID_LEN + 1)
        if len(resp) < 3:
            print(f"    too short: {resp.hex()}")
            return None
        report_type = resp[1]
        report_length = resp[2]
        report_bytes = resp[3 : 3 + report_length]
        print(f"    response: rid=0x{resp[0]:02x} type=0x{report_type:02x} len={report_length} data={report_bytes.hex()}")
        # Decode attribute table
        attrs = {}
        if report_length and report_length % 5 == 0:
            num = report_length // 5
            for i in range(num):
                tag = report_bytes[i * 5]
                val = struct.unpack_from("<I", report_bytes, i * 5 + 1)[0]
                name = ATTR_NAMES.get(tag, f"tag_0x{tag:02x}")
                attrs[name] = val
        return resp, attrs
    finally:
        os.close(fd)


def query_str_attribute(devpath: str, fr_id: int, op: int, attribute_number: int = 0):
    """Read a string attribute (serial, etc.)."""
    fd = os.open(devpath, os.O_RDWR)
    try:
        # struct.pack('=bBbb', fr_id, op, 1, attribute_number)
        blob = struct.pack("=bBbb", fr_id, op, 1, attribute_number)
        send_feature(fd, pad_hid_fr(blob))
        resp = get_feature(fd, fr_id, HID_LEN + 1)
        if len(resp) < 3:
            return None
        rt, rl = resp[1], resp[2]
        data = resp[3 : 3 + rl]
        if rt != op:
            return ("WRONG_TYPE", rt, data)
        # Skip first byte (per code), then decode null-terminated UTF-8
        if not data or data[0] == 0xFF:
            return ("Not Provisioned",)
        data = data[1:]
        nul = data.find(b"\x00")
        if nul == -1:
            return ("no null", data)
        try:
            s = data[:nul].decode("utf-8")
        except UnicodeDecodeError:
            s = data[:nul].hex()
        return (s, data[:nul])
    finally:
        os.close(fd)


def probe_opcodes(devpath: str, fr_id: int, opcodes: list[int]):
    """Try many opcodes and show whatever comes back."""
    fd = os.open(devpath, os.O_RDWR)
    try:
        for op in opcodes:
            try:
                send_feature(fd, pad_hid_fr(bytes([fr_id, op])))
                resp = get_feature(fd, fr_id, HID_LEN + 1)
                rt = resp[1]
                rl = resp[2]
                data = resp[3 : 3 + rl]
                if rl > 0:
                    print(f"    op=0x{op:02x}: type=0x{rt:02x} len={rl} data={data.hex()[:80]}")
                else:
                    pass  # silently skip empty
            except OSError as e:
                if e.errno != 32:  # ignore broken pipe spam
                    print(f"    op=0x{op:02x}: {e}")
    finally:
        os.close(fd)


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def main():
    dev = "/dev/hidraw9"
    print(f"=== Live Feature-Report probe on {dev} ===\n")

    print("=" * 60)
    print(" PUCK (Proteus) attributes — fr_id=2, op=0x83")
    print("=" * 60)
    safe(query_attributes, dev, 2, 0x83)

    print()
    print("=" * 60)
    print(" CONTROLLER (Triton via ESB) attributes — fr_id=1, op=0x83")
    print("=" * 60)
    safe(query_attributes, dev, 1, 0x83)

    print()
    print("=" * 60)
    print(" Brute-force opcode probe (fr_id=1 = Controller path)")
    print("=" * 60)
    for op in range(0x80, 0xD0):
        try:
            fd = os.open(dev, os.O_RDWR)
            try:
                send_feature(fd, pad_hid_fr(bytes([1, op])))
                resp = get_feature(fd, 1, HID_LEN + 1)
                rl = resp[2]
                if rl > 0:
                    rt = resp[1]
                    data = resp[3 : 3 + rl]
                    print(f"  fr_id=1 op=0x{op:02x}: type=0x{rt:02x} len={rl:>3d} data={data.hex()[:100]}")
            finally:
                os.close(fd)
        except OSError as e:
            if e.errno != 32:
                print(f"  fr_id=1 op=0x{op:02x}: {e}")

    print()
    print("=" * 60)
    print(" Brute-force opcode probe (fr_id=2 = Puck path)")
    print("=" * 60)
    for op in range(0x80, 0xD0):
        try:
            fd = os.open(dev, os.O_RDWR)
            try:
                send_feature(fd, pad_hid_fr(bytes([2, op])))
                resp = get_feature(fd, 2, HID_LEN + 1)
                rl = resp[2]
                if rl > 0:
                    rt = resp[1]
                    data = resp[3 : 3 + rl]
                    print(f"  fr_id=2 op=0x{op:02x}: type=0x{rt:02x} len={rl:>3d} data={data.hex()[:100]}")
            finally:
                os.close(fd)
        except OSError as e:
            if e.errno != 32:
                print(f"  fr_id=2 op=0x{op:02x}: {e}")


if __name__ == "__main__":
    main()
