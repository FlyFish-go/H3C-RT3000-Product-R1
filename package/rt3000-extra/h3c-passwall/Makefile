# H3C Magic: one package that pulls in PassWall with Xray and every runtime
# piece the iptables (fw3) transparent proxy needs on this QSDK build.
# Needs the merged single-system layout (80 MiB): Xray alone is about 30 MB.

include $(TOPDIR)/rules.mk

PKG_NAME:=h3c-passwall
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/h3c-passwall
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=PassWall with Xray and all runtime dependencies (H3C Magic)
  PKGARCH:=all
  DEPENDS:=+luci-app-passwall +luci-i18n-passwall-zh-cn +xray-core +geoview \
	+v2ray-geoip +v2ray-geosite +ipset +ipt2socks +dnsmasq-full \
	+iptables-mod-tproxy +iptables-mod-socket +iptables-mod-iprange \
	+iptables-mod-conntrack-extra +iptables-mod-extra +kmod-ipt-nat
endef

define Package/h3c-passwall/description
  Installs PassWall, its Chinese translation, Xray and the iptables
  transparent proxy dependencies in one step. Too large for the standard
  dual-system layout; switch to the merged 80 MiB layout first.
endef

define Build/Compile
endef

define Package/h3c-passwall/install
	true
endef

$(eval $(call BuildPackage,h3c-passwall))
