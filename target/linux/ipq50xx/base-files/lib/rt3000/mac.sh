#!/bin/sh
# RT3000 deterministic per-role MAC derivation shared by B and C.
#
# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
# The caller supplies the per-unit WAN/factory identity. Machine-B normally
# reads U-Boot `ethaddr` from APPSBLENV. Machine-C's RAM-only first-boot path
# uses the live OEM WAN `eth0` address passed through by U-Boot because that
# candidate has no MTD devices. Neither machine uses `ethaddr1` or ART
# placeholders as identity.
#
#   WAN    = factory ethaddr, UNCHANGED
#   LAN    = factory + 1
#   WiFi24 = factory + 2
#   WiFi5  = factory + 3
#
# This is the OEM numbering observed on HW-C (OEM LAN = WAN+1) and HW-D
# (WAN/LAN/radios = base..base+3, see hwd-factory-mac), so every H3C board
# uses the same consecutive, globally administered block. The addition is
# over all 48 bits, matching hwd-factory-mac.

RT3000_ETHADDR_SOURCE=${RT3000_ETHADDR_SOURCE:-}

rt3000_mac_fail() {
	echo "rt3000-mac: $*" >&2
	return 1
}

# APPSBLENV partition holding the factory U-Boot environment.
#
# Machine-B layout: mtd10 "0:APPSBLENV", 0x80000 (512 KiB), erasesize 0x20000.
RT3000_APPSBLENV=${RT3000_APPSBLENV:-/dev/mtd10}
RT3000_APPSBLENV_SCAN=${RT3000_APPSBLENV_SCAN:-4096}

# Read the WAN/factory MAC supplied by the caller, then fall back to the
# Machine-B U-Boot environment when no override is present.
#
# Order of preference:
#   1. RT3000_ETHADDR_SOURCE  (test hook / explicit override)
#   2. fw_printenv ethaddr    (works only if the environment CRC is one the
#                              fw_env tools accept -- see below)
#   3. raw scan of the APPSBLENV partition
#
# Preference 3 exists because the OEM environment on this device does NOT carry a
# U-Boot CRC32 that fw_printenv accepts.  Measured read-only on hardware
# (2026-09-19): APPSBLENV starts with the 4-byte value 0xa2dd811a followed by
# "baudrate=115200\0", is a single-copy (non-redundant) environment at offset 0,
# and NONE of the plausible config geometries
# (/dev/mtd10 0x0 <envsize> [0x20000] for envsize 0x2000..0x10000) passes the CRC
# check -- fw_printenv always reports "Bad CRC, using default environment" and
# returns no variables.  A CRC sweep over every (start,length) window also failed
# to reproduce the stored value, so the format is genuinely non-standard.
#
# Shipping /etc/fw_env.config alone therefore does NOT fix the MAC source; the raw
# read is what actually works.  It is a plain string scan of a read-only MTD
# partition, needs no helper binary, and is what the bootloader itself consumes.
rt3000_factory_mac_raw() {
	local mac=""

	[ -r "$RT3000_APPSBLENV" ] || return 1

	# "ethaddr=" must not match "ethaddr1=", so anchor on the NUL-delimited
	# variable boundary and require the value to end at a NUL or newline.
	mac=$(dd if="$RT3000_APPSBLENV" bs=1 count="$RT3000_APPSBLENV_SCAN" 2>/dev/null \
		| tr '\000' '\n' \
		| sed -n 's/^ethaddr=\(.*\)$/\1/p' \
		| head -n1)

	[ -n "$mac" ] || return 1
	printf '%s' "$mac"
}

rt3000_factory_mac() {
	local mac=""

	if [ -n "$RT3000_ETHADDR_SOURCE" ]; then
		if [ -r "$RT3000_ETHADDR_SOURCE" ]; then
			mac=$(sed -n 's/^ethaddr=//p' "$RT3000_ETHADDR_SOURCE" 2>/dev/null | head -n1)
		else
			mac="$RT3000_ETHADDR_SOURCE"
		fi
	fi

	if [ -z "$mac" ] && command -v fw_printenv >/dev/null 2>&1; then
		mac=$(fw_printenv -n ethaddr 2>/dev/null)
	fi

	# Fall through to the partition when fw_printenv is absent or, as on this
	# device, present but unable to authenticate the OEM environment.
	if [ -z "$mac" ]; then
		mac=$(rt3000_factory_mac_raw 2>/dev/null)
	fi

	printf '%s' "$mac"
}

# Validate: exactly 6 hex octets, unicast, not all-zero, not a known placeholder.
rt3000_mac_valid() {
	local mac="$1" o1

	case "$mac" in
		[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:\
[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]) ;;
		*) return 1 ;;
	esac

	# reject the all-zero address
	[ "$mac" = "00:00:00:00:00:00" ] && return 1

	# reject the known placeholder present in this device's U-Boot env
	case "$(printf '%s' "$mac" | tr 'A-F' 'a-f')" in
		00:11:22:33:44:56) return 1 ;;
	esac

	# must be unicast: the multicast bit of the first octet must be clear
	o1=$(printf '%s' "$mac" | cut -d: -f1)
	[ $(( 0x$o1 & 0x01 )) -eq 0 ] || return 1

	return 0
}

# rt3000_mac_add <mac> <n>: <mac> + <n> over all 48 bits, lower-case.
rt3000_mac_add() {
	local hex n

	hex=$(printf '%s' "$1" | tr -d ':')
	n=$(( 0x$hex + $2 ))
	[ "$n" -le $(( 0xffffffffffff )) ] || return 1
	printf '%012x' "$n" | sed 's/../&:/g; s/:$//'
}

# Emit "<role> <mac>" lines for all roles.  Exits nonzero and prints a clear
# diagnostic when the factory MAC is unusable: the caller must then leave MAC
# handling to the kernel default rather than inventing an identity.
rt3000_mac_map() {
	local factory lan wifi24 wifi5

	factory=$(rt3000_factory_mac)

	if [ -z "$factory" ]; then
		rt3000_mac_fail "factory ethaddr not found; refusing to invent identity"
		return 1
	fi
	if ! rt3000_mac_valid "$factory"; then
		rt3000_mac_fail "factory ethaddr '$factory' is invalid or a placeholder; refusing to derive"
		return 1
	fi

	lan=$(rt3000_mac_add "$factory" 1) || return 1
	wifi24=$(rt3000_mac_add "$factory" 2) || return 1
	wifi5=$(rt3000_mac_add "$factory" 3) || return 1

	printf 'wan %s\n' "$factory"
	printf 'lan %s\n' "$lan"
	printf 'wifi24 %s\n' "$wifi24"
	printf 'wifi5 %s\n' "$wifi5"
	return 0
}

# Only run the CLI when executed directly, so the functions above stay
# sourceable from the board.d hook and from the test suite.
case "$0" in
	*rt3000-mac.sh) rt3000_mac_map ;;
esac
