#!/usr/bin/env python3
import os
import unittest
from image_delivery import ImageTest, load_verifier

verifier = load_verifier("kernel-modules")


class KernelModuleImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        kernel = self.base / "kernel"
        source = kernel / "output/out-modules/lib/modules/7.3-fixture"
        source.mkdir(parents=True)
        (kernel / "output/include/config").mkdir(parents=True)
        (kernel / "output/include/config/kernel.release").write_text("7.3-fixture\n")
        (self.logs / "kernel-release.txt").write_text("7.3-fixture\n")
        for name, data in {"modules.dep": b"kernel/smem_sensor.ko:\n", "modules.softdep": b"",
                           "kernel/smem_sensor.ko": b"installed kernel module fixture",
                           "kernel/drivers/input/misc/mxm1120-slider.ko": b"slider fixture"}.items():
            p = source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            self.put("usr/lib/modules/7.3-fixture/" + name, data)
        old = os.environ.get("KERNEL_DIR")
        os.environ["KERNEL_DIR"] = str(kernel)
        self.addCleanup(lambda: os.environ.pop("KERNEL_DIR", None) if old is None else os.environ.__setitem__("KERNEL_DIR", old))

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_all_modules_and_empty_metadata(self):
        self.verify()

    def test_missing_sensor_module_is_rejected(self):
        (self.root / "usr/lib/modules/7.3-fixture/kernel/smem_sensor.ko").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_stale_module_with_same_release_is_rejected(self):
        self.put("usr/lib/modules/7.3-fixture/kernel/smem_sensor.ko", b"old module")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.verify()

    def test_missing_slider_in_build_is_rejected(self):
        module = "kernel/drivers/input/misc/mxm1120-slider.ko"
        (self.base / "kernel/output/out-modules/lib/modules/7.3-fixture" / module).unlink()
        (self.root / "usr/lib/modules/7.3-fixture" / module).unlink()
        with self.assertRaisesRegex(RuntimeError, "MXM1120"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
