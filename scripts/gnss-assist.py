#!/usr/bin/env python3
"""Refresh Qualcomm GNSS time/XTRA assistance without starting positioning.

Wire definitions: qualcomm-linux/location-apis-qcom, location_service_v02.h.
Uses QueryXtraInfo (0xb0) and InjectXtraData (0xa7) on this SM8450 firmware.
Only AFW registration is used; no master/privileged registration, RF/NV
configuration, engine-lock change, or location upload is performed.
"""

import argparse
import datetime
import hashlib
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_FILE_SIZE = 1024 * 1024


def tlv(tag, data):
    return struct.pack("<BH", tag, len(data)) + data


def number(tag, fmt, value):
    return tlv(tag, struct.pack(fmt, value))


def unpack_tlvs(data):
    fields = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 3:
            raise ValueError("truncated QMI TLV header")
        tag, length = struct.unpack_from("<BH", data, offset)
        offset += 3
        if length > len(data) - offset or tag in fields:
            raise ValueError("truncated or duplicate QMI TLV")
        fields[tag] = data[offset:offset + length]
        offset += length
    return fields


def discover(node):
    ports = []
    for line in subprocess.check_output(["qrtr-lookup"], text=True).splitlines():
        parts = line.split()
        if len(parts) >= 5 and all(part.isdigit() for part in parts[:5]):
            service, _, instance, found_node, port = map(int, parts[:5])
            if (service, instance, found_node) == (16, 0, node):
                ports.append(port)
    if len(ports) != 1:
        raise RuntimeError(f"expected one LOC endpoint on node {node}, found {ports}")
    return node, ports[0]


class Loc:
    def __init__(self, peer):
        self.peer = peer
        self.sock = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
        self.sock.settimeout(0.5)
        self.transaction = 0

    def command(self, message, payload=b"", indication=True):
        self.transaction = self.transaction % 65535 + 1
        transaction = self.transaction
        self.sock.sendto(struct.pack("<BHHH", 0, transaction, message, len(payload)) + payload, self.peer)
        reply = None
        accepted = False
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                data, peer = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            # QRTR flow-control notifications may have no QMI header.
            if peer != self.peer or len(data) < 7:
                continue
            flags, received_txn, received_msg, length = struct.unpack_from("<BHHH", data)
            if len(data) != 7 + length:
                raise ValueError("QMI payload length mismatch")
            if received_msg != message:
                continue
            fields = unpack_tlvs(data[7:])
            if flags == 2 and received_txn == transaction:
                if len(fields.get(2, b"")) != 4:
                    raise ValueError("missing QMI result")
                result, error = struct.unpack("<HH", fields[2])
                if result:
                    raise RuntimeError(f"QMI {message:#06x}: protocol error {error}")
                accepted = True
            elif flags == 4:
                # An indication may arrive before its response. Only one
                # request is in flight, and part numbers are checked below.
                reply = fields
            if accepted and (reply is not None or not indication):
                if indication:
                    if len(reply.get(1, b"")) != 4:
                        raise ValueError("missing LOC indication status")
                    status = struct.unpack("<I", reply[1])[0]
                    if status:
                        raise RuntimeError(f"QMI {message:#06x}: indication status {status}")
                return reply
        raise TimeoutError(f"QMI {message:#06x}: response/indication timeout")


def validity(fields):
    if len(fields.get(0x10, b"")) != 10:
        raise ValueError("missing assistance validity")
    # This field uses Unix seconds; InjectUtcTime uses milliseconds.
    start, hours = struct.unpack("<QH", fields[0x10])
    return start, start + hours * 3600


