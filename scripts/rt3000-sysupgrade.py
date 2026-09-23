#!/usr/bin/env python3
"""Build a deterministic, Machine-B-only sysupgrade archive (metadata added by make)."""
import hashlib
import io
import json
import os
import struct
import sys
import tarfile
from pathlib import Path

kernel, root, output = map(Path, sys.argv[1:])
k, r = kernel.read_bytes(), root.read_bytes()
if len(k) < 8 or k[:4] != b'\xd0\x0d\xfe\xed':
    raise SystemExit('invalid kernel FIT')
size = struct.unpack('>I', k[4:8])[0]
if size != len(k) or size < 40 or r[:4] != b'hsqs':
    raise SystemExit('invalid FIT length or squashfs magic')
if not (0 < len(k) <= 8388608 and 0 < len(r) <= 25165824):
    raise SystemExit('payload exceeds Machine-B upgrade limits')
manifest = dict(schema='rt3000-sysupgrade/v1', board='h3c,rt3000', machine='Machine-B',
                slot=16, page_size=2048, erase_size=131072, oob_size=128,
                kernel_size=len(k), rootfs_size=len(r),
                kernel_sha256=hashlib.sha256(k).hexdigest(),
                rootfs_sha256=hashlib.sha256(r).hexdigest())
prefix = 'sysupgrade-h3c_rt3000/'
with tarfile.open(output, 'w', format=tarfile.USTAR_FORMAT) as archive:
    for name, payload in [('CONTROL', b'BOARD=h3c_rt3000\n'),
                          ('manifest.json', (json.dumps(manifest, sort_keys=True) + '\n').encode()),
                          ('kernel', k), ('root', r)]:
        info = tarfile.TarInfo(prefix + name)
        info.size = len(payload)
        info.mode = 0o644
        info.mtime = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
        archive.addfile(info, io.BytesIO(payload))
