#!/bin/sh
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

${CC:-cc} -std=c99 -Wall -Wextra -Werror -O2 \
	"$repo/scripts/tests/rt3000-c-switch-offload-mock.c" \
	-o "$tmp/mock"
"$tmp/mock"
