#!/usr/bin/env python3
"""
fw_changelog — generate human-readable "what changed" reports between Steam
Controller 2 firmware versions.

Valve ships SC2 firmware silently: the Steam client patch notes mention fixes
in prose ("fixed rumble breaking gyro") but never map them to a specific build,
and nobody publishes a per-version binary diff. This tool does the binary diff
and lines it up against the known Steam-update dates.

Firmware blobs come from the OpenSteamController/Ibex-Firmware archive
(https://opensteamcontroller.github.io/Ibex-Firmware/), downloaded on demand and
cached. No controller needed, so it runs anywhere with a network connection and Python 3.10+.

Usage:
    fw_changelog.py --list controller
    fw_changelog.py 69FA5889 69FE17FF          # diff two controller builds
    fw_changelog.py IBEX_FW_69FA5889.fw 69FE17FF
    fw_changelog.py old.fw new.fw              # local files also work
    fw_changelog.py --sweep controller         # changelog across every pair
    fw_changelog.py --sweep puck --out PUCK_CHANGELOG.md

A "version" argument may be: a bare build hash (69FE17FF), a full filename
(IBEX_FW_69FE17FF.fw), or a path to a local .fw file.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Reuse the stable firmware-parsing helpers from analyze_fw.py (same dir).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_fw import (  # noqa: E402
    extract_strings,
    find_bl_targets,
    find_function_starts,
    find_rodata_region,
    parse_header,
    parse_vector_table,
)

ARCHIVE_BASE = "https://opensteamcontroller.github.io/Ibex-Firmware"
KIND_DIR = {"controller": "Controller", "puck": "Puck"}
KIND_PREFIX = {"controller": "IBEX_FW_", "puck": "PROTEUS_FW_"}
DEFAULT_CACHE = Path(os.environ.get("IBEX_FW_CACHE", "/tmp/ibex_fw_cache"))

# Known Steam-client updates that touched SC2 firmware (public patch notes /
# press). Build timestamps are annotated with the nearest update at/after them.
STEAM_UPDATES = [
    ("2026-05-08", "left trackpad wireless fix; Grip Sensor settings; battery-notification toggle"),
    ("2026-05-27", "rumble-breaking-gyro fix; gyro polling stutter; IMU failure on extended rumble; trackpad dead-zone"),
    ("2026-06",    "charging-issue fix; LED dimming exposed in settings; trigger-deadzone tweaks"),
]


def ts_from_name(name: str) -> int | None:
    """IBEX_FW_69FE17FF.fw -> unix timestamp 0x69FE17FF."""
    stem = Path(name).stem
    hexpart = stem.rsplit("_", 1)[-1]
    try:
        return int(hexpart, 16)
    except ValueError:
        return None


def fmt_date(ts: int | None) -> str:
    if ts is None:
        return "?"
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def steam_note_for(ts: int | None) -> tuple[str, str] | None:
    """Nearest Steam-client update at/after a build timestamp (best-effort,
    approximate — a build can ship in a slightly later client update)."""
    if ts is None:
        return None
    d = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).date().isoformat()
    for date, note in STEAM_UPDATES:
        if d <= date or d[:7] == date:  # at/before that update, or same YYYY-MM
            return (date, note)
    return None


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------
def _fetch_bytes(url: str) -> bytes:
    """GET a URL as bytes. Falls back to `curl` if Python's SSL has no CA certs
    (common on python.org macOS builds); curl ships on macOS and SteamOS."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, ssl.SSLError):
        try:
            return subprocess.run(
                ["curl", "-fsSL", url], capture_output=True, check=True
            ).stdout
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(f"failed to fetch {url}: {e}")


def fetch_index(kind: str) -> list[str]:
    """Return archived filenames for `kind`, oldest first (by build timestamp)."""
    data = json.loads(_fetch_bytes(f"{ARCHIVE_BASE}/index.json"))
    names = list(data.get(kind, {}).keys())
    names.sort(key=lambda n: ts_from_name(n) or 0)
    return names


