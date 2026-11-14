// SPDX-License-Identifier: GPL-2.0
/* Experimental Negroni fixed RAW modes: OV08A10 D-PHY and IMX789 C-PHY. */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/pm_runtime.h>
#include <linux/regulator/consumer.h>
#include <media/v4l2-cci.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-fwnode.h>
#include <media/v4l2-subdev.h>

#include "ov08a10-ftm.h"
#include "imx789-ftm.h"

static bool test_pattern;
module_param(test_pattern, bool, 0644);
MODULE_PARM_DESC(test_pattern, "Enable IMX789 colour bars (OV08A10 pattern unverified)");

struct sensor_profile {
    const char *name;
    u32 id_reg;
    u16 id;
    unsigned int nsupplies;
    const char *supplies[5];
    bool cphy;
    u32 width, height, code;
    s64 link_frequency;
    const struct cci_reg_sequence *registers;
    unsigned int nregisters;
};

struct test_sensor {
    struct v4l2_subdev sd;
    struct media_pad pad;
    struct v4l2_ctrl_handler controls;
    struct clk *clock;
    struct gpio_desc *reset;
    struct regmap *regmap;
    struct device *dev;
    struct regulator_bulk_data supplies[5];
    const struct sensor_profile *profile;
    bool registered;
};

static struct test_sensor *to_sensor(struct v4l2_subdev *sd)
{
    return container_of(sd, struct test_sensor, sd);
}

static int sensor_power_off(struct device *dev)
{
    struct test_sensor *s = to_sensor(dev_get_drvdata(dev));
    unsigned int i = s->profile->nsupplies;

    gpiod_set_value_cansleep(s->reset, 1);
    usleep_range(1000, 1500);
    clk_disable_unprepare(s->clock);
    while (i)
        regulator_disable(s->supplies[--i].consumer);
    return 0;
}

static int sensor_power_on(struct device *dev)
{
    struct test_sensor *s = to_sensor(dev_get_drvdata(dev));
    unsigned int i;
    int ret;

    for (i = 0; i < s->profile->nsupplies; i++) {
        ret = regulator_enable(s->supplies[i].consumer);
        if (ret)
            goto disable;
    }
    /* The local IMX789 sequence releases reset before MCLK. */
    if (s->profile->cphy) {
        gpiod_set_value_cansleep(s->reset, 0);
        usleep_range(1000, 1500);
    }
    ret = clk_prepare_enable(s->clock);
    if (ret) {
        gpiod_set_value_cansleep(s->reset, 1);
        goto disable;
    }
    usleep_range(1000, 1500);
    gpiod_set_value_cansleep(s->reset, 0);
    usleep_range(10000, 12000);
    return 0;
disable:
    while (i)
        regulator_disable(s->supplies[--i].consumer);
    return ret;
}

static void sensor_format(struct test_sensor *s, struct v4l2_mbus_framefmt *fmt)
{
    *fmt = (struct v4l2_mbus_framefmt) {
        .width = s->profile->width,
        .height = s->profile->height,
        .code = s->profile->code,
        .field = V4L2_FIELD_NONE,
        .colorspace = V4L2_COLORSPACE_RAW,
        .quantization = V4L2_QUANTIZATION_FULL_RANGE,
    };
}

static int sensor_init_state(struct v4l2_subdev *sd, struct v4l2_subdev_state *state)
{
    sensor_format(to_sensor(sd), v4l2_subdev_state_get_format(state, 0));
    return 0;
}

static int sensor_set_format(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
                             struct v4l2_subdev_format *fmt)
{
    if (fmt->pad)
        return -EINVAL;
    if (fmt->which == V4L2_SUBDEV_FORMAT_ACTIVE &&
        media_entity_is_streaming(&sd->entity))
        return -EBUSY;
    sensor_format(to_sensor(sd), &fmt->format);
    *v4l2_subdev_state_get_format(state, 0) = fmt->format;
    return 0;
}

static int sensor_enum_code(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
                            struct v4l2_subdev_mbus_code_enum *code)
{
    if (code->pad || code->index)
        return -EINVAL;
    code->code = to_sensor(sd)->profile->code;
    return 0;
}

static int sensor_enum_size(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
                            struct v4l2_subdev_frame_size_enum *size)
{
    if (size->pad || size->index || size->code != to_sensor(sd)->profile->code)
        return -EINVAL;
    size->min_width = size->max_width = to_sensor(sd)->profile->width;
    size->min_height = size->max_height = to_sensor(sd)->profile->height;
    return 0;
}

