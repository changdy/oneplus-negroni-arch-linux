// SPDX-License-Identifier: GPL-2.0
/*
 * imx615.c - experimental IMX615 sensor driver for Negroni
 * Based on the IMX471 driver; original authors retained below.
 * Register sequences: OnePlusOSS SM8450 camera-kernel snapshot
 * 877203a7cf9b79973d44a9db716490f95d820110, cam_sensor_settings.h,
 * imx615_setting (FTM), split into global and 3280x2464 mode settings.
 * The 238 global entries match the local stock sensormodule byte-for-byte.
 * This initial mode has no sensor-specific lens shading or colour tuning.
 *
 * Copyright (C) 2025 Intel Corporation
 * Copyright (C) 2026 Kate Hsuan <hpa@redhat.com>
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/pm_runtime.h>
#include <linux/regulator/consumer.h>
#include <media/v4l2-cci.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-subdev.h>
#include <media/v4l2-fwnode.h>

#define IMX615_REG_MODE_SELECT			CCI_REG8(0x0100)
#define IMX615_MODE_STANDBY			0x00
#define IMX615_MODE_STREAMING			0x01

/* Chip ID */
#define IMX615_REG_CHIP_ID			CCI_REG16(0x0016)
#define IMX615_CHIP_ID				0x0615

/* V_TIMING internal */
#define IMX615_REG_FLL				CCI_REG16(0x0340)
#define IMX615_FLL_MAX				0xffff

/* Exposure control */
#define IMX615_REG_EXPOSURE			CCI_REG16(0x0202)
#define IMX615_EXPOSURE_MIN			16
#define IMX615_EXPOSURE_STEP			1
#define IMX615_EXPOSURE_DEFAULT			2510

/* Default exposure margin */
#define IMX615_EXPOSURE_MARGIN			48

/* Analog gain control */
#define IMX615_REG_ANALOG_GAIN			CCI_REG16(0x0204)
#define IMX615_ANA_GAIN_MIN			0
#define IMX615_ANA_GAIN_MAX			960
#define IMX615_ANA_GAIN_STEP			1
#define IMX615_ANA_GAIN_DEFAULT			0

/* Digital gain control */
#define IMX615_REG_DPGA_USE_GLOBAL_GAIN		CCI_REG16(0x3ff9)
#define IMX615_REG_DIG_GAIN_GLOBAL		CCI_REG16(0x020e)
#define IMX615_DGTL_GAIN_MIN			256
#define IMX615_DGTL_GAIN_MAX			4095
#define IMX615_DGTL_GAIN_STEP			1
#define IMX615_DGTL_GAIN_DEFAULT		256

/* HFLIP and VFLIP control */
#define IMX615_REG_ORIENTATION			CCI_REG8(0x0101)

/* Test Pattern Control */
#define IMX615_REG_TEST_PATTERN			CCI_REG16(0x0600)

/* default link frequency and external clock */
#define IMX615_LINK_FREQ_DEFAULT		334400000LL
#define IMX615_EXT_CLK				19200000

/* PLL */
#define IMX615_REG_VTPXCK_DIV			CCI_REG8(0x0301)
#define IMX615_REG_VTSYCK_DIV			CCI_REG8(0x0303)
#define IMX615_REG_PREPLLCK_VT_DIV		CCI_REG8(0x0305)
#define IMX615_REG_PLL_VT_MPY			CCI_REG16(0x0306)
#define IMX615_REG_OPPXCK_DIV			CCI_REG8(0x0309)
#define IMX615_REG_OPSYCK_DIV			CCI_REG8(0x030b)
#define IMX615_REG_PLL_MULT_DRIV		CCI_REG8(0x0310)
#define IMX615_PLL_SINGLE			0
#define IMX615_PLL_DUAL				1

/* IMX615 native and active pixel array size */
#define IMX615_NATIVE_WIDTH			6560
#define IMX615_NATIVE_HEIGHT			4928
#define IMX615_PIXEL_ARRAY_LEFT			0
#define IMX615_PIXEL_ARRAY_TOP			0
#define IMX615_PIXEL_ARRAY_WIDTH		6560
#define IMX615_PIXEL_ARRAY_HEIGHT		4928

#define IMX615_REG_EXCK_FREQ			CCI_REG16(0x0136)

#define IMX615_REG_CSI_DATA_FORMAT		CCI_REG16(0x0112)
#define IMX615_CSI_DATA_FORMAT_RAW10		0x0a0a

#define IMX615_REG_CSI_LANE_MODE		CCI_REG8(0x0114)
#define IMX615_CSI_2_LANE_MODE			1
#define IMX615_CSI_4_LANE_MODE			3

#define IMX615_REG_X_ADD_STA			CCI_REG16(0x0344)
#define IMX615_REG_Y_ADD_STA			CCI_REG16(0x0346)
#define IMX615_REG_X_ADD_END			CCI_REG16(0x0348)
#define IMX615_REG_Y_ADD_END			CCI_REG16(0x034a)
#define IMX615_REG_X_OUTPUT_SIZE		CCI_REG16(0x034c)
#define IMX615_REG_Y_OUTPUT_SIZE		CCI_REG16(0x034e)
#define IMX615_REG_X_EVEN_INC			CCI_REG8(0x0381)
#define IMX615_REG_X_ODD_INC			CCI_REG8(0x0383)
#define IMX615_REG_Y_EVEN_INC			CCI_REG8(0x0385)
#define IMX615_REG_Y_ODD_INC			CCI_REG8(0x0387)

#define IMX615_REG_DIG_CROP_X_OFFSET		CCI_REG16(0x0408)
#define IMX615_REG_DIG_CROP_Y_OFFSET		CCI_REG16(0x040a)
#define IMX615_REG_DIG_CROP_WIDTH		CCI_REG16(0x040c)
#define IMX615_REG_DIG_CROP_HEIGHT		CCI_REG16(0x040e)

/* Binning mode */
#define IMX615_REG_BINNING_MODE			CCI_REG8(0x0900)
#define IMX615_BINNING_NONE			0
#define IMX615_BINNING_ENABLE			1
#define IMX615_REG_BINNING_TYPE			CCI_REG8(0x0901)
#define IMX615_REG_BINNING_WEIGHTING		CCI_REG8(0x0902)

#define to_imx615(_sd) container_of_const(_sd, struct imx615, sd)

static const char * const imx615_supply_name[] = {
	"vdda",
	"vddd",
	"vddio",
};

