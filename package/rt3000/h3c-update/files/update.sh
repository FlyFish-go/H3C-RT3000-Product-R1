#!/bin/sh
# H3C Magic firmware update: check, download and install new releases.
#
# The release manifest (update.json + usign signature) is published twice:
#   GitHub Pages  https://flyfish-go.github.io/<repo>/update/
#   Gitee         https://gitee.com/FlyFish-go/<repo>/raw/update/
# A check fetches both at the same time, drops anything whose signature does
# not verify against /etc/h3c-update/keys, and keeps the manifest with the
# highest serial (the faster source wins a tie). So whichever site this
# network reaches is used, and a mirror that lags behind cannot hide a newer
# release.
#
# The release line, release name and hardware group come from
# /etc/h3c-update/build, written at build time. The hardware group is never
# probed at run time: one PCB can run more than one image (no-FEM HW-D runs
# HW-B), and the update must follow the image, not the board.
#
# Nothing here writes to flash. Work files live in /tmp/h3c-update; only
# sysupgrade itself writes the running system slot.

. /usr/share/libubox/jshn.sh

BUILD=/etc/h3c-update/build
KEYS=/etc/h3c-update/keys
RUN=/tmp/h3c-update
FW=$RUN/firmware.bin
SELF=/usr/libexec/h3c-update/update.sh

H3C_LINE= H3C_REPO= H3C_RELEASE= H3C_GROUP=
[ -r "$BUILD" ] && . "$BUILD"
mkdir -p "$RUN"

now() { date +%s; }
uptime_ms() { awk '{ printf "%d\n", $1 * 1000 }' /proc/uptime; }
cfg() { local v; v=$(uci -q get "h3c_update.main.$1") && [ -n "$v" ] && echo "$v" || echo "$2"; }
mf() { jsonfilter -i "$1" -e "$2" 2>/dev/null; }
log() { logger -t h3c-update "$*"; }

group() {
	if [ -n "$H3C_GROUP" ]; then
		echo "$H3C_GROUP"
		return
	fi
	# The NSS build makes every board image in one run, so the group comes
	# from the image's own device tree: each NSS image carries exactly one.
	[ "$H3C_LINE" = nss ] || return 0
	case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in
	h3c,magic-rc3000-v1) echo HW-B ;;
	esac
}

# Version order: rN for the QSDK line, vX.Y.Z[-pre.N] for the NSS line.
# Unknown formats give an empty key and never count as newer.
vkey() {
	echo "$1" | awk '{
		if ($0 ~ /^r[0-9]+$/) { printf "r%06d\n", substr($0, 2); exit }
		s = $0; pre = -1
		if (s !~ /^v[0-9]+\.[0-9]+\.[0-9]+(-pre\.[0-9]+)?$/) exit
		sub(/^v/, "", s)
		if (match(s, /-pre\.[0-9]+$/)) { pre = substr(s, RSTART + 5) + 0; s = substr(s, 1, RSTART - 1) }
		split(s, a, ".")
		printf "v%04d%04d%04d%s\n", a[1], a[2], a[3], (pre < 0 ? "10000" : sprintf("0%04d", pre))
	}'
}

# newer A B: A is a later release than B
newer() {
	local a b
	a=$(vkey "$1"); b=$(vkey "$2")
	[ -n "$a" ] && [ -n "$b" ] && [ "${a%%[0-9]*}" = "${b%%[0-9]*}" ] || return 1
	awk -v a="$a" -v b="$b" 'BEGIN { exit !(a > b) }'
}

sources() {
	case "$(cfg source auto)" in
	github) echo github ;;
	gitee) echo gitee ;;
	*) echo github gitee ;;
	esac
}

# base URL of the manifest directory for one source
src_base() {
	local t
	t=$(cfg test_base "")
	if [ -n "$t" ]; then
		echo "$t/$1"
		return
	fi
	case "$1" in
	github) echo "https://flyfish-go.github.io/$H3C_REPO/update" ;;
	gitee) echo "https://gitee.com/FlyFish-go/$H3C_REPO/raw/update" ;;
	esac
}

