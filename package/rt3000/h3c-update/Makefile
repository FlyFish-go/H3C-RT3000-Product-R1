# SPDX-License-Identifier: GPL-2.0-only
#
# Firmware update check, download and install for H3C Magic builds.
# The release line and release name are baked in at build time:
#   CONFIG_H3C_UPDATE_LINE="r"   (QSDK line)  or  "nss"
#   CONFIG_H3C_UPDATE_RELEASE="r12"           or  "v0.1.0-pre.5"

include $(TOPDIR)/rules.mk

PKG_NAME:=h3c-update
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

H3C_LINE:=$(call qstrip,$(CONFIG_H3C_UPDATE_LINE))
H3C_RELEASE:=$(call qstrip,$(CONFIG_H3C_UPDATE_RELEASE))

H3C_REPO_r:=H3C-RT3000-Product-R1
H3C_REPO_nss:=H3C-Magic-NSS
H3C_REPO:=$(H3C_REPO_$(H3C_LINE))

# QSDK line: one image per build run, so the hardware group follows the one
# device selected for this run. Only HW-B is enabled for now. The NSS line
# builds all boards in one run; its group comes from the image's device tree
# at run time (see update.sh).
R_DEV:=CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c
H3C_GROUP:=
ifeq ($(H3C_LINE),r)
  ifeq ($($(R_DEV)_rt3000)$($(R_DEV)_rw3000_hw_a)$($(R_DEV)_rt3000_rtl8367s_native_slot1)$($(R_DEV)_nx30_hw_d),y)
    ifeq ($($(R_DEV)_rt3000),y)
      H3C_GROUP:=HW-B
    endif
  endif
endif

PKG_CONFIG_DEPENDS:= \
	CONFIG_H3C_UPDATE_LINE CONFIG_H3C_UPDATE_RELEASE \
	$(R_DEV)_rt3000 $(R_DEV)_rw3000_hw_a \
	$(R_DEV)_rt3000_rtl8367s_native_slot1 $(R_DEV)_nx30_hw_d

include $(INCLUDE_DIR)/package.mk

define Package/h3c-update
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=H3C Magic firmware update check and install
  DEPENDS:=+uclient-fetch +usign +jsonfilter +ca-bundle
  PKGARCH:=all
endef

define Package/h3c-update/description
  Checks GitHub and Gitee for a newer signed H3C Magic release, downloads
  the image for this hardware group, verifies it and installs it with
  sysupgrade. Automatic checking is off by default.
endef

define Package/h3c-update/config
	config H3C_UPDATE_LINE
		string "Release line (r or nss)"
		depends on PACKAGE_h3c-update
		default ""

	config H3C_UPDATE_RELEASE
		string "Release name of this build"
		depends on PACKAGE_h3c-update
		default ""
endef

define Package/h3c-update/conffiles
/etc/config/h3c_update
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Configure
endef

define Build/Compile
	@[ -n "$(H3C_REPO)" ] && [ -n "$(H3C_RELEASE)" ] || { \
		echo "h3c-update: set CONFIG_H3C_UPDATE_LINE (r|nss) and CONFIG_H3C_UPDATE_RELEASE" >&2; \
		exit 1; }
endef

define Package/h3c-update/install
	$(INSTALL_DIR) $(1)/etc/h3c-update/keys $(1)/etc/config $(1)/etc/init.d \
		$(1)/usr/libexec/h3c-update $(1)/usr/libexec/rpcd
	$(INSTALL_DATA) ./files/keys/* $(1)/etc/h3c-update/keys/
	$(INSTALL_CONF) ./files/h3c_update.config $(1)/etc/config/h3c_update
	$(INSTALL_BIN) ./files/h3c-update.init $(1)/etc/init.d/h3c-update
	$(INSTALL_BIN) ./files/update.sh $(1)/usr/libexec/h3c-update/update.sh
	$(INSTALL_BIN) ./files/h3c.update $(1)/usr/libexec/rpcd/h3c.update
	printf 'H3C_LINE=%s\nH3C_REPO=%s\nH3C_RELEASE=%s\nH3C_GROUP=%s\n' \
		'$(H3C_LINE)' '$(H3C_REPO)' '$(H3C_RELEASE)' '$(H3C_GROUP)' \
		> $(1)/etc/h3c-update/build
endef

define Package/h3c-update/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
/etc/init.d/h3c-update enable
/etc/init.d/h3c-update start
/etc/init.d/rpcd reload
exit 0
endef

define Package/h3c-update/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
sed -i '/h3c-update/d' /etc/crontabs/root 2>/dev/null
/etc/init.d/cron restart
exit 0
endef

$(eval $(call BuildPackage,h3c-update))