struct imx615_mode {
	u32 width;
	u32 height;

	/* V-timing */
	u32 fll_def;
	u32 fll_min;

	/* H-timing */
	u32 llp;

	const struct cci_reg_sequence *default_mode_regs;
	unsigned int default_mode_regs_length;
};

struct imx615 {
	struct v4l2_subdev sd;
	struct media_pad pad;

	struct v4l2_ctrl_handler ctrl_handler;
	struct v4l2_ctrl *vblank;
	struct v4l2_ctrl *hblank;
	struct v4l2_ctrl *vflip;
	struct v4l2_ctrl *hflip;
	struct v4l2_ctrl *exposure;

	struct gpio_desc *reset_gpio;
	struct regulator_bulk_data supplies[ARRAY_SIZE(imx615_supply_name)];
	struct clk *img_clk;

	struct device *dev;
	struct regmap *regmap;
};

static const struct cci_reg_sequence imx615_global_regs[] = {
	{ CCI_REG8(0x0136), 0x13 },
	{ CCI_REG8(0x0137), 0x33 },
	{ CCI_REG8(0x3c7e), 0x01 },
	{ CCI_REG8(0x3c7f), 0x01 },
	{ CCI_REG8(0x0111), 0x02 },
	{ CCI_REG8(0x380c), 0x00 },
	{ CCI_REG8(0x3c00), 0x01 },
	{ CCI_REG8(0x3c01), 0x00 },
	{ CCI_REG8(0x3c02), 0x00 },
	{ CCI_REG8(0x3c03), 0x03 },
	{ CCI_REG8(0x3c04), 0xff },
	{ CCI_REG8(0x3c05), 0x01 },
	{ CCI_REG8(0x3c06), 0x00 },
	{ CCI_REG8(0x3c07), 0x00 },
	{ CCI_REG8(0x3c08), 0x03 },
	{ CCI_REG8(0x3c09), 0xff },
	{ CCI_REG8(0x3c0a), 0x00 },
	{ CCI_REG8(0x3c0b), 0x00 },
	{ CCI_REG8(0x3c0c), 0x10 },
	{ CCI_REG8(0x3c0d), 0x10 },
	{ CCI_REG8(0x3c0e), 0x10 },
	{ CCI_REG8(0x3c0f), 0x10 },
	{ CCI_REG8(0x3c10), 0x10 },
	{ CCI_REG8(0x3c11), 0x20 },
	{ CCI_REG8(0x3c15), 0x00 },
	{ CCI_REG8(0x3c16), 0x00 },
	{ CCI_REG8(0x3c17), 0x01 },
	{ CCI_REG8(0x3c18), 0x00 },
	{ CCI_REG8(0x3c19), 0x01 },
	{ CCI_REG8(0x3c1a), 0x00 },
	{ CCI_REG8(0x3c1b), 0x01 },
	{ CCI_REG8(0x3c1c), 0x00 },
	{ CCI_REG8(0x3c1d), 0x01 },
	{ CCI_REG8(0x3c1e), 0x00 },
	{ CCI_REG8(0x3c1f), 0x00 },
	{ CCI_REG8(0x3f89), 0x01 },
	{ CCI_REG8(0x3f8f), 0x01 },
	{ CCI_REG8(0x53b9), 0x01 },
	{ CCI_REG8(0x62c4), 0x04 },
	{ CCI_REG8(0x658f), 0x07 },
	{ CCI_REG8(0x6590), 0x05 },
	{ CCI_REG8(0x6591), 0x07 },
	{ CCI_REG8(0x6592), 0x05 },
	{ CCI_REG8(0x6593), 0x07 },
	{ CCI_REG8(0x6594), 0x05 },
	{ CCI_REG8(0x6595), 0x07 },
	{ CCI_REG8(0x6596), 0x05 },
	{ CCI_REG8(0x6597), 0x05 },
	{ CCI_REG8(0x6598), 0x05 },
	{ CCI_REG8(0x6599), 0x05 },
	{ CCI_REG8(0x659a), 0x05 },
	{ CCI_REG8(0x659b), 0x05 },
	{ CCI_REG8(0x659c), 0x05 },
	{ CCI_REG8(0x659d), 0x05 },
	{ CCI_REG8(0x659e), 0x07 },
	{ CCI_REG8(0x659f), 0x05 },
	{ CCI_REG8(0x65a0), 0x07 },
	{ CCI_REG8(0x65a1), 0x05 },
	{ CCI_REG8(0x65a2), 0x07 },
	{ CCI_REG8(0x65a3), 0x05 },
	{ CCI_REG8(0x65a4), 0x07 },
	{ CCI_REG8(0x65a5), 0x05 },
	{ CCI_REG8(0x65a6), 0x05 },
	{ CCI_REG8(0x65a7), 0x05 },
	{ CCI_REG8(0x65a8), 0x05 },
	{ CCI_REG8(0x65a9), 0x05 },
	{ CCI_REG8(0x65aa), 0x05 },
	{ CCI_REG8(0x65ab), 0x05 },
	{ CCI_REG8(0x65ac), 0x05 },
	{ CCI_REG8(0x65ad), 0x07 },
	{ CCI_REG8(0x65ae), 0x07 },
	{ CCI_REG8(0x65af), 0x07 },
	{ CCI_REG8(0x65b0), 0x05 },
	{ CCI_REG8(0x65b1), 0x05 },
	{ CCI_REG8(0x65b2), 0x05 },
	{ CCI_REG8(0x65b3), 0x05 },
	{ CCI_REG8(0x65b4), 0x07 },
	{ CCI_REG8(0x65b5), 0x07 },
	{ CCI_REG8(0x65b6), 0x07 },
	{ CCI_REG8(0x65b7), 0x07 },
	{ CCI_REG8(0x65b8), 0x05 },
	{ CCI_REG8(0x65b9), 0x05 },
	{ CCI_REG8(0x65ba), 0x05 },
	{ CCI_REG8(0x65bb), 0x05 },
	{ CCI_REG8(0x65bc), 0x05 },
	{ CCI_REG8(0x65bd), 0x05 },
	{ CCI_REG8(0x65be), 0x05 },
	{ CCI_REG8(0x65bf), 0x05 },
	{ CCI_REG8(0x65c0), 0x05 },
	{ CCI_REG8(0x65c1), 0x05 },
	{ CCI_REG8(0x65c2), 0x05 },
	{ CCI_REG8(0x65c3), 0x05 },
	{ CCI_REG8(0x65c4), 0x05 },
	{ CCI_REG8(0x65c5), 0x05 },
	{ CCI_REG8(0x6e1c), 0x00 },
	{ CCI_REG8(0x6e1d), 0x00 },
	{ CCI_REG8(0x6e25), 0x00 },
	{ CCI_REG8(0x6e38), 0x03 },
	{ CCI_REG8(0x895c), 0x01 },
	{ CCI_REG8(0x895d), 0x00 },
	{ CCI_REG8(0x8966), 0x00 },
	{ CCI_REG8(0x8967), 0x4e },
	{ CCI_REG8(0x896a), 0x00 },
	{ CCI_REG8(0x896b), 0x24 },
	{ CCI_REG8(0x896f), 0x34 },
	{ CCI_REG8(0x8976), 0x00 },
	{ CCI_REG8(0x8977), 0x00 },
	{ CCI_REG8(0x9004), 0x1f },
	{ CCI_REG8(0x9200), 0xb7 },
	{ CCI_REG8(0x9201), 0x34 },
	{ CCI_REG8(0x9202), 0xb7 },
	{ CCI_REG8(0x9203), 0x36 },
	{ CCI_REG8(0x9204), 0xb7 },
	{ CCI_REG8(0x9205), 0x37 },
	{ CCI_REG8(0x9206), 0xb7 },
	{ CCI_REG8(0x9207), 0x38 },
	{ CCI_REG8(0x9208), 0xb7 },
	{ CCI_REG8(0x9209), 0x39 },
	{ CCI_REG8(0x920a), 0xb7 },
	{ CCI_REG8(0x920b), 0x3a },
	{ CCI_REG8(0x920c), 0xb7 },
	{ CCI_REG8(0x920d), 0x3c },
	{ CCI_REG8(0x920e), 0xb7 },
	{ CCI_REG8(0x920f), 0x3d },
	{ CCI_REG8(0x9210), 0xb7 },
	{ CCI_REG8(0x9211), 0x3e },
	{ CCI_REG8(0x9212), 0xb7 },
	{ CCI_REG8(0x9213), 0x3f },
	{ CCI_REG8(0x9214), 0xf6 },
	{ CCI_REG8(0x9215), 0x13 },
	{ CCI_REG8(0x9216), 0xf6 },
	{ CCI_REG8(0x9217), 0x34 },
	{ CCI_REG8(0x9218), 0xf4 },
	{ CCI_REG8(0x9219), 0xa7 },
	{ CCI_REG8(0x921a), 0xf4 },
	{ CCI_REG8(0x921b), 0xaa },
	{ CCI_REG8(0x921c), 0xf4 },
	{ CCI_REG8(0x921d), 0xad },
	{ CCI_REG8(0x921e), 0xf4 },
	{ CCI_REG8(0x921f), 0xb0 },
	{ CCI_REG8(0x9220), 0xf4 },
	{ CCI_REG8(0x9221), 0xb3 },
	{ CCI_REG8(0x9222), 0x85 },
	{ CCI_REG8(0x9223), 0x77 },
	{ CCI_REG8(0x9224), 0xc4 },
	{ CCI_REG8(0x9225), 0x4b },
	{ CCI_REG8(0x9226), 0xc4 },
	{ CCI_REG8(0x9227), 0x4c },
	{ CCI_REG8(0x9228), 0xc4 },
	{ CCI_REG8(0x9229), 0x4d },
	{ CCI_REG8(0x922a), 0xf5 },
	{ CCI_REG8(0x922b), 0x5e },
	{ CCI_REG8(0x922c), 0xf5 },
	{ CCI_REG8(0x922d), 0x5f },
	{ CCI_REG8(0x922e), 0xf5 },
	{ CCI_REG8(0x922f), 0x64 },
	{ CCI_REG8(0x9230), 0xf5 },
	{ CCI_REG8(0x9231), 0x65 },
	{ CCI_REG8(0x9232), 0xf5 },
	{ CCI_REG8(0x9233), 0x6a },
	{ CCI_REG8(0x9234), 0xf5 },
	{ CCI_REG8(0x9235), 0x6b },
	{ CCI_REG8(0x9236), 0xf5 },
	{ CCI_REG8(0x9237), 0x70 },
	{ CCI_REG8(0x9238), 0xf5 },
	{ CCI_REG8(0x9239), 0x71 },
	{ CCI_REG8(0x923a), 0xf5 },
	{ CCI_REG8(0x923b), 0x76 },
	{ CCI_REG8(0x923c), 0xf5 },
	{ CCI_REG8(0x923d), 0x77 },
	{ CCI_REG8(0x9810), 0x14 },
	{ CCI_REG8(0x9814), 0x14 },
	{ CCI_REG8(0xc020), 0x00 },
	{ CCI_REG8(0xc026), 0x00 },
	{ CCI_REG8(0xc027), 0x00 },
	{ CCI_REG8(0xc448), 0x01 },
	{ CCI_REG8(0xc44f), 0x01 },
	{ CCI_REG8(0xc450), 0x00 },
	{ CCI_REG8(0xc451), 0x00 },
	{ CCI_REG8(0xc452), 0x01 },
	{ CCI_REG8(0xc455), 0x00 },
	{ CCI_REG8(0xe186), 0x36 },
	{ CCI_REG8(0xe206), 0x35 },
	{ CCI_REG8(0xe226), 0x33 },
	{ CCI_REG8(0xe266), 0x34 },
	{ CCI_REG8(0xe2a6), 0x31 },
	{ CCI_REG8(0xe2c6), 0x37 },
	{ CCI_REG8(0xe2e6), 0x32 },
	{ CCI_REG8(0x88d6), 0x60 },
	{ CCI_REG8(0x9852), 0x00 },
	{ CCI_REG8(0xa569), 0x06 },
	{ CCI_REG8(0xa56a), 0x13 },
	{ CCI_REG8(0xa56b), 0x13 },
	{ CCI_REG8(0xa56c), 0x01 },
	{ CCI_REG8(0xa678), 0x00 },
	{ CCI_REG8(0xa679), 0x20 },
	{ CCI_REG8(0xa812), 0x00 },
	{ CCI_REG8(0xa813), 0x3f },
	{ CCI_REG8(0xa814), 0x3f },
	{ CCI_REG8(0xa830), 0x68 },
	{ CCI_REG8(0xa831), 0x56 },
	{ CCI_REG8(0xa832), 0x2b },
	{ CCI_REG8(0xa833), 0x55 },
	{ CCI_REG8(0xa834), 0x55 },
	{ CCI_REG8(0xa835), 0x16 },
	{ CCI_REG8(0xa837), 0x51 },
	{ CCI_REG8(0xa838), 0x34 },
	{ CCI_REG8(0xa854), 0x4f },
	{ CCI_REG8(0xa855), 0x48 },
	{ CCI_REG8(0xa856), 0x45 },
	{ CCI_REG8(0xa857), 0x02 },
	{ CCI_REG8(0xa85a), 0x23 },
	{ CCI_REG8(0xa85b), 0x16 },
	{ CCI_REG8(0xa85c), 0x12 },
	{ CCI_REG8(0xa85d), 0x02 },
	{ CCI_REG8(0xaa55), 0x00 },
	{ CCI_REG8(0xaa56), 0x01 },
	{ CCI_REG8(0xaa57), 0x30 },
	{ CCI_REG8(0xaa58), 0x01 },
	{ CCI_REG8(0xaa59), 0x30 },
	{ CCI_REG8(0xac72), 0x01 },
	{ CCI_REG8(0xac73), 0x26 },
	{ CCI_REG8(0xac74), 0x01 },
	{ CCI_REG8(0xac75), 0x26 },
	{ CCI_REG8(0xac76), 0x00 },
	{ CCI_REG8(0xac77), 0xc4 },
	{ CCI_REG8(0xae09), 0xff },
	{ CCI_REG8(0xae0a), 0xff },
	{ CCI_REG8(0xae12), 0x58 },
	{ CCI_REG8(0xae13), 0x58 },
	{ CCI_REG8(0xae15), 0x10 },
	{ CCI_REG8(0xae16), 0x10 },
	{ CCI_REG8(0xaf05), 0x48 },
	{ CCI_REG8(0xb069), 0x02 },
	{ CCI_REG8(0xea4b), 0x00 },
	{ CCI_REG8(0xea4c), 0x00 },
	{ CCI_REG8(0xea4d), 0x00 },
	{ CCI_REG8(0xea4e), 0x00 },
};

