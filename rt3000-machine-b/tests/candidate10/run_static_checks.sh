#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
ath="$root/package/kernel/mac80211/ath.mk"
dts="$root/target/linux/ipq50xx/dts/ipq5000-rt3000.dts"

grep -F 'MODPARAMS.ath11k:=nss_offload=1 frame_mode=2' "$ath" >/dev/null
grep -F 'nss_redirect = false' "$root/package/kernel/mac80211/patches/all-ipq50xx/207-mac80211-add-nss-redirect-support.patch" >/dev/null
test ! -e "$root/package/kernel/mac80211/patches/all-ipq50xx/611-ath11k-Enable-NSS-Redirect-by-default.patch"
if grep -R -F 'bool nss_redirect = true;' "$root/package/kernel/mac80211/patches/all-ipq50xx" >/dev/null; then
	printf '%s\n' 'nss_redirect true default remains in source patch chain' >&2
	exit 1
fi
prepared=$(find "$root/build_dir" -path '*/source/net/mac80211/iface.c' -print -quit 2>/dev/null || true)
if [ -n "$prepared" ]; then
	grep -F 'bool nss_redirect = false;' "$prepared" >/dev/null
	! grep -F 'bool nss_redirect = true;' "$prepared" >/dev/null
fi
grep -F 'nss-radio-priority = <0>;' "$dts" >/dev/null
grep -F 'nss-radio-priority = <1>;' "$dts" >/dev/null

if [ -e "$root/package/kernel/mac80211/patches/all-ipq50xx/603-ath11k-expand-qcn6122-rxdma-ring-256m.patch" ] || \
	[ -e "$root/rt3000-machine-b/bdf/qcn6122-oem-compatible-modal.patch" ]; then
	printf '%s\n' 'rejected RXDMA/modal experiment file remains in source tree' >&2
	exit 1
fi

! grep -R -E 'qcn6122-oem-compatible-modal|schema-safe-modal|603-ath11k-expand-qcn6122-rxdma-ring-256m' \
	"$root/package/kernel/mac80211" "$root/rt3000-machine-b/bdf" >/dev/null
printf '%s\n' 'candidate10 static source checks: PASS'
