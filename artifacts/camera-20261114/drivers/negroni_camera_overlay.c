// SPDX-License-Identifier: GPL-2.0
/* Temporary RAM-only camera overlay. Unload camera consumers before removing. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>

static char *firmware = "negroni-imx615-test.dtbo";
module_param(firmware, charp, 0444);
static int overlay_id;
static struct platform_device *regulators[4];
static unsigned int nregulators;
static struct platform_device *cci;

static int __init camera_overlay_init(void)
{
    const struct firmware *fw;
    struct device_node *node, *parent;
    struct platform_device *parent_dev;
    int ret;

    ret = request_firmware(&fw, firmware, NULL);
    if (ret)
        return ret;
    ret = of_overlay_fdt_apply(fw->data, fw->size, &overlay_id, NULL);
    release_firmware(fw);
    if (ret)
        return ret;
    for_each_node_with_property(node, "negroni,temporary-camera") {
      if (!of_node_check_flag(node, OF_POPULATED)) {
        parent = of_get_parent(node);
        parent_dev = of_find_device_by_node(parent);
        of_node_put(parent);
        if (!parent_dev) {
            of_node_put(node);
            ret = -ENODEV;
            goto unregister;
        }
        if (nregulators == ARRAY_SIZE(regulators)) {
            put_device(&parent_dev->dev);
            of_node_put(node);
            ret = -E2BIG;
            goto unregister;
        }
        regulators[nregulators] = of_platform_device_create(node, NULL, &parent_dev->dev);
        put_device(&parent_dev->dev);
        if (!regulators[nregulators]) {
            of_node_put(node);
            ret = -ENODEV;
            goto unregister;
        }
        nregulators++;
      }
    }
    node = of_find_node_by_path("/soc@0/cci@ac16000");
    if (!node) {
        ret = -ENODEV;
        goto unregister;
    }
    if (!of_node_check_flag(node, OF_POPULATED)) {
        cci = of_platform_device_create(node, NULL, NULL);
        if (!cci) {
            of_node_put(node);
            ret = -ENODEV;
            goto unregister;
        }
    }
    of_node_put(node);
    pr_info("negroni-camera: RAM overlay %d applied (%s)\n", overlay_id, firmware);
    return 0;
unregister:
    while (nregulators)
        platform_device_unregister(regulators[--nregulators]);
    of_overlay_remove(&overlay_id);
    return ret;
}

static void __exit camera_overlay_exit(void)
{
    int ret;
    if (cci)
        platform_device_unregister(cci);
    while (nregulators)
        platform_device_unregister(regulators[--nregulators]);
    ret = of_overlay_remove(&overlay_id);
    if (ret)
        pr_err("negroni-camera: overlay removal failed: %d\n", ret);
}
module_init(camera_overlay_init);
module_exit(camera_overlay_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary Negroni camera device-tree overlay for bring-up");
