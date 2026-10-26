# Package only in Device/h3c_rt3000_rtl8367s_native_slot1.
# Callers source /lib/rt3000/mac.sh before this file.
rt3000_c_factory_mac() {
	local mac
	mac=$(/usr/sbin/c-mtd-mac-identity-ro) || return 1
	rt3000_mac_valid "$mac" || return 1
	printf '%s' "$mac"
}
