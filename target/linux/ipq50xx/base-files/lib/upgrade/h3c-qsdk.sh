# H3C HW-A/B/C/D sysupgrade: rebuild the UBI volumes of this board's QSDK slot.
#
# U-Boot boots the FIT in volume "kernel" and the kernel mounts ubi.block=0,1,
# so the volume ids are fixed: kernel=0, ubi_rootfs=1, rootfs_data=2. Every
# volume in the slot is recreated (older C installs carried extra ones). The
# OEM slot, BOOTCONFIG and all other partitions are read-only in Linux and are
# never touched; the default slot is chosen in U-Boot.
#
# The slot written is the MTD the kernel named rootfs, i.e. the one it booted
# from (U-Boot passes h3c.boot_slot, patch 030 maps it), so QSDK may live in
# either physical slot. C used rootfs_1 before patch 428; its map now uses
# the same rootfs/oem_rootfs names as A/B/D.

H3C_QSDK_UBI=/dev/ubi0

# <mtd name> <FIT configuration>
h3c_qsdk_slot() {
	case "$(board_name)" in
	h3c,rw3000-hw-a) echo "rootfs config@mp03.1" ;;
	h3c,rt3000) echo "rootfs config@mp02.1" ;;
	h3c,rt3000-rtl8367s) echo "rootfs config@mp03.1-c2" ;;
	h3c,nx30-hw-d) echo "rootfs config@mp02.1" ;;
	*) return 1 ;;
	esac
}

# Index of the one MTD with this exact name.
h3c_qsdk_mtd_index() {
	local found

	found=$(grep " \"$1\"\$" /proc/mtd | sed -n 's/^mtd\([0-9]*\):.*/\1/p')
	[ -n "$found" ] && [ "$(echo "$found" | wc -l)" = 1 ] && echo "$found"
}

h3c_qsdk_tar_dir() {
	tar tf "$1" 2>/dev/null | grep -m1 '^sysupgrade-.*/$'
}

h3c_qsdk_member_size() {
	tar xf "$1" "$2" -O 2>/dev/null | wc -c
}

h3c_qsdk_check_image() {
	local img="$1" slot mtd name fitconf dir ksz rsz

	slot=$(h3c_qsdk_slot) || { v "unsupported board $(board_name)"; return 1; }
	set -- $slot
	name=$1 fitconf=$2
	mtd=$(h3c_qsdk_mtd_index "$name")
	[ -n "$mtd" ] &&
	[ "$(cat /sys/class/ubi/ubi0/mtd_num 2>/dev/null)" = "$mtd" ] || {
		v "ubi0 is not attached to $name (mtd${mtd:-?})"
		return 1
	}
	dir=$(h3c_qsdk_tar_dir "$img")
	[ -n "$dir" ] || { v "not a sysupgrade tar"; return 1; }
	ksz=$(h3c_qsdk_member_size "$img" "${dir}kernel")
	rsz=$(h3c_qsdk_member_size "$img" "${dir}root")
	[ "${ksz:-0}" -gt 0 ] && [ "${rsz:-0}" -gt 0 ] || {
		v "image lacks kernel or root"
		return 1
	}
	[ "$(tar xf "$img" "${dir}kernel" -O | head -c 4 | hexdump -v -e '1/1 "%02x"')" = d00dfeed ] &&
	tar xf "$img" "${dir}kernel" -O | grep -q "$fitconf" || {
		v "kernel is not a FIT with $fitconf"
		return 1
	}
	[ "$(tar xf "$img" "${dir}root" -O | head -c 4)" = hsqs ] || {
		v "root is not squashfs"
		return 1
	}
	return 0
}

h3c_qsdk_do_upgrade() {
	local img="$1" dir ksz rsz vol

	dir=$(h3c_qsdk_tar_dir "$img")
	ksz=$(h3c_qsdk_member_size "$img" "${dir}kernel")
	rsz=$(h3c_qsdk_member_size "$img" "${dir}root")
	sync
	for vol in /sys/class/ubi/ubi0_*; do
		[ -e "$vol" ] && ubiblock -r "/dev/${vol##*/}" 2>/dev/null
	done
	for vol in /sys/class/ubi/ubi0_*/name; do
		[ -e "$vol" ] && ubirmvol $H3C_QSDK_UBI -N "$(cat "$vol")" 2>/dev/null
	done
	ubimkvol $H3C_QSDK_UBI -n 0 -N kernel -s "$ksz" &&
	tar xf "$img" "${dir}kernel" -O | ubiupdatevol /dev/ubi0_0 -s "$ksz" - &&
	ubimkvol $H3C_QSDK_UBI -n 1 -N ubi_rootfs -s "$rsz" &&
	tar xf "$img" "${dir}root" -O | ubiupdatevol /dev/ubi0_1 -s "$rsz" - &&
	ubimkvol $H3C_QSDK_UBI -n 2 -N rootfs_data -m || {
		v "UBI volume update FAILED"
		return 1
	}
	if [ -n "$UPGRADE_BACKUP" ] && [ -f "$UPGRADE_BACKUP" ]; then
		mkdir -p /tmp/new_root
		if mount -t ubifs /dev/ubi0_2 /tmp/new_root; then
			mv "$UPGRADE_BACKUP" "/tmp/new_root/${BACKUP_FILE:-sysupgrade.tgz}"
			umount /tmp/new_root
		else
			v "could not mount new rootfs_data; settings not kept"
		fi
	fi
	sync
	return 0
}
