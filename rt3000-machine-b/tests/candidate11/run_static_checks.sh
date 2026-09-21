#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
tool="$root/rt3000-machine-b/tools/build_candidate11_oem_schema_lift.py"
body="$root/rt3000-machine-b/bdf/oem-bdwlan-b90-body.bin"
baseline="$root/package/firmware/ipq-wifi/board-h3c_rt3000.qcn6122"
artifact="${CANDIDATE11_ARTIFACT_DIR:-$root/../artifacts/machine-b/rc1-wifi5-perf-001/candidate11-oem-schema-lift}"
out="$artifact/board-h3c_rt3000-candidate11.qcn6122"
mkdir -p "$artifact"

test "$(sha256sum "$body" | awk '{print $1}')" = fec06dc5cfad170fdc4f463031cf9743cb188e2fe62991de5a9dc973d5459960
python3 "$tool" "$body" "$baseline" "$out"
test "$(sha256sum "$out" | awk '{print $1}')" = e5bd210bfb572ceae15eb132fc5f9950578f171268e5230bed026dbb539c73e3

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$body" "$tmp/tampered.bin" <<'PY'
from pathlib import Path
import sys
b = bytearray(Path(sys.argv[1]).read_bytes())
b[0x100] ^= 1
Path(sys.argv[2]).write_bytes(b)
PY
if python3 "$tool" "$tmp/tampered.bin" "$baseline" "$tmp/should-not-exist" >/dev/null 2>&1; then
    echo 'tampered input was not rejected' >&2
    exit 1
fi

"$root/rt3000-machine-b/tests/candidate10/run_static_checks.sh"
printf '%s\n' 'candidate11 static source/BDF checks: PASS'