static const struct cci_reg_sequence mode_3280x2464_regs[] = {
	{ CCI_REG8(0x0112), 0x0a },
	{ CCI_REG8(0x0113), 0x0a },
	{ CCI_REG8(0x0114), 0x03 },
	{ CCI_REG8(0x0342), 0x0e },
	{ CCI_REG8(0x0343), 0xb8 },
	{ CCI_REG8(0x0340), 0x09 },
	{ CCI_REG8(0x0341), 0xfe },
	{ CCI_REG8(0x0344), 0x00 },
	{ CCI_REG8(0x0345), 0x00 },
	{ CCI_REG8(0x0346), 0x00 },
	{ CCI_REG8(0x0347), 0x00 },
	{ CCI_REG8(0x0348), 0x19 },
	{ CCI_REG8(0x0349), 0x9f },
	{ CCI_REG8(0x034a), 0x13 },
	{ CCI_REG8(0x034b), 0x3f },
	{ CCI_REG8(0x0900), 0x01 },
	{ CCI_REG8(0x0901), 0x22 },
	{ CCI_REG8(0x0902), 0x08 },
	{ CCI_REG8(0x3246), 0x81 },
	{ CCI_REG8(0x3247), 0x81 },
	{ CCI_REG8(0x0401), 0x00 },
	{ CCI_REG8(0x0404), 0x00 },
	{ CCI_REG8(0x0405), 0x10 },
	{ CCI_REG8(0x0408), 0x00 },
	{ CCI_REG8(0x0409), 0x00 },
	{ CCI_REG8(0x040a), 0x00 },
	{ CCI_REG8(0x040b), 0x00 },
	{ CCI_REG8(0x040c), 0x0c },
	{ CCI_REG8(0x040d), 0xd0 },
	{ CCI_REG8(0x040e), 0x09 },
	{ CCI_REG8(0x040f), 0xa0 },
	{ CCI_REG8(0x034c), 0x0c },
	{ CCI_REG8(0x034d), 0xd0 },
	{ CCI_REG8(0x034e), 0x09 },
	{ CCI_REG8(0x034f), 0xa0 },
	{ CCI_REG8(0x0301), 0x05 },
	{ CCI_REG8(0x0303), 0x04 },
	{ CCI_REG8(0x0305), 0x03 },
	{ CCI_REG8(0x0306), 0x00 },
	{ CCI_REG8(0x0307), 0xe2 },
	{ CCI_REG8(0x030b), 0x02 },
	{ CCI_REG8(0x030d), 0x03 },
	{ CCI_REG8(0x030e), 0x00 },
	{ CCI_REG8(0x030f), 0xd1 },
	{ CCI_REG8(0x0310), 0x01 },
	{ CCI_REG8(0x3620), 0x00 },
	{ CCI_REG8(0x3621), 0x00 },
	{ CCI_REG8(0x3c12), 0x56 },
	{ CCI_REG8(0x3c13), 0x52 },
	{ CCI_REG8(0x3c14), 0x3e },
	{ CCI_REG8(0x3f0c), 0x00 },
	{ CCI_REG8(0x3f14), 0x01 },
	{ CCI_REG8(0x3f80), 0x00 },
	{ CCI_REG8(0x3f81), 0xa0 },
	{ CCI_REG8(0x3f8c), 0x00 },
	{ CCI_REG8(0x3f8d), 0x00 },
	{ CCI_REG8(0x3ffc), 0x00 },
	{ CCI_REG8(0x3ffd), 0x1e },
	{ CCI_REG8(0x3ffe), 0x00 },
	{ CCI_REG8(0x3fff), 0xdc },
	{ CCI_REG8(0x0202), 0x09 },
	{ CCI_REG8(0x0203), 0xce },
	{ CCI_REG8(0x0204), 0x00 },
	{ CCI_REG8(0x0205), 0x70 },
	{ CCI_REG8(0x020e), 0x01 },
	{ CCI_REG8(0x020f), 0x00 },
	{ CCI_REG8(0x0210), 0x01 },
	{ CCI_REG8(0x0211), 0x00 },
	{ CCI_REG8(0x0212), 0x01 },
	{ CCI_REG8(0x0213), 0x00 },
	{ CCI_REG8(0x0214), 0x01 },
	{ CCI_REG8(0x0215), 0x00 },
};

