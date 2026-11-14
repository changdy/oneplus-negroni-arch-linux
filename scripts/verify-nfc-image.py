#!/usr/bin/env python3
"""Check NFC runtime tools, clock fallback and matching kernel modules offline."""
import json
from pathlib import Path
import sys
from image_feature import Image, PROJECT, elf_aarch64, sha256


def verify(image_dir, log_dir):
    image, logs = Image(image_dir), Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "nfc-verification.json"
    report.unlink(missing_ok=True)
    hashes = {"/etc/modprobe.d/nxp-nci.conf": image.source(
        "/etc/modprobe.d/nxp-nci.conf", "config/nfc/nxp-nci.conf")}
    manifest = json.loads(image.file("/usr/share/negroni/nfc/manifest.json", "0644"))
    for tool in ("nfc-up", "nfc-live", "nfc-sniff", "nfc-emulate"):
        path = f"/usr/local/sbin/{tool}"
        data = image.file(path, "0755")
        elf_aarch64(data, path)
        if manifest["sources"].get(tool) != sha256((PROJECT / f"artifacts/nfc-20261114/{tool}.c").read_bytes()):
            raise RuntimeError(f"stale NFC tool source: {tool}")
        if manifest["tools"].get(tool) != sha256(data):
            raise RuntimeError(f"NFC tool hash mismatch: {tool}")
        hashes[path] = sha256(data)
    release = (logs / "kernel-release.txt").read_text().strip()
    modules = image.read(f"/usr/lib/modules/{release}/modules.dep").decode()
    for module in ("nxp-nci.ko", "nxp-nci_i2c.ko", "nci.ko", "nfc.ko"):
        paths = [line.split(":", 1)[0] for line in modules.splitlines()
                 if Path(line.split(":", 1)[0]).name == module]
        if len(paths) != 1:
            raise RuntimeError(f"missing NFC module dependency entry: {module}")
        image.file(f"/usr/lib/modules/{release}/{paths[0]}")
    result = {"files_sha256": hashes, "kernel_release": release,
              "scope": "Offline files and module dependency entries; no automatic polling or UID emulation",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("NFC image verified: clock config, four ARM64 tools, kernel modules")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-nfc-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
