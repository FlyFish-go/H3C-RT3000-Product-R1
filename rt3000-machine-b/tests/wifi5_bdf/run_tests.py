#!/usr/bin/env python3
"""Offline gates for the RC1-WIFI5-PERF-001 compatibility BDF candidate."""

import hashlib
from functools import reduce
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[3]
H3C = ROOT / "package/firmware/ipq-wifi/board-h3c_rt3000.qcn6122"
PATCH = ROOT / "rt3000-machine-b/bdf/qcn6122-oem-power-table.hex"
DONOR = ROOT / "rt3000-machine-b/bdf/board-elecom_wrc-x3000gs2.qcn6122"
HEADER_SIZE = 84
PATCH_START = 0x2494
PATCH_END = 0x2758
BDF_CHECKSUM_OFFSET = 0x000A
EXPECTED_BDF_CHECKSUM = 0x38F0
EXPECTED_H3C_SHA256 = "085a6cca54714ed8387341869bbf1f75b257198e87bd590ddf58f7d155c772fb"
EXPECTED_PATCH_SHA256 = "894f180fceaa856707758c24142e7d3ec7c1ad485a6ca1b6803302c57324f713"
EXPECTED_DONOR_SHA256 = "5ca4e0151b0801f3dd23a87a41e3679122359e68e5144bd668200ab0ca245811"
EXPECTED_DONOR_BODY_SHA256 = "0382db72a67618f725f4b60b75de027d611f50fcccbb2fc85abb43bb2b43fe80"
ATH11K_DATA_IE = struct.pack("<II", 1, 0x20000)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(condition: bool, name: str) -> None:
    if not condition:
        print(f"FAIL {name}")
        raise SystemExit(1)
    print(f"PASS {name}")


def bdf_xor(body: bytes) -> int:
    return reduce(int.__xor__, struct.unpack(f"<{len(body) // 2}H", body), 0)


def extract_bdf_body(container: bytes) -> bytes:
    offset = container.find(ATH11K_DATA_IE, 20, 512)
    check(offset >= 0, "donor has one 128 KiB board-data IE")
    start = offset + len(ATH11K_DATA_IE)
    body = container[start : start + 0x20000]
    check(len(body) == 0x20000, "donor body length")
    return body


def main() -> None:
    h3c = H3C.read_bytes()
    donor = DONOR.read_bytes()
    patch_hex = "".join(
        line.split("#", 1)[0].strip()
        for line in PATCH.read_text(encoding="ascii").splitlines()
    )
    patch = bytes.fromhex(patch_hex)

    check(len(h3c) == 131156, "RT3000 container size unchanged")
    check(h3c.startswith(b"QCA-ATH11K-BOARD\0"), "ath11k container magic")
    check(
        b"bus=ahb,qmi-chip-id=0,qmi-board-id=144" in h3c[:HEADER_SIZE],
        "RT3000 board-id remains 0x90",
    )
    check(digest(patch) == EXPECTED_PATCH_SHA256, "OEM donor window hash")
    check(len(patch) == PATCH_END - PATCH_START, "OEM donor window length")
    check(digest(donor) == EXPECTED_DONOR_SHA256, "Elecom donor container hash")

    h3c_body = h3c[HEADER_SIZE:]
    donor_body = extract_bdf_body(donor)
    check(digest(donor_body) == EXPECTED_DONOR_BODY_SHA256, "Elecom donor body hash")
    expected_body = bytearray(donor_body)
    expected_body[PATCH_START:PATCH_END] = patch
    expected_body[BDF_CHECKSUM_OFFSET : BDF_CHECKSUM_OFFSET + 2] = h3c_body[
        BDF_CHECKSUM_OFFSET : BDF_CHECKSUM_OFFSET + 2
    ]
    check(bdf_xor(donor_body) == 0xFFFF, "Elecom donor BDF checksum valid")
    check(bdf_xor(h3c_body) == 0xFFFF, "candidate BDF checksum valid")
    check(
        struct.unpack_from("<H", h3c_body, BDF_CHECKSUM_OFFSET)[0]
        == EXPECTED_BDF_CHECKSUM,
        "candidate checksum word is deterministic",
    )
    check(h3c_body == expected_body, "only approved compatibility donor and power window installed")
    check(
        h3c_body[PATCH_START:PATCH_END] == patch,
        "only approved OEM power/calibration window installed",
    )
    check(
        h3c_body[0x2760:0x2780] == donor_body[0x2760:0x2780],
        "axis-sensitive structure comes from one compatible 0x50.51 donor",
    )
    check(h3c_body[0x003A:0x003C] == b"\x50\x51", "compatible BDF layout version is 0x50.51")
    check(digest(h3c) == EXPECTED_H3C_SHA256, "candidate full SHA256")
    print("WIFI5_BDF_TESTS=PASS")


if __name__ == "__main__":
    main()
