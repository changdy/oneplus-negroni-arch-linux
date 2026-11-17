#!/usr/bin/env python3
import os
import subprocess
import unittest
from image_delivery import ImageTest, PROJECT, load_verifier

verifier = load_verifier("desktop")


class DesktopImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        subprocess.run(["bash", str(PROJECT / "scripts/configure-desktop.sh"), str(self.root), str(self.logs)],
                       check=True, capture_output=True, env=dict(os.environ, SUDO_UID="0", SUDO_GID="0"))
        for name in (PROJECT / "config/packages/common-tools.txt").read_text().splitlines():
            self.put(f"var/lib/pacman/local/{name}-1-1/desc", f"%NAME%\n{name}\n\n%VERSION%\n1-1\n".encode())
        for name in ("usr/bin/angelfish", "usr/bin/snapshot", "usr/bin/cam", "usr/bin/kscreen-doctor",
                     "usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"):
            self.put(name, b"delivery fixture")

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_default_desktop_delivery(self):
        self.verify()

    def test_missing_chinese_font_is_rejected(self):
        (self.root / "usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_missing_browser_package_is_rejected(self):
        (self.root / "var/lib/pacman/local/angelfish-1-1/desc").write_text("%NAME%\nother\n")
        with self.assertRaisesRegex(RuntimeError, "angelfish"):
            self.verify()

    def test_missing_nfc_control_is_rejected(self):
        (self.root / "usr/local/libexec/negroni-hardware-control").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_missing_gps_quick_setting_is_rejected(self):
        (self.root / "usr/share/plasma/quicksettings/org.negroni.quicksetting.gps/contents/ui/main.qml").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
