#!/bin/sh
# rt3000-pin-qca-ssdk.sh — install the hardware-accepted qca-ssdk.ko.
#
# RC1 pins this module rather than using a fresh build, because the module
# embeds __DATE__/__TIME__ and therefore does not rebuild to a stable hash.
# See rc1-qca-ssdk-pinning.md for the rationale.
#
# The pinned payload is carried as base64 in this directory so that no vendor
# binary is committed to Git.  The file is materialised at build time and its
# hash is verified before it is used; a mismatch aborts the build.

set -e

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEST="$1"

[ -n "$DEST" ] || { echo "usage: $0 <destination .ko path>" >&2; exit 2; }

PIN_SHA256=d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497
PIN_SIZE=544716

mkdir -p "$(dirname "$DEST")"
base64 -d "$HERE/qca-ssdk.ko.b64" > "$DEST.tmp"
mv "$DEST.tmp" "$DEST"

got_sha=$(sha256sum "$DEST" | cut -d' ' -f1)
got_size=$(wc -c < "$DEST" | tr -d ' ')

if [ "$got_sha" != "$PIN_SHA256" ] || [ "$got_size" != "$PIN_SIZE" ]; then
	echo "rt3000-pin-qca-ssdk: pinned module failed verification" >&2
	echo "  expected $PIN_SHA256 ($PIN_SIZE bytes)" >&2
	echo "  got      $got_sha ($got_size bytes)" >&2
	rm -f "$DEST"
	exit 1
fi

echo "rt3000-pin-qca-ssdk: pinned qca-ssdk.ko verified ($PIN_SHA256)"
