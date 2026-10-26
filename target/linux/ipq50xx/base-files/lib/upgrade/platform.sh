. /lib/functions.sh

RAMFS_COPY_BIN='fw_printenv fw_setenv fwtool jsonfilter sha256sum mktemp head mknod tar sync'
RAMFS_COPY_DATA='/etc/fw_env.config /var/lock/fw_printenv.lock'

platform_check_image() {
	local board=$(board_name)
	case $board in
		redmi,ax3000|\
		xiaomi,cr881x)
			mi_dualboot_check_image "$1"
			return $?
			;;
		h3c,nx30-hw-d|\
		h3c,rt3000|\
		h3c,rt3000-rtl8367s|\
		h3c,rw3000-hw-a)
			h3c_qsdk_check_image "$1"
			return $?
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
		h3c,nx30-hw-d|\
		h3c,rt3000|\
		h3c,rt3000-rtl8367s|\
		h3c,rw3000-hw-a)
			if ! h3c_qsdk_do_upgrade "$1"; then
				v "Upgrade FAILED; rebooting. Recover by uploading factory.ubi in the U-Boot rescue page."
				sync
				reboot -f
				exit 1
			fi
			;;
		*)
			default_do_upgrade "$1"
			;;
	esac
}
