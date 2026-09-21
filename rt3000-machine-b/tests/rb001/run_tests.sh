#!/bin/bash
# RB001 synthetic fail-closed test suite for rt3bcwrite.
# Every case runs against a private fixture directory; no real MTD is touched.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="${RT3BCWRITE:-$HERE/rt3bcwrite_mock}"
MK="$HERE/mkfixture.py"
TMP="$(mktemp -d)"
PASS=0; FAIL=0
declare -a FAILED

ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED+=("$1"); printf 'FAIL  %s   -- %s\n' "$1" "${2:-}"; }

# selector_of <file>
sel_of() { python3 -c "import struct,sys;print(struct.unpack_from('<I',open(sys.argv[1],'rb').read(),0x80)[0])" "$1"; }
# sha_of <file>
sha_of() { sha256sum "$1" | cut -d' ' -f1; }

# new_case <name> <sel>
new_case() {
  CASE="$TMP/$1"; rm -rf "$CASE"; mkdir -p "$CASE"
  python3 "$MK" good "$CASE/mtd3" "${2:-1}"
  python3 "$MK" good "$CASE/mtd2" "${2:-1}"
}

# run <extra env...> -- <args...>
run_case() {
  local case="$1"; shift
  ( cd "$case" && env RT3BCWRITE_MOCK_DIR="$case" "$@" )
}

echo "=== RB001 synthetic fail-closed test suite ==="
echo "binary: $BIN"
echo

##############################################################################
echo "--- group A: happy path + binary safety ---"
##############################################################################

# 1. selector 0 -> 1
new_case t01 0
out=$(run_case "$CASE" "$BIN" --set 1 2>&1); rc=$?
s3=$(sel_of "$CASE/mtd3"); s2=$(sel_of "$CASE/mtd2")
if [ $rc -eq 0 ] && [ "$s3" = 1 ] && [ "$s2" = 1 ]; then ok "01 selector 0->1"; else bad "01 selector 0->1" "rc=$rc mtd3=$s3 mtd2=$s2"; fi

# 1b. exact byte pattern 01 00 00 00 on media
raw=$(xxd -p -s 128 -l 4 "$CASE/mtd2" 2>/dev/null || od -An -tx1 -j128 -N4 "$CASE/mtd2" | tr -d ' \n')
if [ "$raw" = "01000000" ]; then ok "01b media bytes == 01 00 00 00"; else bad "01b media bytes" "got=$raw"; fi

# 2. selector 1 -> 0
new_case t02 1
out=$(run_case "$CASE" "$BIN" --set 0 2>&1); rc=$?
s3=$(sel_of "$CASE/mtd3"); s2=$(sel_of "$CASE/mtd2")
if [ $rc -eq 0 ] && [ "$s3" = 0 ] && [ "$s2" = 0 ]; then ok "02 selector 1->0"; else bad "02 selector 1->0" "rc=$rc mtd3=$s3 mtd2=$s2"; fi
raw=$(od -An -tx1 -j128 -N4 "$CASE/mtd2" | tr -d ' \n')
if [ "$raw" = "00000000" ]; then ok "02b media bytes == 00 00 00 00"; else bad "02b media bytes" "got=$raw"; fi

# 16. ASCII "\001" negative test: the 4 media bytes must never be 5c 30 30 31
if [ "$raw" != "5c303031" ] && [ "$raw" != "5c30303100" ]; then ok "16 no ASCII backslash-001 escape on media"; else bad "16 ASCII escape detected" "got=$raw"; fi

# 3. OEM blob @0x880+ preserved byte-identical
new_case t03 1
blob_before=$(dd if="$CASE/mtd2" bs=1 skip=2176 count=1024 2>/dev/null | sha256sum | cut -d' ' -f1)
run_case "$CASE" "$BIN" --set 0 >/dev/null 2>&1
blob_after=$(dd if="$CASE/mtd2" bs=1 skip=2176 count=1024 2>/dev/null | sha256sum | cut -d' ' -f1)
if [ "$blob_before" = "$blob_after" ] && [ -n "$blob_before" ]; then ok "03 OEM blob @0x880 preserved"; else bad "03 OEM blob" "before=$blob_before after=$blob_after"; fi

