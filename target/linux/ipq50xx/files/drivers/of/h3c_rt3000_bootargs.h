/* SPDX-License-Identifier: GPL-2.0 */
/* Explicit H3C A/B/C/D opt-in command-line storage contract; included only by drivers/of/fdt.c.
 * The caller supplies kernel string/errno helpers. No allocation or hardware IO.
 */
#ifndef _H3C_RT3000_BOOTARGS_H
#define _H3C_RT3000_BOOTARGS_H

static bool __init h3c_rt3000_storage_arg(const char *arg, size_t len)
{
	static const char * const keys[] = {
		"mtdparts", "ubi.mtd", "ubi.block", "root", "rootfstype",
		"rootflags", "rootwait", "rootdelay", "init", "rdinit", "ro", "rw",
	};
	size_t i, n;

	/* next_arg() also accepts a whole argument wrapped in double quotes. */
	if (len && *arg == '"') {
		arg++;
		len--;
	}
	for (i = 0; i < ARRAY_SIZE(keys); i++) {
		n = strlen(keys[i]);
		if (len >= n && !memcmp(arg, keys[i], n) &&
		    (len == n || arg[n] == '=' || (len == n + 1 && arg[n] == '"')))
			return true;
	}
	return false;
}

static int __init h3c_rt3000_filter_bootargs(char *output, size_t capacity,
					 const char *input, size_t len)
{
	const char *read = input, *start;
	char *write = output;
	size_t n, used = 0;
	bool quoted;

	/* DT strings must be one complete NUL-terminated value, not a list. */
	if (!input || !len || memchr(input, '\0', len) != input + len - 1)
		return -EINVAL;

	while (*read) {
		while (isspace((unsigned char)*read))
			read++;
		if (!*read)
			break;
		start = read;
		quoted = false;
		while (*read) {
			if (*read == '"')
				quoted = !quoted;
			if (!quoted && isspace((unsigned char)*read))
				break;
			read++;
		}
		if (quoted)
			return -EINVAL;
		n = read - start;
		if (h3c_rt3000_storage_arg(start, n))
			continue;
		if (used >= capacity || n >= capacity - used - (used != 0))
			return -E2BIG;
		if (used)
			*write++ = ' ';
		memmove(write, start, n);
		write += n;
		used = write - output;
	}
	if (used >= capacity)
		return -E2BIG;
	*write = '\0';
	return 0;
}

#define H3C_RT3000_SLOT_LOW	0x900000ULL
#define H3C_RT3000_SLOT_HIGH	0x3100000ULL
#define H3C_RT3000_SLOT_SIZE	0x2800000ULL
#define H3C_RT3000_SINGLE_SIZE	0x5000000ULL

/* Parse the one <key><number> U-Boot appended. Return false when it is
 * absent, repeated or not a number.
 */
static bool __init h3c_rt3000_cmdline_ull(const char *cmdline, const char *key,
					  unsigned long long *val)
{
	const char *p = cmdline, *start;
	size_t klen = strlen(key), n;
	char value[24];
	bool seen = false;

	while (*p) {
		while (isspace((unsigned char)*p))
			p++;
		start = p;
		while (*p && !isspace((unsigned char)*p))
			p++;
		n = p - start;
		if (n <= klen || memcmp(start, key, klen))
			continue;
		n -= klen;
		if (seen || n >= sizeof(value))
			return false;
		seen = true;
		memcpy(value, start + klen, n);
		value[n] = '\0';
		if (kstrtoull(value, 0, val))
			return false;
	}
	return seen;
}

/* Return the one h3c.boot_slot= offset U-Boot appended, or 0 when it is
 * absent, repeated or not one of the two rootfs extents.
 */
static unsigned long long __init h3c_rt3000_boot_slot(const char *cmdline)
{
	unsigned long long slot;

	if (!h3c_rt3000_cmdline_ull(cmdline, "h3c.boot_slot=", &slot))
		return 0;
	return slot == H3C_RT3000_SLOT_LOW || slot == H3C_RT3000_SLOT_HIGH ? slot : 0;
}

/* Return the one h3c.boot_size= U-Boot pre.4+ appended (size of the booted
 * rootfs extent), or 0 when it is absent, repeated or not a number.
 */
static unsigned long long __init h3c_rt3000_boot_size(const char *cmdline)
{
	unsigned long long size;

	return h3c_rt3000_cmdline_ull(cmdline, "h3c.boot_size=", &size) ? size : 0;
}

/* Label text after "@<offset>(" up to the next part separator, e.g. "rootfs)"
 * or "oem_rootfs)ro". The extent must appear exactly once.
 */
static const char * __init h3c_rt3000_slot_label(const char *map, const char *at,
						 size_t *len)
{
	const char *hit = strstr(map, at);

	if (!hit || strstr(hit + 1, at))
		return NULL;
	hit += strlen(at);
	*len = strcspn(hit, ", ");
	return hit;
}

static bool __init h3c_rt3000_label_is(const char *label, size_t len,
				       const char *name)
{
	size_t n = strlen(name);

	return len > n && !memcmp(label, name, n) && label[n] == ')';
}

static char h3c_rt3000_slot_storage[COMMAND_LINE_SIZE] __initdata;

/* The DT map names one physical extent rootfs and the other oem_rootfs (ro).
 * When U-Boot booted the oem_rootfs extent, swap the two labels with their
 * flags so Linux attaches and writes the slot it actually booted. Anything
 * unexpected keeps the fixed DT map.
 */
