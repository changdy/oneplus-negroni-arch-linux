// SPDX-License-Identifier: GPL-2.0
/* Diagnostic only: hold camera PHY clocks until this module is removed. */
#include <linux/clk.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
static struct platform_device *camera;
static struct clk *clocks[12];
static unsigned int enabled;
static void release_clocks(void)
{
    while (enabled) {
        struct clk *clock = clocks[--enabled];
        clk_disable_unprepare(clock);
        clk_put(clock);
    }
    if (camera) {
        pm_runtime_put_sync(&camera->dev);
        put_device(&camera->dev);
        camera = NULL;
    }
}
static int __init phy_hold_init(void)
{
    struct device_node *node = of_find_compatible_node(NULL, NULL, "qcom,sm8450-camss");
    int ret;
    unsigned int i;
    char name[24];
    if (!node)
        return -ENODEV;
    camera = of_find_device_by_node(node);
    of_node_put(node);
    if (!camera)
        return -ENODEV;
    ret = pm_runtime_resume_and_get(&camera->dev);
    if (ret < 0) {
        put_device(&camera->dev);
        camera = NULL;
        return ret;
    }
    for (i = 0; i < ARRAY_SIZE(clocks); i++) {
        snprintf(name, sizeof(name), i % 2 ? "csiphy%u_timer" : "csiphy%u", i / 2);
        clocks[i] = clk_get(&camera->dev, name);
        if (IS_ERR(clocks[i])) {
            ret = PTR_ERR(clocks[i]);
            goto error;
        }
        ret = clk_prepare_enable(clocks[i]);
        if (ret) {
            clk_put(clocks[i]);
            goto error;
        }
        enabled++;
    }
    pr_info("negroni-phy-hold: all six PHY clock pairs held for diagnosis\n");
    return 0;
error:
    release_clocks();
    return ret;
}
module_init(phy_hold_init);
module_exit(release_clocks);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Diagnostic SM8450 PHY clock hold");
