#!/usr/bin/env python3
"""Verify that an offline image carries the VoLTE IMS data service."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
UNIT = "negroni-81voltd.service"
DAEMON = "/usr/local/libexec/81voltd"
# image path -> (repository source, mode)
FILES = {
    DAEMON: ("config/volte/81voltd", "0755"),
    f"/etc/systemd/system/{UNIT}": (f"config/systemd/{UNIT}", "0644"),
    "/etc/polkit-1/rules.d/49-negroni-spacebar-bearers.rules":
        ("config/volte/49-negroni-spacebar-bearers.rules", "0644"),
}
# 81voltd is prebuilt against these; mmcli gates the unit's start.
DEPENDENCIES = ("/usr/lib/libmm-glib.so.0", "/usr/lib/libqrtr.so.1", "/usr/bin/mmcli")


def verify(image_dir, log_dir):
    image = image_dir / "root.img"
    log_dir.mkdir(parents=True, exist_ok=True)
    report = log_dir / "volte-verification.json"
    report.unlink(missing_ok=True)

    def debugfs(command):
        result = subprocess.run(["debugfs", "-R", command, str(image)],
                            capture_output=True, check=True)
        # debugfs reports many command failures only on stderr, with exit status 0.
        errors = result.stderr.decode().splitlines()[1:]
        if errors:
            raise RuntimeError("; ".join(errors))
        return result.stdout

    checksums = dict()
    for target, (origin, mode) in FILES.items():
        content = debugfs(f"cat {target}")
        if content != (PROJECT / origin).read_bytes():
            raise RuntimeError(f"image/source mismatch: {target}")
        metadata = debugfs(f"stat {target}").decode()
        if (not re.search(f"Type:[ ]+regular[ ]+Mode:[ ]+{mode}", metadata)
                or not re.search("User:[ ]+0[ ]+Group:[ ]+0", metadata)):
            raise RuntimeError(f"{target} must be root-owned, regular, mode {mode}")
        checksums[target] = hashlib.sha256(content).hexdigest()
    recorded = (PROJECT / "config/volte/81voltd.source").read_text().splitlines()
    if f"sha256 {checksums[DAEMON]}" not in recorded:
        raise RuntimeError("81voltd binary does not match config/volte/81voltd.source")
    for dependency in DEPENDENCIES:
        debugfs(f"stat {dependency}")
    wants = debugfs("ls -p /etc/systemd/system/ModemManager.service.wants").decode()
    if f"/{UNIT}/" not in wants:
        raise RuntimeError(f"{UNIT} is not enabled")
    verification = {
        "image": str(image), "service": UNIT, "enabled": True,
        "sha256": checksums,
        # Outgoing call reached ringing-out on the device; call audio is not wired up.
        "hardware_tested": "outgoing call setup only",
    }
    report.write_text(json.dumps(verification, indent=2) + chr(10))
    print("VoLTE image verified: IMS data service installed and enabled")
    return verification


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-volte-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
