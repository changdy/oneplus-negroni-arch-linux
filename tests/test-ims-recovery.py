#!/usr/bin/env python3
"""Offline tests for the IMS bearer recovery state machine."""
import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "config/volte/negroni-ims-recovery.py"
spec = importlib.util.spec_from_file_location("negroni_ims_recovery", MODULE_PATH)
recovery = importlib.util.module_from_spec(spec)
# dataclass resolves postponed annotations through sys.modules.
sys.modules[spec.name] = recovery
spec.loader.exec_module(recovery)


class Clock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make(**overrides):
    config = dict(recovery.DEFAULTS)
    config.update(overrides)
    actions = []
    logs = []
    clock = Clock()
    unit = recovery.Recovery(
        config,
        mmcli=lambda *args: "",
        systemctl=lambda action, name: actions.append((action, name)),
        clock=clock,
        log=logs.append,
    )
    return unit, actions, logs, clock


def down(state="connected", any_connected=True, bearers=1):
    return recovery.Probe(state, False, any_connected, bearers)


def up(state="connected"):
    return recovery.Probe(state, True, True, 2)


class StateMachineTests(unittest.TestCase):
    def test_healthy_bearer_takes_no_action(self):
        unit, actions, _, _ = make()
        self.assertIsNone(unit.step(up()))
        self.assertEqual(unit.failures, 0)
        self.assertEqual(actions, [])

    def test_modem_not_ready_is_ignored_and_resets_counter(self):
        unit, actions, _, _ = make()
        unit.failures = 3
        self.assertIsNone(unit.step(down(state="initializing")))
        self.assertEqual(unit.failures, 0)
        self.assertEqual(actions, [])

    def test_restarts_81voltd_after_two_failed_checks(self):
        unit, actions, _, clock = make(ALLOW_MODEMMANAGER_RESTART=0)
        self.assertIsNone(unit.step(down()))
        self.assertEqual(actions, [])
        self.assertEqual(unit.step(down()), recovery.VOLTD_UNIT)
        self.assertEqual(actions, [("restart", recovery.VOLTD_UNIT)])
        self.assertEqual(clock(), 1000.0)

    def test_81voltd_restarts_are_rate_limited(self):
        unit, actions, _, clock = make(ALLOW_MODEMMANAGER_RESTART=0)
        for _ in range(5):
            unit.step(down())
        self.assertEqual(actions, [("restart", recovery.VOLTD_UNIT)])
        clock.advance(30)
        unit.step(down())
        self.assertEqual(len(actions), 2)

    def test_persistent_failure_restarts_modemmanager(self):
        unit, actions, logs, clock = make()
        for _ in range(6):
            clock.advance(30)
            unit.step(down())
        self.assertIn(("restart", recovery.MM_UNIT), actions)
        self.assertEqual(unit.mm_restarts, 1)
        self.assertEqual(unit.failures, 0)
        self.assertTrue(any("restarting ModemManager.service" in line
                            for line in logs))

    def test_modemmanager_restart_can_be_disabled(self):
        unit, actions, _, clock = make(ALLOW_MODEMMANAGER_RESTART=0)
        for _ in range(10):
            clock.advance(30)
            unit.step(down())
        self.assertNotIn(("restart", recovery.MM_UNIT), actions)

    def test_modemmanager_restart_skipped_when_data_is_off(self):
        unit, actions, _, clock = make()
        for _ in range(10):
            clock.advance(30)
            unit.step(down(any_connected=False))
        self.assertNotIn(("restart", recovery.MM_UNIT), actions)

    def test_modemmanager_restarts_are_capped(self):
        unit, actions, _, clock = make(MAX_MODEMMANAGER_RESTARTS=1)
        for _ in range(6):
            clock.advance(30)
            unit.step(down())
        for _ in range(6):
            clock.advance(360)
            unit.step(down())
        mm_actions = [a for a in actions if a == ("restart", recovery.MM_UNIT)]
        self.assertEqual(len(mm_actions), 1)

    def test_recovery_resets_counter(self):
        unit, actions, logs, _ = make(ALLOW_MODEMMANAGER_RESTART=0)
        unit.step(down())
        unit.step(down())
        self.assertIsNone(unit.step(up()))
        self.assertEqual(unit.failures, 0)
        self.assertTrue(any("recovered" in line for line in logs))