manifest_ok() {
	[ "$(mf "$1" @.schema)" = 1 ] || return 1
	[ "$(mf "$1" @.line)" = "$H3C_LINE" ] || return 1
	case "$(mf "$1" @.serial)" in '' | *[!0-9]*) return 1 ;; esac
	[ -n "$(mf "$1" @.version)" ] || return 1
}

# verify DIR: DIR/m.json signed by DIR/m.sig and well formed -> result word
verify_dir() {
	if ! usign -V -q -P "$KEYS" -m "$1/m.json" -x "$1/m.sig" >>"$1/log" 2>&1; then
		echo signature
	elif ! manifest_ok "$1/m.json"; then
		echo manifest
	else
		echo ok
	fi
}

fetch_src() {
	local d=$RUN/src.$1 b t0
	b=$(src_base "$1")
	rm -rf "$d"
	mkdir -p "$d"
	t0=$(uptime_ms)
	if uclient-fetch -q -T 15 -O "$d/m.json" "$b/update.json?t=$t0" >"$d/log" 2>&1 &&
	   uclient-fetch -q -T 15 -O "$d/m.sig" "$b/update.json.sig?t=$t0" >>"$d/log" 2>&1; then
		verify_dir "$d" >"$d/result"
	else
		echo fetch >"$d/result"
	fi
	echo $(($(uptime_ms) - t0)) >"$d/ms"
}

# adopt DIR SOURCE: make DIR's manifest the current one
adopt() {
	cp "$1/m.json" "$RUN/manifest.json.new" &&
	cp "$1/m.sig" "$RUN/manifest.sig.new" &&
	mv "$RUN/manifest.sig.new" "$RUN/manifest.sig" &&
	mv "$RUN/manifest.json.new" "$RUN/manifest.json" &&
	echo "$2" >"$RUN/manifest.src"
}

manifest_valid() {
	[ -s "$RUN/manifest.json" ] && [ -s "$RUN/manifest.sig" ] &&
	usign -V -q -P "$KEYS" -m "$RUN/manifest.json" -x "$RUN/manifest.sig" >/dev/null 2>&1 &&
	manifest_ok "$RUN/manifest.json"
}

do_check() { # mode
	local s best= bs=-1 bms=0 serial ms ok=0 srcs
	srcs=$(sources)
	rm -rf "$RUN"/src.*
	for s in $srcs; do
		fetch_src "$s" &
	done
	wait
	for s in $srcs; do
		[ "$(cat "$RUN/src.$s/result" 2>/dev/null)" = ok ] || continue
		serial=$(mf "$RUN/src.$s/m.json" @.serial)
		ms=$(cat "$RUN/src.$s/ms")
		if [ "$serial" -gt "$bs" ] || { [ "$serial" -eq "$bs" ] && [ "$ms" -lt "$bms" ]; }; then
			best=$s bs=$serial bms=$ms
		fi
	done
	[ -n "$best" ] && adopt "$RUN/src.$best" "$best" && ok=1

	json_init
	json_add_int checked "$(now)"
	json_add_string mode "$1"
	json_add_boolean ok "$ok"
	json_add_object sources
	for s in $srcs; do
		json_add_object "$s"
		json_add_string result "$(cat "$RUN/src.$s/result" 2>/dev/null)"
		json_add_int ms "$(cat "$RUN/src.$s/ms" 2>/dev/null || echo 0)"
		json_close_object
	done
	json_close_object
	json_dump >"$RUN/last.json.new" && mv "$RUN/last.json.new" "$RUN/last.json"

	if [ "$ok" = 1 ]; then
		local v
		v=$(mf "$RUN/manifest.json" @.version)
		newer "$v" "$H3C_RELEASE" && log "new firmware $v is available (current $H3C_RELEASE, via $best)"
	else
		log "update check failed ($srcs unreachable or invalid)"
	fi
	[ "$ok" = 1 ]
}

