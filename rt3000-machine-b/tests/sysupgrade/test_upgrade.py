#!/usr/bin/env python3
"""Exercise the real shell gates in an isolated user-namespace chroot.

Uses real BusyBox ash/tar, fwtool and jsonfilter. Only flash/boot/mount tools
are mocked. No host /dev or /sys is visible inside the sandbox.
"""
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
JSONFILTER = Path(os.environ.get('RT3_JSONFILTER_HOST', REPO / 'staging_dir/host/bin/jsonfilter'))
HELPER = REPO / 'target/linux/ipq50xx/base-files/lib/upgrade/rt3000.sh'
FWTOOL = REPO / 'staging_dir/host/bin/fwtool'
FWTOOL = Path(os.environ.get('RT3_FWTOOL_HOST', FWTOOL))
SYSUPGRADE_IMAGE = Path(os.environ.get(
    'RT3_SYSUPGRADE_IMAGE',
    REPO / 'bin/targets/ipq50xx/arm/openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-sysupgrade.bin'))
KERNEL = b'\xd0\x0d\xfe\xed' + struct.pack('>I', 4096) + b'K' * 4088
ROOT = b'hsqs' + b'R' * 8192
PREFIX = 'sysupgrade-h3c_rt3000/'
RESULTS = []

MOCK = r'''#!/bin/sh
name=${0##*/}
echo "$name $*" >> /calls
[ "$(cat /fail)" != "$name $*" ] || exit 1
[ "$(cat /fail)" != "$name $1" ] || exit 1
case "$name" in
rt3bcwrite)
 case "$1" in
 --verify-only) [ "$(cat /selector)" = "$2" ]; exit $?;;
 --set) echo "$2" > /selector;;
 *) exit 1;;
 esac;;
ubidetach)
 # Detaching removes the ubi device, its volume entries and its /dev nodes.
 rm -rf /sys/devices/virtual/ubi/ubi0 /sys/class/ubi/ubi0
 rm -f /dev/ubi0 /dev/ubi0_0 /dev/ubi0_1 /dev/ubi0_2 /dev/ubiblock0_1;;
ubiformat)
 [ "$1" = /dev/mtd16 ] || exit 99
 [ "$(cat /selector)" = 0 ] || exit 98
 # A freshly formatted mtd16 has no ubi device attached at all.
 rm -rf /sys/devices/virtual/ubi/ubi0 /sys/class/ubi/ubi0
 rm -f /dev/ubi0 /dev/ubi0_0 /dev/ubi0_1 /dev/ubi0_2;;
ubiattach)
 # Real kernel behaviour: only sysfs entries appear.  Device nodes are NOT
 # created (the initramfs runs no mdev/hotplug helper); the upgrade code is
 # required to mknod them from <sysfs>/dev.  This is the defect under test.
 mkdir -p /sys/devices/virtual/ubi/ubi0 /sys/class/ubi/ubi0
 echo 16 > /sys/devices/virtual/ubi/ubi0/mtd_num
 echo 242:0 > /sys/devices/virtual/ubi/ubi0/dev
 echo 16 > /sys/class/ubi/ubi0/mtd_num
 rm -f /dev/ubi0 /dev/ubi0_0 /dev/ubi0_1 /dev/ubi0_2;;
ubimkvol)
 # The kernel creates the volume sysfs entry; the /dev node exists only if the
 # upgrade code mknod'ed it beforehand.  This mirrors the real failure:
 #   ubimkvol: error!: error while probing "/dev/ubi0"
 #   error 2 (No such file or directory)
 # The ubi DEVICE node must exist; the volume node is created by this very
 # command, so it cannot be required beforehand.  A missing device node is
 # exactly the real-world failure: "cannot open /dev/ubi0".
 [ -e "/dev/ubi0" ] || { echo "ubimkvol: cannot open /dev/ubi0: No such file or directory" >&2; exit 1; }
 mkdir -p "/sys/devices/virtual/ubi/ubi0/ubi0_$3"
 echo "vol$3" > "/sys/devices/virtual/ubi/ubi0/ubi0_$3/name"
 echo "242:$((1+$3))" > "/sys/devices/virtual/ubi/ubi0/ubi0_$3/dev";;
ubiupdatevol)
 cp "$2" "$1" || exit 1
 [ "$(cat /corrupt)" != "$1" ] || echo damaged > "$1";;
ubiblock)
 # A stale node is not a character device on real hardware, so ubiblock fails
 # with EINVAL.  Emulate that faithfully: the upgrade code must never depend on
 # ubiblock succeeding here.
 echo "ubiblock: error!: \"$2\" is not a character device" >&2
 exit 1;;
mount) [ "$(cat /fail)" != mount ] || exit 1;;
umount) [ "$(cat /fail)" != umount ] || exit 1;;
cp)
 [ "$(cat /fail)" != backup-copy ] || exit 1
 /bin/busybox cp "$@";;
*) exit 1;;
esac
'''

