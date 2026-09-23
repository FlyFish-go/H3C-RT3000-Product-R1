#!/bin/bash
# RT3000 — Wi-Fi duplicate-radio regression suite (offline).
#
# This suite runs the REAL /etc/uci-defaults/99-rt3000-wifi script against a
# mocked device filesystem, so it tests the shipped logic rather than a copy of
# it.  It exists to catch the class of bug that produced
# NONBLOCKING_5G_DUPLICATE_SECTION:
#
#   1. one physical QCN6102 must not yield two user-visible radio sections
#   2. the final radio count / identity must be correct
#   3. both bands must come up enabled and WPA2-secured, never open
#   4. WiFi24 MAC must land on the real 2.4 GHz radio
#   5. WiFi5  MAC must land on the real QCN6102 radio
#
# Usage: run_wifi_dup_tests.sh [path-to-script]
# Default script path is the in-repo uci-defaults file.
#
# Exit: 0 = all pass, 1 = at least one failure (fail-closed).

set -u

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
REPO_ROOT="${REPO_ROOT:-$ROOT}"
SCRIPT="${1:-$ROOT/target/linux/ipq50xx/base-files/etc/uci-defaults/99-rt3000-wifi}"
[ -n "$SCRIPT" ] && [ -f "$SCRIPT" ] || { echo "FATAL: script not found (pass path as \$1)"; exit 1; }

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
chk()  { if [ "$2" = "$3" ]; then ok "$1 ($3)"; else bad "$1: expected [$3] got [$2]"; fi; }

# ---------------------------------------------------------------------------
# Build a mock device root.  The scenario is the REAL defect topology:
#   phy0 -> platform/soc/c000000.wifi         (IPQ5018 integrated, 2.4 GHz)
#   phy1 -> platform/soc/soc:wifi1@c000000    (external QCN6102, 5 GHz)
# ---------------------------------------------------------------------------
setup_mock() {
	# Deliberately NOT mktemp: on macOS that yields /var/... which resolves
	# to /private/var/..., and readlink -f would then report a prefix that
	# does not match the tree the test built.  A fixed, already-canonical
	# location keeps the mock deterministic on every platform.
	MOCK="${TMPDIR_MOCK:-/tmp}/rt3000-wifi-mock.$$"
	rm -rf "$MOCK"
	mkdir -p "$MOCK/sys/devices/platform/soc/c000000.wifi/ieee80211" \
	         "$MOCK/sys/devices/platform/soc/soc:wifi1@c000000/ieee80211" \
	         "$MOCK/sys/class/ieee80211" \
	         "$MOCK/bin" "$MOCK/etc" "$MOCK/tmp"

	mkdir -p "$MOCK/sys/devices/platform/soc/c000000.wifi/ieee80211/phy0"
	mkdir -p "$MOCK/sys/devices/platform/soc/soc:wifi1@c000000/ieee80211/phy1"
	# The mock is a self-contained tree, so class symlinks point at real
	# directories inside it (absolute targets, resolved by readlink -f).
	ln -s "$MOCK/sys/devices/platform/soc/c000000.wifi"      "$MOCK/sys/class/ieee80211/phy0"
	ln -s "$MOCK/sys/devices/platform/soc/soc:wifi1@c000000" "$MOCK/sys/class/ieee80211/phy1"

	echo "00:03:7f:12:8c:8c" > "$MOCK/sys/devices/platform/soc/c000000.wifi/ieee80211/phy0/macaddress"
	echo "00:03:7f:12:16:16" > "$MOCK/sys/devices/platform/soc/soc:wifi1@c000000/ieee80211/phy1/macaddress"

	# /sys/class/ieee80211/phyN/device resolves to the device directory,
	# exactly as on hardware.
	ln -s "$MOCK/sys/devices/platform/soc/c000000.wifi"      "$MOCK/sys/class/ieee80211/phy0/device"
	ln -s "$MOCK/sys/devices/platform/soc/soc:wifi1@c000000" "$MOCK/sys/class/ieee80211/phy1/device"

	# ---- mock uci: operates on a flat key=value store -------------------
	# Emits real `uci show wireless` syntax, i.e. every line is prefixed with
	# the package name and every VALUE is single-quoted, while section
	# headers are not.  `uci get` returns the value unquoted, matching the
	# real tool.  `-q` is stripped before dispatch.
	cat > "$MOCK/bin/uci" <<'UCI'
#!/bin/bash
STORE="$MOCK_STATE"
[ "${1:-}" = "-q" ] && shift
cmd="${1:-}"; shift 2>/dev/null

case "$cmd" in
  show)
	[ "${1:-wireless}" = "wireless" ] || exit 0
	# Section headers first (as uci does), then options, each wrapped in
	# the package prefix; values quoted.
	sed -n 's/^\([A-Za-z0-9_]*\)=\(wifi-[a-z]*\)$/wireless.\1=\2/p' "$STORE"
	sed -n 's/^\([A-Za-z0-9_]*\)\.\([A-Za-z0-9_]*\)=\(.*\)$/wireless.\1.\2='"'"'\3'"'"'/p' "$STORE"
	exit 0
	;;
  get)
	key="${1#wireless.}"
	v="$(sed -n "s/^${key}=//p" "$STORE" | head -1)"
	[ -n "$v" ] || exit 1
	printf '%s\n' "$v"
	exit 0
	;;
  set)
	kv="${1#wireless.}"
	k="${kv%%=*}"; v="${kv#*=}"
	grep -v "^${k}=" "$STORE" > "$STORE.tmp" 2>/dev/null || true
	mv "$STORE.tmp" "$STORE"
	printf '%s=%s\n' "$k" "$v" >> "$STORE"
	exit 0
	;;
  commit) exit 0 ;;
