#!/usr/bin/env python3
import json
import os
from pathlib import Path
import tempfile
import unittest
from image_delivery import ImageTest, PROJECT, load_verifier
from camera_manifest import MODULES, digest, sources
from image_feature import sha256

verifier = load_verifier("camera")


class CameraImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        self.kernel = self.base / "kernel"
        (self.kernel / "output").mkdir(parents=True)
        (self.kernel / "output/Module.symvers").write_text("ABI fixture\n")
        self.old_kernel = os.environ.get("KERNEL_DIR")
        os.environ["KERNEL_DIR"] = str(self.kernel)
        self.addCleanup(self.restore_env)
        (self.logs / "kernel-release.txt").write_text("7.3-fixture\n")
        self.manifest = {"sources": sources(PROJECT), "kernel_release": "7.3-fixture",
                         "module_symvers_sha256": digest(self.kernel / "output/Module.symvers"), "files": {}}
        for name in (*MODULES, "negroni-four-camera-test.dtbo"):
            data = self.arm_elf(b"vermagic=7.3-fixture SMP\0") if name in MODULES else b"overlay fixture"
            self.put(f"usr/lib/negroni/camera/{name}", data)
            self.manifest["files"][name] = sha256(data)
        self.put("usr/lib/firmware/negroni/negroni-four-camera-test.dtbo", b"overlay fixture")
        for name in ("capture.sh", "eeprom.sh", "still.sh", "multi-capture.sh", "meter.py", "raw-preview.py", "idle.sh", "extra.sh"):
            name = "negroni-camera-" + name
            self.source(f"usr/local/bin/{name}", f"scripts/{name}", 0o755)
        self.source("etc/udev/rules.d/70-negroni-dma-heap.rules", "config/camera/70-negroni-dma-heap.rules")
        self.source("etc/wireplumber/wireplumber.conf.d/50-negroni-camera.conf", "config/camera/50-negroni-camera.conf")

    def restore_env(self):
        if self.old_kernel is None:
            os.environ.pop("KERNEL_DIR", None)
        else:
            os.environ["KERNEL_DIR"] = self.old_kernel

    def verify(self):
        self.put("usr/lib/negroni/camera/manifest.json", json.dumps(self.manifest).encode())
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_complete_payload(self):
        self.verify()

    def test_same_release_different_abi_is_rejected(self):
        (self.kernel / "output/Module.symvers").write_text("changed ABI\n")
        with self.assertRaisesRegex(RuntimeError, "kernel ABI"):
            self.verify()

    def test_stale_source_manifest_is_rejected(self):
        self.manifest["sources"] = {}
        with self.assertRaisesRegex(RuntimeError, "stale sources"):
            self.verify()

    def test_missing_user_configuration_is_rejected(self):
        (self.root / "etc/wireplumber/wireplumber.conf.d/50-negroni-camera.conf").unlink()
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
