# Machine-B NAND upgrade. Never fall back to a partition found by label.
# Checks also run in stage2, so sysupgrade -F cannot bypass the write gates.

rt3_upgrade_error() {
	echo "RT3000 upgrade: $*" >&2
	return 1
}

rt3_upgrade_hardware() {
	local part attr expected actual
	[ "$(board_name)" = 'h3c,rt3000' ] || { rt3_upgrade_error 'wrong board'; return 1; }
	# Require the reviewed QSDK partition map, including the read-only OEM slot.
	grep -q '0x2800000@0x900000(oem_rootfs)ro,0x2800000@0x3100000(rootfs)' /proc/cmdline || {
		rt3_upgrade_error 'unrecognized partition offsets'; return 1;
	}
	for part in 2 3 15 16; do
		for attr in type size erasesize writesize oobsize; do
			case "$attr" in
				type) expected=nand;;
				size) case "$part" in 2|3) expected=262144;; *) expected=41943040;; esac;;
				erasesize) expected=131072;; writesize) expected=2048;; oobsize) expected=128;;
			esac
			actual=$(cat "/sys/class/mtd/mtd$part/$attr") || return 1
			[ "$actual" = "$expected" ] || { rt3_upgrade_error "unsupported mtd$part $attr"; return 1; }
		done
	done
	[ "$(cat /sys/class/mtd/mtd2/name)" = 0:BOOTCONFIG ] &&
	[ "$(cat /sys/class/mtd/mtd3/name)" = 0:BOOTCONFIG1 ] &&
	[ "$(cat /sys/class/mtd/mtd15/name)" = oem_rootfs ] &&
	[ "$(cat /sys/class/mtd/mtd16/name)" = rootfs ] || return 1
	[ "$(dd if=/dev/mtd15 bs=4 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"')" = 55424923 ] || {
		rt3_upgrade_error 'OEM UBI header missing'; return 1;
	}
	# Both copies must already agree and pass the RB001 structural checks.
	rt3bcwrite --verify-only 0 >/dev/null 2>&1 || rt3bcwrite --verify-only 1 >/dev/null 2>&1 || {
		rt3_upgrade_error 'BOOTCONFIG verification failed'; return 1;
	}
}

rt3_upgrade_value() {
	jsonfilter -i "$RT3_WORK/manifest.json" -e "@.$1"
}

rt3_upgrade_payload() {
	local file="$1" size="$2" hash="$3" actual
	case "$size" in ''|*[!0-9]*) return 1;; esac
	[ "${#size}" -le 8 ] && [ "$size" -gt 0 ] || return 1
	[ "${#hash}" = 64 ] || return 1
	case "$hash" in *[!0-9a-f]*) return 1;; esac
	[ "$(wc -c < "$file")" -eq "$size" ] || return 1
	actual=$(sha256sum "$file") || return 1
	[ "${actual%% *}" = "$hash" ]
}

