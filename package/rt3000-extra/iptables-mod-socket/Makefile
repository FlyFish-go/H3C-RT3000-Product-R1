# H3C Magic: on this 21.02 tree the iptables socket match (libxt_socket and
# xt_socket) ships inside iptables-mod-tproxy / kmod-ipt-tproxy; OpenWrt 22.03
# split it out. PassWall checks for an installed iptables-mod-socket package,
# so this one only pulls in the package that really carries the match.

include $(TOPDIR)/rules.mk

PKG_NAME:=iptables-mod-socket
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/iptables-mod-socket
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Firewall
  TITLE:=iptables socket match (provided by iptables-mod-tproxy)
  PKGARCH:=all
  DEPENDS:=+iptables-mod-tproxy +kmod-ipt-tproxy
endef

define Build/Compile
endef

define Package/iptables-mod-socket/install
	true
endef

$(eval $(call BuildPackage,iptables-mod-socket))