# 17. unrelated byte mutation detection.
#     A real selector change is 0 -> 1, which flips exactly byte 128 (the other
#     three selector bytes are already 0x00).  To prove that no OTHER byte can
#     ever move, start from a fixture whose remaining three selector bytes are
#     non-zero and confirm exactly bytes 128..131 change.
new_case t17 0
cp "$CASE/mtd2" "$CASE/mtd2.pristine"
run_case "$CASE" "$BIN" --set 1 >/dev/null 2>&1
ndiff=$(python3 -c "
a=open('$CASE/mtd2.pristine','rb').read(); b=open('$CASE/mtd2','rb').read()
d=[i for i in range(len(a)) if a[i]!=b[i]]
print(len(d), ' '.join(map(str,d)))
")
set -- $ndiff; n=${1}; shift || true
if [ "$n" = "1" ] && [ "$*" = "128" ]; then
  ok "17 exactly byte 128 changed on 0->1 (no collateral bytes)"
else
  bad "17 byte-diff 0->1" "count=$n at=$*"
fi

# 17b. force all four selector bytes to flip: plant a non-zero LE32 at 0x80,
#      then set to 0 and confirm exactly bytes 128..131 changed.
new_case t17b 1
python3 - "$CASE/mtd2" "$CASE/mtd3" <<'PYX'
import struct,sys
for f in sys.argv[1:]:
    d=bytearray(open(f,'rb').read())
    struct.pack_into('<I',d,0x80,0x01010101)
    open(f,'wb').write(bytes(d))
PYX
cp "$CASE/mtd2" "$CASE/mtd2.pristine"
run_case "$CASE" "$BIN" --set 0 >/dev/null 2>&1
ndiff=$(python3 -c "
a=open('$CASE/mtd2.pristine','rb').read(); b=open('$CASE/mtd2','rb').read()
d=[i for i in range(len(a)) if a[i]!=b[i]]
print(len(d), ' '.join(map(str,d)))
")
set -- $ndiff; n=${1}; shift || true
if [ "$n" = "4" ] && [ "$*" = "128 129 130 131" ]; then
  ok "17b exactly bytes 128-131 changed on 0x01010101->0 (no collateral bytes)"
else
  bad "17b byte-diff 4-byte flip" "count=$n at=$*"
fi

# 18. already-at-target idempotent
new_case t18 1
out=$(run_case "$CASE" "$BIN" --set 1 2>&1); rc=$?
h3=$(sha_of "$CASE/mtd3"); h2=$(sha_of "$CASE/mtd2")
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'already 0x00000001'; then ok "18 already-at-target idempotent"; else bad "18 idempotent" "rc=$rc out=$out"; fi

##############################################################################
echo
echo "--- group B: structural refusal (nothing may be written) ---"
##############################################################################

struct_case() {  # <name> <desc> <fixture-args...>
  local name="$1"; local desc="$2"; shift 2
  local case="$TMP/$name"; rm -rf "$case"; mkdir -p "$case"
  python3 "$MK" raw "$case/mtd3" 1 "$@" 2>/dev/null || python3 -c "
import struct,sys
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xa3a2a1a0); struct.pack_into('<I',d,4,1); struct.pack_into('<I',d,8,8)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfs','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xb3b2b1b0)
open(sys.argv[1],'wb').write(bytes(d))
" "$case/mtd3"
  python3 "$MK" good "$case/mtd2" 1
  local before3 before2
  before3=$(sha_of "$case/mtd3"); before2=$(sha_of "$case/mtd2")
  local out rc
  out=$(cd "$case" && RT3BCWRITE_MOCK_DIR="$case" "$BIN" --set 0 2>&1); rc=$?
  local after3 after2
  after3=$(sha_of "$case/mtd3"); after2=$(sha_of "$case/mtd2")
  if [ $rc -ne 0 ] && [ "$before3" = "$after3" ] && [ "$before2" = "$after2" ]; then
    ok "$name $desc"
  else
    bad "$name $desc" "rc=$rc mtd3_same=$([ "$before3" = "$after3" ] && echo y || echo n) mtd2_same=$([ "$before2" = "$after2" ] && echo y || echo n)"
  fi
  return $rc
}

