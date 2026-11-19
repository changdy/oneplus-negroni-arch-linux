#!/usr/bin/env python3
"""Exercise RTC unit installation and ext4 delivery checks."""
import os
import subprocess
import unittest

from image_delivery import ImageTest, PROJECT, load_verifier


verifier = load_verifier("rtc")


class RTCImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        self.put("usr/bin/python3.14", b"fixture", 0o755)
        self.link("usr/bin/python3", "python3.14")
        self.put("usr/lib/systemd/systemd-timesyncd", b"fixture", 0o755)
        subprocess.run(
            ["bash", str(PROJECT / "scripts/configure-rtc.sh"), str(self.root), str(self.logs)],
            check=True, capture_output=True,
            env=dict(os.environ, SUDO_UID="0", SUDO_GID="0"),
        )

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_enabled_path_and_units_are_delivered(self):
        self.verify()

    def test_absolute_interpreter_link_is_resolved_inside_image(self):
        (self.root / "usr/bin/python3.14").unlink()
        target = "opt/python-development-environment/libexec/archlinux-arm/bin/python3.14"
        self.put(target, b"fixture", 0o755)
        self.link("usr/bin/python3.14", "/" + target)
        self.verify()

    def test_dangling_interpreter_link_is_rejected(self):
        (self.root / "usr/bin/python3.14").unlink()
        with self.assertRaisesRegex(RuntimeError, "/usr/bin/python3: expected .* executable"):
            self.verify()

    def test_non_executable_interpreter_is_rejected(self):
        (self.root / "usr/bin/python3.14").chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "/usr/bin/python3: expected .* executable"):
            self.verify()

    def test_missing_enablement_is_rejected(self):
        (self.root / "etc/systemd/system/multi-user.target.wants/negroni-rtc-sync.path").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_stale_service_is_rejected(self):
        (self.root / "etc/systemd/system/negroni-rtc-sync.service").write_text("[Service]\n")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.verify()

    def test_missing_restore_enablement_is_rejected(self):
        (self.root / "etc/systemd/system/sysinit.target.wants/negroni-rtc-restore.service").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
