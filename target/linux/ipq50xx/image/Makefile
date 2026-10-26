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

# Packages every public H3C QSDK image (HW-A/B/C/D) ships; each device adds
# only its own board data and hardware packages.
H3C_QSDK_PACKAGES := \
	ATH11K_MEM_PROFILE_256M \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	kmod-qca-nss-ecm-standard \
	iperf3 \
	luci \
	luci-i18n-base-zh-cn \
	luci-i18n-firewall-zh-cn \
	luci-i18n-opkg-zh-cn \
	ttyd \
	luci-app-ttyd \
	luci-i18n-ttyd-zh-cn

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

# Exact same-device HW-D profile. RAM targets share the OEM-compatible FIT
# contract, keep U-Boot untouched, and expose no factory/sysupgrade entry.
define Device/h3c_nx30_hw_d
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  DEVICE_DTS := ipq5000-nx30-hw-d ipq5000-nx30-hw-d-initramfs ipq5000-nx30-hw-d-installer-initramfs
  KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-nx30-hw-d.dtb
  KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-nx30-hw-d-initramfs.dtb
  UBI_ROOTFS_NAME := ubi_rootfs
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic NX30 HW-D EF:BA:21
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp02.1
  SUPPORTED_DEVICES := h3c,nx30-hw-d
  IMAGES := nand-factory.ubi sysupgrade.bin
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := $(H3C_QSDK_PACKAGES) hwd-nx30-oem-wifi hwd-factory-mac
endef
TARGET_DEVICES += h3c_nx30_hw_d

define Device/h3c_nx30_hw_d_ram
  $(call Device/FitImage)
  SOC := ipq5000
  DEVICE_DTS := ipq5000-nx30-hw-d-initramfs
  KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-nx30-hw-d-initramfs.dtb
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic NX30 HW-D (RAM validation)
  DEVICE_DTS_CONFIG := config@mp02.1
  SUPPORTED_DEVICES := h3c,nx30-hw-d
  DEVICE_PACKAGES := ATH11K_MEM_PROFILE_256M hwd-mtd-guard
  IMAGES :=
endef
TARGET_DEVICES += h3c_nx30_hw_d_ram

define Device/h3c_nx30_hw_d_installer_ram
  $(call Device/FitImage)
  SOC := ipq5000
  DEVICE_DTS := ipq5000-nx30-hw-d-installer-initramfs
  KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-nx30-hw-d-installer-initramfs.dtb
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic NX30 HW-D (installer RAM)
  DEVICE_DTS_CONFIG := config@mp02.1
  SUPPORTED_DEVICES := h3c,nx30-hw-d
  DEVICE_PACKAGES := ATH11K_MEM_PROFILE_256M rt3bcwrite hwd-mtd-guard nand-utils
  IMAGES :=
endef
TARGET_DEVICES += h3c_nx30_hw_d_installer_ram

define Device/h3c_rt3000
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  # Build both DTBs, and select exactly one for each FIT payload.
  DEVICE_DTS := ipq5000-rt3000 ipq5000-rt3000-initramfs
  KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-rt3000.dtb
  KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-rt3000-initramfs.dtb
  UBI_ROOTFS_NAME := ubi_rootfs
  UBI_IMAGE_SEQ := 815647064
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp02.1
  # QSDK lives in the high slot "rootfs" (mtd16); the OEM low slot stays
  # read-only and the default slot is chosen in U-Boot (bootconfig). First
  # install is factory.ubi; updates use sysupgrade.bin (lib/upgrade/rt3000-b.sh).
  SUPPORTED_DEVICES := h3c,rt3000
  IMAGES := nand-factory.ubi sysupgrade.bin
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := $(H3C_QSDK_PACKAGES) ipq-wifi-h3c_rt3000 kmod-leds-gpio
endef
TARGET_DEVICES += h3c_rt3000

# RW3000 HW-A: HW-B's board recipe with A's GPIOs and slot order. QSDK lives
# in the low slot, the OEM system stays read-only in the high slot, and this
# profile never touches BOOTCONFIG. First install is factory.ubi; later
# updates use sysupgrade.bin (lib/upgrade/rw3000-hw-a.sh, mtd15 only).
define Device/h3c_rw3000_hw_a
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5018
  DEVICE_DTS := ipq5018-rw3000-hw-a ipq5018-rw3000-hw-a-initramfs
  KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5018-rw3000-hw-a.dtb
  KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5018-rw3000-hw-a-initramfs.dtb
  UBI_ROOTFS_NAME := ubi_rootfs
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := RW3000 HW-A
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  DEVICE_DTS_CONFIG := config@mp03.1
  SUPPORTED_DEVICES := h3c,rw3000-hw-a
  IMAGES := nand-factory.ubi sysupgrade.bin
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := $(H3C_QSDK_PACKAGES) hwa-rw3000-wifi kmod-leds-gpio
endef
TARGET_DEVICES += h3c_rw3000_hw_a

