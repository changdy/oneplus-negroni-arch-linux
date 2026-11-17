#!/usr/bin/env python3
"""Require every installed Kbuild module and dependency index to reach root.img."""
import json
import os
from pathlib import Path
import sys
from image_feature import Image, PROJECT, sha256


def verify(image_dir, log_dir):
    image, logs = Image(image_dir), Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "kernel-modules-verification.json"
    report.unlink(missing_ok=True)
    kernel = Path(os.environ.get("KERNEL_DIR", PROJECT / "linux"))
    release = (logs / "kernel-release.txt").read_text().strip()
    if release != (kernel / "output/include/config/kernel.release").read_text().strip():
        raise RuntimeError("kernel release log does not match the current build")
    source = kernel / "output/out-modules/lib/modules" / release
    files = sorted(p for p in source.rglob("*") if p.is_file() and not p.is_symlink())
    if not files or not (source / "modules.dep").is_file():
        raise RuntimeError("the installed kernel module tree is incomplete")
    slider = source / "kernel/drivers/input/misc/mxm1120-slider.ko"
    if not any(Path(str(slider) + suffix).is_file() for suffix in ("", ".xz", ".zst", ".gz")):
        raise RuntimeError("the kernel module tree is missing the MXM1120 alert slider")
    hashes = {}
    for path in files:
        name = str(path.relative_to(source))
        target = f"/usr/lib/modules/{release}/{name}"
        data = image.read(target)  # Some valid modules.* metadata files can be empty.
        if data != path.read_bytes():
            raise RuntimeError(f"kernel module/index mismatch: {target}")
        hashes[name] = sha256(data)
    result = {"kernel_release": release, "files_sha256": hashes,
              "scope": "All Kbuild-installed modules and indices, excluding build/source symlinks",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Kernel modules image verified: {len(files)} module and metadata files match Kbuild")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-kernel-modules-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
