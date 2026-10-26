include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=leds-rt3000-paired
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define KernelPackage/leds-rt3000-paired
  SUBMENU:=LED modules
  TITLE:=H3C RT3000 C paired system LED GPIO driver
  DEPENDS:=@TARGET_ipq50xx
  FILES:=$(PKG_BUILD_DIR)/leds-rt3000-paired.ko
  AUTOLOAD:=$(call AutoLoad,60,leds-rt3000-paired,1)
  KCONFIG:=
endef

define KernelPackage/leds-rt3000-paired/description
 C-only platform driver for the two paired RT3000 system LED GPIO outputs.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./src/leds-rt3000-paired.c ./src/Makefile $(PKG_BUILD_DIR)/
endef

MAKE_OPTS:= \
	$(KERNEL_MAKE_FLAGS) \
	M="$(PKG_BUILD_DIR)"

define Build/Compile
	$(MAKE) -C "$(LINUX_DIR)" $(MAKE_OPTS) modules
endef

$(eval $(call KernelPackage,leds-rt3000-paired))