static const char * const imx615_test_pattern_menu[] = {
	"Disabled",
	"Solid Colour",
	"Eight Vertical Colour Bars",
	"Colour Bars With Fade to Grey",
	"Pseudorandom Sequence (PN9)",
};

static const s64 link_freq_menu_items[] = {
	IMX615_LINK_FREQ_DEFAULT,
};

/*
 * The Bayer formats for the flipping.
 * - no flip
 * - h flip
 * - v flip
 * - h and v flips
 */
static const u32 imx615_hv_flips_bayer_order[] = {
	MEDIA_BUS_FMT_SRGGB10_1X10,
	MEDIA_BUS_FMT_SGRBG10_1X10,
	MEDIA_BUS_FMT_SGBRG10_1X10,
	MEDIA_BUS_FMT_SBGGR10_1X10,
};

static const struct imx615_mode imx615_modes[] = {
	{
		.width = 3280,
		.height = 2464,
		.fll_def = 2558,
		.fll_min = 2558,
		.llp = 3768,
		.default_mode_regs = mode_3280x2464_regs,
		.default_mode_regs_length = ARRAY_SIZE(mode_3280x2464_regs),
	},
};

static int imx615_get_regulators(struct device *dev, struct imx615 *sensor)
{
	for (unsigned int i = 0; i < ARRAY_SIZE(imx615_supply_name); i++)
		sensor->supplies[i].supply = imx615_supply_name[i];

	return devm_regulator_bulk_get(dev, ARRAY_SIZE(imx615_supply_name),
				       sensor->supplies);
}

