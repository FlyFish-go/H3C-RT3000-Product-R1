#!/bin/sh
# RT3000 Machine-B deterministic per-role MAC derivation.
#
# ---------------------------------------------------------------------------
# Policy (frozen)
# ---------------------------------------------------------------------------
# The ONLY valid per-unit globally-administered factory identity on this device
# is the U-Boot environment variable `ethaddr` (read from the APPSBLENV
# partition).  Everything else in that environment is either a placeholder
# (`ethaddr1=00:11:22:33:44:56`) or OEM bookkeeping, and the ART partition holds
# generic Qualcomm placeholders.  Neither may be used as identity.
#
#   WAN    = factory ethaddr, UNCHANGED
#   LAN    = derived(factory, "rt3000/lan")
#   WiFi24 = derived(factory, "rt3000/wifi24")
#   WiFi5  = derived(factory, "rt3000/wifi5")
#
# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------
# derived = sha256( factory_bytes || role_domain )[0..2]  with the first octet
# forced to a valid locally-administered unicast value:
#
#     first = (first | 0x02) & 0xfe
#
#   | 0x02 -> set the locally-administered bit (no globally unique claim)
#   & 0xfe -> clear the multicast bit (must be a unicast address)
#
# Using a hash rather than arithmetic guarantees:
#   - different roles never collide with each other
#   - no role can collide with the WAN address by construction (WAN keeps the
#     factory value, and the derived first octet always has the local bit set
#     while a real factory OUI does not)
#   - the map is stable across reboots and factory resets: it depends only on
#     the factory MAC and a constant string, never on boot state or RNG
#
# Note the role domain strings are part of the wire format.  Changing one
# changes the derived MAC, so they are frozen here.

RT3000_ETHADDR_SOURCE=${RT3000_ETHADDR_SOURCE:-}
RT3000_ROLE_DOMAINS="lan wifi24 wifi5"

rt3000_mac_fail() {
	echo "rt3000-mac: $*" >&2
	return 1
}

# APPSBLENV partition holding the factory U-Boot environment.
#
# Machine-B layout: mtd10 "0:APPSBLENV", 0x80000 (512 KiB), erasesize 0x20000.
RT3000_APPSBLENV=${RT3000_APPSBLENV:-/dev/mtd10}
RT3000_APPSBLENV_SCAN=${RT3000_APPSBLENV_SCAN:-4096}

# Read the factory MAC from the U-Boot environment.
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

# sha256 of a byte string, hex.  Uses the first available tool.
rt3000_sha256() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum | cut -d' ' -f1
	elif command -v openssl >/dev/null 2>&1; then
		openssl dgst -sha256 | sed 's/.*= *//'
	else
		return 1
	fi
}

# rt3000_derive_mac <factory_mac> <role_domain>
rt3000_derive_mac() {
	local factory="$1" domain="$2" hex b0 b1 b2 o1

	# The domain string is part of the hashed input.  printf without a trailing
	# newline keeps the byte string exactly reproducible.
	hex=$(printf '%s%s' "$factory" "$domain" | rt3000_sha256) || return 1
	[ ${#hex} -ge 6 ] || return 1

	b0=$(printf '%s' "$hex" | cut -c1-2)
	b1=$(printf '%s' "$hex" | cut -c3-4)
	b2=$(printf '%s' "$hex" | cut -c5-6)

	# force locally-administered unicast on the first octet
	o1=$(printf '%02x' $(( (0x$b0 | 0x02) & 0xfe )))

	printf '%s:%s:%s' "$o1" "$b1" "$b2"
	# the remaining three octets come from a second slice of the hash
	local hex2
	hex2=$(printf '%s%s%s' "$factory" "$domain" "tail" | rt3000_sha256) || return 1
	printf ':%s:%s:%s\n' \
		"$(printf '%s' "$hex2" | cut -c1-2)" \
		"$(printf '%s' "$hex2" | cut -c3-4)" \
		"$(printf '%s' "$hex2" | cut -c5-6)"
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

	lan=$(rt3000_derive_mac "$factory" "rt3000/lan") || {
		rt3000_mac_fail "hash tool unavailable"; return 1; }
	wifi24=$(rt3000_derive_mac "$factory" "rt3000/wifi24") || return 1
	wifi5=$(rt3000_derive_mac "$factory" "rt3000/wifi5") || return 1

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
