#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Open the experimental MM5/MM6 voice graphs while a ModemManager call is up.

Experimental. Needs the matching kernel modules and OnePlus voice topology and
runs as root next to negroni-voice-test.py, whose PCM and mixer helpers it
reuses. It never dials, answers, hangs up, records or writes PCM samples.

The graphs are opened when a call is ringing-out or active and closed, with
every changed mixer value restored, when no such call is left. Other sound
desktop sound servers are asked to let go of the card for the duration: their
PipeWire/PulseAudio card profile is switched to "off" and put back afterwards,
because a media stream opened on the shared speaker back end during a call
stalls and the microphone source disappears. Remaining clients get a short
time to release the card first (the ringtone).
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

HELPER = Path(__file__).resolve().with_name("negroni-voice-test.py")
VOICE_STATES = frozenset(("ringing-out", "active"))
CALL_PATH = re.compile(r"/org/freedesktop/ModemManager1/Call/\d+")
STATE_LINE = re.compile(r"^call\.properties\.state\s*:\s*(\S+)", re.M)
WATCH = ("dbus-monitor", "--system",
  "type='signal',sender='org.freedesktop.ModemManager1'")


def load_helper(path=HELPER):
    spec = importlib.util.spec_from_file_location("negroni_voice_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def log(message):
    print(message, flush=True)


def mmcli(*args):
    result = subprocess.run(("mmcli",) + args, capture_output=True, text=True, timeout=10)
    return result.stdout if result.returncode == 0 else ""


def call_states(run=mmcli):
    """Return the state of every call ModemManager currently lists."""
    paths = sorted(set(CALL_PATH.findall(run("-m", "any", "--voice-list-calls"))))
    found = [STATE_LINE.search(run("-o", path, "-K")) for path in paths]
    return [match.group(1) for match in found if match]


def wants_voice(states):
    return any(state in VOICE_STATES for state in states)


class Session:
    """One opened pair of voice graphs; close() restores the mixer."""

    def __init__(self, voice, alsa, mixer, card, rx, tx, routes=None):
        self.alsa = alsa
        self.opened = []
        self.transaction = voice.MixerTransaction(mixer, voice.ROUTES if routes is None else routes)
        self.card, self.rx, self.tx = card, rx, tx

    def open(self):
        self.transaction.apply()
        # Both graphs must exist before their backends prepare. RX carries VSID.
        tx = self.alsa.open(f"hw:{self.card},{self.tx}", capture=True)
        self.opened.append(tx)
        rx = self.alsa.open(f"hw:{self.card},{self.rx}", capture=False)
        self.opened.append(rx)
        self.alsa.start(rx, capture=False)
        self.alsa.start(tx, capture=True)

    def close(self):
        errors = []
        # TX before RX, preserving the VSID while TX is torn down.
        for pcm in self.opened:
            try:
                self.alsa.close(pcm)
            except Exception as exc:
                errors.append(f"close PCM: {exc}")
        self.opened = []
        errors.extend(self.transaction.restore())
        return errors


def card_busy(card, proc=Path("/proc/asound")):
    statuses = (proc / f"card{card}").glob("pcm*/sub*/status")
    return [str(path) for path in statuses if path.read_text().strip() != "closed"]


def make_session(voice, busy=card_busy, wait=time.sleep, idle_timeout=8.0):
    card, rx, tx = voice.find_pcms()
    waited = 0.0
    while busy(card) and waited < idle_timeout:
        wait(0.25)
        waited += 0.25
    still = busy(card)
    if still:
        log(f"card still busy after {idle_timeout:g}s, opening anyway: {still}")
    return Session(voice, voice.Alsa(), voice.Mixer(card), card, rx, tx)


CARD_BLOCK = re.compile(r"^Card #", re.M)
CARD_NAME = re.compile(r"^\s*Name:\s*(\S+)", re.M)
CARD_ALSA = re.compile(r'^\s*alsa\.card\s*=\s*"(\d+)"', re.M)
CARD_PROFILE = re.compile(r"^\s*Active Profile:\s*(.+?)\s*$", re.M)
STATE_FILE = Path("/run/negroni-call-audio.json")


def parse_cards(text, card):
    """Return (name, active profile) of sound-server cards backed by ALSA `card`."""
    blocks = CARD_BLOCK.split(text)[1:]
    fields = [(CARD_NAME.search(b), CARD_ALSA.search(b), CARD_PROFILE.search(b)) for b in blocks]
    return [(n.group(1), p.group(1)) for n, a, p in fields
        if n and a and p and int(a.group(1)) == card]


def sound_sessions(runtime=Path("/run/user")):
    """User ids that have a PulseAudio-compatible socket (pipewire-pulse)."""
    if not runtime.is_dir():
        return []
    return sorted(int(p.name) for p in runtime.iterdir()
        if p.name.isdigit() and (p / "pulse/native").exists())


def pactl(uid, *args):
    import pwd  # POSIX only; kept local so the host tests also load elsewhere
    user = pwd.getpwuid(uid).pw_name
    command = ("runuser", "-u", user, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}", "pactl") + args
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pactl exited {result.returncode}")
    return result.stdout


class Desktop:
    """Takes the card away from desktop sound servers and gives it back."""

    def __init__(self, card, run=pactl, sessions=sound_sessions, state=STATE_FILE):
        self.card = card
        self.run = run
        self.sessions = sessions
        self.state = state
        self.saved = None

    def recover(self):
        """Give back profiles left off by an earlier instance that died."""
        if not self.state.exists():
            return
        try:
            self.saved = [tuple(item) for item in json.loads(self.state.read_text())]
        except (OSError, ValueError) as exc:
            log(f"ignoring unreadable {self.state}: {exc}")
            self.saved = []
        self.restore()

    def release_one(self, uid):
        saved = []
        for name, profile in parse_cards(self.run(uid, "list", "cards"), self.card):
            if profile != "off":
                self.run(uid, "set-card-profile", name, "off")
                saved.append((uid, name, profile))
        return saved

    def release(self):
        if self.saved is not None:
            return
        saved = []
        for uid in self.sessions():
            try:
                saved.extend(self.release_one(uid))
            except Exception as exc:
                log(f"could not release the card from uid {uid}: {exc}")
        self.saved = saved
        try:
            self.state.write_text(json.dumps(saved))
        except OSError as exc:
            log(f"could not record released profiles: {exc}")
        log(f"desktop sound released: {saved}")

    def restore(self):
        if self.saved is None:
            return
        for uid, name, profile in self.saved:
            try:
                self.run(uid, "set-card-profile", name, profile)
            except Exception as exc:
                log(f"could not restore {name} to {profile!r} for uid {uid}: {exc}")
        log(f"desktop sound restored: {self.saved}")
        self.saved = None
        try:
            self.state.unlink(missing_ok=True)
        except OSError as exc:
            log(f"could not remove {self.state}: {exc}")


class Daemon:
    def __init__(self, states, factory, wait, retry_delay=2.0, poll=1.0, desktop=None):
        self.states = states
        self.factory = factory
        self.wait = wait
        self.retry_delay = retry_delay
        self.poll = poll
        self.session = None
        self.desktop = desktop

    def close(self):
        session, self.session = self.session, None
        if session is not None:
            errors = session.close()
            log("voice graphs closed" + (f"; cleanup errors: {errors}" if errors else ""))
        if self.desktop is not None:
            self.desktop.restore()

    def open(self):
        if self.desktop is not None:
            self.desktop.release()
        session = self.factory()
        try:
            session.open()
        except Exception as exc:
            errors = session.close()
            log(f"opening voice graphs failed: {exc}; cleanup errors: {errors}")
            return False
        self.session = session
        log("voice graphs open")
        return True

    def step(self):
        """Reconcile with the current calls; return seconds until the next look,
        or None when idle and only a ModemManager signal needs to wake us."""
        if not wants_voice(self.states()):
            self.close()
            return None
        if self.session is None and not self.open():
            return self.retry_delay
        return self.poll

    def run(self, stopped, wake):
        try:
            while not stopped.is_set():
                delay = self.step()
                wake.clear()
                if delay is None:
                    wake.wait(30.0)
                else:
                    self.wait(delay)
        finally:
            self.close()


def watch_signals(wake, stopped, command=WATCH):
    """Set `wake` whenever ModemManager emits a D-Bus signal."""
    while not stopped.is_set():
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        except OSError as exc:
            log(f"cannot start dbus-monitor ({exc}); polling every 30s only")
            return
        for line in process.stdout:
            if line.startswith("signal"):
                wake.set()
            if stopped.is_set():
                break
        process.kill()
        process.wait()
        stopped.wait(2.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="print call states and exit")
    args = parser.parse_args()
    if args.once:
        states = call_states()
        print(f"calls: {states}; voice wanted: {wants_voice(states)}")
        return 0
    voice = load_helper()
    stopped, wake = threading.Event(), threading.Event()

    def stop(_signum, _frame):
        stopped.set()
        wake.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    threading.Thread(target=watch_signals, args=(wake, stopped), daemon=True).start()
    desktop = Desktop(voice.find_pcms()[0])
    desktop.recover()
    daemon = Daemon(call_states, lambda: make_session(voice), stopped.wait, desktop=desktop)
    log("waiting for calls")
    daemon.run(stopped, wake)
    return 0


if __name__ == "__main__":
    sys.exit(main())
