#!/usr/bin/env python3
"""Exercise the binary reader with synthetic data, never stock calibration."""
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib

spec = importlib.util.spec_from_file_location(
    "camera_module", Path(__file__).resolve().parents[1] / "scripts/inspect-camera-sensormodule.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def fixture(width=2, bad_offset=False):
    payloads = [b"test\0", struct.pack("<10I", 0, 3, 0x1234, 1, 4, 2, width, 0, 1, 5),
                b"", struct.pack("<I", 7), struct.pack("<I", 0), b""]
    names = ["sensorName", "regSetting", "slaveAddr", "registerData", "delayUs", "moduleConfiguration"]
    descriptors, pool = bytearray(), bytearray()
    for i, (name, value) in enumerate(zip(names, payloads), 1):
        offset = len(pool) + (10000 if bad_offset and i == 4 else 0)
        descriptors.extend(struct.pack("<I32s6I", i, name.encode(), 0, 0, 0xffffffff,
                                       offset, len(value), i))
        pool.extend(value)
    data = bytearray(204)
    data[:20] = b"QTI Chromatix Header"
    version = b"Parameter Parser V3.5.1 (2207122229)"
    data[40:40 + len(version)] = version
    struct.pack_into("<II", data, 160, 168, 3)
    struct.pack_into("<9I", data, 168, 0, 204, len(descriptors),
                     1, 204 + len(descriptors), len(pool),
                     2, 204 + len(descriptors) + len(pool), 0)
    data.extend(descriptors)
    data.extend(pool)
    struct.pack_into("<I", data, 28, len(data))
    data.extend(struct.pack("<I", zlib.crc32(data)))
    return data


class CameraModuleTest(unittest.TestCase):
    def test_preserves_word_width_for_small_value(self):
        result = reader.SensorModule(fixture()).inspect(True)
        register = result["register_tables"][0]["registers"][0]
        self.assertEqual((register["address"], register["values"], register["data_bytes"]),
                         (0x1234, [7], 2))

    def test_corruption_rejected(self):
        data = fixture()
        data[-5] ^= 1
        with self.assertRaisesRegex(reader.FormatError, "CRC32"):
            reader.SensorModule(data)

    def test_outside_pool_rejected_even_with_valid_crc(self):
        with self.assertRaisesRegex(reader.FormatError, "exceeds value pool"):
            reader.SensorModule(fixture(bad_offset=True))

    def test_unknown_width_is_not_exported_as_registers(self):
        table = reader.SensorModule(fixture(width=0)).inspect(True)["register_tables"][0]
        self.assertFalse(table["decoded"])
        self.assertNotIn("registers", table)

    def test_truncated_input_rejected(self):
        with self.assertRaises(reader.FormatError):
            reader.SensorModule(fixture()[:-1])


if __name__ == "__main__":
    unittest.main()
