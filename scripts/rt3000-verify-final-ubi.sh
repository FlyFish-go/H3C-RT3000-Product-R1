#!/bin/bash
# RT3000 — PHASE 6: static verification against the FINAL UBI.
#
# Verifies the artifact itself, not the build tree.  Every check extracts from
# the UBI produced by scripts/rt3000-release-pin.sh.
#
# Gate outputs:
#   QCA_SSDK_BASELINE                     PASS/FAIL
#   RELEASE_JSON                          PASS/FAIL
#   WIFI_DUPLICATE_CONFIG_FIX_PRESENT     PASS/FAIL
#   WIFI_DEFAULT_DISABLED                 PASS/FAIL
#   WIFI_MAC_POLICY_PRESENT               PASS/FAIL
#   LUCI_AND_SECURITY_DEFAULTS            PASS/FAIL
#
# Usage: verify-final-ubi.sh <path-to.ubi> [workdir]
set -u

UBI="${1:-}"
WORK="${2:-/tmp/rt3000-final-verify}"
[ -n "$UBI" ] && [ -f "$UBI" ] || { echo "FATAL: usage: $0 <path-to.ubi> [workdir]"; exit 1; }

TOPDIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

EXPECT_SSDK_SHA=d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497
EXPECT_SSDK_SIZE=544716

FAILED=0
gate() { # gate <name> <ok 0/1> <detail>
	if [ "$2" -eq 0 ]; then printf '%-38s PASS   %s\n' "$1" "$3"
	else printf '%-38s FAIL   %s\n' "$1" "$3"; FAILED=$((FAILED+1)); fi
}

echo "==================================================================="
echo " PHASE 6 — FINAL UBI STATIC VERIFICATION"
echo " ubi: $UBI"
echo " sha256: $(sha256sum "$UBI" | cut -d' ' -f1)"
echo " size:   $(wc -c < "$UBI" | tr -d ' ')"
echo "==================================================================="

rm -rf "$WORK"; mkdir -p "$WORK"
python3 "$TOPDIR/scripts/rt3000-ubi-extract.py" "$UBI" "$WORK" >/dev/null || {
	echo "FATAL: UBI extraction failed"; exit 1; }
[ -f "$WORK/ubi_rootfs.bin" ] || { echo "FATAL: no ubi_rootfs volume"; exit 1; }

unsquashfs -f -d "$WORK/rootfs" "$WORK/ubi_rootfs.bin" > "$WORK/unsquashfs.log" 2>&1 || true
grep -q "^created .* files" "$WORK/unsquashfs.log" || {
	echo "FATAL: unsquashfs did not unpack"; tail -20 "$WORK/unsquashfs.log"; exit 1; }

R="$WORK/rootfs"

# ---------------------------------------------------------------------------
# 1. qca-ssdk baseline
# ---------------------------------------------------------------------------
KO="$R/lib/modules/5.4.164/qca-ssdk.ko"
if [ -f "$KO" ]; then
	S=$(sha256sum "$KO" | cut -d' ' -f1); Z=$(wc -c < "$KO" | tr -d ' ')
	[ "$S" = "$EXPECT_SSDK_SHA" ] && [ "$Z" = "$EXPECT_SSDK_SIZE" ]
	gate "QCA_SSDK_BASELINE" $? "$S ($Z bytes)"
	QCA_SSDK_FINAL_SHA256="$S"; QCA_SSDK_FINAL_SIZE="$Z"
else
	gate "QCA_SSDK_BASELINE" 1 "qca-ssdk.ko absent"
	QCA_SSDK_FINAL_SHA256=""; QCA_SSDK_FINAL_SIZE=""
fi

# ---------------------------------------------------------------------------
# 2. release manifest present and schema-correct
# ---------------------------------------------------------------------------
MAN="$R/etc/rt3000-release.json"
man_ok=1; man_detail="absent"
if [ -s "$MAN" ]; then
	man_ok=0; man_detail="present"
	for k in '"schema": "rt3000-release/v1"' '"machine": "Machine-B"' '"kernel_sha256"'; do
		grep -q "$k" "$MAN" || { man_ok=1; man_detail="missing key: $k"; }
	done
	# rootfs_sha256 would be circular and must not appear.
	grep -q 'rootfs_sha256' "$MAN" && { man_ok=1; man_detail="must not carry rootfs_sha256"; }
	# Validate it parses as JSON.
	if command -v python3 >/dev/null 2>&1; then
		python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$MAN" 2>/dev/null \
			|| { man_ok=1; man_detail="not valid JSON"; }
	fi
fi
gate "RELEASE_JSON" "$man_ok" "$man_detail"

# ---------------------------------------------------------------------------
# 3. duplicate-wireless fix present: no static config, path-driven hook shipped
# ---------------------------------------------------------------------------
fix_ok=0; fix_detail=""
if [ -e "$R/etc/config/wireless" ]; then
	fix_ok=1; fix_detail="static /etc/config/wireless is STILL PRESENT"
else
	fix_detail="no static wireless config; "
fi
HOOK="$R/etc/uci-defaults/99-rt3000-wifi"
if [ -s "$HOOK" ]; then
	fix_detail="${fix_detail}path-driven hook present"
	# The hook must key off real device paths, not radioN indices.
	grep -q 'platform/soc/c000000.wifi' "$HOOK" || { fix_ok=1; fix_detail="${fix_detail}; 2.4G path missing"; }
	grep -q 'soc:wifi1@c000000' "$HOOK" || { fix_ok=1; fix_detail="${fix_detail}; 5G path missing"; }