static int imx615_set_ctrl(struct v4l2_ctrl *ctrl)
{
	struct imx615 *sensor = container_of_const(ctrl->handler,
						   struct imx615,
						   ctrl_handler);
	struct v4l2_subdev_state *state =
			v4l2_subdev_get_locked_active_state(&sensor->sd);
	const struct v4l2_mbus_framefmt *format =
			v4l2_subdev_state_get_format(state, 0);
	int ret;

	if (ctrl->id == V4L2_CID_VBLANK) {
		s64 exposure_max = format->height + ctrl->val -
				   IMX615_EXPOSURE_MARGIN;
		ret = __v4l2_ctrl_modify_range(sensor->exposure,
					       sensor->exposure->minimum,
					       exposure_max,
					       sensor->exposure->step,
					       exposure_max);
		if (ret)
			return ret;
	}

	if (!pm_runtime_get_if_in_use(sensor->dev))
		return 0;

	switch (ctrl->id) {
	case V4L2_CID_ANALOGUE_GAIN:
		ret = cci_write(sensor->regmap, IMX615_REG_ANALOG_GAIN,
				ctrl->val, NULL);
		break;
	case V4L2_CID_DIGITAL_GAIN:
		ret = cci_write(sensor->regmap, IMX615_REG_DIG_GAIN_GLOBAL,
				ctrl->val, NULL);
		break;
	case V4L2_CID_EXPOSURE:
		ret = cci_write(sensor->regmap, IMX615_REG_EXPOSURE,
				ctrl->val, NULL);
		break;
	case V4L2_CID_VBLANK:
		/* Update FLL that meets expected vertical blanking */
		ret = cci_write(sensor->regmap, IMX615_REG_FLL,
				format->height + ctrl->val, NULL);
		break;
	case V4L2_CID_TEST_PATTERN:
		ret = cci_write(sensor->regmap, IMX615_REG_TEST_PATTERN,
				ctrl->val, NULL);
		break;
	case V4L2_CID_HFLIP:
	case V4L2_CID_VFLIP:
		ret = cci_write(sensor->regmap, IMX615_REG_ORIENTATION,
				sensor->hflip->val | sensor->vflip->val << 1,
				NULL);
		break;
	default:
		ret = -EINVAL;
		dev_err(sensor->dev, "ctrl(id:0x%x,val:0x%x) is not handled\n",
			ctrl->id, ctrl->val);
		break;
	}

	pm_runtime_put(sensor->dev);

	return ret;
}

static const struct v4l2_ctrl_ops imx615_ctrl_ops = {
	.s_ctrl = imx615_set_ctrl,
};

static u32 imx615_get_format_code(struct imx615 *sensor)
{
	unsigned int i;

	i = (sensor->vflip->val ? 2 : 0) | (sensor->hflip->val ? 1 : 0);

	return imx615_hv_flips_bayer_order[i];
}

static int imx615_enum_mbus_code(struct v4l2_subdev *sd,
				 struct v4l2_subdev_state *sd_state,
				 struct v4l2_subdev_mbus_code_enum *code)
{
	struct imx615 *sensor = to_imx615(sd);

	if (code->index >= (ARRAY_SIZE(imx615_hv_flips_bayer_order) / 4))
		return -EINVAL;

	code->code = imx615_get_format_code(sensor);

	return 0;
}

static int imx615_enum_frame_size(struct v4l2_subdev *sd,
				  struct v4l2_subdev_state *sd_state,
				  struct v4l2_subdev_frame_size_enum *fse)
{
	if (fse->index >= ARRAY_SIZE(imx615_modes))
		return -EINVAL;

	fse->min_width = imx615_modes[fse->index].width;
	fse->max_width = fse->min_width;
	fse->min_height = imx615_modes[fse->index].height;
	fse->max_height = fse->min_height;

	return 0;
}

static void imx615_update_pad_format(struct imx615 *sensor,
				     const struct imx615_mode *mode,
				     struct v4l2_subdev_format *fmt)
{
	fmt->format.code = imx615_get_format_code(sensor);
	fmt->format.width = mode->width;
	fmt->format.height = mode->height;
	fmt->format.field = V4L2_FIELD_NONE;
}

static int imx615_set_pad_format(struct v4l2_subdev *sd,
				 struct v4l2_subdev_state *sd_state,
				 struct v4l2_subdev_format *fmt)
{
	struct imx615 *sensor = to_imx615(sd);
	const struct imx615_mode *mode;
	int h_blank, ret;

	mode = v4l2_find_nearest_size(imx615_modes, ARRAY_SIZE(imx615_modes),
				      width, height, fmt->format.width,
				      fmt->format.height);

	if (fmt->which == V4L2_SUBDEV_FORMAT_ACTIVE &&
	    media_entity_is_streaming(&sensor->sd.entity))
		return -EBUSY;

