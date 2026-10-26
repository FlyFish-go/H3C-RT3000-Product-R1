#!/usr/bin/env python3
"""HW-A (RW3000) QCN6122 board 0x90 BDF for ath11k fw 2.7, comparison candidate:
the unit's OEM bdwlan.b90 verbatim except the antenna-axis gate byte 0x45c
(03 -> 00; non-zero makes fw 2.7 assert phyrf_bdf.c:6245 ANTENNACHAIN_AXIS_Z),
checksum at 0x0a refixed (XOR16 == 0xffff). Container header is HW-B's board 0x90 one.
usage: build_hwa_qcn6122_bdf.py bdwlan.b90 board-h3c_rt3000.qcn6122 OUT"""
import hashlib, struct, sys
from functools import reduce
from pathlib import Path
H = 84
b90, cur = Path(sys.argv[1]).read_bytes(), Path(sys.argv[2]).read_bytes()
assert hashlib.sha256(b90).hexdigest() == "fec06dc5cfad170fdc4f463031cf9743cb188e2fe62991de5a9dc973d5459960"
assert b"qmi-board-id=144" in cur[:H] and len(cur) == H + len(b90)
xr = lambda b: reduce(int.__xor__, struct.unpack(f"<{len(b)//2}H", b), 0)
d = bytearray(b90)
assert d[0x45c] == 3 and xr(d) == 0xffff
d[0x45c] = 0
d[0x0a:0x0c] = b"\0\0"
struct.pack_into("<H", d, 0x0a, xr(d) ^ 0xffff)
assert xr(d) == 0xffff
out = cur[:H] + bytes(d)
Path(sys.argv[3]).write_bytes(out)
print("SHA256", hashlib.sha256(out).hexdigest(), len(out))
