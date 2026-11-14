#!/usr/bin/env python3
import os
import subprocess
import unittest
from image_delivery import ImageTest, PROJECT, load_verifier

verifier = load_verifier("nfc")


class NFCImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        subprocess.run(["bash", str(PROJECT / "scripts/configure-nfc.sh"), str(self.root), str(self.logs)],
                       check=True, capture_output=True, env=dict(os.environ, SUDO_UID="0", SUDO_GID="0"))
        (self.logs / "kernel-release.txt").write_text("7.3-fixture\n")
        entries = []
        for name in ("nxp-nci.ko", "nxp-nci_i2c.ko", "nci.ko", "nfc.ko"):
            self.put("usr/lib/modules/7.3-fixture/kernel/" + name, b"module fixture")
            entries.append("kernel/" + name + ":")
        self.put("usr/lib/modules/7.3-fixture/modules.dep", ("\n".join(entries) + "\n").encode())

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_real_cross_built_tools(self):
        self.verify()

    def test_missing_reader_is_rejected(self):
        (self.root / "usr/local/sbin/nfc-live").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_wrong_tool_permissions_are_rejected(self):
        (self.root / "usr/local/sbin/nfc-emulate").chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "mode"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