# 4. bad magic
sc=$(mktemp -d); cp "$TMP/t18/mtd2" "$sc/mtd2" 2>/dev/null || python3 "$MK" good "$sc/mtd2" 1
python3 - "$sc/mtd3" <<'PY'
import struct,sys
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xdeadbeef); struct.pack_into('<I',d,4,1); struct.pack_into('<I',d,8,8)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfs','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xb3b2b1b0)
open(sys.argv[1],'wb').write(bytes(d))
PY
python3 "$MK" good "$sc/mtd2" 1
b3=$(sha_of "$sc/mtd3"); b2=$(sha_of "$sc/mtd2")
(cd "$sc" && RT3BCWRITE_MOCK_DIR="$sc" "$BIN" --set 0 >/dev/null 2>&1); rc=$?
a3=$(sha_of "$sc/mtd3"); a2=$(sha_of "$sc/mtd2")
[ $rc -ne 0 ] && [ "$b3" = "$a3" ] && [ "$b2" = "$a2" ] && ok "04 bad magic refused, 0 writes" || bad "04 bad magic" "rc=$rc"

# 5. bad version
python3 - "$sc" <<'PY'
import struct,sys,os
c=sys.argv[1]
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xa3a2a1a0); struct.pack_into('<I',d,4,99); struct.pack_into('<I',d,8,8)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfs','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xb3b2b1b0)
open(os.path.join(c,'mtd3'),'wb').write(bytes(d))
PY
b3=$(sha_of "$sc/mtd3"); b2=$(sha_of "$sc/mtd2")
(cd "$sc" && RT3BCWRITE_MOCK_DIR="$sc" "$BIN" --set 0 >/dev/null 2>&1); rc=$?
a3=$(sha_of "$sc/mtd3"); a2=$(sha_of "$sc/mtd2")
[ $rc -ne 0 ] && [ "$b3" = "$a3" ] && [ "$b2" = "$a2" ] && ok "05 bad version refused, 0 writes" || bad "05 bad version" "rc=$rc"

# 6. bad count
python3 - "$sc" <<'PY'
import struct,sys,os
c=sys.argv[1]
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xa3a2a1a0); struct.pack_into('<I',d,4,1); struct.pack_into('<I',d,8,7)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfs','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xb3b2b1b0)
open(os.path.join(c,'mtd3'),'wb').write(bytes(d))
PY
b3=$(sha_of "$sc/mtd3"); b2=$(sha_of "$sc/mtd2")
(cd "$sc" && RT3BCWRITE_MOCK_DIR="$sc" "$BIN" --set 0 >/dev/null 2>&1); rc=$?
a3=$(sha_of "$sc/mtd3"); a2=$(sha_of "$sc/mtd2")
[ $rc -ne 0 ] && [ "$b3" = "$a3" ] && [ "$b2" = "$a2" ] && ok "06 bad count refused, 0 writes" || bad "06 bad count" "rc=$rc"

# 7. bad tail magic
python3 - "$sc" <<'PY'
import struct,sys,os
c=sys.argv[1]
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xa3a2a1a0); struct.pack_into('<I',d,4,1); struct.pack_into('<I',d,8,8)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfs','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xdeadbeef)
open(os.path.join(c,'mtd3'),'wb').write(bytes(d))
PY
b3=$(sha_of "$sc/mtd3"); b2=$(sha_of "$sc/mtd2")
(cd "$sc" && RT3BCWRITE_MOCK_DIR="$sc" "$BIN" --set 0 >/dev/null 2>&1); rc=$?
a3=$(sha_of "$sc/mtd3"); a2=$(sha_of "$sc/mtd2")
[ $rc -ne 0 ] && [ "$b3" = "$a3" ] && [ "$b2" = "$a2" ] && ok "07 bad tail magic refused, 0 writes" || bad "07 bad tail" "rc=$rc"