# Machine-C first-stage RAM/initramfs image only. Keep this target isolated
# from Machine-B's board identity and persistent UBI/sysupgrade/release paths.
define Device/h3c_rt3000_rtl8367s_ram
  $(call Device/FitImage)
  SOC := ipq5000
  DEVICE_DTS := ipq5000-rt3000-rtl8367s
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000 RTL8367S C2 (RAM bring-up)
  DEVICE_DTS_CONFIG := config@mp03.1-c2
  SUPPORTED_DEVICES := h3c,rt3000-rtl8367s
  DEVICE_PACKAGES := \
	kmod-qca-nss-dp \
	ATH11K_MEM_PROFILE_256M \
	kmod-ath11k \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	rt3000-c-oem-wifi \
	wpad-basic-wolfssl
  # Device/Init's KERNEL_INITRAMFS inherits KERNEL; export only that artifact.
  # An empty IMAGES list prevents factory UBI, sysupgrade and release manifests.
  IMAGES :=
endef
TARGET_DEVICES += h3c_rt3000_rtl8367s_ram

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
		$(IMAGE_KERNEL) $(IMAGE_ROOTFS) $@ \
		"Product R1 RC1" "R1-NET-D"
	cp $@ $(@D)/$(DEVICE_NAME)-release.json
endef

# C-only read-only MTD discovery RAM profile. No installer or persistent image.
define Device/h3c_rt3000_rtl8367s_mtd_discovery_ram
  $(call Device/FitImage)
  SOC := ipq5000
  DEVICE_DTS := ipq5000-rt3000-rtl8367s-mtd-discovery
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000 RTL8367S C2 (MTD read-only discovery)
  DEVICE_DTS_CONFIG := config@mp03.1-c2-mtd-discovery
  SUPPORTED_DEVICES := h3c,rt3000-rtl8367s-mtd-discovery
  DEVICE_PACKAGES :=
  IMAGES :=
endef
TARGET_DEVICES += h3c_rt3000_rtl8367s_mtd_discovery_ram

# C persistent slot-1 profile. The isolated native builder packages KDIR/Image,
# this FDT, and the exact SquashFS input below into the reviewed FIT and UBI.
# This profile must resolve CONFIG_TARGET_ROOTFS_INITRAMFS=n.
define Device/h3c_rt3000_rtl8367s_native_slot1
  $(call Device/FitImage)
  $(call Device/UbiFit)
  SOC := ipq5000
  DEVICE_DTS_DIR := $(TOPDIR)/rt3000-machine-c/native
  DEVICE_DTS := ipq5000-rt3000-rtl8367s-persistent
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000 RTL8367S C native slot 1
  DEVICE_DTS_CONFIG := config@mp03.1-c2
  UBI_ROOTFS_NAME := ubi_rootfs
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  # QSDK in rootfs_1 (mtd16) with the standard kernel/ubi_rootfs/rootfs_data
  # volumes, like HW-A/B/D; the OEM slot stays read-only.
  SUPPORTED_DEVICES := h3c,rt3000-rtl8367s
  DEVICE_PACKAGES := $(H3C_QSDK_PACKAGES) \
	kmod-qca-nss-dp \
	kmod-qca-nss-drv \
	kmod-qca-nss-drv-wifi-meshmgr \
	kmod-qca-nss-ecm-standard \
	qca-nss-fw-ipq50xx-retail \
	kmod-leds-rt3000-paired \
	kmod-rtl8367s-expander \
	swconfig \
	kmod-ath11k \
	rt3000-c-oem-wifi \
	rt3000-c-mac-identity-ro \
	kmod-input-core \
	kmod-input-gpio-keys \
	kmod-button-hotplug \
	wpad-wolfssl \
	-kmod-gpio-button-hotplug \
	-wpad-basic-wolfssl \
	fstools \
	ubi-utils \
	dropbear
  IMAGES := nand-factory.ubi sysupgrade.bin
  IMAGE/nand-factory.ubi := append-ubi
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
endef
TARGET_DEVICES += h3c_rt3000_rtl8367s_native_slot1

# C installer/rescue RAM profile. It deliberately uses OpenWrt's Image-initramfs
# path; its FDT supplies init=/init and network transfer/backup facilities.
define Device/h3c_rt3000_rtl8367s_installer_ram
  $(call Device/FitImage)
  SOC := ipq5000
  DEVICE_DTS_DIR := $(TOPDIR)/rt3000-machine-c/native
  DEVICE_DTS := ipq5000-rt3000-rtl8367s-installer
  DEVICE_VENDOR := H3C
  DEVICE_MODEL := Magic RT3000 RTL8367S C installer RAM
  DEVICE_DTS_CONFIG := config@mp03.1-c2
  SUPPORTED_DEVICES := h3c,rt3000-rtl8367s
  DEVICE_PACKAGES := \
	kmod-qca-nss-dp \
	ATH11K_MEM_PROFILE_256M \
	ATH11K_RT3000_MON_OWNER_DIAG \
	ATH11K_RT3000_REO_IDR_CLAIM \
	ATH11K_RT3000_TX_UNKNOWN_DIAG \
	kmod-ath11k \
	ath11k-firmware-ipq5018 \
	ath11k-firmware-qcn6122 \
	rt3000-c-oem-wifi \
	wpad-basic-wolfssl \
	netifd \
	mtd \
	fstools \
	ubi-utils
  IMAGES :=
endef
TARGET_DEVICES += h3c_rt3000_rtl8367s_installer_ram

$(eval $(call BuildImage))
