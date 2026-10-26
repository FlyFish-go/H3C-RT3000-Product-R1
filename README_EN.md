# H3C Magic RT3000 · Product R1

[Simplified Chinese](README.md) · [HW-A/B/C/D classification and OEM evidence](docs/HW-ABCD-CLASSIFICATION.md) · [Hardware-variant research](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) · [Sample hardware configuration](rt3000-machine-b/docs/HARDWARE_SUPPORT.md) · [Support the project](#support-the-project) · [Test records](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md) · [Build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md) · [Known limitations](rt3000-machine-b/release/KNOWN_ISSUES.md)

This is a **device port based on Qualcomm QSDK 11.5 and OpenWrt 21.02.7**. It uses the QSDK vendor kernel, wireless drivers, and network acceleration stack; **it is not a mainline OpenWrt port**.

The long-term goal is to support the **RT3000 / RW3000 / RC3000 / NX30 families**. Starting with RT3000, the project investigates hardware differences on individual devices, brings up networking, Wi-Fi, NAND installation, and boot recovery, and then extends verified work to additional models.

**Product R1 is the first hardware milestone on this path:** basic functionality on RT3000 Machine B has passed staged validation, including NAND installation and OEM / QSDK dual-system booting, switching, and rollback. This establishes a foundation for other devices; family-wide support remains a future goal.

The current public release is **r6 Developer Preview (QSDK 11.5 HW-A/B/C/D)**: one source tree and one config build an image each for HW-A (RW3000), HW-B (RT3000), HW-C (RT3000 RTL8367S) and HW-D (NX30). Each group was tested on one of the project's units: written through the U-Boot rescue page, booted, upgraded in place with configuration kept, and cold-booted five times by power cycling with both Wi-Fi APs up. There is only one unit per group; see the scope and limitations below. Firmware files and SHA-256 checksums are in the [r6 Release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6); the r5 files remain available for the old RT3000 B installation method only.

The project is based on [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000), retaining the OpenWrt build structure, upstream copyright notices, and licenses.

## HW-A/B/C/D classification and QSDK 11.5 porting status

| Engineering group | Board characteristics / representative OEM machid | U-Boot `v0.1.0-pre.5` | QSDK 11.5 r6 |
|---|---|---|---|
| [**HW-A**](docs/HW-ABCD-CLASSIFICATION.md#hw-a) | Long board; IPQ5018 / external DDR / QCA8337; `0x08040001` | One of 84 candidates; passed on one unit | `h3c_rw3000_hw_a`: passed on one RW3000 |
| [**HW-B**](docs/HW-ABCD-CLASSIFICATION.md#hw-b) | Short board; IPQ5000 / integrated DDR / QCA8337; `0x08040000` | One of 84 candidates; passed on one unit | `h3c_rt3000`: passed on one RT3000 |
| [**HW-C**](docs/HW-ABCD-CLASSIFICATION.md#hw-c) | Long board; IPQ5018 / external DDR / RTL8367S; `0x08040101` | One of 84 candidates; passed on one unit | `h3c_rt3000_rtl8367s_native_slot1`: passed on one RT3000 |
| [**HW-D**](docs/HW-ABCD-CLASSIFICATION.md#hw-d) | NX30-type long board; IPQ5000 / integrated DDR / QCA8337; `0x08040000` | One of 84 candidates; passed on one NX30 | `h3c_nx30_hw_d`: passed on one NX30 |

**The same retail model can contain different engineering hardware groups. Both B and D can use OEM machid `0x08040000`; machid alone is not sufficient to select a flash image.** The [classification evidence from photos, OEM CDT/APPSBL, and control FDTs](docs/HW-ABCD-CLASSIFICATION.md) is documented separately from the [earlier physical RT3000 A/B/C research](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md). r6 images are per HW group and must match the group U-Boot detects; an image for the wrong group may leave Ethernet, Wi-Fi or booting broken.

## RT3000 A / B / C sample hardware

All three samples are on the Qualcomm IPQ50xx / QCN6102 AX3000 platform, with 256 MiB RAM, 128 MiB SPI-NAND, and 1 × WAN + 3 × LAN. Physical inspection has confirmed substantial differences in **SoC, RAM topology, NAND, Ethernet switch, PCB, and RF front-end population**:

| Sample | SoC / RAM | NAND | Ethernet switch | Hardware validation status |
|---|---|---|---|---|
| A | **IPQ5018** / external Winbond DDR | Winbond **W25N01GWZEIG** / 128 MiB | Qualcomm Atheros **QCA8337-AL3C** | Previously booted from RAM and enabled Wi-Fi; detailed functional validation was not completed |
| B | **IPQ5000** / integrated 256 MiB DDR3L | GigaDevice **GD5F1GQ5REYIG** / 128 MiB | Qualcomm Atheros **QCA8337-AL3C** | Product R1 r5 baseline; basic functions, NAND installation, and dual-system procedures passed staged testing |
| C | **IPQ5018** / external GigaDevice DDR | Winbond **W25N01GWZEIG** / 128 MiB | Realtek **RTL8367S** | Native08 on RT3000 C: native NAND installation to the non-OEM slot, cold boot, configuration persistence, and limited network/dual-band tests passed; initial DHCP behavior, rate reporting, and long-term stability remain open; not publicly released |

Sample A's NAND markings are `25N01GWZEIG / 2238 / 6206DS900`. During early exploration, **an immature APPSEL modification I made bricked Sample A**, so it can no longer be tested. A did previously run, but full functional testing was not completed at that time, and the current version has not been revalidated on A.

The 5 GHz radio hardware is **QCN6102**, while the QSDK software target is named `QCN6122` / `qcn6122`. The software baseline is QSDK 11.5, Linux 5.4.164, and OpenWrt 21.02.7. For full specifications, evidence scope, and sources, see the [sample hardware records](rt3000-machine-b/docs/HARDWARE_SUPPORT.md).

These configurations combine project records with further inspection of the physical samples. Similar specifications do not establish firmware interchangeability: B's acceptance results do not cover A/C or other batches. Other upstream Redmi / Xiaomi build targets in this repository have not thereby been revalidated by this project.

## Completed work

- Fixed the gigabit WAN receive clock configuration and checked link operation, DHCP, routing, and CRC behavior.
- Integrated RT3000 board configuration, the QCA8337 switch, and all three LAN ports.
- Installed and verified the QSDK NAND slot on Machine B while preserving the OEM slot; tested OEM / QSDK dual-system boot and rollback on hardware.
- Implemented a fail-closed dual-copy boot-selection process and a runtime identity check based on image contents.
- Implemented stable LAN / Wi-Fi MAC address derivation from each device's factory MAC, without hard-coding the developer sample's addresses.
- Fixed 5 GHz BDF compatibility and signal issues, integrating the complete ath11k NSS/WIFILI path.
- Retained WAN-side management isolation and per-device identity settings. The r5 image enables WPA2 access points on both bands by default, with phone association tested after installation and factory reset.

The earlier R1-NET-D and Product R1 pre-release acceptance tests cover different scopes from the later Wi-Fi experiments. See the [network baseline](rt3000-machine-b/docs/NETWORK_BRINGUP_CLOSURE.md), [pre-release acceptance](rt3000-machine-b/docs/PRODUCT_R1_PRERELEASE_1_ACCEPTANCE.md), and [latest staged records](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md).

## Wi-Fi performance: current status

Test path: iQOO Neo10 → RT3000 5 GHz HE160 → gigabit wired Windows PC. The following are iperf3 server-side TCP upload results, with each run lasting approximately 10 seconds.

| Condition | TCP upload |
|---|---:|
| One stream, primary channel 44, two tests | **760 / 789 Mbps** |
| Four streams, primary channel 36, comparison test | **879 Mbps** |
| RT3000 → PC wired-only, one-stream control | **937 / 938 Mbps** |

After basic bring-up, I explored 5 GHz throughput optimization; further expansion of that work is currently paused as planned. **The staged target of repeatedly achieving ≥800 Mbps single-stream upload has not been met.** Four-stream results, negotiated PHY rates, and one-second peaks cannot substitute for single-stream acceptance. Primary channel 44 remains the retained tested setting, but repeated A/B evidence is insufficient to establish why it helps; these results also do not establish the hardware's absolute performance ceiling.

The latest configuration uses `nss_offload=1 frame_mode=2` with generic `nss_redirect` disabled. C13's RXDMA capacity increase is active, but there is no evidence it resolved the upload bottleneck. The complete [CSV files and sanitized raw logs](rt3000-machine-b/docs/evidence/2026-09-21-wifi5/) and [tested image identity manifest](rt3000-machine-b/manifest/wifi5-candidate13-20260921.json) are provided with the source.

## Get the source and build

```sh
git clone https://github.com/FlyFish-go/H3C-RT3000-Product-R1.git
cd H3C-RT3000-Product-R1
```

This repository contains the OpenWrt build system, RT3000 porting sources, and patches. Kernel, toolchain, feeds, and other dependencies must be obtained according to the build rules. Start with the [public source build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md). r6 images are built from [`configs/h3c-magic.config`](configs/h3c-magic.config): copy it to `.config`, append one device line as described in its header (HW-C needs two more lines), then run `make defconfig && make`.

## Installation (r6): through the U-Boot rescue page

r6 does not use the r5 OEM-Telnet installation. Install the [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) U-Boot **v0.1.0-pre.5** first. Devices still on OEM firmware use the [BootBridge web tool](https://flyfish-go.github.io/H3C-NX30-Uboot/); devices with an older project U-Boot follow that project's pre.5 upgrade notes.

| HW group | First write (rescue page) | In-system upgrade |
|---|---|---|
| HW-A | `openwrt-ipq50xx-arm-h3c_rw3000_hw_a-squashfs-nand-factory.ubi` | `…-h3c_rw3000_hw_a-squashfs-sysupgrade.bin` |
| HW-B | `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi` | `…-h3c_rt3000-squashfs-sysupgrade.bin` |
| HW-C | `openwrt-ipq50xx-arm-h3c_rt3000_rtl8367s_native_slot1-squashfs-nand-factory.ubi` | `…-h3c_rt3000_rtl8367s_native_slot1-squashfs-sysupgrade.bin` |
| HW-D | `openwrt-ipq50xx-arm-h3c_nx30_hw_d-squashfs-nand-factory.ubi` | `…-h3c_nx30_hw_d-squashfs-sysupgrade.bin` |

1. Hold Reset while powering on to enter the rescue page; connect the PC to a **LAN** port and open `http://192.168.10.1`.
2. Back up both system slots under "Flash backup" first.
3. Under "Firmware update", write the group's `nand-factory.ubi` to the slot that does **not** hold the OEM system. Identify slots by offset (`0x900000` / `0x3100000`).
4. Set the default boot slot to the slot you just wrote and power-cycle.
5. Later upgrades: upload `sysupgrade.bin` in LuCI "Backup / Flash Firmware"; configuration can be kept.

QSDK boots from either system slot and also from the 80 MiB single partition created by the U-Boot "Partition table update" page. The single partition erases the OEM system; use it only when the OEM system is no longer needed. The r6 release images were tested in the non-OEM slot; booting from either slot and from the single partition was tested on all four groups with the previous build of the same source.

## r6 default management and access

- LAN address `192.168.10.1`; LuCI at `http://192.168.10.1/`; SSH listens on LAN only.
- A fresh installation has no root password; set one on first login.
- 2.4 GHz `OpenWrt` and 5 GHz `OpenWrt-5G` are enabled with WPA2, default key `12345678`, country CN. These are public defaults; change them before regular use.
- MAC addresses follow the OEM numbering: WAN is the factory address; LAN, 2.4 GHz and 5 GHz are factory +1, +2 and +3. Upgrading from r5 changes these three addresses.
- Wi-Fi calibration is read from each unit's own ART partition at boot; the images contain no unit's calibration data.

## Repository layout

| Path | Purpose |
|---|---|
| `target/linux/ipq50xx/` | RT3000 DTS, networking, and system integration |
| `package/kernel/mac80211/` | ath11k, NSS/WIFILI, and diagnostic patches |
| `package/firmware/ipq-wifi/` | Model-specific BDF files and packaging rules |
| `rt3000-machine-b/tools/` | BDF construction and restricted device-control tools |
| `rt3000-machine-b/tests/`, `tests/wifi/` | Offline regression and configuration checks |
| `rt3000-machine-b/docs/` | Acceptance, experiments, builds, and sanitization documentation |
| `rt3000-machine-b/manifest/` | Identity records for tested images and their evidence |

## Known limitations

r6: each group was tested on one project unit only; other NAND parts and batches are unverified. Wired WAN↔LAN routing is accelerated by NSS/ECM (about 940 Mbps on the bench); bridged traffic between Wi-Fi and wired LAN is forwarded by the CPU and not accelerated. HW-C/HW-D keep the OEM Q6 memory reservation, about 21 MiB more than HW-A/B, leaving about 52 MB available at idle (HW-A/B about 72 MB). 10/100 Mbps, long-running stability and LEDs/buttons are not fully verified.

Comprehensive testing of 10/100 Mbps Ethernet, physical WAN cable reconnection, long-running stability, LEDs/buttons, and C13 simultaneous dual-band operation has not been completed. Recent wired controls and LAN-bridge wireless throughput tests do not qualify all WAN/NAT scenarios. See [KNOWN_ISSUES](rt3000-machine-b/release/KNOWN_ISSUES.md).

## Support the project

I currently develop and maintain this project independently. To expand from RT3000 to RW3000, RC3000, and NX30, my greatest need is physical hardware that I can repeatedly test at my workbench. You can support the project in the following ways:

1. **Physical device donations or loans (highest priority).** If you have spare RT3000 / RW3000 / RC3000 / NX30 units, especially with different NAND, switch, or PCB revisions, please contact me about donating or lending them. Working devices are most helpful. For faulty units, boards, or parts, please share the model and condition first so I can determine their usefulness for repair and research.
2. **Financial sponsorship / donations.** Support can help cover test-device purchases and repairs, debugging accessories, shipping, and the continuing cost of hands-on porting and validation. Please contact me by email to discuss arrangements.
3. **Testing and technical evidence.** Board photos, chip markings, OEM firmware versions, and sanitized test logs can help reduce duplicated investigative work.

**Contact: [yufeiyang45@qq.com](mailto:yufeiyang45@qq.com).** For device offers, please specify the model, hardware revision, condition, and whether you propose a donation or a loan. Arrange shipping by email before sending anything.

Support sustains ongoing development, but it does not guarantee completion dates or compatibility for any particular model. Thank you to anyone able to provide devices, evidence, or funding to keep the work moving.

## Contributors

This project's current development and maintenance are carried out independently by [FlyFish-go](https://github.com/FlyFish-go).

## Feedback and sanitization

Please use [GitHub Issues](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues) to report hardware revisions, image SHA-256 hashes, reproduction steps, and sanitized logs. For throughput reports, specify upload or download direction, stream count, server topology, and server-side summaries.

The public snapshot excludes local development history, notification tokens, SSH private keys, original device-specific ART/partition backups, full packet captures, and development-environment paths. Sample identities and test fixtures in the documentation have been sanitized, while production code continues to read each device's own identity. See the [publication scope](rt3000-machine-b/docs/PUBLICATION.md).

## Upstream and licenses

Thanks to [OpenWrt](https://github.com/openwrt/openwrt), [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000), and the relevant Qualcomm/QSDK maintainers. Upstream copyrights, authorship, SPDX notices, and licenses are preserved. License texts are available in [COPYING](COPYING) and [LICENSES](LICENSES/). Each component remains subject to its original license; this public release does not alter third-party licensing terms.

This is an independent porting project and is not affiliated with H3C.
