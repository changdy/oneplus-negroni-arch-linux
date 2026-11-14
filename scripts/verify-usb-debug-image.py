#!/usr/bin/env python3
"""Verify the USB debug gadget, its NetworkManager link, and boot enablement in an unmounted ext4 image."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
FILES = {
    "/usr/local/bin/usb-gadget.sh": ("config/usb-debug/usb-gadget.sh", "0755"),
    "/etc/systemd/system/usb-gadget.service": ("config/usb-debug/usb-gadget.service", "0644"),
    "/etc/udev/rules.d/86-usb-debug-managed.rules": (
        "config/usb-debug/86-usb-debug-managed.rules", "0644"),
    "/etc/NetworkManager/system-connections/usb-debug.nmconnection": (
        "config/usb-debug/usb-debug.nmconnection", "0600"),
}
LINKS = {
    "/etc/systemd/system/multi-user.target.wants/usb-gadget.service": (
        "/etc/systemd/system/usb-gadget.service", "../usb-gadget.service"),
    "/etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service": (
        "/usr/lib/systemd/system/serial-getty@.service",),
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
    debugfs("stat /usr/bin/dnsmasq")
    links = {}
    for link, allowed in LINKS.items():
        meta = debugfs(f"stat {link}").decode()
        match = re.search(r'Fast link dest: "([^"]+)"', meta)
        if "Type: symlink" not in meta or not match or match[1] not in allowed:
            raise RuntimeError(f"missing enablement link: {link}")
        links[link] = match[1]
    verification = {
        "image": str(image),
        "files_match_sources": True,
        "dnsmasq_present": True,
        "installed_file_sha256": checksums,
        "enablement_links": links,
        "hardware_tested": (
            "2026-11-12/13 NE2210: the same files, hand-installed, give USB SSH at 10.55.0.1 "
            "and a COM3 serial login on USB3 and USB2 ports; a flashed image with them is untested"),
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "usb-debug-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print("USB debug image verified: gadget script, unit, udev rule, NetworkManager link, and enablement")
    return verification


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-usb-debug-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