static int sensor_enable_streams(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
                                  u32 pad, u64 mask)
{
    struct test_sensor *s = to_sensor(sd);
    unsigned int i;
    int ret;

    ret = pm_runtime_resume_and_get(s->dev);
    if (ret < 0)
        return ret;
    for (i = 0; i < s->profile->nregisters; i++) {
        u32 reg = s->profile->registers[i].reg;
        /* Streaming starts only after all mode writes have succeeded. */
        if (reg == CCI_REG8(0x0100))
            continue;
        ret = cci_write(s->regmap, reg, s->profile->registers[i].val, NULL);
        if (ret)
            goto error;
        if (reg == CCI_REG8(0x0103))
            usleep_range(5000, 6000);
    }
    if (s->profile->cphy) {
        ret = cci_write(s->regmap, CCI_REG16(0x0600), test_pattern ? 2 : 0, NULL);
    } else {
        ret = cci_write(s->regmap, CCI_REG8(0x5e00), test_pattern ? 0x80 : 0, NULL);
        if (!ret)
            ret = cci_write(s->regmap, CCI_REG8(0x4320), 0x80, NULL);
    }
    if (ret)
        goto error;
    ret = cci_write(s->regmap, CCI_REG8(0x0100), 1, NULL);
    if (!ret)
        return 0;
error:
    cci_write(s->regmap, CCI_REG8(0x0100), 0, NULL);
    pm_runtime_put_sync(s->dev);
    return ret;
}

static int sensor_disable_streams(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
                                   u32 pad, u64 mask)
{
    struct test_sensor *s = to_sensor(sd);
    int ret = cci_write(s->regmap, CCI_REG8(0x0100), 0, NULL);

    usleep_range(35000, 40000);
    pm_runtime_put_sync(s->dev);
    return ret;
}

static const struct v4l2_subdev_video_ops sensor_video_ops = {
    .s_stream = v4l2_subdev_s_stream_helper,
};
static const struct v4l2_subdev_pad_ops sensor_pad_ops = {
    .enum_mbus_code = sensor_enum_code,
    .enum_frame_size = sensor_enum_size,
    .get_fmt = v4l2_subdev_get_fmt,
    .set_fmt = sensor_set_format,
    .enable_streams = sensor_enable_streams,
    .disable_streams = sensor_disable_streams,
};
static const struct v4l2_subdev_ops sensor_ops = {
    .video = &sensor_video_ops,
    .pad = &sensor_pad_ops,
};
static const struct v4l2_subdev_internal_ops sensor_internal_ops = {
    .init_state = sensor_init_state,
};

