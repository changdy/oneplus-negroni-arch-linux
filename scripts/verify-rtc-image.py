#!/usr/bin/env python3
"""Check PMIC RTC counter offset services in the unmounted root image."""
import json
from pathlib import Path
import sys

from image_feature import Image


def verify(image_dir, log_dir):
    image = Image(image_dir)
    files = {}
    files["/usr/local/libexec/negroni-rtc-clock"] = image.source(
        "/usr/local/libexec/negroni-rtc-clock", "config/rtc/negroni-rtc-clock", "0755")
    for unit in ("negroni-rtc-sync.path", "negroni-rtc-sync.service",
                 "negroni-rtc-restore.service"):
        path = f"/etc/systemd/system/{unit}"
        files[path] = image.source(path, f"config/systemd/{unit}")
    image.enabled("negroni-rtc-sync.path")
    image.enabled("negroni-rtc-restore.service", "sysinit.target")
    image.file("/usr/bin/python3")
    image.file("/usr/lib/systemd/systemd-timesyncd")
    report = {
        "image": str(image.path),
        "unit_sha256": files,
        "sync_path_and_restore_enabled": True,
        "hardware_tested": False,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "rtc-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("RTC image verified: PMIC counter script, restore and sync units")
    return report


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-rtc-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
