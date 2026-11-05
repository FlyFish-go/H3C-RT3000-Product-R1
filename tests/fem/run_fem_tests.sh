#!/bin/sh
# H3C mp02.1 5 GHz FEM probe + HW-D board data selection (offline).
#
# Runs the shipped lib/rt3000/fem.sh and the HW-D preinit 05_hwd_caldata
# against fake ART images (paths rewritten into a temp dir), and checks the
# two-entry board-2.bin the hwd-nx30-oem-wifi package builds.
# Usage: run_fem_tests.sh   (any POSIX sh with dd, hexdump, python3)
set -u
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
FEM="$ROOT/target/linux/ipq50xx/base-files/lib/rt3000/fem.sh"
CAL="$ROOT/package/firmware/hwd-nx30-oem-wifi/files/05_hwd_caldata"
PKG="$ROOT/package/firmware/hwd-nx30-oem-wifi/files"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
chk() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS  $1 ($3)"; else FAIL=$((FAIL+1)); echo "  FAIL  $1: expected [$3] got [$2]"; fi; }

# fake ART: 0x80000 bytes of 0xff, 5 GHz block header + flags at 0x26800
mkart() { # name hdr b3a b45
	python3 - "$T/$1" "$2" "$3" "$4" <<'PY'
import sys
p,h,a,b=sys.argv[1:]
d=bytearray(b"\xff"*0x80000)
if h: d[0x26800:0x26804]=bytes.fromhex(h)
if a: d[0x26800+0x3a]=int(a,16)
if b: d[0x26800+0x45]=int(b,16)
open(p,"wb").write(d)
PY
}
mkart fem 01000404 60 09
mkart nofem 01000404 50 01
mkart mixed 01000404 60 01
mkart badhdr 01000405 50 01
mkart blank "" "" ""
printf 'dev:    size   erasesize  name\nmtd9: 00080000 00020000 "0:ART"\n' > "$T/mtd"
: > "$T/mtd-none"

sed -e "s#/proc/mtd#\$H3C_TEST_MTD#; s#/dev/\$mtd#\$H3C_TEST_ART#" "$FEM" > "$T/fem.sh"
probe() { H3C_TEST_MTD="$2" H3C_TEST_ART="$T/$1" sh -c ". $T/fem.sh; h3c_fem_probe"; }
echo "fem.sh probe"
chk fem "$(probe fem "$T/mtd")" fem
chk nofem "$(probe nofem "$T/mtd")" nofem
chk "mixed flags" "$(probe mixed "$T/mtd")" unknown
chk "bad header" "$(probe badhdr "$T/mtd")" unknown
chk "erased ART" "$(probe blank "$T/mtd")" unknown
chk "no ART partition" "$(probe fem "$T/mtd-none")" unknown

echo "05_hwd_caldata"
sed -e "s#/proc/mtd#\$H3C_TEST_MTD#; s#/dev/\$mtd#\$H3C_TEST_ART#; s#/tmp/hwd-cal#$T/cal#; s#/dev/kmsg#$T/kmsg#; s#/lib/rt3000/fem.sh#$T/fem.sh#" "$CAL" > "$T/cal.sh"
runcal() { rm -rf "$T/cal"; : > "$T/kmsg"
	H3C_TEST_MTD="$T/mtd" H3C_TEST_ART="$T/$1" sh -c "boot_hook_add() { :; }; . $T/cal.sh; hwd_caldata"; }
ids() { echo "$(cat "$T/cal/fem" 2>/dev/null)/$(cat "$T/cal/board_id-2g" 2>/dev/null)/$(cat "$T/cal/board_id-5g" 2>/dev/null)"; }
runcal fem;     chk "FEM -> NX30 ids" "$(ids)" fem/0x10/0x60
chk "FEM caldata 5g size" "$(wc -c < "$T/cal/qcn6122-1.bin" | tr -d ' ')" 131072
runcal nofem;   chk "no FEM -> HW-B ids" "$(ids)" nofem/0x23/0x90
chk "no FEM kmsg" "$(grep -c 'HW-B board data' "$T/kmsg")" 1
runcal mixed;   chk "unknown -> no override" "$(ids)" unknown//

echo "board-2.bin (two entries per radio)"
for c in ipq5018 qcn6122; do
	{ cat "$PKG/board-2-$c.bin"; tail -c +21 "$PKG/board-2-$c-hwb.bin"; } > "$T/b2-$c"
	r=$(python3 - "$T/b2-$c" "$PKG/board-2-$c.bin" "$PKG/board-2-$c-hwb.bin" <<'PY'
import struct,sys
def boards(b):
    assert b.startswith(b"QCA-ATH11K-BOARD\0"); o=20; out=[]
    while o+8<=len(b):
        t,l=struct.unpack_from("<II",b,o); d=b[o+8:o+8+l]; o+=8+l+(-l%4)
        if t!=0: continue
        s=0; name=data=None
        while s+8<=len(d):
            t2,l2=struct.unpack_from("<II",d,s); v=d[s+8:s+8+l2]; s+=8+l2+(-l2%4)
            if t2==0: name=v.decode()
            if t2==1: data=v
        out.append((name,data))
    return out
m,d,b=[boards(open(f,"rb").read()) for f in sys.argv[1:]]
print(" ".join(n.split("=")[-1] for n,_ in m), "ok" if m==d+b else "MISMATCH")
PY
)
	case $c in ipq5018) want="16 35 ok";; qcn6122) want="96 144 ok";; esac
	chk "$c board ids + data" "$r" "$want"
done

echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
