#!/usr/bin/env python3
"""Keep the protected PMIC RTC counter and SDAM out of the write path."""
import json
from pathlib import Path
import subprocess
import sys


RTC = "/soc@0/spmi@c400000/pmic@0/rtc@6100"
SDAM = "/soc@0/spmi@c400000/pmic@0/nvram@7000"


def property_value(dtb, node, prop, kind="s"):
    return subprocess.check_output(
        ["fdtget", "-t", kind, str(dtb), node, prop], text=True
    ).strip()


def absent(dtb, node, prop):
    result = subprocess.run(
        ["fdtget", str(dtb), node, prop], capture_output=True
    )
    if result.returncode == 0:
        raise RuntimeError(f"{node}/{prop} must not be set")


def verify(dtb, log_dir):
    if property_value(dtb, RTC, "compatible") != "qcom,pmk8350-rtc":
        raise RuntimeError("wrong RTC controller")
    if property_value(dtb, RTC, "status") != "okay":
        raise RuntimeError("RTC is disabled")
    if property_value(dtb, SDAM, "compatible") != "qcom,spmi-sdam":
        raise RuntimeError("wrong PMIC SDAM provider")
    absent(dtb, RTC, "nvmem-cells")
    absent(dtb, RTC, "nvmem-cell-names")
    absent(dtb, RTC, "allow-set-time")
    absent(dtb, RTC, "qcom,uefi-rtc-info")
    result = subprocess.run(["fdtget", str(dtb), f"{SDAM}/rtc-offset@7c", "reg"],
                            capture_output=True)
    if result.returncode == 0:
        raise RuntimeError("protected SDAM RTC offset cell must be absent")

    output_dir = next((parent for parent in dtb.resolve().parents
                       if parent.name == "output"), None)
    if output_dir is None:
        raise RuntimeError("DTB is not under a kernel output directory")
    config = (output_dir / ".config").read_text()
    for setting in ("CONFIG_RTC_HCTOSYS=y", "CONFIG_RTC_DRV_PM8XXX=m"):
        if setting not in config.splitlines():
            raise RuntimeError(f"missing kernel setting: {setting}")
    report = {"dtb": str(dtb), "pmic_counter_writable_by_linux": False,
              "protected_sdam_offset_absent": True,
              "userspace_offset_storage": "/var/lib/negroni-rtc/state.json",
              "hardware_tested": False}
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "rtc-dtb-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("RTC DTB verified: PMIC counter readable, protected SDAM write path absent")
    return report


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify-rtc-dtb.py DTB LOG_DIRECTORY")
    verify(*map(Path, sys.argv[1:]))
