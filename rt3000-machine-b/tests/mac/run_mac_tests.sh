#!/bin/sh
# RT3000 Machine-B — deterministic MAC policy test suite.
#
# Runs entirely offline against the shipped derivation script; no device, no
# network.  Set RT3000_ETHADDR_SOURCE to inject a factory value.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$HERE/rt3000-mac.sh"
PASS=0; FAIL=0; FAILED=""

ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED="$FAILED
  $1"; printf 'FAIL  %s   -- %s\n' "$1" "${2:-}"; }

# run with an injected factory MAC
run_mac() { RT3000_ETHADDR_SOURCE="$1" sh "$SCRIPT" 2>&1; }

# field <role> <output>
field() { printf '%s\n' "$2" | sed -n "s/^$1 //p" | head -n1; }

echo "=== RT3000 deterministic MAC policy test suite ==="
echo "script: $SCRIPT"
echo

FACTORY="00:11:22:33:44:55"

##############################################################################
echo "--- group A: determinism and stability ---"
##############################################################################

OUT1=$(run_mac "$FACTORY")
OUT2=$(run_mac "$FACTORY")
if [ "$OUT1" = "$OUT2" ] && [ -n "$OUT1" ]; then
	ok "same factory MAC -> identical output across invocations"
else
	bad "determinism" "outputs differ"
fi

# repeat 5x to catch any hidden nondeterminism
same=1
i=0
while [ $i -lt 5 ]; do
	[ "$(run_mac "$FACTORY")" = "$OUT1" ] || same=0
	i=$((i+1))
done
[ $same -eq 1 ] && ok "stable across 5 repeated runs" || bad "stability" "varied output"

# different factory MACs must give different derived sets
OTHER="00:11:22:33:44:99"
OUT_OTHER=$(run_mac "$OTHER")
if [ "$(field lan "$OUT1")" != "$(field lan "$OUT_OTHER")" ]; then
	ok "different factory MAC -> different LAN MAC"
else
	bad "factory sensitivity" "same derived MAC for different factory"
fi

##############################################################################
echo
echo "--- group B: per-role properties ---"
##############################################################################

LAN=$(field lan "$OUT1")
W24=$(field wifi24 "$OUT1")
W5=$(field wifi5 "$OUT1")
WAN=$(field wan "$OUT1")

# roles unique
if [ "$LAN" != "$W24" ] && [ "$LAN" != "$W5" ] && [ "$W24" != "$W5" ]; then
	ok "three roles produce three distinct MACs"
else
	bad "role uniqueness" "lan=$LAN wifi24=$W24 wifi5=$W5"
fi

# locally administered + unicast
check_local_unicast() {
	local name="$1" mac="$2" o1
	case "$mac" in
		[0-9a-fA-F][0-9a-fA-F]:*) ;;
		*) bad "$name locally administered" "malformed '$mac'"; return ;;
	esac
	o1=$(printf '%s' "$mac" | cut -d: -f1)
	[ $(( 0x$o1 & 0x02 )) -ne 0 ] && ok "$name locally administered (first=0x$o1)" \
		|| bad "$name locally administered" "first=0x$o1"
	[ $(( 0x$o1 & 0x01 )) -eq 0 ] && ok "$name unicast" \
		|| bad "$name unicast" "multicast bit set (first=0x$o1)"
}
check_local_unicast lan "$LAN"
check_local_unicast wifi24 "$W24"
check_local_unicast wifi5 "$W5"

# WAN preserved exactly
if [ "$WAN" = "$FACTORY" ]; then
	ok "WAN keeps the factory MAC unchanged"
else
	bad "WAN preservation" "wan=$WAN factory=$FACTORY"
fi

# no derived MAC collides with WAN
if [ "$LAN" != "$WAN" ] && [ "$W24" != "$WAN" ] && [ "$W5" != "$WAN" ]; then
	ok "no derived role collides with WAN"
else
	bad "WAN collision" "a role equals the WAN MAC"
fi

