#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Hostless PCM sequence based on royka1/diting-ubuntu's diting-voice-pcm
# (GPL-2.0), commit c68ff47db94792fb5fd608e98d1ae489c2e592b1:
# https://github.com/royka1/diting-ubuntu/blob/c68ff47db94792fb5fd608e98d1ae489c2e592b1/ubuntu-diting/packages/device-xiaomi-diting/src/diting-voice-pcm
"""Run the experimental MM5/MM6 voice graphs for a bounded manual test.

Requires the matching kernel patches and OnePlus voice topology. This does
not place/answer calls, write PCM samples, record audio, or enable a daemon.
The graph routes modem audio directly to the speakers and DMIC3 to the modem.
DMIC3 needs the matching board pinctrl, bias and VA clock dependency fix.
Stop other sound clients first; any open PCM on this card is a conflict.
Mixer state is captured before any write and restored after closing both PCMs.
"""

import argparse
import contextlib
import ctypes
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time


ROUTES = (
    ("TERTIARY_MI2S_RX Audio Mixer MultiMedia1", "0"),
    ("TERTIARY_MI2S_RX Audio Mixer MultiMedia2", "0"),
    ("MultiMedia3 Mixer TX_CODEC_DMA_TX_3", "0"),
    ("ADC1_MIXER Switch", "0"),
    ("ADC1 Switch", "0"),
    ("TX0 MODE", "ADC_NORMAL"),
    ("TX DEC0 MUX", "MSM_DMIC"),
    ("TX DMIC MUX0", "DMIC3"),
    ("TX_AIF1_CAP Mixer DEC0", "1"),
    ("TX_AIF1_CAP Mixer DEC1", "0"),
    ("TX_DEC0 Volume", "84"),
    ("TERTIARY_MI2S_RX Audio Mixer MultiMedia5", "1"),
    ("MultiMedia6 Mixer TX_CODEC_DMA_TX_3", "1"),
)


class StopRequested(Exception):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(f"received signal {signum}")


def find_pcms(proc=Path("/proc/asound")):
    found = {}
    for line in (proc / "pcm").read_text().splitlines():
        match = re.match(r"\s*(\d+)-(\d+):\s*(MultiMedia[56] Voice)\b", line)
        if match:
            card, device, name = match.groups()
            if name in found:
                raise RuntimeError(f"ambiguous PCM: {name}")
            found[name] = (int(card), int(device))
    if set(found) != {"MultiMedia5 Voice", "MultiMedia6 Voice"}:
        raise RuntimeError("matching MultiMedia5/6 Voice PCMs are missing; install the experimental kernel/topology first")
    card, rx = found["MultiMedia5 Voice"]
    tx_card, tx = found["MultiMedia6 Voice"]
    if card != tx_card or (proc / f"card{card}" / "id").read_text().strip() != "OnePlus10Pro":
        raise RuntimeError("voice PCMs are not on the OnePlus10Pro card")
    return card, rx, tx


def check_idle(card, proc=Path("/proc/asound")):
    statuses = sorted((proc / f"card{card}").glob("pcm*/sub*/status"))
    if not statuses:
        raise RuntimeError("cannot inspect PCM state")
    busy = []
    for path in statuses:
        status = path.read_text().strip()
        if status != "closed":
            busy.append(f"{path}: {status.replace(chr(10), '; ')}")
    if busy:
        print("Open PCM streams:\n" + "\n".join(busy), file=sys.stderr)
        raise RuntimeError("audio clients still own the card; stop them before running this test")
    print(f"Card {card}: all {len(statuses)} PCM substreams closed", flush=True)


class Mixer:
    def __init__(self, card):
        self.card = str(card)

    def command(self, *args):
        # sysdefault may be UCM's remap plugin (including different numids).
        # Use the hardware control namespace for both snapshot and restore.
        result = subprocess.run(["amixer", "-D", f"hw:{self.card}", *args], check=True,
                                capture_output=True, text=True, timeout=5)
        return result.stdout

    def get(self, selector):
        output = self.command("cget", selector)
        number = re.search(r"^numid=(\d+),", output, re.M)
        values = re.search(r"^\s*: values=(.+)$", output, re.M)
        if not number or not values:
            raise RuntimeError(f"cannot parse mixer state: {selector}")
        return (f"numid={number.group(1)}", values.group(1).strip())

    def set(self, selector, value):
        self.command("cset", selector, value)


class MixerTransaction:
    def __init__(self, mixer, routes):
        self.mixer = mixer
        # A missing control must fail before any control is changed.
        self.saved = {name: mixer.get(f"name={name}") for name, _ in routes}
        self.routes = routes
        self.changed = []

    def apply(self):
        for name, value in self.routes:
            selector, _ = self.saved[name]
            # A failed cset may still have changed hardware, so record first.
            self.changed.append(name)
            self.mixer.set(selector, value)

    def restore(self):
        errors = []
        for name in reversed(self.changed):
            selector, value = self.saved[name]
            try:
                self.mixer.set(selector, value)
                if self.mixer.get(selector)[1] != value:
                    raise RuntimeError("readback differs from saved value")
            except Exception as exc:
                errors.append(f"restore {name} ({selector}) to {value}: {exc}")
        return errors


