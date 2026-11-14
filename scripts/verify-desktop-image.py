#!/usr/bin/env python3
"""Check default desktop applications, Chinese fonts and the rotation setup."""
import json
from pathlib import Path
import sys
from image_feature import Image, PROJECT


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
    }.items():
        hashes[path] = image.source(path, source)
    for path in ("/usr/bin/angelfish", "/usr/bin/snapshot", "/usr/bin/cam", "/usr/bin/kscreen-doctor",
                 "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"):
        image.file(path)
    result = {"packages": packages, "files_sha256": hashes,
              "scope": "Offline delivery check; fresh-image desktop, touch and rotation are untested",
              "hardware_tested": False}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("Desktop image verified: default packages, CJK font, camera/browser executables, rotation setup")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-desktop-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
