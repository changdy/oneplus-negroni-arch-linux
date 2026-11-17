#!/usr/bin/env python3
"""Check desktop packages, quick settings and default KRDP delivery."""
import json
from pathlib import Path
import sys
from image_feature import Image, PROJECT

KRDP_UNIT = "app-org.kde.krdpserver.service"


def verify(image_dir, log_dir):
    image, logs = Image(image_dir), Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "desktop-verification.json"
    report.unlink(missing_ok=True)
    packages = image.packages((PROJECT / "config/packages/common-tools.txt").read_text().splitlines())
    hashes = {}
    for path, source in {
        "/etc/xdg/autostart/negroni-desktop-defaults.desktop": "config/desktop/negroni-desktop-defaults.desktop",
        "/usr/local/libexec/negroni-desktop-defaults.py": "config/desktop/negroni-desktop-defaults.py",
        "/usr/local/libexec/negroni-hardware-control": "config/quicksettings/negroni-hardware-control",
        "/usr/share/polkit-1/actions/org.negroni.hardware-control.policy": "config/quicksettings/org.negroni.hardware-control.policy",
        "/etc/modprobe.d/nxp-nci-off.conf": "config/quicksettings/nxp-nci-off.conf",
        "/etc/xdg/krdpserverrc": "config/desktop/krdpserverrc",
        f"/etc/systemd/user/{KRDP_UNIT}.d/10-negroni-usb.conf": "config/desktop/krdp-usb.conf",
    }.items():
        hashes[path] = image.source(path, source, "0755" if path.endswith("/negroni-hardware-control") else "0644")
    path = "/usr/local/libexec/negroni-krdp-server.py"
    hashes[path] = image.source(path, "config/desktop/negroni-krdp-server.py", "0755")
    for setting in ("nfc", "gyro", "gps", "krdp"):
        base = f"/usr/share/plasma/quicksettings/org.negroni.quicksetting.{setting}"
        source = f"config/quicksettings/{setting}"
        hashes[f"{base}/metadata.json"] = image.source(f"{base}/metadata.json", f"{source}/metadata.json", "0644")
        hashes[f"{base}/contents/ui/main.qml"] = image.source(
            f"{base}/contents/ui/main.qml", f"{source}/contents/ui/main.qml", "0644")
    for path in ("/usr/bin/angelfish", "/usr/bin/snapshot", "/usr/bin/cam", "/usr/bin/kscreen-doctor",
                 "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"):
        image.file(path)
    for path in ("/usr/bin/krdpserver", "/usr/bin/openssl"):
        image.file(path, "0755")
    image.file(f"/usr/lib/systemd/user/{KRDP_UNIT}")
    preset = image.file("/usr/lib/systemd/user-preset/00-krdp.preset").decode().splitlines()
    if f"disable {KRDP_UNIT}" not in preset:
        raise RuntimeError("KRDP package must declare a disabled preset")
    for user_units in ("/etc/systemd/user", "/usr/lib/systemd/user", "/home/oneplus/.config/systemd/user"):
        link = f"{user_units}/plasma-workspace.target.wants/{KRDP_UNIT}"
        if image.query(f"stat {link}", missing_ok=True) is not None:
            raise RuntimeError(f"KRDP must start disabled: {link}")
    result = {"packages": packages, "files_sha256": hashes,
              "krdp_autostart": False,
              "scope": "Offline delivery check; fresh-image desktop, touch, rotation and RDP are untested",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("Desktop image verified: packages, rotation defaults, quick settings and KRDP disabled")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-desktop-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
