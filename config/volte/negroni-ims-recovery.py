#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep the IMS data bearer for VoLTE up on the OnePlus 10 Pro (negroni).

81voltd logs a failed Connect() and then stays alive. The modem asks for its
IMS connection only once, when the QMI service appears, so a failed first
attempt (in practice "call-already-present" after a reboot) leaves VoLTE
unusable until somebody restarts the service by hand.

This watches the *result* in ModemManager instead of guessing from a daemon
log, and recovers in two stages:

  1. restart negroni-81voltd.service, so the modem asks again;
  2. if the bearer is still missing, restart ModemManager.service, which
     clears the stale call state that makes the modem answer
     "call-already-present".

Stage 2 reconnects mobile data and interrupts calls. It is opt-out, rate
limited, capped per boot, and only used while another data bearer is up.

Run with --check for a read-only, one-shot status report.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = "/etc/negroni-ims-recovery.conf"
VOLTD_UNIT = "negroni-81voltd.service"
MM_UNIT = "ModemManager.service"
READY_STATES = ("registered", "connected")

DEFAULTS = {
    "CHECK_INTERVAL": 15,
    "FAILURES_BEFORE_RESTART": 2,
    "RESTART_COOLDOWN": 30,
    "MM_RESTART_AFTER": 6,
    "ALLOW_MODEMMANAGER_RESTART": 1,
    "MM_RESTART_COOLDOWN": 300,
    "MAX_MODEMMANAGER_RESTARTS": 2,
}

LIMITS = {
    "CHECK_INTERVAL": (1, 3600),
    "FAILURES_BEFORE_RESTART": (1, 100),
    "RESTART_COOLDOWN": (0, 3600),
    "MM_RESTART_AFTER": (1, 100),
    "ALLOW_MODEMMANAGER_RESTART": (0, 1),
    "MM_RESTART_COOLDOWN": (0, 86400),
    "MAX_MODEMMANAGER_RESTARTS": (0, 100),
}


def log(message):
    print(message, flush=True)


def load_config(path=CONFIG_PATH):
    """Read KEY=VALUE overrides; unknown keys and bad values are errors."""
    values = dict(DEFAULTS)
    source = Path(path)
    text = source.read_text() if source.exists() else ""
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or key not in DEFAULTS:
            raise ValueError(f"{path}:{lineno}: unknown setting {key!r}")
        try:
            values[key] = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{path}:{lineno}: {key} must be an integer") from exc
    for key, (low, high) in LIMITS.items():
        if not low <= values[key] <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
    if values["MM_RESTART_AFTER"] < values["FAILURES_BEFORE_RESTART"]:
        raise ValueError("MM_RESTART_AFTER must not be below FAILURES_BEFORE_RESTART")
    return values


def run_mmcli(*args, timeout=10):
    result = subprocess.run(
        ["mmcli", *args, "-K"], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"mmcli {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def run_systemctl(action, unit, timeout=30):
    result = subprocess.run(
        ["systemctl", action, unit], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"systemctl {action} {unit} failed: {result.stderr.strip()}")
    return result.stdout


def parse_keyvalue(text):
    """Parse mmcli -K output into a dict of stripped key/value strings."""
    values = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class Probe:
    state: str
    ims_connected: bool
    any_connected: bool
    bearer_count: int


def probe(mmcli=run_mmcli):
    modem = parse_keyvalue(mmcli("-m", "any"))
    paths = [
        value for key, value in modem.items()
        if key.startswith("modem.generic.bearers.value[")
    ]
    ims_connected = False
    any_connected = False
    for path in paths:
        bearer = parse_keyvalue(mmcli("-b", path))
        connected = bearer.get("bearer.status.connected") == "yes"
        any_connected = any_connected or connected
        if bearer.get("bearer.properties.apn", "").strip().lower() == "ims":
            ims_connected = ims_connected or connected
    return Probe(modem.get("modem.generic.state", ""), ims_connected,
                 any_connected, len(paths))


class Recovery:
    def __init__(self, config, *, mmcli=run_mmcli, systemctl=run_systemctl,
                 clock=time.monotonic, log=log):
        self.config = config
        self._mmcli = mmcli
        self._systemctl = systemctl
        self._clock = clock
        self._log = log
        self.failures = 0
        self.mm_restarts = 0
        self.last_voltd_restart = None
        self.last_mm_restart = None

    def _cooled(self, last, seconds, now):
        return last is None or now - last >= seconds

    def step(self, current):
        """Decide one recovery action for a single probe result."""
        if current.state not in READY_STATES:
            if self.failures:
                self._log(f"modem is {current.state or 'unknown'}, waiting")
            self.failures = 0
            return None

        if current.ims_connected:
            if self.failures:
                self._log(f"IMS bearer recovered after {self.failures} failed checks")
            self.failures = 0
            return None

        self.failures += 1
        now = self._clock()
        cfg = self.config

        # One action per check: restarting ModemManager already restarts
        # 81voltd through BindsTo, so doing both in one round is wasteful.
        mm_allowed = (cfg["ALLOW_MODEMMANAGER_RESTART"] == 1
                      and self.failures >= cfg["MM_RESTART_AFTER"]
                      and current.any_connected
                      and self.mm_restarts < cfg["MAX_MODEMMANAGER_RESTARTS"]
                      and self._cooled(self.last_mm_restart,
                                       cfg["MM_RESTART_COOLDOWN"], now))
        if mm_allowed:
            self._systemctl("restart", MM_UNIT)
            self.last_mm_restart = now
            self.mm_restarts += 1
            self.failures = 0
            self._log(f"IMS bearer still missing after {VOLTD_UNIT} restarts, "
                      f"restarting {MM_UNIT} ({self.mm_restarts}/"
                      f"{cfg['MAX_MODEMMANAGER_RESTARTS']})")
            return MM_UNIT

        if (self.failures >= cfg["FAILURES_BEFORE_RESTART"]
                and self._cooled(self.last_voltd_restart,
                                 cfg["RESTART_COOLDOWN"], now)):
            self._systemctl("restart", VOLTD_UNIT)
            self.last_voltd_restart = now
            self._log(f"IMS bearer missing for {self.failures} checks, "
                      f"restarting {VOLTD_UNIT}")
            return VOLTD_UNIT

        if self.failures == 1 or self.failures % 10 == 0:
            self._log(f"IMS bearer missing, {self.failures} consecutive checks, "
                      "no action yet")
        return None

    def run(self):
        interval = self.config["CHECK_INTERVAL"]
        while True:
            try:
                current = probe(self._mmcli)
            except Exception as exc:
                self._log(f"probe failed, will retry: {exc}")
            else:
                try:
                    self.step(current)
                except Exception as exc:
                    self._log(f"recovery action failed, will retry: {exc}")
            time.sleep(interval)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv not in ([], ["--check"]):
        print(f"Usage: {Path(__file__).name} [--check]", file=sys.stderr)
        return 2
    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    if argv == ["--check"]:
        try:
            current = probe()
        except Exception as exc:
            print(f"probe failed: {exc}", file=sys.stderr)
            return 1
        print(f"modem state: {current.state or 'unknown'}; "
              f"bearers: {current.bearer_count}; "
              f"IMS bearer: {'up' if current.ims_connected else 'down'}")
        return 0 if current.ims_connected else 1
    recovery = Recovery(config)
    log(f"watching IMS bearer every {config['CHECK_INTERVAL']}s")
    recovery.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
