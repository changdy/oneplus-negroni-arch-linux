#!/usr/bin/env python3
"""Read registration and voice status for the tested NE2210 SIM on binding 0.

Message and TLV definitions: libqmi 1.38.0 data/qmi-service-imsa.json.
The binding applies to this QRTR socket and expires when it closes.
"""

import socket
import struct
import subprocess
import time


def imsa_peer():
    ports = []
    for line in subprocess.check_output(["qrtr-lookup"], text=True).splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0] == "33" and fields[2:4] == ["0", "0"]:
            ports.append(int(fields[4]))
    if len(ports) != 1:
        raise ValueError(f"expected one IMSA endpoint on node 0, found {ports}")
    return 0, ports[0]


def request(sock, peer, txn, message, payload=b""):
    header = struct.Struct("<BHHH")
    sock.sendto(header.pack(0, txn, message, len(payload)) + payload, peer)
    deadline = time.monotonic() + 5
    while (remaining := deadline - time.monotonic()) > 0:
        sock.settimeout(remaining)
        data, source = sock.recvfrom(8192)
        if source != peer or len(data) < header.size:
            continue
        flags, rx_txn, rx_message, length = header.unpack_from(data)
        if (flags, rx_txn, rx_message) != (2, txn, message):
            continue
        if len(data) != header.size + length:
            raise ValueError("incomplete QMI response")
        fields = {}
        offset = header.size
        while offset < len(data):
            tag, size = struct.unpack_from("<BH", data, offset)
            offset += 3
            if offset + size > len(data) or tag in fields:
                raise ValueError("invalid QMI TLV")
            fields[tag] = data[offset:offset + size]
            offset += size
        result, error = struct.unpack("<HH", fields[2])
        if result:
            raise ValueError(f"QMI message {message:#06x} returned error {error}")
        return fields
    raise TimeoutError(f"no response to QMI message {message:#06x}")


def describe(fields, tag, names):
    if tag not in fields:
        return "not reported"
    value, = struct.unpack("<I", fields[tag])
    return names[value] if value < len(names) else f"unknown ({value})"


def main():
    peer = imsa_peer()
    with socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM) as sock:
        request(sock, peer, 1, 0x33, struct.pack("<BHI", 0x10, 4, 0))
        registration = request(sock, peer, 2, 0x20)
        services = request(sock, peer, 3, 0x21)
    networks = ("WLAN", "WWAN", "interworking WLAN")
    print("registration:", describe(registration, 0x12, ("unregistered", "registering", "registered", "limited")))
    print("registration network:", describe(registration, 0x14, networks))
    print("voice service:", describe(services, 0x11, ("unavailable", "limited", "available")))
    print("voice network:", describe(services, 0x14, networks))


if __name__ == "__main__":
    main()