	imx615_update_pad_format(sensor, mode, fmt);
	*v4l2_subdev_state_get_format(sd_state, fmt->pad) = fmt->format;

	if (fmt->which == V4L2_SUBDEV_FORMAT_TRY)
		return 0;

	ret = __v4l2_ctrl_modify_range(sensor->vblank,
				       mode->fll_min - mode->height,
				       IMX615_FLL_MAX - mode->height,
				       1,
				       mode->fll_def - mode->height);
	if (ret)
		return ret;

	h_blank = mode->llp - mode->width;
	/*
	 * Currently hblank is not changeable.
	 * So FPS control is done only by vblank.
	 */
	return __v4l2_ctrl_modify_range(sensor->hblank, h_blank,
					h_blank, 1, h_blank);
}

static int imx615_get_selection(struct v4l2_subdev *sd,
				struct v4l2_subdev_state *sd_state,
				struct v4l2_subdev_selection *sel)
{
	switch (sel->target) {
	case V4L2_SEL_TGT_CROP:
		sel->r = *v4l2_subdev_state_get_crop(sd_state, sel->pad);
		break;

	case V4L2_SEL_TGT_NATIVE_SIZE:
		sel->r.top = 0;
		sel->r.left = 0;
		sel->r.width = IMX615_NATIVE_WIDTH;
		sel->r.height = IMX615_NATIVE_HEIGHT;
		return 0;

	case V4L2_SEL_TGT_CROP_DEFAULT:
	case V4L2_SEL_TGT_CROP_BOUNDS:
		sel->r.top = IMX615_PIXEL_ARRAY_TOP;
		sel->r.left = IMX615_PIXEL_ARRAY_LEFT;
		sel->r.width = IMX615_PIXEL_ARRAY_WIDTH;
		sel->r.height = IMX615_PIXEL_ARRAY_HEIGHT;
		return 0;
	}

	return -EINVAL;
}

static int imx615_init_state(struct v4l2_subdev *sd,
			     struct v4l2_subdev_state *sd_state)
{
	struct v4l2_subdev_format fmt = {
		.which = V4L2_SUBDEV_FORMAT_TRY,
		.format = {
			.code = MEDIA_BUS_FMT_SRGGB10_1X10,
			.width = imx615_modes[0].width,
			.height = imx615_modes[0].height,
		},
	};

	return imx615_set_pad_format(sd, sd_state, &fmt);
}

static int imx615_identify_module(struct imx615 *sensor)
{
	int ret;
	u64 val;

	ret = cci_read(sensor->regmap, IMX615_REG_CHIP_ID, &val, NULL);
	if (ret)
		return dev_err_probe(sensor->dev, ret,
				     "failed to read chip id\n");

	if (val != IMX615_CHIP_ID)
		return dev_err_probe(sensor->dev, -EIO,
				     "chip id mismatch: %x!=%llx\n",
				     IMX615_CHIP_ID, val);

	dev_info(sensor->dev, "IMX615 chip ID 0x%04llx\n", val);
	return 0;
}

static int imx615_power_off(struct device *dev)
{
	struct v4l2_subdev *sd = dev_get_drvdata(dev);
	struct imx615 *sensor = to_imx615(sd);

	clk_disable_unprepare(sensor->img_clk);
	gpiod_set_value_cansleep(sensor->reset_gpio, 1);

	regulator_bulk_disable(ARRAY_SIZE(imx615_supply_name),
			       sensor->supplies);

	return 0;
}

static int imx615_power_on(struct device *dev)
{
	struct v4l2_subdev *sd = dev_get_drvdata(dev);
	struct imx615 *sensor = to_imx615(sd);
	int ret;

	for (unsigned int i = 0; i < ARRAY_SIZE(imx615_supply_name); i++) {
		ret = regulator_enable(sensor->supplies[i].consumer);
		if (ret) {
			while (i)
				regulator_disable(sensor->supplies[--i].consumer);
			return ret;
		}
	}
	ret = 0;
	if (ret < 0) {
		dev_err(dev, "failed to enable regulators: %d\n", ret);
		return ret;
	}

	ret = clk_prepare_enable(sensor->img_clk);
	if (ret < 0) {
		regulator_bulk_disable(ARRAY_SIZE(imx615_supply_name),
				       sensor->supplies);
		dev_err(dev, "failed to enable imaging clock: %d\n", ret);
		return ret;
	}

	gpiod_set_value_cansleep(sensor->reset_gpio, 0);

	usleep_range(10000, 15000);

	return 0;
}

static int imx615_enable_stream(struct v4l2_subdev *sd,
				struct v4l2_subdev_state *state,
				u32 pad, u64 streams_mask)
{
	struct imx615 *sensor = to_imx615(sd);
	const struct imx615_mode *mode;
	struct v4l2_mbus_framefmt *fmt;
	int ret;

	ret = pm_runtime_resume_and_get(sensor->dev);
	if (ret)
		return ret;

	ret = imx615_identify_module(sensor);
	if (ret)
		goto error_powerdown;

	ret = cci_multi_reg_write(sensor->regmap, imx615_global_regs,
				  ARRAY_SIZE(imx615_global_regs), NULL);
	if (ret) {
		dev_err(sensor->dev, "failed to set global settings: %d\n",
			ret);
		goto error_powerdown;
	}

	fmt = v4l2_subdev_state_get_format(state, 0);
	mode = v4l2_find_nearest_size(imx615_modes, ARRAY_SIZE(imx615_modes),
				      width, height, fmt->width, fmt->height);

	ret = cci_multi_reg_write(sensor->regmap, mode->default_mode_regs,
				  mode->default_mode_regs_length, NULL);
	if (ret) {
		dev_err(sensor->dev, "failed to set mode: %d\n", ret);
		goto error_powerdown;
	}

	ret = __v4l2_ctrl_handler_setup(&sensor->ctrl_handler);
	if (ret)
		goto error_powerdown;

	ret = cci_write(sensor->regmap, IMX615_REG_MODE_SELECT,
			IMX615_MODE_STREAMING, NULL);
	if (ret)
		goto error_powerdown;

	__v4l2_ctrl_grab(sensor->vflip, true);
	__v4l2_ctrl_grab(sensor->hflip, true);

	return ret;

error_powerdown:
	pm_runtime_put(sensor->dev);

	return ret;
}

