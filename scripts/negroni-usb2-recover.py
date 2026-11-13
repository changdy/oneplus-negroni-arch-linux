#!/usr/bin/env python3
"""Inspect Negroni USB2; --apply releases a stuck charger-detection override.

Experimental runtime workaround, not installed or enabled by the image build.
Run on the phone as root. It changes only PHY_CFG0.DATAPATH_OVERRIDE (bit 0),
without changing clocks, USB roles, UDC binding, services, or partitions.
"""

import argparse
import json
import mmap
import os
from pathlib import Path
import struct
import time


PHY_CFG0 = 0x088E3094
DATAPATH_OVERRIDE = 1


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def status():
    return {
        "role": read("/sys/class/usb_role/a600000.usb-role-switch/role"),
        "mode": read("/sys/kernel/debug/usb/a600000.usb/mode"),
        "data_role": read("/sys/class/typec/port0/data_role"),
        "partner": Path("/sys/class/typec/port0/port0-partner").exists(),
        "udc": read("/sys/kernel/config/usb_gadget/negroni/UDC"),
        "state": read("/sys/class/udc/a600000.usb/state"),
        "speed": read("/sys/class/udc/a600000.usb/current_speed"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="clear only PHY_CFG0 bit 0")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run as root on the phone")
    compatible = Path("/sys/firmware/devicetree/base/compatible").read_bytes().split(b"\0")
    if b"oplus,negroni" not in compatible:
        parser.error("this workaround supports only oplus,negroni")
    before = status()
    print(json.dumps({"before": before}), flush=True)
    if not args.apply:
        return
    if before["state"] == "configured":
        print("Already configured; no register changed.")
        return
    if not (before["role"] == before["mode"] == "device"
            and "[device]" in (before["data_role"] or "") and before["partner"]
            and before["udc"] == "a600000.usb" and before["state"] == "not attached"):
        parser.error("requires an attached Type-C device partner and a bound, unconfigured gadget")

    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    try:
        base = PHY_CFG0 // mmap.PAGESIZE * mmap.PAGESIZE
        with mmap.mmap(fd, mmap.PAGESIZE, flags=mmap.MAP_SHARED,
                       prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=base) as mem:
            offset = PHY_CFG0 - base
            value = struct.unpack_from("<I", mem, offset)[0]
            # Recheck roles immediately before the write; userspace cannot make
            # this atomic with the kernel, so keep the physical cable unchanged.
            if status() != before:
                parser.error("USB state changed during inspection; retry after it settles")
            if not value & DATAPATH_OVERRIDE:
                parser.error("datapath override is already clear; this failure has another cause")
            struct.pack_into("<I", mem, offset, value & ~DATAPATH_OVERRIDE)
            after = struct.unpack_from("<I", mem, offset)[0]
            print(json.dumps({"address": hex(PHY_CFG0), "before_register": hex(value),
                              "after_register": hex(after)}), flush=True)
    finally:
        os.close(fd)

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = status()
        if current["state"] == "configured":
            print(json.dumps({"after": current}), flush=True)
            return
        time.sleep(0.1)
    print(json.dumps({"after": status()}), flush=True)
    raise SystemExit("No configured gadget within 15 seconds; no further registers changed.")


if __name__ == "__main__":
    main()