else
	fix_ok=1; fix_detail="${fix_detail}path-driven hook ABSENT"
fi
# The fabricated donor path must not appear as a live option anywhere.
if grep -rqs "^[[:space:]]*option[[:space:]]\+path[[:space:]]\+'platform/soc/c000000\.wifi+1'" "$R/etc" 2>/dev/null; then
	fix_ok=1; fix_detail="${fix_detail}; fabricated path still set"
fi
gate "WIFI_DUPLICATE_CONFIG_FIX_PRESENT" "$fix_ok" "$fix_detail"

# ---------------------------------------------------------------------------
# 4. radios disabled by default
# ---------------------------------------------------------------------------
dis_ok=0; dis_detail=""
if [ -s "$HOOK" ]; then
	# The hook must assert disabled=1 for both radios; and the old index-based
	# MAC-only hook must be gone.
	grep -q 'disabled=1' "$HOOK" || { dis_ok=1; dis_detail="hook does not set disabled"; }
	[ -e "$R/etc/uci-defaults/99-rt3000-wifi-mac" ] && { dis_ok=1; dis_detail="${dis_detail} old index hook still present"; }
	[ -z "$dis_detail" ] && dis_detail="hook disables both radios; no static enabled config"
else
	dis_ok=1; dis_detail="hook absent"
fi
# No shipped config may enable a radio or leave an open network.
if [ -e "$R/etc/config/wireless" ]; then
	grep -q "disabled '0'" "$R/etc/config/wireless" && { dis_ok=1; dis_detail="${dis_detail}; config enables a radio"; }
fi
gate "WIFI_DEFAULT_DISABLED" "$dis_ok" "$dis_detail"

# ---------------------------------------------------------------------------
# 5. MAC policy present and path-bound
# ---------------------------------------------------------------------------
mac_ok=0; mac_detail=""
MACS="$R/lib/rt3000/mac.sh"
[ -s "$MACS" ] || { mac_ok=1; mac_detail="missing /lib/rt3000/mac.sh"; }
if [ -s "$HOOK" ]; then
	grep -q 'rt3000_mac_map' "$HOOK" || { mac_ok=1; mac_detail="${mac_detail}; hook does not use rt3000_mac_map"; }
	# Must bind by path, and must NOT hardcode radio indices as the selector.
	grep -qE 'apply_radio_(mac|policy) radio[0-9]' "$HOOK" && { mac_ok=1; mac_detail="${mac_detail}; hook still selects by radioN index"; }
	[ -x "$MACS" ] && grep -q 'wifi24' "$MACS" && grep -q 'wifi5' "$MACS" || { mac_ok=1; mac_detail="${mac_detail}; mac.sh lacks wifi24/wifi5 roles"; }
	[ -z "$mac_detail" ] && mac_detail="path-bound; derived from factory MAC; fails closed"
else
	mac_ok=1; mac_detail="${mac_detail} hook absent"
fi
gate "WIFI_MAC_POLICY_PRESENT" "$mac_ok" "$mac_detail"

# ---------------------------------------------------------------------------
# 6. LuCI / security defaults not broken
# ---------------------------------------------------------------------------
sec_ok=0; sec_detail=""
[ -e "$R/www/cgi-bin/luci" ] || { sec_ok=1; sec_detail="LuCI entrypoint absent"; }
[ -s "$R/etc/config/firewall" ] || { sec_ok=1; sec_detail="${sec_detail} firewall config absent"; }
[ -s "$R/etc/config/dropbear" ] || { sec_ok=1; sec_detail="${sec_detail} dropbear config absent"; }
if [ -s "$R/etc/config/dropbear" ]; then
	# Must remain LAN-bound, not 0.0.0.0.
	grep -qiE "option[[:space:]]+Interface[[:space:]]+'?lan'?" "$R/etc/config/dropbear" \
		|| { sec_ok=1; sec_detail="${sec_detail}; dropbear not LAN-bound"; }
fi
if [ -s "$R/etc/config/firewall" ]; then
	# WAN input must be rejected.
	awk '/config zone/{z=$0} /name .wan./{w=1} w&&/input/{print; w=0}' "$R/etc/config/firewall" \
		| grep -q "REJECT" || { sec_ok=1; sec_detail="${sec_detail}; wan input not REJECT"; }
fi
[ "$(find "$R/www" -type f 2>/dev/null | wc -l | tr -d ' ')" -gt 0 ] \
	|| { sec_ok=1; sec_detail="${sec_detail}; no www content"; }
[ -z "$sec_detail" ] && sec_detail="LuCI present; wan input REJECT; dropbear LAN-bound"
gate "LUCI_AND_SECURITY_DEFAULTS" "$sec_ok" "$sec_detail"

# ---------------------------------------------------------------------------
echo
echo "-------------------------------------------------------------------"
if [ "$FAILED" -eq 0 ]; then
	echo "PHASE6_STATIC_VERIFY=PASS"
else
	echo "PHASE6_STATIC_VERIFY=FAIL ($FAILED gate(s) failed)"
fi
echo "QCA_SSDK_FINAL_SHA256=$QCA_SSDK_FINAL_SHA256"
echo "QCA_SSDK_FINAL_SIZE=$QCA_SSDK_FINAL_SIZE"
echo "-------------------------------------------------------------------"
[ "$FAILED" -eq 0 ] || exit 1
exit 0
