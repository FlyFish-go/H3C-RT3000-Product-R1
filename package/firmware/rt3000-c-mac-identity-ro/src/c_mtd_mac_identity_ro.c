#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <unistd.h>

#define ENV_LABEL        "0:APPSBLENV"
#define ENV_OFFSET       0x00480000ULL
#define ENV_SIZE         0x00080000ULL
#define ENV_ERASE_SIZE   0x00020000U
#define ENV_PAGE_SIZE    2048U
#define ENV_OOB_SIZE     64U
#define ENV_ECC_STRENGTH 4U
#define MTD_MAJOR        90U
#define C_EXPECTED_MTD_COUNT 21U
#define NATIVE_MODEL     "H3C Magic RT3000 (RTL8367S, persistent C native profile)"
#define C_COMPAT         "h3c,rt3000-rtl8367s"

struct mtd_row {
	unsigned int index;
	uint64_t proc_size;
	uint64_t proc_erase;
	char name[64];
};

struct geometry {
	uint64_t offset;
	uint64_t size;
	uint32_t erasesize;
	uint32_t writesize;
	uint32_t oobsize;
	uint32_t ecc_strength;
	uint32_t flags;
};

static int valid_mac(const char *s)
{
	unsigned int b[6];
	unsigned int i;
	static const char *const placeholders[] = {
		"00:11:22:33:44:55", "00:11:22:33:44:56"
	};
	char lower[18];

	if (!s || strlen(s) != 17)
		return 0;
	for (i = 0; i < 6; i++) {
		char pair[3];
		char *end;
		unsigned long v;

		pair[0] = s[i * 3];
		pair[1] = s[i * 3 + 1];
		pair[2] = '\0';
		if (!((pair[0] >= '0' && pair[0] <= '9') ||
		      (pair[0] >= 'a' && pair[0] <= 'f') ||
		      (pair[0] >= 'A' && pair[0] <= 'F')) ||
		    !((pair[1] >= '0' && pair[1] <= '9') ||
		      (pair[1] >= 'a' && pair[1] <= 'f') ||
		      (pair[1] >= 'A' && pair[1] <= 'F')))
			return 0;
		if (i < 5 && s[i * 3 + 2] != ':')
			return 0;
		errno = 0;
		v = strtoul(pair, &end, 16);
		if (errno || *end)
			return 0;
		b[i] = (unsigned int)v;
	}
	if ((b[0] & 1U) || (b[0] == 0 && b[1] == 0 && b[2] == 0 &&
			 b[3] == 0 && b[4] == 0 && b[5] == 0) ||
	    (b[0] == 255 && b[1] == 255 && b[2] == 255 &&
		     b[3] == 255 && b[4] == 255 && b[5] == 255))
		return 0;
	for (i = 0; i < 17; i++) {
		char c = s[i];
		lower[i] = (c >= 'A' && c <= 'F') ? (char)(c - 'A' + 'a') : c;
	}
	lower[17] = '\0';
	for (i = 0; i < sizeof(placeholders) / sizeof(placeholders[0]); i++)
		if (strcmp(lower, placeholders[i]) == 0)
			return 0;
	return 1;
}

static int parse_ethaddr_page(const unsigned char *page, size_t len, char out[18])
{
	static const char key[] = "ethaddr=";
	size_t pos = 0;
	unsigned int found = 0;
	char candidate[18];

	if (!page || !out || len != ENV_PAGE_SIZE)
		return -1;
	while (pos < len) {
		size_t start = pos;
		size_t token_len;

		while (pos < len && page[pos] != '\0' && page[pos] != '\n')
			pos++;
		token_len = pos - start;
		if (token_len >= sizeof(key) - 1 &&
		    memcmp(page + start, key, sizeof(key) - 1) == 0) {
			if (++found != 1 || token_len != (sizeof(key) - 1) + 17)
				return -1;
			memcpy(candidate, page + start + sizeof(key) - 1, 17);
			candidate[17] = '\0';
			if (!valid_mac(candidate))
				return -1;
		}
		if (pos == len) {
			/* A possible key/value cut at the page edge is ambiguous. */
			if (token_len >= 6 && memcmp(page + start, "ethaddr", 6) == 0)
				return -1;
			break;
		}
		pos++;
	}
	if (found != 1)
		return -1;
	memcpy(out, candidate, sizeof(candidate));
	return 0;
}

