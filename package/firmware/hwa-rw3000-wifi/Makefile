include $(TOPDIR)/rules.mk

PKG_NAME:=hwa-rw3000-wifi
PKG_VERSION:=20261023
PKG_RELEASE:=3
PKG_LICENSE:=Proprietary
PKG_FLAGS:=nonshared
PKG_FILE_DEPENDS:=./files/

include $(INCLUDE_DIR)/package.mk

# HW-A and the legacy RT3000 package install the same ath11k board-2.bin
# paths. Refuse a mixed profile before rootfs package installation can choose
# one file by package ordering.
ifeq ($(CONFIG_PACKAGE_hwa-rw3000-wifi),y)
ifneq ($(filter y m,$(CONFIG_PACKAGE_ipq-wifi-h3c_rt3000)),)
$(error hwa-rw3000-wifi cannot be combined with ipq-wifi-h3c_rt3000)
endif
endif

define Package/hwa-rw3000-wifi
  SECTION:=firmware
  CATEGORY:=Firmware
  TITLE:=RW3000 HW-A BDFs (QCN6122 OEM b90, axis gate cleared) and switch
  DEPENDS:=@TARGET_ipq50xx_arm +ath11k-firmware-ipq5018 +ath11k-firmware-qcn6122
endef

define Package/hwa-rw3000-wifi/description
  HW-A has no 5 GHz FEM and OEM board ID 0x90. The QCN6122 default is the
  OEM bdwlan.b90 with only byte 0x45c cleared and the checksum refixed
  (build_hwa_qcn6122_bdf.py), as on HW-C/D. Compared with HW-B's hybrid on
  build02 it gives the same peak rates and a 23 dBm limit instead of 16/19
  dBm (ch36/ch149), +7 dB beacon RSSI. The IPQ5018 BDF is A's own OEM
  bdwlan.b23 (IPQ5018, same file as HW-C), not HW-B's IPQ5000 b23: 25 vs 20
  dBm limit, +3-4 dB beacon, same rates.
  `hwa-bdf oem-axis0|hybrid|status` switches; the hybrid stays installed.
  Calibration is taken from the unit's 0:ART by 11-ath11k-caldata.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Compile
	cd $(CURDIR)/files && sha256sum -c SHA256SUMS
endef

define Package/hwa-rw3000-wifi/install
	cd $(CURDIR)/files && sha256sum -c SHA256SUMS
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/IPQ5018/hw1.0
	$(INSTALL_DIR) $(1)/lib/firmware/ath11k/qcn6122/hw1.0 $(1)/usr/sbin
	$(INSTALL_DATA) ./files/board-2-ipq5018.bin $(1)/lib/firmware/ath11k/IPQ5018/hw1.0/board-2.bin
	$(INSTALL_DATA) ./files/board-2-qcn6122-b90-axis0.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin
	$(INSTALL_DATA) ./files/board-2-qcn6122-b90-axis0.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin.b90-axis0
	$(INSTALL_DATA) ./files/board-2-qcn6122-hybrid.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin.hybrid
	$(INSTALL_BIN) ./files/hwa-bdf $(1)/usr/sbin/hwa-bdf
endef

$(eval $(call BuildPackage,hwa-rw3000-wifi))
