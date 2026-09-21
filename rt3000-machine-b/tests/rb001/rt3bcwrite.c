/*
 * rt3bcwrite - RT3000 BOOTCONFIG A/B rootfs selector writer (user space).
 *
 * Direct MTD read-modify-erase-write of the 4-byte rootfs selector inside the
 * redundant BOOTCONFIG / BOOTCONFIG1 partitions.  No kernel module required:
 * plain open/ioctl(MEMERASE)/read/write on /dev/mtdN.
 *
 * ---------------------------------------------------------------------------
 * RB001 safety contract (fail-closed, per-copy sequential verify)
 * ---------------------------------------------------------------------------
 * The selector lives in TWO redundant copies:
 *
 *   mtd3 (BOOTCONFIG1)  = redundant copy, written FIRST
 *   mtd2 (BOOTCONFIG)   = primary   copy, written SECOND
 *
 * mtd2 shares its erase block with an OEM configuration blob at ~0x880, so a
 * whole-partition image write is FORBIDDEN.  Every write is a live read-modify
 * -write of exactly one erase block, and only the 4 selector bytes at 0x080
 * may ever differ.
 *
 * Each copy runs the identical transaction, in this order:
 *
 *   1. read the current live erase block
 *   2. structurally validate it (magic/version/count/records/tail)
 *   3. patch ONLY the 4 selector bytes (binary-safe LE32 store)
 *   4. confirm that every other byte is unchanged vs. the live copy
 *   5. erase + write the block
 *   6. read back the whole block
 *   7. byte-compare the whole block against the intended image
 *   8. re-parse the structure from the readback
 *   9. confirm the selector is exactly the target value
 *
 * The second copy is touched ONLY if the first copy's transaction fully
 * passed.  Any failure on the first copy aborts with the second copy
 * untouched.  A failure on the second copy aborts with a nonzero status and
 * an explicit statement that the copies are now divergent.  There is no path
 * that reports success unless both copies hold the exact target selector.
 *
 * Commands:
 *   rt3bcwrite --show
 *   rt3bcwrite --set 0|1 [--reboot] [--force-unequal]
 *   rt3bcwrite --verify-only 0|1
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <mtd/mtd-user.h>

#define BC_EFF      0x150
#define BC_HDR      12
#define BC_ENT      20
#define BC_NAME_LEN 16
#define BC_SEL_OFF  16
#define BC_COUNT    8
#define BC_MAGIC    0xa3a2a1a0u
#define BC_TAIL     0xb3b2b1b0u
#define SEL_OFF     0x080
#define MANAGED     "rootfs"
#define REC_INDEX   5

/* Exit codes.  Distinct values so the shell layer can distinguish a refusal
 * (nothing written) from a partial write (first copy written, second failed). */
#define EX_OK        0
#define EX_USAGE     2
#define EX_STRUCT    3   /* structural validation refused; nothing written      */
#define EX_IO        4   /* open/read failure; nothing written                 */
#define EX_WRITE1    5   /* first-copy write/erase failed; second untouched    */
#define EX_WRITE2    6   /* second-copy write/erase failed; copies DIVERGENT   */
#define EX_VERIFY1   7   /* first-copy readback mismatch; second untouched     */
#define EX_VERIFY2   8   /* second-copy readback mismatch; copies DIVERGENT    */

static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Binary-safe little-endian store.  This is the ONLY way the selector is ever
 * materialised.  No printf escapes, no shell quoting, no string literals: a
 * historical incident wrote the ASCII text "\001" instead of byte 0x01. */
static void put_le32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)(v & 0xff);
    p[1] = (unsigned char)((v >> 8) & 0xff);
    p[2] = (unsigned char)((v >> 16) & 0xff);
    p[3] = (unsigned char)((v >> 24) & 0xff);
}

struct copy_info {
    const char *path;
    const char *label;
    const char *tag;       /* "mtd3" / "mtd2", used for fault-injection hooks */
    int fd;
    uint32_t erasesize;
    unsigned char raw[BC_EFF];
    unsigned char *live;   /* pristine live erase block, for full-block compare */
    uint32_t live_len;
    uint32_t count;
    uint32_t sel[BC_COUNT];
    int rec;
    int valid;
};

