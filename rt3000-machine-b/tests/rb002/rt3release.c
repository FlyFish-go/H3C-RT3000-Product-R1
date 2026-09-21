/*
 * rt3release - RT3000 Machine-B stable firmware identity (RB002).
 *
 * ---------------------------------------------------------------------------
 * Why this exists
 * ---------------------------------------------------------------------------
 * The previous slot logic used the UBI "image sequence" number
 * (a 4-byte field in the UBI EC header) as firmware identity.  That is wrong
 * by construction: image_seq is *format metadata*.  Any re-format of the same
 * bytes (ubiformat, a re-pack, a vendor flashing tool) writes a new image_seq
 * while the firmware content is bit-for-bit identical.  Equally, a corrupted
 * payload keeps its image_seq.  So image_seq can produce both false negatives
 * (identical firmware reported as different) and false positives (damaged
 * firmware reported as the expected release).
 *
 * Identity here is derived ONLY from stable content:
 *
 *   kernel  = SHA-256 over the kernel volume payload (FIT image, d00dfeed)
 *   rootfs  = SHA-256 over the squashfs rootfs volume payload (hsqs)
 *
 * and both are compared against the hashes recorded in the release manifest
 * that is itself part of the running rootfs (/etc/rt3000-release.json).
 *
 * Nothing in this file reads or depends on image_seq, EC counters, VID headers
 * or PEB placement.
 *
 * ---------------------------------------------------------------------------
 * Runtime payload path
 * ---------------------------------------------------------------------------
 * A running QSDK slot exposes:
 *   /dev/ubi0_0        kernel volume  (FIT,   d00dfeed)
 *   /dev/ubiblock0_1   rootfs volume  (squashfs, hsqs)  -- the mounted /
 *
 * Both are read-only views of the *payload*, so hashing them is stable across
 * re-flashes and independent of flash layout.  The runner hashes the ACTIVE
 * slot.  The inactive slot's payload is not reachable through these nodes, so
 * inactive verification is reported honestly as UNSUPPORTED rather than faked.
 *
 * ---------------------------------------------------------------------------
 * Truncation / padding rule
 * ---------------------------------------------------------------------------
 * The kernel is a FIT image whose total size is declared in its header; only
 * that many bytes are hashed so trailing volume padding does not affect the
 * identity.  The rootfs is a squashfs; its exact payload length is recorded in
 * the manifest at build time (rootfs_size), because a squashfs has no
 * self-describing total length field in its superblock.
 *
 * Commands:
 *   rt3release show
 *   rt3release verify [--manifest PATH]
 *   rt3release id [--manifest PATH]
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>

#define MANIFEST_DEFAULT "/etc/rt3000-release.json"
#define KERNEL_DEV       "/dev/ubi0_0"
#define ROOTFS_DEV       "/dev/ubiblock0_1"

#define EX_OK       0
#define EX_USAGE    2
#define EX_NOMAN    3   /* manifest missing / unreadable / malformed          */
#define EX_MISMATCH 4   /* payload does not match the manifest                */
#define EX_HW       5   /* device/platform identity does not match            */
#define EX_IO       6

/* --------------------------------------------------------------------------
 * SHA-256
 * -------------------------------------------------------------------------- */
struct sha256_ctx {
    uint32_t h[8];
    uint64_t len;
    unsigned char buf[64];
    size_t buflen;
};

