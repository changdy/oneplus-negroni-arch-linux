"""The gyroscope uses the accelerometer's confirmed panel orientation."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "config/sensors/negroni-gyro.c").read_text(encoding="utf-8")
RULES = (ROOT / "config/sensors/81-negroni-ssc.rules").read_text(encoding="utf-8")
SERVICE = (ROOT / "config/systemd/negroni-gyro.service").read_text(encoding="utf-8")
INSTALL = (ROOT / "scripts/configure-sensors.sh").read_text(encoding="utf-8")
BUILD = (ROOT / "build.sh").read_text(encoding="utf-8")
PACK = (ROOT / "scripts/pack-images.sh").read_text(encoding="utf-8")


def matrix_from_source():
    match = re.search(
        r"panel_from_chip\[3\]\[3\] = \{\s*"
        r"\{([^}]+)\},\s*\{([^}]+)\},\s*\{([^}]+)\},",
        SOURCE,
    )
    if not match:
        raise SystemExit("panel_from_chip is missing")
    rows = []
    for group in match.groups():
        rows.append([float(item.replace("f", "")) for item in group.split(",")])
    return rows


def apply_matrix(rows, vector):
    return [
        sum(rows[row][col] * vector[col] for col in range(3))
        for row in range(3)
    ]


def main():
    rows = matrix_from_source()
    if rows != [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]:
        raise SystemExit(f"unexpected gyroscope matrix: {rows}")
    if 'ACCEL_MOUNT_MATRIX}="-1, 0, 0; 0, -1, 0; 0, 0, 1"' not in RULES:
        raise SystemExit("accelerometer mount matrix changed; review the gyroscope")
    sample = apply_matrix(rows, [0.009, -0.002, 0.012])
    if sample != [-0.009, 0.002, 0.012]:
        raise SystemExit(f"mount transform failed: {sample}")
    if "ExecStart=/usr/local/sbin/negroni-gyro" not in SERVICE:
        raise SystemExit("gyroscope service does not start negroni-gyro")
    if "org.negroni.Gyroscope" not in SERVICE:
        raise SystemExit("gyroscope service does not own its bus name")
    for name in ("negroni-gyro", "negroni-gyro.service", "org.negroni.Gyroscope.conf"):
        if name not in INSTALL:
            raise SystemExit(f"configure-sensors.sh does not install {name}")
    if "update-sensors-image.sh" not in BUILD or "sensors-sources.sha256" not in BUILD:
        raise SystemExit("build.sh does not refresh an existing image when the gyroscope changes")
    if "verify-sensors-image.py" not in PACK:
        raise SystemExit("pack-images.sh does not check the gyroscope")
    print("gyroscope axes match the accelerometer mount matrix")


if __name__ == "__main__":
    main()
