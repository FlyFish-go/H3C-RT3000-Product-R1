#!/bin/sh
# Wi-Fi defaults shared by the HW-A/B/C/D first-boot scripts, plus the
# first-boot policy helpers (HW-A/B/C uci-defaults, HW-C hotplug).

RT3000_WIFI24_PATH="platform/soc/c000000.wifi"
RT3000_WIFI5_PATH="platform/soc/soc:wifi1@c000000"
RT3000_WIFI_SSID_2G="${RT3000_WIFI_SSID_2G:-OpenWrt}"
RT3000_WIFI_SSID_5G="${RT3000_WIFI_SSID_5G:-OpenWrt-5G}"
RT3000_WIFI_DEFAULT_KEY="${RT3000_WIFI_DEFAULT_KEY:-12345678}"

rt3000_wifi_phy_for_path() {
	local want="$1" phy dev node

	want="${want##*/}"
	for phy in /sys/class/ieee80211/*; do
		[ -e "$phy" ] || continue
		dev="$(readlink -f "$phy/device" 2>/dev/null)" || continue
		[ -n "$dev" ] || continue
		node="${dev##*/}"
		[ "$node" = "$want" ] && {
			echo "${phy##*/}"
			return 0
		}
	done

	return 1
}

rt3000_wifi_section_is_path() {
	local section="$1" want="$2" path

	path="$(uci -q get "wireless.$section.path")" || return 1
	[ -n "$path" ] || return 1
	[ "${path##*/}" = "${want##*/}" ]
}

# Give an operator-owned AP the factory MAC only when it has no address of its
# own; without one mac80211 derives 00:03:7f:.. from the ART placeholder.
rt3000_wifi_fill_mac() {
	local section="$1" iface="$2" mac="$3"

	[ -n "$mac" ] || return 0
	[ -n "$(uci -q get "wireless.$iface.macaddr")" ] ||
		uci -q set "wireless.$iface.macaddr=$mac"
	[ -n "$(uci -q get "wireless.$section.macaddr")" ] ||
		uci -q set "wireless.$section.macaddr=$mac"
	return 0
}

# Apply defaults only to mac80211's untouched, disabled AP template (radio
# disabled, AP on lan, SSID OpenWrt, no encryption). That template is what a
# fresh overlay gets, and also what r8 left behind on HW-A/B/C. Everything else
# is operator-owned: it is marked "preserve" and only gets the factory MAC when
# it has none, so a keep-settings sysupgrade never resets SSID, key, country,
# channel width or radio state. The marker is committed with the settings, so
# later runs (uci-defaults after sysupgrade, PHY add events) do not re-apply.
rt3000_c_wifi_apply_radio() {
	local want="$1" band="$2" ssid="$3" mac="$4" htmode="$5"
	local phy section iface radio_disabled found=0
	local mode network iface_ssid encryption iface_disabled managed

	phy="$(rt3000_wifi_phy_for_path "$want")" || {
		logger -t rt3000-wifi "no live PHY at $want; waiting for ieee80211 hotplug"
		return 0
	}

	for section in $(uci show wireless 2>/dev/null | sed -n "s/^wireless\\.\\([^.=]*\\)=wifi-device$/\\1/p"); do
		rt3000_wifi_section_is_path "$section" "$want" || continue
		found=1
		radio_disabled="$(uci -q get "wireless.$section.disabled")"

		for iface in $(uci show wireless 2>/dev/null | sed -n "s/^wireless\\.\\([^.=]*\\)=wifi-iface$/\\1/p"); do
			[ "$(uci -q get "wireless.$iface.device")" = "$section" ] || continue
			managed="$(uci -q get "wireless.$iface.rt3000_c_policy")"
			mode="$(uci -q get "wireless.$iface.mode")"
			[ "$mode" = "ap" ] || continue

			if [ "$managed" = "default" ]; then
				[ -n "$mac" ] && uci -q set "wireless.$section.macaddr=$mac"
				[ -n "$mac" ] && uci -q set "wireless.$iface.macaddr=$mac"
				continue
			fi
			if [ "$managed" = "preserve" ]; then
				rt3000_wifi_fill_mac "$section" "$iface" "$mac"
				continue
			fi

			network="$(uci -q get "wireless.$iface.network")"
			iface_ssid="$(uci -q get "wireless.$iface.ssid")"
			encryption="$(uci -q get "wireless.$iface.encryption")"
			iface_disabled="$(uci -q get "wireless.$iface.disabled")"

			# Only transform the known stock auto-detected AP. Existing custom
			# or open-AP choices are preserved and marked as operator-owned.
			if [ "$radio_disabled" = "1" ] &&
			   { [ -z "$iface_disabled" ] || [ "$iface_disabled" = "1" ]; } &&
			   [ "$network" = "lan" ] && [ "$iface_ssid" = "OpenWrt" ] &&
			   [ "$encryption" = "none" ]; then
				uci -q set "wireless.$section.band=$band"
				uci -q set "wireless.$section.disabled=0"
				uci -q set "wireless.$section.htmode=$htmode"
				# ath11k wiphys are self-managed; without a country the
				# firmware default (US) stays in force. CN-market unit.
				uci -q set "wireless.$section.country=CN"
				[ -n "$mac" ] && uci -q set "wireless.$section.macaddr=$mac"
				uci -q set "wireless.$iface.mode=ap"
				uci -q set "wireless.$iface.network=lan"
				uci -q set "wireless.$iface.ssid=$ssid"
				uci -q set "wireless.$iface.encryption=psk2"
				uci -q set "wireless.$iface.key=$RT3000_WIFI_DEFAULT_KEY"
				uci -q set "wireless.$iface.disabled=0"
				[ -n "$mac" ] && uci -q set "wireless.$iface.macaddr=$mac"
				uci -q set "wireless.$iface.rt3000_c_policy=default"
			else
				uci -q set "wireless.$iface.rt3000_c_policy=preserve"
				rt3000_wifi_fill_mac "$section" "$iface" "$mac"
			fi
		done
	done

	[ "$found" = "1" ] || logger -t rt3000-wifi "no wifi-device section for $want; waiting for ieee80211 hotplug"
	return 0
}

rt3000_c_wifi_apply() {
	local wifi24="$1" wifi5="$2"

	rt3000_c_wifi_apply_radio "$RT3000_WIFI24_PATH" "2g" "$RT3000_WIFI_SSID_2G" \
		"$wifi24" "HE20" || return 1
	rt3000_c_wifi_apply_radio "$RT3000_WIFI5_PATH" "5g" "$RT3000_WIFI_SSID_5G" \
		"$wifi5" "HE80" || return 1
	return 0
}
