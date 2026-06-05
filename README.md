# sc2-research

> **First public documentation of the Steam Controller 2 firmware update protocol** — HDLC framing, message IDs, bootloader USB PIDs, firmware-file format, the live Feature-Report attribute-query routing, and the silicon/RTOS/toolchain identifiers extracted by static analysis of the firmware blobs.

*Hobby reverse-engineering project, heavy AI assistance — see [Disclaimer](#disclaimer) at the bottom. Corrections via issues / PRs very welcome.*

Reverse-engineered from Steam's bundled `hardwareupdater.x86_64` (a PyInstaller bundle that ships with every Steam client and turned out to contain the entire update stack in readable Python bytecode) and live-verified on SteamOS against the actual hardware.

Hardware targets: Steam Controller 2 (Valve-internal codenames "Triton" / "Ibex", USB `28DE:1302/1303`) and its wireless dongle "Proteus" (USB `28DE:1304`). Also covers what little is publicly knowable about the parallel **Nereid** dongle (USB `28DE:1305`), which is most plausibly the **Steam-Machine-integrated dongle** based on the SDL3 commit timing and the absence of a `Nereid_BL` path in Steam's user-facing updater.

Firmware baseline: `bcdDevice 0.02` (pre-update, May 2026).

## Documentation

| Path | Contents |
|---|---|
| [`docs/FIRMWARE_PROTOCOL.md`](docs/FIRMWARE_PROTOCOL.md) | The full update protocol: HDLC framing, message IDs, firmware-file header format, bootloader-mode switching, live Feature-Report attribute queries, ARM Cortex-M static analysis. |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | Concrete RE lessons: PyInstaller-bundle extraction, bytecode disassembly without a decompiler, the InHand-flag debunking, capture-timing pitfalls, SteamOS ACL quirks, multi-device `fr_id` routing pattern. |
| [`docs/CONTROLLER_CAPABILITIES.md`](docs/CONTROLLER_CAPABILITIES.md) | Hardware notes relevant to the RE work — chip identification, USB topology, haptic actuator IDs, components found via firmware-string analysis. Cross-links to Wikipedia / iFixit / GamersNexus for general specs. |
| [`docs/HID_REPORT_FORMAT.md`](docs/HID_REPORT_FORMAT.md) | The 54-byte Report-0x42 layout (verbatim from SDL3 + verified against 9k+ frames on this device), plus the parts SDL3 doesn't cover: puck USB topology, Lizard-mode timing, sub-reports `0x43` (battery, per SDL3) and `0x7b` (the only Triton input report ID **not** in SDL3), SteamOS access notes. |
| [`docs/SDL3_REFERENCE.md`](docs/SDL3_REFERENCE.md) | Exhaustive cross-reference of everything SDL3's open-source code publicly says about Triton — report IDs, output haptic message types, setting IDs, audio cues, charge states, IMU axis swizzle and scaling, trackpad transforms, timing constants — with file/line citations. The tiebreaker for "is this novel or already public?" |

## Tools

All Python 3.10+, stdlib only (no pip dependencies). Run as the `deck` user on SteamOS (NOT sudo — root is blocked by the ACL).

Firmware analysis & extraction:

| Tool | What it does |
|---|---|
| `tools/extract_pyinst.py` | Minimal PyInstaller bundle extractor — parses the MEI cookie, walks the TOC, dumps raw + decompressed entries. Used to crack open `hardwareupdater.x86_64`. |
| `tools/walk_pyc.py` | Walks a marshaled Python code object, lists nested functions with signatures + interesting constants. For bytecode RE when no decompiler supports the target Python version. |
| `tools/analyze_fw.py` | Parses ARM Cortex-M firmware blobs (header, vector table, IRQ handlers, embedded strings). |
| `tools/attr_query.py` | Sends HID Feature-Reports directly via `ioctl` to query device attributes (`build_timestamp`, `hw_id`, `frame_rate`, …). Live-tested on Proteus puck, including the brute-force opcode scan that surfaced the `fr_id`/`op` routing pattern. |

Live capture & observation:

| Tool | What it does |
|---|---|
| `tools/live_monitor.py` | Streams `/dev/hidraw9`, prints button transitions by SDL name and analog deflection. |
| `tools/one_capture.py NAME [NAME...]` | Capture 3 s of hidraw9 traffic per named action; auto-diff vs a baseline. |
| `tools/event_logger.py [seconds]` | Parallel logger across hidraw9–13; summarises report-IDs seen per interface. |

## Quick start

```bash
git clone <this-repo>
cd sc2-research

# Probe the puck + controller via HID Feature-Reports
# (queries 31 attributes incl. build_timestamp / frame_rate / hw_id, then
# brute-force-scans opcodes 0x80..0xCF for both fr_id=1 and fr_id=2)
python3 tools/attr_query.py

# Crack open Steam's firmware updater (PyInstaller bundle)
python3 tools/extract_pyinst.py    # → /tmp/hu_extracted/
python3 tools/walk_pyc.py          # walk the bytecode

# Analyse a firmware blob
python3 tools/analyze_fw.py ~/.local/share/Steam/bin/hardwareupdater/IBEX_FW_69FA5889.fw
```

## Sources & credits

Valve open-source code that this work builds on:

- [SDL3 `SDL_hidapi_steam_triton.c`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_steam_triton.c) — Valve-authored driver inside SDL3 (Sam Lantinga, commit `1998b6504`, Nov 12 2025)
- [SDL3 `controller_structs.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_structs.h)
- [SDL3 `controller_constants.h`](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/steam/controller_constants.h)
- **Steam's bundled `hardwareupdater.x86_64`** at `~/.local/share/Steam/bin/hardwareupdater/` on every installed Steam client — a PyInstaller bundle that, once extracted, gives the entire update protocol in readable Python bytecode

Adjacent third-party work in the SC2 era:

- [`OpenSteamController/Ibex-Firmware`](https://github.com/OpenSteamController/Ibex-Firmware) — **complementary, not competing.** They mirror every `.fw` blob Valve ships (extracted from the `bins_hardware_all` zip on Valve's CDN) and expose a public catalog at <https://opensteamcontroller.github.io/IbexFirmware/>. They document the 32-byte header (including identifying the checksum field specifically as **CRC32 at offset `0x08`** — more precise than our earlier "checksum"). Their scope is the firmware archive; this repo's scope is the protocol / tooling / static-analysis side. Both are useful together.
- [SteamHapticsSinger](https://github.com/CrazyCritic89/SteamHapticsSinger) — haptic output side. Their "Note-On `0x83`" turns out to be the canonical `HAPTIC_LFO_TONE` (per SDL3 `ValveTritonOutReportMessageIDs`); their "Note-Off `0x81`" is `HAPTIC_PULSE`. Functional naming for a MIDI-player use case.
- [SteamlessController](https://github.com/ddeverill/SteamlessController) — Windows tool that disables Lizard mode and bridges Report 0x42 to virtual Xbox 360 via ViGEmBus.
- [OpenSteamController](https://github.com/greggersaurus/OpenSteamController) (the original / greggersaurus) — RE for the *2015* Steam Controller (LPC11U37F + nRF51822). Architecturally unrelated to the 2026 model — included so readers understand none of that work applies to SC2.

Hardware identification:

- [iFixit Steam Controller (2nd Generation)](https://www.ifixit.com/Device/Steam_Controller_%282nd_Generation%29) — chip markings (read by iFixit as nRF52833 "appears to be"; firmware-DT-address analysis in this repo identifies it as nRF52840 — see `docs/FIRMWARE_PROTOCOL.md` §"Hardware inference")
- [PC Gamer 2026 teardown](https://www.pcgamer.com/hardware/game-pads/steam-controller-2026-review/) — corroborating chip-marking read
- [GamersNexus review](https://gamersnexus.net/handheld-pcs-peripherals/valve-steam-controller-review-latency-benchmarks-battery-life) — latency, battery, "4 controllers per puck, 2 puck-pairings per controller"
- [PCGamingWiki: Steam Controller (2nd generation)](https://www.pcgamingwiki.com/wiki/Controller:Steam_Controller_(2nd_generation)) — public PID cross-reference

Codenames that were already public before this work:

- [Brad Lynch on X, Nov 19 2024](https://x.com/SadlyItsBradley/status/1858925211363553316) — "Ibex" SC2 hardware codename
- [Tom's Hardware on "Ibex" + "Roy" SteamVR datamine](https://www.tomshardware.com/video-games/pc-gaming/valve-seemingly-preps-steam-controller-2-and-vr-controller-ibex-and-roy-controller-renders-spotted-in-steamvr-data-mine) (Q4 2025)
- [NeoGAF on "Triton" icon datamine](https://www.neogaf.com/threads/new-triton-steam-controller-icon-datamined.1689607/) (Q4 2025)
- [Phoronix on SDL3 Triton driver, Nov 12 2025](https://www.phoronix.com/news/New-Steam-Controller-SDL) — first public mention of "Proteus" and "Nereid" as Valve dongle codenames (quoting the SDL3 commit text)

## License

MIT — see [LICENSE](LICENSE). Some embedded code patterns are credited to the BSD-3-Clause licensed SteamHapticsSinger; their attribution is preserved in inline comments where applicable.

## Disclaimer

I'm not a professional reverse engineer or embedded developer — this project started because I picked up a Steam Controller 2 and got curious about how it actually works under the hood. The research and writing here were done with **heavy AI assistance (Claude)**, used as a sparring partner for hypothesis-testing, cross-referencing public sources (SDL3, datamining articles, teardowns), and drafting documentation.

**What's mine:** the hardware (Steam Controller 2 + Puck on SteamOS, firmware `bcdDevice 0.02`), running the extraction of `hardwareupdater.x86_64` from my own Steam install, the packet captures, the live `attr_query.py` runs, and the direction of what to investigate.

**What's AI-assisted:** most of the writing, structuring, cross-checking against SDL3 source, debugging suggestions, and a lot of the methodological framing.

**Practical implications for the reader:**
- Every claim labelled as novel has been cross-checked against SDL3 source and other public references (see [`docs/SDL3_REFERENCE.md`](docs/SDL3_REFERENCE.md)). The tools have been run on real hardware.
- I may have missed conventions or context that someone with deeper RE / embedded background would catch immediately. If you spot something wrong or unclear, please open an issue — corrections from people who know more than I do are explicitly welcome.

Other standard caveats:
- Documentation reflects the pre-update (`bcdDevice 0.02`) baseline as of 2026-05-22. **Valve shipped at least one firmware update in June 2026** (charging-issue fix, LED dimming exposed in settings, trigger-deadzone tweaks) after this snapshot, so the precise timestamps and specific bytes may shift on current hardware. The protocol layer is expected to be stable; the static-analysis details (firmware string offsets, etc.) are tied to the specific FW versions analysed.
- Reverse-engineering is for interoperability / educational purposes. No proprietary code or firmware blobs are redistributed in this repo — for the blobs themselves see [`OpenSteamController/Ibex-Firmware`](https://github.com/OpenSteamController/Ibex-Firmware).
- I have no affiliation with Valve.
