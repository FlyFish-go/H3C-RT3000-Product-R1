. /lib/functions.sh

RAMFS_COPY_BIN='fw_printenv fw_setenv'
RAMFS_COPY_DATA='/etc/fw_env.config /var/lock/fw_printenv.lock'

platform_check_image() {
	local board=$(board_name)
	case $board in
		redmi,ax3000|\
		xiaomi,cr881x)
			mi_dualboot_check_image "$1"
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
		h3c,rt3000)
			v "Sysupgrade is disabled on H3C RT3000 Product R0; use the verified OEM/slot workflow."
			return 1
			;;
		*)
			default_do_upgrade "$1"
			;;
	esac
}
