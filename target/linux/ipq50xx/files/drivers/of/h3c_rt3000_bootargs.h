/* SPDX-License-Identifier: GPL-2.0 */
/* HW-B opt-in command-line storage contract; included only by drivers/of/fdt.c.
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

static int __init h3c_rt3000_storage_bootargs(char *cmdline, size_t capacity,
					  const char *storage, size_t len)
{
	size_t used;
	int err;

	if (!storage || len < 2 || memchr(storage, '\0', len) != storage + len - 1)
		return -EINVAL;
	used = strnlen(cmdline, capacity);
	if (used == capacity)
		return -EINVAL;
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