esac
exit 0
UCI
	chmod +x "$MOCK/bin/uci"

	cat > "$MOCK/bin/logger" <<'LOG'
#!/bin/bash
echo "logger: $*" >> "$MOCK_LOG"
LOG
	chmod +x "$MOCK/bin/logger"
	printf '#!/bin/bash\necho "h3c,rt3000"\n' > "$MOCK/bin/board_name"
	chmod +x "$MOCK/bin/board_name"

	export MOCK_STATE="$MOCK/tmp/uci.state"
	: > "$MOCK_STATE"
	export MOCK_LOG="$MOCK/tmp/logger.log"
	: > "$MOCK_LOG"
	export MOCK
	export SYSROOT="$MOCK/sys"
}

# Seed the UCI store with what detect_mac80211 would have generated on a CLEAN
# image (no static wireless config): exactly one section per real PHY.
seed_detected_clean() {
	cat > "$MOCK_STATE" <<'EOF'
radio0=wifi-device
radio0.type=mac80211
radio0.path=platform/soc/c000000.wifi
radio0.band=2g
radio0.channel=1
radio0.htmode=HE20
radio0.disabled=1
default_radio0=wifi-iface
default_radio0.device=radio0
default_radio0.network=lan
default_radio0.mode=ap
default_radio0.ssid=OpenWrt
default_radio0.encryption=none
radio1=wifi-device
radio1.type=mac80211
radio1.path=platform/soc/soc:wifi1@c000000
radio1.band=5g
radio1.channel=36
radio1.htmode=HE80
radio1.disabled=1
default_radio1=wifi-iface
default_radio1.device=radio1
default_radio1.network=lan
default_radio1.mode=ap
default_radio1.ssid=OpenWrt
default_radio1.encryption=none
EOF
}

# Seed the store with the LEGACY broken topology (phantom radio1 + radio2):
# used to prove the fix detects the duplicate even if it somehow reappears.
seed_legacy_duplicate() {
	cat > "$MOCK_STATE" <<'EOF'
radio0=wifi-device
radio0.type=mac80211
radio0.path=platform/soc/c000000.wifi
radio0.band=2g
radio0.disabled=1
default_radio0=wifi-iface
default_radio0.device=radio0
radio1=wifi-device
radio1.type=mac80211
radio1.path=platform/soc/c000000.wifi+1
radio1.band=5g
radio1.disabled=1
default_radio1=wifi-iface
default_radio1.device=radio1
radio2=wifi-device
radio2.type=mac80211
radio2.path=platform/soc/soc:wifi1@c000000
radio2.band=5g
radio2.disabled=1
default_radio2=wifi-iface
default_radio2.device=radio2
default_radio2.ssid=OpenWrt
default_radio2.encryption=none
EOF
}

