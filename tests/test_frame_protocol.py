"""
Tests for the HDLC-style firmware-update wire protocol.

These reimplement the encode_msg / decode_msg pair from hardwareupdater.py
and verify they're invertible on synthetic payloads.
"""
import struct
import unittest

SOF_BYTE = 0xAD
EOF_BYTE = 0xAE
ESCAPE_BYTE = 0xAC

MESSAGE_INFO = 0x1233
MESSAGE_FW_BEGIN = 0x1234
MESSAGE_FW_DATA = 0x1235
MESSAGE_FW_END = 0x1236
MESSAGE_RESET = 0x1237
MESSAGE_PROVISION = 0x1238

RSP_ACK = 0


def encode_msg(msg: bytes) -> bytes:
    out = bytes([SOF_BYTE])
    for b in msg:
        if b == ESCAPE_BYTE:
            out += bytes([ESCAPE_BYTE, 0x00])
        elif b == SOF_BYTE:
            out += bytes([ESCAPE_BYTE, 0x01])
        elif b == EOF_BYTE:
            out += bytes([ESCAPE_BYTE, 0x02])
        else:
            out += bytes([b])
    out += bytes([EOF_BYTE])
    return out


def decode_msg(buf: bytes) -> bytes:
    sof = buf.index(SOF_BYTE)
    eof = buf.index(EOF_BYTE, sof + 1)
    payload = buf[sof + 1 : eof]
    out = []
    escape = False
    for c in payload:
        if escape:
            out.append(c + ESCAPE_BYTE)
            escape = False
        elif c == ESCAPE_BYTE:
            escape = True
        else:
            out.append(c)
    return bytes(out)


class FrameEncodingTest(unittest.TestCase):

    def test_simple_payload_roundtrip(self):
        for payload in [
            b"",
            b"\x00",
            b"\x01\x02\x03",
            bytes(range(0, 256)),
        ]:
            encoded = encode_msg(payload)
            self.assertEqual(encoded[0], SOF_BYTE)
            self.assertEqual(encoded[-1], EOF_BYTE)
            decoded = decode_msg(encoded)
            self.assertEqual(decoded, payload)

    def test_escape_byte_in_payload_is_escaped(self):
        payload = bytes([0xAC])
        encoded = encode_msg(payload)
        # Expect: SOF 0xAC 0x00 EOF
        self.assertEqual(encoded, bytes([0xAD, 0xAC, 0x00, 0xAE]))

    def test_sof_byte_in_payload_is_escaped(self):
        payload = bytes([0xAD])
        encoded = encode_msg(payload)
        self.assertEqual(encoded, bytes([0xAD, 0xAC, 0x01, 0xAE]))

    def test_eof_byte_in_payload_is_escaped(self):
        payload = bytes([0xAE])
        encoded = encode_msg(payload)
        self.assertEqual(encoded, bytes([0xAD, 0xAC, 0x02, 0xAE]))

    def test_all_three_special_bytes_in_one_payload(self):
        payload = bytes([0xAC, 0xAD, 0xAE, 0x42])
        encoded = encode_msg(payload)
        # SOF + 3 escape pairs + 0x42 + EOF
        expected = bytes([0xAD,  0xAC, 0x00,  0xAC, 0x01,  0xAC, 0x02,  0x42,  0xAE])
        self.assertEqual(encoded, expected)
        self.assertEqual(decode_msg(encoded), payload)

    def test_random_payload_roundtrip(self):
        import os
        for _ in range(20):
            payload = os.urandom(1 + (os.urandom(1)[0] % 256))
            self.assertEqual(decode_msg(encode_msg(payload)), payload)


class FirmwareMessageTest(unittest.TestCase):

    def test_fw_begin_is_two_bytes(self):
        msg = struct.pack("<H", MESSAGE_FW_BEGIN)
        self.assertEqual(msg, bytes([0x34, 0x12]))

    def test_fw_data_layout(self):
        chunk = b"\xde\xad\xbe\xef"
        msg = struct.pack("<HH", MESSAGE_FW_DATA, len(chunk)) + chunk
        # uint16 type + uint16 length + payload
        self.assertEqual(msg[:2], bytes([0x35, 0x12]))
        self.assertEqual(msg[2:4], bytes([0x04, 0x00]))
        self.assertEqual(msg[4:], chunk)

    def test_fw_end_with_metadata(self):
        metadata = bytes(32)
        msg = struct.pack("<H", MESSAGE_FW_END) + metadata
        self.assertEqual(msg[:2], bytes([0x36, 0x12]))
        self.assertEqual(len(msg), 34)


class FirmwareHeaderTest(unittest.TestCase):

    TRITON_MAGIC = 0xD2D86467
    PROTEUS_MAGIC = 0x2E795631

    def test_triton_magic_bytes_layout(self):
        header = struct.pack("<I", self.TRITON_MAGIC)
        # LE: 67 64 D8 D2
        self.assertEqual(header, bytes([0x67, 0x64, 0xD8, 0xD2]))

    def test_proteus_magic_bytes_layout(self):
        header = struct.pack("<I", self.PROTEUS_MAGIC)
        self.assertEqual(header, bytes([0x31, 0x56, 0x79, 0x2E]))

    def test_payload_size_field(self):
        # Header: 32 bytes total = magic(4) + payload_size(4) + checksum(4) + 20B reserved
        magic = self.TRITON_MAGIC
        payload_size = 0x5C298
        checksum = 0x6FAE706E
        header = struct.pack("<3I", magic, payload_size, checksum) + bytes(20)
        self.assertEqual(len(header), 32)

        parsed_magic, parsed_size, parsed_cs = struct.unpack_from("<3I", header)
        self.assertEqual(parsed_magic, magic)
        self.assertEqual(parsed_size, payload_size)
        self.assertEqual(parsed_cs, checksum)


if __name__ == "__main__":
    unittest.main(verbosity=2)
