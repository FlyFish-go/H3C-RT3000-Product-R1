#!/usr/bin/env python3
"""Exercise the actual C (425/428/429) and HW-D (426/429) NAND map guards offline.

Applies patch 429 to a private copy of drivers/mtd/mtdpart.c from a prepared
kernel tree (425-428 already applied), compiles the guard functions natively
with UBSan and feeds them the DT storage maps, both two-slot orientations and
the single 80 MiB rootfs map patch 030 builds. Only writes to --output-dir.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT/'target/linux/ipq50xx/patches/429-mtd-single-rootfs-layout.patch'

def run(args, **kw):
    r = subprocess.run([str(x) for x in args], capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(str(args) + '\n' + r.stdout + r.stderr)
    return r

PRELUDE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64;
typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define MTD_NANDFLASH 4
#define MTD_WRITEABLE 0x400
struct device_node { int safe_c, safe_d, installer_c, installer_d, ramro_d; };
struct device { struct device_node *of_node; };
struct mtd_info {
    int type; u64 size; u32 writesize, erasesize, oobsize, ecc_strength;
    struct { struct device *parent; } dev;
};
struct mtd_partition { const char *name; u64 size, offset; u32 mask_flags; };
static const char *machine;
static int of_machine_is_compatible(const char *c) { return !strcmp(c, machine); }
static int mtd_is_partition(const struct mtd_info *m) { (void)m; return 0; }
static bool of_property_read_bool(const struct device_node *np, const char *p) {
    if (!strcmp(p, "h3c,rt3000-native-nand-safe-config")) return np->safe_c;
    if (!strcmp(p, "h3c,nx30-hw-d-nand-safe-config")) return np->safe_d;
    if (!strcmp(p, "h3c,rt3000-c-installer-write-bootconfig")) return np->installer_c;
    if (!strcmp(p, "h3c,nx30-hw-d-installer-write-bootconfig")) return np->installer_d;
    if (!strcmp(p, "h3c,nx30-hw-d-ram-readonly")) return np->ramro_d;
    return 0;
}
'''

MAIN = r'''
/* argv: board(c|d) ramro mtdparts-body ; prints "valid named" and per-part windows */
int main(int argc, char **argv) {
    static struct mtd_partition parts[64];
    static char names[64][32];
    struct device_node np = {1, 1, 0, 0, 0};
    struct device dev = {&np};
    struct mtd_info m = {MTD_NANDFLASH, 0x08000000ULL, 2048, 131072, 64, 4, {&dev}};
    char *s, *tok, *save;
    int n = 0, i;
    if (argc != 4) return 3;
    machine = argv[1][0] == 'c' ? "h3c,rt3000-rtl8367s" : "h3c,nx30-hw-d";
    np.ramro_d = atoi(argv[2]);
    s = strdup(argv[3]);
    for (tok = strtok_r(s, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        char *at = strchr(tok, '@'), *lp = strchr(tok, '('), *rp = strchr(tok, ')');
        if (!at || !lp || !rp || n == 64) return 4;
        parts[n].size = strtoull(tok, NULL, 0);
        parts[n].offset = strtoull(at + 1, NULL, 0);
        snprintf(names[n], sizeof(names[n]), "%.*s", (int)(rp - lp - 1), lp + 1);
        parts[n].name = names[n];
        parts[n].mask_flags = !strcmp(rp + 1, "ro") ? MTD_WRITEABLE : 0;
        n++;
    }
    if (argv[1][0] == 'c') {
        bool valid = rt3000_c_partition_map_valid(&m, parts, n);
        printf("%d %d\n", valid, valid && rt3000_c_named_slots(parts, n));
    } else {
        printf("%d", hwd_partition_map_valid(&m, parts, n));
        for (i = 0; i < n; i++)
            if (hwd_write_window(parts[i].offset, parts[i].size, parts[i].name, 0, np.ramro_d))
                printf(" %s@0x%llx", parts[i].name, (unsigned long long)parts[i].offset);
        printf("\n");
    }
    free(s);
    return 0;
}
'''

def dt_map(path):
    text = path.read_text()
    m = re.search(r'h3c,storage-bootargs = "mtdparts=qcom_nand\.0:([^ "]+) ubi\.mtd=rootfs', text)
    return m.group(1)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    kernel = args.kernel.resolve(strict=True)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        results.append(name)

    src = out/'kernel/drivers/mtd'
    src.mkdir(parents=True)
    (src/'mtdpart.c').write_bytes((kernel/'drivers/mtd/mtdpart.c').read_bytes())
    applied = run(['patch', '--batch', '--fuzz=0', '-p1', '-d', out/'kernel', '-i', PATCH])
    (out/'patch.log').write_text(applied.stdout + applied.stderr)
    text = (src/'mtdpart.c').read_text()
    region = text[text.index('/* RT3000 C fail-closed physical NAND policy'):text.index('static u64 part_absolute_offset')]
    harness = out/'guard.c'
    harness.write_text(PRELUDE + region + MAIN)
    exe = out/'guard'
    run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
         '-Wno-sign-compare', '-fsanitize=undefined,address', '-fno-sanitize-recover=all', harness, '-o', exe])

    def guard(board, body, ramro=0):
        return run([exe, board, str(ramro), body]).stdout.split()

    c_dt = dt_map(ROOT/'rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-persistent.dts')
    d_dt = dt_map(ROOT/'target/linux/ipq50xx/dts/ipq5000-nx30-hw-d.dts')
    hi = '0x2800000@0x900000(oem_rootfs)ro,0x2800000@0x3100000(rootfs)'
    lo = '0x2800000@0x900000(rootfs),0x2800000@0x3100000(oem_rootfs)ro'
    single = '0x5000000@0x900000(rootfs)'
    check(hi in c_dt and lo in d_dt, 'DT maps have the expected slot entries')

    # C: two-slot maps in both orientations, then the single rootfs.
    check(guard('c', c_dt) == ['1', '1'], 'C: DT map valid, named slots')
    check(guard('c', c_dt.replace(hi, lo)) == ['1', '1'], 'C: swapped map valid, named slots')
    check(guard('c', c_dt.replace(hi, single)) == ['1', '1'], 'C: single rootfs valid, named (rootfs writable)')
    check(guard('c', c_dt.replace(hi, '0x5000000@0x900000(oem_rootfs)ro'))[0] == '0', 'C: single named oem_rootfs rejected')
    check(guard('c', c_dt.replace(hi, single+',0x2800000@0x3100000(rootfs)'))[0] == '0', 'C: single plus high slot rejected')
    check(guard('c', c_dt.replace(hi, single+','+single))[0] == '0', 'C: two single rows rejected')
    check(guard('c', c_dt.replace(hi, '0x5000000@0x3100000(rootfs)'))[0] == '0', 'C: 80 MiB at the high slot rejected')
    check(guard('c', c_dt.replace(hi, '0x2800000@0x900000(rootfs)'))[0] == '0', 'C: missing high slot rejected')

    # HW-D: the guard also checks names and write flags.
    check(guard('d', d_dt) == ['1', 'rootfs@0x900000'], 'D: DT map valid, low rootfs writable')
    check(guard('d', d_dt.replace(lo, hi)) == ['1', 'rootfs@0x3100000'], 'D: swapped map valid, high rootfs writable')
    check(guard('d', d_dt.replace(lo, single)) == ['1', 'rootfs@0x900000'], 'D: single rootfs valid and writable')
    check(guard('d', d_dt.replace(lo, single+'ro'))[0] == '0', 'D: read-only single rootfs rejected')
    check(guard('d', d_dt.replace(lo, single+'ro'), ramro=1) == ['1'], 'D: RAM read-only profile accepts read-only single, no write window')
    check(guard('d', d_dt.replace(lo, single), ramro=1) == ['0'], 'D: RAM read-only profile rejects writable single')
    check(guard('d', d_dt.replace(lo, '0x5000000@0x900000(oem_rootfs)ro'))[0] == '0', 'D: single named oem_rootfs rejected')
    check(guard('d', d_dt.replace(lo, single+',0x2800000@0x3100000(oem_rootfs)ro'))[0] == '0', 'D: single plus high slot rejected')
    check(guard('d', d_dt.replace(lo, single+','+single))[0] == '0', 'D: two single rows rejected')
    check(guard('d', d_dt.replace(lo, '0x5000000@0x3100000(rootfs)'))[0] == '0', 'D: 80 MiB at the high slot rejected')
    check(guard('d', d_dt.replace(lo, '0x2800000@0x900000(rootfs)'))[0] == '0', 'D: missing high slot rejected')
    check(guard('d', d_dt.replace(lo, '0x2800000@0x900000(rootfs),0x2800000@0x3100000(rootfs)'))[0] == '0', 'D: two rootfs slots rejected')

    (out/'results.json').write_text(json.dumps({'passed': len(results), 'checks': results}, indent=2)+'\n')
    print(json.dumps({'passed': len(results), 'output': str(out)}))

if __name__ == '__main__':
    main()
