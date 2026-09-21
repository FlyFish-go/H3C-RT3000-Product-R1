#!/bin/sh
# rt3000-mkmanifest.sh - build the Product R1 external release identity manifest.
#
# Usage:
#   rt3000-mkmanifest.sh <fit-kernel-itb> <rootfs-squashfs> <out.json> [release] [netbaseline]
#
# ---------------------------------------------------------------------------
# Identity model (RB002)
# ---------------------------------------------------------------------------
# kernel_sha256 : SHA-256 over the FIT image's DECLARED length.
#                 The UBI kernel volume is the FIT padded with 0xFF to the
#                 erase-block boundary, so hashing the declared extent makes the
#                 kernel identity independent of volume padding and block size.
# rootfs_sha256 : SHA-256 over the squashfs rootfs payload, at the exact length
#                 recorded as rootfs_size.
#
# Both are STABLE CONTENT.  No UBI image_seq, EC counter, VID header or PEB
# placement participates in identity anywhere in this chain.
#
# ---------------------------------------------------------------------------
# Why the manifest is emitted beside the image, not inside it
# ---------------------------------------------------------------------------
# The manifest records the rootfs' own hash.  Embedding that value inside the
# rootfs is circular: writing it changes the squashfs, which changes the hash.
# The in-rootfs manifest (scripts/rt3000-mkinrootfs-manifest.sh) therefore
# carries the metadata + kernel hash only, while this external manifest carries
# the full identity and is what the installer and acceptance check against.

set -e

FITK="$1"
ROOTFS="$2"
OUT="$3"
RELEASE="${4:-Product R1 RC1}"
NETBASE="${5:-R1-NET-D}"

[ -r "$FITK" ]   || { echo "kernel FIT not readable: $FITK" >&2; exit 1; }
[ -r "$ROOTFS" ] || { echo "rootfs image not readable: $ROOTFS" >&2; exit 1; }
[ -n "$OUT" ]    || { echo "usage: $0 <fit-kernel-itb> <rootfs> <out.json> [release] [netbaseline]" >&2; exit 2; }

# Kernel: hash exactly the FIT declared length (strip erase-block padding).
FSZ=$(python3 - "$FITK" <<'PY'
import struct,sys
d=open(sys.argv[1],'rb').read(8)
if len(d)<8 or d[0:4]!=b'\xd0\x0d\xfe\xed':
    raise SystemExit("not a FIT/DTB: %s" % sys.argv[1])
total=struct.unpack_from('>I',d,4)[0]
if total<8: raise SystemExit("implausible FIT totalsize %d" % total)
print(total)
PY
)
KSHA=$(head -c "$FSZ" "$FITK" | sha256sum | cut -d' ' -f1)

RSHA=$(sha256sum "$ROOTFS" | cut -d' ' -f1)
RSZ=$(wc -c < "$ROOTFS" | tr -d ' ')

cat > "$OUT" <<EOF
{
  "schema": "rt3000-release/v1",
  "product": "H3C Magic RT3000",
  "machine": "Machine-B",
  "release": "$RELEASE",
  "network_baseline": "$NETBASE",
  "kernel_sha256": "$KSHA",
  "kernel_size": $FSZ,
  "rootfs_sha256": "$RSHA",
  "rootfs_size": $RSZ
}
EOF

echo "RT3000_RELEASE_MANIFEST=$OUT"
echo "  kernel_sha256=$KSHA (fit declared $FSZ bytes)"
echo "  rootfs_sha256=$RSHA (rootfs $RSZ bytes)"
