<div align="center">

# H3C Magic · QSDK 11.5 Firmware

**Qualcomm QSDK 11.5 OpenWrt firmware for the H3C RT3000 / RW3000 / RC3000 / NX30**

All four board variants running on real hardware · NSS-offloaded wired NAT at ~940 Mbps · dual-band Wi-Fi 6 · coexists with the stock firmware

[![Release](https://img.shields.io/badge/release-r6-e76f51)](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6)
[![QSDK](https://img.shields.io/badge/QSDK-11.5-2a9d8f)](#)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-21.02.7-00a3e0)](#)
[![Kernel](https://img.shields.io/badge/Linux-5.4.164-555)](#)
[![Stars](https://img.shields.io/github/stars/FlyFish-go/H3C-RT3000-Product-R1?style=social)](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/stargazers)

### [⬇️ Download r6](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6)

[Install](#install) · [Install U-Boot first (BootBridge)](https://github.com/FlyFish-go/H3C-NX30-Uboot) · [Performance](#performance) · [Community](#community-and-feedback) · [简体中文](README.md)

</div>

## Why QSDK

These routers use Qualcomm IPQ50xx (IPQ5018 / IPQ5000) with a QCN6102 5 GHz radio. This project uses the vendor kernel, wireless drivers and NSS acceleration stack from Qualcomm's SDK rather than mainline OpenWrt:

- **⚡ NSS offload**: wired WAN↔LAN routing goes through NSS/ECM; 939–942 Mbps on all four boards with low CPU load (about 1.5% measured on HW-A).
- **📶 Dual-band Wi-Fi 6**: 2.4 GHz + 5 GHz (QCN6102) on ath11k 2.7 firmware, with each unit's own calibration data read from its ART partition at boot.
- **🧩 One tree, four boards**: one source tree and one config build an image for each of HW-A/B/C/D, with the same defaults and the same sysupgrade path.
- **🔀 Stock firmware stays**: with [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) the firmware goes into the other system slot and you can switch back at any time. A merged 80 MiB partition is also supported.
- **🏷️ Device identity kept**: MAC addresses follow the stock scheme from the unit's factory address; images contain no per-device data.

## Supported devices

| Board | Retail model | SoC / switch | r6 image | Tested |
|---|---|---|---|:---:|
| **HW-A** | RW3000 / RC3000 | IPQ5018 · QCA8337 | `H3C-Magic-r6-HW-A-*` | ✅ RW3000 |
| **HW-B** | RT3000 | IPQ5000 · QCA8337 | `H3C-Magic-r6-HW-B-*` | ✅ RT3000 |
| **HW-C** | RT3000 | IPQ5018 · RTL8367S | `H3C-Magic-r6-HW-C-*` | ✅ RT3000 |
| **HW-D** | NX30 / RX3000 | IPQ5000 · QCA8337 | `H3C-Magic-r6-HW-D-*` | ✅ NX30 |

One retail model can use different boards (the RT3000 exists as HW-B and HW-C). **Pick the image for the "Hardware Family" shown on the U-Boot rescue page, not by model name or machid.** The wrong image can break Ethernet, Wi-Fi or booting. See the [HW-A/B/C/D classification](docs/HW-ABCD-CLASSIFICATION.md).

## Performance

r6 release images, one unit per board. iperf3 with 4 streams, MT7921 client (Wi-Fi 6, 2×2, close range); wired NAT is LAN → router NAT → WAN. Mbps, upload / download:

| Board | 5 GHz HE80 | 2.4 GHz HE20 | Wired NAT | Idle free memory |
|---|---|---|---|---|
| HW-A | 646 / 729 | 216 / 102 | **942 / 942** | ~73 MB |
| HW-B | 727 / 692 | 200 / 114 | **941 / 942** | ~72 MB |
| HW-C | 672 / 774 | 213 / 187 | **941 / 942** | ~52 MB |
| HW-D | 727 / 729 | 188 / 174 | **939 / 939** | ~53 MB |

Wireless numbers are limited by the test client (2×2, HE80), not the router. An earlier phone test on RT3000 at HE160 reached 760–789 Mbps single-stream upload; see [history](#history).

## Install

**Prerequisite:** U-Boot **v0.1.0-pre.5** from [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot). Devices still on stock firmware install it with [BootBridge Web](https://flyfish-go.github.io/H3C-NX30-Uboot/), no disassembly or serial cable needed.

| Board | First install (rescue page) | Upgrade (LuCI) |
|---|---|---|
| HW-A | `H3C-Magic-r6-HW-A-nand-factory.ubi` | `H3C-Magic-r6-HW-A-sysupgrade.bin` |
| HW-B | `H3C-Magic-r6-HW-B-nand-factory.ubi` | `H3C-Magic-r6-HW-B-sysupgrade.bin` |
| HW-C | `H3C-Magic-r6-HW-C-nand-factory.ubi` | `H3C-Magic-r6-HW-C-sysupgrade.bin` |
| HW-D | `H3C-Magic-r6-HW-D-nand-factory.ubi` | `H3C-Magic-r6-HW-D-sysupgrade.bin` |

1. Power off, hold Reset, power on to enter the rescue page; connect to a **LAN** port and open `http://192.168.10.1`.
2. Back up both system slots under "Flash Backup".
3. Under "Firmware Update", write the board's `nand-factory.ubi` to the slot that does **not** hold the stock firmware. Identify slots by offset (`0x900000` / `0x3100000`).
4. Make that slot the default and power-cycle.
5. Later upgrades: upload `sysupgrade.bin` in LuCI "Backup / Flash Firmware"; settings are kept.

To go back to stock, set the default slot back to the stock one on the rescue page.

QSDK also runs from the 80 MiB partition created by U-Boot's partition-table page. That layout erases the stock firmware; use it only if you no longer need it.

### Defaults

- LAN `192.168.10.1`, LuCI at `http://192.168.10.1/`; SSH on LAN only.
- No root password on a fresh install; set one at first login.
- 2.4 GHz `OpenWrt` and 5 GHz `OpenWrt-5G`, WPA2, key `12345678`, country CN. These are public defaults; change them.
- MACs follow the stock scheme: WAN = factory address, LAN / 2.4 GHz / 5 GHz = +1 / +2 / +3. Upgrading from r5 changes these three.

## Test scope and known limitations

One unit per board, using the exact r6 release files: write to the non-stock slot from the rescue page → boot checks (model, slot, MTD map, no UBI errors) → in-place upgrade keeping settings → five power-cycle cold boots, each with both radios and both APs up and no firmware asserts. All four boards passed.

- One unit per board; other NAND parts and batches are untested.
- LAN-side bridging between Wi-Fi and Ethernet is forwarded by the CPU, not NSS; WAN↔LAN routing is offloaded.
- HW-C / HW-D keep the stock Q6 memory reservation and have ~20 MB less free memory than HW-A / HW-B.
- 10/100 Mbps, long-term operation and LEDs / buttons are not fully verified.

See [KNOWN_ISSUES](rt3000-machine-b/release/KNOWN_ISSUES.md).

## Building

```sh
git clone https://github.com/FlyFish-go/H3C-RT3000-Product-R1.git
cd H3C-RT3000-Product-R1
```

Read the [public build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md) first. r6 images are built from [`configs/h3c-magic.config`](configs/h3c-magic.config): copy it to `.config`, append the device line described in its header (two more lines for HW-C), then run `make defconfig && make`.

| Path | Contents |
|---|---|
| `target/linux/ipq50xx/` | DTS, networking and system integration for the four boards |
| `package/kernel/mac80211/` | ath11k, NSS/WIFILI and diagnostic patches |
| `package/firmware/ipq-wifi/` | Per-model BDF files and packaging |
| `configs/` | r6 build configuration |
| `docs/` | Board classification and hardware research |
| `rt3000-machine-b/` | Tools, tests, acceptance records and image manifests |

## Community and feedback

- **QQ group: 1131957442** (questions, discussion and bug reports)
- [GitHub Issues](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues): include the board (HW-A/B/C/D), image SHA-256, steps to reproduce and logs with serial numbers removed. For throughput, state direction, stream count and topology.

**If this firmware gave your router a second life, a ⭐ star helps other owners find it.**

## Support the project

This project is developed and maintained by one person. What helps most is hardware that can sit on the bench:

1. **Devices (highest priority).** Spare RT3000 / RW3000 / RC3000 / NX30 units, especially with different NAND, switch or PCB revisions, donated or lent. Working units help most; faulty units or boards are welcome after a short description.
2. **Funding** for buying and repairing units, debug accessories and shipping. Please get in touch by email.
3. **Data and testing.** Board photos, chip markings, stock firmware versions and redacted logs.

**Contact: [yufeiyang45@qq.com](mailto:yufeiyang45@qq.com)**. Please include model, hardware version, condition, and whether it is a donation or a loan; confirm shipping by email first. Support does not guarantee a schedule or result for any model.

## History

<details>
<summary>From one RT3000 to four boards (click to expand)</summary>

- **r5 (2026-09)**: first hardware milestone. RT3000 unit B (HW-B) passed staged validation: WAN gigabit receive clock fix, QCA8337 with three LAN ports, NAND install, OEM / QSDK dual boot and rollback, MAC derivation from the unit's factory address, 5 GHz BDF fixes and the full ath11k NSS/WIFILI path. r5 installs over the stock Telnet path; its files remain in the [r5 release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r5).
- **5 GHz throughput experiment (2026-09-21)**: iQOO Neo10 → RT3000 5 GHz HE160 → gigabit wired PC, 760 / 789 Mbps single-stream upload, 879 Mbps with four streams; wired control 937 / 938 Mbps. The ≥800 Mbps single-stream goal was not met at the time. See the [session notes](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md) and [raw data](rt3000-machine-b/docs/evidence/2026-09-21-wifi5/).
- **Hardware research**: physical inspection showed RT3000 units with different SoC, memory, NAND, switch and RF front end, which became the HW-A/B/C/D groups. See the [hardware research](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) and [sample configuration](rt3000-machine-b/docs/HARDWARE_SUPPORT.md).
- **r6 (2026-10-26)**: one source tree for HW-A (RW3000), HW-B (RT3000), HW-C (RT3000 RTL8367S) and HW-D (NX30); installation through the U-Boot rescue page; boot from either slot or the merged partition; RTL8367S driver; per-board BDFs.

</details>

## Upstream and licenses

Based on [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000). Thanks to [OpenWrt](https://github.com/openwrt/openwrt), hzyitc and the Qualcomm/QSDK maintainers. Upstream copyrights, authorship, SPDX notices and licenses are retained; see [COPYING](COPYING) and [LICENSES](LICENSES/).

The public snapshot excludes development history, keys, raw ART/partition backups and development directories; see [publication scope](rt3000-machine-b/docs/PUBLICATION.md).

Developed independently by [FlyFish-go](https://github.com/FlyFish-go). Not affiliated with H3C.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=FlyFish-go/H3C-RT3000-Product-R1,FlyFish-go/H3C-NX30-Uboot&type=Date)](https://star-history.com/#FlyFish-go/H3C-RT3000-Product-R1&FlyFish-go/H3C-NX30-Uboot&Date)