static int imx615_disable_stream(struct v4l2_subdev *sd,
				 struct v4l2_subdev_state *state,
				 u32 pad, u64 streams_mask)
{
	struct imx615 *sensor = to_imx615(sd);
	int ret;

	ret = cci_write(sensor->regmap, IMX615_REG_MODE_SELECT,
			IMX615_MODE_STANDBY, NULL);
	pm_runtime_put(sensor->dev);

	if (ret)
		dev_err(sensor->dev,
			"failed to disable stream with return value: %d\n",
			ret);

	__v4l2_ctrl_grab(sensor->vflip, false);
	__v4l2_ctrl_grab(sensor->hflip, false);

	return 0;
}

static const struct v4l2_subdev_video_ops imx615_video_ops = {
	.s_stream = v4l2_subdev_s_stream_helper,
};

static const struct v4l2_subdev_pad_ops imx615_pad_ops = {
	.enum_mbus_code = imx615_enum_mbus_code,
	.get_fmt = v4l2_subdev_get_fmt,
	.set_fmt = imx615_set_pad_format,
	.get_selection = imx615_get_selection,
	.enum_frame_size = imx615_enum_frame_size,
	.enable_streams = imx615_enable_stream,
	.disable_streams = imx615_disable_stream,
};

static const struct v4l2_subdev_ops imx615_subdev_ops = {
	.video = &imx615_video_ops,
	.pad = &imx615_pad_ops,
};

static const struct v4l2_subdev_internal_ops imx615_internal_ops = {
	.init_state = imx615_init_state,
};

static int imx615_init_controls(struct imx615 *sensor)
{
	const struct imx615_mode *mode = &imx615_modes[0];
	struct v4l2_fwnode_device_properties props;
	struct v4l2_ctrl_handler *ctrl_hdlr;
	struct v4l2_ctrl *link_freq;
	s64 exposure_max, hblank;
	u64 pixel_rate;
	int ret;

	ret = v4l2_fwnode_device_parse(sensor->dev, &props);
	if (ret) {
		dev_err(sensor->dev, "failed to parse fwnode: %d\n", ret);
		return ret;
	}

	ctrl_hdlr = &sensor->ctrl_handler;
	v4l2_ctrl_handler_init(ctrl_hdlr, 12);

	v4l2_ctrl_new_fwnode_properties(ctrl_hdlr, &imx615_ctrl_ops, &props);

	link_freq = v4l2_ctrl_new_int_menu(ctrl_hdlr,
					   &imx615_ctrl_ops,
					   V4L2_CID_LINK_FREQ,
					   ARRAY_SIZE(link_freq_menu_items) - 1,
					   0,
					   link_freq_menu_items);

	/* V4L2 pixel rate describes the line/frame timing clock. */
	pixel_rate = 289280000; /* VT clock of the factory-test PLL */

	v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops,
			  V4L2_CID_PIXEL_RATE, pixel_rate,
			  pixel_rate, 1, pixel_rate);

	sensor->vblank = v4l2_ctrl_new_std(ctrl_hdlr,
					   &imx615_ctrl_ops,
					   V4L2_CID_VBLANK,
					   mode->fll_min - mode->height,
					   IMX615_FLL_MAX - mode->height,
					   1,
					   mode->fll_def - mode->height);

	hblank = mode->llp - mode->width;
	sensor->hblank = v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops,
					   V4L2_CID_HBLANK, hblank, hblank,
					   1, hblank);

	/* fll >= exposure time + adjust parameter (default value is 18) */
	exposure_max = mode->fll_def - IMX615_EXPOSURE_MARGIN;
	sensor->exposure = v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops,
					     V4L2_CID_EXPOSURE,
					     IMX615_EXPOSURE_MIN, exposure_max,
					     IMX615_EXPOSURE_STEP,
					     IMX615_EXPOSURE_DEFAULT);

	v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops, V4L2_CID_ANALOGUE_GAIN,
			  IMX615_ANA_GAIN_MIN, IMX615_ANA_GAIN_MAX,
			  IMX615_ANA_GAIN_STEP, IMX615_ANA_GAIN_DEFAULT);

	v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops, V4L2_CID_DIGITAL_GAIN,
			  IMX615_DGTL_GAIN_MIN, IMX615_DGTL_GAIN_MAX,
			  IMX615_DGTL_GAIN_STEP, IMX615_DGTL_GAIN_DEFAULT);

	v4l2_ctrl_new_std_menu_items(ctrl_hdlr, &imx615_ctrl_ops,
				     V4L2_CID_TEST_PATTERN,
				     ARRAY_SIZE(imx615_test_pattern_menu) - 1,
				     0, 0, imx615_test_pattern_menu);

	sensor->hflip = v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops,
					  V4L2_CID_HFLIP, 0, 1, 1, 0);

	sensor->vflip = v4l2_ctrl_new_std(ctrl_hdlr, &imx615_ctrl_ops,
					  V4L2_CID_VFLIP, 0, 1, 1, 0);

	if (ctrl_hdlr->error) {
		dev_err(sensor->dev, "%s control init failed: %d\n",
			__func__, ctrl_hdlr->error);
		goto error;
	}

	link_freq->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	sensor->hblank->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	sensor->hflip->flags |= V4L2_CTRL_FLAG_MODIFY_LAYOUT;
	sensor->vflip->flags |= V4L2_CTRL_FLAG_MODIFY_LAYOUT;

	sensor->sd.ctrl_handler = ctrl_hdlr;

	return 0;

error:
	v4l2_ctrl_handler_free(ctrl_hdlr);

	return ctrl_hdlr->error;
}