# Run the real script against the mock.
run_script() {
	# A stub mac.sh supplying a fixed MACMAP keyed to the frozen expectations.
	# Only written when the caller has not installed its own stub (T7 uses a
	# failing one to exercise the fail-closed path).
	[ -f "$MOCK/bin/rt3000_mac_stub.sh" ] || cat > "$MOCK/bin/rt3000_mac_stub.sh" <<'STUB'
rt3000_mac_map() {
	cat <<'MAP'
wan 00:11:22:33:44:55
lan 9e:a7:ce:69:5e:6a
wifi24 da:96:3b:3f:c7:c2
wifi5 2e:1c:f2:2a:33:76
MAP
}
STUB
	# The script sources /lib/rt3000/mac.sh, calls board_name, and reads the
	# sysfs wifi tree.  Rewrite those three anchors to the mock equivalents.
	# SYSROOT is exported so the paths stay resolvable at run time.
	sed -e 's#^\. /lib/rt3000/mac\.sh$#. "$MOCK/bin/rt3000_mac_stub.sh"#' \
	    -e 's#\bboard_name\b#"$MOCK/bin/board_name"#g' \
	    -e "s#/sys/class/ieee80211#\$SYSROOT/class/ieee80211#g" \
	    -e "s#/sys/devices/#\$SYSROOT/devices/#g" \
	    "$SCRIPT" > "$MOCK/tmp/script.sh"
	chmod +x "$MOCK/tmp/script.sh"

	SYSROOT="$MOCK/sys" \
	MOCK="$MOCK" MOCK_STATE="$MOCK_STATE" MOCK_LOG="$MOCK_LOG" \
	PATH="$MOCK/bin:$PATH" \
		sh "$MOCK/tmp/script.sh" >/dev/null 2>&1
	return $?
}

state_get() { sed -n "s/^$1=//p" "$MOCK_STATE" | head -1; }
count_devices() { grep -c '=wifi-device$' "$MOCK_STATE" 2>/dev/null || echo 0; }

# ===========================================================================
echo "==================================================================="
echo " RT3000 Wi-Fi duplicate-radio regression suite"
echo " script under test: $SCRIPT"
echo "==================================================================="

# ---------------------------------------------------------------------------
echo
echo "[T1] clean first boot -> exactly one section per real PHY"
setup_mock; seed_detected_clean; run_script
chk "T1.1 wifi-device section count" "$(count_devices)" "2"
chk "T1.2 no phantom path present" "$(grep -c 'c000000.wifi+1' "$MOCK_STATE")" "0"
chk "T1.3 2.4G path preserved" "$(state_get radio0.path)" "platform/soc/c000000.wifi"
chk "T1.4 5G path is real QCN6102 node" "$(state_get radio1.path)" "platform/soc/soc:wifi1@c000000"

# ---------------------------------------------------------------------------
echo
echo "[T2] no duplicate 5 GHz radio (the core defect)"
setup_mock; seed_detected_clean; run_script
n5=0
for s in $(sed -n 's/^\([a-zA-Z0-9_]*\)=wifi-device$/\1/p' "$MOCK_STATE"); do
	[ "$(state_get "$s.band")" = "5g" ] && n5=$((n5+1))
done
chk "T2.1 number of 5g wifi-device sections" "$n5" "1"
n24=0
for s in $(sed -n 's/^\([a-zA-Z0-9_]*\)=wifi-device$/\1/p' "$MOCK_STATE"); do
	[ "$(state_get "$s.band")" = "2g" ] && n24=$((n24+1))
done
chk "T2.2 number of 2g wifi-device sections" "$n24" "1"

