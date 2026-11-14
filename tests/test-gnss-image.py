#!/usr/bin/env python3
import unittest
from image_delivery import ImageTest, load_verifier

verifier = load_verifier("gnss")


class GNSSImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        for target, source, mode in (
            ("opt/negroni-gnss/sbin/ModemManager", "config/gnss/runtime/ModemManager", 0o755),
            ("opt/negroni-gnss/lib/libqmi-glib.so.5.12.0", "config/gnss/runtime/libqmi-glib.so.5.12.0", 0o755),
            ("etc/systemd/system/ModemManager.service.d/20-negroni-gnss.conf", "config/gnss/20-negroni-gnss.conf", 0o644),
            ("etc/systemd/system/negroni-gnss-unlock.service", "config/gnss/negroni-gnss-unlock.service", 0o644),
            ("usr/local/libexec/negroni-gnss-assist.py", "scripts/gnss-assist.py", 0o755),
            ("usr/share/licenses/negroni-gnss/COPYING", "config/gnss/runtime/COPYING", 0o644),
            ("usr/share/licenses/negroni-gnss/COPYING.LIB", "config/gnss/runtime/COPYING.LIB", 0o644),
            ("usr/share/licenses/negroni-gnss/sources.txt", "config/gnss/sources.txt", 0o644),
        ):
            self.source(target, source, mode)
        self.link("opt/negroni-gnss/lib/libqmi-glib.so.5", "libqmi-glib.so.5.12.0")
        self.link("etc/systemd/system/ModemManager.service.wants/negroni-gnss-unlock.service",
                  "/etc/systemd/system/negroni-gnss-unlock.service")
        self.put("usr/bin/qmicli", b"fixture", 0o755)
        self.put("usr/bin/qrtr-lookup", b"fixture", 0o755)

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_deployed_payload_and_service(self):
        self.verify()

    def test_library_replaced_by_package_version_is_rejected(self):
        self.put("opt/negroni-gnss/lib/libqmi-glib.so.5.12.0", b"other library", 0o755)
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.verify()

    def test_disabled_unlock_service_is_rejected(self):
        (self.root / "etc/systemd/system/ModemManager.service.wants/negroni-gnss-unlock.service").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
