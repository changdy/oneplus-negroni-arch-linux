"""Small offline ext4 checks shared by the device feature verifiers."""
import hashlib
import re
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Image:
    def __init__(self, image_dir):
        self.path = Path(image_dir) / "root.img"

    def query(self, command):
        result = subprocess.run(["debugfs", "-R", command, str(self.path)],
                                check=True, capture_output=True)
        errors = result.stderr.decode().splitlines()[1:]
        if errors:
            raise RuntimeError("\n".join(errors))
        return result.stdout

    def read(self, path):
        return self.query(f"cat {path}")

    def file(self, path, mode=None):
        meta = self.query(f"stat {path}").decode()
        if not re.search(r"Type:\s+regular\b", meta):
            raise RuntimeError(f"{path}: expected a regular file")
        if mode and (not re.search(rf"Mode:\s+0?{mode}\b", meta)
                     or not re.search(r"User:\s+0\s+Group:\s+0", meta)):
            raise RuntimeError(f"{path}: expected root:root mode {mode}")
        data = self.read(path)
        if not data:
            raise RuntimeError(f"{path}: empty file")
        return data

    def source(self, path, source, mode="0644"):
        data = self.file(path, mode)
        if data != (PROJECT / source).read_bytes():
            raise RuntimeError(f"image/source mismatch: {path}")
        return sha256(data)

    def link(self, path, target):
        meta = self.query(f"stat {path}").decode()
        if "Type: symlink" not in meta or f'Fast link dest: "{target}"' not in meta:
            raise RuntimeError(f"{path}: expected symlink to {target}")

    def enabled(self, unit, target="multi-user.target"):
        path = f"/etc/systemd/system/{target}.wants/{unit}"
        meta = self.query(f"stat {path}").decode()
        if "Type: symlink" not in meta or not any(
                f'Fast link dest: "{dest}"' in meta
                for dest in (f"/etc/systemd/system/{unit}", f"../{unit}")):
            raise RuntimeError(f"{unit}: missing or incorrect enablement link")

    def packages(self, names):
        entries = self.query("ls -p /var/lib/pacman/local").decode().splitlines()
        directories = [line.split("/")[5] for line in entries if line.startswith("/")
                       and int(line.split("/")[2], 8) & 0o170000 == 0o040000]
        versions = {}
        for name in names:
            for directory in directories:
                if not directory.startswith(name + "-"):
                    continue
                desc = self.read(f"/var/lib/pacman/local/{directory}/desc").decode()
                if f"%NAME%\n{name}\n" in desc:
                    versions[name] = desc.split("%VERSION%\n", 1)[1].splitlines()[0]
                    break
            if name not in versions:
                raise RuntimeError(f"missing required package: {name}")
        return versions


def elf_aarch64(data, path):
    if data[:5] != b"\x7fELF\x02" or data[18:20] != b"\xb7\x00":
        raise RuntimeError(f"{path}: expected an aarch64 ELF64 binary")
