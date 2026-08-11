"""
Unit tests for the SC2 decoder library.

Run: python3 -m unittest discover tests
"""
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sc2 import (
    INPUT_REPORT_SIZES,
    STATE_REPORT_ID,
    STATE_REPORT_SIZE,
    KNOWN_BUTTON_BITS,
    ANALOG_FIELDS,
    ControllerFrame,
    decode_state,
    iter_reports,
    iter_state_frames,
    diff_unknown,
)


REPO = Path(__file__).resolve().parent.parent
CAPTURES = REPO / "captures"


class ConstantsTest(unittest.TestCase):
    def test_state_report_size_is_54(self):
        self.assertEqual(STATE_REPORT_SIZE, 54)

    def test_state_report_id_is_42(self):
        self.assertEqual(STATE_REPORT_ID, 0x42)

    def test_all_30_sdl_buttons_present(self):
        expected = {
            "A", "B", "X", "Y", "QAM", "R3", "View", "R4",
            "R5", "RB", "DPad_Down", "DPad_Right", "DPad_Left", "DPad_Up",
            "Menu", "L3", "Steam", "L4", "L5", "LB",
            "RStick_Touch", "RPad_Touch", "RPad_Click", "RTrig_Click",
            "LStick_Touch", "LPad_Touch", "LPad_Click", "LTrig_Click",
            "RGrip_Touch", "LGrip_Touch",
        }
        self.assertEqual(set(KNOWN_BUTTON_BITS.keys()), expected)
        self.assertEqual(len(KNOWN_BUTTON_BITS), 30)

    def test_button_bit_positions_match_sdl_layout(self):
        # SDL TritonButtons enum: bits 0..29 in a uint32 starting at byte 0x02
        expected_layout = {
            "A": (0x02, 0), "B": (0x02, 1), "X": (0x02, 2), "Y": (0x02, 3),
            "QAM": (0x02, 4), "R3": (0x02, 5), "View": (0x02, 6), "R4": (0x02, 7),
            "R5": (0x03, 0), "RB": (0x03, 1),
            "DPad_Down": (0x03, 2), "DPad_Right": (0x03, 3),
            "DPad_Left": (0x03, 4), "DPad_Up": (0x03, 5),
            "Menu": (0x03, 6), "L3": (0x03, 7),
            "Steam": (0x04, 0), "L4": (0x04, 1), "L5": (0x04, 2), "LB": (0x04, 3),
            "RStick_Touch": (0x04, 4), "RPad_Touch": (0x04, 5),
            "RPad_Click": (0x04, 6), "RTrig_Click": (0x04, 7),
            "LStick_Touch": (0x05, 0), "LPad_Touch": (0x05, 1),
            "LPad_Click": (0x05, 2), "LTrig_Click": (0x05, 3),
            "RGrip_Touch": (0x05, 4), "LGrip_Touch": (0x05, 5),
        }
        self.assertEqual(KNOWN_BUTTON_BITS, expected_layout)

    def test_analog_fields_cover_full_imu_region(self):
        names = {f[2] for f in ANALOG_FIELDS}
        # Required analog fields per SDL controller_structs.h
        for required in [
            "TrigL", "TrigR",
            "LStickX", "LStickY", "RStickX", "RStickY",
            "LPadX", "LPadY", "LPress",
            "RPadX", "RPadY", "RPress",
            "IMU_ts",
            "AccelX", "AccelY", "AccelZ",
            "GyroX", "GyroY", "GyroZ",
            "QuatW", "QuatX", "QuatY", "QuatZ",
        ]:
            self.assertIn(required, names, f"missing analog field: {required}")


class StateDecodeTest(unittest.TestCase):
    def setUp(self):
        # Build a synthetic 54-byte Report 0x42 with known content.
        self.report = bytearray(STATE_REPORT_SIZE)
        self.report[0] = 0x42
        self.report[1] = 0xAB  # seq
        self.report[2] = 0b00000101  # A + X
        self.report[4] = 0b00000001  # Steam

    def test_decodes_button_state(self):
        fr = decode_state(bytes(self.report))
        self.assertEqual(fr.seq, 0xAB)
        self.assertTrue(fr.pressed("A"))
        self.assertFalse(fr.pressed("B"))
        self.assertTrue(fr.pressed("X"))
        self.assertTrue(fr.pressed("Steam"))
        self.assertFalse(fr.pressed("Menu"))

    def test_rejects_wrong_report_id(self):
        bad = bytearray(self.report)
        bad[0] = 0x43
        with self.assertRaises(ValueError):
            decode_state(bytes(bad))

    def test_rejects_wrong_size(self):
        with self.assertRaises(ValueError):
            decode_state(bytes(self.report) + b"\x00")


