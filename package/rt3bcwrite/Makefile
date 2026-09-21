include $(TOPDIR)/rules.mk

PKG_NAME:=rt3bcwrite
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/rt3bcwrite
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=RT3000 BOOTCONFIG A/B selector writer
  DEPENDS:=@NAND_SUPPORT
endef

define Package/rt3bcwrite/description
  Fail-closed selector update for redundant RT3000 BOOTCONFIG MTD copies.
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -D_FILE_OFFSET_BITS=64 \
		-o $(PKG_BUILD_DIR)/rt3bcwrite $(CURDIR)/src/rt3bcwrite.c
endef

define Package/rt3bcwrite/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/rt3bcwrite $(1)/usr/sbin/
endef

$(eval $(call BuildPackage,rt3bcwrite))