def put(root, name, data):
    p = root / name.lstrip('/')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)
    return p

def image(path, mutation=None):
    manifest = dict(schema='rt3000-sysupgrade/v1', board='h3c,rt3000', machine='Machine-B',
                    slot=16, page_size=2048, erase_size=131072, oob_size=128,
                    kernel_size=len(KERNEL), rootfs_size=len(ROOT),
                    kernel_sha256=hashlib.sha256(KERNEL).hexdigest(),
                    rootfs_sha256=hashlib.sha256(ROOT).hexdigest())
    meta = dict(supported_devices=['h3c,rt3000'], compat_version='1.0')
    entries = [('CONTROL', b'BOARD=h3c_rt3000\n'), ('kernel', KERNEL), ('root', ROOT)]
    if mutation == 'wrong-manifest-board': manifest['board'] = 'xiaomi,cr881x'
    if mutation == 'wrong-manifest-slot': manifest['slot'] = 15
    if mutation == 'wrong-metadata-board': meta['supported_devices'] = ['h3c,other']
    if mutation == 'wrong-compat': meta['compat_version'] = '2.0'
    if mutation == 'bad-hash': manifest['rootfs_sha256'] = '0' * 64
    if mutation == 'bad-size': manifest['kernel_size'] = len(KERNEL) + 1
    if mutation == 'bad-fit':
        k = b'WRNG' + KERNEL[4:]; entries[1] = ('kernel', k)
        manifest['kernel_sha256'] = hashlib.sha256(k).hexdigest()
    if mutation == 'bad-fit-length':
        k = KERNEL[:4] + struct.pack('>I', 123) + KERNEL[8:]; entries[1] = ('kernel', k)
        manifest['kernel_sha256'] = hashlib.sha256(k).hexdigest()
    if mutation == 'bad-squashfs':
        r = b'WRNG' + ROOT[4:]; entries[2] = ('root', r)
        manifest['rootfs_sha256'] = hashlib.sha256(r).hexdigest()
    entries.append(('manifest.json', json.dumps(manifest).encode()))
    if mutation == 'extra': entries.append(('extra', b'x'))
    if mutation == 'traversal': entries[-1] = ('../manifest.json', b'x')
    if mutation == 'duplicate': entries[-1] = entries[0]
    if mutation == 'missing': entries.pop()
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in entries:
            info = tarfile.TarInfo(PREFIX + name)
            if mutation == 'link' and name == 'root':
                info.type = tarfile.SYMTYPE; info.linkname = '/dev/mtd15'
                archive.addfile(info)
            else:
                info.size = len(data); archive.addfile(info, io.BytesIO(data))
    if mutation == 'truncated': path.write_bytes(path.read_bytes()[:4000])
    if mutation != 'no-metadata':
        subprocess.run([str(FWTOOL), '-I', '-', str(path)], input=json.dumps(meta).encode(), check=True)

