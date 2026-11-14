#!/usr/bin/env python3
"""Synthetic RAW10 checks for the software still meter. No phone and no photos."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "camera_meter", Path(__file__).resolve().parents[1] / "scripts/negroni-camera-meter.py")
meter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meter)


def pack_raw10(pixels, width, height, stride=None):
    packed = width * 5 // 4
    stride = stride or packed
    out = bytearray(height * stride)
    for y in range(height):
        for group in range(width // 4):
            values = [pixels[y * width + group * 4 + index] for index in range(4)]
            low = 0
            base = y * stride + group * 5
            for index, value in enumerate(values):
                out[base + index] = value >> 2
                low |= (value & 3) << (2 * index)
            out[base + 4] = low
    return bytes(out)


class CameraMeterTest(unittest.TestCase):
    def test_roundtrip_and_gray_world(self):
        width, height = 8, 4
        pixels = []
        for _y in range(height):
            for x in range(width):
                even = _y % 2 == 0
                if even:
                    pixels.append(100 if x % 2 == 0 else 200)
                else:
                    pixels.append(50 if x % 2 == 0 else 100)
        raw = pack_raw10(pixels, width, height, stride=16)
        geometry = {
            "width": width, "height": height, "stride": 16, "bayer": "GRBG", "black": 0,
            "exposure": (8, 4266), "gain": (1, 64),
        }
        means = meter.sample_phases(raw, geometry, 1)
        self.assertEqual(means, {"R": 200, "G": 100, "B": 50})
        gains = meter.white_balance(means, 0)
        self.assertEqual(gains, {"R": 0.5, "G": 1, "B": 2})

    def test_exposure_scales_then_clamps_into_gain(self):
        geometry = meter.CAMERAS["ultrawide"]
        exposure, gain, scale = meter.suggest_exposure(64 + 50, 64, 1000, 1, geometry)
        self.assertEqual(scale, 4)
        self.assertEqual((exposure, gain), (4000, 1))
        exposure, gain, scale = meter.suggest_exposure(64 + 25, 64, 4000, 8, geometry)
        self.assertEqual(scale, 8)
        self.assertEqual(exposure, 4266)
        self.assertGreater(gain, 8)
        self.assertLessEqual(gain, 64)

    def test_srgb_endpoints(self):
        self.assertEqual(meter.srgb_byte(64, 64, 1), 0)
        self.assertEqual(meter.srgb_byte(1023, 64, 1), 255)


if __name__ == "__main__":
    unittest.main()
