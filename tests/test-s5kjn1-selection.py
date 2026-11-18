#!/usr/bin/env python3
"""Check the S5KJN1 selection callback against both hardware mode tables."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
KERNEL = Path(os.environ.get("KERNEL_DIR", PROJECT / "linux"))

HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <linux/v4l2-subdev.h>

struct v4l2_subdev;
struct v4l2_subdev_state;

CALLBACK

static void check(unsigned int which, unsigned int target,
                  const struct v4l2_rect *expected)
{
    struct v4l2_subdev_selection sel = {
        .which = which,
        .target = target,
        .r = { -1, -1, 0, 0 },
    };

    assert(s5kjn1_get_selection(NULL, NULL, &sel) == (expected ? 0 : -EINVAL));
    if (!expected)
        return;
    assert(sel.r.left == expected->left && sel.r.top == expected->top);
    assert(sel.r.width == expected->width && sel.r.height == expected->height);
}

int main(void)
{
    const struct v4l2_rect readable = { 0, 0, 8192, 6176 };
    const struct v4l2_rect active = { 16, 16, 8160, 6144 };
    const unsigned int selections[] = {
        V4L2_SUBDEV_FORMAT_ACTIVE, V4L2_SUBDEV_FORMAT_TRY,
    };

    for (size_t i = 0; i < sizeof(selections) / sizeof(selections[0]); i++) {
        unsigned int which = selections[i];

        check(which, V4L2_SEL_TGT_CROP, &readable);
        check(which, V4L2_SEL_TGT_CROP_BOUNDS, &readable);
        check(which, V4L2_SEL_TGT_NATIVE_SIZE, &readable);
        check(which, V4L2_SEL_TGT_CROP_DEFAULT, &active);
        check(which, V4L2_SEL_TGT_COMPOSE, NULL);
    }
    puts("S5KJN1 ACTIVE and TRY selection targets passed.");
}
"""


def main():
    source = (KERNEL / "drivers/media/i2c/s5kjn1.c").read_text(encoding="utf-8")
    macros = re.findall(r"^#define S5KJN1_(?:NATIVE_\w+|ACTIVE_BORDER)\s+\d+$",
                        source, re.MULTILINE)
    callback = re.search(r"^static int s5kjn1_get_selection\(.*?^}", source,
                         re.MULTILINE | re.DOTALL)
    if len(macros) != 3 or callback is None:
        raise SystemExit("Could not extract the S5KJN1 selection implementation")

    # Both modes read the same analogue rectangle. Digital offsets are in
    # output pixels, so the offsets for 2x2 binning need to be doubled.
    for mode, binning in (("4080x3072_30fps", 2), ("8160x6144_10fps", 1)):
        table_start = source.index(f"s5kjn1_{mode}_mode[] = {{")
        table = source[table_start:source.index("\n};", table_start)]
        for axis, last, output in (("X", 8191, 8160), ("Y", 6175, 6144)):
            offset_reg = "0350" if axis == "X" else "0352"
            expected = {
                f"S5KJN1_REG_{axis}_ADDR_START": 0,
                f"S5KJN1_REG_{axis}_ADDR_END": last,
                f"S5KJN1_REG_{axis}_OUTPUT_SIZE": output // binning,
                f"CCI_REG16(0x{offset_reg})": 16 // binning,
            }
            for reg, value in expected.items():
                entry = re.search(rf"\{{ {re.escape(reg)},\s+(0x[0-9a-f]+) \}}", table)
                if entry is None or int(entry[1], 16) != value:
                    raise SystemExit(f"{mode}: unexpected value for {reg}")

    with tempfile.TemporaryDirectory(prefix="negroni-jn1-") as tmp:
        test = Path(tmp) / "selection.c"
        binary = Path(tmp) / "selection"
        test.write_text(HARNESS.replace("CALLBACK", "\n".join([*macros, callback[0]])),
                        encoding="utf-8")
        subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        "-o", binary, test], check=True)
        subprocess.run([binary], check=True)


if __name__ == "__main__":
    main()
