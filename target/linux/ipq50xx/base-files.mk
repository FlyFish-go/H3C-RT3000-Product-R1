# Machine-C single-profile RAM and installer images: remove persistent ENV and
# upgrade service paths from temporary RAM roots.
#
# The target selector has no DEVICE_ prefix in a single-profile .config.
# Keep this filter disabled for multi-profile builds, where base-files is shared
# and cannot be safely filtered for one device here.
ifeq ($(CONFIG_TARGET_MULTI_PROFILE),)
ifneq ($(filter y,$(CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_ram) $(CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_installer_ram)),)
define Package/base-files/install-target
	rm -f \
		$(1)/etc/board.d/01_leds \
		$(1)/etc/hotplug.d/firmware/10-ath11k-board_id \
		$(1)/etc/hotplug.d/firmware/11-ath11k-caldata \
		$(1)/etc/init.d/done \
		$(1)/etc/init.d/uboot_env \
		$(1)/etc/rc.d/S95done \
		$(1)/etc/rc.d/S99uboot_env \
		$(1)/lib/preinit/80_mount_root \
		$(1)/sbin/firstboot \
		$(1)/etc/uci-defaults/zz-rt3000-luci-language \
		$(1)/etc/uci-defaults/zz-rt3000-package-mirror \
		$(1)/sbin/sysupgrade \
		$(1)/sbin/upgraded
	# The console-only C profile has no netifd. Wired RAM and installer profiles
	# keep their network map, MAC policy and safe LAN address when netifd is selected.
	if [ "$(CONFIG_PACKAGE_netifd)" != y ]; then \
		rm -f $(1)/etc/board.d/02_macaddr \
			$(1)/etc/board.d/02_network \
			$(1)/etc/uci-defaults/98-rt3000-lan-default \
			$(1)/etc/uci-defaults/99-rt3000-wifi \
			$(1)/etc/hotplug.d/ieee80211/20-rt3000-c-wifi; \
		rm -rf $(1)/lib/rt3000; \
	else \
		rm -rf $(1)/lib/rt3000/pin; \
	fi
	if [ "$(CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_installer_ram)" = y ]; then \
		install -d $(1)/etc/sysctl.d; \
		printf '%s\n' 'kernel.panic=0' > $(1)/etc/sysctl.d/99-c-installer-panic.conf; \
	fi
	rm -rf $(1)/lib/upgrade
endef
endif
endif

# HW-D: remove the Machine-B ENV service, B/C Wi-Fi hooks and the SSDK pin.
# The target build is isolated to the D profile; RAM FITs share this safe root.
ifneq ($(filter y,$(CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c_nx30_hw_d) $(CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c_nx30_hw_d_ram) $(CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c_nx30_hw_d_installer_ram)),)
define Package/base-files/install-target
	rm -f \
		$(1)/etc/init.d/uboot_env \
		$(1)/etc/rc.d/S99uboot_env \
		$(1)/etc/uci-defaults/99-rt3000-wifi \
		$(1)/etc/hotplug.d/ieee80211/20-rt3000-c-wifi \
		$(1)/lib/rt3000/pin/qca-ssdk.ko.b64
	rm -rf $(1)/lib/rt3000/pin
endef
endif
