# RE notes & lessons

Notes from working through the Triton/SC2 firmware and HID stack on a Steam Deck. Mostly things that weren't obvious at the start and would have saved time if known up front.

## Summary

- Vendor SDK / open-source contributions first. Valve commits Triton driver code directly to SDL3, so the wire format is free.
- Codenames are layered: marketing name ≠ internal name ≠ firmware filename. Find one, grep for the others.
- `#pragma pack(1)` makes adjacent-field bits look like flags. Confirm the surrounding field before naming a bit.
- Capture-timing sync is fragile: auto-countdown + background process = invalid data when the user can't see the clock. Use interactive Enter or a foreground tool.
- Bytecode disassembly works without a decompiler: `marshal.loads()` + `dis.dis()` from Python's stdlib are enough for PyInstaller bundles.
- SteamOS hidraw ACLs: the `deck` user has more access than `root`. Don't `sudo`.

## Table of Contents

- [General Strategy](#general-strategy)
- [Technical Patterns](#technical-patterns)
- [Reusable Tooling Patterns](#reusable-tooling-patterns)
- [Anti-Patterns We Hit](#anti-patterns-we-hit)

## Where to look first (for this specific project)

For Triton/SC2 specifically, the three highest-leverage sources are:
- **SDL3 mainline** (Valve commits the driver directly): `controller_structs.h`, `SDL_hidapi_steam_triton.c` → complete wire format for Report 0x42, all 30 button bits, MTU structs
- **`~/.local/share/Steam/bin/hardwareupdater/hardwareupdater.x86_64`**: PyInstaller bundle containing the entire update stack in Python 3.12
- **`~/.local/share/Steam/logs/controller.txt`**: leaks Steam-internal C++ class names like `CGetTritonDonglePairingBondWorkItem`

With those three, empirical captures become **verification**, not discovery.

The codenames are layered: marketing "Steam Controller 2" / hardware "Ibex" or "Triton" / firmware-filename "IBEX_FW" / Wireless "ESB". `Triton` and `Ibex` were datamined publicly in Q4 2025; `Proteus` (puck) and `Nereid` (the receiver built into the Steam Machine, `EDeviceType=6`) come out of `hardwareupdater.py` and are first publicly documented in this project. When you have one name, grep every binary for related strings. The others fall out.

Privacy: redact USB iSerial strings and per-device serial numbers (`FX*`) before sharing captures. Firmware file hashes and the `hardware_id` integer (model revision) are not PII.

## Technical Patterns

### Concrete case: the "InHand" flag that wasn't

We identified what looked like a sticky capacitive-touch flag at byte `0x0b` bit 1: 0 % at idle, 100 % when controller held. Plausible, internally consistent, "found" within a day.

It was actually the **high byte of `sLeftStickX`** (bytes `0x0a-0x0b`). When the stick is biased into the 512-767 range (which happens systematically while holding the controller because of grip-induced tilt), the high byte is `0x02..0x03`, which sets bit 1.

The fix took 5 minutes once the SDL3 struct layout was in front of us; the rabbit hole had taken a day.

Lesson formalised: under `#pragma pack(1)` there are no padding bytes between fields, so the high bits of any non-zero-centred analog field will systematically light up bits in the "next" byte. Any "new bit-flag" that correlates with a known analog signal is the analog signal, not a flag. Confirm the surrounding-field assignment from authoritative layout before naming a bit.

See also: [HID_REPORT_FORMAT.md](HID_REPORT_FORMAT.md) for the verified layout.

### Capture-timing sync is critical

**Anti-pattern**: Tool with auto-countdown started in the background, user supposed to perform the action during the countdown. When the user doesn't see the countdown (other terminal, no `tail -f`), the action-to-capture mapping breaks → hours of data become useless.

**Pattern**: Live monitor in the terminal the user actively sees. Tool waits for Enter, user triggers when ready. One capture file per action with a descriptive name.

### On sync drift: source code as ground truth

When empirical tests are compromised by sync errors: **don't** keep arguing with questionable data. Take the authoritative source code as truth, treat captures only as spot-check.

Example: Our mapping captures had wrong action labels due to sync drift. But the individual captures clearly showed which bytes/bits were active. With SDL's `TritonButtons` table as schema, we could retroactively show that the captures are consistent with the table, even though the labels were wrong. No empirical re-verification needed.

### Identifying firmware files: magic bytes over filenames

Vendors name firmware files creatively (codenames, timestamps, project IDs). Instead of searching filenames, **search by magic bytes**:
- `head -c 4 *.bin` and match magic values against the `*_MAGIC` constants from source code
- For multiple firmware files: compare first bytes, identical magic = same firmware family

For Triton: `0xD2D86467` LE for Triton/IBEX, `0x2E795631` LE for Proteus. Extracted from `hardwareupdater.py` as constants, then validated against the 4 local .fw files: perfect match.

See also: [FIRMWARE_PROTOCOL.md](FIRMWARE_PROTOCOL.md) for the full header layout.

### PyInstaller bundles are gold mines

When a vendor tool is a single Python executable (8-100 MB), check if it's a **PyInstaller bundle**:
1. Search for the magic `MEI\x0c\x0b\n\x0b\x0e` at the end of the file
2. If present: parse the TOC → contains all Python modules uncompiled
3. Modules are stored as **marshalled code objects** (no .pyc magic header)
4. Load directly with `marshal.loads(open(f).read())`
5. `dis.dis()` for bytecode disassembly (no external decompiler needed)

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

(Lizard-mode reports only appear when Steam is dead; see [HID_REPORT_FORMAT.md](HID_REPORT_FORMAT.md).)

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
- `fr_id=1` with `op=0x83` → response from the controller (routed via ESB). Same opcode, `fr_id` selects the target

→ To find out which channels exist, walk the **read** opcodes for each `fr_id` and see what answers.

Do not sweep the whole `0x80..0xCF` range on hardware you care about, which is what an earlier version of this section suggested. SDL3's `FeatureReportMessageIDs` puts `FACTORY_RESET` (`0x86`), `CLEAR_SETTINGS_VALUES` (`0x88`), `TURN_OFF_CONTROLLER` (`0x9F`), `CALIBRATE_TRACKPADS` (`0xA7`), `SET_SERIAL_NUMBER` (`0xA9`), `ENABLE_PAIRING` (`0xAD`) and `RADIO_ERASE_RECORDS` (`0xAF`) in that range, and the reboot opcodes documented in [`FIRMWARE_PROTOCOL.md`](FIRMWARE_PROTOCOL.md) (`0x90`, `0x95`) sit in it too. An empty payload might get rejected, but nothing guarantees that. `tools/attr_query.py` sends the read-style opcodes by default and keeps the full sweep behind `--dangerous-probe`.

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
4. ❌ `pkill -f "steam.sh|..."` executed: pkill matched its own shell command line and killed the controlling bash
5. ❌ `sudo` tried for hidraw access: worse than without sudo due to SteamOS ACLs
6. ❌ A 24-byte "Per-Device-Constant" identified as calibration was actually the IMU+Quat block in OFF mode
7. ❌ Claimed nRF52840, "correcting" the teardowns, from the `gpio1`/`i2s` Device-Tree nodes, but those peripherals exist on the nRF52833 too. A *present* peripheral only proves a family lower-bound; the *absent* high-end ones (QSPI, CryptoCell) plus flash/RAM size identify the part. The teardowns (nRF52833) were right; confirmed later by the `mwdmwd/sc26re` firmware, which targets nRF52833.

Each of these mistakes is a concrete lesson. Worth re-reading before starting a similar project.