# no multicast anywhere
mc=0
for m in "$WAN" "$LAN" "$W24" "$W5"; do
	o1=$(printf '%s' "$m" | cut -d: -f1)
	[ $(( 0x$o1 & 0x01 )) -ne 0 ] && mc=1
done
[ $mc -eq 0 ] && ok "no multicast address in any role" || bad "multicast" "one role is multicast"

# not simple arithmetic increments of the factory MAC
FLAST=$(printf '%s' "$FACTORY" | cut -d: -f6)
LLASt=$(printf '%s' "$LAN" | cut -d: -f6)
if [ "$LLASt" != "$(printf '%02X' $(( 0x$FLAST + 1 )) )" ]; then
	ok "derivation is not a simple +1 of the factory MAC"
else
	bad "arithmetic derivation" "LAN looks like factory+1"
fi

# derived addressing is independent of the factory OUI (local bit set)
F1=$(printf '%s' "$FACTORY" | cut -d: -f1)
L1=$(printf '%s' "$LAN" | cut -d: -f1)
if [ $(( 0x$L1 & 0x02 )) -ne 0 ] && [ $(( 0x$F1 & 0x02 )) -eq 0 ]; then
	ok "derived MACs are in the locally-administered space, factory is not"
else
	bad "admin space" "factory first=0x$F1 lan first=0x$L1"
fi

##############################################################################
echo
echo "--- group C: fail-safe on invalid factory identity ---"
##############################################################################

failsafe() {
	local name="$1" val="$2" out rc
	out=$(run_mac "$val"); rc=$?
	if [ $rc -ne 0 ] && [ -z "$(field lan "$out")" ]; then
		ok "$name -> refuses and derives nothing"
	else
		bad "$name fail-safe" "rc=$rc out=$(printf '%s' "$out" | tr '\n' '|')"
	fi
}

failsafe "empty ethaddr"            ""
failsafe "all-zero ethaddr"         "00:00:00:00:00:00"
failsafe "placeholder ethaddr1"     "00:11:22:33:44:56"
failsafe "malformed (too short)"    "00:11:22"
failsafe "malformed (non-hex)"      "ZZ:11:22:33:44:55"
failsafe "malformed (extra octet)"  "00:11:22:33:44:55:99"
failsafe "multicast factory MAC"    "01:11:22:33:44:55"

# the placeholder must be rejected even though it is syntactically valid
OUT=$(run_mac "00:11:22:33:44:56" 2>&1)
case "$OUT" in
	*placeholder*) ok "placeholder rejection is explained to the operator" ;;
	*) bad "placeholder diagnostic" "no explanation: $OUT" ;;
esac

# a missing value must not silently produce a random identity
OUTA=$(run_mac "" 2>&1); OUTB=$(run_mac "" 2>&1)
if [ "$OUTA" = "$OUTB" ] && [ -z "$(field lan "$OUTA")" ]; then
	ok "missing ethaddr never yields an invented or random identity"
else
	bad "no invented identity" "$OUTA / $OUTB"
fi

##############################################################################
echo
echo "--- group D: explicit role-domain definition ---"
##############################################################################

if grep -q 'rt3000/lan' "$SCRIPT" && grep -q 'rt3000/wifi24' "$SCRIPT" && \
   grep -q 'rt3000/wifi5' "$SCRIPT"; then
	ok "role-domain strings are explicit in the implementation"
else
	bad "role domains" "expected rt3000/lan, rt3000/wifi24, rt3000/wifi5"
fi

# domains must be distinct constants (a typo collapsing two roles would show up
# as identical derived MACs, already covered above)
nd=$(grep -c 'rt3000/' "$SCRIPT")
[ "$nd" -ge 3 ] && ok "each role has its own domain string" || bad "domain count" "found $nd"

##############################################################################
echo
echo "--- group E: production factory-MAC source path (RC1-HW-001 regression) ---"
##############################################################################
# RC1-HW-001: the algorithm tests above all pass a synthetic factory MAC through
# RT3000_ETHADDR_SOURCE, so they could not catch the production source path being
# broken.  On the shipped RC1 image /etc/fw_env.config was absent AND the OEM
# environment CRC is not one fw_printenv accepts, so rt3000_factory_mac() returned
# empty, the policy failed closed, and LAN/WiFi fell back to unstable defaults.
# These tests exercise the REAL production path instead.

