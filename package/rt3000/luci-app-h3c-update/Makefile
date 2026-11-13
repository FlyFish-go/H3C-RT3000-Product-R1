# SPDX-License-Identifier: GPL-2.0-only
#
# System -> Firmware Update: check, download and install new H3C Magic
# releases. Status -> Overview shows a line when a new release is found.

include $(TOPDIR)/rules.mk

LUCI_TITLE:=Firmware update page for H3C Magic builds
LUCI_DEPENDS:=+luci-base +h3c-update
LUCI_PKGARCH:=all

PKG_LICENSE:=GPL-2.0-only

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
