#!/usr/bin/env python3
"""Inspect or exercise the phone's evdev vibrator using the native Linux ABI."""
import argparse
import ctypes as ct
import fcntl
import glob
import json
import os
from pathlib import Path
import struct
import time


class Envelope(ct.Structure):
    _fields_ = [(name, ct.c_uint16) for name in
                ('attack_length', 'attack_level', 'fade_length', 'fade_level')]


class Constant(ct.Structure):
    _fields_ = [('level', ct.c_int16), ('envelope', Envelope)]


class Periodic(ct.Structure):
    _fields_ = [('waveform', ct.c_uint16), ('period', ct.c_uint16),
                ('magnitude', ct.c_int16), ('offset', ct.c_int16),
                ('phase', ct.c_uint16), ('envelope', Envelope),
                ('custom_len', ct.c_uint32), ('custom_data', ct.POINTER(ct.c_int16))]


class Rumble(ct.Structure):
    _fields_ = [('strong', ct.c_uint16), ('weak', ct.c_uint16)]


class Payload(ct.Union):
    _fields_ = [('constant', Constant), ('periodic', Periodic), ('rumble', Rumble)]


class Effect(ct.Structure):
    _fields_ = [('type', ct.c_uint16), ('id', ct.c_int16),
                ('direction', ct.c_uint16), ('trigger_button', ct.c_uint16),
                ('trigger_interval', ct.c_uint16), ('length', ct.c_uint16),
                ('delay', ct.c_uint16), ('u', Payload)]


FF_RUMBLE, FF_CONSTANT, FF_PERIODIC, FF_SINE, FF_GAIN = 0x50, 0x52, 0x51, 0x5a, 0x60
EV_FF = 0x15


def ioctl_code(direction, number, size):
    return direction << 30 | size << 16 | ord('E') << 8 | number


def event(fd, code, value):
    os.write(fd, struct.pack('@llHHi', 0, 0, EV_FF, code, value))


def find_device():
    for name in sorted(glob.glob('/sys/class/input/event*/device/name')):
        if Path(name).read_text().strip() == 'qcom-hv-haptics':
            return '/dev/input/' + Path(name).parents[1].name
    raise RuntimeError('qcom-hv-haptics input device is missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='default: discover qcom-hv-haptics by name')
    parser.add_argument('--info', action='store_true', help='inspect without vibrating')
    parser.add_argument('--type', choices=('rumble', 'constant', 'sine'), default='rumble')
    parser.add_argument('--duration-ms', type=int, default=80)
    parser.add_argument('--strength', type=float, default=0.3)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--upload-delay-ms', type=int, default=0)
    parser.add_argument('--stop-after-ms', type=int, help='stop before the programmed duration')
    parser.add_argument('--auto-stop', action='store_true', help='wait past the driver timer before sending stop')
    args = parser.parse_args()
    if not (1 <= args.duration_ms <= 1000 and 0 < args.strength <= 1
            and 1 <= args.count <= 20 and 0 <= args.upload_delay_ms <= 2000
            and (args.stop_after_ms is None or 0 <= args.stop_after_ms <= args.duration_ms)
            and not (args.auto_stop and args.stop_after_ms is not None)):
        parser.error('duration 1..1000 ms, strength (0,1], count 1..20, delay 0..2000 ms; stop within duration')
    device = args.device or find_device()
    fd = os.open(device, (os.O_RDONLY if args.info else os.O_RDWR) | os.O_NONBLOCK)
    try:
        caps = bytearray(16)
        fcntl.ioctl(fd, ioctl_code(2, 0x20 + EV_FF, len(caps)), caps, True)
        supported = [name for name, bit in (('rumble', FF_RUMBLE), ('constant', FF_CONSTANT),
                                            ('periodic', FF_PERIODIC), ('sine', FF_SINE), ('gain', FF_GAIN))
                     if caps[bit // 8] & (1 << (bit % 8))]
        print(json.dumps({'device': device, 'capabilities': supported,
                          'effect_size': ct.sizeof(Effect)}, sort_keys=True), flush=True)
        if args.info:
            return
        if args.type not in supported:
            raise RuntimeError(f'{args.type} is not supported')
        effect = Effect(id=-1, length=args.duration_ms)
        if args.type == 'rumble':
            effect.type = FF_RUMBLE
            effect.u.rumble.strong = round(args.strength * 65535)
        elif args.type == 'constant':
            effect.type = FF_CONSTANT
            effect.u.constant.level = round(args.strength * 32767)
        else:
            effect.type = FF_PERIODIC
            effect.u.periodic.waveform = FF_SINE
            effect.u.periodic.period = 6
            effect.u.periodic.magnitude = round(args.strength * 32767)
        payload = bytearray(effect)
        fcntl.ioctl(fd, ioctl_code(1, 0x80, len(payload)), payload, True)
        effect = Effect.from_buffer_copy(payload)
        try:
            time.sleep(args.upload_delay_ms / 1000)
            for index in range(args.count):
                event(fd, effect.id, 1)
                print(f'play {index + 1}/{args.count}: {args.type}, {args.duration_ms} ms, {args.strength:.0%}', flush=True)
                delay = args.duration_ms if args.stop_after_ms is None else args.stop_after_ms
                if args.auto_stop:
                    delay += 200
                time.sleep(delay / 1000)
                event(fd, effect.id, 0)
                time.sleep(0.35)
        finally:
            event(fd, effect.id, 0)
            fcntl.ioctl(fd, ioctl_code(1, 0x81, ct.sizeof(ct.c_int)), effect.id)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
