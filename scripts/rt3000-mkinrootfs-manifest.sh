#!/bin/sh
# rt3000-mkinrootfs-manifest.sh
#
# Write the in-rootfs release identity manifest.
#
# Usage:
#   rt3000-mkinrootfs-manifest.sh <kernel-image> <staging-rootfs-dir> [release] [netbaseline]
#
# ---------------------------------------------------------------------------
# What goes in, and what deliberately does not
# ---------------------------------------------------------------------------
# The manifest that ships inside the rootfs records:
#   - schema / product / machine / release / network_baseline  (stable metadata)
#   - kernel_sha256  (the running kernel volume payload)
#
# It deliberately does NOT record rootfs_sha256: the manifest is itself part of
# the rootfs, so embedding the rootfs' own hash would be circular, and any
# scheme that "solves" that by excluding the manifest from the measurement
# weakens the guarantee.
#
# The rootfs half of the identity therefore lives in the EXTERNAL manifest that
# scripts/rt3000-mkmanifest.sh emits next to the finished images, and is checked
# by `rt3release verify-rootfs <payload> --manifest <external.json>`.  This is
# the check the installer and hardware acceptance use.
#
# The staging rootfs directory is re-squashfs'd by the normal image build
# afterwards, so writing here lands inside the shipped rootfs.

set -e

KERNEL="$1"
ROOTFSDIR="$2"
RELEASE="${3:-Product R1 RC1}"
NETBASE="${4:-R1-NET-D}"

[ -r "$KERNEL" ]    || { echo "kernel image not readable: $KERNEL" >&2; exit 1; }
[ -d "$ROOTFSDIR" ] || { echo "staging rootfs dir not found: $ROOTFSDIR" >&2; exit 1; }

FSZ=$(python3 - "$KERNEL" <<'PYX'
import struct,sys
d=open(sys.argv[1],'rb').read(8)
if len(d)<8 or d[0:4]!=b'\xd0\x0d\xfe\xed':
    raise SystemExit("not a FIT/DTB: %s" % sys.argv[1])
print(struct.unpack_from('>I',d,4)[0])
PYX
)
KSHA=$(head -c "$FSZ" "$KERNEL" | sha256sum | cut -d' ' -f1)

mkdir -p "$ROOTFSDIR/etc"
cat > "$ROOTFSDIR/etc/rt3000-release.json" <<EOF
{
  "schema": "rt3000-release/v1",
  "product": "H3C Magic RT3000",
  "machine": "Machine-B",
  "release": "$RELEASE",
  "network_baseline": "$NETBASE",
  "kernel_sha256": "$KSHA"
}
EOF

echo "RT3000_IN_ROOTFS_MANIFEST=$ROOTFSDIR/etc/rt3000-release.json"
echo "  kernel_sha256=$KSHA"
