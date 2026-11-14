#!/usr/bin/env python3
"""Measure and render one Negroni ultrawide RAW10 frame.

This is a software still path: 2x2 binning, gray-world white balance and an
sRGB curve. It does not apply a module colour matrix or lens shading, and it
is not the Android Spectra ISP.
"""
import argparse
import json
import math
from pathlib import Path

CAMERAS = {
    "ultrawide": {
        "width": 4080,
        "height": 3072,
        "stride": 5104,
        "bayer": "GRBG",
        "black": 64,
        "exposure": (8, 4266),
        "gain": (1, 64),
    },
}
PHASES = {
    "GRBG": ("G", "R", "B", "G"),
    "RGGB": ("R", "G", "G", "B"),
    "BGGR": ("B", "G", "G", "R"),
    "GBRG": ("G", "B", "R", "G"),
}
TARGET_ABOVE_BLACK = 200


def unpack_row(raw, width):
    groups = width // 4
    if len(raw) < groups * 5 or width % 4:
        raise ValueError("RAW row is not packed RAW10")
    pixels = [0] * width
    for group in range(groups):
        offset = group * 5
        low = raw[offset + 4]
        base = group * 4
        for index in range(4):
            pixels[base + index] = (raw[offset + index] << 2) | ((low >> (2 * index)) & 3)
    return pixels


def frame_bytes(path, geometry):
    size = geometry["height"] * geometry["stride"]
    data = path.read_bytes()
    if not data or len(data) % size:
        raise ValueError(
            f"Expected complete {geometry['width']}x{geometry['height']} "
            f"frames of {size} bytes")
    return data[-size:]


def sample_phases(frame, geometry, step):
    width, height, stride = geometry["width"], geometry["height"], geometry["stride"]
    totals = {"R": 0, "G": 0, "B": 0}
    counts = {"R": 0, "G": 0, "B": 0}
    labels = PHASES[geometry["bayer"]]
    for y in range(0, height - 1, step * 2):
        even = unpack_row(frame[y * stride:(y + 1) * stride], width)
        odd = unpack_row(frame[(y + 1) * stride:(y + 2) * stride], width)
        for x in range(0, width - 1, step * 2):
            cells = (even[x], even[x + 1], odd[x], odd[x + 1])
            for label, value in zip(labels, cells):
                totals[label] += value
                counts[label] += 1
    if min(counts.values()) < 4:
        raise ValueError("Not enough Bayer samples")
    return {channel: totals[channel] / counts[channel] for channel in totals}


def white_balance(means, black):
    green = means["G"] - black
    if green <= 1:
        raise ValueError("Frame is too dark to estimate white balance")
    gains = {}
    for channel in ("R", "G", "B"):
        level = means[channel] - black
        if level <= 1:
            raise ValueError(f"{channel} channel is too dark to estimate white balance")
        gains[channel] = green / level
    if any(gain <= 0 or gain > 8 for gain in gains.values()):
        raise ValueError("White-balance estimate is outside 0..8; scene is not near neutral")
    return gains


def suggest_exposure(mean_green, black, exposure, gain, geometry):
    level = max(mean_green - black, 1)
    scale = min(8.0, max(0.25, TARGET_ABOVE_BLACK / level))
    exp_min, exp_max = geometry["exposure"]
    gain_min, gain_max = geometry["gain"]
    product = exposure * gain * scale
    new_gain = gain_min
    new_exposure = product / new_gain
    if new_exposure > exp_max:
        new_exposure = exp_max
        new_gain = min(gain_max, max(gain_min, round(product / new_exposure)))
        new_exposure = min(exp_max, max(exp_min, product / new_gain))
    new_exposure = int(round(min(exp_max, max(exp_min, new_exposure))))
    new_gain = int(min(gain_max, max(gain_min, new_gain)))
    return new_exposure, new_gain, scale


def srgb_byte(value, black, gain, white=1023):
    linear = max(0.0, value - black) * gain / (white - black)
    linear = min(1.0, linear)
    if linear <= 0.0031308:
        encoded = 12.92 * linear
    else:
        encoded = 1.055 * math.pow(linear, 1 / 2.4) - 0.055
    return min(255, max(0, int(round(encoded * 255))))


def render_ppm(frame, geometry, gains, black, output):
    width, height, stride = geometry["width"], geometry["height"], geometry["stride"]
    labels = PHASES[geometry["bayer"]]
    out_w, out_h = width // 2, height // 2
    pixels = bytearray(out_w * out_h * 3)
    destination = 0
    for y in range(0, height - 1, 2):
        even = unpack_row(frame[y * stride:(y + 1) * stride], width)
        odd = unpack_row(frame[(y + 1) * stride:(y + 2) * stride], width)
        for x in range(0, width - 1, 2):
            channels = {"R": 0, "G": 0, "B": 0}
            green_count = 0
            for label, value in zip(labels, (even[x], even[x + 1], odd[x], odd[x + 1])):
                if label == "G":
                    channels["G"] += value
                    green_count += 1
                else:
                    channels[label] = value
            channels["G"] /= green_count
            for channel in ("R", "G", "B"):
                pixels[destination] = srgb_byte(channels[channel], black, gains[channel])
                destination += 1
    header = f"P6\n{out_w} {out_h}\n255\n".encode("ascii")
    output.write_bytes(header + pixels)
    return out_w, out_h


def measure(path, camera, exposure, gain, step=16):
    geometry = CAMERAS[camera]
    frame = frame_bytes(path, geometry)
    means = sample_phases(frame, geometry, step)
    black = geometry["black"]
    new_exposure, new_gain, scale = suggest_exposure(
        means["G"], black, exposure, gain, geometry)
    result = {
        "camera": camera,
        "bayer": geometry["bayer"],
        "black_level_assumed": black,
        "mean_rgb": means,
        "captured_exposure": exposure,
        "captured_gain": gain,
        "exposure": new_exposure,
        "gain": new_gain,
        "scale": scale,
        "recapture": abs(scale - 1) > 0.15,
        "white_balance_rgb": None,
        "colour_matrix": "uncalibrated identity",
        "lens_shading": "not corrected",
        "isp": "software 2x2 binning, not Spectra",
    }
    try:
        result["white_balance_rgb"] = white_balance(means, black)
    except ValueError as exc:
        result["white_balance_error"] = str(exc)
    return result, frame, geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--camera", choices=sorted(CAMERAS), default="ultrawide")
    parser.add_argument("--exposure", type=int, required=True)
    parser.add_argument("--gain", type=int, required=True)
    parser.add_argument("--ppm", type=Path)
    parser.add_argument("--step", type=int, default=16)
    args = parser.parse_args()
    geometry = CAMERAS[args.camera]
    exp_min, exp_max = geometry["exposure"]
    gain_min, gain_max = geometry["gain"]
    if not exp_min <= args.exposure <= exp_max or not gain_min <= args.gain <= gain_max:
        parser.error("Exposure or gain is outside the ultrawide control range")
    if args.step < 1:
        parser.error("Sample step must be positive")
    if args.ppm and args.ppm.exists():
        parser.error("PPM output already exists")
    try:
        result, frame, geometry = measure(
            args.raw, args.camera, args.exposure, args.gain, args.step)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.ppm:
        gains = result["white_balance_rgb"] or {"R": 1, "G": 1, "B": 1}
        width, height = render_ppm(
            frame, geometry, gains, geometry["black"], args.ppm)
        result["preview_size"] = [width, height]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
