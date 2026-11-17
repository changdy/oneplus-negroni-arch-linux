#!/usr/bin/env python3
"""Compile ath11k's real intersection decision against the board compatible."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
KERNEL = Path(os.environ.get("KERNEL_DIR", PROJECT / "linux"))


def function(source, name):
    match = re.search(r"static bool\s+" + name + r"\(", source)
    if not match:
        raise RuntimeError(f"Missing driver function: {name}")
    end = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    source = (KERNEL / "drivers/net/wireless/ath/ath11k/reg.c").read_text()
    dts = (KERNEL / "arch/arm64/boot/dts/qcom/sm8450-oneplus-negroni.dts").read_text()
    compatible = re.search(r'^\s*compatible = "([^"]+)"', dts, re.M)[1]
    if not re.search(r"intersect = ath11k_reg_should_intersect\(ab,\s*"
                     r"ab->default_regd\[pdev_idx\],\s*reg_info->alpha2\)", source):
        raise RuntimeError("Firmware event does not use the tested decision")
    fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
enum { ATH11K_HW_WCN6855_HW20, ATH11K_HW_WCN6855_HW21, OTHER_HW };
struct ath11k_base { int hw_rev; };
struct ieee80211_regdomain { char alpha2[3]; };
static const char *machine;
static bool of_machine_is_compatible(const char *compatible)
{
    return !strcmp(machine, compatible);
}
'''
    fixture += function(source, "ath11k_reg_is_world_alpha") + "\n"
    fixture += function(source, "ath11k_reg_should_intersect") + "\n"
    fixture += r'''
int main(void)
{
    struct ath11k_base ab;
    struct ieee80211_regdomain initial[] = { {"US"}, {"CN"}, {"00"}, {"na"} };
    const char *countries[] = { "CN", "US", "00", "na" };
    const char *machines[] = { BOARD_COMPATIBLE, "qcom,sm8450-hdk" };
    unsigned checks = 0;

    for (unsigned m = 0; m < 2; m++) {
        machine = machines[m];
        for (ab.hw_rev = 0; ab.hw_rev <= OTHER_HW; ab.hw_rev++) {
            assert(!ath11k_reg_should_intersect(&ab, NULL, "CN"));
            checks++;
            for (unsigned i = 0; i < 4; i++) {
                for (unsigned c = 0; c < 4; c++) {
                    bool expected = i < 2 && c < 2;
                    if (m == 0 && ab.hw_rev != OTHER_HW)
                        expected = false;
                    assert(ath11k_reg_should_intersect(&ab, &initial[i],
                                                       countries[c]) == expected);
                    checks++;
                }
            }
        }
    }
    printf("ath11k regulatory: %u board/chip/country checks passed\n", checks);
}
'''
    fixture = fixture.replace("BOARD_COMPATIBLE", '"' + compatible + '"')
    with tempfile.TemporaryDirectory(prefix="negroni-wifi-regulatory-") as temp:
        path = Path(temp)
        (path / "test.c").write_text(fixture)
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror", str(path / "test.c"), "-o", str(path / "test")],
                       check=True)
        subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    main()
