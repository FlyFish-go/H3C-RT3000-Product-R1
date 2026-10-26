include $(TOPDIR)/rules.mk

PKG_NAME:=hwd-nx30-oem-wifi
PKG_VERSION:=20261023
PKG_RELEASE:=2
PKG_LICENSE:=Proprietary
PKG_FLAGS:=nonshared
PKG_FILE_DEPENDS:=./files/

include $(INCLUDE_DIR)/package.mk

# HW-D and the legacy RT3000 package install the same ath11k board-2.bin
# paths. Refuse a mixed profile before rootfs package installation can choose
# one file by package ordering.
ifeq ($(CONFIG_PACKAGE_hwd-nx30-oem-wifi),y)
ifneq ($(filter y m,$(CONFIG_PACKAGE_ipq-wifi-h3c_rt3000)),)
$(error hwd-nx30-oem-wifi cannot be combined with ipq-wifi-h3c_rt3000)
endif
endif

define Package/hwd-nx30-oem-wifi
  SECTION:=firmware
  CATEGORY:=Firmware
  TITLE:=NX30 HW-D OEM BDF (QCN6122 axis gate cleared), calibration from local ART
  DEPENDS:=@TARGET_ipq50xx_arm +ath11k-firmware-ipq5018 +ath11k-firmware-qcn6122
endef

define Package/hwd-nx30-oem-wifi/description
  Device-bound IPQ5018/QCN6122 board data and calibration extracted from
  the exact HW-D OEM firmware and ART partition. Do not install on another board.
  The QCN6122 board-2.bin is the OEM bdwlan.b60 with only byte 0x45c
  (antenna-axis gate) cleared and the checksum refixed, built by
  build_hwd_qcn6122_bdf.py; otherwise ath11k fw 2.7 asserts
  (phyrf_bdf.c:6245 ANTENNACHAIN_AXIS_Z). Do not use the Elecom-based hybrid:
  it is a no-FEM layout and caps 5G at 16 dBm on this 2xFEM board.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Compile
	cd $(CURDIR)/files && sha256sum -c SHA256SUMS
endef

define Package/hwd-nx30-oem-wifi/install
	cd $(CURDIR)/files && sha256sum -c SHA256SUMS
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/IPQ5018/hw1.0
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/qcn6122/hw1.0
	$(INSTALL_DATA) ./files/board-2-ipq5018.bin $(1)/lib/firmware/ath11k/IPQ5018/hw1.0/board-2.bin
	$(INSTALL_DATA) ./files/board-2-qcn6122.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin
	# Calibration comes from the running unit's own 0:ART, not this package.
	$(INSTALL_DIR) $(1)/lib/preinit
	$(INSTALL_DATA) ./files/05_hwd_caldata $(1)/lib/preinit/05_hwd_caldata
	$(LN) /tmp/hwd-cal/ipq5018.bin $(1)/lib/firmware/ath11k/IPQ5018/hw1.0/caldata.bin
	$(LN) /tmp/hwd-cal/qcn6122-1.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/caldata_1.bin
	$(LN) /tmp/hwd-cal/qcn6122-2.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/caldata_2.bin
endef

$(eval $(call BuildPackage,hwd-nx30-oem-wifi))
