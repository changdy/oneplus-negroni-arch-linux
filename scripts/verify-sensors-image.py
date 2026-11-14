#!/usr/bin/env python3
"""Verify the gyroscope publisher and its boot enablement in an unmounted ext4 image."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
UNIT = "negroni-gyro.service"
FILES = {
    "/usr/local/sbin/negroni-gyro": ("config/sensors/negroni-gyro", "0755"),
    "/usr/share/dbus-1/system.d/org.negroni.Gyroscope.conf": (
        "config/sensors/org.negroni.Gyroscope.conf", "0644"),
    f"/etc/systemd/system/{UNIT}": (f"config/systemd/{UNIT}", "0644"),
}


def verify(image_dir, log_dir):
    image = image_dir / "root.img"

    def debugfs(command):
        result = subprocess.run(["debugfs", "-R", command, str(image)],
                                capture_output=True, check=True)
        errors = result.stderr.decode().splitlines()[1:]
        if errors:
            raise RuntimeError("\n".join(errors))
        return result.stdout

    checksums = {}
    for target, (source, mode) in FILES.items():
        installed = debugfs(f"cat {target}")
        if installed != (PROJECT / source).read_bytes():
            raise RuntimeError(f"image/source mismatch: {target}")
        meta = debugfs(f"stat {target}").decode()
        if (not re.search(rf"Type:\s+regular\s+Mode:\s+{mode}", meta)
                or not re.search(r"User:\s+0\s+Group:\s+0", meta)):
            raise RuntimeError(f"{target} must be regular, root-owned, mode {mode}")
        checksums[target] = hashlib.sha256(installed).hexdigest()
    debugfs("stat /usr/lib/libssc.so.2")
    link = f"/etc/systemd/system/multi-user.target.wants/{UNIT}"
    meta = debugfs(f"stat {link}").decode()
    match = re.search(r'Fast link dest: "([^"]+)"', meta)
    if ("Type: symlink" not in meta or not match
            or match[1] not in (f"/etc/systemd/system/{UNIT}", f"../{UNIT}")):
        raise RuntimeError(f"gyroscope service must be enabled: {link}")
    verification = {
        "image": str(image),
        "service": UNIT,
        "service_enabled": True,
        "files_match_sources": True,
        "libssc_present": True,
        "installed_file_sha256": checksums,
        "enablement_link": link,
        "enablement_target": match[1],
        "hardware_tested": "2026-11-14 NE2210: stationary panel-frame sample over the file and system bus; axis signs not turned by hand",
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "sensors-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print("Sensor image verified: gyroscope binary, bus policy, unit, and boot enablement")
    return verification


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-sensors-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
