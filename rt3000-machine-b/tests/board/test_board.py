#!/usr/bin/env python3
"""Compile HW-B DTBs and exercise the actual patched early chosen parser offline.

Only writes to --output-dir. Does not run make, access a device or modify caches.
Requires a prepared QSDK kernel tree for read-only DTS includes and fdt.c.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]

def run(args, **kw):
    r = subprocess.run([str(x) for x in args], capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(str(args) + '\n' + r.stdout + r.stderr)
    return r

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    kernel = args.kernel.resolve(strict=True)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dtsdir = ROOT / 'target/linux/ipq50xx/dts'
    results = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        results.append(name)

    def prop(dtb, node, name, typ='s'):
        return run(['fdtget', '-t', typ, dtb, node, name]).stdout.strip()

    storage = {}
    for profile in ['ipq5000-rt3000', 'ipq5000-rt3000-initramfs']:
        for small in [False, True]:
            base = out / (profile + ('-256m' if small else '-default'))
            cpp = ['cpp', '-nostdinc', '-undef', '-D__DTS__', '-D__ARM32__',
                   '-D__IPQ_MEM_PROFILE_256_MB__', '-x', 'assembler-with-cpp',
                   '-I', kernel/'arch/arm/boot/dts', '-I', dtsdir,
                   '-I', kernel/'scripts/dtc/include-prefixes', '-I', kernel/'include']
            if small:
                cpp.append('-DCONFIG_ATH11K_MEM_PROFILE_256M')
            preprocessed = run(cpp + [dtsdir/(profile+'.dts')]).stdout
            base.with_suffix('.dts').write_text(preprocessed)
            compiled = run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', base.with_suffix('.dtb'), base.with_suffix('.dts')])
            base.with_suffix('.warnings').write_text(compiled.stderr)
            dtb = base.with_suffix('.dtb')
            check(prop(dtb, '/soc/gpio_keys/button_reset', 'gpios', 'x').split()[1:] == ['22', '1'], profile+': RESET34 active-low')
            check(prop(dtb, '/soc/gpio_keys/button_wps', 'gpios', 'x').split()[1:] == ['26', '1'], profile+': WPS38 unchanged')
            for color, pin in [('green', '18'), ('red', '17')]:
                node = '/leds/system_'+color
                check(prop(dtb, node, 'gpios', 'x').split()[1:] == [pin, '0'], profile+': '+color+' GPIO active-high')
                check(prop(dtb, node, 'label') == color+':system', profile+': '+color+' LED label')
            for state, color in [('boot','green'), ('running','green'), ('failsafe','red'), ('upgrade','red')]:
                check(prop(dtb, '/aliases', 'led-'+state) == '/leds/system_'+color, profile+': '+state+' alias')
            # Every critical protected partition remains read-only in the fallback DT.
            partitions = '/soc/nand@79b0000/nandcs@0/partitions'
            # Find NAND path from dtc output rather than assuming its parent unit name.
            decoded = run(['dtc', '-I', 'dtb', '-O', 'dts', dtb]).stdout
            check('label = "oem_rootfs";' in decoded and 'label = "rootfs_1";' not in decoded, profile+': fallback slot labels')
            for address in ['0', '80000', '480000', '500000', '640000', '780000', '900000']:
                body = re.search(r'partition@'+address+r' \{(.*?)\n\s*\};', decoded, re.S).group(1)
                check('read-only;' in body, profile+': protected partition '+address)
            storage[profile] = prop(dtb, '/chosen', 'h3c,storage-bootargs')
            check('root=' not in prop(dtb, '/chosen', 'bootargs-append'), profile+': generic append has no root selector')

    nand = storage['ipq5000-rt3000']
    ram = storage['ipq5000-rt3000-initramfs']
    check(nand.split()[0] == ram.split()[0], 'RAM/NAND identical physical partition map')
    check('0x2800000@0x900000(oem_rootfs)ro,0x2800000@0x3100000(rootfs)' in nand, 'fixed high-slot upgrade contract')
    check('ubi.mtd=rootfs' in nand and 'root=/dev/ubiblock0_1' in nand, 'NAND selects high rootfs')
    check(ram.endswith('rdinit=/init') and 'ubi.mtd=' not in ram and 'ubi.block=' not in ram and ' root=' not in ram, 'RAM never auto-attaches NAND')

    # Apply the real source patch to a private copy, with no fuzz.
    src = out/'kernel/drivers/of';src.mkdir(parents=True)
    (src/'fdt.c').write_bytes((kernel/'drivers/of/fdt.c').read_bytes())
    patch = ROOT/'target/linux/ipq50xx/patches/030-of-h3c-rt3000-storage-bootargs.patch'
    applied = run(['patch', '--batch', '--fuzz=0', '-p1', '-d', out/'kernel', '-i', patch])
    (out/'patch.log').write_text(applied.stdout+applied.stderr)
    text = (src/'fdt.c').read_text()
    function = text[text.index('int __init early_init_dt_scan_chosen(unsigned'):text.index('\n#ifndef MIN_MEMBLOCK_ADDR')]
    header = ROOT/'target/linux/ipq50xx/files/drivers/of/h3c_rt3000_bootargs.h'
    prelude = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <errno.h>
#include <setjmp.h>
#define __init
#define COMMAND_LINE_SIZE 1024
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
#define pr_debug(...) ((void)0)
#define fdt_nop_property(...) ((void)0)
#define fdt_totalsize(...) 0
#define crc32_be(...) 0
static int initial_boot_params, of_fdt_crc32;
static const char *incoming, *canonical, *extra;
static int board, malformed;
static jmp_buf bailout;
static void panic(const char *s) { (void)s; longjmp(bailout, 1); }
static void early_init_dt_check_for_initrd(unsigned long n) { (void)n; }
static void add_bootloader_randomness(const void *p, int l) { (void)p; (void)l; }
static unsigned long of_get_flat_dt_root(void) { return 0; }
static int of_flat_dt_is_compatible(unsigned long n, const char *c) {
    (void)n; return board && !strcmp(c,"h3c,rt3000");
}
static const char *of_get_flat_dt_prop(unsigned long n, const char *name, int *len) {
    const char *p = NULL; (void)n;
    if (!strcmp(name,"bootargs")) p=incoming;
    if (!strcmp(name,"bootargs-append")) p=extra;
    if (!strcmp(name,"h3c,storage-bootargs")) p=canonical;
    if (p && len) *len = strlen(p)+1-(!strcmp(name,"h3c,storage-bootargs") && malformed);
    return p;
}
static size_t strlcpy(char *d, const char *s, size_t n) {
    size_t len=strlen(s); if(n) {size_t c=len<n-1?len:n-1;memcpy(d,s,c);d[c]=0;}return len;
}
static size_t strlcat(char *d, const char *s, size_t n) {
    size_t used=strnlen(d,n);if(used==n)return n+strlen(s);
    return used+strlcpy(d+used,s,n-used);
}
'''
    main_c = r'''
int main(int argc, char **argv) {
    struct {unsigned char before[16]; char cmd[COMMAND_LINE_SIZE]; unsigned char after[16];} guarded;
    if(argc!=7)return 3;
    memset(&guarded,0xa5,sizeof(guarded));guarded.cmd[0]=0;
    incoming=argv[1];canonical=strcmp(argv[2],"NONE")?argv[2]:NULL;
    extra=argv[3];board=atoi(argv[4]);malformed=atoi(argv[5]);
    if(setjmp(bailout)) { puts("REFUSED"); return 0; }
    early_init_dt_scan_chosen(1,"chosen",1,guarded.cmd);
    for(int i=0;i<16;i++)if(guarded.before[i]!=0xa5 || guarded.after[i]!=0xa5)abort();
    puts(guarded.cmd);return 0;
}
'''
    harness = out/'chosen.c'
    harness.write_text(prelude+'\n#include '+json.dumps(str(header))+'\n'+function+main_c)
    for mode, flags in [('default', []), ('extend', ['-DCONFIG_CMDLINE="root=/wrong ubi.mtd=bad nandeccbits=8"', '-DCONFIG_CMDLINE_EXTEND']), ('force', ['-DCONFIG_CMDLINE="root=/wrong ubi.mtd=bad nandeccbits=8"', '-DCONFIG_CMDLINE_FORCE'])]:
        exe=out/('chosen-'+mode)
        run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-fsanitize=undefined', '-fno-sanitize-recover=all', *flags, harness, '-o', exe])
        def parse(raw, suffix, board=1, malformed=0, extra=' coherent_pool=2M loglevel=7'):
            return run([exe, raw, suffix, extra, str(board), str(malformed), 'unused']).stdout.strip()
        stale = ('console=ttyMSM0,115200n8 ubi.mtd=rootfs_1 ubi.mtd=rootfs '
                 'ubi.block=3,1 root=/dev/old rootfstype=ubifs rootflags=bad '
                 'rootwait rootdelay=4 rdinit=/bad init=/bad ro rw '
                 'mtdparts=old:40m(rootfs_1) nandspare=128 nandeccbits=4 cnss2.skip_radio_bmap=6')
        for label, suffix in [('nand',nand), ('ram',ram)]:
            final=parse(stale,suffix)
            check(final!='REFUSED', mode+': '+label+' accepts legacy bootargs')
            words=final.split()
            check(sum(x.startswith('ubi.mtd=') for x in words)==(label=='nand'), mode+': '+label+' unique attach')
            check(sum(x.startswith('root=') for x in words)==(label=='nand'), mode+': '+label+' unique root')
            check(sum(x.startswith('mtdparts=') for x in words)==1, mode+': '+label+' unique map')
            check(final.endswith(suffix),mode+': '+label+' canonical selectors last')
            if mode!='force':
                check('console=ttyMSM0,115200n8' in final and 'nandspare=128' in final and 'cnss2.skip_radio_bmap=6' in final, mode+': '+label+' preserves console/ECC/radio')
            if mode=='default':
                check('nandeccbits=4' in final, label+': preserves ECC4')
        check(parse(stale,nand,malformed=1)=='REFUSED', mode+': refuses malformed DT string')
        check(parse('x='+'a'*1100,nand)=='REFUSED', mode+': refuses oversized retained argument')
        if mode!='force':
            check(parse('x='+'a'*400,nand)=='REFUSED', mode+': refuses final truncation')
        if mode=='default':
            longmap='mtdparts=old:'+('x'*1800)+' nandeccbits=8 nandspare=128 console=ttyMSM0'
            final=parse(longmap,nand)
            check('nandeccbits=8' in final and final.endswith(nand), 'filters before copy; preserves ECC8 beyond old 1024-byte limit')
            check(parse('root="/wrong path" keep="root=not-a-selector text" "ubi.mtd=wrong"',ram).startswith('keep="root=not-a-selector text"'), 'quoted values and exact keys')
            check(parse('myroot=keep ubi.mtdfoo=keep',ram).startswith('myroot=keep ubi.mtdfoo=keep'), 'does not remove prefix-lookalikes')
            check(parse('keep="unclosed',ram)=='REFUSED', 'refuses unbalanced quoted commandline')
            check(parse(stale,'NONE')==stale+' coherent_pool=2M loglevel=7', 'unmarked B uses original chosen flow')
            check(parse(stale,nand,board=0)==stale+' coherent_pool=2M loglevel=7', 'non-B ignores custom property')
            # Exact final buffer boundary, including the required separator and NUL.
            prefix='x='+'a'*(1024-len(nand)-2-2)
            check(len(parse(prefix,nand,extra=''))==1023, 'exact 1024-byte capacity accepted')
            check(parse(prefix+'a',nand,extra='')=='REFUSED', 'one-byte excess refused')

    image=(ROOT/'target/linux/ipq50xx/image/Makefile').read_text()
    profile=image.split('define Device/h3c_rt3000\n',1)[1].split('\nendef',1)[0]
    check('DEVICE_DTS := ipq5000-rt3000 ipq5000-rt3000-initramfs' in profile, 'both DTBs registered with image_prepare')
    check('KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-rt3000.dtb' in profile, 'NAND FIT selects NAND DTB')
    check('KERNEL_INITRAMFS = kernel-bin | lzma | fit lzma $$(KDIR)/image-ipq5000-rt3000-initramfs.dtb' in profile, 'RAM FIT selects RAM DTB')
    (out/'results.json').write_text(json.dumps({'passed':len(results),'checks':results},indent=2)+'\n')
    print(json.dumps({'passed':len(results),'output':str(out)}))

if __name__=='__main__':
    main()