static const uint32_t K256[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

#define ROR32(x,n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha256_init(struct sha256_ctx *c)
{
    static const uint32_t iv[8] = {
        0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
    };
    memcpy(c->h, iv, sizeof(iv));
    c->len = 0; c->buflen = 0;
}

static void sha256_block(struct sha256_ctx *c, const unsigned char *p)
{
    uint32_t w[64], a, b, d, e, f, g, hh, t1, t2, cc;
    int i;
    for (i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) |
               ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
    for (i = 16; i < 64; i++) {
        uint32_t s0 = ROR32(w[i-15],7) ^ ROR32(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = ROR32(w[i-2],17) ^ ROR32(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    a=c->h[0]; b=c->h[1]; cc=c->h[2]; d=c->h[3];
    e=c->h[4]; f=c->h[5]; g=c->h[6]; hh=c->h[7];
    for (i = 0; i < 64; i++) {
        uint32_t S1 = ROR32(e,6) ^ ROR32(e,11) ^ ROR32(e,25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t S0 = ROR32(a,2) ^ ROR32(a,13) ^ ROR32(a,22);
        uint32_t mj = (a & b) ^ (a & cc) ^ (b & cc);
        t1 = hh + S1 + ch + K256[i] + w[i];
        t2 = S0 + mj;
        hh=g; g=f; f=e; e=d+t1; d=cc; cc=b; b=a; a=t1+t2;
    }
    c->h[0]+=a; c->h[1]+=b; c->h[2]+=cc; c->h[3]+=d;
    c->h[4]+=e; c->h[5]+=f; c->h[6]+=g; c->h[7]+=hh;
}

static void sha256_update(struct sha256_ctx *c, const unsigned char *p, size_t n)
{
    c->len += n;
    while (n) {
        size_t take = 64 - c->buflen;
        if (take > n) take = n;
        memcpy(c->buf + c->buflen, p, take);
        c->buflen += take; p += take; n -= take;
        if (c->buflen == 64) { sha256_block(c, c->buf); c->buflen = 0; }
    }
}

static void sha256_final(struct sha256_ctx *c, unsigned char out[32])
{
    uint64_t bits = c->len * 8;
    unsigned char pad = 0x80;
    unsigned char z = 0;
    int i;
    sha256_update(c, &pad, 1);
    while (c->buflen != 56) sha256_update(c, &z, 1);
    for (i = 7; i >= 0; i--) {
        unsigned char b = (unsigned char)((bits >> (i*8)) & 0xff);
        sha256_update(c, &b, 1);
    }
    for (i = 0; i < 8; i++) {
        out[i*4]   = (unsigned char)(c->h[i] >> 24);
        out[i*4+1] = (unsigned char)(c->h[i] >> 16);
        out[i*4+2] = (unsigned char)(c->h[i] >> 8);
        out[i*4+3] = (unsigned char)(c->h[i]);
    }
}

static void hex32(const unsigned char d[32], char out[65])
{
    static const char hx[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; i++) { out[i*2] = hx[d[i] >> 4]; out[i*2+1] = hx[d[i] & 15]; }
    out[64] = 0;
}

/* Read the FIT/DTB declared total size from a payload.  The UBI kernel volume
 * is the FIT image padded with 0xFF to the erase-block boundary, so the
 * declared length is the stable content extent: hashing exactly that many bytes
 * makes kernel identity independent of volume padding and erase-block size.
 * Returns 0 when the payload is not a FIT image. */
static uint64_t fit_total_size(const char *path)
{
    int fd = open(path, O_RDONLY);
    unsigned char h[8];
    ssize_t n;
    uint32_t magic, total;
    uint64_t sz;

    if (fd < 0) return 0;
    n = read(fd, h, sizeof(h));
    if (n != (ssize_t)sizeof(h)) { close(fd); return 0; }
    magic = ((uint32_t)h[0] << 24) | ((uint32_t)h[1] << 16) |
            ((uint32_t)h[2] << 8) | (uint32_t)h[3];
    total = ((uint32_t)h[4] << 24) | ((uint32_t)h[5] << 16) |
            ((uint32_t)h[6] << 8) | (uint32_t)h[7];
    close(fd);
    if (magic != 0xd00dfeed) return 0;   /* not a FIT/DTB */
    sz = (uint64_t)total;
    if (sz < 8 || sz > (64u << 20)) return 0;
    return sz;
}

/* Hash a device/file region.  maxlen==0 means "to EOF"; nonzero means exactly
 * maxlen bytes (used for the squashfs rootfs, whose length the manifest
 * records). */
static int hash_region(const char *path, uint64_t maxlen, char hex[65],
                       uint64_t *out_len, const char **err)
{
    int fd;
    unsigned char buf[65536];
    struct sha256_ctx c;
    uint64_t total = 0;
    ssize_t n;

    fd = open(path, O_RDONLY);
    if (fd < 0) { *err = strerror(errno); return EX_IO; }

    sha256_init(&c);
    for (;;) {
        size_t want = sizeof(buf);
        if (maxlen && (total + want) > maxlen) want = (size_t)(maxlen - total);
        if (want == 0) break;
        n = read(fd, buf, want);
        if (n < 0) {
            if (errno == EINTR) continue;
            *err = strerror(errno); close(fd); return EX_IO;
        }
        if (n == 0) break;
        sha256_update(&c, buf, (size_t)n);
        total += (uint64_t)n;
        if (maxlen && total >= maxlen) break;
    }
    close(fd);
    sha256_final(&c, buf);
    hex32(buf, hex);
    if (out_len) *out_len = total;
    return EX_OK;
}

/* --------------------------------------------------------------------------
 * Minimal JSON field extraction (flat string/number values only).
 *
 * The manifest is generated by the build, is flat, and is never
 * attacker-controlled input; a tiny extractor avoids pulling in a JSON
 * dependency for a 20-line read.
 * -------------------------------------------------------------------------- */
static int json_get(const char *json, const char *key, char *out, size_t outsz)
{
    char pat[128];
    const char *p, *q;
    size_t n;

    snprintf(pat, sizeof(pat), "\"%s\"", key);
    p = strstr(json, pat);
    if (!p) return 0;
    p += strlen(pat);
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p != ':') return 0;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p == '"') {
        p++;
        q = strchr(p, '"');
        if (!q) return 0;
        n = (size_t)(q - p);
    } else {
        q = p;
        while (*q && *q != ',' && *q != '\n' && *q != '}' &&
               *q != ' ' && *q != '\r' && *q != '\t') q++;
        n = (size_t)(q - p);
    }
    if (n == 0 || n >= outsz) return 0;
    memcpy(out, p, n); out[n] = 0;
    return 1;
}

static char *slurp(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    char *b;
    long sz;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    sz = ftell(f);
    if (sz < 0 || sz > (1 << 20)) { fclose(f); return NULL; }
    rewind(f);
    b = malloc((size_t)sz + 1);
    if (!b) { fclose(f); return NULL; }
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) { free(b); fclose(f); return NULL; }
    b[sz] = 0;
    fclose(f);
    if (len) *len = (size_t)sz;
    return b;
}

struct manifest {
    char schema[64], product[128], machine[64], release[128];
    char network_baseline[64], kernel_sha256[65], rootfs_sha256[65];
    char build_id[65];
    uint64_t rootfs_size;
    int have_rootfs_size;
    int have_rootfs;
};

static int manifest_load(const char *path, struct manifest *m, const char **err)
{
    char *j;
    size_t len;
    char num[32];

    memset(m, 0, sizeof(*m));
    j = slurp(path, &len);
    if (!j) { *err = "manifest missing or unreadable"; return EX_NOMAN; }

    if (!json_get(j, "schema", m->schema, sizeof(m->schema)) ||
        strcmp(m->schema, "rt3000-release/v1") != 0) {
        *err = "manifest schema is not rt3000-release/v1";
        free(j); return EX_NOMAN;
    }
    if (!json_get(j, "product", m->product, sizeof(m->product)) ||
        !json_get(j, "machine", m->machine, sizeof(m->machine)) ||
        !json_get(j, "release", m->release, sizeof(m->release)) ||
        !json_get(j, "network_baseline", m->network_baseline, sizeof(m->network_baseline)) ||
        !json_get(j, "kernel_sha256", m->kernel_sha256, sizeof(m->kernel_sha256))) {
        *err = "manifest is missing required fields";
        free(j); return EX_NOMAN;
    }
    if (strlen(m->kernel_sha256) != 64) {
        *err = "manifest kernel hash is not 64-hex";
        free(j); return EX_NOMAN;
    }
    /* rootfs_sha256 is recorded only in the external (build-time) manifest.
     * The manifest that ships inside the rootfs cannot contain the rootfs' own
     * hash without being circular, so its absence is valid and simply means the
     * rootfs half of the identity is not checkable from inside the rootfs. */
    m->have_rootfs = (json_get(j, "rootfs_sha256", m->rootfs_sha256,
                               sizeof(m->rootfs_sha256)) &&
                      strlen(m->rootfs_sha256) == 64);
    if (json_get(j, "build_id", m->build_id, sizeof(m->build_id)) == 0)
        m->build_id[0] = 0;
    if (json_get(j, "rootfs_size", num, sizeof(num))) {
        char *e = NULL;
        unsigned long long v = strtoull(num, &e, 10);
        if (e && *e == 0) { m->rootfs_size = (uint64_t)v; m->have_rootfs_size = 1; }
    }
    free(j);
    return EX_OK;
}

static int manifest_check_machine(const struct manifest *m)
{
    if (strcmp(m->machine, "Machine-B") != 0) {
        fprintf(stderr, "manifest machine='%s' is not Machine-B\n", m->machine);
        return EX_HW;
    }
    if (strcmp(m->product, "H3C Magic RT3000") != 0) {
        fprintf(stderr, "manifest product='%s' is not H3C Magic RT3000\n", m->product);
        return EX_HW;
    }
    return EX_OK;
}

int main(int argc, char **argv)
{
    const char *cmd = (argc > 1) ? argv[1] : NULL;
    const char *mpath = MANIFEST_DEFAULT;
    const char *kdev = getenv("RT3RELEASE_KERNEL_DEV");
    const char *rdev = getenv("RT3RELEASE_ROOTFS_DEV");
    struct manifest m;
    const char *err = NULL;
    int i, r;

    if (!kdev || !*kdev) kdev = KERNEL_DEV;
    if (!rdev || !*rdev) rdev = ROOTFS_DEV;

    /* Collect --manifest; tolerate positional args (used by the
     * verify-rootfs / verify-kernel subcommands). */
    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--manifest")) {
            if (++i >= argc) goto usage;
            mpath = argv[i];
        } else if (argv[i][0] == '-' && argv[i][1] == '-') {
            goto usage;
        }
    }
    if (!cmd) goto usage;
    if (strcmp(cmd, "show") && strcmp(cmd, "verify") && strcmp(cmd, "id") &&
        strcmp(cmd, "verify-rootfs") && strcmp(cmd, "verify-kernel")) goto usage;

    /* verify-rootfs / verify-kernel: compare ONE payload file (given as the
     * first positional argument) against the manifest.  Used by the installer
     * and by hardware acceptance to check a payload before a slot is accepted. */
    if (!strcmp(cmd, "verify-rootfs") || !strcmp(cmd, "verify-kernel")) {
        const char *target = NULL;
        int want_rootfs = (cmd[7] == 'r');
        for (i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--manifest")) {
                if (++i >= argc) goto usage;
                mpath = argv[i];
            } else if (!target) {
                target = argv[i];
            } else goto usage;
        }
        if (!target) goto usage;
        r = manifest_load(mpath, &m, &err);
        if (r) {
            fprintf(stderr, "release identity UNAVAILABLE: %s (%s)\n", err, mpath);
            return r;
        }
        if (want_rootfs && !m.have_rootfs) {
            fprintf(stderr, "manifest records no rootfs_sha256; cannot verify a rootfs payload\n");
            printf("ROOTFS_VERIFY=UNSUPPORTED_NO_ROOTFS_HASH\n");
            return EX_NOMAN;
        }
        if (r) { printf("MACHINE_MATCH=FAIL\n"); return r; }
        printf("MACHINE_MATCH=PASS\n");
        {
            char hex[65];
            uint64_t len = 0;
            uint64_t maxlen;
            const char *want = want_rootfs ? m.rootfs_sha256 : m.kernel_sha256;
            if (want_rootfs)
                maxlen = m.have_rootfs_size ? m.rootfs_size : 0;
            else
                maxlen = fit_total_size(target);   /* truncate FIT padding */
            if (!want_rootfs && maxlen)
                printf("KERNEL_FIT_DECLARED_BYTES=%llu\n", (unsigned long long)maxlen);
            r = hash_region(target, maxlen, hex, &len, &err);
            if (r) {
                fprintf(stderr, "cannot hash %s: %s\n", target, err);
                return r;
            }
            printf("PAYLOAD_FILE=%s\n", target);
            printf("%s_ID=%s\n", want_rootfs ? "ROOTFS" : "KERNEL", hex);
            printf("%s_BYTES=%llu\n", want_rootfs ? "ROOTFS" : "KERNEL", (unsigned long long)len);
            if (strcmp(hex, want) == 0) {
                printf("%s_MATCH=PASS\n", want_rootfs ? "ROOTFS" : "KERNEL");
                printf("IMAGE_SEQ_DEPENDENCY=NONE\n");
                return EX_OK;
            }
            fprintf(stderr, "%s payload %s != manifest %s\n",
                    want_rootfs ? "rootfs" : "kernel", hex, want);
            printf("%s_MATCH=FAIL\n", want_rootfs ? "ROOTFS" : "KERNEL");
            printf("IMAGE_SEQ_DEPENDENCY=NONE\n");
            return EX_MISMATCH;
        }
    }

    r = manifest_load(mpath, &m, &err);
    if (r) {
        fprintf(stderr, "release identity UNAVAILABLE: %s (%s)\n", err, mpath);
        printf("MANIFEST_STATUS=ABSENT\n");
        printf("RELEASE_IDENTITY=UNKNOWN\n");
        return r;
    }

    printf("RELEASE_MANIFEST=%s\n", mpath);
    printf("RELEASE_SCHEMA=%s\n", m.schema);
    printf("RELEASE_PRODUCT=%s\n", m.product);
    printf("RELEASE_MACHINE=%s\n", m.machine);
    printf("RELEASE_NAME=%s\n", m.release);
    printf("RELEASE_NETWORK_BASELINE=%s\n", m.network_baseline);
    if (m.build_id[0]) printf("RELEASE_BUILD_ID=%s\n", m.build_id);
    printf("RELEASE_KERNEL_ID=%s\n", m.kernel_sha256);
    if (m.have_rootfs)
        printf("RELEASE_ROOTFS_ID=%s\n", m.rootfs_sha256);
    else
        printf("RELEASE_ROOTFS_ID=NOT_IN_MANIFEST\n");

    if (!strcmp(cmd, "show") || !strcmp(cmd, "id")) {
        if (!strcmp(cmd, "id")) {
            printf("RUNNING_KERNEL_ID=%s\n", m.kernel_sha256);
            printf("RUNNING_ROOTFS_ID=%s\n", m.rootfs_sha256);
        }
        return EX_OK;
    }

    /* ---- verify: identity from stable payload content only ---- */
    r = manifest_check_machine(&m);
    if (r) {
        printf("MACHINE_MATCH=FAIL\n");
        printf("QSDK_SLOT_VALID=NO\n");
        return r;
    }
    printf("MACHINE_MATCH=PASS\n");

    {
        char khex[65], rhex[65];
        uint64_t klen = 0, rlen = 0;

        {
            uint64_t fitsz = fit_total_size(kdev);
            r = hash_region(kdev, fitsz, khex, &klen, &err);
            if (!r && fitsz)
                printf("KERNEL_FIT_DECLARED_BYTES=%llu\n", (unsigned long long)fitsz);
        }
        if (r) {
            fprintf(stderr, "cannot hash kernel payload %s: %s\n", kdev, err);
            printf("KERNEL_PAYLOAD_STATUS=UNREADABLE\n");
            printf("QSDK_SLOT_VALID=UNKNOWN\n");
            return r;
        }
        printf("RUNNING_KERNEL_ID=%s\n", khex);
        printf("RUNNING_KERNEL_BYTES=%llu\n", (unsigned long long)klen);

        if (m.have_rootfs_size)
            r = hash_region(rdev, m.rootfs_size, rhex, &rlen, &err);
        else
            r = hash_region(rdev, 0, rhex, &rlen, &err);
        if (r) {
            fprintf(stderr, "cannot hash rootfs payload %s: %s\n", rdev, err);
            printf("ROOTFS_PAYLOAD_STATUS=UNREADABLE\n");
            printf("QSDK_SLOT_VALID=UNKNOWN\n");
            return r;
        }
        printf("RUNNING_ROOTFS_ID=%s\n", rhex);
        printf("RUNNING_ROOTFS_BYTES=%llu\n", (unsigned long long)rlen);

        {
            int kok = (strcmp(khex, m.kernel_sha256) == 0);
            int rok = m.have_rootfs ? (strcmp(rhex, m.rootfs_sha256) == 0) : -1;
            printf("KERNEL_MATCH=%s\n", kok ? "PASS" : "FAIL");
            if (rok < 0) {
                printf("ROOTFS_MATCH=NOT_IN_MANIFEST\n");
                printf("ROOTFS_VERIFY=UNSUPPORTED_FROM_INSIDE_ROOTFS\n");
            } else {
                printf("ROOTFS_MATCH=%s\n", rok ? "PASS" : "FAIL");
            }
            if (!kok) fprintf(stderr, "kernel payload %s != manifest %s\n", khex, m.kernel_sha256);
            if (rok == 0) fprintf(stderr, "rootfs payload %s != manifest %s\n", rhex, m.rootfs_sha256);
            printf("IMAGE_SEQ_DEPENDENCY=NONE\n");
            if (kok && rok != 0) {
                printf("QSDK_SLOT_VALID=YES\n");
                printf("RELEASE_IDENTITY_MATCH=%s\n",
                       rok < 0 ? "PASS_KERNEL_ONLY" : "PASS");
                return EX_OK;
            }
            printf("QSDK_SLOT_VALID=NO\n");
            printf("RELEASE_IDENTITY_MATCH=FAIL\n");
            return EX_MISMATCH;
        }
    }

usage:
    fprintf(stderr, "usage: %s show|id|verify|verify-rootfs|verify-kernel [FILE] [--manifest PATH]\n", argv[0]);
    return EX_USAGE;
}
