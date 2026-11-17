#!/usr/bin/env python3
"""Check that the GPS tile reflects ModemManager's enabled sources only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CONTROL = Path(__file__).resolve().parents[1] / "config/quicksettings/negroni-hardware-control"


class GpsQuickSettingTests(unittest.TestCase):
    def status(self, enabled="", capabilities="gps-raw\ngps-nmea", fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mmcli = root / "mmcli"
            mmcli.write_text("#!/bin/sh\ncat \"$GPS_FIXTURE\"\n" if not fail else "#!/bin/sh\nexit 1\n")
            mmcli.chmod(0o755)
            fixture = root / "status"
            lines = [f"modem.location.capabilities.value[{i}] : {name}"
                     for i, name in enumerate(capabilities.splitlines(), 1)]
            lines += [f"modem.location.enabled.value[{i}] : {name}"
                      for i, name in enumerate(enabled.splitlines(), 1)]
            fixture.write_text("\n".join(lines) + "\n")
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", GPS_FIXTURE=str(fixture))
            result = subprocess.run(["sh", str(CONTROL), "gps", "status"], capture_output=True,
                                    text=True, check=True, env=env)
            return result.stdout.strip()

    def test_only_cellular_location_is_off(self):
        self.assertEqual(self.status("3gpp-lac-ci\ncdma-bs"), "off")

    def test_either_gps_source_is_on(self):
        self.assertEqual(self.status("gps-nmea"), "on")
        self.assertEqual(self.status("gps-raw"), "on")

    def test_missing_modem_or_gps_capability_is_unavailable(self):
        self.assertEqual(self.status(fail=True), "unavailable")
        self.assertEqual(self.status(capabilities="3gpp-lac-ci"), "unavailable")


if __name__ == "__main__":
    unittest.main()
