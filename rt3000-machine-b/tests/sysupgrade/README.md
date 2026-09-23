# Machine-B sysupgrade gate tests

`test_upgrade.py` runs the actual upgrade helper in an unprivileged user namespace and a disposable chroot. It never exposes the host `/dev` or `/sys`. Requirements: Linux user namespaces, static BusyBox, Python 3, the build tree's host fwtool and a host jsonfilter built from the same pinned source.

The test uses `staging_dir/host/bin/jsonfilter` by default. If that host binary is not present, build it from the pinned jsonfilter sources and host libubox/libjson-c archives, then pass its path with `RT3_JSONFILTER_HOST`. By default the test also reads the completed RT3000 sysupgrade image from `bin/targets/ipq50xx/arm/` and host `fwtool` from `staging_dir/host/bin/`. In a source-only checkout, download and verify the r5 sysupgrade release asset and point `RT3_SYSUPGRADE_IMAGE` at it; point `RT3_FWTOOL_HOST` at a trusted host build of fwtool:

```sh
RT3_JSONFILTER_HOST=/path/to/host/jsonfilter \
RT3_FWTOOL_HOST=/path/to/host/fwtool \
RT3_SYSUPGRADE_IMAGE=/path/to/verified/sysupgrade.bin \
  python3 rt3000-machine-b/tests/sysupgrade/test_upgrade.py
```

Coverage includes valid images, metadata/board/geometry/partition/BOOTCONFIG rejection, malformed or duplicate archive members, payload corruption, live-root and unrelated-UBI rejection, ordered slot selection, exact payload readback, and failures during formatting, attachment, volume creation, payload writing and configuration restoration. This models error handling; it does not simulate NAND hardware or prove bootability.