class ParsingTests(unittest.TestCase):
    def test_parse_keyvalue_handles_mmcli_output(self):
        text = (
            "modem.generic.state                  : connected\n"
            "modem.generic.bearers.value[1]       : /org/freedesktop/ModemManager1/Bearer/1\n"
            "bearer.properties.apn                : IMS\n"
            "bearer.status.connected             : yes\n"
            "not-a-pair\n"
        )
        values = recovery.parse_keyvalue(text)
        self.assertEqual(values["modem.generic.state"], "connected")
        self.assertEqual(values["bearer.properties.apn"], "IMS")
        self.assertNotIn("not-a-pair", values)

    def test_probe_detects_ims_bearer(self):
        modem = (
            "modem.generic.state : connected\n"
            "modem.generic.bearers.value[1] : /org/freedesktop/ModemManager1/Bearer/0\n"
            "modem.generic.bearers.value[2] : /org/freedesktop/ModemManager1/Bearer/1\n"
        )
        bearers = {
            "/org/freedesktop/ModemManager1/Bearer/0":
                "bearer.properties.apn : ctnet\nbearer.status.connected : yes\n",
            "/org/freedesktop/ModemManager1/Bearer/1":
                "bearer.properties.apn : IMS\nbearer.status.connected : yes\n",
        }

        def fake_mmcli(*args):
            return modem if args[0] == "-m" else bearers[args[1]]

        result = recovery.probe(fake_mmcli)
        self.assertTrue(result.ims_connected)
        self.assertTrue(result.any_connected)
        self.assertEqual(result.bearer_count, 2)
        self.assertEqual(result.state, "connected")

        bearers["/org/freedesktop/ModemManager1/Bearer/1"] = (
            "bearer.properties.apn : IMS\nbearer.status.connected : no\n"
        )
        result = recovery.probe(fake_mmcli)
        self.assertFalse(result.ims_connected)
        self.assertTrue(result.any_connected)


class IntegrationTests(unittest.TestCase):
    def test_image_verification_covers_every_recovery_file(self):
        path = ROOT / "scripts/verify-volte-image.py"
        verify_spec = importlib.util.spec_from_file_location("verify_volte_image", path)
        verify = importlib.util.module_from_spec(verify_spec)
        sys.modules[verify_spec.name] = verify
        verify_spec.loader.exec_module(verify)
        self.assertEqual(verify.RECOVERY_UNIT, "negroni-ims-recovery.service")
        expected = {
            "/usr/local/libexec/negroni-ims-recovery.py":
                "config/volte/negroni-ims-recovery.py",
            "/etc/negroni-ims-recovery.conf":
                "config/volte/negroni-ims-recovery.conf",
            "/etc/systemd/system/negroni-ims-recovery.service":
                "config/systemd/negroni-ims-recovery.service",
        }
        for target, origin in expected.items():
            self.assertIn(target, verify.FILES)
            self.assertEqual(verify.FILES[target][0], origin)
        for origin, _mode in verify.FILES.values():
            self.assertTrue((ROOT / origin).is_file(), origin)

    def test_installer_and_check_cover_recovery(self):
        installer = (ROOT / "scripts/configure-volte.sh").read_text()
        for needle in (
            "config/volte/negroni-ims-recovery.py",
            "config/volte/negroni-ims-recovery.conf",
            "config/systemd/negroni-ims-recovery.service",
            "enable negroni-81voltd.service negroni-ims-recovery.service",
        ):
            self.assertIn(needle, installer)
        self.assertIn("tests/test-ims-recovery.py",
                      (ROOT / "scripts/check.sh").read_text())

    def test_build_chain_covers_fresh_and_existing_images(self):
        build = (ROOT / "build.sh").read_text()
        self.assertIn('sha256sum --check --status "$log_dir/volte-sources.sha256"',
                      build)
        self.assertIn("bash scripts/update-volte-image.sh", build)
        self.assertIn("scripts/configure-volte.sh",
                      (ROOT / "scripts/finalize-rootfs.sh").read_text())
        self.assertIn("scripts/verify-volte-image.py",
                      (ROOT / "scripts/pack-images.sh").read_text())


class ConfigTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recovery.conf"
            path.write_text(
                "# comment\n\nCHECK_INTERVAL=20\nALLOW_MODEMMANAGER_RESTART=0\n",
                encoding="utf-8",
            )
            config = recovery.load_config(path)
        self.assertEqual(config["CHECK_INTERVAL"], 20)
        self.assertEqual(config["ALLOW_MODEMMANAGER_RESTART"], 0)
        self.assertEqual(config["MAX_MODEMMANAGER_RESTARTS"], 2)

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = recovery.load_config(Path(tmp) / "absent.conf")
        self.assertEqual(config, recovery.DEFAULTS)

    def test_rejects_bad_settings(self):
        cases = [
            "NO_SUCH_KEY=1\n",
            "CHECK_INTERVAL=abc\n",
            "CHECK_INTERVAL=0\n",
            "FAILURES_BEFORE_RESTART=5\nMM_RESTART_AFTER=2\n",
        ]
        for text in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "recovery.conf"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    recovery.load_config(path)

    def test_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(recovery.main(["--bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
