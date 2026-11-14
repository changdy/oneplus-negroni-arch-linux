#!/usr/bin/env python3
"""Inspect the local Negroni CamX Parameter Parser V3.5.1 sensor modules.

Offline only: no I2C operations and no generated driver or calibration data.
The observed 32-bit format differs from V1.4.0's 64-bit format described at
https://github.com/miromraz/a52q-linux/blob/master/tools/camx-sensormodule.py.
Register widths come from the serialized fields, never from register values.
Unknown layouts are rejected instead of producing a plausible register table.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


class FormatError(ValueError):
    pass


class SensorModule:
    def __init__(self, data):
        self.data = data
        if len(data) < 204 or data[:20] != b"QTI Chromatix Header":
            raise FormatError("Not a QTI sensor module")
        self.version = data[40:88].split(b"\0", 1)[0].decode("ascii")
        if self.version != "Parameter Parser V3.5.1 (2207122229)":
            raise FormatError(f"Unsupported parser version: {self.version}")
        if self.u32(28) != len(data) - 4:
            raise FormatError("Header file length mismatch")
        if self.u32(len(data) - 4) != zlib.crc32(data[:-4]):
            raise FormatError("CRC32 mismatch")
        table, count = self.u32(160), self.u32(164)
        if count != 3:
            raise FormatError("Expected three sections")
        sections = {}
        for i in range(count):
            kind, offset, length = struct.unpack("<3I", self.slice(table + i * 12, 12))
            self.slice(offset, length)
            if kind in sections:
                raise FormatError("Duplicate section")
            sections[kind] = (offset, length)
        if set(sections) != {0, 1, 2}:
            raise FormatError("Unknown sections")
        start, length = sections[0]
        self.pool_start, self.pool_size = sections[1]
        if length % 60:
            raise FormatError("Descriptor table is not a multiple of 60 bytes")
        self.nodes = []
        self.by_id = {}
        for at in range(start, start + length, 60):
            index, name, kind, flag, reserved, offset, size, reference = struct.unpack(
                "<I32s6I", self.slice(at, 60))
            try:
                name = name.split(b"\0", 1)[0].decode("ascii")
            except UnicodeDecodeError as exc:
                raise FormatError("Invalid descriptor name") from exc
            if index != len(self.nodes) + 1 or not name or not name.isprintable():
                raise FormatError("Invalid descriptor index/name")
            if offset > self.pool_size or size > self.pool_size - offset:
                raise FormatError(f"Descriptor {index} exceeds value pool")
            node = dict(id=index, name=name, kind=kind, flag=flag,
                        reserved=reserved, offset=offset, size=size, reference=reference)
            self.nodes.append(node)
            self.by_id[index] = node
        self.sensor_end = next((n["id"] for n in self.nodes
                                if n["name"] == "moduleConfiguration"), len(self.nodes) + 1)

    def slice(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.data) or size > len(self.data) - offset:
            raise FormatError("File range out of bounds")
        return self.data[offset:offset + size]

    def u32(self, offset):
        return struct.unpack("<I", self.slice(offset, 4))[0]

    def payload(self, node):
        return self.slice(self.pool_start + node["offset"], node["size"])

    def words(self, node):
        data = self.payload(node)
        if len(data) % 4:
            raise FormatError(f"Non-integer payload: {node['name']}")
        return list(struct.unpack(f"<{len(data) // 4}I", data))

    def leaf(self, index, name):
        node = self.by_id.get(index)
        if node is None or node["name"] != name:
            raise FormatError(f"Expected {name} descriptor {index}")
        return self.words(node)

    def registers(self, node):
        words = self.words(node)
        if not words or len(words) % 10:
            raise FormatError(f"Unknown regSetting layout at {node['id']}")
        registers = []
        for i in range(0, len(words), 10):
            slave_count, slave_id, address, count, data_id, aw, dw, operation, delay_count, delay_id = words[i:i + 10]
            expected = node["id"] + 1 + i // 10 * 3
            if (slave_id, data_id, delay_id) != (expected, expected + 1, expected + 2):
                raise FormatError("Register descriptor order mismatch")
            slave = self.leaf(slave_id, "slaveAddr")
            values = self.leaf(data_id, "registerData")
            delay = self.leaf(delay_id, "delayUs")
            if slave_count != len(slave) or count != len(values) or delay_count != len(delay):
                raise FormatError("Register array count mismatch")
            if values and (aw not in (1, 2, 3, 4) or dw not in (1, 2, 3, 4)):
                raise FormatError(f"Unknown register address/data width at {node['id']} record {i // 10}: {aw}/{dw}")
            if values and (address >= 1 << (8 * aw) or any(v >= 1 << (8 * dw) for v in values)):
                raise FormatError("Register value exceeds declared width")
            registers.append(dict(address=address, values=values, address_bytes=aw,
                                  data_bytes=dw, operation=operation,
                                  slave_address_raw=slave, delay_us=delay))
        return registers

    def inspect(self, include_registers=False):
        tables = []
        streams = []
        power = []
        section = None
        sections = {"initSettings", "resolutionData", "startSettings", "stopSettings",
                    "groupHoldOnSettings", "groupHoldOffSettings", "testPatternData",
                    "masterSettings", "slaveSettings", "SPCSettings", "PDAFSettings"}
        name = None
        for node in self.nodes:
            if node["id"] >= self.sensor_end:
                break
            if node["name"] in sections:
                section = node["name"]
            if node["name"] == "sensorName" and name is None:
                name = self.payload(node).rstrip(b"\0").decode("ascii")
            if node["name"] == "powerSetting" and node["size"]:
                words = self.words(node)
                if len(words) % 3:
                    raise FormatError("Unknown power sequence layout")
                power.append(dict(descriptor=node["id"],
                                  steps=[dict(type_raw=words[i], value_raw=words[i+1],
                                              delay_raw=words[i+2])
                                         for i in range(0, len(words), 3)]))
            if node["name"] == "streamConfiguration":
                streams.append(dict(descriptor=node["id"], words=self.words(node)))
            if node["name"] == "regSetting":
                try:
                    registers = self.registers(node)
                except FormatError as exc:
                    tables.append(dict(descriptor=node["id"], section=section,
                                       decoded=False, error=str(exc)))
                    continue
                table = dict(descriptor=node["id"], section=section, count=len(registers),
                             decoded=True,
                             widths=sorted({(r["address_bytes"], r["data_bytes"])
                                            for r in registers}),
                             operations=sorted({r["operation"] for r in registers}))
                if include_registers:
                    table["registers"] = registers
                tables.append(table)
        return dict(sensor=name, parser=self.version, descriptors=len(self.nodes),
                    sensor_descriptor_end=self.sensor_end,
                    sha256=hashlib.sha256(self.data).hexdigest(), bytes=len(self.data),
                    power_sequences=power, stream_configurations=streams,
                    register_tables=tables,
                    limitations="Offline structural decode; no hardware validation. "
                                 "Power type/delay units and mode associations need schema confirmation.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--registers", action="store_true",
                        help="include register data; keep the output outside Git")
    args = parser.parse_args()
    try:
        result = SensorModule(args.module.read_bytes()).inspect(args.registers)
    except (OSError, ValueError, struct.error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
