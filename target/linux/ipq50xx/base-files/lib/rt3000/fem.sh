# mp02.1 boards (HW-B, HW-D) share one OEM route and machid; what separates
# them for Wi-Fi is whether the 5 GHz radio has external FEMs. The factory
# calibration block says so (ART + 0x26800, the QCN6122 PD1 block):
#
#   header 01 00 04 04, +0x3a 60, +0x45 09  -> 5 GHz FEM     (HW-D, NX30)
#   header 01 00 04 04, +0x3a 50, +0x45 01  -> no 5 GHz FEM  (HW-B build)
#
# A D-PCB without FEMs (RC3000 B0) therefore belongs to HW-B. This is the
# same rule BootBridge2 and U-Boot use. Any other combination is "unknown"
# and callers must not change anything for it.
#
# Prints fem, nofem or unknown. Needs only /proc/mtd, dd and hexdump, so it
# also works in preinit.
h3c_fem_probe() {
	local mtd

	mtd=$(sed -n 's/^\(mtd[0-9]*\):.*"0:ART"$/\1/p' /proc/mtd)
	[ -n "$mtd" ] || { echo unknown; return 0; }
	# 0x26800 = 77 * 2048; bytes 0x00..0x45 of the block.
	set -- $(dd if=/dev/$mtd bs=2048 skip=77 count=1 2>/dev/null |
		hexdump -v -n 70 -e '1/1 "%02x "')
	[ "$#" -eq 70 ] && [ "$1$2$3$4" = 01000404 ] || { echo unknown; return 0; }
	shift 58	# $1 = +0x3a
	local b3a=$1
	shift 11	# $1 = +0x45
	case "$b3a:$1" in
	60:09) echo fem ;;
	50:01) echo nofem ;;
	*) echo unknown ;;
	esac
}