# ---------------------------------------------------------------------------
echo
echo "[T3] shipped defaults: both bands enabled and WPA2-secured, never open"
setup_mock; seed_detected_clean
# An inherited key must not survive application of fresh-image defaults.
echo 'default_radio0.key=fixture-old-key' >> "$MOCK_STATE"
run_script
chk "T3.1 2.4G radio enabled" "$(state_get radio0.disabled)" "0"
chk "T3.2 5G radio enabled" "$(state_get radio1.disabled)" "0"
chk "T3.3 2.4G iface enabled" "$(state_get default_radio0.disabled)" "0"
chk "T3.4 5G iface enabled" "$(state_get default_radio1.disabled)" "0"
chk "T3.5 2.4G authentication policy" "$(state_get default_radio0.encryption)" "psk2"
chk "T3.6 2.4G SSID" "$(state_get default_radio0.ssid)" "RT3000"
chk "T3.7 5G authentication policy" "$(state_get default_radio1.encryption)" "psk2"
chk "T3.8 5G SSID" "$(state_get default_radio1.ssid)" "RT3000-5G"
# The defect this guards: a shipped image must never broadcast an open AP.
chk "T3.9 no encryption=none survives" "$(grep -c '\.encryption=none$' "$MOCK_STATE")" "0"
chk "T3.10 no stock OpenWrt SSID survives" "$(grep -c '\.ssid=OpenWrt$' "$MOCK_STATE")" "0"
chk "T3.11 both bands carry the shipped key" "$(grep -c '\.key=RTRCRWNX$' "$MOCK_STATE")" "2"
chk "T3.12 inherited fixture key is gone" "$(grep -c 'fixture-old-key' "$MOCK_STATE")" "0"
chk "T3.13 2.4G AP joins LAN" "$(state_get default_radio0.network)" "lan"
chk "T3.14 2.4G interface is an AP" "$(state_get default_radio0.mode)" "ap"
# 5 GHz must stay inside the non-DFS 36-48 block so the AP starts without CAC.
chk "T3.15 2.4G channel width" "$(state_get radio0.htmode)" "HE20"
chk "T3.16 5G channel width stays non-DFS" "$(state_get radio1.htmode)" "HE80"

# ---------------------------------------------------------------------------
echo
echo "[T4] Wi-Fi MAC policy bound to the CORRECT physical radio"
setup_mock; seed_detected_clean; run_script
chk "T4.1 WiFi24 MAC on the 2.4G radio" "$(state_get radio0.macaddr)" "da:96:3b:3f:c7:c2"
chk "T4.2 WiFi5 MAC on the QCN6102 radio" "$(state_get radio1.macaddr)" "2e:1c:f2:2a:33:76"
# The interface section is the one that actually programs the hardware for
# 'mode ap' (mac80211_prepare_vif -> mac80211_hostapd_setup_bss).  A MAC present
# only on the wifi-device section never reaches the running interface, which is
# the defect found on hardware in PHASE 8B.  Both must carry it.
chk "T4.4 WiFi24 MAC on the 2.4G iface" "$(state_get default_radio0.macaddr)" "da:96:3b:3f:c7:c2"
chk "T4.5 WiFi5 MAC on the QCN6102 iface" "$(state_get default_radio1.macaddr)" "2e:1c:f2:2a:33:76"
# The 5 GHz MAC must NOT appear on the 2.4 GHz radio and vice versa.
[ "$(state_get radio0.macaddr)" != "$(state_get radio1.macaddr)" ] \
	&& ok "T4.3 the two radios carry distinct MACs" \
	|| bad "T4.3 both radios carry the same MAC"

# ---------------------------------------------------------------------------
echo
echo "[T5] phantom-path regression guard (index-independence)"
setup_mock; seed_legacy_duplicate; run_script
# Even given the broken legacy layout, the phantom section must not receive a
# usable 5 GHz identity, and the real radio must.
chk "T5.1 real QCN6102 section keeps the WiFi5 MAC" \
	"$(state_get radio2.macaddr)" "2e:1c:f2:2a:33:76"
chk "T5.2 phantom path is not treated as the 5 GHz radio" \
	"$(state_get radio2.path)" "platform/soc/soc:wifi1@c000000"
# radio1's path is unresolvable, so it must not be claimed as the 5G radio.
[ "$(state_get radio1.macaddr)" != "2e:1c:f2:2a:33:76" ] \
	&& ok "T5.3 phantom section did not receive the WiFi5 MAC" \
	|| bad "T5.3 phantom section wrongly received the WiFi5 MAC"

# ---------------------------------------------------------------------------
echo
echo "[T6] index-independence: policy follows path, not radioN order"
setup_mock
# Same two PHYs, but detected in the OPPOSITE order (5 GHz enumerated first).
cat > "$MOCK_STATE" <<'EOF'
radio0=wifi-device
radio0.type=mac80211
radio0.path=platform/soc/soc:wifi1@c000000
radio0.band=5g
radio0.disabled=1
default_radio0=wifi-iface
default_radio0.device=radio0
radio1=wifi-device
radio1.type=mac80211
radio1.path=platform/soc/c000000.wifi
radio1.band=2g
radio1.disabled=1
default_radio1=wifi-iface
default_radio1.device=radio1
EOF
run_script
chk "T6.1 5G radio (now radio0) got the WiFi5 MAC" "$(state_get radio0.macaddr)" "2e:1c:f2:2a:33:76"
chk "T6.2 2.4G radio (now radio1) got the WiFi24 MAC" "$(state_get radio1.macaddr)" "da:96:3b:3f:c7:c2"
chk "T6.3 5G band still asserted by path" "$(state_get radio0.band)" "5g"
chk "T6.4 2.4G band still asserted by path" "$(state_get radio1.band)" "2g"

