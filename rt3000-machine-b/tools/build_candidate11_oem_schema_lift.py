#!/usr/bin/env python3
"""Fail-closed Candidate 11 OEM-body/schema-lift generator.

The input is the complete Machine-B OEM bdwlan.b90 body.  Candidate 11
changes exactly one schema byte (payload 0x045c, 03 -> 00), then recomputes
the little-endian XOR16 word at [0x000a, 0x000c).  The existing 84-byte
RT3000 ath11k container header is retained verbatim; no other body byte is
permitted to change.
"""

from functools import reduce
import hashlib
from pathlib import Path
import struct
import sys

BODY_SIZE = 0x20000
HEADER_SIZE = 84
CHECKSUM_OFFSET = 0x000A
SCHEMA_OFFSET = 0x045C
SCHEMA_OLD = b"\x03\x00"
SCHEMA_NEW = b"\x00\x00"
VERSION_OFFSET = 0x003A
VERSION = b"\x50\x52"
XOR_GOAL = 0xFFFF
INPUT_SHA256 = "fec06dc5cfad170fdc4f463031cf9743cb188e2fe62991de5a9dc973d5459960"
CONTAINER_SHA256 = "085a6cca54714ed8387341869bbf1f75b257198e87bd590ddf58f7d155c772fb"
OUTPUT_BODY_SHA256 = "5c76bbe511c55cfa5cf31388d09713aefbe8364d3656bac93d8634279985adad"
OUTPUT_CONTAINER_SHA256 = "e5bd210bfb572ceae15eb132fc5f9950578f171268e5230bed026dbb539c73e3"
OUTPUT_CHECKSUM = 0x4FBD


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def xor16(data: bytes) -> int:
    if len(data) % 2:
        raise SystemExit("odd-sized XOR input")
    return reduce(int.__xor__, struct.unpack(f"<{len(data)//2}H", data), 0)


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def build(body_path: Path, baseline_path: Path, output_path: Path) -> None:
    source = body_path.read_bytes()
    if len(source) != BODY_SIZE:
        fail(f"OEM body length {len(source)} != {BODY_SIZE}")
    if sha(source) != INPUT_SHA256:
        fail("OEM body SHA256 mismatch")
    if source[VERSION_OFFSET:VERSION_OFFSET + 2] != VERSION:
        fail("OEM body schema/version marker is not 0x50.52")
    if source[SCHEMA_OFFSET:SCHEMA_OFFSET + 2] != SCHEMA_OLD:
        fail("OEM body schema byte is not exactly 0x03 at 0x045c")
    if xor16(source) != XOR_GOAL:
        fail("OEM body input XOR16 is not 0xffff")

    baseline = baseline_path.read_bytes()
    if len(baseline) != HEADER_SIZE + BODY_SIZE:
        fail("Candidate6 container length mismatch")
    if sha(baseline) != CONTAINER_SHA256:
        fail("Candidate6 container SHA256 mismatch")
    if not baseline.startswith(b"QCA-ATH11K-BOARD\0"):
        fail("Candidate6 container magic mismatch")

    result_body = bytearray(source)
    result_body[SCHEMA_OFFSET:SCHEMA_OFFSET + 2] = SCHEMA_NEW
    result_body[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 2] = b"\0\0"
    struct.pack_into("<H", result_body, CHECKSUM_OFFSET, xor16(result_body) ^ XOR_GOAL)
    if struct.unpack_from("<H", result_body, CHECKSUM_OFFSET)[0] != OUTPUT_CHECKSUM:
        fail("recomputed checksum is not 0x4fbd")
    if xor16(result_body) != XOR_GOAL:
        fail("output body XOR16 is not 0xffff")
    for offset, size in ((0, CHECKSUM_OFFSET), (CHECKSUM_OFFSET + 2, SCHEMA_OFFSET - CHECKSUM_OFFSET - 2),
                         (SCHEMA_OFFSET + 2, BODY_SIZE - SCHEMA_OFFSET - 2)):
        if result_body[offset:offset + size] != source[offset:offset + size]:
            fail(f"unexpected body mutation near 0x{offset:04x}")
    if sha(bytes(result_body)) != OUTPUT_BODY_SHA256:
        fail("output body SHA256 mismatch")

    container = baseline[:HEADER_SIZE] + bytes(result_body)
    if sha(container) != OUTPUT_CONTAINER_SHA256:
        fail("output container SHA256 mismatch")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(container)
    print(f"PASS body_sha256={OUTPUT_BODY_SHA256} container_sha256={OUTPUT_CONTAINER_SHA256}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: build_candidate11_oem_schema_lift.py BODY CANDIDATE6_CONTAINER OUTPUT")
    build(*(Path(arg) for arg in sys.argv[1:]))