class IdleCaptureTest(unittest.TestCase):
    """Validate decoder against the sample idle capture."""

    @classmethod
    def setUpClass(cls):
        cls.frames = list(iter_state_frames(str(CAPTURES / "sample_idle.bin")))

    def test_at_least_1000_frames(self):
        self.assertGreater(len(self.frames), 1000)

    def test_no_buttons_pressed(self):
        for name in KNOWN_BUTTON_BITS:
            pressed = sum(1 for f in self.frames if f.pressed(name))
            self.assertEqual(pressed, 0, f"idle capture should have 0 {name}-presses, got {pressed}")

    def test_seq_num_increments_linearly(self):
        for prev, curr in zip(self.frames, self.frames[1:]):
            diff = (curr.seq - prev.seq) % 256
            self.assertEqual(diff, 1, f"seq jumped from {prev.seq} to {curr.seq}")


class SteamPressCaptureTest(unittest.TestCase):
    """Sample with Steam-button held — should show ~94% press quote."""

    @classmethod
    def setUpClass(cls):
        cls.frames = list(iter_state_frames(str(CAPTURES / "sample_steam_press.bin")))

    def test_steam_pressed_most_of_capture(self):
        n_steam = sum(1 for f in self.frames if f.pressed("Steam"))
        pct = 100 * n_steam / len(self.frames)
        self.assertGreater(pct, 80.0)
        self.assertLess(pct, 100.0)  # not literally every frame

    def test_other_buttons_not_pressed(self):
        # A and B should be 0 — only Steam should fire
        for name in ["A", "B", "X", "Y", "LB", "RB"]:
            n = sum(1 for f in self.frames if f.pressed(name))
            self.assertEqual(n, 0, f"{name} should be 0 in steam-press capture")


class StreamParseTest(unittest.TestCase):
    """iter_reports must split a mixed-ID stream correctly."""

    def test_idle_stream_has_only_known_report_ids(self):
        path = str(CAPTURES / "sample_idle.bin")
        ids = {r[0] for r in iter_reports(path)}
        # Idle stream may contain 0x42 (state), 0x43, 0x7b (sub-reports)
        for rid in ids:
            self.assertIn(rid, INPUT_REPORT_SIZES, f"unknown report id 0x{rid:02x}")

    def test_report_sizes_match_descriptor(self):
        path = str(CAPTURES / "sample_idle.bin")
        for rep in iter_reports(path):
            self.assertEqual(len(rep), INPUT_REPORT_SIZES[rep[0]])


class DiffUnknownTest(unittest.TestCase):
    """diff_unknown should ignore known button bits and IMU bytes."""

    def test_pressing_known_button_yields_no_unknown_diff(self):
        a = bytearray(STATE_REPORT_SIZE)
        a[0] = 0x42
        b = bytearray(a)
        # Flip the A-button bit (known)
        b[2] = 0x01
        diffs = diff_unknown(bytes(a), bytes(b))
        self.assertEqual(diffs, [])

    def test_flipping_unknown_bit_is_reported(self):
        a = bytearray(STATE_REPORT_SIZE)
        a[0] = 0x42
        b = bytearray(a)
        # Byte 0x05 bit 7 — outside the 30-button table (reserved)
        b[5] = 0b10000000
        diffs = diff_unknown(bytes(a), bytes(b))
        self.assertEqual(len(diffs), 1)
        byte_i, bit_i, old, new = diffs[0]
        self.assertEqual(byte_i, 0x05)
        self.assertEqual(bit_i, 7)
        self.assertEqual(old, 0)
        self.assertEqual(new, 1)

    def test_diff_unknown_tolerates_different_lengths(self):
        a = bytearray(STATE_REPORT_SIZE)
        a[0] = 0x42
        self.assertEqual(diff_unknown(bytes(a[:8]), bytes(a)), [])


class TestDegenerateInput(unittest.TestCase):
    """Regressions for inputs that used to raise the wrong exception or return nothing."""

    def test_empty_report_raises_valueerror_not_indexerror(self):
        with self.assertRaises(ValueError):
            decode_state(b"")

    def test_iter_reports_accepts_bytes(self):
        """The bytes branch used to yield nothing: `return` inside a generator."""
        path = str(CAPTURES / "sample_idle.bin")
        from_path = list(iter_reports(path))
        with open(path, "rb") as fh:
            from_bytes = list(iter_reports(fh.read()))
        self.assertEqual(from_bytes, from_path)
        self.assertTrue(from_bytes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