static int range_and_label_ok(uint64_t offset, uint64_t size,
			      const char *name, uint64_t proc_size,
			      uint64_t proc_erase)
{
	return offset == ENV_OFFSET && size == ENV_SIZE &&
	       proc_size == ENV_SIZE && proc_erase == ENV_ERASE_SIZE &&
	       name && strcmp(name, ENV_LABEL) == 0;
}

static int unique_mapping_ok(unsigned int label_matches, unsigned int range_matches)
{
	return label_matches == 1 && range_matches == 1;
}

/* 21 rows with the two 40 MiB system slots; 20 when U-Boot's PTABLE single
 * layout gives one 80 MiB rootfs (kernel patch 429 validated the rest).
 */
static int physical_map_count_ok(unsigned int entry_count)
{
	return entry_count == C_EXPECTED_MTD_COUNT ||
	       entry_count == C_EXPECTED_MTD_COUNT - 1U;
}

static int geometry_ok(const struct geometry *g)
{
	return g && g->offset == ENV_OFFSET && g->size == ENV_SIZE &&
	       g->erasesize == ENV_ERASE_SIZE &&
	       g->writesize == ENV_PAGE_SIZE &&
	       g->oobsize == ENV_OOB_SIZE &&
	       g->ecc_strength == ENV_ECC_STRENGTH && g->flags == 0;
}

static int node_identity_ok(unsigned int maj, unsigned int min,
			    unsigned int mtd_index)
{
	return maj == MTD_MAJOR && min == 2U * mtd_index + 1U;
}

static int blob_has_token(const unsigned char *p, size_t n, const char *token)
{
	size_t pos = 0, wanted = strlen(token);
	if (!p || !token)
		return 0;
	while (pos < n) {
		size_t start = pos;
		while (pos < n && p[pos] != '\0')
			pos++;
		if (pos - start == wanted && memcmp(p + start, token, wanted) == 0)
			return 1;
		pos++;
	}
	return 0;
}

static int native_platform_ok(const unsigned char *compat, size_t compat_len,
			      const unsigned char *model, size_t model_len)
{
	static const char expected[] = NATIVE_MODEL;
	if (!blob_has_token(compat, compat_len, C_COMPAT))
		return 0;
	if (!model || model_len != sizeof(expected) ||
	    memcmp(model, expected, sizeof(expected)) != 0)
		return 0;
	return 1;
}

