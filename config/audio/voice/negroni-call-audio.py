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

While the graphs are open, /run/negroni-call-audio.route selects the output.
"speaker" (the default) leaves both TFA9874 amplifiers enabled. "earpiece"
clears the amplifier-enable bit on the right-hand chip (I2C 0x35) so only the
left-hand chip (0x34) plays. Stock Android uses that same chip, with a
receiver DSP profile this driver does not load, as the handset. The driver
turns both amplifiers on when the stream starts and off when it stops, so the
switch is applied after the graphs start and does not persist into later
media playback.
"""

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

HELPER = Path(__file__).resolve().with_name("negroni-voice-test.py")
VOICE_STATES = frozenset(("ringing-out", "active"))
OUTPUTS = frozenset(("speaker", "earpiece"))
CALL_PATH = re.compile(r"/org/freedesktop/ModemManager1/Call/\d+")
STATE_LINE = re.compile(r"^call\.properties\.state\s*:\s*(\S+)", re.M)
WATCH = ("dbus-monitor", "--system",
  "type='signal',sender='org.freedesktop.ModemManager1'")
ROUTE_FILE = Path("/run/negroni-call-audio.route")
# Stock handset is TFA chip selector 1 (left, 0x34, receiver profile).
# Speakerphone is selector 3 (both chips). SYS_CTRL0 bit 3 is the amp enable.
TFA_BUS = "/dev/i2c-2"
TFA_LEFT, TFA_RIGHT = 0x34, 0x35
TFA_SYS_CTRL0 = 0x00
TFA_AMPE = 1 << 3


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


class LinuxI2C:
    """Big-endian 8/16-bit register access, matching the tfa987x regmap."""

    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)
        self._msg, self._data, self._ioctl = self._layouts()

    def close(self):
        os.close(self.fd)

    @staticmethod
    def _layouts():
        class Msg(ctypes.Structure):
            _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                        ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]

        class Data(ctypes.Structure):
            _fields_ = [("msgs", ctypes.c_void_p), ("nmsgs", ctypes.c_uint32)]

        if ctypes.sizeof(Msg) != 16:
            raise OSError(f"unexpected i2c_msg size {ctypes.sizeof(Msg)}")
        ioctl = ctypes.CDLL("libc.so.6", use_errno=True).ioctl
        ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
        ioctl.restype = ctypes.c_int
        return Msg, Data, ioctl

    def _xfer(self, addr, outgoing, incoming):
        """Send `outgoing` then, when `incoming` is not None, read that many bytes."""
        write_buf = ctypes.create_string_buffer(len(outgoing))
        write_buf.raw = outgoing
        count = 2 if incoming is not None else 1
        msgs = (self._msg * count)()
        msgs[0].addr, msgs[0].flags, msgs[0].len = addr, 0, len(outgoing)
        msgs[0].buf = ctypes.addressof(write_buf)
        read_buf = None
        if incoming is not None:
            read_buf = ctypes.create_string_buffer(incoming)
            msgs[1].addr, msgs[1].flags, msgs[1].len = addr, 1, incoming
            msgs[1].buf = ctypes.addressof(read_buf)
        data = self._data(ctypes.addressof(msgs), count)
        if self._ioctl(self.fd, 0x0707, ctypes.byref(data)) < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return None if read_buf is None else read_buf.raw

    def read(self, addr, reg):
        raw = self._xfer(addr, bytes([reg]), 2)
        return (raw[0] << 8) | raw[1]

    def write(self, addr, reg, value):
        self._xfer(addr, bytes((reg, value >> 8, value & 0xFF)), None)


class AmpRoute:
    """Enable both TFA9874 amps, or only the left one used as the earpiece."""

    def __init__(self, bus, left=TFA_LEFT, right=TFA_RIGHT):
        self.bus, self.left, self.right = bus, left, right

    def apply(self, mode):
        if mode not in OUTPUTS:
            raise ValueError(mode)
        self._enable(self.left, True)
        self._enable(self.right, mode == "speaker")

    def _enable(self, addr, enabled):
        value = self.bus.read(addr, TFA_SYS_CTRL0)
        updated = (value | TFA_AMPE) if enabled else (value & ~TFA_AMPE)
        if updated != value:
            self.bus.write(addr, TFA_SYS_CTRL0, updated)


def read_route(path, current="speaker"):
    """Return a valid output name from `path`, or `current` when it is unusable."""
    try:
        text = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return current
    return text if text in OUTPUTS else current


def publish_route_file(path):
    """Create the route file so a user in the audio group can switch outputs."""
    if not path.exists():
        path.write_text("speaker\n", encoding="utf-8")
    try:
        os.chmod(path, 0o664)
        import grp
        os.chown(path, 0, grp.getgrnam("audio").gr_gid)
    except (AttributeError, ImportError, KeyError, OSError, PermissionError):
        pass


def open_amp_route(path=TFA_BUS):
    try:
        return AmpRoute(LinuxI2C(path))
    except OSError as exc:
        log(f"earpiece switch unavailable: {exc}")
        return None


class Session:
    """One opened pair of voice graphs; close() restores the mixer."""

    def __init__(self, voice, alsa, mixer, card, rx, tx, routes=None, output=None):
        self.alsa = alsa
        self.opened = []
        self.transaction = voice.MixerTransaction(mixer, voice.ROUTES if routes is None else routes)
        self.card, self.rx, self.tx = card, rx, tx
        self.output = output
        # The driver enables both amplifiers as the stream starts.
        self.route = "speaker"

    def set_route(self, route):
        """Switch the playing amplifiers. The route is recorded only after it sticks."""
        if route not in OUTPUTS:
            raise ValueError(route)
        if self.output is None:
            raise RuntimeError("amplifier route is unavailable")
        if self.opened:
            self.output.apply(route)
        self.route = route

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


def make_session(voice, busy=card_busy, wait=time.sleep, idle_timeout=8.0, output=None):
    card, rx, tx = voice.find_pcms()
    waited = 0.0
    while busy(card) and waited < idle_timeout:
        wait(0.25)
        waited += 0.25
    still = busy(card)
    if still:
        log(f"card still busy after {idle_timeout:g}s, opening anyway: {still}")
    return Session(voice, voice.Alsa(), voice.Mixer(card), card, rx, tx, output=output)


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
    def __init__(self, states, factory, wait, retry_delay=2.0, poll=1.0, desktop=None,
                 route_path=None):
        self.states = states
        self.factory = factory
        self.wait = wait
        self.retry_delay = retry_delay
        self.poll = poll
        self.session = None
        self.desktop = desktop
        self.route_path = route_path
        self.route_error = None

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

    def apply_route(self):
        """Follow the route file without reopening the voice graphs."""
        if self.session is None or self.route_path is None:
            return
        route = read_route(self.route_path, self.session.route)
        if route == self.session.route:
            self.route_error = None
            return
        try:
            self.session.set_route(route)
        except Exception as exc:
            message = f"could not switch call output to {route}: {exc}"
            if message != self.route_error:
                log(message)
                self.route_error = message
            return
        self.route_error = None
        log(f"call output: {route}")

    def step(self):
        """Reconcile with the current calls; return seconds until the next look,
        or None when idle and only a ModemManager signal needs to wake us."""
        if not wants_voice(self.states()):
            self.close()
            return None
        if self.session is None and not self.open():
            return self.retry_delay
        self.apply_route()
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
    parser.add_argument("--route", choices=sorted(OUTPUTS),
                        help="ask the running service to use this output")
    args = parser.parse_args()
    if args.route:
        try:
            if not ROUTE_FILE.exists():
                publish_route_file(ROUTE_FILE)
            ROUTE_FILE.write_text(args.route + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"cannot write {ROUTE_FILE}: {exc}", file=sys.stderr)
            return 1
        print(f"call output requested: {args.route}")
        return 0
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
    publish_route_file(ROUTE_FILE)
    output = open_amp_route()
    daemon = Daemon(call_states, lambda: make_session(voice, output=output), stopped.wait,
                    desktop=desktop, route_path=ROUTE_FILE)
    log(f"waiting for calls; output file {ROUTE_FILE}")
    daemon.run(stopped, wake)
    return 0


if __name__ == "__main__":
    sys.exit(main())