def case(name, mutation=None, write=False, fault='', expected=False, backup=False):
    with tempfile.TemporaryDirectory(prefix='rt3-upgrade-test-') as tmp:
        root = Path(tmp)
        for d in ['bin','tmp','dev','proc','sys/class/ubi','lib64','lib/x86_64-linux-gnu']:
            (root/d).mkdir(parents=True, exist_ok=True)
        shutil.copy('/usr/bin/busybox', root/'bin/busybox')
        apps = subprocess.check_output(['/usr/bin/busybox','--list'], text=True).splitlines()
        for app in apps:
            if app != 'busybox': (root/'bin'/app).symlink_to('busybox')
        for src, dst in [(FWTOOL,'bin/fwtool'), (JSONFILTER,'bin/jsonfilter'),
                         (Path('/lib/x86_64-linux-gnu/libc.so.6'),'lib/x86_64-linux-gnu/libc.so.6'),
                         (Path('/lib64/ld-linux-x86-64.so.2'),'lib64/ld-linux-x86-64.so.2')]:
            shutil.copy(src,root/dst)
        shutil.copy(HELPER, root/'helper.sh')
        for tool in ['rt3bcwrite','ubidetach','ubiformat','ubiattach','ubimkvol','ubiupdatevol','ubiblock','mount','umount','cp']:
            p = root/'bin'/tool
            if p.is_symlink(): p.unlink()
            p.write_text(MOCK);p.chmod(0o755)
        put(root,'selector','1\n');put(root,'fail',fault);put(root,'corrupt','')
        put(root,'proc/cmdline','mtdparts=qcom_nand.0:0x2800000@0x900000(oem_rootfs)ro,0x2800000@0x3100000(rootfs)')
        put(root,'proc/mounts','')
        put(root,'dev/mtd15',b'UBI#' + b'OEM-PRESERVE' * 1024)
        put(root,'dev/mtd16',b'OLD-QSDK')
        for part, label in [(2,'0:BOOTCONFIG'),(3,'0:BOOTCONFIG1'),(15,'oem_rootfs'),(16,'rootfs')]:
            for attr,val in dict(name=label,type='nand',size=(262144 if part in (2,3) else 41943040),erasesize=131072,writesize=2048,oobsize=128).items():
                put(root,f'sys/class/mtd/mtd{part}/{attr}',str(val)+'\n')
        # Pre-attach state on the real device: NO ubi device is attached, so
        # /sys/devices/virtual/ubi is empty.  Only ubiattach creates entries.
        (root/'sys/devices/virtual/ubi').mkdir(parents=True,exist_ok=True)
        (root/'sys/class/ubi').mkdir(parents=True,exist_ok=True)
        put(root,'dev/ubi_ctrl','')
        if mutation == 'a-c-nand': put(root,'sys/class/mtd/mtd16/oobsize','64\n')
        if mutation == 'wrong-partition-name': put(root,'sys/class/mtd/mtd16/name','oem_rootfs\n')
        if mutation == 'wrong-offset': put(root,'proc/cmdline','0x2800000@0x900000(rootfs)')
        if mutation == 'bad-oem': put(root,'dev/mtd15','broken')
        if mutation == 'bad-bootconfig': put(root,'selector','diverged')
        if mutation == 'mounted-root': put(root,'proc/mounts','/dev/ubiblock0_1 /rom squashfs ro 0 0\n')
        if mutation == 'nand2nand':
            # NAND-to-NAND: the running QSDK rootfs lives on mtd16, so ubi0 is
            # ALREADY attached to mtd16 when the upgrade starts.  This is the
            # normal case for an in-place upgrade and must be released with
            # ubidetach before ubiformat - never refused.  The ubiblock for
            # volume 1 (rootfs) is also present and must be removed first.
            put(root,'sys/devices/virtual/ubi/ubi0/mtd_num','16\n')
            put(root,'sys/devices/virtual/ubi/ubi0/dev','242:0\n')
            put(root,'sys/class/ubi/ubi0/mtd_num','16\n')
            # A stale node lingers in /dev after the live rootfs is unmounted.
            # Real hardware had exactly this and ubiblock failed with EINVAL.
            put(root,'dev/ubiblock0_1','')
        if mutation == 'bad-readback': put(root,'corrupt','/dev/ubi0_1')
        if backup:
            with tarfile.open(root/'tmp/sysupgrade.tgz','w:gz') as t:
                data=b'config preserved\n';info=tarfile.TarInfo('etc/config/test');info.size=len(data);t.addfile(info,io.BytesIO(data))
        if mutation == 'built-image':
            shutil.copy(SYSUPGRADE_IMAGE,root/'tmp/image.bin')
        else:
            image(root/'tmp/image.bin', mutation)
        oem_before=(root/'dev/mtd15').read_bytes()
        board='wrong' if mutation == 'wrong-board' else 'h3c,rt3000'
        command='umount() { /bin/umount "$@"; }; cp() { /bin/cp "$@"; }; '
        # Shadow the mknod applet: unprivileged userns cannot create char
        # devices.  Record the exact major:minor the code read from sysfs.
        command+='mknod() { echo "mknod $*" >> /calls; '
        command+='[ "$2" = c ] || return 1; '
        command+='case "$1" in /dev/*) ;; *) return 1;; esac; '
        command+='[ -n "$3" ] && [ -n "$4" ] || return 1; '
        command+='printf "%s:%s" "$3" "$4" > "$1.major_minor"; : > "$1"; }; '
        command+=f'export PATH=/bin; board_name() {{ echo "{board}"; }}; . /helper.sh; '
        if backup:command+='UPGRADE_BACKUP=/tmp/sysupgrade.tgz; '
        command+=('rt3_upgrade_write' if write else 'rt3_upgrade_check')+' /tmp/image.bin'
        run=subprocess.run(['unshare','-Ur','chroot',str(root),'/bin/ash','-c',command],capture_output=True,text=True)
        calls=(root/'calls').read_text().splitlines() if (root/'calls').exists() else []
        writes=[c for c in calls
                if not c.startswith('rt3bcwrite --verify-only')
                and not c.startswith('mknod ')]
        assert (run.returncode==0)==expected,(name,run.returncode,run.stdout,run.stderr,calls)
        assert (root/'dev/mtd15').read_bytes()==oem_before,name
        if not write or mutation in ['wrong-board','a-c-nand','wrong-partition-name','wrong-offset','bad-oem','bad-bootconfig','mounted-root','wrong-ubi','bad-hash']:
            assert not writes,(name,writes)
        if write and expected:
            assert calls.index('rt3bcwrite --set 0') < calls.index('ubiformat /dev/mtd16 -y -s 2048 -O 2048') < calls.index('rt3bcwrite --set 1')
            assert (root/'dev/ubi0_0').read_bytes()==KERNEL
            assert (root/'dev/ubi0_1').read_bytes()==ROOT
            # The /dev nodes must have been created via mknod during the run.
            mn=[c for c in calls if c.startswith('mknod ')]
            for node in ['/dev/ubi0','/dev/ubi0_0','/dev/ubi0_1','/dev/ubi0_2']:
                assert any(node in c for c in mn),(name,node,mn)
        if write and not expected:
            assert 'rt3bcwrite --set 1' not in calls,(name,calls)
        RESULTS.append(dict(name=name,result='PASS',returncode=run.returncode))
        print('PASS',name)