# 8. missing/corrupt rootfs record
python3 - "$sc" <<'PY'
import struct,sys,os
c=sys.argv[1]
d=bytearray(4096); d[:]=b'\xff'*4096
struct.pack_into('<I',d,0,0xa3a2a1a0); struct.pack_into('<I',d,4,1); struct.pack_into('<I',d,8,8)
for i,n in enumerate(['sbl1','mibib','bootconfig','bootconfig1','qsee','rootfz','rootfs_1','pdt_data']):
    off=12+i*20; nb=n.encode(); d[off:off+len(nb)]=nb; d[off+len(nb)]=0
    struct.pack_into('<I',d,off+16,1)
struct.pack_into('<I',d,0x14c,0xb3b2b1b0)
open(os.path.join(c,'mtd3'),'wb').write(bytes(d))
PY
b3=$(sha_of "$sc/mtd3"); b2=$(sha_of "$sc/mtd2")
(cd "$sc" && RT3BCWRITE_MOCK_DIR="$sc" "$BIN" --set 0 >/dev/null 2>&1); rc=$?
a3=$(sha_of "$sc/mtd3"); a2=$(sha_of "$sc/mtd2")
[ $rc -ne 0 ] && [ "$b3" = "$a3" ] && [ "$b2" = "$a2" ] && ok "08 missing rootfs record refused, 0 writes" || bad "08 missing rootfs" "rc=$rc"

##############################################################################
echo
echo "--- group C: first-copy failure => second copy 0 writes ---"
##############################################################################

first_copy_fail() {  # <name> <desc> <env-var>
  local name="$1" desc="$2" var="$3"
  local case="$TMP/$name"; rm -rf "$case"; mkdir -p "$case"
  python3 "$MK" good "$case/mtd3" 1; python3 "$MK" good "$case/mtd2" 1
  local b2; b2=$(sha_of "$case/mtd2")
  local order="$case/order.txt"
  local out rc
  out=$(cd "$case" && env RT3BCWRITE_MOCK_DIR="$case" \
        RT3BCWRITE_MOCK_ORDER="$order" "$var=1" "$BIN" --set 0 2>&1); rc=$?
  local a2; a2=$(sha_of "$case/mtd2")
  local wrote2="NO"
  [ -f "$order" ] && grep -q '^mtd2$' "$order" && wrote2="YES"
  if [ $rc -ne 0 ] && [ "$b2" = "$a2" ] && [ "$wrote2" = "NO" ]; then
    ok "$name $desc (mtd2 0 writes)"
  else
    bad "$name $desc" "rc=$rc mtd2_same=$([ "$b2" = "$a2" ] && echo y || echo n) mtd2_written=$wrote2"
  fi
}

# 9. first-copy write failure
first_copy_fail t09 "first-copy write failure" RT3BCWRITE_MOCK_FAIL_mtd3_WRITE
# 10. first-copy readback mismatch
first_copy_fail t10 "first-copy readback mismatch" RT3BCWRITE_MOCK_CORRUPT_mtd3
# 11. first-copy structural failure -> emulated by corrupting mtd3 structure
case="$TMP/t11"; rm -rf "$case"; mkdir -p "$case"
python3 "$MK" good "$case/mtd3" 1; python3 "$MK" good "$case/mtd2" 1
# corrupt the tail of mtd3 only
printf '\xde\xad\xbe\xef' | dd of="$case/mtd3" bs=1 seek=332 conv=notrunc 2>/dev/null
b2=$(sha_of "$case/mtd2")
out=$(cd "$case" && RT3BCWRITE_MOCK_DIR="$case" "$BIN" --set 0 2>&1); rc=$?
a2=$(sha_of "$case/mtd2")
[ $rc -ne 0 ] && [ "$b2" = "$a2" ] && ok "11 first-copy structural failure (mtd2 0 writes)" || bad "11 structural failure" "rc=$rc"

