#!/usr/bin/env python3
"""Render the tested S5KJN1 pgAA capture; requires NumPy and Pillow.

This is a diagnostic half-resolution preview, without a calibrated colour
matrix or lens shading correction. White balance is explicit, never implicit.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def numbers(value, count, kind):
    try:
        result = [kind(item) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated numbers") from exc
    if len(result) != count:
        raise argparse.ArgumentTypeError(f"Expected {count} comma-separated numbers")
    return result


def unpack_raw10(path, frame):
    width, height, stride = 4080, 3072, 5104
    frame_bytes = height * stride
    length = path.stat().st_size
    if not length or length % frame_bytes:
        raise ValueError("Expected complete 4080x3072 RAW10 frames with stride 5104")
    count = length // frame_bytes
    if frame < 0:
        frame += count
    if not 0 <= frame < count:
        raise ValueError(f"Frame index out of range (file has {count} frames)")
    with path.open("rb") as source:
        source.seek(frame * frame_bytes)
        packed = np.frombuffer(source.read(frame_bytes), dtype=np.uint8)
    packed = packed.reshape(height, stride)[:, :width * 5 // 4]
    groups = packed.reshape(height, width // 4, 5).astype(np.uint16)
    raw = np.empty((height, width), dtype=np.float32)
    for i in range(4):
        raw[:, i::4] = (groups[:, :, i] << 2) | ((groups[:, :, 4] >> (2 * i)) & 3)
    return raw, frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frame", type=int, default=-1, help="zero-based; default last frame")
    parser.add_argument("--black", type=float, default=64, help="provisional RAW black level")
    parser.add_argument("--ev", type=float, default=0, help="display exposure adjustment in stops")
    parser.add_argument("--max-width", type=int, default=1020)
    balance = parser.add_mutually_exclusive_group()
    balance.add_argument("--wb", type=lambda s: numbers(s, 3, float), metavar="R,G,B")
    balance.add_argument("--wb-roi", type=lambda s: numbers(s, 4, int), metavar="X,Y,W,H",
                         help="estimate gains from an assumed neutral patch in full RAW coordinates")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new filename")
    if not 0 <= args.black < 1023 or not -10 <= args.ev <= 10 or args.max_width < 1:
        parser.error("Invalid black level, exposure adjustment or output width")
    try:
        raw, frame = unpack_raw10(args.raw, args.frame)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    # pgAA is GRBG: average the two greens, retaining one RGB sample per 2x2 cell.
    rgb = np.stack([raw[0::2, 1::2],
                    (raw[0::2, 0::2] + raw[1::2, 1::2]) / 2,
                    raw[1::2, 0::2]], axis=-1) - args.black
    gains = np.ones(3, dtype=np.float64)
    patch_median = None
    if args.wb is not None:
        gains = np.asarray(args.wb, dtype=np.float64)
    elif args.wb_roi is not None:
        x, y, width, height = args.wb_roi
        if (any(value % 2 for value in args.wb_roi) or min(x, y) < 0 or
                min(width, height) < 2 or x + width > 4080 or y + height > 3072):
            parser.error("ROI must be even-aligned, positive-sized and within the RAW frame")
        patch = rgb[y // 2:(y + height) // 2, x // 2:(x + width) // 2]
        # Avoid near-black and clipped cells; this is a scene assumption, not calibration.
        valid = (patch.min(axis=-1) > 8) & (patch.max(axis=-1) < 800)
        if valid.sum() < 100:
            parser.error("Neutral patch contains too few usable cells")
        patch_median = np.median(patch[valid].astype(np.float64), axis=0)
        gains = patch_median[1] / patch_median
    if not np.isfinite(gains).all() or (gains <= 0).any() or (gains > 16).any():
        parser.error("White balance gains must be finite and in (0,16]")
    # Fixed RAW white point: matched previews differ only by the requested gains/EV.
    linear = np.clip(rgb * gains * 2 ** args.ev / (1023 - args.black), 0, 1)
    display = np.where(linear <= 0.0031308, 12.92 * linear,
                       1.055 * linear ** (1 / 2.4) - 0.055)
    preview = Image.fromarray(np.rint(display * 255).astype(np.uint8))
    if preview.width > args.max_width:
        preview = preview.resize((args.max_width,
                                  round(preview.height * args.max_width / preview.width)),
                                 Image.Resampling.LANCZOS)
    preview.save(args.output)
    metadata = {
        "frame": frame, "format": "GRBG RAW10 / pgAA", "stride": 5104,
        "black_level_assumed": args.black, "white_level": 1023,
        "white_balance_rgb": gains.tolist(), "neutral_roi_raw": args.wb_roi,
        "neutral_patch_median_after_black": None if patch_median is None else patch_median.tolist(),
        "ev": args.ev, "transfer": "sRGB", "colour_matrix": "uncalibrated identity",
        "lens_shading": "not corrected", "orientation": "native sensor orientation",
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
