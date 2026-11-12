#!/usr/bin/env python3
"""Bounded QMI LOC probe; prints satellite/fix summaries, never coordinates.

Uses the public Qualcomm location_service_v02.h wire definitions. Each run
owns a separate QRTR socket and stops only its own session in finally.
The GNSS engine must already be unlocked; no NV or lock settings are changed.
"""

import argparse
import collections
import socket
import struct
import subprocess
import time


def tlv(tag, fmt, value):
    data = struct.pack(fmt, value)
    return struct.pack("<BH", tag, len(data)) + data


def unpack_tlvs(data):
    fields = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 3:
            raise ValueError("truncated TLV header")
        tag, length = struct.unpack_from("<BH", data, offset)
        offset += 3
        if length > len(data) - offset:
            raise ValueError("truncated TLV value")
        fields[tag] = data[offset:offset + length]
        offset += length
    return fields


class Probe:
    def __init__(self, node, port):
        self.sock = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
        self.sock.settimeout(0.5)
        self.peer = (node, port)
        self.transaction = 0
        self.reports = collections.Counter()
        self.last_summary = 0
        self.have_fix = False

    def receive(self):
        data, peer = self.sock.recvfrom(65535)
        if peer != self.peer or len(data) < 7:
            raise ValueError("unexpected QMI peer/header")
        flags, transaction, message, length = struct.unpack_from("<BHHH", data)
        if len(data) != 7 + length:
            raise ValueError("QMI length mismatch")
        fields = unpack_tlvs(data[7:])
        if flags == 4:
            self.indication(message, fields)
        return flags, transaction, message, fields

    def request(self, message, body=b""):
        self.transaction += 1
        self.sock.sendto(struct.pack("<BHHH", 0, self.transaction, message, len(body)) + body, self.peer)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                flags, transaction, received, fields = self.receive()
            except socket.timeout:
                continue
            if flags == 2 and transaction == self.transaction and received == message:
                if len(fields.get(2, b"")) != 4:
                    raise ValueError("missing QMI result")
                result, error = struct.unpack("<HH", fields[2])
                if result:
                    raise RuntimeError(f"QMI {message:#06x} failed: error {error}")
                print(f"QMI {message:#06x}: accepted", flush=True)
                return
        raise TimeoutError(f"QMI {message:#06x}: response timeout")

    def indication(self, message, fields):
        self.reports[message] += 1
        if message == 0x24:
            status = int.from_bytes(fields.get(1, b"\xff"), "little")
            if status == 0 and 0x13 in fields and 0x14 in fields:
                self.have_fix = True
        elif message == 0x25:
            expanded = 0x11 in fields
            data = fields.get(0x11 if expanded else 0x10, b"")
            if not data:
                return
            fmt = "<IIHBIBfff" + ("B" if expanded else "")
            width = struct.calcsize(fmt)
            count = data[0]
            if len(data) != 1 + count * width:
                raise ValueError("unexpected satellite array length")
            systems = collections.Counter()
            tracking = 0
            cn0 = []
            for offset in range(1, len(data), width):
                row = struct.unpack_from(fmt, data, offset)
                valid, system, _, _, status = row[:5]
                if valid & 1:
                    systems[system] += 1
                tracking += bool(valid & 8 and status == 3)
                if valid & 0x80:
                    cn0.append(round(row[8], 1))
            if time.monotonic() - self.last_summary >= 15:
                self.last_summary = time.monotonic()
                print(f"SV targets={count} systems={dict(systems)} tracking={tracking} "
                      f"valid_CN0={len(cn0)} max_CN0={max(cn0, default=None)} "
                      f"fix={self.have_fix}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--node", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.duration <= 1800:
        parser.error("duration must be between 1 and 1800 seconds")
    servers = subprocess.check_output(["qrtr-lookup"], text=True)
    ports = []
    for line in servers.splitlines():
        parts = line.split()
        if len(parts) >= 5 and all(part.isdigit() for part in parts[:5]):
            service, _, instance, node, port = map(int, parts[:5])
            if service == 16 and instance == 0 and node == args.node:
                ports.append(port)
    if len(ports) != 1:
        raise RuntimeError(f"expected one LOC endpoint on node {args.node}, found {ports}")
    probe = Probe(args.node, ports[0])
    started = False
    try:
        # Register as AFW before Start; the default NFW registration is rejected.
        probe.request(0x21, tlv(1, "<Q", 7) + tlv(0x10, "4s", b"NGNS")
                      + tlv(0x11, "<I", 1) + tlv(0x12, "<B", 0))
        # Set before sending so cleanup also runs if the Start response is lost.
        started = True
        probe.request(0x22, tlv(1, "<B", 222) + tlv(0x10, "<I", 1)
                      + tlv(0x12, "<I", 1) + tlv(0x13, "<I", 1000))
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            try:
                probe.receive()
            except socket.timeout:
                continue
    finally:
        try:
            if started:
                probe.request(0x23, tlv(1, "<B", 222))
        finally:
            probe.sock.close()
        print(f"Reports: {dict(probe.reports)}; valid_fix={probe.have_fix}")


if __name__ == "__main__":
    main()
