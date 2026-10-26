# External proposal only. Canonical destination:
# package/firmware/rt3000-c-dsa-master/Makefile
include $(TOPDIR)/rules.mk

PKG_NAME:=rt3000-c-dsa-master
PKG_VERSION:=20261005
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-or-later
PKG_FILE_DEPENDS:=./files/

include $(INCLUDE_DIR)/package.mk

define Package/rt3000-c-dsa-master
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=C-native RT3000 RTL8367S DSA master retry
  DEPENDS:=@TARGET_ipq50xx_arm
endef

define Package/rt3000-c-dsa-master/description
C-native-only, identity-gated retry for the RTL8367S DSA probe after NSS dp2
registers as eth1. A bounded init reconciliation handles an early net event.
endef

define Build/Compile
endef

define Package/rt3000-c-dsa-master/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/etc/hotplug.d/net $(1)/etc/init.d $(1)/etc/rc.d
	$(INSTALL_BIN) ./files/usr/libexec/rt3000-c-dsa-master-bind \
		$(1)/usr/libexec/rt3000-c-dsa-master-bind
	$(INSTALL_BIN) ./files/etc/hotplug.d/net/10-rt3000-c-dsa-master \
		$(1)/etc/hotplug.d/net/10-rt3000-c-dsa-master
	$(INSTALL_BIN) ./files/etc/init.d/rt3000-c-dsa-master \
		$(1)/etc/init.d/rt3000-c-dsa-master
	$(LN) ../init.d/rt3000-c-dsa-master \
		$(1)/etc/rc.d/S19rt3000-c-dsa-master
endef

$(eval $(call BuildPackage,rt3000-c-dsa-master))
