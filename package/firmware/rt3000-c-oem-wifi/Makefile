include $(TOPDIR)/rules.mk

PKG_NAME:=rt3000-c-oem-wifi
PKG_VERSION:=20260925
PKG_RELEASE:=3
PKG_LICENSE:=Proprietary
PKG_FLAGS:=nonshared
PKG_FILE_DEPENDS:=./files/
# A multi-profile config sets CONFIG_TARGET_DEVICE_<target>_DEVICE_<name>,
# a single-profile one CONFIG_TARGET_<target>_DEVICE_<name>; accept both.
c_profile = $(filter y,$(CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_$(1)) $(CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_$(1)))

ifneq ($(call c_profile,installer_ram),)
ifeq ($(strip $(RT3000_C_INSTALLER_QCN6122_BDF)),)
$(error RT3000_C_INSTALLER_QCN6122_BDF is required for the RAM installer profile)
endif
RT3000_C_QCN6122_BOARD2:=$(RT3000_C_INSTALLER_QCN6122_BDF)
PKG_FILE_DEPENDS+=$(RT3000_C_INSTALLER_QCN6122_BDF)
else ifneq ($(call c_profile,native_slot1),)
ifneq ($(strip $(RT3000_C_NATIVE_QCN6122_BDF)),)
ifeq ($(wildcard $(RT3000_C_NATIVE_QCN6122_BDF)),)
$(error RT3000_C_NATIVE_QCN6122_BDF does not exist)
endif
RT3000_C_QCN6122_BOARD2:=$(RT3000_C_NATIVE_QCN6122_BDF)
PKG_FILE_DEPENDS+=$(RT3000_C_NATIVE_QCN6122_BDF)
else
# WLAN.HK.2.7 asserts phyrf_bdf.c:6245 ANTENNACHAIN_AXIS_Z on the raw OEM
# body; the native default is the same container with body 0x45c cleared.
RT3000_C_QCN6122_BOARD2:=./files/board-2-qcn6122-axis0.bin
endif
else
RT3000_C_QCN6122_BOARD2:=./files/board-2-qcn6122.bin
endif

# Every C profile uses the calibration of the unit it runs on: the ath11k
# caldata paths link to copies a preinit hook takes from the local ART.
define RT3000_C_INSTALL_CALDATA
	$(INSTALL_DIR) $(1)/lib/preinit
	$(INSTALL_DATA) ./files/05_rt3000_c_caldata $(1)/lib/preinit/05_rt3000_c_caldata
	$(LN) /tmp/rt3000-c-cal/ipq5018.bin $(1)/lib/firmware/ath11k/IPQ5018/hw1.0/caldata.bin
	$(LN) /tmp/rt3000-c-cal/qcn6122.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/caldata_1.bin
endef

include $(INCLUDE_DIR)/package.mk

define Package/rt3000-c-oem-wifi
  SECTION:=firmware
  CATEGORY:=Firmware
  TITLE:=Private C2 OEM board data and ART calibration for RAM bring-up
  DEPENDS:=@TARGET_ipq50xx_arm +ath11k-firmware-ipq5018 +ath11k-firmware-qcn6122
endef

define Package/rt3000-c-oem-wifi/description
  Machine-C-only board-2 containers and ART calibration extracted from the
  current C2 OEM firmware and partition backup. Private development only.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Compile
endef

define Package/rt3000-c-oem-wifi/install
	cd $(CURDIR) && sha256sum -c files/SHA256SUMS
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/IPQ5018/hw1.0
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/qcn6122/hw1.0
	$(INSTALL_DATA) ./files/board-2-ipq5018.bin $(1)/lib/firmware/ath11k/IPQ5018/hw1.0/board-2.bin
	$(INSTALL_DATA) $(RT3000_C_QCN6122_BOARD2) $(1)/lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin
	$(call RT3000_C_INSTALL_CALDATA,$(1))
endef

$(eval $(call BuildPackage,rt3000-c-oem-wifi))
