include $(TOPDIR)/rules.mk

BOARD:=ipq50xx
BOARDNAME:=Qualcomm Atheros IPQ50XX
SUBTARGETS:=arm aarch64

CPU_TYPE:=cortex-a53
FEATURES:=fpu ramdisk nand squashfs pcie

KERNEL_PATCHVER:=5.4
LINUX_VERSION-5.4:=-qsdk-11.5.0.5

CONFIG_KERNEL_GIT_CLONE_URI:=https://git.codelinaro.org/clo/qsdk/oss/kernel/linux-ipq-5.4
CONFIG_KERNEL_GIT_REF:=d5fcb18e5420670c8734c6a659873e73adab6dac

include $(INCLUDE_DIR)/target.mk

define Kernel/Prepare/Default
	$(LINUX_CAT) $(DL_DIR)/$(LINUX_SOURCE) | $(TAR) -C $(KERNEL_BUILD_DIR) $(TAR_OPTIONS)
	$(Kernel/Patch)
	$(if $(QUILT),touch $(LINUX_DIR)/.quilt_used)
endef

KERNELNAME:=Image dtbs

DEFAULT_PACKAGES += \
	kmod-gpio-button-hotplug \
	uboot-envtools \
	kmod-qca-nss-dp swconfig \
	kmod-qca-nss-drv qca-nss-fw-ipq50xx-retail \
	kmod-ath11k wpad-basic-wolfssl \
	ath11k-firmware-ipq5018 ath11k-firmware-qcn6122

# Machine-C first-stage console RAM profile does not bring up networking or
# board services. Filter both generic router defaults and ipq50xx extras only
# for this explicitly selected, single-profile build.
C_RAM_ONLY_SINGLE_PROFILE := $(shell test -f $(TOPDIR)/.config && grep -q '^CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_ram=y' $(TOPDIR)/.config && ! grep -q '^CONFIG_TARGET_MULTI_PROFILE=y' $(TOPDIR)/.config && echo 1)
ifeq ($(C_RAM_ONLY_SINGLE_PROFILE),1)
DEFAULT_PACKAGES := $(filter-out \
	ca-bundle dropbear libustream-wolfssl mtd netifd opkg uclient-fetch \
	dnsmasq firewall ip6tables iptables kmod-ipt-offload odhcp6c \
	odhcpd-ipv6only ppp ppp-mod-pppoe \
	kmod-gpio-button-hotplug uboot-envtools kmod-qca-nss-dp swconfig \
	kmod-qca-nss-drv qca-nss-fw-ipq50xx-retail kmod-ath11k \
	wpad-basic-wolfssl ath11k-firmware-ipq5018 ath11k-firmware-qcn6122, \
	$(DEFAULT_PACKAGES))
endif

$(eval $(call BuildTarget))
