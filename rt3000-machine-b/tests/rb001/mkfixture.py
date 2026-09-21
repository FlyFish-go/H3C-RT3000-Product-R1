#!/usr/bin/env python3
"""Build a synthetic RT3000 BOOTCONFIG erase block for rt3bcwrite tests."""
import struct, sys, os

BC_EFF = 0x150
BC_HDR = 12
BC_ENT = 20
BC_NAME_LEN = 16
BC_SEL_OFF = 16
BC_COUNT = 8
BC_MAGIC = 0xa3a2a1a0
BC_TAIL = 0xb3b2b1b0
SEL_OFF = 0x080
REC_INDEX = 5

RECORDS = ["sbl1", "mibib", "bootconfig", "bootconfig1", "qsee",
           "rootfs", "rootfs_1", "pdt_data"]

def build(sel=1, magic=BC_MAGIC, version=1, count=BC_COUNT, tail=BC_TAIL,
          records=None, oem_blob=True, block_size=4096):
    recs = records if records is not None else RECORDS
    b = bytearray(b'\xff' * block_size)
    struct.pack_into("<I", b, 0x000, magic)
    struct.pack_into("<I", b, 0x004, version)
    struct.pack_into("<I", b, 0x008, count)
    for i, name in enumerate(recs):
        off = BC_HDR + i * BC_ENT
        nm = name.encode()
        b[off:off+len(nm)] = nm
        b[off+len(nm)] = 0
        struct.pack_into("<I", b, off + BC_SEL_OFF, sel)
    struct.pack_into("<I", b, 0x14c, tail)
    # OEM configuration blob sharing mtd2's erase block, past ~0x880
    if oem_blob:
        blob = b"RT3000-OEM-CONFIG-BLOB\x00" + bytes(range(256)) * 2
        b[0x880:0x880+len(blob)] = blob[:block_size-0x880]
    return bytes(b)

def write(path, data):
    with open(path, "wb") as f:
        f.write(data)

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "good":
        out, sel = sys.argv[2], int(sys.argv[3], 0)
        write(out, build(sel=sel))
    elif cmd == "raw":
        # raw <out> <sel> <field=value>...  e.g. magic=0xdeadbeef
        out = sys.argv[2]; sel = int(sys.argv[3], 0)
        kw = {}
        for a in sys.argv[4:]:
            k, v = a.split("=", 1)
            kw[k] = int(v, 0) if not v.startswith("[") else v
        # records override
        if "records" in kw:
            kw["records"] = kw["records"].strip("[]").split(",")
        write(out, build(sel=sel, **kw))
    elif cmd == "oem":
        # write a known OEM blob over an existing fixture at 0x880
        out = sys.argv[2]
        d = bytearray(open(out, "rb").read())
        blob = b"RT3000-OEM-CONFIG-BLOB\x00" + bytes(range(256)) * 2
        d[0x880:0x880+len(blob)] = blob[:len(d)-0x880]
        write(out, bytes(d))
    else:
        raise SystemExit("unknown cmd")
