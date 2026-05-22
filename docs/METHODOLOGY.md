# Reverse-Engineering Methodology & Lessons Learned

A collection of non-obvious lessons from this Triton/SC2 RE project. Intended for other reverse-engineers, or as a reminder when starting similar hardware projects.

## TL;DR

- **Look for vendor SDK / open-source contributions first** — Valve commits Triton driver code directly to SDL3, which gives you the entire wire format for free.
- **Codenames are layered** — marketing name ≠ internal name ≠ firmware filename. Find one and grep for all the others.
- **`#pragma pack(1)` lies** about field boundaries: high bytes of an `int16` can look like a fake flag in the next byte. Always confirm the surrounding field before declaring a single bit.
- **Capture-timing sync is fragile** — auto-countdown + background process = invalid data when the user can't see the clock. Use interactive Enter or a foreground tool.
- **Bytecode disassembly works without a decompiler** — `marshal.loads()` + `dis.dis()` from Python's stdlib is enough to reverse PyInstaller bundles when no decompiler supports the target Python version.
- **SteamOS sandbox quirks** matter for tooling: the `deck` user has more HID access than `root` via ACLs.

## Table of Contents

- [General Strategy](#general-strategy)
- [Technical Patterns](#technical-patterns)
- [Reusable Tooling Patterns](#reusable-tooling-patterns)
- [Anti-Patterns We Hit](#anti-patterns-we-hit)

## General Strategy

### 1. Authoritative sources before empiricism

Before guessing bytes for hours: search for SDK / open-source releases from the vendor. For Valve it was:
- **SDL3 mainline code** (Valve commits directly to libsdl-org/SDL): `controller_structs.h`, `SDL_hidapi_steam_triton.c` → complete wire format
- **PyInstaller tools** shipped locally on the device: `hardwareupdater.x86_64` contains the entire update stack in Python
- **Log files with symbol leaks**: `~/.local/share/Steam/logs/controller.txt` contains C++ class names like `CGetTritonDonglePairingBondWorkItem`

Empirical captures then become **verification**, not discovery. Saves hours.

### 2. Codename discipline

Vendors often use 3+ names for the same thing. For Triton/SC2:
- **Marketing**: "Steam Controller 2" (SC2)
- **Internal codename**: "Triton" (controller), "Proteus" (puck), "Nereid" (unknown)
- **Firmware filename**: "IBEX" (= Triton internally), "PROTEUS" (= puck)
- **Wireless protocol**: "ESB" (Enhanced ShockBurst, Nordic Semi)

When you know one name, grep all related binaries for **all the symbols** — additional codenames often pop out as string constants.

### 3. Privacy hygiene

Redact before sharing:
- Serial numbers (hardware-specific, traceable)
- USB iSerial strings
- MAC addresses
- Per-device calibration data

Not redaction-worthy (even if it looks like it should be):
- Firmware file hashes (per-build, not per-unit)
- Hardware IDs (model revisions, not unit serials)

## Technical Patterns

### Bit-flag analysis is dangerous under `#pragma pack(1)`

**Cautionary tale**: We initially identified an "InHand" flag at byte 0x0b bit 1 — it looked like a capacitive-touch sensor (0% idle → 100% when controller held).

It was actually **an overflow** from the neighbouring `sLeftStickX` int16 field (bytes 0x0a-0x0b). When the stick bias drifts into range 512-767, the high byte equals `0x02..0x03`, which sets bit 1.

**Rule**: For any "new flag" that shows a consistent bit pattern, **first** clarify the surrounding-field context:
- Is it a sign bit of an adjacent int16/int32?
- Is it a value-range effect (`high byte` of an analog field)?
- Only when the surrounding field is safely assigned can the bit stand on its own.

`#pragma pack(1)` makes this doubly important — no padding bytes as natural separators.

See also: [HID_REPORT_FORMAT.md](HID_REPORT_FORMAT.md) for the resolved layout.

### Capture-timing sync is critical

**Anti-pattern**: Tool with auto-countdown started in the background, user supposed to perform the action during the countdown. When the user doesn't see the countdown (other terminal, no `tail -f`), the action-to-capture mapping breaks → hours of data become useless.

**Pattern**: Live monitor in the terminal the user actively sees. Tool waits for Enter, user triggers when ready. One capture file per action with a descriptive name.

### On sync drift: source code as ground truth

When empirical tests are compromised by sync errors: **don't** keep arguing with questionable data. Take the authoritative source code as truth, treat captures only as spot-check.

Example: Our mapping captures had wrong action labels due to sync drift. But the individual captures clearly showed which bytes/bits were active. With SDL's `TritonButtons` table as schema, we could retroactively show that the captures are consistent with the table — even though the labels were wrong. No empirical re-verification needed.

### Identifying firmware files: magic bytes over filenames

Vendors name firmware files creatively (codenames, timestamps, project IDs). Instead of searching filenames, **search by magic bytes**:
- `head -c 4 *.bin` and match magic values against the `*_MAGIC` constants from source code
- For multiple firmware files: compare first bytes, identical magic = same firmware family

For Triton: `0xD2D86467` LE for Triton/IBEX, `0x2E795631` LE for Proteus. Extracted from `hardwareupdater.py` as constants, then validated against the 4 local .fw files — perfect match.

See also: [FIRMWARE_PROTOCOL.md](FIRMWARE_PROTOCOL.md) for the full header layout.

### PyInstaller bundles are gold mines

When a vendor tool is a single Python executable (8-100 MB), check if it's a **PyInstaller bundle**:
1. Search for the magic `MEI\x0c\x0b\n\x0b\x0e` at the end of the file
2. If present: parse the TOC → contains all Python modules uncompiled
3. Modules are stored as **marshalled code objects** (no .pyc magic header)
4. Load directly with `marshal.loads(open(f).read())`
5. `dis.dis()` for bytecode disassembly — no external decompiler needed

Reusable script for this: `tools/extract_pyinst.py`.

### Bytecode disassembly instead of decompilation

Python 3.12 decompiler support is poor (`uncompyle6` max 3.8, `decompyle3` max 3.9, `pycdc` is build-from-source). **But**: `dis.dis()` from the stdlib shows bytecode readable enough to reconstruct function logic. Plus:
- `co.co_consts` shows all string/int/bytes constants
- `co.co_names` shows all referenced names (method/attribute names)
- `co.co_varnames[:co.co_argcount]` shows the argument names

That alone is enough to handle small tools without a decompiler.

### SteamOS sandbox: less than the user sees

Claude Code's bash sandbox on SteamOS has a restricted path:
- `/usr/bin/podman` not there, but `/run/host/usr/bin/podman` is (with missing libs)
- `flatpak-spawn` is not installed
- `distrobox enter` fails due to missing container runtime
- `file`, `strings` may be missing

Workarounds:
- Python stdlib is almost always available → write your own tools in Python instead of relying on CLI utilities
- `head -c N | python3 -c "..."` for hex/string ops instead of `xxd`/`strings`

### SteamOS hidraw permissions: deck > root

`/dev/hidraw*` and `/dev/ttyACM*` have ACLs that **grant the `deck` user access but block root**:
```
crw-rw----+ 1 nobody nogroup 245, 9 /dev/hidraw9
```
The `+` indicates an extended POSIX ACL. Sudo leads to EACCES, without sudo it works.

Corollary: If a hidraw tool gives "Permission denied" with sudo, **try without sudo**. Especially on Steam Deck.

### Steam grabs are not exclusive

Initial assumption: "Steam blocks all HID interfaces of the puck exclusively". Reality: Steam is running, and we can still read `/dev/hidraw9` as the `deck` user. Steam and our tools coexist without problems.

(Lizard-mode reports only appear when Steam is dead — see [HID_REPORT_FORMAT.md](HID_REPORT_FORMAT.md).)

### Live Feature-Reports work with Linux ioctl directly

No `hid` Python package needed:
```python
HIDIOCSFEATURE(N) = _IOC(WRITE|READ, 'H', 0x06, N)
HIDIOCGFEATURE(N) = _IOC(WRITE|READ, 'H', 0x07, N)
```
Use with `os.open(O_RDWR)` and `fcntl.ioctl` directly. Buffer format: first byte = Report ID, rest = payload (write) or response (read).

### Multi-device routing via fr_id

For a wireless dongle: the same HID path is often a **bidirectional multiplexer** between local dongle firmware and the wireless-attached device. For Triton/Proteus:
- `fr_id=2` with `op=0x83` → response from the puck itself (local)
- `fr_id=1` with `op=0x81` → response from the controller (routed via ESB)

→ Collect ALL fr_id/op combinations via brute-force (0x80..0xCF, both fr_ids). What comes back tells you which channels exist.

## Reusable Tooling Patterns

| Script | Reusable for |
|---|---|
| `tools/event_logger.py` | Parallel listen on multiple hidraw nodes, count report IDs, timestamp sub-reports |
| `tools/live_monitor.py` | Stream decoder that only shows transitions (instead of 266 Hz spam) |
| `tools/one_capture.py` | Targeted single-action capture with diff against baseline |
| `tools/extract_pyinst.py` | Extract PyInstaller bundles via MEI cookie parsing |
| `tools/walk_pyc.py` | Recursively walk Python code objects, list functions + constants |
| `tools/attr_query.py` | Live HID Feature-Report queries via `ioctl`, no `hid` package needed |
| `tools/analyze_fw.py` | Pure-Python ARM Cortex-M firmware analyzer |

All reusable for other vendor-specific HID devices.

## Anti-Patterns We Hit

1. ❌ Auto-countdown mapper started in the background → user saw nothing → broken data
2. ❌ "Sticks only go to ±700" documented prematurely based on an inactive capture
3. ❌ "InHand flag" identified as capacitive sensor without checking the stick value range
4. ❌ `pkill -f "steam.sh|..."` executed — pkill matched its own shell command line and killed the controlling bash
5. ❌ `sudo` tried for hidraw access — worse than without sudo due to SteamOS ACLs
6. ❌ A 24-byte "Per-Device-Constant" identified as calibration — was actually the IMU+Quat block in OFF mode

Each of these mistakes is a concrete lesson. Worth re-reading before starting a similar project.
