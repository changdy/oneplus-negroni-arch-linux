"""Record the source revision and kernel ABI of externally built camera modules."""
import hashlib
import json
from pathlib import Path
import sys

MODULES = ("imx615.ko", "negroni_extra_sensors.ko", "negroni_camera_overlay.ko")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(project):
    files = list((project / "artifacts/camera-20261114/drivers").glob("*.c"))
    files += list((project / "artifacts/camera-20261114/drivers").glob("*.h"))
    files += [project / "artifacts/camera-20261114/drivers/Makefile",
              project / "artifacts/camera-20261114/negroni-four-camera-test.dts"]
    return {str(p.relative_to(project)).replace("\\", "/"): digest(p) for p in sorted(files)}


if __name__ == "__main__":
    destination, kernel, project = map(Path, sys.argv[1:])
    manifest = {
        "sources": sources(project),
        "kernel_release": (kernel / "output/include/config/kernel.release").read_text().strip(),
        "module_symvers_sha256": digest(kernel / "output/Module.symvers"),
        "files": {name: digest(destination / name) for name in (*MODULES, "negroni-four-camera-test.dtbo")},
        "autoload": False,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
