# BASE-SDK — the base SDK this repository is a delta against

This repository is **not** a wholesale QSDK source copy. It is the **Machine-B reproducibility
layer**: the board integration, config and patches that, applied on top of the base SDK below,
reproduce the hardware-tested `R1-NET-D` network baseline.

```
base SDK  +  Machine-B delta (this repo)  =  R1-NET-D
```

---

## Base SDK provenance

| Item | Value |
|---|---|
| Upstream repository | `https://github.com/hzyitc/openwrt-redmi-ax3000.git` |
| Upstream commit (worktree HEAD at freeze) | `96eac2e4467d772126270c1b1c88c49a75ff5020` |
| Upstream commit subject | `Machine-B M1: accept minimal B delta in ipq5000-rt3000 DTS` |
| Upstream commit date | 2026-09-07 21:53:21 +0800 |
| Branch | `machine-b-ram-muse-20260907` |
| History depth at freeze | 14 commits |
| Parent worktree | `openwrt-redmi-ax3000` @ `e3243d0` (branch `campaign12-replay`) |

This worktree is a `git worktree` of the parent checkout:
`.git` is a **file** containing
`gitdir: .../openwrt-redmi-ax3000/.git/worktrees/openwrt-redmi-ax3000-machine-b-muse`.

## Platform

| Item | Value |
|---|---|
| SoC | Qualcomm IPQ5018 (`ipq50xx`) |
| Board | H3C Magic RT3000, Machine B |
| OpenWrt base | 21.02.7 (`r16847-f8282da11e`) |
| Kernel | Linux **5.4.164** (QSDK 11.5 / `5.4-qsdk-11.5.0.5`) |
| QSDK | NHSS.QSDK.11.5.0.5 |
| Target | `ipq50xx/arm`, device profile `h3c_rt3000` |
| Flash | 128 MiB NAND, `BLOCKSIZE := 128k` |

## Feed revisions

```
src-git-full packages    https://git.openwrt.org/feed/packages.git^48242ee7a
src-git-full luci        https://git.openwrt.org/project/luci.git^e98243ef9e
src-git-full routing     https://git.openwrt.org/feed/routing.git^8071852
src-git-full telephony   https://git.openwrt.org/feed/telephony.git^920fbc5
```

## Build configuration

```
CONFIG_TARGET_ipq50xx=y
CONFIG_TARGET_ipq50xx_arm=y
CONFIG_TARGET_MULTI_PROFILE=y
CONFIG_TARGET_DEVICE_ipq50xx_arm_DEVICE_h3c_rt3000=y
```

The full `.config` is ~126 KB and is **not** committed (it is gitignored, and it is a generated
artifact rather than hand-maintained source). Record its identity by hash instead — see
`manifests/r1-net-d.json`.

## Build environment

| Item | Value |
|---|---|
| Host | WSL2 Ubuntu 22.04 (`Ubuntu-22.04`), accessed from a local terminal (a Windows workstation) |
| Source root | `/home/builder/build/RT3000-QSDK11.5-EVAL-20260824/openwrt-redmi-ax3000-machine-b-muse` |
| Toolchain | `arm-openwrt-linux-muslgnueabi-gcc` 8.4.0 |

Build commands that produced R1-NET-D:

```
make package/kernel/qca/qca-ssdk/compile
make package/install
make target/install
```

Output: `bin/targets/ipq50xx/arm/openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi`

## Reproducing R1-NET-D

1. Check out the base SDK at the commit above.
2. Apply the patch stack, in order:
   - `patches/qca-ssdk/0201-add-swconfig_leds-support.patch` (base-SDK-relative, already upstream)
   - `patches/qca-ssdk/0902-rt3000-r1-net-d-non-force-port-clock.patch` ← **the R1-NET-D fix**
3. Apply the board delta recorded in this repo (`patches/board/`) — MDIO1 pinmux, `phy-reset-gpio`,
   PHY children 0/1/2, QCA8337 / `ess-switch1`, `port_phyinfo`, two-switch board model.
4. Use the committed config fragments in `config/`.
5. Build with the commands above.
6. Verify the result against `manifests/r1-net-d.json` — the firmware and packaged `qca-ssdk.ko`
   hashes must match.

## Known deviation from upstream

The R1-NET-D build includes `rt3bcwrite` and `rt3slot` as device packages
(`package/rt3bcwrite/`, `package/rt3slot/`, wired in by `target/linux/ipq50xx/image/Makefile`).
These are project tools, not upstream OpenWrt packages.
