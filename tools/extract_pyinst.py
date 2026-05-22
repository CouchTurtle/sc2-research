#!/usr/bin/env python3
"""Minimal PyInstaller bundle extractor — just enough to find the source."""
import struct
import os
import zlib
import sys

PATH = "/home/deck/.local/share/Steam/bin/hardwareupdater/hardwareupdater.x86_64"
OUT = "/tmp/hu_extracted"
os.makedirs(OUT, exist_ok=True)

with open(PATH, "rb") as f:
    data = f.read()

# Find the cookie magic at end
magic = b"MEI\x0c\x0b\n\x0b\x0e"
cookie_pos = data.rfind(magic)
print(f"Cookie at offset: {cookie_pos}")

# Cookie layout: magic(8) + length(4) + toc(4) + toclen(4) + pyver(4) + pylibname(64)
# Total = 88 bytes
length, toc, toclen, pyver = struct.unpack(">IIII", data[cookie_pos+8:cookie_pos+24])
pylib = data[cookie_pos+24:cookie_pos+88].rstrip(b"\x00").decode("ascii", errors="replace")
print(f"  archive length: {length}")
print(f"  TOC pos: {toc}")
print(f"  TOC len: {toclen}")
print(f"  Python: {pyver}")
print(f"  Lib: {pylib}")

# Archive starts at: cookie_pos + 88 - length
archive_start = cookie_pos + 88 - length
print(f"  Archive start: {archive_start}")
toc_start_abs = archive_start + toc
toc_end_abs = toc_start_abs + toclen
print(f"  TOC abs range: {toc_start_abs} .. {toc_end_abs}")

# Parse TOC — each entry: entry_size(4) + data_pos(4) + data_size(4) + uncompressed_size(4)
#                         + cflag(1) + typecmprs(1) + name(...)
i = toc_start_abs
toc_entries = []
while i < toc_end_abs:
    entry_size = struct.unpack(">I", data[i:i+4])[0]
    pos, size, uncompr = struct.unpack(">III", data[i+4:i+16])
    cflag = data[i+16]
    ctype = chr(data[i+17])
    name = data[i+18 : i+entry_size].rstrip(b"\x00").decode("utf-8", errors="replace")
    toc_entries.append((name, pos, size, uncompr, cflag, ctype))
    i += entry_size

print(f"\nTOC entries: {len(toc_entries)}")
print(f"{'name':<60s} {'cflag':>5s} {'type':>4s} {'size':>10s} {'uncomp':>10s}")
for name, pos, size, uncompr, cflag, ctype in toc_entries[:40]:
    print(f"  {name:<58s} {cflag:>5d}  {ctype:>4s}  {size:>10d}  {uncompr:>10d}")
print(f"... ({len(toc_entries)} total)")

# Extract everything
for name, pos, size, uncompr, cflag, ctype in toc_entries:
    raw = data[archive_start + pos : archive_start + pos + size]
    if cflag:
        try:
            raw = zlib.decompress(raw)
        except Exception as e:
            print(f"  !! decompress failed for {name}: {e}")
            continue
    # Build safe filename
    safe = name.replace("/", "_").replace("..", "_")
    if ctype == "s":  # source
        outpath = os.path.join(OUT, safe + ".py")
    elif ctype == "m":  # importable module
        outpath = os.path.join(OUT, safe + ".pyc")
    elif ctype == "M":  # bootloader's package marker
        outpath = os.path.join(OUT, safe + ".pyc")
    elif ctype == "z":  # PYZ archive
        outpath = os.path.join(OUT, safe + ".pyz")
    else:
        outpath = os.path.join(OUT, safe)
    with open(outpath, "wb") as f:
        f.write(raw)
print(f"\nExtracted to: {OUT}")