static const char * __init h3c_rt3000_select_slot(const char *storage, size_t len,
						  unsigned long long slot)
{
	const char *booted, *other, *first, *second;
	size_t booted_len, other_len, first_len, second_len;
	char *out = h3c_rt3000_slot_storage;

	if (!strstr(storage, "ubi.mtd=rootfs ") || !strstr(storage, "mtdparts="))
		return storage;
	booted = h3c_rt3000_slot_label(storage, slot == H3C_RT3000_SLOT_LOW ?
				       "@0x900000(" : "@0x3100000(", &booted_len);
	other = h3c_rt3000_slot_label(storage, slot == H3C_RT3000_SLOT_LOW ?
				      "@0x3100000(" : "@0x900000(", &other_len);
	if (booted && other && h3c_rt3000_label_is(booted, booted_len, "rootfs") &&
	    h3c_rt3000_label_is(other, other_len, "oem_rootfs"))
		return storage;
	if (!booted || !other || len > sizeof(h3c_rt3000_slot_storage) ||
	    !h3c_rt3000_label_is(booted, booted_len, "oem_rootfs") ||
	    !h3c_rt3000_label_is(other, other_len, "rootfs")) {
		pr_warn("H3C: cannot map booted slot 0x%llx, keeping DT rootfs\n", slot);
		return storage;
	}
	first = booted < other ? booted : other;
	first_len = booted < other ? booted_len : other_len;
	second = booted < other ? other : booted;
	second_len = booted < other ? other_len : booted_len;
	/* Same total length: prefix, second label, middle, first label, rest. */
	memcpy(out, storage, first - storage);
	out += first - storage;
	memcpy(out, second, second_len);
	out += second_len;
	memcpy(out, first + first_len, second - (first + first_len));
	out += second - (first + first_len);
	memcpy(out, first, first_len);
	out += first_len;
	memcpy(out, second + second_len, storage + len - (second + second_len));
	pr_info("H3C: booted rootfs slot 0x%llx\n", slot);
	return h3c_rt3000_slot_storage;
}

/* U-Boot's PTABLE "big partition" layout replaces both 40 MiB slots with one
 * 80 MiB rootfs at 0x900000. Rewrite the two adjacent DT slot entries (named
 * rootfs and oem_rootfs either way round) into that one writable rootfs and
 * update *len. Anything unexpected keeps the DT map.
 */
static const char * __init h3c_rt3000_single_slot(const char *storage, size_t *len)
{
	static const char low[] = "0x2800000@0x900000(";
	static const char high[] = ",0x2800000@0x3100000(";
	static const char single[] = "0x5000000@0x900000(rootfs)";
	const char *first, *second, *start, *end;
	size_t first_len, second_len, head, tail;
	char *out = h3c_rt3000_slot_storage;

	if (!strstr(storage, "ubi.mtd=rootfs ") || !strstr(storage, "mtdparts="))
		return storage;
	first = h3c_rt3000_slot_label(storage, "@0x900000(", &first_len);
	second = h3c_rt3000_slot_label(storage, "@0x3100000(", &second_len);
	if (!first || !second || (size_t)(first - storage) <= sizeof(low) - 1 ||
	    second != first + first_len + sizeof(high) - 1 ||
	    *len > sizeof(h3c_rt3000_slot_storage))
		goto keep;
	start = first - (sizeof(low) - 1);
	if ((start[-1] != ',' && start[-1] != ':') ||
	    memcmp(start, low, sizeof(low) - 1) ||
	    memcmp(first + first_len, high, sizeof(high) - 1))
		goto keep;
	if (!(h3c_rt3000_label_is(first, first_len, "rootfs") &&
	      h3c_rt3000_label_is(second, second_len, "oem_rootfs")) &&
	    !(h3c_rt3000_label_is(first, first_len, "oem_rootfs") &&
	      h3c_rt3000_label_is(second, second_len, "rootfs")))
		goto keep;
	end = second + second_len;
	head = start - storage;
	tail = storage + *len - end;
	memcpy(out, storage, head);
	memcpy(out + head, single, sizeof(single) - 1);
	memcpy(out + head + sizeof(single) - 1, end, tail);
	*len = head + sizeof(single) - 1 + tail;
	pr_info("H3C: single 80 MiB rootfs at 0x900000\n");
	return h3c_rt3000_slot_storage;
keep:
	pr_warn("H3C: cannot map single rootfs, keeping DT rootfs\n");
	return storage;
}

static int __init h3c_rt3000_storage_bootargs(char *cmdline, size_t capacity,
					  const char *storage, size_t len)
{
	unsigned long long slot, size;
	size_t used;
	int err;

	if (!storage || len < 2 || memchr(storage, '\0', len) != storage + len - 1)
		return -EINVAL;
	used = strnlen(cmdline, capacity);
	if (used == capacity)
		return -EINVAL;
	slot = h3c_rt3000_boot_slot(cmdline);
	size = h3c_rt3000_boot_size(cmdline);
	/* No size (U-Boot before pre.4) means the two-slot layout. */
	if (slot == H3C_RT3000_SLOT_LOW && size == H3C_RT3000_SINGLE_SIZE) {
		storage = h3c_rt3000_single_slot(storage, &len);
	} else {
		if (size && size != H3C_RT3000_SLOT_SIZE)
			pr_warn("H3C: unexpected h3c.boot_size 0x%llx, assuming two slots\n",
				size);
		if (slot)
			storage = h3c_rt3000_select_slot(storage, len, slot);
	}
	err = h3c_rt3000_filter_bootargs(cmdline, capacity, cmdline, used + 1);
	if (err)
		return err;
	used = strlen(cmdline);
	/* len includes NUL; refuse truncation instead of dropping root selectors. */
	if (used >= capacity || len > capacity - used - (used != 0))
		return -E2BIG;
	if (used)
		cmdline[used++] = ' ';
	memcpy(cmdline + used, storage, len);
	return 0;
}
#endif
