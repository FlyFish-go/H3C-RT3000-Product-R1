include $(TOPDIR)/rules.mk
PKG_NAME:=hwd-factory-mac
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKG_FILE_DEPENDS:=./src/ ./files/
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)
include $(INCLUDE_DIR)/package.mk
define Package/hwd-factory-mac
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Read-only HW-D factory MAC resolver
  DEPENDS:=@TARGET_ipq50xx
endef
define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(CP) ./src/hwd-factory-mac.c $(PKG_BUILD_DIR)/
endef
define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -std=gnu11 -Wall -Wextra -Werror \
		$(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/hwd-factory-mac $(PKG_BUILD_DIR)/hwd-factory-mac.c
endef
define Package/hwd-factory-mac/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/hwd-factory-mac $(1)/usr/sbin/hwd-factory-mac
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/rc.d
	$(INSTALL_BIN) ./files/hwd-factory-mac.init $(1)/etc/init.d/hwd-factory-mac
	$(LN) ../init.d/hwd-factory-mac $(1)/etc/rc.d/S19hwd-factory-mac
endef
$(eval $(call BuildPackage,hwd-factory-mac))
