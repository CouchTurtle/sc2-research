# Steam Controller 2 firmware change log

Valve ships SC2 firmware without release notes. This is a binary diff of every published build in the [Ibex-Firmware](https://opensteamcontroller.github.io/Ibex-Firmware/) archive: the payload size, and which text strings appear or vanish between builds. From the new strings you can read roughly what changed. It is unofficial, reconstructed from the blobs.

> **Snapshot, not live.** This is a point-in-time snapshot (newest build here: 2026-07-07). It does not update itself. When Valve ships new firmware, regenerate it yourself with `python3 tools/fw_changelog.py --changelog --out docs/CHANGELOG.md`. The Ibex-Firmware archive it reads from tracks new builds automatically.

The **New strings** column lists the readable strings that appeared in that build, the evidence for the summary. An empty cell means only a recompile or a debug-logging change, where you can tell it changed but not what.

## Controller (Triton)

26 builds, 2025-11 to 2026-07, 15 with a readable change.

| Date | Build | Size | What changed | New strings |
|---|---|---|---|---|
| 2026-07-07 | `6A4D85E3` | 376 KB (+400 B) | Rebuild only |  |
| 2026-06-30 | `6A4440DD` | 375 KB (+32 KB) | Rebuild only |  |
| 2026-06-30 | `6A4423D7` | 342 KB (+144 B) | New messages in the code | `failed to enable sensor fusion` |
| 2026-06-27 | `6A3F2424` | 342 KB (+288 B) | Rebuild only |  |
| 2026-06-24 | `6A3BFE74` | 342 KB (-1 KB) | New messages in the code | `HCI driver close failed (%d)` |
| 2026-05-28 | `6A18D057` | 344 KB | Rebuild only |  |
| 2026-05-28 | `6A18C27C` | 344 KB (+3 KB) | Rebuild only |  |
| 2026-05-22 | `6A1091CE` | 340 KB | Rebuild only |  |
| 2026-05-20 | `6A0E0230` | 340 KB (+140 B) | New messages in the code | `Failed to set stop on WTM` |
| 2026-05-18 | `6A0B53FB` | 340 KB (-12 B) | Debug strings changed |  |
| 2026-05-14 | `6A05E8CE` | 340 KB (+300 B) | New messages in the code | `Failed to set stop on WTM` |
| 2026-05-12 | `6A035EE8` | 340 KB | Rebuild only |  |
| 2026-05-08 | `69FE17FF` | 340 KB | Rebuild only |  |
| 2026-05-07 | `69FD20D4` | 340 KB (-29 KB) | New messages in the code | `0123456789abcdef`, `Failed to clear SC %d`, `TTR REGGES`, `ibexesb_common`, `smf_set_state` |
| 2026-05-05 | `69FA5889` | 369 KB (+28 B) | Debug strings changed |  |
| 2026-04-24 | `69EB90AA` | 369 KB (-456 B) | Debug strings changed |  |
| 2026-04-20 | `69E687A0` | 369 KB (+1016 B) | Settings management | `Failed to delete bt settings`, `Failed to delete debug settings`, `Failed to delete esb settings`, `Failed to delete mte settings`, `Ignoring`, `Log Entry: %u %08x %s %u %08x %08x`, `NVM reset log`, `New resetreason found`, `Nothing in reset log`, `Resetreason RAM empty`, `Starting`, `debug/resetreason` |
| 2026-04-08 | `69D6B8FB` | 368 KB (+812 B) | IMU / trackpad handling | `Call to lsm6dsv16x_interrupt_enable_set failed`, `Failed to adjust ff time windows`, `Failed to set freefall trigger: %d`, `LSM6D is not ready. Skipping ff time windows setting`, `ST_USB_WIRELESS_OFF_entry`, `ST_USB_WIRELESS_ON_entry` |
| 2026-03-18 | `69B9EE01` | 367 KB (-3 KB) | IMU / trackpad handling | `CLEAR DIGITAL MAPPINGS`, `Failed to adjust alpha_blend factor`, `LSM6D is not ready. Skipping alpha-blending adjusement`, `Watchdog about to expire`, `uart_nrfx_uarte` |
| 2026-02-24 | `699DE729` | 371 KB (+76 B) | Pairing / radio link | `No message on private channel`, `Wrong kind of message on private channel` |
| 2026-02-05 | `69850FF2` | 371 KB (+140 B) | Settings-corruption recovery | `Erasing the whole settings block to recover`, `Potential corrupt settings partition. All pages are occupied`, `Recovery faild. Device functionality will be degraded`, `Recovery succeeded!` |
| 2026-01-30 | `697D2B17` | 371 KB (+1 KB) | Analog / battery | `Failed to update VBATT_REG (%d)` |
| 2026-01-13 | `69668E1E` | 369 KB (+10 KB) | Haptics | `Haptics script already active - ignoring new script` |
| 2025-12-16 | `6941BF08` | 359 KB (+3 KB) | Pairing / radio link | `Bond updated - ignoring event`, `Configuring for %d seconds`, `Connected: private pipe (%u/%u, addr 0x%08X, prefix %u`, `Disabling activity monitor`, `Init device not ready`, `Init device(s) not ready: left(%d), right(%d)`, `Switching to backup channel %u`, `Unrecognized protocol version %u %u`, `grip de-touch threshold failed to retrieve (%d)`, `grip touch threshold failed to retrieve (%d)`, `ibex_input`, `k_msgq_get error: %d`, `olympus-trackpad-left`, `olympus-trackpad-right`, `olympus_trackpad` |
| 2025-11-25 | `6925D603` | 355 KB (+148 B) | New messages in the code | `SettingsChanged: Exceeded CB array (%d)`, `SettingsSet: Exceeded CB array (%d)` |
| 2025-11-17 | `691BB5B3` | 355 KB | First archived build |  |

## Puck (Proteus)

22 builds, 2025-11 to 2026-06, 12 with a readable change.

| Date | Build | Size | What changed | New strings |
|---|---|---|---|---|
| 2026-06-30 | `6A4423DE` | 193 KB (+16 B) | Debug strings changed |  |
| 2026-06-27 | `6A3F2420` | 193 KB | Rebuild only |  |
| 2026-06-24 | `6A3BFE78` | 193 KB (+1 KB) | Debug strings changed |  |
| 2026-05-28 | `6A18D053` | 192 KB (+1 KB) | Dock detection (pilot / pogo) | `Failed to init ADCs`, `In pilot envelope`, `Pilot signal is valid but controller unresponsive`, `VPILOT out of range`, `VPOGO out of range`, `puck_adcs_read` |
| 2026-05-28 | `6A18C280` | 191 KB (+16 B) | Rebuild only |  |
| 2026-05-22 | `6A1091CF` | 191 KB | Rebuild only |  |
| 2026-05-20 | `6A0E01F4` | 191 KB | Debug strings changed |  |
| 2026-05-18 | `6A0B53F7` | 191 KB (-32 B) | Debug strings changed |  |
| 2026-05-14 | `6A05E8B8` | 191 KB (-3 KB) | New messages in the code | ` messages dropped ---`, `TTR REGGES`, `get_id_get_attributes_values`, `get_id_get_string_attribute`, `ibexesb_common`, `smf_set_state` |
| 2026-05-06 | `69FBD45D` | 195 KB (-208 B) | Rebuild only |  |
| 2026-05-05 | `69FA587F` | 195 KB (-152 B) | New messages in the code | `  %s_channel[%u] : %u`, `Slot %u : Connected Ibex %s (Ch %u)` |
| 2026-04-24 | `69EBDC14` | 195 KB (+3 KB) | RF link and channel tuning | `Show costs`, `channel_cost_show` |
| 2026-04-20 | `69E687A0` | 191 KB (+1 KB) | Settings management | `Factory restore --really`, `Failed to delete bt settings`, `Failed to delete debug settings`, `Failed to delete esb settings`, `Failed to delete mte settings`, `Failed to delete user settings`, `Ignoring`, `Log Entry: %u %08x %s %u %08x %08x`, `Starting`, `debug/resetreason`, `factory_restore` |
| 2026-04-08 | `69D6B915` | 190 KB (+128 B) | Debug strings changed |  |
| 2026-03-18 | `69B9EE2D` | 190 KB (+2 KB) | New messages in the code | `Calling %s from exit action`, `Clear reset reason`, `Failed to enable puck UART RX %d`, `Failed to execute GET_INPUT_REPORT`, `Failed to init async rx, err %d`, `Generate assertion failure`, `Generate div0`, `Generate wdt`, `Log Entry: %u %08x %08x %08x`, `NVM reset log`, `New resetreason found`, `Nothing in reset log`, `Print reset reason`, `Resetreason RAM empty`, `Starting Proteus BUILD_TIME_%08x GIT_SHA_%s`, `Watchdog about to expire`, `failed to process state machine (%d)`, `generate_exception_assert`, `generate_exception_div0`, `generate_exception_wdt`, `hid-puck`, `new_state cannot be NULL`, `resetreason_clear`, `resetreason_print`, `uart_nrfx_uarte` |
| 2026-02-24 | `699DE734` | 188 KB (+5 KB) | RF link and channel tuning | `%02u: %s/%s  %s/%s  %s/%s  %s/%s`, `Best : %u`, `Configure cost funtion scaling factors`, `Dump controller PER`, `Enable/Disable debug prints of channel costs`, `Listing current cost function scaling factors`, `Show bg rssi map`, `Slot %u: Pairing failed`, `Slot %u: Pairing successful`, `Updating cost function scaling factors`, `Usage: radio_send_ch <timout_s> [<channels]`, `background_rssi_show`, `channel_cost`, `channel_cost_debug`, `packet_error_rate`, `radio_send_channels`, `radio_send_channels <timeout_s> [channels]` |
| 2026-02-05 | `69850FF3` | 182 KB (+304 B) | Settings-corruption recovery | `Erasing the whole settings block to recover`, `Potential corrupt settings partition. All pages are occupied`, `Recovery faild. Device functionality will be degraded`, `Recovery succeeded!` |
| 2026-01-30 | `697D2B40` | 182 KB (+156 B) | Debug shell and QoS reports | `Adjust or print QOS data reports [interval_ms] [--print]`, `Return QOS reporting to defaults`, `Slot %u : Connecting Ibex %s`, `Slot %u : Host awake`, `Slot %u : Host did not wakeup within timeout`, `Slot %u : Host suspended - waiting for wakeup`, `Slot %u : Host suspended, turn off controller`, `connection_qos`, `connection_qos_stop` |
| 2026-01-13 | `696671DF` | 181 KB (+96 B) | Rebuild only |  |
| 2025-12-16 | `6941BF87` | 181 KB (+33 KB) | RF link and channel tuning | `  %s_backup_channel : %u`, `  %s_connection_uptime_s: %u`, `  %s_rf_channel : %u`, `%s_state : %s`, `, function: `, `0123456789ABCDEF`, `0123456789abcdef`, `Balloc succeeded`, `CONNECTED`, `CONNECTED_SUSP`, `CONNECTING_SUSP`, `IDLE_SUSP`, `Ibex took too long to shutdown`, `Infinity`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `Show connection stats`, `Slot %u :     disconnected`, `Slot %u :     done`, `Slot %u : Connected Ibex %s (Ch %u/%u)`, `Slot %u : Connected Ibex %s (susp) (Ch %u/%u)`, `Slot %u : Connection timeout`, `Slot %u : Disconnect message`, `Slot %u : Disconnect message from switch`, `Slot %u : Disconnect message while updating backup channel`, `Slot %u : Proactive channel switch %u/%u -> %u/%u`, `Slot %u : Protocol version updated %u`, `Slot %u : Sending protocol version: %u %u`, `Slot %u : Tearing down Ibex %s (Ch %u/%u)`, `Slot %u : Using backup channel %u / %u`, `Slot %u: Unrecognized protocol version %u`, `Suspended timeout`, `assertion "%s" failed: file "%s", line %d%s%s`, `esb_set_rf_channel %d %u`, `get_id_get_attributes_values`, `get_id_get_string_attribute`, `ibex%d Unknown state %u` |
| 2025-11-21 | `69209D2F` | 148 KB (-30 KB) | New messages in the code | `Starting Proteus BUILD_TIME_%08x GIT_SHA_%s`, `ibex%d %06u %04u %04u %02u -%02u `, `ibex%d %s` |
| 2025-11-18 | `691CFEB0` | 178 KB | First archived build |  |
