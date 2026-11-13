#!/bin/sh
# H3C Magic: prepare the extra package feeds after "./scripts/feeds update -a".
#
# The images do not contain these packages; they go to the extra package
# repository published with each release (OpenClash, PassWall and what they
# need, Tailscale, AdGuard Home, Argon settings).
#
#  - Go: the 21.02 packages feed has Go 1.18; Xray, sing-box and hysteria
#    need Go 1.27. Replace feeds/packages/lang/golang with a pinned copy of
#    sbwml/packages_lang_golang (a drop-in for this build system).
#  - passwall_packages carries a newer xray-core than the packages feed and
#    must win; smartdns from it does not parse on 21.02 and is skipped.
#  - sing-box depends on kmod-inet-diag, which this kernel does not build
#    (only process-based routing uses it).
set -eu
cd "$(dirname "$0")/.."
GO_REPO=https://github.com/sbwml/packages_lang_golang
GO_COMMIT=a7942fbbc78a482c32b71bfee659d2327570ea33
G=feeds/packages/lang/golang
if [ "$(cat $G/.h3c-go-commit 2>/dev/null)" != "$GO_COMMIT" ]; then
	tmp=$(mktemp -d)
	git -C "$tmp" init -q
	git -C "$tmp" fetch -q --depth 1 "$GO_REPO" "$GO_COMMIT"
	git -C "$tmp" checkout -q FETCH_HEAD
	rm -rf "$tmp/.git" "$G"
	mv "$tmp" "$G"
	echo "$GO_COMMIT" > "$G/.h3c-go-commit"
fi
sed -i 's/ +kmod-inet-diag//' feeds/passwall_packages/sing-box/Makefile
./scripts/feeds update -i packages passwall_packages passwall openclash
./scripts/feeds uninstall xray-core tailscale adguardhome >/dev/null 2>&1 || true
./scripts/feeds install -f -p passwall_packages chinadns-ng dns2socks geoview \
	hysteria ipt2socks microsocks simple-obfs sing-box tcping v2ray-geodata \
	v2ray-plugin xray-core xray-plugin
./scripts/feeds install -p passwall luci-app-passwall
./scripts/feeds install -p openclash luci-app-openclash
