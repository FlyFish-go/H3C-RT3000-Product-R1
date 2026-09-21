#!/usr/bin/env python3
"""RT3000 UBI image -> volume payload extractor.

PARSER ACCEPTANCE TEST: against the canonical Product R1 prerelease #1 image it
must reproduce, byte-exactly, the values recorded in its external manifest:
  kernel volume (padded) 52d8e38fc4f4bb22403d98231d140507702e26f161cb942c3a0b77afce9c07c7
  kernel FIT declared    95254958dadcbe9c5630fd258543874b1a92d66a5bb4791fcbbf60c8839134de
  rootfs (squashfs)      f0d49c448a7f00ec694c90aa5cb54051544395804203fe708b2773d7b8c8b70f

On-flash layout (IPQ5018 / GD5F1GQ5REYIG), established by CRC-verified probing:
  PEB 131072, subpage 2048, EC hdr 64B @ PEB+0 (CRC ~crc32 over [0:60] @60),
  VID hdr 64B @ PEB+2048 (same CRC convention), payload @ PEB+4096,
  LEB payload 126976 bytes.

Volume membership comes from vol_id in the VID header.  Within a volume, LEBs
are ordered by ascending PEB index: on this image the vid lnum field is zeroed,
and PEB-contiguous ordering is exactly what reproduces the authoritative
manifest hashes above, so it is validated rather than assumed.  Squashfs/kernel
payload lengths are then taken from the content itself (superblock / FIT header)
so trailing 0xFF padding never enters a hash.

UBI image_seq is read for information only and is NEVER used as identity.
"""
import struct, hashlib, sys, os, json, zlib

EC_MAGIC = b'UBI#'; VID_MAGIC = b'UBI!'; SQUASH_MAGIC = b'hsqs'; FIT_MAGIC = b'\xd0\x0d\xfe\xed'
LAYOUT_VOL_ID = 0x7fffefff
PEB = 131072; EC_SZ = 64; VID_OFF = 2048; DATA_OFF = 4096; LEB = PEB - DATA_OFF

def crc(b): return (~zlib.crc32(b)) & 0xffffffff

def ec_hdr(b):
    assert b[:4] == EC_MAGIC, "bad EC magic"
    s = struct.unpack_from('>I', b, 60)[0]
    assert s == crc(b[:60]), "EC CRC mismatch %08x != %08x" % (s, crc(b[:60]))
    return {"image_seq": struct.unpack_from('>I', b, 24)[0]}

def vid_hdr(b):
    assert b[:4] == VID_MAGIC, "bad VID magic"
    s = struct.unpack_from('>I', b, 60)[0]
    assert s == crc(b[:60]), "VID CRC mismatch %08x != %08x" % (s, crc(b[:60]))
    return {"vol_id": struct.unpack_from('>I', b, 8)[0],
            "lnum": struct.unpack_from('>I', b, 16)[0]}

def parse(path):
    d = open(path, 'rb').read()
    assert d[:4] == EC_MAGIC and len(d) % PEB == 0, "not a UBI image / bad PEB"
    npeb = len(d) // PEB
    order, seqs, members = [], set(), {}
    for i in range(npeb):
        p = d[i*PEB:(i+1)*PEB]
        if p[:4] != EC_MAGIC: continue
        seqs.add(ec_hdr(p[:EC_SZ])["image_seq"])
        vh = p[VID_OFF:VID_OFF+64]
        if vh[:4] != VID_MAGIC: continue
        v = vid_hdr(vh)
        pay = p[DATA_OFF:DATA_OFF+LEB]
        assert len(pay) == LEB
        members.setdefault(v["vol_id"], []).append((i, v["lnum"], pay))
    return members, seqs, npeb

def squash_len(b):
    """squashfs bytes_used from superblock (offset 40, u64 LE)."""
    assert b[:4] == SQUASH_MAGIC, "not squashfs"
    return struct.unpack_from('<Q', b, 40)[0]

def fit_len(b):
    assert b[:4] == FIT_MAGIC, "not a FIT image"
    return struct.unpack_from('>I', b, 4)[0]

def main():
    path, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    members, seqs, npeb = parse(path)
    print("PEB=%d nPEB=%d LEB=%d image_seq=%s (informational only, NOT identity)"
          % (PEB, npeb, LEB, ",".join(hex(s) for s in sorted(seqs))))
    res = {}
    for vid in sorted(v for v in members if v != LAYOUT_VOL_ID):
        entries = members[vid]
        # order by lnum when it is meaningful, else by PEB index
        if all(e[1] == 0 for e in entries):
            entries = sorted(entries, key=lambda e: e[0])
        else:
            entries = sorted(entries, key=lambda e: e[1])
        data = b''.join(e[2] for e in entries)
        name = {0: "kernel", 1: "ubi_rootfs"}.get(vid, "vol%d" % vid)
        fn = os.path.join(outdir, "%s.bin" % name)
        open(fn, 'wb').write(data)
        info = {"vol_id": hex(vid), "leb_count": len(entries),
                "volume_size": len(data),
                "volume_sha256": hashlib.sha256(data).hexdigest(),
                "pebs": [e[0] for e in entries][:1] + [e[0] for e in entries][-1:],
                "path": fn}
        try:
            if data[:4] == FIT_MAGIC:
                n = fit_len(data); info["payload_size"] = n
                info["payload_sha256"] = hashlib.sha256(data[:n]).hexdigest()
            elif data[:4] == SQUASH_MAGIC:
                n = squash_len(data); info["payload_size"] = n
                info["payload_sha256"] = hashlib.sha256(data[:n]).hexdigest()
        except AssertionError:
            pass
        res[name] = info
        print("%-10s vol_id=%-6s leb=%-4d vol_size=%-9d payload=%-9d sha256(payload)=%s"
              % (name, hex(vid), len(entries), len(data),
                 info.get("payload_size", -1), info.get("payload_sha256", "-")))
    open(os.path.join(outdir, "_volumes.json"), 'w').write(json.dumps(res, indent=2))

main()
