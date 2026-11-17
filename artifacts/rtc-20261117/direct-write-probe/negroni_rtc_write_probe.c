// SPDX-License-Identifier: GPL-2.0-only
/* NE2210 experiment: probe write permission with an unchanged RTC control byte. */
#include <linux/device.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

#define RTC_DEVICE "c400000.spmi:pmic@0:rtc@6100"
#define PMK8350_RTC_CTRL 0x6146
#define EXPECTED_CTRL 0x80

static bool confirm_same_value_write;
module_param(confirm_same_value_write, bool, 0400);
MODULE_PARM_DESC(confirm_same_value_write,
	"Required to attempt one same-value write to PMK8350 RTC_CTRL");

static int __init negroni_rtc_write_probe_init(void)
{
	struct device *rtc_dev;
	struct regmap *regmap;
	unsigned int before, after;
	int ret;

	if (!confirm_same_value_write) {
		pr_info("confirmation absent; no PMIC write attempted\n");
		return -EPERM;
	}

	rtc_dev = bus_find_device_by_name(&platform_bus_type, NULL, RTC_DEVICE);
	if (!rtc_dev)
		return -ENODEV;
	if (!rtc_dev->of_node ||
	    !of_device_is_compatible(rtc_dev->of_node, "qcom,pmk8350-rtc")) {
		ret = -ENODEV;
		goto out_put;
	}

	regmap = dev_get_regmap(rtc_dev->parent, NULL);
	if (!regmap) {
		ret = -ENODEV;
		goto out_put;
	}

	ret = regmap_read(regmap, PMK8350_RTC_CTRL, &before);
	if (ret)
		goto out_put;
	if (before != EXPECTED_CTRL) {
		pr_err("RTC_CTRL changed from expected %#x to %#x; no write attempted\n",
		       EXPECTED_CTRL, before);
		ret = -EBUSY;
		goto out_put;
	}

	ret = regmap_write(regmap, PMK8350_RTC_CTRL, before);
	pr_info("same-value RTC_CTRL write returned %d\n", ret);
	if (ret)
		goto out_put;

	ret = regmap_read(regmap, PMK8350_RTC_CTRL, &after);
	if (!ret && after != before)
		ret = -EIO;
	pr_info("RTC_CTRL before=%#x after=%#x verify=%d\n",
		before, ret ? 0U : after, ret);

out_put:
	put_device(rtc_dev);
	return ret;
}

static void __exit negroni_rtc_write_probe_exit(void)
{
}

module_init(negroni_rtc_write_probe_init);
module_exit(negroni_rtc_write_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("One-shot same-value PMK8350 RTC write-permission probe");
