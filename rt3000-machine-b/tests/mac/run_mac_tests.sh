#!/bin/sh
# RT3000 B/C — OEM-numbered MAC policy test suite.
#
# Runs entirely offline against the shipped derivation script; no device, no
# network.  Set RT3000_ETHADDR_SOURCE to inject a factory value.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="${1:-$HERE/../../../target/linux/ipq50xx/base-files/lib/rt3000/mac.sh}"
PASS=0; FAIL=0; FAILED=""

ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED="$FAILED
  $1"; printf 'FAIL  %s   -- %s\n' "$1" "${2:-}"; }

# run with an injected factory MAC
run_mac() { RT3000_ETHADDR_SOURCE="$1" sh -c '. "$1"; rt3000_mac_map' sh "$SCRIPT" 2>&1; }

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

# OEM numbering: LAN/WiFi24/WiFi5 = factory +1/+2/+3
LAN=$(field lan "$OUT1"); W24=$(field wifi24 "$OUT1"); W5=$(field wifi5 "$OUT1")
WAN=$(field wan "$OUT1")
if [ "$WAN" = "$FACTORY" ] && [ "$LAN" = "00:11:22:33:44:56" ] && \
   [ "$W24" = "00:11:22:33:44:57" ] && [ "$W5" = "00:11:22:33:44:58" ]; then
	ok "wan unchanged, lan/wifi24/wifi5 = factory +1/+2/+3"
else
	bad "OEM numbering" "wan=$WAN lan=$LAN wifi24=$W24 wifi5=$W5"
fi

# HW-C reference unit: OEM firmware showed LAN dc:65:55:bb:d9:68
OUTC=$(run_mac "DC:65:55:BB:D9:67")
[ "$(field lan "$OUTC")" = "dc:65:55:bb:d9:68" ] && ok "HW-C LAN matches OEM (WAN+1)" \
	|| bad "HW-C OEM LAN" "lan=$(field lan "$OUTC")"

# carry crosses octets over all 48 bits, like hwd-factory-mac
OUTK=$(run_mac "00:11:22:ff:ff:fe")
[ "$(field wifi24 "$OUTK")" = "00:11:23:00:00:00" ] && ok "carry propagates across octets" \
	|| bad "carry" "wifi24=$(field wifi24 "$OUTK")"

# different factory MACs must give different role MACs
OUT_OTHER=$(run_mac "00:11:22:33:44:65")
[ "$(field lan "$OUT1")" != "$(field lan "$OUT_OTHER")" ] && ok "role MACs follow the factory MAC" \
	|| bad "factory sensitivity" "same LAN MAC for different factory"

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

if [ "$EWAN" = "00:11:22:33:44:55" ] && [ "$ELAN" = "00:11:22:33:44:56" ] && \
   [ "$E24" = "00:11:22:33:44:57" ] && [ "$E5" = "00:11:22:33:44:58" ]; then
	ok "production path yields the four OEM-numbered role MACs from the raw environment"
else
	bad "production role MACs" "wan=$EWAN lan=$ELAN w24=$E24 w5=$E5"
fi

# E5: the shipped image must actually carry the MAC policy implementation
if [ -f "$SCRIPT" ] && grep -q 'rt3000_mac_add' "$SCRIPT"; then
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
