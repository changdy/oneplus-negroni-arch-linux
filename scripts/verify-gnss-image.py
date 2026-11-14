#!/usr/bin/env python3
"""Check the deployed AFW fix, runtime provenance, unlock service and helper."""
import json
from pathlib import Path
import sys
from image_feature import Image, PROJECT, elf_aarch64, sha256


def verify(image_dir, log_dir):
    image, logs = Image(image_dir), Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "gnss-verification.json"
    report.unlink(missing_ok=True)
    files = {
        "/opt/negroni-gnss/sbin/ModemManager": ("config/gnss/runtime/ModemManager", "0755"),
        "/opt/negroni-gnss/lib/libqmi-glib.so.5.12.0": ("config/gnss/runtime/libqmi-glib.so.5.12.0", "0755"),
        "/etc/systemd/system/ModemManager.service.d/20-negroni-gnss.conf": ("config/gnss/20-negroni-gnss.conf", "0644"),
        "/etc/systemd/system/negroni-gnss-unlock.service": ("config/gnss/negroni-gnss-unlock.service", "0644"),
        "/usr/local/libexec/negroni-gnss-assist.py": ("scripts/gnss-assist.py", "0755"),
    }
    for name in ("COPYING", "COPYING.LIB"):
        files[f"/usr/share/licenses/negroni-gnss/{name}"] = (f"config/gnss/runtime/{name}", "0644")
    files["/usr/share/licenses/negroni-gnss/sources.txt"] = ("config/gnss/sources.txt", "0644")
    hashes = {path: image.source(path, *source) for path, source in files.items()}
    for path in ("/opt/negroni-gnss/sbin/ModemManager", "/opt/negroni-gnss/lib/libqmi-glib.so.5.12.0"):
        elf_aarch64(image.read(path), path)
    image.link("/opt/negroni-gnss/lib/libqmi-glib.so.5", "libqmi-glib.so.5.12.0")
    image.enabled("negroni-gnss-unlock.service", "ModemManager.service")
    image.file("/usr/bin/qmicli")
    image.file("/usr/bin/qrtr-lookup")
    result = {"files_sha256": hashes, "positioning_on_demand": True,
              "scope": "AFW engine startup fix; valid coordinates, outdoor acquisition and full-image boot are untested",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("GNSS image verified: AFW daemon/library, source licenses, unlock service, assistance helper")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-gnss-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
