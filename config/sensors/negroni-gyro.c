/*
 * Publish the ICM-4x6xx gyroscope that the SLPI already streams.
 *
 * libssc delivers angular velocity in rad/s. Its command-line text says m/s;
 * that label is copied from the accelerometer and does not match the magnitude
 * of a stationary sample (about 0.01, a rad/s bias).
 *
 * The chip's +X/+Y point opposite the panel, the same orientation already
 * confirmed for the accelerometer. panel_from_chip negates X and Y and keeps Z.
 * A hand rotation of the gyroscope axes has not been checked on the device.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <glib.h>
#include <glib-unix.h>
#include <libssc.h>

static const float panel_from_chip[3][3] = {
	{-1.0f, 0.0f, 0.0f},
	{0.0f, -1.0f, 0.0f},
	{0.0f, 0.0f, 1.0f},
};

static const char gyro_path[] = "/run/negroni/gyro";
static const char gyro_tmp[] = "/run/negroni/gyro.tmp";

static GMutex sample_lock;
static GCond sample_cond;
static gboolean saw_sample;
static float latest_x;
static float latest_y;
static float latest_z;
static gboolean daemon_mode;
static GMainLoop *main_loop;
static SSCSensorGyroscope *gyro_sensor;

static void chip_to_panel(float x, float y, float z, float *ox, float *oy, float *oz)
{
	*ox = panel_from_chip[0][0] * x + panel_from_chip[0][1] * y + panel_from_chip[0][2] * z;
	*oy = panel_from_chip[1][0] * x + panel_from_chip[1][1] * y + panel_from_chip[1][2] * z;
	*oz = panel_from_chip[2][0] * x + panel_from_chip[2][1] * y + panel_from_chip[2][2] * z;
}

static void write_sample(float x, float y, float z)
{
	char body[128];
	int fd;
	int length;

	if (mkdir("/run/negroni", 0755) < 0 && errno != EEXIST)
		return;
	length = snprintf(body, sizeof body, "%.6f %.6f %.6f\n", x, y, z);
	if (length < 0 || (size_t)length >= sizeof body)
		return;
	fd = open(gyro_tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0)
		return;
	if (write(fd, body, (size_t)length) == length) {
		if (close(fd) == 0)
			rename(gyro_tmp, gyro_path);
	} else {
		close(fd);
	}
}

static void on_measurement(SSCSensorGyroscope *sensor, gfloat x, gfloat y, gfloat z, gpointer user_data)
{
	float px, py, pz;

	(void)sensor;
	(void)user_data;
	chip_to_panel(x, y, z, &px, &py, &pz);
	g_mutex_lock(&sample_lock);
	latest_x = px;
	latest_y = py;
	latest_z = pz;
	saw_sample = TRUE;
	g_cond_signal(&sample_cond);
	g_mutex_unlock(&sample_lock);
	if (daemon_mode)
		write_sample(px, py, pz);
	else if (main_loop)
		g_main_loop_quit(main_loop);
}

static gboolean once_timeout(gpointer user_data)
{
	(void)user_data;
	if (main_loop)
		g_main_loop_quit(main_loop);
	return G_SOURCE_REMOVE;
}

static gpointer watchdog(gpointer user_data)
{
	int i;

	(void)user_data;
	for (i = 0; i < 150; i++) {
		g_mutex_lock(&sample_lock);
		if (saw_sample) {
			g_mutex_unlock(&sample_lock);
			return NULL;
		}
		g_mutex_unlock(&sample_lock);
		g_usleep(100 * 1000);
	}
	g_printerr("negroni-gyro: no gyroscope sample within 15 seconds\n");
	_exit(1);
}

static gboolean on_unix_signal(gpointer user_data)
{
	(void)user_data;
	if (main_loop)
		g_main_loop_quit(main_loop);
	return G_SOURCE_REMOVE;
}

static void on_method(GDBusConnection *connection, const gchar *sender,
		const gchar *object_path, const gchar *interface_name,
		const gchar *method_name, GVariant *parameters,
		GDBusMethodInvocation *invocation, gpointer user_data)
{
	float x, y, z;
	gboolean ready;

	(void)connection;
	(void)sender;
	(void)object_path;
	(void)interface_name;
	(void)method_name;
	(void)parameters;
	(void)user_data;
	g_mutex_lock(&sample_lock);
	ready = saw_sample;
	x = latest_x;
	y = latest_y;
	z = latest_z;
	g_mutex_unlock(&sample_lock);
	if (!ready) {
		g_dbus_method_invocation_return_error(invocation, G_IO_ERROR,
			G_IO_ERROR_NOT_INITIALIZED, "gyroscope has no sample yet");
		return;
	}
	g_dbus_method_invocation_return_value(invocation,
		g_variant_new("(ddd)", (double)x, (double)y, (double)z));
}

static GVariant *on_get_property(GDBusConnection *connection, const gchar *sender,
		const gchar *object_path, const gchar *interface_name,
		const gchar *property_name, GError **error, gpointer user_data)
{
	float value;
	gboolean ready;
	gboolean known = TRUE;

	(void)connection;
	(void)sender;
	(void)object_path;
	(void)interface_name;
	(void)user_data;
	g_mutex_lock(&sample_lock);
	ready = saw_sample;
	if (g_strcmp0(property_name, "AngularVelocityX") == 0)
		value = latest_x;
	else if (g_strcmp0(property_name, "AngularVelocityY") == 0)
		value = latest_y;
	else if (g_strcmp0(property_name, "AngularVelocityZ") == 0)
		value = latest_z;
	else
		known = FALSE;
	g_mutex_unlock(&sample_lock);
	if (!known) {
		g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND, "unknown property");
		return NULL;
	}
	if (!ready) {
		g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_INITIALIZED,
			"gyroscope has no sample yet");
		return NULL;
	}
	return g_variant_new_double(value);
}

static const GDBusInterfaceVTable gyro_vtable = {
	.method_call = on_method,
	.get_property = on_get_property,
};

static const gchar introspection_xml[] =
	"<node>"
	"  <interface name='org.negroni.Gyroscope'>"
	"    <method name='GetAngularVelocity'>"
	"      <arg type='d' name='x' direction='out'/>"
	"      <arg type='d' name='y' direction='out'/>"
	"      <arg type='d' name='z' direction='out'/>"
	"    </method>"
	"    <property name='AngularVelocityX' type='d' access='read'/>"
	"    <property name='AngularVelocityY' type='d' access='read'/>"
	"    <property name='AngularVelocityZ' type='d' access='read'/>"
	"  </interface>"
	"</node>";

static void on_bus_acquired(GDBusConnection *connection, const gchar *name, gpointer user_data)
{
	g_autoptr(GError) error = NULL;
	GDBusNodeInfo *info = user_data;

	(void)name;
	if (g_dbus_connection_register_object(connection, "/org/negroni/Gyroscope",
			info->interfaces[0], &gyro_vtable, NULL, NULL, &error) == 0) {
		g_printerr("negroni-gyro: %s\n", error->message);
		g_main_loop_quit(main_loop);
	}
}

static void on_name_lost(GDBusConnection *connection, const gchar *name, gpointer user_data)
{
	(void)connection;
	(void)user_data;
	g_printerr("negroni-gyro: unable to own %s\n", name);
	if (main_loop)
		g_main_loop_quit(main_loop);
}

static int open_gyro(GError **error)
{
	gyro_sensor = ssc_sensor_gyroscope_new_sync(NULL, error);
	if (!gyro_sensor)
		return -1;
	g_signal_connect(gyro_sensor, "measurement", G_CALLBACK(on_measurement), NULL);
	if (!ssc_sensor_gyroscope_open_sync(gyro_sensor, NULL, error))
		return -1;
	return 0;
}

int main(int argc, char **argv)
{
	g_autoptr(GError) error = NULL;
	GThread *watch;

	daemon_mode = TRUE;
	if (argc == 2 && strcmp(argv[1], "--once") == 0)
		daemon_mode = FALSE;
	else if (argc != 1) {
		g_printerr("usage: negroni-gyro [--once]\n");
		return 2;
	}

	if (access("/dev/fastrpc-sdsp", F_OK) != 0) {
		g_printerr("negroni-gyro: /dev/fastrpc-sdsp is missing\n");
		return 1;
	}

	watch = g_thread_new("gyro-watchdog", watchdog, NULL);
	if (open_gyro(&error) < 0) {
		g_printerr("negroni-gyro: %s\n", error->message);
		return 1;
	}

	if (!daemon_mode) {
		gboolean ready;
		g_mutex_lock(&sample_lock);
		ready = saw_sample;
		g_mutex_unlock(&sample_lock);
		if (!ready) {
			main_loop = g_main_loop_new(NULL, FALSE);
			g_timeout_add_seconds(3, once_timeout, NULL);
			g_main_loop_run(main_loop);
		}
		g_mutex_lock(&sample_lock);
		ready = saw_sample;
		if (ready)
			printf("%.6f %.6f %.6f\n", latest_x, latest_y, latest_z);
		g_mutex_unlock(&sample_lock);
		ssc_sensor_gyroscope_close_sync(gyro_sensor, NULL, NULL);
		g_thread_join(watch);
		if (!ready) {
			g_printerr("negroni-gyro: sample was not delivered\n");
			return 1;
		}
		return 0;
	}

	{
		g_autoptr(GDBusNodeInfo) info = NULL;
		info = g_dbus_node_info_new_for_xml(introspection_xml, &error);
		if (!info) {
			g_printerr("negroni-gyro: %s\n", error->message);
			return 1;
		}
		main_loop = g_main_loop_new(NULL, FALSE);
		g_unix_signal_add(SIGTERM, on_unix_signal, NULL);
		g_unix_signal_add(SIGINT, on_unix_signal, NULL);
		g_bus_own_name(G_BUS_TYPE_SYSTEM, "org.negroni.Gyroscope",
			G_BUS_NAME_OWNER_FLAGS_NONE, on_bus_acquired, NULL, on_name_lost,
			info, NULL);
		g_main_loop_run(main_loop);
		ssc_sensor_gyroscope_close_sync(gyro_sensor, NULL, NULL);
		g_thread_join(watch);
		return 0;
	}
}
