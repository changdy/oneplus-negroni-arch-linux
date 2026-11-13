#!/usr/bin/env python3
"""Protocol regressions for GNSS assistance and fix detection (no device I/O)."""

import collections
import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assist = load("gnss_assist", "scripts/gnss-assist.py")
probe = load("gnss_probe", "artifacts/gnss-20261112/probe.py")


class GnssTests(unittest.TestCase):
    def test_validity_is_seconds_not_injection_milliseconds(self):
        start, end = assist.validity({0x10: bytes.fromhex("e036f66a00000000a800")})
        self.assertEqual(start, 1794520800)
        self.assertEqual(end - start, 168 * 3600)

    def test_server_urls_are_length_prefixed_not_delimited(self):
        urls = ["https://path1.xtracloud.net/xtra3Mgrbej.bin",
                "https://path2.xtracloud.net/xtra3Mgrbej.bin"]
        data = struct.pack("<IHQB", 4, 0, 0, 2)
        data += b"".join(bytes([len(url)]) + url.encode() for url in urls)
        self.assertEqual(assist.server_urls({2: data}), urls)
        with self.assertRaises(ValueError):
            assist.server_urls({2: data[:-1]})

    def test_download_cannot_downgrade_to_http(self):
        with self.assertRaises(ValueError):
            assist.HttpsOnly().redirect_request(None, None, 302, "", {}, "http://example.com/xtra")
        url = b"http://example.com/xtra.bin"
        data = struct.pack("<IHQB", 4, 0, 0, 1) + bytes([len(url)]) + url
        with self.assertRaises(ValueError):
            assist.server_urls({2: data})

    def test_truncated_and_duplicate_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            assist.unpack_tlvs(bytes.fromhex("0104000000"))
        with self.assertRaises(ValueError):
            assist.unpack_tlvs(assist.tlv(1, b"a") * 2)

    def test_indication_before_response_is_not_lost(self):
        body = assist.number(1, "<I", 0) + assist.number(0x10, "<H", 1)
        indication = struct.pack("<BHHH", 4, 9, 0xa7, len(body)) + body
        body = assist.tlv(2, bytes.fromhex("00000000"))
        response = struct.pack("<BHHH", 2, 1, 0xa7, len(body)) + body

        class Socket:
            packets = [indication, response]

            def sendto(self, data, peer):
                pass

            def recvfrom(self, size):
                return self.packets.pop(0), (0, 111)

        loc = object.__new__(assist.Loc)
        loc.peer, loc.sock, loc.transaction = (0, 111), Socket(), 0
        self.assertEqual(loc.command(0xa7)[0x10], b"\x01\x00")

    def test_each_assistance_part_is_acknowledged(self):
        class Loc:
            calls = []

            def command(self, message, payload):
                fields = assist.unpack_tlvs(payload)
                self.calls.append(fields)
                return {0x10: fields[3]}

        loc = Loc()
        with contextlib.redirect_stdout(io.StringIO()):
            assist.inject(loc, bytes(1025))
        self.assertEqual(len(loc.calls), 2)
        self.assertEqual(loc.calls[0][4][:2], b"\x00\x04")
        self.assertEqual(loc.calls[1][4], b"\x01\x00\x00")

        class WrongPart:
            def command(self, message, payload):
                return {0x10: b"\x00\x00"}

        with self.assertRaises(ValueError):
            assist.inject(WrongPart(), bytes(1024))

    def test_uncertainty_axes_do_not_count_as_coordinates(self):
        instance = object.__new__(probe.Probe)
        instance.reports = {0x24: 0}
        instance.have_fix = False
        instance.indication(0x24, {1: bytes(4), 0x13: bytes(4), 0x14: bytes(4)})
        self.assertFalse(instance.have_fix)
        instance.indication(0x24, {1: b"\x01\x00\x00\x00", 0x10: bytes(8), 0x11: bytes(8)})
        self.assertFalse(instance.have_fix)
        instance.indication(0x24, {1: bytes(4), 0x10: bytes(8), 0x11: bytes(8)})
        self.assertTrue(instance.have_fix)

    def test_rf_metrics_preserve_signed_gain_and_unscaled_wire_values(self):
        fields = {2: bytes.fromhex("f4ffffff"), 0x17: bytes.fromhex("faffffff"),
                  0x10: struct.pack("<HHi", 200, 201, 7900), 0x11: b"truncated"}
        result = probe.rf_metrics(fields)
        self.assertEqual(result["band1_pga_db"], -12)
        self.assertEqual(result["band5_pga_db"], -6)
        self.assertEqual(result["gps_l1"]["jammer_raw"], 7900)
        self.assertNotIn("glo_g1", result)

    def test_measurements_use_protocol_scales_and_valid_status_bits(self):
        row = struct.pack("<HBIHBBQQHH", 7, 0, 3, 0, 1, 1, 4, 0x08000004, 348, 0)
        fields = {3: struct.pack("<I", 1), 0x1e: struct.pack("<Q", 1),
                  0x1f: struct.pack("<ii", -1234, 7900), 0x1b: b"\1" + row + bytes(59)}
        result = probe.measurement_summary(fields)
        self.assertEqual(result["max_cn0"], 34.8)
        self.assertEqual(result["agc_db"], -12.34)
        self.assertEqual(result["bp_db"], 79)
        self.assertEqual(result["known_sv_ms"], 1)
        self.assertEqual(result["fresh"], 0)  # The fresh bit is not marked valid.
        self.assertEqual(result["with_ephemeris"], 1)
        self.assertNotIn("agc_status", result)  # Absent does not mean no saturation.
        with self.assertRaises(ValueError):
            probe.measurement_summary({0x1b: b"\1" + bytes(89)})

    def test_measurement_configuration_waits_for_successful_indication(self):
        def packet(flags, fields):
            return struct.pack("<BHHH", flags, 1, 0x88, len(fields)) + fields, (0, 111)

        response = packet(2, struct.pack("<BH", 2, 4) + bytes(4))
        for status in (0, 1):
            indication = packet(4, struct.pack("<BHI", 1, 4, status))
            for packets in ([response, indication], [indication, response]):
                with self.subTest(status=status, first_flags=packets[0][0][0]):
                    class Socket:
                        def sendto(self, data, peer):
                            pass

                        def recvfrom(self, size):
                            return self.packets.pop(0)

                    instance = probe.Probe.__new__(probe.Probe)
                    instance.sock = Socket()
                    instance.sock.packets = list(packets)
                    instance.peer = (0, 111)
                    instance.transaction = 0
                    instance.reports = collections.Counter()
                    with contextlib.redirect_stdout(io.StringIO()):
                        if status:
                            with self.assertRaises(RuntimeError):
                                instance.request(0x88, indication=True)
                        else:
                            instance.request(0x88, indication=True)


if __name__ == "__main__":
    unittest.main()
