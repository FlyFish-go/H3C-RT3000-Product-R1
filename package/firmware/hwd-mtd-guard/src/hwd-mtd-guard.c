/*
 * Read-only bad-block gate for the exact HW-D resistor-repair NAND layout.
 * It performs MEMGETINFO followed by MEMGETBADBLOCK at every eraseblock.
 * No erase, write, markbad, OOB, or BBT-management ioctl is issued.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <unistd.h>

struct allowed_mtd {
	unsigned int index;
	const char *name;
	uint64_t offset;
	uint64_t size;
};

static const struct allowed_mtd allowed[] = {
	{2, "0:BOOTCONFIG", 0x00100000, 0x00040000},
	{3, "0:BOOTCONFIG1", 0x00140000, 0x00040000},
	{15, "rootfs", 0x00900000, 0x02800000},
	{16, "oem_rootfs", 0x03100000, 0x02800000},
};

static const struct allowed_mtd *target_for_index(unsigned int index)
{
	size_t i;
	for (i = 0; i < sizeof(allowed) / sizeof(allowed[0]); i++)
		if (allowed[i].index == index)
			return &allowed[i];
	return NULL;
}

static int read_sysfs(const char *path, char *buf, size_t cap)
{
	int fd;
	ssize_t n;

	if (!cap)
		return -1;
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	n = read(fd, buf, cap - 1);
	if (n < 0) {
		close(fd);
		return -1;
	}
	if ((size_t)n == cap - 1) {
		close(fd);
		return -1;
	}
	if (close(fd) < 0)
		return -1;
	while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r'))
		n--;
	buf[n] = '\0';
	return 0;
}

static int read_u64_sysfs(const char *path, uint64_t *value)
{
	char buf[64], *end;
	unsigned long long parsed;

	if (read_sysfs(path, buf, sizeof(buf)) < 0 || !buf[0] || buf[0] == '-')
		return -1;
	errno = 0;
	parsed = strtoull(buf, &end, 10);
	if (errno || *end)
		return -1;
	*value = parsed;
	return 0;
}

/* Return 0 only if every eraseblock is readable and good. */
static int scan_badblocks(int fd, const struct mtd_info_user *info,
			  const struct allowed_mtd *target,
			  uint64_t *blocks_scanned)
{
	uint64_t off, blocks;
	/* MEMGETBADBLOCK consumes the kernel's signed 64-bit loff_t ABI.  Use an
	 * explicit fixed-width type here: musl user headers need not expose loff_t. */
	int64_t query;
	int ret;

	if (!blocks_scanned)
		return -1;
	*blocks_scanned = 0;
	if (!info || !target ||
	    info->type != MTD_NANDFLASH ||
	    info->size != target->size || info->erasesize != 131072 ||
	    info->writesize != 2048 || info->oobsize != 64 ||
	    !info->erasesize || info->size % info->erasesize)
		return -1;
	blocks = info->size / info->erasesize;
	for (off = 0; off < info->size; off += info->erasesize) {
		query = (int64_t)off;
		errno = 0;
		ret = ioctl(fd, MEMGETBADBLOCK, &query);
		if (ret < 0)
			return -1;
		if (ret > 0)
			return 1;
		(*blocks_scanned)++;
	}
	return *blocks_scanned == blocks ? 0 : -1;
}

#ifndef HWD_MTD_GUARD_TEST
static int parse_device(const char *s, unsigned int *index)
{
	const char prefix[] = "/dev/mtd";
	char *end;
	unsigned long parsed;

	if (strncmp(s, prefix, sizeof(prefix) - 1) || !s[sizeof(prefix) - 1])
		return -1;
	errno = 0;
	parsed = strtoul(s + sizeof(prefix) - 1, &end, 10);
	if (errno || *end || parsed > UINT32_MAX)
		return -1;
	*index = (unsigned int)parsed;
	return 0;
}

int main(int argc, char **argv)
{
	const struct allowed_mtd *target;
	struct mtd_info_user info;
	struct stat st;
	char path[256], value[128];
	uint64_t offset, blocks = 0;
	unsigned int index;
	int fd, ret;

	if (argc != 3 || strcmp(argv[1], "--check-no-badblocks") ||
	    parse_device(argv[2], &index) < 0 || !(target = target_for_index(index))) {
		fprintf(stderr, "usage: %s --check-no-badblocks /dev/mtd{2,3,15,16}\n", argv[0]);
		return 2;
	}
	if (snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/name", index) >= (int)sizeof(path) ||
	    read_sysfs(path, value, sizeof(value)) < 0 || strcmp(value, target->name)) {
		fprintf(stderr, "hwd-mtd-guard: MTD label missing or mismatched\n");
		return 1;
	}
	if (snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/offset", index) >= (int)sizeof(path) ||
	    read_u64_sysfs(path, &offset) < 0 || offset != target->offset) {
		fprintf(stderr, "hwd-mtd-guard: MTD physical offset missing or mismatched\n");
		return 1;
	}
	if (snprintf(path, sizeof(path), "/dev/mtd%u", index) >= (int)sizeof(path) ||
	    stat(path, &st) < 0 || !S_ISCHR(st.st_mode) || major(st.st_rdev) != 90 ||
	    minor(st.st_rdev) != index * 2) {
		fprintf(stderr, "hwd-mtd-guard: not the expected read-write MTD character node\n");
		return 1;
	}
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		perror("hwd-mtd-guard: open read-only");
		return 1;
	}
	memset(&info, 0, sizeof(info));
	if (ioctl(fd, MEMGETINFO, &info) < 0) {
		perror("hwd-mtd-guard: MEMGETINFO");
		close(fd);
		return 1;
	}
	ret = scan_badblocks(fd, &info, target, &blocks);
	if (close(fd) < 0) {
		perror("hwd-mtd-guard: close");
		return 1;
	}
	if (ret != 0) {
		if (ret > 0)
			fprintf(stderr, "hwd-mtd-guard: bad block found after %" PRIu64 " clean blocks\n", blocks);
		else
			fprintf(stderr, "hwd-mtd-guard: geometry mismatch or MEMGETBADBLOCK error after %" PRIu64 " clean blocks\n", blocks);
		return 1;
	}
	printf("BADBLOCK_SCAN=PASS device=/dev/mtd%u name=%s offset=0x%08" PRIx64 " blocks=%" PRIu64 " bad=0\n",
	       index, target->name, target->offset, blocks);
	return 0;
}
#endif
