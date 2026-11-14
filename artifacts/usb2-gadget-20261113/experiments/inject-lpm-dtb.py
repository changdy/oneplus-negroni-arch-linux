#!/usr/bin/env python3
"""Build a vendor_boot image with snps,usb2-gadget-lpm-disable, from the
currently running slot's partition backup. Pure-Python FDT edit: no dtc,
no mkbootimg, no kernel tree / WSL needed. This script never touches a device.

Verification: every original DT property must survive byte-for-byte, the only
addition must be one empty boolean property on the &usb_1 node, and the
vendor_boot header may only change its dtb_size field.
"""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "vendor_boot_b-original-20261113.img"
DST = HERE / "vendor_boot_b-lpm.img"
REPORT = HERE / "lpm-image-build.json"
PROP = b"snps,usb2-gadget-lpm-disable"
TARGET = "/soc@0/usb@a600000"  # &usb_1 in sm8450-oneplus-negroni.dts

FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
HEADER_NAMES = ("magic", "totalsize", "off_dt_struct", "off_dt_strings",
                "off_mem_rsvmap", "version", "last_comp_version",
                "boot_cpuid_phys", "size_dt_strings", "size_dt_struct")


def be32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def parse_fdt(dtb):
    header = dict(zip(HEADER_NAMES, struct.unpack_from(">10I", dtb, 0)))
    if header["magic"] != 0xD00DFEED:
        raise ValueError("not a flattened device tree")
    if header["totalsize"] > len(dtb):
        raise ValueError("truncated dtb")
    tail = dtb[header["totalsize"]:]
    if any(tail):
        raise ValueError("nonzero bytes after fdt totalsize")
    off_struct = header["off_dt_struct"]
    off_strings = header["off_dt_strings"]
    size_struct = header["size_dt_struct"]
    size_strings = header["size_dt_strings"]
    blob = dtb[off_struct:off_struct + size_struct]
    strings = dtb[off_strings:off_strings + size_strings]

    props, insertion_points = {}, {}
    path, off = [], 0
    while True:
        token = be32(blob, off)
        off += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\0", off)
            name = blob[off:end].decode()
            off = (end + 4) & ~3
            if name in ("", "/"):  # the root node name is usually empty
                path = []
            else:
                path.append(name)
            insertion_points["/" + "/".join(path)] = off
        elif token == FDT_END_NODE:
            if path:
                path.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from(">II", blob, off)
            off += 8
            end = strings.index(b"\0", nameoff)
            pname = strings[nameoff:end].decode()
            value = blob[off:off + length]
            off = (off + length + 3) & ~3
            props["/" + "/".join(path) + "/" + pname] = value.hex()
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unexpected FDT token {token:#x} at {off}")
    return {"header": header, "props": props, "nodes": insertion_points,
            "blob": blob, "strings": strings, "tail": tail}


def main():
    image = SRC.read_bytes()
    if image[:8] != b"VNDRBOOT":
        raise ValueError("unexpected vendor_boot magic")
    if struct.unpack_from("<II", image, 8) != (4, 4096):
        raise ValueError("expected vendor_boot v4 / 4096-byte pages")
    if struct.unpack_from("<I", image, 24)[0] != 0:
        raise ValueError("expected an empty vendor ramdisk")
    dtb_size = struct.unpack_from("<I", image, 2100)[0]
    dtb = image[4096:4096 + dtb_size]
    if len(dtb) != dtb_size or any(image[4096 + dtb_size:]):
        raise ValueError("unexpected vendor_boot layout")

    old = parse_fdt(dtb)
    if TARGET not in old["nodes"]:
        raise ValueError(f"target node {TARGET} not found; candidates: " +
                         ", ".join(n for n in old["nodes"] if "usb" in n))
    needle = PROP + b"\0"
    if needle in old["strings"]:
        nameoff = old["strings"].index(needle)
        strings = old["strings"]
        growth = 0
    else:
        nameoff = len(old["strings"])
        strings = old["strings"] + needle
        growth = len(needle)

    insertion = old["nodes"][TARGET]
    prop_token = struct.pack(">III", FDT_PROP, 0, nameoff)  # empty boolean
    blob = old["blob"][:insertion] + prop_token + old["blob"][insertion:]

    header = bytearray(struct.pack(">10I", *(
        old["header"][n] for n in HEADER_NAMES)))
    header[4:8] = struct.pack(">I", old["header"]["totalsize"] + len(prop_token) + growth)
    header[12:16] = struct.pack(">I", old["header"]["off_dt_strings"] + len(prop_token))
    header[32:36] = struct.pack(">I", old["header"]["size_dt_strings"] + growth)
    header[36:40] = struct.pack(">I", old["header"]["size_dt_struct"] + len(prop_token))

    new_dtb = (bytes(header)
               + dtb[40:old["header"]["off_dt_struct"]]
               + blob
               + dtb[old["header"]["off_dt_struct"] + old["header"]["size_dt_struct"]:
                     old["header"]["off_dt_strings"]]
               + strings)
    if len(new_dtb) != old["header"]["totalsize"] + len(prop_token) + growth:
        raise ValueError("rebuilt dtb length mismatch")

    new = parse_fdt(new_dtb)
    removed = {k: v for k, v in old["props"].items() if new["props"].get(k) != v}
    added = {k: v for k, v in new["props"].items() if k not in old["props"]}
    expected_added = {TARGET + "/" + PROP.decode(): ""}
    if removed or added != expected_added:
        raise ValueError(f"unexpected DT delta: removed={removed}, added={added}")

    new_image = bytearray(image[:4096])
    struct.pack_into("<I", new_image, 2100, len(new_dtb))
    if new_image[:2100] != image[:2100] or new_image[2104:4096] != image[2104:4096]:
        raise ValueError("vendor_boot header changed beyond dtb_size")
    new_image += new_dtb
    new_image += b"\0" * (len(image) - len(new_image))
    if len(new_image) != len(image):
        raise ValueError("image length changed")
    DST.write_bytes(new_image)

    report = {
        "source": SRC.name,
        "source_sha256": hashlib.sha256(image).hexdigest(),
        "output": DST.name,
        "output_sha256": hashlib.sha256(new_image).hexdigest(),
        "slot_partition": "vendor_boot_b",
        "dtb_size_before": dtb_size,
        "dtb_size_after": len(new_dtb),
        "prop_added": TARGET + "/" + PROP.decode(),
        "properties_before": len(old["props"]),
        "properties_after": len(new["props"]),
        "verification": "all original DT properties byte-identical; exactly one empty boolean added; vendor_boot v4 header identical except dtb_size; image size unchanged",
        "device_validation": "NOT DONE - image has not been flashed or booted",
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