static int sensor_probe(struct i2c_client *client)
{
    struct device *dev = &client->dev;
    struct test_sensor *s;
    struct v4l2_ctrl *ctrl;
    u64 id;
    int ret;
    unsigned int i;

    s = devm_kzalloc(dev, sizeof(*s), GFP_KERNEL);
    if (!s)
        return -ENOMEM;
    s->dev = dev;
    s->profile = i2c_get_match_data(client);
    for (i = 0; i < s->profile->nsupplies; i++)
        s->supplies[i].supply = s->profile->supplies[i];
    ret = devm_regulator_bulk_get(dev, s->profile->nsupplies, s->supplies);
    if (ret)
        return dev_err_probe(dev, ret, "supplies unavailable\n");
    s->clock = devm_v4l2_sensor_clk_get(dev, NULL);
    if (IS_ERR(s->clock))
        return PTR_ERR(s->clock);
    if (clk_get_rate(s->clock) != 19200000)
        return -EINVAL;
    s->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
    if (IS_ERR(s->reset))
        return PTR_ERR(s->reset);
    s->regmap = devm_cci_regmap_init_i2c(client, 16);
    if (IS_ERR(s->regmap))
        return PTR_ERR(s->regmap);
    v4l2_i2c_subdev_init(&s->sd, client, &sensor_ops);
    strscpy(s->sd.name, s->profile->name, sizeof(s->sd.name));
    ret = sensor_power_on(dev);
    if (ret)
        return ret;
    ret = cci_read(s->regmap, s->profile->id_reg, &id, NULL);
    if (!ret && id != s->profile->id)
        ret = -ENODEV;
    if (ret) {
        dev_err(dev, "%s chip ID read failed: %d\n", s->profile->name, ret);
        goto power_off;
    }
    dev_info(dev, "%s chip ID 0x%04llx (%s)\n", s->profile->name, id,
             s->profile->cphy ? "experimental C-PHY RAW mode" : "fixed RAW mode candidate");
    v4l2_ctrl_handler_init(&s->controls, 1);
    ctrl = v4l2_ctrl_new_int_menu(&s->controls, NULL, V4L2_CID_LINK_FREQ, 0, 0, &s->profile->link_frequency);
    if (ctrl)
        ctrl->flags |= V4L2_CTRL_FLAG_READ_ONLY;
    if (s->controls.error) {
        ret = s->controls.error;
        goto controls;
    }
    s->sd.ctrl_handler = &s->controls;
    s->sd.state_lock = s->controls.lock;
    s->sd.internal_ops = &sensor_internal_ops;
    s->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;
    s->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
    s->pad.flags = MEDIA_PAD_FL_SOURCE;
    ret = media_entity_pads_init(&s->sd.entity, 1, &s->pad);
    if (ret)
        goto controls;
    ret = v4l2_subdev_init_finalize(&s->sd);
    if (ret)
        goto entity;
    pm_runtime_set_active(dev);
    pm_runtime_enable(dev);
    ret = v4l2_async_register_subdev_sensor(&s->sd);
    if (ret)
        goto runtime;
    s->registered = true;
    pm_runtime_idle(dev);
    return 0;
runtime:
    pm_runtime_disable(dev);
    pm_runtime_set_suspended(dev);
    v4l2_subdev_cleanup(&s->sd);
entity:
    media_entity_cleanup(&s->sd.entity);
controls:
    v4l2_ctrl_handler_free(&s->controls);
power_off:
    sensor_power_off(dev);
    return ret;
}

static void sensor_remove(struct i2c_client *client)
{
    struct test_sensor *s = to_sensor(i2c_get_clientdata(client));
    if (!s->registered)
        return;
    v4l2_async_unregister_subdev(&s->sd);
    v4l2_subdev_cleanup(&s->sd);
    media_entity_cleanup(&s->sd.entity);
    v4l2_ctrl_handler_free(&s->controls);
    pm_runtime_disable(&client->dev);
    if (!pm_runtime_status_suspended(&client->dev))
        sensor_power_off(&client->dev);
    pm_runtime_set_suspended(&client->dev);
}

static const struct sensor_profile ov08a10 = {
    .name = "ov08a10",
    .id_reg = CCI_REG16(0x300b),
    .id = 0x0841,
    .width = 3264, .height = 1836, .code = MEDIA_BUS_FMT_SBGGR10_1X10,
    .link_frequency = 800000000,
    .registers = ov08a10_ftm, .nregisters = ARRAY_SIZE(ov08a10_ftm),
    .nsupplies = 4,
    .supplies = { "vdda", "vddd", "vaf", "vddio" },
};
static const struct sensor_profile imx789 = {
    .name = "imx789",
    .id_reg = CCI_REG16(0x0016),
    .id = 0x0789,
    .width = 4000, .height = 3008, .code = MEDIA_BUS_FMT_SBGGR10_1X10,
    .link_frequency = 823200000,
    .registers = imx789_ftm, .nregisters = ARRAY_SIZE(imx789_ftm),
    .nsupplies = 5,
    .supplies = { "vdda", "vddd", "vddio", "vaf", "custom1" },
    .cphy = true,
};
static const struct of_device_id sensor_match[] = {
    { .compatible = "ovti,ov08a10", .data = &ov08a10 },
    { .compatible = "sony,imx789", .data = &imx789 },
    { }
};
MODULE_DEVICE_TABLE(of, sensor_match);
static DEFINE_RUNTIME_DEV_PM_OPS(sensor_pm, sensor_power_off, sensor_power_on, NULL);
static struct i2c_driver sensor_driver = {
    .probe = sensor_probe,
    .remove = sensor_remove,
    .driver = {
        .name = "negroni-extra-sensors",
        .of_match_table = sensor_match,
        .pm = pm_sleep_ptr(&sensor_pm),
    },
};
module_i2c_driver(sensor_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Experimental Negroni OV08A10 and IMX789 fixed RAW modes");
