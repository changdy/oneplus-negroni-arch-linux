#!/usr/bin/env python3
"""Exercise offline boot restoration and PMIC counter reset guards."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "config/rtc/negroni-rtc-clock"
loader = importlib.machinery.SourceFileLoader("negroni_rtc_clock", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
clock = importlib.util.module_from_spec(spec)
loader.exec_module(clock)


class RTCClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.rtc = root / "since_epoch"
        self.rtc.write_text("72000\n")
        self.state = root / "state.json"
        self.marker = root / "synchronized"
        self.marker.touch()
        self.unix = 1794897000

    def save(self):
        return clock.save(self.state, self.rtc, self.marker, now=lambda: self.unix)

    def test_offline_boot_advances_from_pmic_counter(self):
        data = self.save()
        self.rtc.write_text("75600\n")
        restored = []
        self.assertTrue(clock.restore(self.state, self.rtc, now=lambda: 67200,
                                      set_clock=lambda ident, value: restored.append(value)))
        self.assertEqual(restored, [self.unix + 3600])
        self.assertEqual(clock.read_state(self.state), data)

    def test_counter_reset_rejects_stale_offset(self):
        self.save()
        self.rtc.write_text("100\n")
        self.assertFalse(clock.restore(self.state, self.rtc, now=lambda: 67200,
                                       set_clock=lambda *_: self.fail("clock set")))

    def test_existing_good_system_time_is_preserved(self):
        self.save()
        self.assertFalse(clock.restore(self.state, self.rtc, now=lambda: self.unix + 10,
                                       set_clock=lambda *_: self.fail("clock set")))

    def test_unsynchronized_time_cannot_be_saved(self):
        self.marker.unlink()
        with self.assertRaisesRegex(RuntimeError, "not synchronized"):
            self.save()
        self.assertFalse(self.state.exists())

    def test_corrupt_offset_is_rejected(self):
        self.save()
        data = json.loads(self.state.read_text())
        data["offset_seconds"] += 86400
        self.state.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            clock.restore(self.state, self.rtc, now=lambda: 67200)


if __name__ == "__main__":
    unittest.main()
