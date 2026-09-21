#!/usr/bin/env python3
"""Build the RT3000 QCN6122 compatibility BDF candidate, failing closed.

The shipping Product R1 BDF uses a CMCC 0x60-family payload.  Candidate 4
proved that transplanting the H3C 0x50-family modal header into that payload
mixes incompatible layouts and makes WLAN.HK.2.7.0.1 assert while parsing the
antenna-chain axis.  Candidate 5 instead uses the complete, upstream Elecom
0x50.51-family payload as one internally consistent ath11k-compatible donor,
then replaces only the same bounded Machine-B OEM power/calibration window.
The RT3000 container name and device ART caldata remain device-specific.
"""

import argparse
from functools import reduce
import hashlib
import os
from pathlib import Path
import struct
import tempfile


BOARD_SIZE = 131156
HEADER_SIZE = 84
PATCH_START = 0x2494
PATCH_END = 0x2758
BDF_CHECKSUM_OFFSET = 0x000A
BDF_CHECKSUM_GOAL = 0xFFFF
BASE_SHA256 = "35f512602d6895a6a66cbfec1aade6219fbcfe4d419b66df42952e2374927a25"
PATCH_SHA256 = "894f180fceaa856707758c24142e7d3ec7c1ad485a6ca1b6803302c57324f713"
PREVIOUS_SHA256 = "7857fe4326bebc3063b923bb3bf035e75da94258aef1e6d5a26d4f8dde2a8f1e"
DONOR_SHA256 = "5ca4e0151b0801f3dd23a87a41e3679122359e68e5144bd668200ab0ca245811"
DONOR_BODY_SHA256 = "0382db72a67618f725f4b60b75de027d611f50fcccbb2fc85abb43bb2b43fe80"
OUTPUT_SHA256 = "085a6cca54714ed8387341869bbf1f75b257198e87bd590ddf58f7d155c772fb"
BOARD_NAME = b"bus=ahb,qmi-chip-id=0,qmi-board-id=144"
ATH11K_DATA_IE = struct.pack("<II", 1, 0x20000)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_patch(path: Path) -> bytes:
    fields = []
    for line in path.read_text(encoding="ascii").splitlines():
        fields.append(line.split("#", 1)[0].strip())
    encoded = "".join(fields)
    try:
        patch = bytes.fromhex(encoded)
    except ValueError as exc:
        raise SystemExit(f"invalid hex patch: {exc}") from exc
    if len(patch) != PATCH_END - PATCH_START:
        raise SystemExit(
            f"patch length mismatch: got {len(patch)}, "
            f"want {PATCH_END - PATCH_START}"
        )
    if sha256(patch) != PATCH_SHA256:
        raise SystemExit("patch SHA256 mismatch")
    return patch


def extract_bdf_body(container: bytes) -> bytes:
    """Extract the single 128 KiB board-data IE from an ath11k container."""
    if not container.startswith(b"QCA-ATH11K-BOARD\0"):
        raise SystemExit("donor is not an ath11k board container")
    ie_offset = container.find(ATH11K_DATA_IE, 20, 512)
    if ie_offset < 0:
        raise SystemExit("donor does not contain a 128 KiB board-data IE")
    body_start = ie_offset + len(ATH11K_DATA_IE)
    body = container[body_start : body_start + 0x20000]
    if len(body) != 0x20000:
        raise SystemExit("donor board-data IE is truncated")
    return body


def load_compat_donor(path: Path) -> bytes:
    donor = path.read_bytes()
    if sha256(donor) != DONOR_SHA256:
        raise SystemExit("compatibility donor SHA256 mismatch")
    body = extract_bdf_body(donor)
    if sha256(body) != DONOR_BODY_SHA256:
        raise SystemExit("compatibility donor body SHA256 mismatch")
    if bdf_xor(body) != BDF_CHECKSUM_GOAL:
        raise SystemExit("compatibility donor BDF checksum invalid")
    return body


def validate_container(data: bytes) -> None:
    if len(data) != BOARD_SIZE:
        raise SystemExit(f"board size mismatch: got {len(data)}, want {BOARD_SIZE}")
    if not data.startswith(b"QCA-ATH11K-BOARD\0"):
        raise SystemExit("not an ath11k board-2 container")
    if BOARD_NAME not in data[:HEADER_SIZE]:
        raise SystemExit("container does not select QCN6122 board-id 0x90")


def bdf_xor(body: bytes) -> int:
    if len(body) % 2:
        raise SystemExit("BDF body length must be an even number of bytes")
    return reduce(int.__xor__, struct.unpack(f"<{len(body) // 2}H", body), 0)


def repair_bdf_checksum(body: bytearray) -> None:
    """Set the QCA BDF XOR checksum word so the complete body XOR is 0xffff."""
    body[BDF_CHECKSUM_OFFSET : BDF_CHECKSUM_OFFSET + 2] = b"\0\0"
    checksum = bdf_xor(body) ^ BDF_CHECKSUM_GOAL
    struct.pack_into("<H", body, BDF_CHECKSUM_OFFSET, checksum)
    if bdf_xor(body) != BDF_CHECKSUM_GOAL:
        raise SystemExit("failed to repair BDF XOR checksum")


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp_name = stream.name
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temp_name, mode)
    os.replace(temp_name, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("compat_donor", type=Path)
    args = parser.parse_args()

    source = args.input.read_bytes()
    validate_container(source)
    source_sha = sha256(source)
    if source_sha not in (
        BASE_SHA256,
        PREVIOUS_SHA256,
        OUTPUT_SHA256,
    ):
        raise SystemExit(f"unapproved input SHA256: {source_sha}")

    patch = load_patch(args.patch)
    donor_body = load_compat_donor(args.compat_donor)
    header = source[:HEADER_SIZE]
    body = bytearray(donor_body)
    body[PATCH_START:PATCH_END] = patch
    repair_bdf_checksum(body)
    result = header + bytes(body)

    validate_container(result)
    if sha256(result) != OUTPUT_SHA256:
        raise SystemExit(f"output SHA256 mismatch: {sha256(result)}")

    mode = args.input.stat().st_mode & 0o777
    if args.output == args.input and result == source:
        print(f"BDF_RESULT=PASS_ALREADY_GENERATED SHA256={OUTPUT_SHA256}")
        return
    atomic_write(args.output, result, mode)
    print(f"BDF_RESULT=PASS SHA256={OUTPUT_SHA256}")


if __name__ == "__main__":
    main()
