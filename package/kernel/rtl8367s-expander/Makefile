include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=rtl8367s-expander
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define KernelPackage/rtl8367s-expander
  SUBMENU:=Network Devices
  TITLE:=H3C RT3000 HW-C RTL8367S port-expander setup
  DEPENDS:=@TARGET_ipq50xx
  FILES:=$(PKG_BUILD_DIR)/rtl8367s-expander.ko
  AUTOLOAD:=$(call AutoLoad,35,rtl8367s-expander)
  KCONFIG:=
endef

define KernelPackage/rtl8367s-expander/description
  Checks that the RTL8367S on HW-C is in the untagged port-expander state
  left by h3c-common4 U-Boot and repeats that setup when it is not.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./src/rtl8367s-expander.c ./src/Makefile $(PKG_BUILD_DIR)/
endef

MAKE_OPTS:= \
	$(KERNEL_MAKE_FLAGS) \
	M="$(PKG_BUILD_DIR)"

define Build/Compile
	$(MAKE) -C "$(LINUX_DIR)" $(MAKE_OPTS) modules
endef

$(eval $(call KernelPackage,rtl8367s-expander))