/* --------------------------------------------------------------------------
 * Fault injection.  Compiled in only for the synthetic test suite; the
 * shipped binary has RT3BCWRITE_MOCK undefined and this block vanishes.
 * -------------------------------------------------------------------------- */
#ifdef RT3BCWRITE_MOCK
static const char *mock_env(const char *k)
{
    const char *v = getenv(k);
    return (v && *v) ? v : NULL;
}
static void mock_record(const char *tag)
{
    const char *p = mock_env("RT3BCWRITE_MOCK_ORDER");
    FILE *f;
    if (!p) return;
    f = fopen(p, "a");
    if (f) { fprintf(f, "%s\n", tag); fclose(f); }
}
/* Returns nonzero when this operation on this copy must fail. */
static int mock_fail(const char *tag, const char *op)
{
    char key[128];
    const char *v;
    snprintf(key, sizeof(key), "RT3BCWRITE_MOCK_FAIL_%s_%s", tag, op);
    v = mock_env(key);
    if (v) return 1;
    v = mock_env("RT3BCWRITE_MOCK_FAIL_ALL");
    return v ? 1 : 0;
}
/* Corrupt the readback buffer to simulate a NAND readback mismatch. */
static int mock_corrupt_readback(const char *tag)
{
    char key[128];
    snprintf(key, sizeof(key), "RT3BCWRITE_MOCK_CORRUPT_%s", tag);
    return mock_env(key) ? 1 : 0;
}
#else
#define mock_record(t)              do { } while (0)
#define mock_fail(t, o)             (0)
#define mock_corrupt_readback(t)    (0)
#endif

/* --------------------------------------------------------------------------
 * Structural validation
 * -------------------------------------------------------------------------- */
static int parse(struct copy_info *c, const unsigned char *b)
{
    uint32_t magic, ver, count, tail;
    int i;

    magic = le32(b + 0); ver = le32(b + 4);
    count = le32(b + 8); tail = le32(b + 0x14c);

    if (magic != BC_MAGIC) { fprintf(stderr, "%s: bad magic 0x%08x\n", c->label, magic); return EX_STRUCT; }
    if (tail  != BC_TAIL)  { fprintf(stderr, "%s: bad tail 0x%08x\n",  c->label, tail);  return EX_STRUCT; }
    if (ver   != 1)        { fprintf(stderr, "%s: bad version %u\n",   c->label, ver);   return EX_STRUCT; }
    if (count != BC_COUNT) { fprintf(stderr, "%s: bad count %u\n",     c->label, count); return EX_STRUCT; }

    c->count = count; c->rec = -1;
    for (i = 0; i < (int)count; i++) {
        const unsigned char *e = b + BC_HDR + i * BC_ENT;
        size_t n = strnlen((const char *)e, BC_NAME_LEN);
        /* A full-width name has no NUL terminator and is not a valid record. */
        if (n == 0 || n == BC_NAME_LEN) { fprintf(stderr, "%s: rec %d bad name\n", c->label, i); return EX_STRUCT; }
        c->sel[i] = le32(e + BC_SEL_OFF);
        if (memcmp(e, MANAGED, strlen(MANAGED)) == 0 && e[strlen(MANAGED)] == 0)
            c->rec = i;
    }
    if (c->rec < 0) { fprintf(stderr, "%s: no '%s' record\n", c->label, MANAGED); return EX_STRUCT; }
    if (c->rec != REC_INDEX) {
        fprintf(stderr, "%s: '%s' is rec %d, layout requires %d\n", c->label, MANAGED, c->rec, REC_INDEX);
        return EX_STRUCT;
    }
    memcpy(c->raw, b, BC_EFF);
    c->valid = 1;
    return EX_OK;
}

static int open_copy(struct copy_info *c, const char *dev, const char *label, const char *tag)
{
    char path[256];
#ifdef RT3BCWRITE_MOCK
    const char *root = mock_env("RT3BCWRITE_MOCK_DIR");
    if (root)
        snprintf(path, sizeof(path), "%s/%s", root, dev);
    else
        snprintf(path, sizeof(path), "/dev/%s", dev);
#else
    snprintf(path, sizeof(path), "/dev/%s", dev);
#endif
    c->path = strdup(path); c->label = label; c->tag = tag;
    c->fd = open(path, O_RDWR);
    if (c->fd < 0) { fprintf(stderr, "%s: open %s: %s\n", label, path, strerror(errno)); return EX_IO; }
#ifdef RT3BCWRITE_MOCK
    c->erasesize = 4096;
#else
    {
        struct mtd_info_user mtd;
        if (ioctl(c->fd, MEMGETINFO, &mtd) < 0) {
            fprintf(stderr, "%s: MEMGETINFO: %s\n", label, strerror(errno)); return EX_IO;
        }
        c->erasesize = mtd.erasesize;
    }
#endif
    return EX_OK;
}