rt3_upgrade_unpack() {
	local image="$1" value field expected names bytes magic fitlen
	[ -f "$image" ] || return 1
	bytes=$(wc -c < "$image") || return 1
	[ "$bytes" -gt 0 ] && [ "$bytes" -le 34603008 ] || return 1
	fwtool -q -i "$RT3_WORK/metadata.json" "$image" || return 1
	[ "$(jsonfilter -i "$RT3_WORK/metadata.json" -e '@.supported_devices[*]')" = 'h3c,rt3000' ] || return 1
	value=$(jsonfilter -i "$RT3_WORK/metadata.json" -e '@.compat_version') || return 1
	[ "$value" = 1.0 ] || return 1
	# Four regular members only: reject duplicates, links and unexpected paths.
	tar -tf "$image" > "$RT3_WORK/list" || return 1
	awk '
	  $0 !~ /^sysupgrade-h3c_rt3000\/(CONTROL|manifest.json|kernel|root)$/ {exit 1}
	  ++seen[$0] != 1 {exit 1}
	  END {if (NR != 4) exit 1}
	' "$RT3_WORK/list" || return 1
	tar -tvf "$image" > "$RT3_WORK/types" || return 1
	awk 'substr($0,1,1) != "-" {exit 1} END {if (NR != 4) exit 1}' "$RT3_WORK/types" || return 1
	for field in CONTROL manifest.json kernel root; do
		tar -xOf "$image" "sysupgrade-h3c_rt3000/$field" > "$RT3_WORK/$field" || return 1
	done
	[ "$(cat "$RT3_WORK/CONTROL")" = BOARD=h3c_rt3000 ] || return 1
	[ "$(wc -c < "$RT3_WORK/manifest.json")" -le 4096 ] || return 1
	for field in schema board machine slot page_size erase_size oob_size; do
		case "$field" in
			schema) expected=rt3000-sysupgrade/v1;; board) expected=h3c,rt3000;;
			machine) expected=Machine-B;; slot) expected=16;; page_size) expected=2048;;
			erase_size) expected=131072;; oob_size) expected=128;;
		esac
		value=$(rt3_upgrade_value "$field") || return 1
		[ "$value" = "$expected" ] || return 1
	done
	RT3_KSIZE=$(rt3_upgrade_value kernel_size) || return 1
	RT3_RSIZE=$(rt3_upgrade_value rootfs_size) || return 1
	RT3_KHASH=$(rt3_upgrade_value kernel_sha256) || return 1
	RT3_RHASH=$(rt3_upgrade_value rootfs_sha256) || return 1
	rt3_upgrade_payload "$RT3_WORK/kernel" "$RT3_KSIZE" "$RT3_KHASH" || return 1
	rt3_upgrade_payload "$RT3_WORK/root" "$RT3_RSIZE" "$RT3_RHASH" || return 1
	[ "$RT3_KSIZE" -le 8388608 ] && [ "$RT3_RSIZE" -le 25165824 ] || return 1
	magic=$(dd if="$RT3_WORK/kernel" bs=4 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"')
	[ "$magic" = d00dfeed ] || return 1
	fitlen=$(dd if="$RT3_WORK/kernel" bs=4 skip=1 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"')
	[ "$((0x$fitlen))" -eq "$RT3_KSIZE" ] || return 1
	magic=$(dd if="$RT3_WORK/root" bs=4 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"')
	[ "$magic" = 68737173 ] || return 1
}

rt3_upgrade_check() (
	umask 077
	RT3_WORK=$(mktemp -d /tmp/rt3-upgrade.XXXXXX) || exit 1
	trap 'rm -rf "$RT3_WORK"' EXIT
	rt3_upgrade_hardware && rt3_upgrade_unpack "$1" || {
		rt3_upgrade_error 'image/hardware check failed; nothing written'; exit 1;
	}
	echo 'RT3000 Machine-B sysupgrade image verified'
)

# Create the /dev node for a ubi device or volume from its sysfs "dev"
# attribute.  ubiattach/ubimkvol only populate sysfs; the initramfs has no
# mdev/hotplug helper, so without this the /dev/ubi* nodes never appear and
# every later ubimkvol/ubiupdatevol fails with ENOENT.  Mirrors the upstream
# implementation in /lib/upgrade/nand.sh.
rt3_upgrade_mknod() {
	local dir="$1"
	local dev="/dev/$(basename "$dir")"

	[ -e "$dev" ] && return 0
	[ -f "$dir/dev" ] || return 1
	local devid major minor
	devid="$(cat "$dir/dev")" || return 1
	major="${devid%%:*}"
	minor="${devid##*:}"
	mknod "$dev" c "$major" "$minor"
}

# Locate the UBI device attached to a given mtd number, creating /dev nodes
# for it and (optionally) its volumes.  Sets RT3_UBI to the device name.
rt3_upgrade_find_ubi_for_mtd() {
	local want="$1" dir mtd found=
	RT3_UBI=
	for dir in /sys/devices/virtual/ubi/ubi*; do
		[ -d "$dir" ] || continue
		[ -f "$dir/mtd_num" ] || continue
		mtd="$(cat "$dir/mtd_num")" || continue
		[ "$mtd" = "$want" ] || continue
		found="${dir##*/}"
		rt3_upgrade_mknod "$dir" || return 1
		local vol
		for vol in "$dir"/${found}_*; do
			[ -d "$vol" ] || continue
			rt3_upgrade_mknod "$vol" || return 1
		done
		break
	done
	RT3_UBI="$found"
	[ -n "$found" ]
}

rt3_upgrade_write() (
	umask 077
	RT3_WORK=$(mktemp -d /tmp/rt3-upgrade.XXXXXX) || exit 1
	RT3_MOUNTED=0
	trap 'if [ "$RT3_MOUNTED" = 0 ] || umount "$RT3_WORK/overlay"; then rm -rf "$RT3_WORK"; fi' EXIT
	rt3_upgrade_hardware && rt3_upgrade_unpack "$1" || exit 1
	# mtd16 may already carry a UBI device in two very different situations:
	#   * first install from the RAM system   -> nothing attached
	#   * NAND-to-NAND upgrade of a running QSDK -> ubi0 IS attached to mtd16,
	#     because the running rootfs lives there.  That is normal and must be
	#     released, NOT refused.
	# Record the current owner so it can be detached before ubiformat.
	rt3_upgrade_find_ubi_for_mtd 16
	RT3_OLD_UBI="$RT3_UBI"
	# Refuse if stage2 did not release the live filesystems.
	grep -Eq ' /rom | /overlay | /mnt |^/dev/ubiblock|^ubi[0-9]+:' /proc/mounts && exit 1
	if [ -n "$UPGRADE_BACKUP" ]; then
		[ -s "$UPGRADE_BACKUP" ] || exit 1
		tar -tzf "$UPGRADE_BACKUP" >/dev/null || exit 1
	fi
	# A loss of power from here through payload verification boots the OEM slot.
	sync
	rt3bcwrite --set 0 && rt3bcwrite --verify-only 0 || exit 1
	# Release mtd16 before formatting it.
	#
	# The mount check above already guarantees /rom, /overlay and any ubiblock
	# are gone: stage2 unmounted the live rootfs before this ran.  So we must
	# NOT try to release a ubiblock here -- a stale node can still linger in
	# /dev and probing it fails with EINVAL ("is not a character device"),
	# which would abort an otherwise good upgrade.  Upstream nand.sh likewise
	# just detaches and tolerates failure.
	if [ -n "$RT3_OLD_UBI" ]; then
		ubidetach -m 16 || true
		sync
		rt3_upgrade_find_ubi_for_mtd 16
		[ -z "$RT3_UBI" ] || {
			echo "RT3000 upgrade: mtd16 still attached as $RT3_UBI after detach" >&2
			exit 1
		}
	fi
	ubiformat /dev/mtd16 -y -s 2048 -O 2048 || exit 1
	ubiattach -m 16 -O 2048 || exit 1
	rt3_upgrade_find_ubi_for_mtd 16 || exit 1
	[ -n "$RT3_UBI" ] || exit 1
	# The exact UBI device index is whatever the kernel assigned; do not
	# assume it is 0.  The /dev node was created by the helper above.
	local ubidev="/dev/$RT3_UBI"
	local ubidir="/sys/devices/virtual/ubi/$RT3_UBI"
	[ -e "$ubidev" ] || exit 1
	# Create each volume and mknod its node immediately: the sysfs volume
	# entry only exists once ubimkvol has run.
	local spec
	for spec in "0:kernel:$RT3_KSIZE" "1:ubi_rootfs:$RT3_RSIZE" "2:rootfs_data:-m"; do
		local vol="${spec%%:*}"
		local rest="${spec#*:}"
		local name="${rest%%:*}"
		local size="${rest#*:}"
		if [ "$size" = "-m" ]; then
			ubimkvol "$ubidev" -n "$vol" -N "$name" -m || exit 1
		else
			ubimkvol "$ubidev" -n "$vol" -N "$name" -s "$size" || exit 1
		fi
		rt3_upgrade_mknod "$ubidir/${RT3_UBI}_$vol" || exit 1
		[ -e "$ubidev"_"$vol" ] || exit 1
	done
	ubiupdatevol "${ubidev}_0" "$RT3_WORK/kernel" || exit 1
	ubiupdatevol "${ubidev}_1" "$RT3_WORK/root" || exit 1
	head -c "$RT3_KSIZE" "${ubidev}_0" > "$RT3_WORK/readback" || exit 1
	rt3_upgrade_payload "$RT3_WORK/readback" "$RT3_KSIZE" "$RT3_KHASH" || exit 1
	head -c "$RT3_RSIZE" "${ubidev}_1" > "$RT3_WORK/readback" || exit 1
	rt3_upgrade_payload "$RT3_WORK/readback" "$RT3_RSIZE" "$RT3_RHASH" || exit 1
	rm "$RT3_WORK/readback" || exit 1
	if [ -n "$UPGRADE_BACKUP" ]; then
		mkdir "$RT3_WORK/overlay" || exit 1
		mount -t ubifs "${ubidev}_2" "$RT3_WORK/overlay" || exit 1
		RT3_MOUNTED=1
		cp "$UPGRADE_BACKUP" "$RT3_WORK/overlay/sysupgrade.tgz" || exit 1
		local before after
		before=$(sha256sum "$UPGRADE_BACKUP") || exit 1
		after=$(sha256sum "$RT3_WORK/overlay/sysupgrade.tgz") || exit 1
		[ "${before%% *}" = "${after%% *}" ] || exit 1
		sync
		umount "$RT3_WORK/overlay" || exit 1
		RT3_MOUNTED=0
	fi
	sync
	rt3bcwrite --set 1 && rt3bcwrite --verify-only 1 || exit 1
	echo 'RT3000 upgrade: second-slot payload verified; QSDK selected'
)
