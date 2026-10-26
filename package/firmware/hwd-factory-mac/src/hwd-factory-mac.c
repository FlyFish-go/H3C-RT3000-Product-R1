/* SPDX-License-Identifier: GPL-2.0-only */
/* HW-D: read factory ethaddr from CRC-checked ENV without modifying it.
 * Fresh OEM observation establishes WAN=base, LAN=base+1, radios=base+2/+3.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#define ENV_SIZE 262144U
static uint32_t crc32_env(const unsigned char *p, size_t size)
{
    uint32_t crc = UINT32_MAX;
    size_t i;
    unsigned int j;
    for (i = 0; i < size; i++) {
        crc ^= p[i];
        for (j = 0; j < 8; j++)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    return ~crc;
}
static int hexn(unsigned char c)
{
    if (c >= '0' && c <= '9') return c-'0';
    if (c >= 'a' && c <= 'f') return c-'a'+10;
    if (c >= 'A' && c <= 'F') return c-'A'+10;
    return -1;
}
static int parse_env(const unsigned char *data, size_t size, uint64_t *base)
{
    uint32_t expected;
    const unsigned char *p, *end, *nul;
    uint64_t mac = 0;
    size_t i, n;
    unsigned int found = 0;
    int hi, lo;
    if (size != ENV_SIZE) return -1;
    expected = (uint32_t)data[0] | ((uint32_t)data[1]<<8) |
        ((uint32_t)data[2]<<16) | ((uint32_t)data[3]<<24);
    if (crc32_env(data+4, size-4) != expected) return -1;
    end = data+size;
    for (p = data+4; p < end && *p; p = nul+1) {
        nul = memchr(p, 0, (size_t)(end-p));
        if (!nul) return -1;
        n = (size_t)(nul-p);
        if (n < 8 || memcmp(p, "ethaddr=", 8)) continue;
        if (++found != 1 || n != 25) return -1;
        mac = 0;
        for (i = 0; i < 6; i++) {
            hi = hexn(p[8+i*3]); lo = hexn(p[9+i*3]);
            if (hi < 0 || lo < 0 || (i != 5 && p[10+i*3] != ':')) return -1;
            mac = (mac<<8) | (unsigned int)((hi<<4)|lo);
        }
    }
    if (p >= end || found != 1 || !mac || mac > UINT64_C(0xfffffffffffc) ||
        ((mac>>40)&1)) return -1;
    *base = mac;
    return 0;
}
static int identity_file(const char *path, const char *expected)
{
    char data[256];
    ssize_t n;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    n = read(fd, data, sizeof(data)-1);
    close(fd);
    if (n <= 0 || n == (ssize_t)sizeof(data)-1) return -1;
    data[n] = 0;
    if (data[n-1] == '\n') data[--n] = 0;
    return strcmp(data, expected) ? -1 : 0;
}
int main(int argc, char **argv)
{
    unsigned char compatible[256], data[ENV_SIZE];
    struct mtd_info_user info;
    struct stat st;
    uint64_t base, mac;
    int64_t bad_offset;
    size_t off, i;
    ssize_t n;
    int fd;
    (void)argv;
    if (argc != 1) return 2;
    fd = open("/proc/device-tree/compatible", O_RDONLY | O_CLOEXEC);
    if (fd < 0) goto reject;
    n = read(fd, compatible, sizeof(compatible));
    close(fd);
    if (n < 14 || n >= (ssize_t)sizeof(compatible) ||
        memcmp(compatible, "h3c,nx30-hw-d\0", 14)) goto reject;
    if (identity_file("/sys/class/mtd/mtd10/name", "0:APPSBLENV") ||
        identity_file("/sys/class/mtd/mtd10/offset", "4718592")) goto reject;
    fd = open("/dev/mtd10", O_RDONLY | O_CLOEXEC);
    if (fd < 0) goto reject;
    if (fstat(fd, &st) || !S_ISCHR(st.st_mode) || major(st.st_rdev) != 90 ||
        minor(st.st_rdev) != 20 || ioctl(fd, MEMGETINFO, &info) ||
        info.type != MTD_NANDFLASH || info.size != 524288 ||
        info.writesize != 2048 || info.erasesize != 131072 || info.oobsize != 64) {
        close(fd); goto reject;
    }
    for (off = 0; off < ENV_SIZE; off += 131072) {
        bad_offset = (int64_t)off;
        if (ioctl(fd, MEMGETBADBLOCK, &bad_offset) != 0) {
            close(fd); goto reject;
        }
    }
    for (off = 0; off < ENV_SIZE; off += 2048) {
        do { n = read(fd, data+off, 2048); } while (n < 0 && errno == EINTR);
        if (n != 2048) { close(fd); goto reject; }
    }
    close(fd);
    if (parse_env(data, sizeof(data), &base)) goto reject;
    for (i = 0; i < 4; i++) {
        mac = base+i;
        if ((mac>>40)&1) goto reject;
        printf("%02" PRIx64 ":%02" PRIx64 ":%02" PRIx64 ":%02" PRIx64 ":%02" PRIx64 ":%02" PRIx64 "%c",
            (mac>>40)&255, (mac>>32)&255, (mac>>24)&255,
            (mac>>16)&255, (mac>>8)&255, mac&255, i==3?'\n':' ');
    }
    return 0;
reject:
    fprintf(stderr, "hwd-factory-mac: board/physical ENV/CRC/factory MAC rejected\n");
    return 1;
}