static int read_struct(struct copy_info *c)
{
    unsigned char buf[BC_EFF];
    ssize_t n = pread(c->fd, buf, BC_EFF, 0);
    if (n != BC_EFF) { fprintf(stderr, "%s: read %zd: %s\n", c->label, n, strerror(errno)); return EX_IO; }
    return parse(c, buf);
}

/* --------------------------------------------------------------------------
 * One complete transaction on one copy.
 *
 * Returns 0 only when the copy provably holds `want` after a full erase/write
 * /readback/compare/re-parse cycle.  Any nonzero return means this copy's
 * on-media content is NOT guaranteed to be the target value.
 * -------------------------------------------------------------------------- */
static int transaction(struct copy_info *c, uint32_t want, int *already)
{
    unsigned char *blk = NULL, *rb = NULL;
    uint32_t esz;
#ifndef RT3BCWRITE_MOCK
    struct erase_info_user ei;
#endif
    ssize_t n;
    size_t i, bad;
    int r;

    *already = 0;
    esz = c->erasesize;
    if (esz < BC_EFF || esz > (64u << 20)) {
        fprintf(stderr, "%s: implausible erasesize %u\n", c->label, esz);
        return EX_WRITE1;
    }
    blk = malloc(esz); rb = malloc(esz);
    if (!blk || !rb) { fprintf(stderr, "%s: oom\n", c->label); r = EX_WRITE1; goto out; }

    /* 1. read the live erase block */
    n = pread(c->fd, blk, esz, 0);
    if (n != (ssize_t)esz) { fprintf(stderr, "%s: block read %zd\n", c->label, n); r = EX_IO; goto out; }

    /* 2. validate the live block before touching it */
    r = parse(c, blk);
    if (r) { fprintf(stderr, "%s: live block invalid, refusing to write\n", c->label); goto out; }

    /* Keep a pristine copy of the live block so step 4 can prove that the
     * patched image differs from the live image in the selector bytes only.
     * This covers the WHOLE erase block, including the OEM config blob that
     * shares mtd2's erase block past ~0x880. */
    free(c->live);
    c->live = malloc(esz);
    if (!c->live) { fprintf(stderr, "%s: oom\n", c->label); r = EX_WRITE1; goto out; }
    memcpy(c->live, blk, esz);
    c->live_len = esz;

    /* 18. idempotence: already at target -> nothing to write */
    if (c->sel[c->rec] == want) {
        printf("%s: already 0x%08x (idempotent, 0 writes)\n", c->label, want);
        *already = 1; r = EX_OK; goto out;
    }

    /* 3. patch ONLY the selector bytes (binary-safe) */
    put_le32(blk + SEL_OFF, want);

    /* 4. prove nothing else changed: every byte outside the 4 selector bytes
     *    must be identical to the pristine live block. */
    for (i = 0; i < esz; i++) {
        if (i >= SEL_OFF && i < SEL_OFF + 4) continue;
        if (blk[i] != c->live[i]) {
            fprintf(stderr, "%s: internal error: byte %zu mutated outside selector\n", c->label, i);
            r = EX_STRUCT; goto out;
        }
    }

    /* 5. erase + write */
    mock_record(c->tag);
    if (mock_fail(c->tag, "WRITE")) {
        fprintf(stderr, "%s: injected write failure\n", c->label);
        r = EX_WRITE1; goto out;
    }
#ifndef RT3BCWRITE_MOCK
    ei.start = 0; ei.length = esz;
    if (ioctl(c->fd, MEMERASE, &ei) < 0) {
        fprintf(stderr, "%s: MEMERASE: %s\n", c->label, strerror(errno)); r = EX_WRITE1; goto out;
    }
#endif
    n = pwrite(c->fd, blk, esz, 0);
    if (n != (ssize_t)esz) { fprintf(stderr, "%s: write %zd: %s\n", c->label, n, strerror(errno)); r = EX_WRITE1; goto out; }
    fsync(c->fd);

    /* 6. read back the whole block */
    n = pread(c->fd, rb, esz, 0);
    if (n != (ssize_t)esz) { fprintf(stderr, "%s: verify read %zd\n", c->label, n); r = EX_VERIFY1; goto out; }
    if (mock_corrupt_readback(c->tag)) {
        rb[SEL_OFF] = (unsigned char)(rb[SEL_OFF] ^ 0xff);
        fprintf(stderr, "%s: injected readback corruption\n", c->label);
    }

    /* 7. full-block byte compare */
    bad = 0;
    for (i = 0; i < esz; i++)
        if (rb[i] != blk[i]) {
            if (bad < 8) fprintf(stderr, "%s: byte %zu 0x%02x!=0x%02x\n", c->label, i, rb[i], blk[i]);
            bad++;
        }
    if (bad) { fprintf(stderr, "%s: BLOCK VERIFY FAILED (%zu bytes)\n", c->label, bad); r = EX_VERIFY1; goto out; }

    /* 8. re-parse structure from the readback */
    r = parse(c, rb);
    if (r) { fprintf(stderr, "%s: post-write structure invalid\n", c->label); r = EX_VERIFY1; goto out; }

    /* 9. exact selector confirmation */
    if (c->sel[c->rec] != want) {
        fprintf(stderr, "%s: post-write selector 0x%08x != 0x%08x\n", c->label, c->sel[c->rec], want);
        r = EX_VERIFY1; goto out;
    }
    r = EX_OK;
out:
    free(blk); free(rb);
    return r;
}