def resolve_blob(ref: str, kind: str, cache: Path) -> Path:
    """Resolve a version ref (hash / filename / path) to a local .fw file,
    downloading from the archive into `cache` when needed."""
    p = Path(ref)
    if p.exists() and p.is_file():
        return p
    prefix = KIND_PREFIX[kind]
    if ref.upper().startswith(prefix.upper()):
        filename = ref if ref.endswith(".fw") else ref + ".fw"
    else:
        filename = f"{prefix}{ref.upper()}.fw"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / filename
    if not dest.exists():
        url = f"{ARCHIVE_BASE}/{KIND_DIR[kind]}/{filename}"
        print(f"  fetching {filename} ...", file=sys.stderr)
        dest.write_bytes(_fetch_bytes(url))
    return dest


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def summarize(path: Path) -> dict:
    data = path.read_bytes()
    code = data[32:]
    h = parse_header(data)
    vt = parse_vector_table(code)
    rodata = find_rodata_region(code)
    strings = extract_strings(code, min_len=8, only_in_range=rodata)
    return {
        "name": path.name,
        "ts": ts_from_name(path.name),
        "file_size": len(data),
        "payload_size": h["payload_size"],
        "crc": h.get("checksum"),
        "reset_handler": vt["reset_handler"] & ~1,
        "n_funcs": len(find_function_starts(code)),
        "n_bl": len(find_bl_targets(code, 0)),
        "strings": {s for _, s in strings},
    }


def _classify(added: set[str]) -> str:
    """Rough read of what a string-set change implies."""
    if not added:
        return "recompile only, no new strings (likely a bug fix or config flip)"
    debugy = sum(1 for s in added if any(k in s.lower() for k in
                 ("log", "dbg", "error", "fail", "assert", "%d", "%s", "%u")))
    if debugy >= 0.6 * len(added):
        return "mostly log/debug strings changed (LOG_LEVEL or diagnostics)"
    return "new functional strings — possibly a new feature or subsystem"


def diff_report(old: Path, new: Path, kind: str, md: bool = False) -> str:
    a, b = summarize(old), summarize(new)
    added = b["strings"] - a["strings"]
    removed = a["strings"] - b["strings"]
    d_pay = b["payload_size"] - a["payload_size"]
    d_fun = b["n_funcs"] - a["n_funcs"]
    d_bl = b["n_bl"] - a["n_bl"]
    su = steam_note_for(b["ts"])

    h = "### " if md else ""
    out = []
    out.append(f"{h}{a['name']} → {b['name']}")
    out.append(f"- build dates: {fmt_date(a['ts'])} → {fmt_date(b['ts'])}")
    out.append(f"- payload: {a['payload_size']:,} → {b['payload_size']:,} B ({d_pay:+,})")
    out.append(f"- CRC32: 0x{a['crc']:08X} → 0x{b['crc']:08X}")
    out.append(f"- reset handler: 0x{a['reset_handler']:X} → 0x{b['reset_handler']:X}")
    out.append(f"- function prologs: {a['n_funcs']:,} → {b['n_funcs']:,} ({d_fun:+})  |  BL sites: {a['n_bl']:,} → {b['n_bl']:,} ({d_bl:+})")
    out.append(f"- strings: +{len(added)} / -{len(removed)}  →  {_classify(added)}")
    if added:
        sample = sorted(added)[:8]
        out.append("  - added: " + ", ".join(repr(s) for s in sample) + (" ..." if len(added) > 8 else ""))
    if removed:
        sample = sorted(removed)[:6]
        out.append("  - removed: " + ", ".join(repr(s) for s in sample) + (" ..." if len(removed) > 6 else ""))
    if su:
        out.append(f"- ~Steam-client update {su[0]} (approx.): _{su[1]}_")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_list(kind: str) -> None:
    names = fetch_index(kind)
    print(f"{len(names)} {kind} firmware versions (oldest first):")
    for n in names:
        print(f"  {fmt_date(ts_from_name(n)):22s}  {n}")


def cmd_diff(old_ref: str, new_ref: str, kind: str, cache: Path) -> None:
    old = resolve_blob(old_ref, kind, cache)
    new = resolve_blob(new_ref, kind, cache)
    print(diff_report(old, new, kind))


def cmd_sweep(kind: str, cache: Path, out: str | None, limit: int | None) -> None:
    names = fetch_index(kind)
    if limit:
        names = names[-(limit + 1):]
    pairs = list(zip(names, names[1:]))
    lines = [f"# {kind.capitalize()} firmware changelog (binary diff)",
             "",
             f"Generated from the Ibex-Firmware archive, {len(pairs)} consecutive diffs. "
             "Binary-level, not official; Valve publishes no per-build changelog.",
             ""]
    for old_name, new_name in pairs:
        old = resolve_blob(old_name, kind, cache)
        new = resolve_blob(new_name, kind, cache)
        lines.append(diff_report(old, new, kind, md=True))
        lines.append("")
    text = "\n".join(lines)
    if out:
        Path(out).write_text(text)
        print(f"wrote {out} ({len(pairs)} entries)")
    else:
        print(text)


