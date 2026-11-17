#!/usr/bin/env python3
import os
import subprocess
import unittest
from image_delivery import ImageTest, PROJECT, load_verifier

verifier = load_verifier("sensors")


class SensorImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        for path in ("usr/local/bin/hexagonrpcd", "usr/local/lib/libhexagonrpc.so.0.5",
                     "usr/lib/libssc.so.2", "usr/bin/ssccli", "usr/lib/iio-sensor-proxy"):
            self.put(path, b"dependency fixture", 0o755)
        subprocess.run(["bash", str(PROJECT / "scripts/configure-sensors.sh"), str(self.root), str(self.logs)],
                       check=True, capture_output=True, env=dict(os.environ, SUDO_UID="0", SUDO_GID="0"))

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_installed_sensor_stack(self):
        self.verify()

    def test_disabled_light_proximity_service_is_rejected(self):
        (self.root / "etc/systemd/system/multi-user.target.wants/negroni-smem-sensor.service").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_distribution_proxy_regression_is_rejected(self):
        self.put("usr/lib/iio-sensor-proxy", b"unpatched proxy", 0o755)
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.verify()

    def test_missing_proxy_boot_order_is_rejected(self):
        (self.root / "etc/systemd/system/iio-sensor-proxy.service.d/negroni.conf").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_gyroscope_is_off_by_default(self):
        link = self.root / "etc/systemd/system/multi-user.target.wants/negroni-gyro.service"
        link.symlink_to("../negroni-gyro.service")
        with self.assertRaisesRegex(RuntimeError, "on-demand"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
