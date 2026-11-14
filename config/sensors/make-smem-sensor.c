#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define REG_NUM 10
#define PARAMETER_NUM 25
#define FEATURE_NUM 10
#define SOURCE_NUM 2
#define ALGO_PARAMETER_NUM 15
#define ALGO_FEATURE_NUM 5
#define SENSORS_NUM 12
#define SENSOR_ALGO_NUM 8
#define DEFAULT_CONFIG 0xff

struct sensor_feature {
	int reg[REG_NUM];
	int parameter[PARAMETER_NUM];
	int feature[FEATURE_NUM];
};

struct sensor_hw {
	uint8_t sensor_name;
	uint8_t bus_number;
	uint8_t direction;
	uint8_t irq_number;
	struct sensor_feature feature;
};

struct sensor_vector {
	int sensor_id;
	struct sensor_hw hw[SOURCE_NUM];
};

struct sensor_algorithm {
	int sensor_id;
	int parameter[ALGO_PARAMETER_NUM];
	int feature[ALGO_FEATURE_NUM];
};

struct sensor_info {
	int magic_num;
	struct sensor_vector s_vector[SENSORS_NUM];
	struct sensor_algorithm a_vector[SENSOR_ALGO_NUM];
};

enum {
	OPLUS_LIGHT = 3,
	OPLUS_PROXIMITY = 4,
};

static void mark_registry(struct sensor_hw *hw)
{
	hw->sensor_name = 0;
	hw->bus_number = DEFAULT_CONFIG;
	hw->direction = DEFAULT_CONFIG;
	hw->irq_number = DEFAULT_CONFIG;
}

static void fill_light(struct sensor_hw *hw)
{
	mark_registry(hw);
	hw->sensor_name = 2; /* TCS3701 */
	hw->bus_number = 2;
	hw->irq_number = 14;
	hw->feature.feature[0] = 4;    /* als-type */
	hw->feature.feature[1] = 1;    /* is-unit-device */
	hw->feature.feature[2] = 1;    /* is-als-dri */
	hw->feature.feature[3] = 110;  /* als-factor */
	hw->feature.feature[4] = 0;    /* is_als_initialed */
	hw->feature.feature[5] = 8;    /* als_buffer_length */
	hw->feature.feature[6] = 1057; /* normalization_value */
	hw->feature.feature[7] = 0;    /* use_lb_algo */
	hw->feature.feature[8] = 2;    /* para-matrix */
	hw->feature.feature[9] = 0;    /* als_ratio_type */
	hw->feature.parameter[6] = 1001; /* gold-reset-scale default */
}

static void fill_proximity(struct sensor_hw *hw)
{
	static const int parameter[] = {
		300, 400, 400, 600, 100, 150, 1020, 500, 0, 600, 5, 400,
		100, 1500, 80, 1024, 20800, 250, -255, 255, 2000, 20, 80,
	};

	mark_registry(hw);
	hw->sensor_name = 2; /* TCS3701 */
	hw->bus_number = 2;
	hw->irq_number = 14;
	hw->feature.feature[0] = 1; /* ps-type */
	hw->feature.reg[0] = 2;
	hw->feature.reg[1] = 187;
	hw->feature.reg[2] = 0;
	memcpy(hw->feature.parameter, parameter, sizeof(parameter));
}

int main(void)
{
	struct sensor_info info;
	int sensor, source;

	if (sizeof(info) != 5140) {
		fprintf(stderr, "unexpected size %zu\n", sizeof(info));
		return 1;
	}

	memset(&info, 0, sizeof(info));
	for (sensor = 0; sensor < SENSORS_NUM; sensor++) {
		for (source = 0; source < SOURCE_NUM; source++)
			mark_registry(&info.s_vector[sensor].hw[source]);
	}

	info.s_vector[OPLUS_LIGHT].sensor_id = OPLUS_LIGHT;
	fill_light(&info.s_vector[OPLUS_LIGHT].hw[0]);
	info.s_vector[OPLUS_PROXIMITY].sensor_id = OPLUS_PROXIMITY;
	fill_proximity(&info.s_vector[OPLUS_PROXIMITY].hw[0]);

	if (fwrite(&info, 1, sizeof(info), stdout) != sizeof(info))
		return 1;
	return 0;
}