# ---------------------------------------------------------------------------
# plain-language change log (GitHub-flavoured markdown)
# ---------------------------------------------------------------------------
# added-string keyword -> (title, note). Checked in order.
_RULES = [
    (("recover", "corrupt settings", "erasing the whole settings"),
     "Settings-corruption recovery", "Error handling for a corrupted settings partition."),
    (("vpilot", "vpogo", "pilot envelope", "pilot signal", "puck-pilot"),
     "Dock detection (pilot / pogo)", "Diagnostics for docking onto the puck over the pogo pins."),
    (("cost funtion", "cost function", "channel_cost", "channel cost", "background_rssi", "rssi",
      "backup_channel", "rf_channel", "connection_uptime", "hopping"),
     "RF link and channel tuning", "Channel cost, signal strength and channel hopping on the puck link."),
    (("lsm6d", "alpha_blend", "alpha-blend", "mounting matrix"),
     "IMU / trackpad handling", "IMU readiness and trackpad processing."),
    (("qos data reports", "adjust or print", "radio_send_channels", "shell"),
     "Debug shell and QoS reports", "Diagnostic commands over the hidden UART shell."),
    (("delete bt settings", "delete esb settings", "mte settings", "delete debug settings", "delete user"),
     "Settings management", "Managing or deleting the settings namespaces (bt, esb, debug, mte)."),
    (("factory restore", "factory reset", "factory"),
     "Factory reset", "A factory-restore path."),
    (("haptic", "script already active"),
     "Haptics", "Haptic-script handling hardened."),
    (("private channel", "private pipe", "bond updated", "pairing", "disconnect"),
     "Pairing / radio link", "Connection and bond handling."),
    (("init adcs", "vbatt", "adc"),
     "Analog / battery", "ADC and battery measurement."),
]


def _is_interesting(s: str) -> bool:
    if s.startswith("*** Using"):
        return False
    if sum(c.isalpha() for c in s) < 4 or not (8 <= len(s) <= 64) or s.count(" ") > 8:
        return False
    return any(c.isupper() or c.isdigit() or c in " _%:/-." for c in s)


def _interpret(has_prev: bool, interesting: list[str], n_add: int, n_rem: int):
    if not has_prev:
        return "change", "First archived build", "The oldest build in the archive, used as the baseline."
    if n_add == 0 and n_rem == 0:
        return "minor", "Rebuild only", "Identical strings, so only a recompile is visible, not what changed."
    if n_rem >= 100 and len(interesting) <= 3:
        return "minor", "Release build, logging stripped", f"{n_rem} debug strings removed (LOG_LEVEL lowered)."
    if interesting:
        blob = " ".join(interesting).lower()
        for keys, title, note in _RULES:
            if any(k in blob for k in keys):
                return "change", title, note
        return "change", "New messages in the code", "New functional strings appear; the evidence shows which."
    return "minor", "Debug strings changed", f"Mostly log or debug messages (+{n_add} / -{n_rem}), no clear feature."


def _fmt_dpay(d: int) -> str:
    if not d:
        return ""
    sign = "+" if d > 0 else "-"
    return f"{sign}{abs(d) // 1024} KB" if abs(d) >= 1024 else f"{sign}{abs(d)} B"


def _changelog_rows(kind: str, cache: Path) -> list[dict]:
    """One row per build, oldest first, with a plain-language read of the diff."""
    sums = [summarize(resolve_blob(n, kind, cache)) for n in fetch_index(kind)]
    rows = []
    for i, s in enumerate(sums):
        prev = sums[i - 1] if i else None
        added = (s["strings"] - prev["strings"]) if prev else set()
        removed = (prev["strings"] - s["strings"]) if prev else set()
        interesting = sorted(x for x in added if _is_interesting(x))
        tier, title, note = _interpret(prev is not None, interesting, len(added), len(removed))
        rows.append({
            "ts": s["ts"], "hash": s["name"].replace(".fw", "").rsplit("_", 1)[-1],
            "kb": s["payload_size"] / 1024,
            "dpay": (s["payload_size"] - prev["payload_size"]) if prev else 0,
            "tier": tier, "title": title, "ev": interesting,
        })
    return rows


