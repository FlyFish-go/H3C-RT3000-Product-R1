include $(TOPDIR)/rules.mk

PKG_NAME:=rt3slot
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/rt3slot
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=RT3000 Machine-B native slot manager
  DEPENDS:=+rt3bcwrite
endef

define Package/rt3slot/description
  Product command for verified OEM/QSDK target selection on RT3000 Machine-B.
endef

define Build/Compile
endef

define Package/rt3slot/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/rt3slot $(1)/usr/sbin/rt3slot
endef

$(eval $(call BuildPackage,rt3slot))
