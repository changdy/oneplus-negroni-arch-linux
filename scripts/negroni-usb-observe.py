#!/usr/bin/env python3
"""Record USB role/gadget transitions without changing the device configuration."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def read_value(path):
    try:
        return path.read_text().strip()
    except OSError as exc:
        return f"<{exc.__class__.__name__}>"


def snapshot():
    values = {}
    for pattern in (
        "/sys/class/usb_role/*/role",
        "/sys/class/udc/*/state",
        "/sys/class/udc/*/current_speed",
        "/sys/class/typec/port*/data_role",
        "/sys/class/typec/port*/power_role",
        "/sys/class/typec/port*/orientation",
        "/sys/class/typec/port*/power_operation_mode",
        "/sys/kernel/config/usb_gadget/*/UDC",
        "/sys/class/net/usb*/operstate",
        "/sys/class/net/usb*/carrier",
    ):
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            values[str(path)] = read_value(path)
    values["typec_partners"] = sorted(
        str(path) for path in Path("/sys/class/typec").glob("port*-partner")
    )
    # These debugfs files expose the current controller state; never write them.
    for name in ("mode", "link_state"):
        path = Path("/sys/kernel/debug/usb/a600000.usb") / name
        values[str(path)] = read_value(path)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory for local raw logs")
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--interval", type=float, default=0.02)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600 or not 0.01 <= args.interval <= 10:
        parser.error("seconds must be in (0, 3600], interval in [0.01, 10]")
    args.output.mkdir(parents=True, exist_ok=False)
    processes = []
    streams = []
    start = time.monotonic()
    try:
        for name, command in (
            ("kernel.log", ["journalctl", "-k", "-f", "-n", "0", "-o", "short-monotonic", "--no-pager"]),
            ("uevents.log", ["udevadm", "monitor", "--kernel", "--property",
                             "--subsystem-match=usb", "--subsystem-match=typec",
                             "--subsystem-match=usb_role", "--subsystem-match=net"]),
        ):
            stream = (args.output / name).open("w")
            streams.append(stream)
            processes.append(subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT))
        with (args.output / "states.jsonl").open("w", buffering=1) as stream:
            stream.write(json.dumps({"metadata": {
                "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "monotonic": start, "kernel": os.uname().release,
                "interval": args.interval, "euid": os.geteuid(),
                "note": "Sequential samples, not atomic; transitions shorter than interval may be missed.",
            }}) + "\n")
            previous = None
            samples = 0
            while time.monotonic() - start < args.seconds:
                sample_start = time.monotonic()
                current = snapshot()
                samples += 1
                if current != previous:
                    stream.write(json.dumps({"monotonic": sample_start,
                                             "elapsed": sample_start - start,
                                             "read_seconds": time.monotonic() - sample_start,
                                             "state": current}, ensure_ascii=False) + "\n")
                    previous = current
                time.sleep(max(0, args.interval - (time.monotonic() - sample_start)))
            stream.write(json.dumps({"finished": True, "samples": samples,
                                     "monotonic": time.monotonic()}) + "\n")
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in streams:
            stream.close()


if __name__ == "__main__":
    main()
