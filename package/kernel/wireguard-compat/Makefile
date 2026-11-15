#
# WireGuard for the QSDK 5.4 kernel. That kernel does not carry the WireGuard
# backport from target/linux/generic, so build the official out-of-tree module
# for kernels before 5.6 and package it as kmod-wireguard, which wireguard-tools
# and luci-proto-wireguard from the OpenWrt 21.02 feeds depend on.
#
include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=wireguard-linux-compat
PKG_VERSION:=1.0.20220627
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://git.zx2c4.com/wireguard-linux-compat/snapshot/
PKG_HASH:=19b181e5c7d2260c23ecad4ad324425fd8e88200d97a885a2c7d4bd26cd61461

PKG_LICENSE:=GPL-2.0
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk

define KernelPackage/wireguard
  SUBMENU:=Network Support
  TITLE:=WireGuard secure network tunnel
  URL:=https://www.wireguard.com
  DEPENDS:=+kmod-udptunnel4 +IPV6:kmod-udptunnel6
  FILES:=$(PKG_BUILD_DIR)/src/wireguard.ko
  AUTOLOAD:=$(call AutoProbe,wireguard)
endef

define KernelPackage/wireguard/description
  WireGuard VPN kernel module, built from wireguard-linux-compat because the
  QSDK 5.4 kernel does not include WireGuard.
endef

define Build/Compile
	$(KERNEL_MAKE) M="$(PKG_BUILD_DIR)/src" modules
endef

$(eval $(call KernelPackage,wireguard))
