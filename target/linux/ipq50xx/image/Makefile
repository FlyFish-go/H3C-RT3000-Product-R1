include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/image.mk

ifeq ($(SUBTARGET),arm)
  KERNEL_LOADADDR := 0x41208000
  DTS_CPPFLAGS-y += -D__ARM32__
else
  KERNEL_LOADADDR := 0x41080000
  DTS_CPPFLAGS-y += -D__AARCH64__
endif

DTS_CPPFLAGS-y += -D__IPQ_MEM_PROFILE_256_MB__
DTS_CPPFLAGS-$(CONFIG_ATH11K_MEM_PROFILE_256M) += -DCONFIG_ATH11K_MEM_PROFILE_256M

define Device/Default
  PROFILES := Default
  DEVICE_DTS_DIR := ../dts
  DEVICE_DTS = $$(SOC)-$(lastword $(subst _, ,$(1)))
  DTS_CPPFLAGS += $(DTS_CPPFLAGS-y)
  IMAGES := sysupgrade.tar
  IMAGE/sysupgrade.tar := sysupgrade-tar | append-metadata
endef

define Device/FitImage
  KERNEL_SUFFIX := -fit-uImage.itb
  KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-$$(DEVICE_DTS).dtb
  KERNEL_NAME := Image
endef

define Device/UbiFit
  KERNEL_IN_UBI := 1
  IMAGES := nand-factory.ubi release.json
  IMAGE/release.json := rt3000-release-manifest nand-sysupgrade.bin
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/nand-sysupgrade.bin := sysupgrade-tar | append-metadata
endef

define Device/cmcc_rax3000q
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  DEVICE_VENDOR := CMCC
  DEVICE_MODEL := RAX3000Q
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp02.1
  IMAGES := nand-factory.ubi release.json
  IMAGE/release.json := rt3000-release-manifest
  DEVICE_PACKAGES := \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	ipq-wifi-cmcc_rax3000q
endef
TARGET_DEVICES += cmcc_rax3000q

define Device/redmi_ax3000
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  DEVICE_VENDOR := Redmi
  DEVICE_MODEL := AX3000
  DEVICE_ALT0_VENDOR := Xiaomi
  DEVICE_ALT0_MODEL := CR880x
  DEVICE_ALT0_VARIANT := (M81 version)
  DEVICE_ALT1_VENDOR := Xiaomi
  DEVICE_ALT1_MODEL := CR880x
  DEVICE_ALT1_VARIANT := (M79 version)
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp02.1
  IMAGES := nand-factory.ubi release.json
  IMAGE/release.json := rt3000-release-manifest
  DEVICE_PACKAGES := \
	ATH11K_MEM_PROFILE_256M \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	ipq-wifi-redmi_ax3000
endef
TARGET_DEVICES += redmi_ax3000

define Device/xiaomi_cr881x
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5018
  DEVICE_VENDOR := Xiaomi
  DEVICE_MODEL := CR881x
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp03.3
  IMAGES := nand-factory.ubi release.json
  IMAGE/release.json := rt3000-release-manifest
  DEVICE_PACKAGES := \
	ATH11K_MEM_PROFILE_256M \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	ipq-wifi-xiaomi_cr881x
endef
TARGET_DEVICES += xiaomi_cr881x

define Device/h3c_rt3000
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  UBI_ROOTFS_NAME := ubi_rootfs
  UBI_IMAGE_SEQ := 815647064
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp02.1
  # G11-P4.6: WiFi bring-up PASSed; factory image enabled but FLASHING
  # REMAINS GATED on explicit human confirmation (SAFE_TO_FLASH=NO).
  IMAGES := nand-factory.ubi release.json
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/release.json := rt3000-release-manifest
  DEVICE_PACKAGES := \
	ATH11K_MEM_PROFILE_256M \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	ipq-wifi-h3c_rt3000 \
	kmod-qca-nss-ecm-standard \
	iperf3 \
	rt3bcwrite \
	rt3slot \
	rt3release
endef
TARGET_DEVICES += h3c_rt3000

# ---------------------------------------------------------------------------
# Product R1 release identity manifest (RB002).
#
# Emitted beside the finished images from the ACTUAL kernel and rootfs payloads.
# It cannot ship inside the rootfs because it records the rootfs' own hash;
# embedding that would be circular.  rt3release verifies the running kernel
# payload against it, and `rt3release verify-rootfs <payload>` verifies the
# rootfs payload -- the check the installer and hardware acceptance use.
#
# Identity is stable content only.  No UBI image_seq, EC counter, VID header or
# PEB placement participates.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Product R1 RC1 qca-ssdk binary pinning.
#
# Runs on the assembled rootfs, which is the only stage after every strip and
# module-copy step has finished.  qca-ssdk.ko embeds __DATE__/__TIME__, so a
# rebuild of identical source yields a different hash; RC1 pins the module to
# the byte-exact binary that was hardware-accepted with the R1-NET-D network
# baseline.  This is release binary pinning, not a source change: qca-ssdk
# source, patches and build flags are all untouched.
#
# The pinned payload is carried as base64 under lib/rt3000/pin so that no vendor
# binary enters Git; pin.sh verifies the hash and aborts on any mismatch.
# ---------------------------------------------------------------------------


define Build/rt3000-release-manifest
	$(TOPDIR)/scripts/rt3000-mkmanifest.sh \
		$(IMAGE_KERNEL) $(IMAGE_ROOTFS) $(@D)/$(DEVICE_NAME)-release.json \
		"Product R1 RC1" "R1-NET-D"
endef

$(eval $(call BuildImage))