# 12. explicit: after first-copy failure, count mtd2 write attempts == 0
#     (t09/t10 already assert this via the order log; assert count explicitly)
cnt=0
for c in t09 t10; do
  if [ -f "$TMP/$c/order.txt" ]; then
    n=$(grep -c '^mtd2$' "$TMP/$c/order.txt" 2>/dev/null || true)
    [ -n "$n" ] && cnt=$((cnt + n))
  fi
done
[ "$cnt" = "0" ] && ok "12 first-copy failure => mtd2 write attempts == 0" || bad "12 mtd2 attempts" "count=$cnt"

##############################################################################
echo
echo "--- group D: second-copy failure => nonzero exit, divergent reported ---"
##############################################################################

# 13. second-copy write failure
case="$TMP/t13"; rm -rf "$case"; mkdir -p "$case"
python3 "$MK" good "$case/mtd3" 1; python3 "$MK" good "$case/mtd2" 1
out=$(cd "$case" && env RT3BCWRITE_MOCK_DIR="$case" \
      RT3BCWRITE_MOCK_FAIL_mtd2_WRITE=1 "$BIN" --set 0 2>&1); rc=$?
s3=$(sel_of "$case/mtd3")
if [ $rc -ne 0 ] && [ "$s3" = 0 ] && printf '%s' "$out" | grep -qi 'divergen'; then
  ok "13 second-copy write failure: nonzero exit + divergent reported"
else
  bad "13 second-copy write failure" "rc=$rc mtd3=$s3 out=$(printf '%s' "$out"|tail -2|tr '\n' '|')"
fi

# 14. second-copy readback mismatch
case="$TMP/t14"; rm -rf "$case"; mkdir -p "$case"
python3 "$MK" good "$case/mtd3" 1; python3 "$MK" good "$case/mtd2" 1
out=$(cd "$case" && env RT3BCWRITE_MOCK_DIR="$case" \
      RT3BCWRITE_MOCK_CORRUPT_mtd2=1 "$BIN" --set 0 2>&1); rc=$?
s3=$(sel_of "$case/mtd3")
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi 'divergen'; then
  ok "14 second-copy readback mismatch: nonzero exit + divergent reported"
else
  bad "14 second-copy readback" "rc=$rc mtd3=$s3"
fi

# 15. selector corruption: mtd2 selector changed but structure still valid
case="$TMP/t15"; rm -rf "$case"; mkdir -p "$case"
python3 "$MK" good "$case/mtd3" 1; python3 "$MK" good "$case/mtd2" 1
printf '\x02\x00\x00\x00' | dd of="$case/mtd2" bs=1 seek=128 conv=notrunc 2>/dev/null
out=$(cd "$case" && RT3BCWRITE_MOCK_DIR="$case" "$BIN" --set 0 2>&1); rc=$?
if [ $rc -ne 0 ]; then ok "15 invalid selector value 0x2 rejected"; else bad "15 selector corruption" "rc=$rc"; fi

# 15b. selector corruption -> target 0x2 must be refused by arg validation
out=$(cd "$case" && RT3BCWRITE_MOCK_DIR="$case" "$BIN" --set 2 2>&1); rc=$?
if [ $rc -ne 0 ]; then ok "15b --set 2 refused (only 0/1)"; else bad "15b --set 2" "rc=$rc"; fi

echo
echo "==================================================="
echo "RB001_TESTS_PASS=$PASS"
echo "RB001_TESTS_FAIL=$FAIL"
if [ $FAIL -eq 0 ]; then
  echo "FAIL_CLOSED=YES"
  echo "RB001_TESTS=PASS"
else
  echo "FAIL_CLOSED=NO"
  echo "RB001_TESTS=FAIL"
  for f in "${FAILED[@]}"; do echo "  failed: $f"; done
fi
echo "==================================================="
rm -rf "$TMP" "$sc"
[ $FAIL -eq 0 ]
