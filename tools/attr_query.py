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

By default this only sends opcodes from GET_OPCODES below, which are the
read-style entries of SDL3's `FeatureReportMessageIDs` enum. That is not a
guarantee: the enum is the generic Steam-Controller opcode map, and Triton
firmware is known to differ (`0x90` reboots to the bootloader and is not in
SDL3's enum at all). Treat every opcode as unverified on this hardware.

An earlier version of this file swept every opcode from 0x80 to 0xCF and
described itself as read-only. It was not: that range contains FACTORY_RESET
(0x86), CLEAR_SETTINGS_VALUES (0x88), TURN_OFF_CONTROLLER (0x9F),
CALIBRATE_TRACKPADS (0xA7), SET_SERIAL_NUMBER (0xA9), ENABLE_PAIRING (0xAD),
RADIO_ERASE_RECORDS (0xAF) and the reboot opcodes this repo documents itself.
The sweep now lives behind --dangerous-probe.
"""
from __future__ import annotations
import argparse
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

# Read-style opcodes from SDL3 `controller_constants.h` (FeatureReportMessageIDs).
# Everything not listed here is either known to mutate device state or unknown,
# and is only sent under --dangerous-probe.
GET_OPCODES: dict[int, str] = {
    0x82: "GET_DIGITAL_MAPPINGS",
    0x83: "GET_ATTRIBUTES_VALUES",
    0x84: "GET_ATTRIBUTE_LABEL",
    0x89: "GET_SETTINGS_VALUES",
    0x8A: "GET_SETTING_LABEL",
    0x8B: "GET_SETTINGS_MAXS",
    0x8C: "GET_SETTINGS_DEFAULTS",
    0xA1: "GET_DEVICE_INFO",
    0xAA: "GET_TRACKPAD_CALIBRATION",
    0xAB: "GET_TRACKPAD_FACTORY_CALIBRATION",
    0xAE: "GET_STRING_ATTRIBUTE",
    0xB4: "DONGLE_GET_WIRELESS_STATE",
    0xBA: "GET_CHIPID",
    0xC4: "DONGLE_GET_CONNECTED_SLOTS",
}

# Opcodes in 0x80..0xCF that are known to change persistent state or power.
# Shown to the user before --dangerous-probe runs.
DESTRUCTIVE_OPCODES: dict[int, str] = {
    0x80: "SET_DIGITAL_MAPPINGS",
    0x81: "CLEAR_DIGITAL_MAPPINGS",
    0x85: "SET_DEFAULT_DIGITAL_MAPPINGS",
    0x86: "FACTORY_RESET",
    0x87: "SET_SETTINGS_VALUES",
    0x88: "CLEAR_SETTINGS_VALUES",
    0x8D: "SET_CONTROLLER_MODE",
    0x8E: "LOAD_DEFAULT_SETTINGS",
    0x90: "REBOOT_TO_BOOTLOADER (Triton-specific, not in SDL3)",
    0x95: "FIRMWARE_UPDATE_REBOOT (Triton-specific, not in SDL3)",
    0x9F: "TURN_OFF_CONTROLLER",
    0xA7: "CALIBRATE_TRACKPADS",
    0xA9: "SET_SERIAL_NUMBER",
    0xAD: "ENABLE_PAIRING",
    0xAF: "RADIO_ERASE_RECORDS",
    0xB0: "RADIO_WRITE_RECORD",
    0xB1: "SET_DONGLE_SETTING",
    0xB2: "DONGLE_DISCONNECT_DEVICE",
    0xB3: "DONGLE_COMMIT_DEVICE",
    0xB5: "CALIBRATE_GYRO",
    0xB7: "AUDIO_UPDATE_START",
    0xB8: "AUDIO_UPDATE_DATA",
    0xB9: "AUDIO_UPDATE_COMPLETE",
    0xBF: "CALIBRATE_JOYSTICK",
    0xC0: "CALIBRATE_ANALOG_TRIGGERS",
    0xC1: "SET_AUDIO_MAPPING",
    0xC3: "CALIBRATE_ANALOG",
    0xCE: "RESET_IMU",
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


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"    ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def probe_range(dev: str, fr_id: int, opcodes: list[int], names: dict[int, str]):
    """Send each opcode once and print any non-empty response."""
    for op in opcodes:
        try:
            fd = os.open(dev, os.O_RDWR)
            try:
                send_feature(fd, pad_hid_fr(bytes([fr_id, op])))
                resp = get_feature(fd, fr_id, HID_LEN + 1)
                rl = resp[2]
                if rl > 0:
                    rt = resp[1]
                    data = resp[3 : 3 + rl]
                    label = names.get(op, "")
                    print(f"  fr_id={fr_id} op=0x{op:02x} {label:<34} "
                          f"type=0x{rt:02x} len={rl:>3d} data={data.hex()[:100]}")
            finally:
                os.close(fd)
        except OSError as e:
            if e.errno != 32:  # ignore broken-pipe spam
                print(f"  fr_id={fr_id} op=0x{op:02x}: {e}", file=sys.stderr)


def confirm_dangerous() -> bool:
    print("!" * 68)
    print(" --dangerous-probe sends EVERY opcode from 0x80 to 0xCF.")
    print(" That range includes commands which change persistent device state:")
    print("!" * 68)
    for op in sorted(DESTRUCTIVE_OPCODES):
        print(f"   0x{op:02x}  {DESTRUCTIVE_OPCODES[op]}")
    print()
    print(" Possible consequences: factory reset, wiped pairing/radio records,")
    print(" lost trackpad/gyro/joystick calibration, overwritten serial number,")
    print(" the device powering off or rebooting into its bootloader.")
    print()
    print(" Only do this on a device you are willing to re-pair and re-calibrate.")
    print(" Empty payloads MAY be rejected by the firmware. That is unverified.")
    print()
    return input(" Type 'I understand' to continue: ").strip() == "I understand"


def main():
    ap = argparse.ArgumentParser(description="Query SC2 device attributes via HID Feature-Reports.")
    ap.add_argument("--dev", default="/dev/hidraw9", help="hidraw node (default: /dev/hidraw9)")
    ap.add_argument("--dangerous-probe", action="store_true",
                    help="sweep ALL opcodes 0x80-0xCF, including state-changing ones")
    args = ap.parse_args()
    dev = args.dev

    print(f"=== Feature-Report probe on {dev} ===\n")

    print("=" * 60)
    print(" PUCK (Proteus) attributes: fr_id=2, op=0x83")
    print("=" * 60)
    safe(query_attributes, dev, 2, 0x83)

    print()
    print("=" * 60)
    print(" CONTROLLER (Triton via ESB) attributes: fr_id=1, op=0x83")
    print("=" * 60)
    safe(query_attributes, dev, 1, 0x83)

    for fr_id, who in ((1, "Controller"), (2, "Puck")):
        print()
        print("=" * 60)
        print(f" Read-style opcodes (fr_id={fr_id} = {who} path)")
        print("=" * 60)
        probe_range(dev, fr_id, sorted(GET_OPCODES), GET_OPCODES)

    if not args.dangerous_probe:
        print()
        print("Skipped the full 0x80-0xCF sweep. It can reset, re-pair, re-calibrate")
        print("or power off the device. Pass --dangerous-probe if you accept that.")
        return

    print()
    if not confirm_dangerous():
        print("Aborted.")
        return

    names = {**GET_OPCODES, **DESTRUCTIVE_OPCODES}
    for fr_id, who in ((1, "Controller"), (2, "Puck")):
        print()
        print("=" * 60)
        print(f" FULL opcode sweep (fr_id={fr_id} = {who} path)")
        print("=" * 60)
        probe_range(dev, fr_id, list(range(0x80, 0xD0)), names)


if __name__ == "__main__":
    main()
