# C-native-only package. Package path: package/firmware/rt3000-c-mac-identity-ro/Makefile
include $(TOPDIR)/rules.mk

PKG_NAME:=rt3000-c-mac-identity-ro
PKG_VERSION:=20261004
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-or-later
PKG_FILE_DEPENDS:=./src/ ./files/
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)

include $(INCLUDE_DIR)/package.mk

define Package/rt3000-c-mac-identity-ro
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Read-only C-native factory MAC resolver
  DEPENDS:=@TARGET_ipq50xx_arm +libgcc
endef

define Package/rt3000-c-mac-identity-ro/description
C-native-only helper. It validates the exact C APPSBLENV physical range,
partition identity, geometry, read-only flags and DT model before reading one
main-data page through the mtdXro character node. It prints only a valid ethaddr.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./src/c_mtd_mac_identity_ro.c $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) -std=c99 -Wall -Wextra -Werror \
		-o $(PKG_BUILD_DIR)/c-mtd-mac-identity-ro \
		$(PKG_BUILD_DIR)/c_mtd_mac_identity_ro.c
endef

define Package/rt3000-c-mac-identity-ro/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/lib/rt3000
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/c-mtd-mac-identity-ro \
		$(1)/usr/sbin/c-mtd-mac-identity-ro
	$(INSTALL_DATA) ./files/native-c-mac.sh $(1)/lib/rt3000/c-mac.sh
endef

$(eval $(call BuildPackage,rt3000-c-mac-identity-ro))

# Add `rt3000-c-mac-identity-ro` only to
# Device/h3c_rt3000_rtl8367s_native_slot1's DEVICE_PACKAGES list.
# Do not add it to B, C RAM, or installer profiles.
