#!/usr/bin/env python3
"""HW-D (NX30 R012) QCN6122 board 0x60 BDF for ath11k fw 2.7: OEM bdwlan.b60 verbatim
except the antenna-axis gate byte 0x45c (03 -> 00; non-zero makes fw 2.7 assert
phyrf_bdf.c:6245 ANTENNACHAIN_AXIS_Z), checksum at 0x0a refixed (XOR16 == 0xffff).
usage: build_hwd_qcn6122_bdf.py bdwlan.b60 current-board-2-qcn6122.bin OUT"""
import hashlib, struct, sys
from functools import reduce
from pathlib import Path
H = 84
b60, cur = Path(sys.argv[1]).read_bytes(), Path(sys.argv[2]).read_bytes()
assert hashlib.sha256(b60).hexdigest() == "b1a97c41b305338164ea27711de69ed593c7d61bccceca0acfc6896062411026"
assert b"qmi-board-id=96" in cur[:H]
xr = lambda b: reduce(int.__xor__, struct.unpack(f"<{len(b)//2}H", b), 0)
d = bytearray(b60)
assert d[0x45c] == 3
d[0x45c] = 0
d[0x0a:0x0c] = b"\0\0"
struct.pack_into("<H", d, 0x0a, xr(d) ^ 0xffff)
assert xr(d) == 0xffff
out = cur[:H] + bytes(d)
Path(sys.argv[3]).write_bytes(out)
print("SHA256", hashlib.sha256(out).hexdigest(), len(out))