# E1: the implementation must not depend only on the test hook.  There must be a
# non-hook source that reads the partition directly.
if grep -q 'rt3000_factory_mac_raw' "$SCRIPT"; then
	ok "production path has a non-hook factory-MAC source"
else
	bad "production source path" "rt3000_factory_mac_raw missing; only the test hook exists"
fi

# E2: with NO test hook set and fw_printenv absent, the raw partition read must
# still resolve the factory MAC from a synthetic APPSBLENV image.
E_TMP=$(mktemp -d)
RAWENV="$E_TMP/appsblenv.bin"
python3 - "$RAWENV" <<'PYE'
import sys
blob = b'\xa2\xdd\x81\x1a'
blob += b'baudrate=115200\x00bootcmd=bootipq\x00'
blob += b'ethaddr1=00:11:22:33:44:56\x00'
blob += b'ethaddr=00:11:22:33:44:55\x00'
blob += b'manucode=219801A2W3P226000YZ8\x00'
blob += b'\x00' * 4096
open(sys.argv[1], 'wb').write(blob)
PYE

GOT=$(env -u RT3000_ETHADDR_SOURCE RT3000_APPSBLENV="$RAWENV" \
	PATH=/usr/bin:/bin sh -c '. "'"$SCRIPT"'"; rt3000_factory_mac' 2>/dev/null)

if [ "$GOT" = "00:11:22:33:44:55" ]; then
	ok "raw partition read resolves the factory ethaddr without the test hook"
else
	bad "raw partition read" "expected 00:11:22:33:44:55, got '$GOT'"
fi

# E3: the placeholder ethaddr1 must never be chosen in preference to ethaddr
GOT1=$(printf '%s' "$GOT")
case "$GOT1" in
	00:11:22:33:44:56) bad "placeholder precedence" "selected the ethaddr1 placeholder" ;;
	00:11:22:33:44:55) ok "ethaddr1 placeholder is not selected over ethaddr" ;;
	*) bad "placeholder precedence" "unexpected value '$GOT1'" ;;
esac

# E4: end-to-end, the production path must yield exactly the four frozen role MACs
MAP=$(env -u RT3000_ETHADDR_SOURCE RT3000_APPSBLENV="$RAWENV" \
	PATH=/usr/bin:/bin sh -c '. "'"$SCRIPT"'"; rt3000_mac_map' 2>/dev/null)
ELAN=$(printf '%s\n' "$MAP" | sed -n 's/^lan //p')
E24=$(printf '%s\n' "$MAP"  | sed -n 's/^wifi24 //p')
E5=$(printf '%s\n' "$MAP"   | sed -n 's/^wifi5 //p')
EWAN=$(printf '%s\n' "$MAP" | sed -n 's/^wan //p')

if [ "$EWAN" = "00:11:22:33:44:55" ] && [ "$ELAN" = "9e:a7:ce:69:5e:6a" ] && \
   [ "$E24" = "da:96:3b:3f:c7:c2" ] && [ "$E5" = "2e:1c:f2:2a:33:76" ]; then
	ok "production path yields the four frozen role MACs from the raw environment"
else
	bad "production role MACs" "wan=$EWAN lan=$ELAN w24=$E24 w5=$E5"
fi

# E5: the shipped image must actually carry the MAC policy implementation
if [ -f "$SCRIPT" ] && grep -q 'rt3000_derive_mac' "$SCRIPT"; then
	ok "MAC policy implementation present for packaging"
else
	bad "policy present" "$SCRIPT"
fi

echo
echo "==================================================="
echo "MAC_TESTS_PASS=$PASS"
echo "MAC_TESTS_FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then
	echo "MAC_POLICY_TESTS=PASS"
else
	echo "MAC_POLICY_TESTS=FAIL"
	printf '%s\n' "$FAILED"
fi
echo "==================================================="
[ "$FAIL" -eq 0 ]
