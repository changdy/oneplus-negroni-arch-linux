"""Fixtures for real debugfs checks on small offline ext4 images, without phone access."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))


def load_verifier(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT / f"scripts/verify-{name}-image.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImageTest(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("offline root ownership checks require root or a user namespace")
        self.temp = tempfile.TemporaryDirectory(prefix="negroni-delivery-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.logs = self.base / "logs"
        self.logs.mkdir()
        self.put("etc/hostname", b"fixture\n")

    def put(self, name, data, mode=0o644):
        path = self.root / name.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def source(self, name, source, mode=0o644):
        return self.put(name, (PROJECT / source).read_bytes(), mode)

    def link(self, name, target):
        path = self.root / name.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)

    def image(self):
        path = self.base / "root.img"
        with path.open("wb") as output:
            output.truncate(96 * 1024 * 1024)
        subprocess.run(["mkfs.ext4", "-q", "-F", "-d", str(self.root), str(path)],
                       check=True, capture_output=True)

    @staticmethod
    def arm_elf(extra=b""):
        # Clearly synthetic fixture for file/ABI rejection tests, not executable code.
        data = bytearray(64)
        data[:5] = b"\x7fELF\x02"
        data[18:20] = b"\xb7\x00"
        return bytes(data) + extra
