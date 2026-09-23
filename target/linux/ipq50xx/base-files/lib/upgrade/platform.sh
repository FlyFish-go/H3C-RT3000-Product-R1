. /lib/functions.sh

RAMFS_COPY_BIN='fw_printenv fw_setenv fwtool jsonfilter sha256sum rt3bcwrite mktemp head mknod tar sync'
RAMFS_COPY_DATA='/etc/fw_env.config /var/lock/fw_printenv.lock'

platform_check_image() {
	local board=$(board_name)
	case $board in
		redmi,ax3000|\
		xiaomi,cr881x)
			mi_dualboot_check_image "$1"
			return $?
			;;
		h3c,rt3000)
			if ! rt3_upgrade_check "$1"; then
				# Hide LuCI's force option as well as enforcing the stage2 gate.
				type notify_firmware_broken >/dev/null 2>&1 && notify_firmware_broken
				return 1
			fi
			return 0
			;;
		*)
			v "Sysupgrade is not supported on your board($board) yet."
			return 1
			;;
	esac
}

platform_do_upgrade() {
	local board=$(board_name)
	case $board in
		redmi,ax3000|\
		xiaomi,cr881x)
			mi_dualboot_do_upgrade "$1"
			;;
		h3c,rt3000)
			if ! rt3_upgrade_write "$1"; then
				v "RT3000 upgrade FAILED. Rebooting with the last verified slot selection."
				sync
				reboot -f
				# do_stage2 ignores return codes; exit prevents a false success message.
				exit 1
			fi
			;;
		*)
			default_do_upgrade "$1"
			;;
	esac
}