int main(int argc, char **argv)
{
    struct copy_info B, A;   /* B = mtd3 (redundant), A = mtd2 (primary) */
    int i, r, show = 0, reboot = 0, force = 0, verify_only = 0, set_mode = 0;
    int already_b = 0, already_a = 0;
    long want = -1;
    char *end = NULL;

    memset(&B, 0, sizeof(B)); memset(&A, 0, sizeof(A));
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--show")) show = 1;
        else if (!strcmp(argv[i], "--reboot")) reboot = 1;
        else if (!strcmp(argv[i], "--force-unequal")) force = 1;
        else if (!strcmp(argv[i], "--verify-only")) {
            verify_only = 1;
            if (++i >= argc) goto usage;
            end = NULL; want = strtol(argv[i], &end, 0);
            if (!end || *end != '\0') goto usage;
        }
        else if (!strcmp(argv[i], "--set")) {
            set_mode = 1;
            if (++i >= argc) goto usage;
            end = NULL; want = strtol(argv[i], &end, 0);
            if (!end || *end != '\0') goto usage;
        } else goto usage;
    }

    if ((show && (verify_only || set_mode)) || (verify_only && set_mode)) goto usage;
    if (open_copy(&B, "mtd3", "mtd3(0:BOOTCONFIG1)", "mtd3")) return EX_IO;
    if (open_copy(&A, "mtd2", "mtd2(0:BOOTCONFIG)",  "mtd2")) return EX_IO;

    if (show) {
        r = read_struct(&B); if (!r) printf("%s rootfs selector = 0x%08x\n", B.label, B.sel[B.rec]);
        r = read_struct(&A); if (!r) printf("%s rootfs selector = 0x%08x\n", A.label, A.sel[A.rec]);
        if (B.valid && A.valid) {
            printf("copies_agree=%s\n", B.sel[B.rec] == A.sel[A.rec] ? "YES" : "NO");
            printf("current_slot=%s\n", A.sel[A.rec] ? "B(rootfs_1/QSDK)" : "A(rootfs/OEM)");
        }
        return EX_OK;
    }
    if (want < 0) goto usage;
    if (want != 0 && want != 1) { fprintf(stderr, "only 0 or 1 accepted\n"); return EX_USAGE; }

    r = read_struct(&B); if (r) { fprintf(stderr, "FATAL: mtd3 invalid, nothing written\n"); return r; }
    r = read_struct(&A); if (r) { fprintf(stderr, "FATAL: mtd2 invalid, nothing written\n"); return r; }

    printf("PRE  %s = 0x%08x\n", B.label, B.sel[B.rec]);
    printf("PRE  %s = 0x%08x\n", A.label, A.sel[A.rec]);

    if (verify_only) {
        int ok = (B.sel[B.rec] == (uint32_t)want && A.sel[A.rec] == (uint32_t)want);
        printf("VERIFY_ONLY want=0x%08x -> %s\n", (uint32_t)want, ok ? "PASS" : "FAIL");
        return ok ? EX_OK : EX_VERIFY2;
    }

    if (B.sel[B.rec] != A.sel[A.rec]) {
        fprintf(stderr, "copies DISAGREE (mtd3=0x%08x mtd2=0x%08x)\n", B.sel[B.rec], A.sel[A.rec]);
        if (!force) { fprintf(stderr, "refusing; pass --force-unequal to converge\n"); return EX_STRUCT; }
    }
    if (B.sel[B.rec] == (uint32_t)want && A.sel[A.rec] == (uint32_t)want) {
        printf("both copies already 0x%08x - nothing to do\n", (uint32_t)want);
        printf("copy=mtd3 write=SKIP verify=SKIP\n");
        printf("copy=mtd2 write=SKIP verify=SKIP\n");
        printf("final_selector=0x%08x\n", (uint32_t)want);
        printf("RESULT=PASS both copies = 0x%08x\n", (uint32_t)want);
        goto done;
    }

    /* ---------------- FIRST COPY = mtd3 (redundant) ---------------- */
    printf("copy=mtd3 FIRST (redundant)\n"); fflush(stdout);
    r = transaction(&B, (uint32_t)want, &already_b);
    if (r) {
        fprintf(stderr, "mtd3(0:BOOTCONFIG1) TRANSACTION FAILED (rc=%d); "
                        "mtd2 was NOT touched\n", r);
        printf("copy=mtd3 write=FAIL verify=FAIL\n");
        printf("copy=mtd2 write=NONE verify=NONE\n");
        printf("RESULT=FAIL first_copy_failed second_copy_untouched\n");
        return r ? r : EX_WRITE1;
    }
    printf("copy=mtd3 write=PASS verify=PASS%s\n", already_b ? " (already-at-target)" : "");

    /* ---------------- SECOND COPY = mtd2 (primary) ----------------- */
    printf("copy=mtd2 SECOND (primary)\n"); fflush(stdout);
    r = transaction(&A, (uint32_t)want, &already_a);
    if (r) {
        fprintf(stderr, "mtd2(0:BOOTCONFIG) TRANSACTION FAILED (rc=%d); "
                        "mtd3 IS ALREADY 0x%08x -> COPIES NOW DIVERGENT\n",
                r, (uint32_t)want);
        printf("copy=mtd2 write=FAIL verify=FAIL\n");
        printf("RESULT=FAIL second_copy_failed copies_divergent\n");
        return r ? (r + 2) : EX_WRITE2;
    }
    printf("copy=mtd2 write=PASS verify=PASS%s\n", already_a ? " (already-at-target)" : "");

    /* ---------------- final dual-copy confirmation ----------------- */
    r = read_struct(&B); if (r) { printf("RESULT=FAIL final_readback_mtd3\n"); return r; }
    r = read_struct(&A); if (r) { printf("RESULT=FAIL final_readback_mtd2\n"); return r; }
    printf("POST %s = 0x%08x\n", B.label, B.sel[B.rec]);
    printf("POST %s = 0x%08x\n", A.label, A.sel[A.rec]);
    if (B.sel[B.rec] != (uint32_t)want || A.sel[A.rec] != (uint32_t)want) {
        fprintf(stderr, "FINAL CHECK FAILED\n");
        printf("RESULT=FAIL final_selector_mismatch\n");
        return EX_VERIFY2;
    }
    printf("final_selector=0x%08x\n", (uint32_t)want);
    printf("RESULT=PASS both copies = 0x%08x\n", (uint32_t)want);

done:
    free(B.live); free(A.live);
    if (reboot) {
        printf("requesting normal reboot...\n"); fflush(stdout);
        sync();
        execl("/sbin/reboot", "reboot", (char *)NULL);
        execl("/bin/busybox", "busybox", "reboot", (char *)NULL);
        perror("reboot"); return 7;
    }
    return EX_OK;

usage:
    fprintf(stderr, "usage: %s --show | --set 0|1 [--reboot] [--force-unequal] | --verify-only 0|1\n", argv[0]);
    return EX_USAGE;
}
