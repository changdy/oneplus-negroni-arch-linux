#!/usr/bin/env python3
"""Check camera userspace and external module ABI against the current build."""
import json
import os
from pathlib import Path
import sys
from camera_manifest import MODULES, digest, sources
from image_feature import Image, PROJECT, elf_aarch64, sha256


def verify(image_dir, log_dir):
    image, logs = Image(image_dir), Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "camera-verification.json"
    report.unlink(missing_ok=True)
    kernel = Path(os.environ.get("KERNEL_DIR", PROJECT / "linux"))
    release = (logs / "kernel-release.txt").read_text().strip()
    base = "/usr/lib/negroni/camera"
    manifest = json.loads(image.file(f"{base}/manifest.json", "0644"))
    if manifest["sources"] != sources(PROJECT):
        raise RuntimeError("external camera modules were built from stale sources")
    if (manifest["kernel_release"] != release or manifest["module_symvers_sha256"]
            != digest(kernel / "output/Module.symvers")):
        raise RuntimeError("external camera modules do not match the kernel ABI")
    hashes = {}
    for name in (*MODULES, "negroni-four-camera-test.dtbo"):
        data = image.file(f"{base}/{name}", "0644")
        if sha256(data) != manifest["files"].get(name):
            raise RuntimeError(f"camera artifact hash mismatch: {name}")
        if name in MODULES:
            elf_aarch64(data, name)
            if f"vermagic={release} ".encode() not in data:
                raise RuntimeError(f"camera module vermagic mismatch: {name}")
        hashes[name] = sha256(data)
    firmware = image.file("/usr/lib/firmware/negroni/negroni-four-camera-test.dtbo", "0644")
    if sha256(firmware) != manifest["files"]["negroni-four-camera-test.dtbo"]:
        raise RuntimeError("camera firmware overlay does not match the built overlay")
    for name in ("capture.sh", "eeprom.sh", "still.sh", "multi-capture.sh", "meter.py", "raw-preview.py", "idle.sh", "extra.sh"):
        name = "negroni-camera-" + name
        hashes[name] = image.source(f"/usr/local/bin/{name}", f"scripts/{name}", "0755")
    for path, source in {
        "/etc/udev/rules.d/70-negroni-dma-heap.rules": "config/camera/70-negroni-dma-heap.rules",
        "/etc/wireplumber/wireplumber.conf.d/50-negroni-camera.conf": "config/camera/50-negroni-camera.conf",
    }.items():
        hashes[path] = image.source(path, source)
    result = {"files_sha256": hashes, "kernel_release": release,
              "scope": "Ultrawide application setup; other three cameras are installed experiments, not autoloaded",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("Camera image verified: source hashes, kernel ABI, modules, capture tools, WirePlumber and dma-heap rules")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-camera-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
