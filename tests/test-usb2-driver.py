#!/usr/bin/env python3
"""Compile actual USB2 recovery functions against host mocks."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def function(source, name):
    start = source.index("static ", source.index(name) - 40)
    brace = source.index("{", source.index(name, start))
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--kernel", type=Path, default=Path(__file__).resolve().parents[1] / "linux")
args = parser.parse_args()
phy = (args.kernel / "drivers/phy/qualcomm/phy-qcom-snps-femto-v2.c").read_text()
glue = (args.kernel / "drivers/usb/dwc3/dwc3-qcom.c").read_text()

header = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
#define __iomem
#define USB2_PHY_USB_PHY_CFG0 0x94
#define UTMI_PHY_DATAPATH_CTRL_OVERRIDE_EN 1
struct qcom_snps_hsphy { void *base; void *dev; };
static int mmio_writes;
static u32 readl_relaxed(void *p) { return *(u32 *)p; }
static void writel_relaxed(u32 v, void *p) { *(u32 *)p = v; mmio_writes++; }
#define dev_info(...) do {} while (0)
#define dev_err(...) do {} while (0)
#define dev_dbg(...) do {} while (0)
enum usb_role { USB_ROLE_NONE, USB_ROLE_HOST, USB_ROLE_DEVICE };
#define DWC3_GCTL_PRTCAP_HOST 1
#define DWC3_GCTL_PRTCAP_DEVICE 2
#define PHY_MODE_USB_DEVICE 1
struct mutex { int held; };
struct dwc3 { struct mutex mutex; int current_dr_role; void *usb2_generic_phy[1]; };
struct dwc3_qcom { struct dwc3 dwc; void *dev; enum usb_role current_role; };
#define to_dwc3_qcom(d) ((struct dwc3_qcom *)(d))
static int gets, puts_count, modes, vbus_writes, pm_error, phy_error;
static bool vbus;
static int pm_runtime_resume_and_get(void *p) { (void)p; gets++; return pm_error; }
static void pm_runtime_mark_last_busy(void *p) { (void)p; }
static void pm_runtime_put_sync(void *p) { (void)p; puts_count++; }
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = 0; }
static int phy_set_mode(void *p, int mode) {
    assert(p && mode == PHY_MODE_USB_DEVICE); modes++; return phy_error;
}
static void dwc3_qcom_vbus_override_enable(struct dwc3_qcom *q, bool on) {
    (void)q; vbus = on; vbus_writes++;
}
"""

cases = r"""
int main(void) {
    u32 regs[64] = {0};
    struct qcom_snps_hsphy phy = { .base = regs };
    regs[USB2_PHY_USB_PHY_CFG0 / 4] = 0xa5a5a5a5;
    qcom_snps_hsphy_release_datapath(&phy);
    assert(regs[USB2_PHY_USB_PHY_CFG0 / 4] == 0xa5a5a5a4 && mmio_writes == 1);
    qcom_snps_hsphy_release_datapath(&phy);
    assert(mmio_writes == 1);

    struct dwc3_qcom q = { .current_role = USB_ROLE_DEVICE };
    q.dwc.current_dr_role = DWC3_GCTL_PRTCAP_DEVICE;
    q.dwc.usb2_generic_phy[0] = &phy;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_DEVICE);
    assert(modes == 1 && gets == 1 && puts_count == 1 && vbus);
    assert(!q.dwc.mutex.held);

    /* PHY errors must still release both the DWC3 mutex and the PM reference. */
    phy_error = -5;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_DEVICE);
    assert(modes == 2 && gets == 2 && puts_count == 2 && !q.dwc.mutex.held);
    phy_error = 0;

    /* A failed resume cannot touch the PHY or QSCRATCH. */
    pm_error = -5;
    int writes = vbus_writes;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_DEVICE);
    assert(modes == 2 && gets == 3 && puts_count == 2 && vbus_writes == writes);
    pm_error = 0;

    /* Repeated HOST and NONE requests retain the original early exit. */
    q.current_role = USB_ROLE_HOST;
    q.dwc.current_dr_role = DWC3_GCTL_PRTCAP_HOST;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_HOST);
    q.current_role = USB_ROLE_NONE;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_NONE);
    assert(gets == 3 && modes == 2);

    /* A real HOST -> DEVICE transition leaves PHY setup to the role worker. */
    q.current_role = USB_ROLE_HOST;
    dwc3_qcom_set_role_notifier(&q.dwc, USB_ROLE_DEVICE);
    assert(modes == 2 && gets == 4 && puts_count == 3 && vbus);
    assert(q.current_role == USB_ROLE_DEVICE && !q.dwc.mutex.held);
    puts("USB2 driver: datapath mask, repeated DEVICE, PM errors and HOST paths passed");
    return 0;
}
"""

source = "\n".join((header, function(phy, "qcom_snps_hsphy_write_mask"),
                    function(phy, "qcom_snps_hsphy_release_datapath"),
                    function(glue, "dwc3_qcom_set_role_notifier"), cases))
with tempfile.TemporaryDirectory(prefix="negroni-usb2-driver-") as directory:
    path = Path(directory)
    (path / "test.c").write_text(source)
    subprocess.run([os.environ.get("HOSTCC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
