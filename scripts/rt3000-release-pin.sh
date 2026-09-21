#!/bin/sh
# rt3000-release-pin.sh - fail-closed Product R1 RC1 release wrapper.
#
# ---------------------------------------------------------------------------
# Why this exists (and why it is NOT a Makefile hook)
# ---------------------------------------------------------------------------
# qca-ssdk.ko embeds __DATE__/__TIME__, so rebuilding identical source produces a
# different SHA256 while shipping identical code.  RC1 must ship the byte-exact
# binary that was hardware-accepted with the R1-NET-D network baseline.
#
# No in-tree Make hook satisfies both requirements at once:
#   (a) run BEFORE mksquashfs, and
#   (b) act on $(TARGET_DIR) (build_dir/.../root-$(BOARD)), the directory
#       mksquashfs actually reads.
# Every candidate was tried and rejected:
#   * Build/ step on IMAGE/nand-factory.ubi  -> runs after the squashfs exists
#   * $(STAGING_DIR_ROOT)                    -> a different tree from $(TARGET_DIR)
#   * define Image/Prepare                   -> bypassed by target/linux/install
#   * $(KDIR)/root.% prerequisite in target  -> overridden by include/image.mk
#   * define Image/Build/targz in target     -> also overridden
#   * KernelPackage/qca-ssdk-*/install       -> runs before RSTRIP rewrites the .ko
#
# So the pin is applied by this wrapper, which drives the whole sequence in the
# correct order and then VERIFIES THE RESULT BY EXTRACTING FROM THE FINAL UBI.
# It fails closed: any mismatch aborts with a nonzero exit, and no artifact is
# published.
#
# ---------------------------------------------------------------------------
# Usage: scripts/rt3000-release-pin.sh [--no-build]
#   --no-build   re-pin and re-verify using the existing build tree (skip make)
# ---------------------------------------------------------------------------
set -eu

TOPDIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TOPDIR"

EXPECT_SHA=d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497
EXPECT_SIZE=544716
PIN_SH="$TOPDIR/target/linux/ipq50xx/base-files/lib/rt3000/pin/pin.sh"
# Default log lives beside the build tree, not inside it, so it never enters Git.
BUILD_LOG="${RT3000_BUILD_LOG:-}"
if [ -z "$BUILD_LOG" ]; then
	BUILD_LOG="$(dirname -- "$TOPDIR")/rc1-work/release-pin-build.log"
fi
mkdir -p "$(dirname -- "$BUILD_LOG")" 2>/dev/null || \
	BUILD_LOG="$TOPDIR/release-pin-build.log"

TARGET_DIR=$(ls -d "$TOPDIR"/build_dir/target-*/root-ipq50xx 2>/dev/null | head -n1 || true)
KDIR=$(ls -d "$TOPDIR"/build_dir/target-*/linux-ipq50xx_arm 2>/dev/null | head -n1 || true)
UBI="$TOPDIR/bin/targets/ipq50xx/arm/openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi"

[ -n "$TARGET_DIR" ] || { echo "FATAL: cannot locate TARGET_DIR (root-ipq50xx)" >&2; exit 1; }
[ -n "$KDIR" ]       || { echo "FATAL: cannot locate KDIR (linux-ipq50xx_arm)" >&2; exit 1; }
[ -x "$PIN_SH" ] || [ -r "$PIN_SH" ] || { echo "FATAL: missing $PIN_SH" >&2; exit 1; }

echo "=== rt3000-release-pin: TARGET_DIR=$TARGET_DIR"
echo "=== rt3000-release-pin: KDIR=$KDIR"

##############################################################################
# 1. build (optional) so the tree is in its normal post-strip state
##############################################################################
if [ "${1:-}" != "--no-build" ]; then
	echo "=== rt3000-release-pin: building (log: $BUILD_LOG)"
	if ! make world V=s > "$BUILD_LOG" 2>&1; then
		echo "FATAL: build failed; see $BUILD_LOG" >&2
		tail -n 20 "$BUILD_LOG" >&2 || true
		exit 1
	fi
