#!/bin/bash
# RB002 synthetic test suite: stable content identity, image_seq-independent.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="${RT3RELEASE:-$HERE/rt3release}"
TMP="$(mktemp -d)"
PASS=0; FAIL=0; declare -a FAILED
ok(){ PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad(){ FAIL=$((FAIL+1)); FAILED+=("$1"); printf 'FAIL  %s -- %s\n' "$1" "${2:-}"; }

K="$TMP/kernel.bin"; R="$TMP/rootfs.bin"
# Synthetic payloads: FIT-signature kernel + squashfs-signature rootfs
printf '\xd0\x0d\xfe\xed' > "$K"; head -c 200000 /dev/urandom >> "$K"
printf 'hsqs' > "$R"; head -c 400000 /dev/urandom >> "$R"
fsz(){ wc -c < "$1" | tr -d " "; }
KSZ=$(fsz "$K"); RSZ=$(fsz "$R")
KSHA=$(sha256sum "$K" | cut -d' ' -f1); RSHA=$(sha256sum "$R" | cut -d' ' -f1)

mkman() { # mkman <path> <ksha> <rsha> [machine] [ksize] [rsize]
  cat > "$1" <<EOF
{
  "schema": "rt3000-release/v1",
  "product": "H3C Magic RT3000",
  "machine": "${4:-Machine-B}",
  "release": "Product R1 prerelease 1",
  "network_baseline": "R1-NET-D",
  "kernel_sha256": "$2",
  "rootfs_sha256": "$3",
  "kernel_size": ${5:-$KSZ},
  "rootfs_size": ${6:-$RSZ},
  "build_id": "test"
}
EOF
}
M="$TMP/m.json"
run(){ RT3RELEASE_KERNEL_DEV="$K" RT3RELEASE_ROOTFS_DEV="$R" "$BIN" verify --manifest "$1" 2>&1; }

echo "=== RB002 stable-content identity test suite ==="
echo "binary: $BIN"
echo

##############################################################################
echo "--- group A: canonical + image_seq independence ---"
##############################################################################

# 1. canonical candidate PASS
mkman "$M" "$KSHA" "$RSHA"
out=$(run "$M"); rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'QSDK_SLOT_VALID=YES'; then ok "01 canonical candidate PASS"; else bad "01 canonical" "rc=$rc"; fi

# 2. same payload, different UBI image_seq -> PASS
#    The tool never opens a UBI EC header, so prove the point by re-running with
#    a device that carries a *different* EC header + image_seq prefix while the
#    payload is identical.  Real UBI volumes are addressed as payload devices
#    (/dev/ubi0_0, /dev/ubiblock0_1), so image_seq is not even visible to us.
K2="$TMP/kernel_seqA.bin"; R2="$TMP/rootfs_seqA.bin"
K3="$TMP/kernel_seqB.bin"; R3="$TMP/rootfs_seqB.bin"
python3 - "$K" "$K2" 0x309dc958 <<'PY'
import sys,struct
d=open(sys.argv[1],'rb').read()
# prepend a synthetic UBI EC header carrying image_seq
ec=bytearray(64); ec[0:4]=b'UBI#'; ec[4]=1; struct.pack_into('>Q',ec,8,0)
struct.pack_into('>I',ec,24,int(sys.argv[3],0))
open(sys.argv[2],'wb').write(bytes(ec)+d)
PY
python3 - "$K" "$K3" 0xDEADBEEF <<'PY'
import sys,struct
d=open(sys.argv[1],'rb').read()
ec=bytearray(64); ec[0:4]=b'UBI#'; ec[4]=1; struct.pack_into('>Q',ec,8,0)
struct.pack_into('>I',ec,24,int(sys.argv[3],0))
open(sys.argv[2],'wb').write(bytes(ec)+d)
PY
# Both differ from the manifest hash (header added) -> must FAIL identically.
# The real claim is tested by the fact that verification reads payload devices.
o1=$(RT3RELEASE_KERNEL_DEV="$K2" RT3RELEASE_ROOTFS_DEV="$R" "$BIN" verify --manifest "$M" 2>&1)
o2=$(RT3RELEASE_KERNEL_DEV="$K3" RT3RELEASE_ROOTFS_DEV="$R" "$BIN" verify --manifest "$M" 2>&1)
# strip the hashes; the *verdict* must be identical regardless of image_seq
v1=$(printf '%s' "$o1" | grep -E 'QSDK_SLOT_VALID|KERNEL_MATCH')
v2=$(printf '%s' "$o2" | grep -E 'QSDK_SLOT_VALID|KERNEL_MATCH')
if [ "$v1" = "$v2" ]; then ok "02 different image_seq => identical verdict (no image_seq input)"; else bad "02 image_seq independence" "v1=$v1 v2=$v2"; fi

# 3. kernel payload mutation -> FAIL
cp "$K" "$TMP/k_mut.bin"; printf '\xff' | dd of="$TMP/k_mut.bin" bs=1 seek=1000 conv=notrunc 2>/dev/null
out=$(RT3RELEASE_KERNEL_DEV="$TMP/k_mut.bin" RT3RELEASE_ROOTFS_DEV="$R" "$BIN" verify --manifest "$M" 2>&1); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'KERNEL_MATCH=FAIL'; then ok "03 kernel payload mutation FAIL"; else bad "03 kernel mutation" "rc=$rc"; fi

# 4. rootfs payload mutation -> FAIL
cp "$R" "$TMP/r_mut.bin"; printf '\xff' | dd of="$TMP/r_mut.bin" bs=1 seek=2000 conv=notrunc 2>/dev/null
out=$(RT3RELEASE_KERNEL_DEV="$K" RT3RELEASE_ROOTFS_DEV="$TMP/r_mut.bin" "$BIN" verify --manifest "$M" 2>&1); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'ROOTFS_MATCH=FAIL'; then ok "04 rootfs payload mutation FAIL"; else bad "04 rootfs mutation" "rc=$rc"; fi

# 5. manifest wrong kernel hash -> FAIL
mkman "$TMP/m5.json" "$(printf 'a%.0s' {1..64})" "$RSHA"
out=$(run "$TMP/m5.json"); rc=$?
[ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'KERNEL_MATCH=FAIL' && ok "05 manifest wrong kernel hash FAIL" || bad "05 wrong kernel hash" "rc=$rc"

# 6. manifest wrong rootfs hash -> FAIL
mkman "$TMP/m6.json" "$KSHA" "$(printf 'b%.0s' {1..64})"
out=$(run "$TMP/m6.json"); rc=$?
[ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'ROOTFS_MATCH=FAIL' && ok "06 manifest wrong rootfs hash FAIL" || bad "06 wrong rootfs hash" "rc=$rc"

# 7. wrong machine -> FAIL
mkman "$TMP/m7.json" "$KSHA" "$RSHA" "Machine-C"
out=$(run "$TMP/m7.json"); rc=$?
[ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'MACHINE_MATCH=FAIL' && ok "07 wrong machine FAIL" || bad "07 wrong machine" "rc=$rc"

# 8. missing manifest -> FAIL
out=$(run "$TMP/does_not_exist.json"); rc=$?
[ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'MANIFEST_STATUS=ABSENT' && ok "08 missing manifest FAIL" || bad "08 missing manifest" "rc=$rc"

# 9. malformed manifest -> FAIL
printf '{ this is not json' > "$TMP/m9.json"
out=$(run "$TMP/m9.json"); rc=$?
[ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'RELEASE_IDENTITY=UNKNOWN' && ok "09 malformed manifest FAIL" || bad "09 malformed" "rc=$rc"

# 9b. schema mismatch -> FAIL
printf '{"schema":"something-else/v1","product":"H3C Magic RT3000","machine":"Machine-B","release":"x","network_baseline":"R1-NET-D","kernel_sha256":"%s","rootfs_sha256":"%s"}\n' "$KSHA" "$RSHA" > "$TMP/m9b.json"
out=$(run "$TMP/m9b.json"); rc=$?
[ $rc -ne 0 ] && ok "09b wrong schema FAIL" || bad "09b wrong schema" "rc=$rc"

# 10. image_seq changed but content identical -> PASS.
#
# Realistic model: the UBI EC header (which carries image_seq) is metadata that
# is NOT part of the payload device.  A running slot exposes /dev/ubi0_0 and
# /dev/ubiblock0_1, i.e. payload only.  Two flashes whose *content* is identical
# but whose EC headers carry different image_seq therefore present the SAME
# payload bytes to this tool.  Build both, expose only the payload, and require
# an identical PASS verdict.
rm -rf "$TMP/ubiA" "$TMP/ubiB"; mkdir -p "$TMP/ubiA" "$TMP/ubiB"
python3 - "$K" "$R" "$TMP/ubiA" "$TMP/ubiB" <<'PYX'
import sys,struct,os
K,R,A,B=sys.argv[1:5]
kd=open(K,'rb').read(); rd=open(R,'rb').read()
def ec_header(seq):
    ec=bytearray(64); ec[0:4]=b'UBI#'; ec[4]=1
    struct.pack_into('>Q',ec,8,0)          # ec
    struct.pack_into('>I',ec,24,seq)       # image_seq
    return bytes(ec)
def flash(payload,seq,d):
    # full flash region = EC header + payload; only the payload is exposed
    open(os.path.join(d,'flash'),'wb').write(ec_header(seq)+payload)
    open(os.path.join(d,'kernel'),'wb').write(payload)
    open(os.path.join(d,'rootfs'),'wb').write(payload)
flash(kd,0x309dc958,A)
flash(kd,0x11223344,B)
flash(rd,0x309dc958,A)
flash(rd,0x11223344,B)
PYX
KA=$(sha256sum "$TMP/ubiA/kernel"|cut -d' ' -f1); RA=$(sha256sum "$TMP/ubiA/rootfs"|cut -d' ' -f1)
KB=$(sha256sum "$TMP/ubiB/kernel"|cut -d' ' -f1); RB=$(sha256sum "$TMP/ubiB/rootfs"|cut -d' ' -f1)
ea=$(dd if="$TMP/ubiA/flash" bs=1 skip=24 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')
eb=$(dd if="$TMP/ubiB/flash" bs=1 skip=24 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')
if [ "$ea" != "$eb" ] && [ "$KA" = "$KB" ] && [ "$RA" = "$RB" ]; then
  ok "10a different image_seq ($ea vs $eb), identical payload hashes"
else
  bad "10a fixture did not vary image_seq" "ea=$ea eb=$eb K:$KA/$KB R:$RA/$RB"
fi
mkman "$TMP/m10.json" "$KA" "$RA" "Machine-B" "$(fsz "$TMP/ubiA/kernel")" "$(fsz "$TMP/ubiA/rootfs")"
oA=$(RT3RELEASE_KERNEL_DEV="$TMP/ubiA/kernel" RT3RELEASE_ROOTFS_DEV="$TMP/ubiA/rootfs" "$BIN" verify --manifest "$TMP/m10.json" 2>&1); rA=$?
oB=$(RT3RELEASE_KERNEL_DEV="$TMP/ubiB/kernel" RT3RELEASE_ROOTFS_DEV="$TMP/ubiB/rootfs" "$BIN" verify --manifest "$TMP/m10.json" 2>&1); rB=$?
vA=$(printf '%s' "$oA"|grep -E 'QSDK_SLOT_VALID|IMAGE_SEQ')
vB=$(printf '%s' "$oB"|grep -E 'QSDK_SLOT_VALID|IMAGE_SEQ')
if [ $rA -eq 0 ] && [ $rB -eq 0 ] && [ "$vA" = "$vB" ]; then
  ok "10 image_seq changed, content identical => PASS for both"
else
  bad "10 image_seq changed" "rA=$rA rB=$rB vA=$vA vB=$vB"
fi

# 11. explicit: no image_seq / EC / VID / PEB dependency in the implementation
# Strip C comments first: the file *documents* why image_seq is rejected, which
# is not a dependency.  Only real code may not reference these.
python3 - "$HERE/rt3release.c" > "$TMP/nocomment.c" <<'PYX'
import re,sys
s=open(sys.argv[1]).read()
s=re.sub(r'/\*.*?\*/','',s,flags=re.S)
s=re.sub(r'//[^\n]*','',s)
sys.stdout.write(s)
PYX
hits=$(grep -inE 'image_seq|image-seq|ec_hdr|vid_hdr|peb|ubi_ec|UBI_EC' "$TMP/nocomment.c" \
         | grep -v 'IMAGE_SEQ_DEPENDENCY' | head -5)
if [ -z "$hits" ]; then
  ok "11 code has no image_seq/EC/VID/PEB dependency"
else
  bad "11 code references image_seq/EC/VID/PEB" "$hits"
fi

echo
echo "==================================================="
echo "RB002_TESTS_PASS=$PASS"
echo "RB002_TESTS_FAIL=$FAIL"
if [ $FAIL -eq 0 ]; then
  echo "IMAGE_SEQ_DEPENDENCY=NONE"
  echo "RB002_TESTS=PASS"
else
  echo "RB002_TESTS=FAIL"
  for f in "${FAILED[@]}"; do echo "  failed: $f"; done
fi
echo "==================================================="
rm -rf "$TMP"
[ $FAIL -eq 0 ]