def cmd_changelog(cache: Path, out: str | None) -> None:
    def esc(x):  # keep inline-code spans and table cells from breaking
        return x.replace("`", "'").replace("|", "\\|")

    def day(ts):  # date only, drop the time-of-day noise
        return fmt_date(ts).split()[0]

    kinds = (("controller", "Controller (Triton)"), ("puck", "Puck (Proteus)"))
    laned = [(kind, label, _changelog_rows(kind, cache)) for kind, label in kinds]
    newest = max(r["ts"] for _, _, rows in laned for r in rows)
    parts = [
        "# Steam Controller 2 firmware change log",
        "",
        "Valve ships SC2 firmware without release notes. This is a binary diff of every published build "
        "in the [Ibex-Firmware](https://opensteamcontroller.github.io/Ibex-Firmware/) archive: the payload "
        "size, and which text strings appear or vanish between builds. From the new strings you can read "
        "roughly what changed. It is unofficial, reconstructed from the blobs.",
        "",
        f"> **Snapshot, not live.** This is a point-in-time snapshot (newest build here: {day(newest)}). "
        "It does not update itself. When Valve ships new firmware, regenerate it yourself with "
        "`python3 tools/fw_changelog.py --changelog --out docs/CHANGELOG.md`. The Ibex-Firmware archive it "
        "reads from tracks new builds automatically.",
        "",
        "The **New strings** column lists the readable strings that appeared in that build, the evidence "
        "for the summary. An empty cell means only a recompile or a debug-logging change, where you can "
        "tell it changed but not what.",
        "",
    ]
    for kind, label, rows in laned:
        changes = sum(1 for r in rows if r["tier"] == "change")
        span = (fmt_date(rows[0]["ts"])[:7], fmt_date(rows[-1]["ts"])[:7])
        parts += [
            f"## {label}", "",
            f"{len(rows)} builds, {span[0]} to {span[1]}, {changes} with a readable change.", "",
            "| Date | Build | Size | What changed | New strings |",
            "|---|---|---|---|---|",
        ]
        for r in reversed(rows):
            d = _fmt_dpay(r["dpay"])
            size = f"{r['kb']:.0f} KB" + (f" ({d})" if d else "")
            strs = ", ".join(f"`{esc(s)}`" for s in r["ev"])
            parts.append(f"| {day(r['ts'])} | `{r['hash']}` | {size} | {r['title']} | {strs} |")
        parts.append("")
    Path(out).write_text("\n".join(parts).rstrip() + "\n") if out else print("\n".join(parts))
    if out:
        print(f"wrote {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate SC2 firmware changelogs by binary diff.")
    p.add_argument("versions", nargs="*", help="OLD NEW (hashes, filenames, or paths)")
    p.add_argument("--kind", choices=("controller", "puck"), default="controller")
    p.add_argument("--list", metavar="KIND", choices=("controller", "puck"), help="list archived versions")
    p.add_argument("--sweep", metavar="KIND", choices=("controller", "puck"), help="diff every consecutive pair")
    p.add_argument("--limit", type=int, help="(with --sweep) only the most recent N steps")
    p.add_argument("--changelog", action="store_true",
                   help="write a plain-language CHANGELOG.md (both devices) to --out")
    p.add_argument("--out", help="output file (with --sweep or --changelog)")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help=f"blob cache dir (default: {DEFAULT_CACHE})")
    args = p.parse_args()

    if args.changelog:
        cmd_changelog(args.cache, args.out)
    elif args.list:
        cmd_list(args.list)
    elif args.sweep:
        cmd_sweep(args.sweep, args.cache, args.out, args.limit)
    elif len(args.versions) == 2:
        # infer kind from a filename ref if possible
        kind = args.kind
        for v in args.versions:
            if v.upper().startswith("PROTEUS"):
                kind = "puck"
            elif v.upper().startswith("IBEX"):
                kind = "controller"
        cmd_diff(args.versions[0], args.versions[1], kind, args.cache)
    else:
        p.error("give two versions to diff, or use --list / --sweep")


if __name__ == "__main__":
    main()
