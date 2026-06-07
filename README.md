# sc2-research

Notes and tools for the Steam Controller 2 (Triton): HID input layout, firmware update protocol, feature-report routing, and static analysis of the firmware blobs.

Most of this comes from extracting `hardwareupdater.x86_64` — the PyInstaller bundle that ships with the Steam client — and verifying against an actual SC2 + Puck on a Steam Deck (SteamOS) with controller firmware `bcdDevice 0.02`. Hobby project with heavy AI assistance — see [Disclaimer](#disclaimer).

Covers: SC2 (USB `28DE:1302/1303`), the Proteus puck (`28DE:1304`), and the parallel Nereid dongle (`28DE:1305`). Nereid is plausibly the Steam-Machine-integrated dongle, based on SDL3 commit timing and the absence of a Nereid bootloader path in Steam's user-facing updater.

## Documentation

| Path | Contents |
|---|---|
| [`docs/FIRMWARE_PROTOCOL.md`](docs/FIRMWARE_PROTOCOL.md) | Update protocol: HDLC framing, message IDs, firmware-file format, bootloader-mode switching, live feature-report attribute queries, ARM Cortex-M static analysis. |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | RE notes: PyInstaller-bundle extraction, bytecode disassembly without a decompiler, the InHand-flag debunking, capture-timing pitfalls, SteamOS ACL quirks, multi-device `fr_id` routing. |
| [`docs/CONTROLLER_CAPABILITIES.md`](docs/CONTROLLER_CAPABILITIES.md) | Hardware notes — chip identification, USB topology, haptic actuator IDs, components found via firmware-string analysis. |
| [`docs/HID_REPORT_FORMAT.md`](docs/HID_REPORT_FORMAT.md) | The 54-byte Report-0x42 layout (from SDL3, verified against ~9k frames), puck USB topology, Lizard-mode timing, sub-reports `0x43` (battery) and `0x7b` (the one Triton input report ID not in SDL3), SteamOS access notes. |
| [`docs/SDL3_REFERENCE.md`](docs/SDL3_REFERENCE.md) | Cross-reference of what SDL3's open-source code says about Triton — report IDs, output haptic message types, settings, audio cues, charge states, IMU axis swizzle and scaling, trackpad transforms, timing constants. |

## Tools

Python 3.10+, stdlib only. Run as the `deck` user on SteamOS (not `sudo` — root is blocked by the hidraw ACL).

Firmware analysis & extraction:

| Tool | What it does |
|---|---|
| `tools/extract_pyinst.py` | Minimal PyInstaller bundle extractor — MEI cookie + TOC walker. |
| `tools/walk_pyc.py` | Walks marshaled Python code objects, lists nested functions + constants. |
| `tools/analyze_fw.py` | Parses ARM Cortex-M firmware blobs (header, vector table, IRQ handlers, strings). |
| `tools/attr_query.py` | Sends HID Feature-Reports via `ioctl` to query device attributes. |

Live capture & observation:

| Tool | What it does |
|---|---|
| `tools/live_monitor.py` | Streams `/dev/hidraw9`, prints button transitions + analog deflection. |
| `tools/one_capture.py NAME [NAME...]` | Captures 3 s of hidraw9 traffic per named action; diffs against a baseline. |
| `tools/event_logger.py [seconds]` | Parallel logger across hidraw9–13; report-ID histogram per interface. |

## Quick start

```bash
git clone <this-repo>
cd sc2-research

# Probe puck + controller via HID Feature-Reports
python3 tools/attr_query.py

# Extract Steam's firmware updater
python3 tools/extract_pyinst.py
python3 tools/walk_pyc.py

# Analyse a firmware blob
python3 tools/analyze_fw.py ~/.local/share/Steam/bin/hardwareupdater/IBEX_FW_69FA5889.fw
```

## Background

Valve's own open releases this work builds on:

- [SDL3 `SDL_hidapi_steam_triton.c`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_steam_triton.c) — driver Sam Lantinga upstreamed in commit `1998b6504` (Nov 12 2025)
- [SDL3 `controller_structs.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_structs.h)
- [SDL3 `controller_constants.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_constants.h)
- `hardwareupdater.x86_64` in `~/.local/share/Steam/bin/hardwareupdater/` — the PyInstaller bundle that ships with the Steam client.

Other SC2-era work:

- [`OpenSteamController/Ibex-Firmware`](https://github.com/OpenSteamController/Ibex-Firmware) — mirrors `.fw` blobs from Valve's CDN with a versioned catalog. Documents the 32-byte header (checksum field = CRC32 at offset `0x08`).
- [SteamHapticsSinger](https://github.com/CrazyCritic89/SteamHapticsSinger) — haptic output side. Their "Note-On `0x83`" is `HAPTIC_LFO_TONE` per SDL3; "Note-Off `0x81`" is `HAPTIC_PULSE`.
- [SteamlessController](https://github.com/ddeverill/SteamlessController) — Windows tool that disables Lizard mode and bridges Report 0x42 to a virtual Xbox 360 pad.
- [OpenSteamController](https://github.com/greggersaurus/OpenSteamController) (greggersaurus) — RE for the 2015 Steam Controller (LPC11U37F + nRF51822); architecturally unrelated to the SC2.

Hardware identification:

- [iFixit Steam Controller (2nd Generation)](https://www.ifixit.com/Device/Steam_Controller_%282nd_Generation%29) — chip markings read as nRF52833 ("appears to be"). Firmware-DT-address analysis in this repo identifies it as nRF52840.
- [PC Gamer 2026 teardown](https://www.pcgamer.com/hardware/game-pads/steam-controller-2026-review/), [GamersNexus review](https://gamersnexus.net/handheld-pcs-peripherals/valve-steam-controller-review-latency-benchmarks-battery-life), [PCGamingWiki](https://www.pcgamingwiki.com/wiki/Controller:Steam_Controller_(2nd_generation)).

Codenames that were already public before this work:

- [Brad Lynch on X, Nov 19 2024](https://x.com/SadlyItsBradley/status/1858925211363553316) — "Ibex".
- [Tom's Hardware Q4 2025](https://www.tomshardware.com/video-games/pc-gaming/valve-seemingly-preps-steam-controller-2-and-vr-controller-ibex-and-roy-controller-renders-spotted-in-steamvr-data-mine) — "Ibex" + "Roy".
- [NeoGAF Q4 2025](https://www.neogaf.com/threads/new-triton-steam-controller-icon-datamined.1689607/) — "Triton".
- [Phoronix Nov 12 2025](https://www.phoronix.com/news/New-Steam-Controller-SDL) — "Proteus" and "Nereid".

## License

MIT — see [LICENSE](LICENSE). Some patterns credited inline to the BSD-3-Clause SteamHapticsSinger.

## Disclaimer

Hobby project, done with heavy AI assistance (Claude) for hypothesis-testing, cross-referencing, and drafting. The hardware testing, firmware extraction, and packet captures were on my own Steam Deck (SteamOS) with an SC2 + Puck (USB `bcdDevice 0.02`). Cross-checked against SDL3 source where possible; I may have missed conventions someone with deeper RE background would catch — corrections via issues / PRs welcome.

Baseline: the firmware blobs analysed here are **`IBEX_FW_69FA5889` + `69FE17FF`** (Triton) and **`PROTEUS_FW_69FA587F` + `69FBD45D`** (Proteus), all from early May 2026. Both pairs are byte-identically mirrored in [`OpenSteamController/Ibex-Firmware`](https://github.com/OpenSteamController/Ibex-Firmware), so anyone can reproduce the analysis without their own Steam install:

```bash
curl -O https://opensteamcontroller.github.io/Ibex-Firmware/Controller/IBEX_FW_69FE17FF.fw
curl -O https://opensteamcontroller.github.io/Ibex-Firmware/Puck/PROTEUS_FW_69FBD45D.fw
python3 tools/analyze_fw.py IBEX_FW_69FE17FF.fw
```

Valve has shipped further updates since (the June 2026 release added LED dimming in settings + trigger-deadzone tweaks). The protocol layer is expected to be stable across these; static-analysis offsets are tied to the specific FW versions above.

No proprietary code or firmware blobs are redistributed here — for the blobs see [`OpenSteamController/Ibex-Firmware`](https://github.com/OpenSteamController/Ibex-Firmware). No affiliation with Valve.
