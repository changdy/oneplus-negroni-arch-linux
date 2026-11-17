#!/usr/bin/env python3
"""Check the default language and generated locale in an unmounted image."""
import json
from pathlib import Path
import sys

from image_feature import Image, PROJECT


def verify(image_dir, log_dir):
    image = Image(image_dir)
    locale_conf = image.source("/etc/locale.conf", "config/locale/locale.conf")
    locale_gen = image.file("/etc/locale.gen").decode()
    if "zh_CN.UTF-8 UTF-8" not in locale_gen.splitlines():
        raise RuntimeError("zh_CN.UTF-8 must be enabled in locale.gen")
    archive = image.file("/usr/lib/locale/locale-archive")
    if b"zh_CN.utf8" not in archive:
        raise RuntimeError("zh_CN.utf8 is missing from the generated locale archive")
    report = {
        "language": "zh_CN.UTF-8",
        "locale_conf_sha256": locale_conf,
        "generated_locale_present": True,
        "hardware_tested": False,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "locale-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Locale image verified: Simplified Chinese is the generated default")
    return report


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-locale-image.py IMAGE_DIRECTORY LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
