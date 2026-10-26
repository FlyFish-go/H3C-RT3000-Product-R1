#!/bin/sh
set -eu

repo=${1:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
fixture="$repo/scripts/tests/fixtures/package-metadata-mconf-depends.packageinfo"
output=$(mktemp)
trap 'rm -f "$output"' EXIT HUP INT TERM

perl -I"$repo/scripts" "$repo/scripts/package-metadata.pl" config "$fixture" > "$output"
python3 - "$output" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
parent = text.split("config PACKAGE_demo-parent\n", 1)[1].split("\n\t\t\thelp", 1)[0]
option = text.split("config PACKAGE_demo_parent_conntrack\n", 1)[1].split("\n\tendif", 1)[0]

assert "depends on PACKAGE_ppp-module" in option, option
assert "PACKAGE_demo_parent_conntrack) || PACKAGE_ppp-module" not in parent, parent
assert "select PACKAGE_tc-tiny if PACKAGE_tc-full<PACKAGE_demo-parent" in parent, parent
assert "PACKAGE_tc-full<PACKAGE_demo-parent" not in "\n".join(
    line for line in parent.splitlines() if line.lstrip().startswith("depends on")
), parent
print("package-metadata mconf dependency fixture: PASS")
PY