class Alsa:
    def __init__(self):
        self.lib = ctypes.CDLL("libasound.so.2")
        pointer = ctypes.c_void_p
        pointer_out = ctypes.POINTER(pointer)
        ulong = ctypes.c_ulong
        signatures = {
            "snd_pcm_open": ([pointer_out, ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "snd_pcm_set_params": ([pointer, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                    ctypes.c_uint, ctypes.c_int, ctypes.c_uint], ctypes.c_int),
            "snd_pcm_sw_params_malloc": ([pointer_out], ctypes.c_int),
            "snd_pcm_sw_params_free": ([pointer], None),
            "snd_pcm_sw_params_current": ([pointer, pointer], ctypes.c_int),
            "snd_pcm_sw_params_get_boundary": ([pointer, ctypes.POINTER(ulong)], ctypes.c_int),
            "snd_pcm_sw_params_set_stop_threshold": ([pointer, pointer, ulong], ctypes.c_int),
            "snd_pcm_sw_params_set_silence_size": ([pointer, pointer, ulong], ctypes.c_int),
            "snd_pcm_sw_params": ([pointer, pointer], ctypes.c_int),
            "snd_pcm_prepare": ([pointer], ctypes.c_int),
            "snd_pcm_start": ([pointer], ctypes.c_int),
            "snd_pcm_close": ([pointer], ctypes.c_int),
            "snd_strerror": ([ctypes.c_int], ctypes.c_char_p),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result

    def call(self, name, *args):
        result = getattr(self.lib, name)(*args)
        if result < 0:
            error = self.lib.snd_strerror(result).decode(errors="replace")
            raise RuntimeError(f"{name}: {error} ({result})")

    def open(self, name, capture):
        pcm = ctypes.c_void_p()
        self.call("snd_pcm_open", ctypes.byref(pcm), name.encode(), int(capture), 0)
        return pcm

    def start(self, pcm, capture):
        # S16_LE, RW_INTERLEAVED, stereo 48 kHz; the graph converts to voice rate.
        self.call("snd_pcm_set_params", pcm, 2, 3, 2, 48000, 0, 500000)
        if not capture:
            sw = ctypes.c_void_p()
            self.call("snd_pcm_sw_params_malloc", ctypes.byref(sw))
            try:
                self.call("snd_pcm_sw_params_current", pcm, sw)
                boundary = ctypes.c_ulong()
                self.call("snd_pcm_sw_params_get_boundary", sw, ctypes.byref(boundary))
                self.call("snd_pcm_sw_params_set_stop_threshold", pcm, sw, boundary)
                self.call("snd_pcm_sw_params_set_silence_size", pcm, sw, 0)
                self.call("snd_pcm_sw_params", pcm, sw)
            finally:
                self.lib.snd_pcm_sw_params_free(sw)
        self.call("snd_pcm_prepare", pcm)
        self.call("snd_pcm_start", pcm)

    def close(self, pcm):
        self.call("snd_pcm_close", pcm)


@contextlib.contextmanager
def ignore_stop_signals():
    previous = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run_test(alsa, mixer, card, rx_device, tx_device, seconds, wait=time.sleep,
             routes=ROUTES, checkpoint=lambda: None):
    transaction = MixerTransaction(mixer, routes)
    opened = []
    failure = None
    cleanup_errors = []
    try:
        checkpoint()
        transaction.apply()
        checkpoint()
        # Both graphs must exist before their backends prepare. RX carries VSID.
        tx = alsa.open(f"hw:{card},{tx_device}", capture=True)
        opened.append(tx)
        checkpoint()
        rx = alsa.open(f"hw:{card},{rx_device}", capture=False)
        opened.append(rx)
        checkpoint()
        alsa.start(rx, capture=False)
        checkpoint()
        alsa.start(tx, capture=True)
        checkpoint()
        print(f"Voice graphs running for {seconds:g} seconds (no host PCM data transfer)", flush=True)
        wait(seconds)
    except BaseException as exc:
        failure = exc
    finally:
        # A second Ctrl-C must not interrupt restoration halfway through.
        with ignore_stop_signals():
            # Close TX before RX, preserving the VSID while TX is torn down.
            for pcm in opened:
                try:
                    alsa.close(pcm)
                except Exception as exc:
                    cleanup_errors.append(f"close PCM: {exc}")
            cleanup_errors.extend(transaction.restore())
    if cleanup_errors:
        detail = "; ".join(cleanup_errors)
        raise RuntimeError(f"cleanup incomplete: {detail}") from failure
    if failure is not None:
        raise failure
    print("Voice PCMs closed; all changed mixer values restored and verified", flush=True)


@contextlib.contextmanager
def exclusive_lock():
    import fcntl
    fd = os.open("/run/lock/negroni-voice-test.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another voice test is already running") from exc
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=20, help="test duration, 1..300 seconds (default: 20)")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 300:
        parser.error("--seconds must be finite and between 1 and 300")
    previous = {}
    try:
        stopped = threading.Event()
        stop_signal = [None]
        def stop(signum, _frame):
            # Do not raise between a successful C allocation/open and saving
            # its handle. Checkpoints stop work after ownership is recorded.
            stop_signal[0] = signum
            stopped.set()
        def checkpoint():
            if stop_signal[0] is not None:
                raise StopRequested(stop_signal[0])
        def wait(seconds):
            stopped.wait(seconds)
            checkpoint()
        previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
        with exclusive_lock():
            card, rx, tx = find_pcms()
            check_idle(card)
            run_test(Alsa(), Mixer(card), card, rx, tx, args.seconds,
                     wait=wait, checkpoint=checkpoint)
    except StopRequested as exc:
        print(f"Stopped; mixer restoration completed: {exc}", file=sys.stderr)
        return 128 + exc.signum
    except Exception as exc:
        print(f"Voice test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
