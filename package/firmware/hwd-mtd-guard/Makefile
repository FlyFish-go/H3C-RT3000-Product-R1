include $(TOPDIR)/rules.mk

PKG_NAME:=hwd-mtd-guard
PKG_RELEASE:=1
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)

include $(INCLUDE_DIR)/package.mk

define Package/hwd-mtd-guard
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Read-only HW-D NAND bad-block verifier
  DEPENDS:=@TARGET_ipq50xx
endef

define Package/hwd-mtd-guard/description
Read-only exact-map gate for the HW-D EF:BA:21 2 KiB/64-byte-OOB NAND sample.
Scans every eraseblock in the protected or selected target MTD using MEMGETBADBLOCK.
endef

define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(CP) ./src/hwd-mtd-guard.c $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -std=gnu11 -Wall -Wextra -Werror \
		$(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/hwd-mtd-guard $(PKG_BUILD_DIR)/hwd-mtd-guard.c
endef

define Package/hwd-mtd-guard/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/hwd-mtd-guard $(1)/usr/sbin/hwd-mtd-guard
endef

$(eval $(call BuildPackage,hwd-mtd-guard))