static int read_text_u64(const char *path, int base, uint64_t *value)
{
	char buf[64], *end;
	unsigned long long v;
	FILE *f = fopen(path, "re");
	if (!f)
		return -1;
	if (!fgets(buf, sizeof(buf), f)) {
		fclose(f);
		return -1;
	}
	fclose(f);
	errno = 0;
	v = strtoull(buf, &end, base);
	if (errno || end == buf)
		return -1;
	while (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')
		end++;
	if (*end)
		return -1;
	*value = (uint64_t)v;
	return 0;
}

static int read_attr(unsigned int index, const char *attr, uint64_t *value)
{
	char path[160];
	if (snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/%s", index, attr) >=
	    (int)sizeof(path))
		return -1;
	return read_text_u64(path, 0, value);
}

static int read_platform_property(const char *name, unsigned char *buf,
				 size_t cap, size_t *len)
{
	char path[128];
	int fd;
	ssize_t n;
	if (snprintf(path, sizeof(path), "/proc/device-tree/%s", name) >=
	    (int)sizeof(path))
		return -1;
	fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return -1;
	n = read(fd, buf, cap);
	close(fd);
	if (n <= 0 || (size_t)n == cap)
		return -1;
	*len = (size_t)n;
	return 0;
}

static int native_platform_from_tree(void)
{
	unsigned char compat[512], model[160];
	size_t compat_len, model_len;
	if (read_platform_property("compatible", compat, sizeof(compat), &compat_len) ||
	    read_platform_property("model", model, sizeof(model), &model_len))
		return 0;
	return native_platform_ok(compat, compat_len, model, model_len);
}

static int parse_proc_row(const char *line, struct mtd_row *row)
{
	int used = 0;
	unsigned int index;
	unsigned int size, erase;
	char name[64];
	if (sscanf(line, "mtd%u: %x %x \"%63[^\"]\"%n",
		   &index, &size, &erase, name, &used) != 4)
		return 0;
	while (line[used] == ' ' || line[used] == '\t' ||
	       line[used] == '\r' || line[used] == '\n')
		used++;
	if (line[used] != '\0')
		return 0;
	row->index = index;
	row->proc_size = size;
	row->proc_erase = erase;
	memcpy(row->name, name, strlen(name) + 1);
	return 1;
}

static int find_env_mtd(unsigned int *index_out)
{
	FILE *f;
	char *line = NULL;
	size_t cap = 0;
	ssize_t n;
	unsigned int labels = 0, ranges = 0, chosen = 0, entries = 0;
	unsigned char seen[C_EXPECTED_MTD_COUNT] = { 0 };

	f = fopen("/proc/mtd", "re");
	if (!f)
		return -1;
	while ((n = getline(&line, &cap, f)) >= 0) {
		struct mtd_row row;
		uint64_t off, size;
		int label_match;
		(void)n;
		if (!parse_proc_row(line, &row)) {
			if (strncmp(line, "mtd", 3) == 0) {
				free(line);
				fclose(f);
				return -1;
			}
			continue;
		}
		if (row.index >= C_EXPECTED_MTD_COUNT || seen[row.index]) {
			free(line);
			fclose(f);
			return -1;
		}
		seen[row.index] = 1;
		entries++;
		label_match = strcmp(row.name, ENV_LABEL) == 0;
		if (label_match)
			labels++;
		if (read_attr(row.index, "offset", &off) ||
		    read_attr(row.index, "size", &size)) {
			free(line);
			fclose(f);
			return -1;
		}
		if (off == ENV_OFFSET && size == ENV_SIZE) {
			ranges++;
			if (!range_and_label_ok(off, size, row.name,
						row.proc_size, row.proc_erase)) {
				free(line);
				fclose(f);
				return -1;
			}
			chosen = row.index;
		}
	}
	free(line);
	fclose(f);
	if (!unique_mapping_ok(labels, ranges) || !physical_map_count_ok(entries))
		return -1;
	*index_out = chosen;
	return 0;
}

static int read_ecc_strength(unsigned int index, uint32_t *out)
{
	uint64_t value;
	if (read_attr(index, "ecc_strength", &value) || value > UINT32_MAX)
		return -1;
	*out = (uint32_t)value;
	return 0;
}

static int read_env_mac(char out[18])
{
	unsigned int index;
	char path[64];
	struct stat st;
	struct mtd_info_user info;
	struct geometry g;
	unsigned char page[ENV_PAGE_SIZE];
	int fd = -1;
	size_t got = 0;
	uint64_t offset, size, erasesize, writesize, oobsize;
	uint32_t ecc_strength;

	if (!native_platform_from_tree() || find_env_mtd(&index))
		return -1;
	if (read_attr(index, "offset", &offset) || read_attr(index, "size", &size) ||
	    read_attr(index, "erasesize", &erasesize) ||
	    read_attr(index, "writesize", &writesize) ||
	    read_attr(index, "oobsize", &oobsize) ||
	    read_ecc_strength(index, &ecc_strength) ||
	    offset != ENV_OFFSET || size != ENV_SIZE ||
	    erasesize != ENV_ERASE_SIZE || writesize != ENV_PAGE_SIZE ||
	    oobsize != ENV_OOB_SIZE || ecc_strength != ENV_ECC_STRENGTH)
		return -1;
	if (snprintf(path, sizeof(path), "/dev/mtd%uro", index) >= (int)sizeof(path))
		return -1;
	fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode) ||
	    !node_identity_ok(major(st.st_rdev), minor(st.st_rdev), index) ||
	    ioctl(fd, MEMGETINFO, &info))
		goto fail;
	g.offset = offset;
	g.size = info.size;
	g.erasesize = info.erasesize;
	g.writesize = info.writesize;
	g.oobsize = info.oobsize;
	g.ecc_strength = ecc_strength;
	g.flags = info.flags;
	if (!geometry_ok(&g) || lseek(fd, 0, SEEK_SET) != 0)
		goto fail;
	while (got < sizeof(page)) {
		ssize_t r = read(fd, page + got, sizeof(page) - got);
		if (r < 0 && errno == EINTR)
			continue;
		if (r <= 0)
			goto fail;
		got += (size_t)r;
	}
	if (parse_ethaddr_page(page, sizeof(page), out))
		goto fail;
	close(fd);
	return 0;
fail:
	if (fd >= 0)
		close(fd);
	return -1;
}

#ifndef C_MTD_MAC_IDENTITY_NO_MAIN
int main(void)
{
	char mac[18];
	if (read_env_mac(mac)) {
		fputs("C factory MAC unavailable\n", stderr);
		return 1;
	}
	puts(mac);
	return 0;
}
#endif