fi

##############################################################################
# 2. pin every qca-ssdk.ko in the tree mksquashfs reads, then force the rootfs
#    and everything derived from it to be regenerated from the pinned bytes.
##############################################################################
echo "=== rt3000-release-pin: pinning qca-ssdk.ko in TARGET_DIR"
found=0
for ko in "$TARGET_DIR"/lib/modules/*/qca-ssdk.ko; do
	[ -f "$ko" ] || continue
	found=1
	sh "$PIN_SH" "$ko"
done
[ "$found" -eq 1 ] || { echo "FATAL: no qca-ssdk.ko under $TARGET_DIR" >&2; exit 1; }

# The rootfs squashfs and the UBI are cached; delete them so the pinned bytes are
# actually re-packaged rather than the previous content being reused.
rm -f "$KDIR"/root.squashfs "$KDIR"/root.squashfs.* 2>/dev/null || true
rm -f "$KDIR"/tmp/openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi* 2>/dev/null || true
rm -f "$UBI" 2>/dev/null || true

##############################################################################
# 2b. authoritative release metadata, BEFORE the rootfs is squashed.
#
# The in-rootfs /etc/rt3000-release.json is produced by the project's existing
# generator scripts/rt3000-mkinrootfs-manifest.sh.  It must run against the
# staging rootfs before mksquashfs, otherwise the shipped image has no manifest
# and rt3release loses its input (RC1-HW-003).
#
# This reuses the authoritative generator rather than hand-writing JSON, so the
# schema, the kernel-hash semantics and the deliberate omission of rootfs_sha256
# (circularity) all stay exactly as accepted under RT3-RB002.
##############################################################################
MKINROOTFS="$TOPDIR/scripts/rt3000-mkinrootfs-manifest.sh"
KERNEL_FIT="$KDIR/h3c_rt3000-fit-uImage.itb"
if [ -x "$MKINROOTFS" ] || [ -r "$MKINROOTFS" ]; then
	if [ -f "$KERNEL_FIT" ]; then
		echo "=== rt3000-release-pin: writing in-rootfs release manifest"
		sh "$MKINROOTFS" "$KERNEL_FIT" "$TARGET_DIR" "Product R1 RC1" "R1-NET-D"
	else
		echo "FATAL: kernel FIT not found at $KERNEL_FIT" >&2
		exit 1
	fi
else
	echo "FATAL: missing $MKINROOTFS" >&2
	exit 1
fi

[ -s "$TARGET_DIR/etc/rt3000-release.json" ] || {
	echo "FATAL: in-rootfs manifest was not produced" >&2; exit 1; }

echo "=== rt3000-release-pin: re-running image install to regenerate rootfs + UBI"
if ! make target/linux/install V=s >> "$BUILD_LOG" 2>&1; then
	echo "FATAL: image install failed; see $BUILD_LOG" >&2
	tail -n 20 "$BUILD_LOG" >&2 || true
	exit 1
fi

[ -f "$UBI" ] || { echo "FATAL: final UBI not produced at $UBI" >&2; exit 1; }

##############################################################################
# 3. FAIL-CLOSED reverse verification: extract from the FINAL UBI and compare.
#    Nothing is trusted from the build tree here; the artifact is the oracle.
##############################################################################
echo "=== rt3000-release-pin: extracting qca-ssdk.ko from the FINAL UBI"
WORK=$(mktemp -d)
KEEP_WORK=0
trap '[ "$KEEP_WORK" = 1 ] || rm -rf "$WORK"' EXIT

EXTRACT_PY="$TOPDIR/scripts/rt3000-ubi-extract.py"
[ -r "$EXTRACT_PY" ] || { echo "FATAL: missing $EXTRACT_PY" >&2; exit 1; }

python3 "$EXTRACT_PY" "$UBI" "$WORK" >/dev/null
[ -f "$WORK/ubi_rootfs.bin" ] || { echo "FATAL: could not extract ubi_rootfs" >&2; exit 1; }

# unsquashfs exits nonzero when it cannot mknod /dev/console as a non-root user,
# even though it has unpacked every regular file.  That is an environment
# limitation, not an artifact defect, so the gate is the presence and hash of the
# module we are about to examine -- not unsquashfs' exit status alone.
unsquashfs -f -d "$WORK/rootfs" "$WORK/ubi_rootfs.bin" > "$WORK/unsquashfs.log" 2>&1 || true
if ! grep -q "^created 985 files\|^created .* files" "$WORK/unsquashfs.log" 2>/dev/null; then
	echo "FATAL: unsquashfs did not unpack the rootfs" >&2
	tail -n 15 "$WORK/unsquashfs.log" >&2 || true
	exit 1
fi
if [ -s "$WORK/unsquashfs.log" ] && grep -q "could not create character device" "$WORK/unsquashfs.log"; then
	echo "NOTE: unsquashfs could not create device nodes (not superuser); files are intact."
fi

GOT_KO="$WORK/rootfs/lib/modules/5.4.164/qca-ssdk.ko"
[ -f "$GOT_KO" ] || { echo "FATAL: qca-ssdk.ko absent from the FINAL UBI rootfs" >&2; exit 1; }

GOT_SHA=$(sha256sum "$GOT_KO" | cut -d' ' -f1)
GOT_SIZE=$(wc -c < "$GOT_KO" | tr -d ' ')

echo "=== rt3000-release-pin: final UBI qca-ssdk.ko"
echo "    sha256 = $GOT_SHA"
echo "    size   = $GOT_SIZE"

if [ "$GOT_SHA" != "$EXPECT_SHA" ] || [ "$GOT_SIZE" != "$EXPECT_SIZE" ]; then
	echo "FATAL: final UBI does NOT carry the hardware-accepted qca-ssdk.ko" >&2
	echo "  expected $EXPECT_SHA ($EXPECT_SIZE bytes)" >&2
	echo "  got      $GOT_SHA ($GOT_SIZE bytes)" >&2
	echo "RELEASE_PIN=FAIL" >&2
	exit 1
fi

##############################################################################
# 4. same fail-closed treatment for the release manifest (RC1-HW-003).
##############################################################################
GOT_MAN="$WORK/rootfs/etc/rt3000-release.json"
if [ ! -s "$GOT_MAN" ]; then
	echo "FATAL: /etc/rt3000-release.json absent from the FINAL UBI rootfs" >&2
	echo "RELEASE_PIN=FAIL" >&2
	exit 1
fi
# Schema and required keys must match the accepted RT3-RB002 shape.
for k in '"schema": "rt3000-release/v1"' '"machine": "Machine-B"' '"kernel_sha256"'; do
	if ! grep -q "$k" "$GOT_MAN"; then
		echo "FATAL: in-rootfs manifest missing expected key: $k" >&2
		cat "$GOT_MAN" >&2
		echo "RELEASE_PIN=FAIL" >&2
		exit 1
	fi
done
# rootfs_sha256 must NOT be present: embedding it would be circular.
if grep -q 'rootfs_sha256' "$GOT_MAN"; then
	echo "FATAL: in-rootfs manifest must not carry rootfs_sha256 (circular)" >&2
	echo "RELEASE_PIN=FAIL" >&2
	exit 1
fi
echo "=== rt3000-release-pin: in-rootfs manifest verified"
cat "$GOT_MAN"

echo
echo "RELEASE_PIN=PASS"
echo "FINAL_UBI=$UBI"
echo "QCA_SSDK_SHA256=$GOT_SHA"
echo "QCA_SSDK_SIZE=$GOT_SIZE"