# Manifest fetched by the browser: stdin = {"source":..,"json":..,"sig":..}
do_verify() {
	local input src d r serial cur
	input=$(cat)
	src=$(jsonfilter -s "$input" -e @.source 2>/dev/null)
	case "$src" in github | gitee) ;; *) echo '{"result":"manifest"}'; return ;; esac
	d=$RUN/browser.$src
	rm -rf "$d"
	mkdir -p "$d"
	printf '%s' "$(jsonfilter -s "$input" -e @.json 2>/dev/null)" >"$d/m.json"
	printf '%s\n' "$(jsonfilter -s "$input" -e @.sig 2>/dev/null)" >"$d/m.sig"
	r=$(verify_dir "$d")
	json_init
	json_add_string result "$r"
	if [ "$r" = ok ]; then
		serial=$(mf "$d/m.json" @.serial)
		cur=-1
		manifest_valid && cur=$(mf "$RUN/manifest.json" @.serial)
		[ "$serial" -ge "$cur" ] && adopt "$d" "$src-browser"
		json_add_int serial "$serial"
		json_add_string version "$(mf "$d/m.json" @.version)"
	fi
	json_dump
}

dl_state() { # state [error]
	json_init
	json_add_string state "$1"
	json_add_string error "$2"
	json_add_string source "$DL_SRC"
	json_dump >"$RUN/download.json.new" && mv "$RUN/download.json.new" "$RUN/download.json"
}

dl_fail() {
	rm -f "$FW" "$FW.part"
	dl_state error "$1"
	log "download failed: $1"
	exit 1
}

image_field() { mf "$RUN/manifest.json" "@.images['$(group)'].$1"; }

image_ok() { # file
	local size sha
	size=$(image_field size)
	sha=$(image_field sha256)
	[ -s "$1" ] && [ "$(wc -c <"$1")" = "$size" ] &&
	[ "$(sha256sum "$1" | cut -d' ' -f1)" = "$sha" ]
}

url_ok() { # source url
	local t
	t=$(cfg test_base "")
	if [ -n "$t" ]; then
		case "$2" in "$t"/*) return 0 ;; esac
		return 1
	fi
	case "$1:$2" in
	github:https://github.com/FlyFish-go/*) return 0 ;;
	gitee:https://gitee.com/FlyFish-go/*) return 0 ;;
	esac
	return 1
}

do_download() {
	local file size avail need first s url order
	DL_SRC=
	dl_state downloading
	manifest_valid || dl_fail "no valid manifest, check again"
	[ -n "$(group)" ] || dl_fail "hardware group not supported"
	newer "$(mf "$RUN/manifest.json" @.version)" "$H3C_RELEASE" || dl_fail "no newer firmware"
	file=$(image_field file)
	size=$(image_field size)
	case "$file" in '' | */* | *[!A-Za-z0-9._-]*) dl_fail "no image for $(group)" ;; esac
	case "$size" in '' | *[!0-9]*) dl_fail "bad image size" ;; esac
	[ -n "$(image_field sha256)" ] || dl_fail "no checksum"

	# The image is held in RAM (tmpfs) until sysupgrade writes it.
	rm -f "$FW" "$FW.part"
	sync
	echo 1 2>/dev/null >/proc/sys/vm/drop_caches
	avail=$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)
	need=$((size / 1024 + 12288))
	[ "${avail:-0}" -ge "$need" ] ||
		dl_fail "not enough free memory (${avail} KiB free, ${need} KiB needed); stop memory-heavy services or upgrade manually"

	first=$(sed 's/-browser$//' "$RUN/manifest.src" 2>/dev/null)
	case "$(cfg source auto)" in
	github) order=github ;;
	gitee) order=gitee ;;
	*) [ "$first" = gitee ] && order="gitee github" || order="github gitee" ;;
	esac
	for s in $order; do
		url=$(mf "$RUN/manifest.json" "@.mirrors.$s")$file
		url_ok "$s" "$url" || continue
		DL_SRC=$s
		dl_state downloading
		rm -f "$FW.part"
		uclient-fetch -q -T 30 -O "$FW.part" "$url" >"$RUN/download.log" 2>&1 &
		echo $! >"$RUN/fetch.pid"
		wait $! && image_ok "$FW.part" && break
		rm -f "$FW.part"
	done
	[ -s "$FW.part" ] || dl_fail "download failed or checksum mismatch"
	mv "$FW.part" "$FW"
	sysupgrade -T "$FW" >"$RUN/test.log" 2>&1 || dl_fail "image rejected by sysupgrade: $(tail -n 1 "$RUN/test.log")"
	dl_state ready
	log "downloaded and verified $file via $DL_SRC"
}

