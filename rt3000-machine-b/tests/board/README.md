# HW-B board and boot-argument regression

Run from the WSL QSDK repository:

```sh
python3 rt3000-machine-b/tests/board/test_board.py \
  --kernel /absolute/path/to/prepared/qsdk-kernel \
  --output-dir /tmp/hwb-board-new-unique-directory
```

The output path must not exist. The test only reads the prepared kernel for DTS includes and `drivers/of/fdt.c`; it applies the source patch to a private copy and writes all DTBs, test executables and results under the output directory. It does not run OpenWrt make, access devices or update caches.

Requires Python 3, cpp, dtc/fdtget, GNU patch and a native GCC with UBSan. It compiles NAND and RAM DTBs under both ath11k memory selections, checks GPIOs/LED aliases/protected partitions, and compiles the actual patched chosen parser with the actual filter header. Tests exercise duplicate UBI selectors, quoted arguments, ECC/console/radio preservation, long inherited command lines, final-buffer boundaries, and CONFIG_CMDLINE default/extend/force. Non-B and unmarked legacy DT behavior are included.

These are offline checks, not a full kernel/firmware build or a hardware acceptance result. See [the dated source report](../../docs/HW-B-BOARD-FIXES-20261015.md).
