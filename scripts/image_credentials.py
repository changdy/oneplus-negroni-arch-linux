#!/usr/bin/env python3
"""Read and install the login credentials for a fresh image."""

import json
from pathlib import Path
import subprocess
import sys


CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / "image-credentials.json"
DEFAULT_ONEPLUS_PASSWORD = "123321"


def load_image_credentials():
    credentials = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    if credentials.get("username", "oneplus") != "oneplus":
        raise SystemExit("image-credentials.json must target the oneplus account.")
    password = credentials.get("password", DEFAULT_ONEPLUS_PASSWORD)
    root_password = credentials.get("root_password")
    for field, value in (("password", password), ("root_password", root_password)):
        if not isinstance(value, str) or not value or any(char in value for char in "\r\n\0"):
            raise SystemExit(f"Invalid {field} in image-credentials.json.")
    return password, root_password


def install_image_credentials(target_dir):
    password, root_password = load_image_credentials()
    subprocess.run(
        ["chroot", target_dir, "chpasswd"],
        input=f"oneplus:{password}\nroot:{root_password}\n",
        text=True,
        check=True,
    )


if __name__ == "__main__":
    install_image_credentials(sys.argv[1])
