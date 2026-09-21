include $(TOPDIR)/rules.mk

PKG_NAME:=rt3release
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/rt3release
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=RT3000 Machine-B stable firmware identity
  DEPENDS:=@NAND_SUPPORT
endef

define Package/rt3release/description
  Stable content-derived firmware identity for RT3000 Machine-B.
  Verifies the running QSDK slot by hashing the kernel and rootfs payloads and
  comparing them against /etc/rt3000-release.json.  Never uses UBI image_seq,
  EC counters, VID headers or PEB placement as identity.
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -D_FILE_OFFSET_BITS=64 \
		-o $(PKG_BUILD_DIR)/rt3release $(CURDIR)/src/rt3release.c
endef

define Package/rt3release/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/rt3release $(1)/usr/sbin/
endef

$(eval $(call BuildPackage,rt3release))
