"""
sc2 — Steam Controller 2 (Triton) protocol library.

Re-exports the most commonly used decoder symbols. See docs/HID_REPORT_FORMAT.md
for the full Report-0x42 layout and docs/FIRMWARE_PROTOCOL.md for the firmware
update protocol.
"""
from .decoder import (
    INPUT_REPORT_SIZES,
    STATE_REPORT_ID,
    STATE_REPORT_SIZE,
    KNOWN_BUTTON_BITS,
    ANALOG_FIELDS,
    ControllerFrame,
    decode_state,
    iter_reports,
    iter_reports_live,
    iter_state_frames,
    diff_unknown,
)

__all__ = [
    "INPUT_REPORT_SIZES",
    "STATE_REPORT_ID",
    "STATE_REPORT_SIZE",
    "KNOWN_BUTTON_BITS",
    "ANALOG_FIELDS",
    "ControllerFrame",
    "decode_state",
    "iter_reports",
    "iter_reports_live",
    "iter_state_frames",
    "diff_unknown",
]
__version__ = "0.1.0"