def server_urls(fields):
    data = fields.get(2, b"")
    if len(data) < 15 or not struct.unpack_from("<I", data)[0] & 4:
        raise ValueError("firmware did not provide XTRA servers")
    # reportMask:u32, absolute age:u16, relative age:u64, server array.
    count = data[14]
    if not 1 <= count <= 3:
        raise ValueError("unexpected XTRA server count")
    offset = 15
    urls = []
    for _ in range(count):
        if offset >= len(data):
            raise ValueError("truncated XTRA server list")
        length = data[offset]
        offset += 1
        if not length or offset + length > len(data):
            raise ValueError("invalid XTRA server length")
        url = data[offset:offset + length].decode("ascii")
        offset += length
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("XTRA download requires an HTTPS URL without userinfo")
        urls.append(url)
    return urls


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("refusing a non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(urls):
    opener = urllib.request.build_opener(HttpsOnly())
    errors = []
    for url in urls:
        host = urllib.parse.urlsplit(url).hostname
        try:
            # Default SSL verification is retained. No location is sent.
            with opener.open(url, timeout=20) as response:
                data = response.read(MAX_FILE_SIZE + 1)
            if not 1024 <= len(data) <= MAX_FILE_SIZE:
                raise ValueError("assistance download has an unexpected size")
            print(f"Downloaded {len(data)} bytes from {host}", flush=True)
            return data
        except (OSError, ValueError, urllib.error.URLError) as error:
            errors.append(f"{host}: {type(error).__name__}")
    raise RuntimeError("XTRA downloads failed: " + "; ".join(errors))


def inject(loc, data):
    if not 1024 <= len(data) <= MAX_FILE_SIZE:
        raise ValueError("assistance file must be between 1 KiB and 1 MiB")
    total = (len(data) + 1023) // 1024
    for part_number in range(1, total + 1):
        chunk = data[(part_number - 1) * 1024:part_number * 1024]
        payload = (number(1, "<I", len(data)) + number(2, "<H", total)
                   + number(3, "<H", part_number)
                   + tlv(4, struct.pack("<H", len(chunk)) + chunk) + number(0x10, "<I", 0))
        reply = loc.command(0xa7, payload)
        if reply.get(0x10) != struct.pack("<H", part_number):
            raise ValueError("assistance part acknowledgment mismatch")
    print(f"Injected {total} parts; every response and indication succeeded", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", type=int, default=0)
    parser.add_argument("--file", type=Path, help="inject an already downloaded XTRA file")
    parser.add_argument("--force", action="store_true", help="refresh even if cached data remains valid")
    args = parser.parse_args()
    # Boot starts with an invalid clock on this phone. Do not inject it.
    synced = subprocess.check_output(
        ["timedatectl", "show", "-p", "NTPSynchronized", "--value"], text=True).strip()
    if synced not in ("yes", "true"):
        raise RuntimeError("wait for NTP synchronization before injecting GNSS time")
    loc = Loc(discover(args.node))
    try:
        loc.command(0x21, number(1, "<Q", 0) + tlv(0x10, b"NGNS")
                    + number(0x11, "<I", 1) + number(0x12, "<B", 0), indication=False)
        loc.command(0x38, number(1, "<Q", int(time.time() * 1000)) + number(2, "<I", 1000))
        print("Injected NTP-synchronized UTC time", flush=True)
        _, end = validity(loc.command(0x37))
        if not args.file and not args.force and end - time.time() >= 12 * 3600:
            print("Cached assistance has at least 12 hours remaining; no download needed")
            return
        if args.file:
            with args.file.open("rb") as stream:
                data = stream.read(MAX_FILE_SIZE + 1)
        else:
            data = download(server_urls(loc.command(0xb0, number(1, "<I", 0))))
        print("Assistance sha256=" + hashlib.sha256(data).hexdigest(), flush=True)
        inject(loc, data)
        start, end = validity(loc.command(0x37))
        if end <= time.time() or start > time.time() + 3600:
            raise RuntimeError("injected assistance does not cover the current time")
        print("Assistance valid until " + datetime.datetime.fromtimestamp(
            end, datetime.timezone.utc).isoformat(), flush=True)
    finally:
        loc.sock.close()


if __name__ == "__main__":
    main()
