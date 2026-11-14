#!/usr/bin/env python3
"""Verify the SLPI file server, gyroscope publisher, and boot enablement in an unmounted ext4 image."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
UNITS = ("hexagonrpcd-sdsp.service", "negroni-gyro.service")
FILES = {
    "/usr/local/sbin/negroni-gyro": ("config/sensors/negroni-gyro", "0755"),
    "/usr/share/dbus-1/system.d/org.negroni.Gyroscope.conf": (
        "config/sensors/org.negroni.Gyroscope.conf", "0644"),
    "/etc/systemd/system/negroni-gyro.service": ("config/systemd/negroni-gyro.service", "0644"),
    "/usr/local/libexec/negroni-sensor-files": ("config/sensors/negroni-sensor-files", "0755"),
    "/usr/local/libexec/hexagonrpcd-sdsp-wait": ("config/sensors/hexagonrpcd-sdsp-wait", "0755"),
    "/etc/systemd/system/negroni-sensor-files.service": (
        "config/systemd/negroni-sensor-files.service", "0644"),
    "/etc/systemd/system/hexagonrpcd-sdsp.service": (
        "config/systemd/hexagonrpcd-sdsp.service", "0644"),
    "/usr/share/negroni/sensors/sns_reg.conf": ("config/sensors/qcom/sns_reg.conf", "0644"),
}
for json_file in sorted((PROJECT / "config/sensors/qcom/config").glob("*.json")):
    FILES[f"/usr/share/negroni/sensors/config/{json_file.name}"] = (
        str(json_file.relative_to(PROJECT)), "0644")


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
    debugfs("stat /usr/local/bin/hexagonrpcd")
    debugfs("stat /usr/local/lib/libhexagonrpc.so.0.5")
    links = {}
    for unit in UNITS:
        link = f"/etc/systemd/system/multi-user.target.wants/{unit}"
        meta = debugfs(f"stat {link}").decode()
        match = re.search(r'Fast link dest: "([^"]+)"', meta)
        if ("Type: symlink" not in meta or not match
                or match[1] not in (f"/etc/systemd/system/{unit}", f"../{unit}")):
            raise RuntimeError(f"{unit} must be enabled: {link}")
        links[link] = match[1]
    verification = {
        "image": str(image),
        "services_enabled": list(UNITS),
        "files_match_sources": True,
        "libssc_present": True,
        "hexagonrpc_present": True,
        "installed_file_sha256": checksums,
        "enablement_links": links,
        "hardware_tested": (
            "2026-11-14 NE2210: gyroscope stationary sample over the file and system bus; "
            "accelerometer auto-rotation, light and proximity with a hand-installed hexagonrpc "
            "serving /usr/share/qcom. The /run/negroni-sensors boot assembly is untested."),
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "sensors-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print("Sensor image verified: hexagonrpc files, stock sensor JSON, gyroscope, units, and boot enablement")
    return verification


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-sensors-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