case('built-image-check','built-image',expected=True)
case('valid-check',expected=True)
for mutation in ['wrong-board','a-c-nand','wrong-partition-name','wrong-offset','bad-oem','bad-bootconfig',
                 'wrong-manifest-board','wrong-manifest-slot','wrong-metadata-board','wrong-compat',
                 'bad-hash','bad-size','bad-fit','bad-fit-length','bad-squashfs','extra','traversal',
                 'duplicate','missing','link','truncated','no-metadata']:
    case(mutation,mutation)
case('valid-write',write=True,expected=True)
case('valid-config-preserve',write=True,expected=True,backup=True)
for mutation in ['wrong-board','a-c-nand','bad-hash','mounted-root','bad-readback']:
    case('stage2-'+mutation,mutation,write=True)
# NAND-to-NAND: mtd16 already attached -> must detach and proceed (not refuse).
case('nand2nand-write',write=True,expected=True,mutation='nand2nand')
case('nand2nand-config-preserve',write=True,expected=True,mutation='nand2nand',backup=True)
for fault in ['rt3bcwrite --set 0', 'ubiformat /dev/mtd16 -y -s 2048 -O 2048',
              'ubiattach -m 16 -O 2048',f'ubimkvol /dev/ubi0 -n 0 -N kernel -s {len(KERNEL)}',
              f'ubimkvol /dev/ubi0 -n 1 -N ubi_rootfs -s {len(ROOT)}','ubimkvol /dev/ubi0 -n 2 -N rootfs_data -m',
              'ubiupdatevol /dev/ubi0_0','ubiupdatevol /dev/ubi0_1',
              'mount','umount','backup-copy']:
    case('fault-'+fault,write=True,fault=fault,backup=True)
report_path = os.environ.get('RT3_TEST_REPORT')
if report_path:
    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(RESULTS, indent=2) + '\n')
print(f'{len(RESULTS)} checks passed')