do_install() { # keep(1/0)
	local opt= err=
	if ! manifest_valid || ! image_ok "$FW"; then
		err="no verified image, download again"
	elif ! sysupgrade -T "$FW" >"$RUN/test.log" 2>&1; then
		err="image rejected by sysupgrade"
	else
		[ "$1" = 1 ] || opt=-n
		DL_SRC=$(jsonfilter -i "$RUN/download.json" -e @.source 2>/dev/null)
		dl_state installing
		log "installing $(mf "$RUN/manifest.json" @.version) (keep settings: $1)"
		# detach so that this rpc call returns before the system goes down
		(sleep 2; exec /sbin/sysupgrade $opt "$FW") </dev/null >"$RUN/sysupgrade.log" 2>&1 &
	fi
	json_init
	if [ -n "$err" ]; then
		json_add_string error "$err"
	else
		json_add_boolean ok 1
	fi
	json_dump
}

job_pid() {
	local p
	p=$(cat "$RUN/job.pid" 2>/dev/null) || return 1
	[ -n "$p" ] && grep -qs h3c-update "/proc/$p/cmdline" && echo "$p"
}

do_start() { # job args...
	local busy=0
	if job_pid >/dev/null; then
		busy=1
	else
		echo "$1" >"$RUN/job.type"
		[ "$1" = download ] && { DL_SRC=; dl_state downloading; }
		"$SELF" run "$@" </dev/null >/dev/null 2>&1 &
		echo $! >"$RUN/job.pid"
	fi
	json_init
	if [ "$busy" = 1 ]; then
		json_add_string error busy
	else
		json_add_boolean started 1
	fi
	json_dump
}

do_cancel() {
	local p
	p=$(job_pid) && kill -TERM "$p" 2>/dev/null
	p=$(cat "$RUN/fetch.pid" 2>/dev/null) && grep -qs uclient "/proc/$p/cmdline" && kill -TERM "$p"
	sleep 1
	rm -f "$FW.part" "$RUN/job.pid" "$RUN/fetch.pid"
	[ -f "$FW" ] && dl_state ready || dl_state idle
	echo '{"ok":true}'
}

do_tick() {
	local iv last t
	[ "$(cfg auto 0)" = 1 ] || return 0
	[ -n "$(group)" ] || return 0
	t=$(now)
	[ "$t" -gt 1767225600 ] || return 0 # clock not set yet, HTTPS would fail
	iv=$(cfg interval 12)
	case "$iv" in '' | *[!0-9]*) iv=12 ;; esac
	[ "$iv" -lt 1 ] && iv=1
	[ "$iv" -gt 168 ] && iv=168
	last=$(cat "$RUN/last_auto" 2>/dev/null || echo 0)
	[ $((t - last)) -ge $((iv * 3600 - 600)) ] || return 0
	job_pid >/dev/null && return 0
	echo "$t" >"$RUN/last_auto"
	echo check >"$RUN/job.type"
	echo $$ >"$RUN/job.pid"
	# on failure try again in about an hour instead of a full interval
	do_check auto || echo $((t - iv * 3600 + 3600)) >"$RUN/last_auto"
	rm -f "$RUN/job.pid"
}

