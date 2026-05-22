# sc2-research

Reverse-engineering documentation and tooling for the **Steam Controller 2** (codename "Triton"), its wireless dongle ("Proteus" / "Vigor", USB `28DE:1304`), and Valve's firmware-update mechanism.

Status: input protocol fully documented, firmware update protocol fully reverse-engineered (HDLC framing, message IDs, mode-switching), live-verified against the actual hardware on SteamOS.

## What you'll find here

| Path | Contents |
|---|---|
| [`docs/HID_REPORT_FORMAT.md`](docs/HID_REPORT_FORMAT.md) | The 54-byte Report-0x42 controller-state layout — all 30 buttons, analog axes, IMU. Lizard-Mode behaviour, sub-reports 0x43/0x7b. Empirically verified. |
| [`docs/CONTROLLER_CAPABILITIES.md`](docs/CONTROLLER_CAPABILITIES.md) | Hardware inventory: TMR-sticks, Hall-triggers, haptic trackpads, IMU, IR-LEDs, 4× LRA actuators, battery telemetry, connectivity modes. |
| [`docs/FIRMWARE_PROTOCOL.md`](docs/FIRMWARE_PROTOCOL.md) | The full update protocol: HDLC framing, message IDs, firmware-file header format, mode-switching between HID and CDC ACM bootloader, live-verified Feature-Report attribute queries. Plus initial Cortex-M analysis (Nordic nRF52). |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | Lessons learned doing this work. Anti-patterns to avoid, traps with `#pragma pack(1)`, SteamOS sandbox quirks, capture-timing pitfalls. Useful for similar projects. |
| [`sc2/decoder.py`](sc2/decoder.py) | Python library: parse a hidraw stream, decode Report 0x42 frames, walk all 30 buttons by name, expose analog fields. |
| [`tools/`](tools/) | Standalone reusable scripts — see below. |
| [`captures/`](captures/) | Sample binary captures (idle + Steam-button-press) for offline testing. |

## Tools

All Python 3.10+, stdlib only (no pip dependencies). Run as the `deck` user on SteamOS (NOT sudo — that's blocked by the ACL).

| Tool | What it does |
|---|---|
| `tools/live_monitor.py` | Streams `/dev/hidraw9`, prints button transitions by SDL name and analog deflection. Real-time. |
| `tools/attr_query.py` | Sends HID Feature-Reports directly via `ioctl` to query device attributes (`build_timestamp`, `hw_id`, `frame_rate`, …). Live-tested on Proteus puck. |
| `tools/one_capture.py NAME [NAME...]` | Capture 3s of hidraw9 traffic per named action; auto-diff vs a baseline. For systematic input mapping. |
| `tools/event_logger.py [seconds]` | Parallel logger across hidraw9–13; summarizes report-IDs seen per interface. |
| `tools/extract_pyinst.py` | Minimal PyInstaller bundle extractor (MEI-cookie parser → marshal/zlib). Used to crack open `hardwareupdater.x86_64`. |
| `tools/walk_pyc.py` | Walks a marshaled Python code object, lists nested functions with signatures + interesting constants. For bytecode reverse engineering when no decompiler supports the target Python version. |
| `tools/analyze_fw.py` | Parses ARM Cortex-M firmware blobs (header, vector table, IRQ handlers, embedded strings). |

## Quick start

```bash
git clone <this-repo>
cd sc2-research

# Live monitor — press buttons, see decoded transitions
python3 tools/live_monitor.py

# Query the Puck firmware version directly
python3 tools/attr_query.py

# Parse a sample capture offline
python3 -c "from sc2 import iter_state_frames; \
            f = list(iter_state_frames('captures/sample_steam_press.bin')); \
            print(sum(1 for fr in f if fr.pressed('Steam')), 'of', len(f), 'frames have Steam pressed')"
```

## Key findings at a glance

- **30 button bits** at report bytes 0x02-0x05 (uint32 LE), matching SDL3's `TritonButtons` enum exactly
- **Analog fields** at 0x06-0x1D (triggers, sticks, trackpad X/Y, pressure) — int16 LE per SDL3 `controller_structs.h`
- **IMU at 0x1E-0x35** including a 4× int16 LE quaternion in the Full variant — **OFF by default**, requires `SETTING_IMU_MODE` via Feature-Report to enable
- **Sub-reports 0x43, 0x7b** carry telemetry (battery, link quality) in a tagged-attribute format identical to the main attribute-read protocol
- **Lizard-mode reports (0x40/0x41)** appear within ~8 seconds of Steam being killed (watchdog re-enables HID-mouse/HID-keyboard fallback)
- **Firmware update protocol**: HID Feature-Report `0x01 90` switches to bootloader → device re-enumerates as CDC ACM (PIDs `28DE:1005` Triton-BL, `28DE:1007` Proteus-BL) → HDLC-framed messages (`SOF=0xAD, EOF=0xAE, ESCAPE=0xAC`) send 32-KB chunks → final `MESSAGE_RESET` returns to normal mode
- **Codenames**: Triton (controller), Proteus (puck/dongle), Nereid (unknown — possibly Steam Frame Tracker). IBEX is the controller's firmware-filename prefix. ESB = Nordic Enhanced ShockBurst (proprietary 2.4 GHz protocol between puck and controller).
- **Likely silicon**: Nordic nRF52840 (controller) and nRF52833/nRF52820 (puck), based on flash base 0x00000000, RAM-top, IRQ count, and the BLE+ESB+USB capability matrix.

## Sources & credits

This work builds heavily on Valve's own open releases:

- [SDL3 `SDL_hidapi_steam_triton.c`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_steam_triton.c) — Valve-authored driver inside SDL3, exposes `TritonButtons` enum, MTU struct layouts, settings IDs
- [SDL3 `controller_structs.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_structs.h) — wire-format struct definitions with `#pragma pack(1)`
- [SDL3 `controller_constants.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_constants.h) — shared feature-report IDs (inherited from SC1)
- [SteamHapticsSinger](https://github.com/CrazyCritic89/SteamHapticsSinger) — the only other active SC2-era project; covers haptic output (Note-On `0x83` / Note-Off `0x81`, actuator IDs)
- **Steam's bundled `hardwareupdater.x86_64`** at `~/.local/share/Steam/bin/hardwareupdater/` on every installed Steam client — a PyInstaller bundle that, once extracted, gives the entire update protocol in readable Python bytecode

## License

MIT — see [LICENSE](LICENSE). Some embedded code patterns are credited to the BSD-3-Clause licensed SteamHapticsSinger; their attribution is preserved in inline comments where applicable.

## Disclaimers

- Documentation reflects pre-update (`bcdDevice 0.02`) baseline as of 2026-05. Future firmware updates may change layouts.
- Reverse-engineering is for interoperability / educational purposes. No proprietary code or firmware blobs are redistributed in this repo.
- The author has no affiliation with Valve.