static int imx615_check_hwcfg(struct imx615 *sensor)
{
	struct v4l2_fwnode_endpoint bus_cfg = {
		.bus_type = V4L2_MBUS_CSI2_DPHY,
	};
	struct fwnode_handle *ep, *fwnode = dev_fwnode(sensor->dev);
	unsigned long link_freq_bitmap;
	struct clk *clk;
	int ret;

	clk = devm_v4l2_sensor_clk_get(sensor->dev, NULL);
	if (IS_ERR(clk))
		return dev_err_probe(sensor->dev, PTR_ERR(clk),
				     "can't get clock frequency\n");

	if (clk_get_rate(clk) != IMX615_EXT_CLK)
		return dev_err_probe(sensor->dev, -EINVAL,
				     "external clock %lu is not supported\n",
				     clk_get_rate(clk));

	ep = fwnode_graph_get_endpoint_by_id(fwnode, 0, 0, 0);
	ret = v4l2_fwnode_endpoint_alloc_parse(ep, &bus_cfg);
	fwnode_handle_put(ep);
	if (ret)
		return dev_err_probe(sensor->dev, ret,
				     "parsing endpoint failed\n");

	if (bus_cfg.bus.mipi_csi2.num_data_lanes != 4) {
		ret = dev_err_probe(sensor->dev, -EINVAL,
				    "number of CSI2 data lanes %u is not supported\n",
				    bus_cfg.bus.mipi_csi2.num_data_lanes);
		goto done_endpoint_free;
	}

	ret = v4l2_link_freq_to_bitmap(sensor->dev, bus_cfg.link_frequencies,
				       bus_cfg.nr_of_link_frequencies,
				       link_freq_menu_items,
				       ARRAY_SIZE(link_freq_menu_items),
				       &link_freq_bitmap);

done_endpoint_free:
	v4l2_fwnode_endpoint_free(&bus_cfg);

	return ret;
}

static int imx615_probe(struct i2c_client *client)
{
	struct imx615 *sensor;
	int ret;

	sensor = devm_kzalloc(&client->dev, sizeof(*sensor), GFP_KERNEL);
	if (!sensor)
		return dev_err_probe(&client->dev, -ENOMEM,
				     "failed to allocate memory\n");

	sensor->dev = &client->dev;

	ret = imx615_check_hwcfg(sensor);
	if (ret)
		return dev_err_probe(sensor->dev, ret,
				     "failed to check hwcfg: %d\n", ret);

	ret = imx615_get_regulators(sensor->dev, sensor);
	if (ret)
		return dev_err_probe(sensor->dev, ret,
				     "failed to get regulators\n");

	sensor->reset_gpio = devm_gpiod_get_optional(sensor->dev, "reset",
						     GPIOD_OUT_HIGH);
	if (IS_ERR(sensor->reset_gpio))
		return dev_err_probe(sensor->dev, PTR_ERR(sensor->reset_gpio),
				     "failed to get reset gpio\n");

	sensor->img_clk = devm_v4l2_sensor_clk_get(sensor->dev, NULL);
	if (IS_ERR(sensor->img_clk))
		return dev_err_probe(sensor->dev, PTR_ERR(sensor->img_clk),
				     "failed to get imaging clock\n");

	v4l2_i2c_subdev_init(&sensor->sd, client, &imx615_subdev_ops);

	sensor->regmap = devm_cci_regmap_init_i2c(client, 16);
	if (IS_ERR(sensor->regmap))
		return dev_err_probe(sensor->dev, PTR_ERR(sensor->regmap),
				     "failed to initialize CCI\n");

	ret = imx615_power_on(sensor->dev);
	if (ret)
		return dev_err_probe(sensor->dev, ret,
				     "failed to power on\n");

	ret = imx615_identify_module(sensor);
	if (ret) {
		dev_err_probe(sensor->dev, ret, "failed to find sensor: %d\n",
			      ret);
		goto error_power_off;
	}

	ret = imx615_init_controls(sensor);
	if (ret) {
		dev_err_probe(sensor->dev, ret, "failed to init controls: %d\n",
			      ret);
		goto error_power_off;
	}

	sensor->sd.internal_ops = &imx615_internal_ops;
	sensor->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;
	sensor->pad.flags = MEDIA_PAD_FL_SOURCE;
	sensor->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;

	ret = media_entity_pads_init(&sensor->sd.entity, 1, &sensor->pad);
	if (ret) {
		dev_err_probe(sensor->dev, ret,
			      "failed to init entity pads: %d\n", ret);
		goto error_v4l2_ctrl_handler_free;
	}

	sensor->sd.state_lock = sensor->ctrl_handler.lock;
	ret = v4l2_subdev_init_finalize(&sensor->sd);
	if (ret < 0) {
		dev_err_probe(sensor->dev, ret, "failed to init subdev: %d\n",
			      ret);
		goto error_media_entity_pm;
	}

	pm_runtime_set_active(sensor->dev);
	pm_runtime_enable(sensor->dev);

	ret = v4l2_async_register_subdev_sensor(&sensor->sd);
	if (ret < 0)
		goto error_v4l2_subdev_cleanup;

	pm_runtime_idle(sensor->dev);

	return 0;

error_v4l2_subdev_cleanup:
	pm_runtime_disable(sensor->dev);
	pm_runtime_set_suspended(sensor->dev);
	v4l2_subdev_cleanup(&sensor->sd);

error_media_entity_pm:
	media_entity_cleanup(&sensor->sd.entity);

error_v4l2_ctrl_handler_free:
	v4l2_ctrl_handler_free(sensor->sd.ctrl_handler);

error_power_off:
	imx615_power_off(sensor->dev);

	return ret;
}

static void imx615_remove(struct i2c_client *client)
{
	struct v4l2_subdev *sd = i2c_get_clientdata(client);

	v4l2_async_unregister_subdev(sd);
	v4l2_subdev_cleanup(sd);
	media_entity_cleanup(&sd->entity);
	v4l2_ctrl_handler_free(sd->ctrl_handler);

	pm_runtime_disable(&client->dev);

	if (!pm_runtime_status_suspended(&client->dev)) {
		imx615_power_off(&client->dev);
		pm_runtime_set_suspended(&client->dev);
	}
}

static DEFINE_RUNTIME_DEV_PM_OPS(imx615_pm_ops, imx615_power_off,
				 imx615_power_on, NULL);

static const struct of_device_id imx615_of_match[] = {
	{ .compatible = "sony,imx615" },
	{ }
};
MODULE_DEVICE_TABLE(of, imx615_of_match);

static struct i2c_driver imx615_i2c_driver = {
	.driver = {
		.name = "imx615",
		.of_match_table = imx615_of_match,
		.pm = pm_sleep_ptr(&imx615_pm_ops),
	},
	.probe = imx615_probe,
	.remove = imx615_remove,
};
module_i2c_driver(imx615_i2c_driver);

MODULE_AUTHOR("Jimmy Su <jimmy.su@intel.com>");
MODULE_AUTHOR("Serin Yeh <serin.yeh@intel.com>");
MODULE_AUTHOR("Kate Hsuan <hpa@redhat.com>");
MODULE_DESCRIPTION("Sony imx615 sensor driver");
MODULE_LICENSE("GPL");