do_status() {
	local g v job= dlf bytes=0 cur_serial
	g=$(group)
	job_pid >/dev/null && job=$(cat "$RUN/job.type" 2>/dev/null)

	json_init
	json_add_string line "$H3C_LINE"
	json_add_string repo "$H3C_REPO"
	json_add_string release "$H3C_RELEASE"
	json_add_string group "$g"
	json_add_string board "$(cat /tmp/sysinfo/board_name 2>/dev/null)"
	json_add_string job "$job"
	json_add_object config
	json_add_string auto "$(cfg auto 0)"
	json_add_string interval "$(cfg interval 12)"
	json_add_string source "$(cfg source auto)"
	json_add_string test_base "$(cfg test_base "")"
	json_close_object
	json_add_int mem_available "$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
	if manifest_valid; then
		v=$(mf "$RUN/manifest.json" @.version)
		json_add_object latest
		json_add_string source "$(cat "$RUN/manifest.src")"
		json_add_string version "$v"
		json_add_int serial "$(mf "$RUN/manifest.json" @.serial)"
		json_add_string date "$(mf "$RUN/manifest.json" @.date)"
		json_add_string summary_zh "$(mf "$RUN/manifest.json" @.summary_zh)"
		json_add_string summary_en "$(mf "$RUN/manifest.json" @.summary_en)"
		json_add_string release_github "$(mf "$RUN/manifest.json" @.release.github)"
		json_add_string release_gitee "$(mf "$RUN/manifest.json" @.release.gitee)"
		json_add_boolean newer "$(newer "$v" "$H3C_RELEASE" && echo 1 || echo 0)"
		if [ -n "$g" ]; then
			json_add_string file "$(image_field file)"
			json_add_int size "$(image_field size)"
			json_add_string sha256 "$(image_field sha256)"
		fi
		# keep_min: oldest release whose settings the new one still accepts
		local km
		km=$(mf "$RUN/manifest.json" @.keep_min)
		json_add_string keep_min "$km"
		json_add_boolean keep "$([ -z "$km" ] || ! newer "$km" "$H3C_RELEASE" && echo 1 || echo 0)"
		json_close_object
	fi
	json_add_object download
	dlf=$RUN/download.json
	if [ -s "$dlf" ]; then
		json_add_string state "$(jsonfilter -i "$dlf" -e @.state)"
		json_add_string error "$(jsonfilter -i "$dlf" -e @.error)"
		json_add_string source "$(jsonfilter -i "$dlf" -e @.source)"
	else
		json_add_string state idle
	fi
	[ -f "$FW.part" ] && bytes=$(wc -c <"$FW.part")
	[ -f "$FW" ] && bytes=$(wc -c <"$FW")
	json_add_int bytes "$bytes"
	json_close_object
	json_dump | sed 's/}$//' | tr -d '\n'
	# last check record is already JSON
	if [ -s "$RUN/last.json" ]; then
		printf ', "last": '
		cat "$RUN/last.json"
	fi
	echo ' }'
}

case "$1" in
status) do_status ;;
start) shift; do_start "$@" ;;
run)
	shift
	trap 'rm -f "$RUN/job.pid"' EXIT
	case "$1" in
	check) do_check "${2:-manual}" ;;
	download) do_download ;;
	esac
	;;
check) do_check "${2:-manual}" ;;
verify) do_verify ;;
cancel) do_cancel ;;
install) do_install "${2:-1}" ;;
tick) do_tick ;;
*)
	echo "usage: $0 status|check|tick|cancel|install <keep 1|0>" >&2
	exit 1
	;;
esac
