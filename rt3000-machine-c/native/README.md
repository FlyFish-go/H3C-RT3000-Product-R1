# RT3000 C persistent-native profile

The persistent `h3c_rt3000_rtl8367s_native_slot1` profile selects the C factory-MAC resolver, its fail-closed base-files hooks, GPIO38 WPS input, and full `wpad-wolfssl`. It removes target-default `wpad-basic-wolfssl` and the competing `kmod-gpio-button-hotplug`; installer and RAM profiles retain their existing package selections.

The MAC helper requires exactly 21 parsed `/proc/mtd` rows with unique indices 0–20 and readable sysfs offset/size attributes for each row. It validates the exact `0:APPSBLENV` name, offset, size, selected-partition geometry, read-only flags and read-only character node before reading one 2048-byte page. It does **not** validate every physical partition range or independently prove raw-master absence; those protections belong to the separate kernel MTD guard and runtime checks. On any helper failure, native MAC hooks leave existing identity settings unchanged and do not fall back to the live `eth0` address.

The only key consumer added here is GPIO38 active-low `KEY_WPS_BUTTON`, with pull-up and 60 ms debounce. GPIO27 is not mapped as reset; no GPIO19/30 LEDs or GPIO38 long-press factory reset are configured. The reviewed OEM evidence establishes GPIO38 as WPS only. Physical key events, WPS enrollment, and LED behavior remain **NOT_EXECUTED**.