chk "T6.5 swapped 2.4G radio enabled" "$(state_get radio1.disabled)" "0"
chk "T6.6 swapped 2.4G iface enabled" "$(state_get default_radio1.disabled)" "0"
chk "T6.7 swapped 2.4G iface secured" "$(state_get default_radio1.encryption)" "psk2"
chk "T6.8 swapped 5G radio enabled" "$(state_get radio0.disabled)" "0"
chk "T6.9 swapped 5G iface enabled" "$(state_get default_radio0.disabled)" "0"
chk "T6.10 swapped 5G iface uses psk2" "$(state_get default_radio0.encryption)" "psk2"

# ---------------------------------------------------------------------------
echo
echo "[T7] fail-closed: unusable factory MAC must not invent identities"
setup_mock; seed_detected_clean
cat > "$MOCK/bin/rt3000_mac_stub.sh" <<'STUB'
rt3000_mac_map() { return 1; }
STUB
run_script
chk "T7.1 no MAC invented on radio0" "$(state_get radio0.macaddr)" ""
chk "T7.2 no MAC invented on radio1" "$(state_get radio1.macaddr)" ""
chk "T7.3 no MAC invented on the 2.4G iface" "$(state_get default_radio0.macaddr)" ""
chk "T7.4 no MAC invented on the 5G iface" "$(state_get default_radio1.macaddr)" ""
# A missing factory MAC must not silently downgrade the radio policy: identity
# is withheld, but both bands still come up enabled and secured.
chk "T7.5 2.4G policy still applied" "$(state_get radio0.disabled)" "0"
chk "T7.6 5G policy still applied" "$(state_get radio1.disabled)" "0"
chk "T7.7 2.4G still secured without a MAC" "$(state_get default_radio0.encryption)" "psk2"
chk "T7.8 5G still secured without a MAC" "$(state_get default_radio1.encryption)" "psk2"
chk "T7.9 fail-closed is logged" "$(grep -c 'factory MAC unusable' "$MOCK_LOG")" "1"

# ---------------------------------------------------------------------------
echo
echo "[T8] static wireless config must NOT be shipped (root-cause guard)"
REPO_GUESS="${REPO_ROOT:-}"
if [ -n "$REPO_GUESS" ] && [ -d "$REPO_GUESS" ]; then
	if [ -e "$REPO_GUESS/target/linux/ipq50xx/base-files/etc/config/wireless" ]; then
		bad "T8.1 static /etc/config/wireless is still shipped (root cause)"
	else
		ok "T8.1 static /etc/config/wireless is absent"
	fi
	# The fabricated path may still be *documented* in explanatory comments;
	# what must not survive is an active option setting it.
	if grep -rqs "^[[:space:]]*option[[:space:]]\+path[[:space:]]\+'platform/soc/c000000\.wifi+1'" \
			"$REPO_GUESS/target/linux/ipq50xx/base-files/" 2>/dev/null; then
		bad "T8.2 fabricated path 'c000000.wifi+1' still set as a live option"
	else
		ok "T8.2 fabricated path 'c000000.wifi+1' is not set anywhere as a live option"
	fi
	# And no wireless config file may be shipped at all.
	if [ -e "$REPO_GUESS/target/linux/ipq50xx/base-files/etc/config/wireless" ]; then
		bad "T8.3 a static wireless config is still shipped"
	else
		ok "T8.3 no static wireless config is shipped"
	fi
else
	echo "  SKIP  T8 (set REPO_ROOT to enable the source-tree guards)"
fi

# ===========================================================================
echo
echo "==================================================================="
printf ' TOTAL: %d passed, %d failed\n' "$PASS" "$FAIL"
echo "==================================================================="
rm -rf "$MOCK" 2>/dev/null
[ "$FAIL" -eq 0 ] || exit 1
exit 0
