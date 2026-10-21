# H3C Magic RT3000 · Product R1

[Simplified Chinese](README.md) · [HW-A/B/C/D classification and OEM evidence](docs/HW-ABCD-CLASSIFICATION.md) · [Hardware-variant research](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) · [Sample hardware configuration](rt3000-machine-b/docs/HARDWARE_SUPPORT.md) · [Support the project](#support-the-project) · [Test records](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md) · [Build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md) · [Known limitations](rt3000-machine-b/release/KNOWN_ISSUES.md)

This is a **device port based on Qualcomm QSDK 11.5 and OpenWrt 21.02.7**. It uses the QSDK vendor kernel, wireless drivers, and network acceleration stack; **it is not a mainline OpenWrt port**.

The long-term goal is to support the **RT3000 / RW3000 / RC3000 / NX30 families**. Starting with RT3000, the project investigates hardware differences on individual devices, brings up networking, Wi-Fi, NAND installation, and boot recovery, and then extends verified work to additional models.

**Product R1 is the first hardware milestone on this path:** basic functionality on RT3000 Machine B has passed staged validation, including NAND installation and OEM / QSDK dual-system booting, switching, and rollback. This establishes a foundation for other devices; family-wide support remains a future goal.

The current public release is **Product R1 r5 Developer Preview**. On RT3000 Machine B, r5 was installed into NAND from OEM firmware, read back and verified, booted, switched in both directions, upgraded while retaining configuration, and checked after factory reset. Phones successfully connected to both Wi-Fi bands. The earlier Wi-Fi Candidate 13 was a RAM-boot performance experiment and must not be treated as validation of the r5 flash image. Firmware artifacts and SHA-256 checksums are available in the [r5 Release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r5).

The project is based on [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000), retaining the OpenWrt build structure, upstream copyright notices, and licenses.

## HW-A/B/C/D classification and QSDK 11.5 porting status

| Engineering group | Board characteristics / representative OEM machid | U-Boot `v0.1.0-pre.1` | Current QSDK 11.5 evidence |
|---|---|---|---|
| [**HW-A**](docs/HW-ABCD-CLASSIFICATION.md#hw-a) | Long board; IPQ5018 / external DDR / QCA8337; `0x08040001` | Separate candidate; hardware testing pending in this round | Historical RAM-boot evidence; no independent QSDK acceptance completed |
| [**HW-B**](docs/HW-ABCD-CLASSIFICATION.md#hw-b) | Short board; IPQ5000 / integrated DDR / QCA8337; `0x08040000` | Separate candidate; hardware testing pending in this round | **RT3000 B Product R1 r5:** published Developer Preview with staged hardware validation |
| [**HW-C**](docs/HW-ABCD-CLASSIFICATION.md#hw-c) | Long board; IPQ5018 / external DDR / RTL8367S; `0x08040101` | Separate candidate; hardware testing pending in this round | **RT3000 C Native08:** local persistent installation and bounded functional validation; open issues remain; not publicly released |
| [**HW-D**](docs/HW-ABCD-CLASSIFICATION.md#hw-d) | NX30-type long board; IPQ5000 / integrated DDR / QCA8337; `0x08040000` | Limited testing passed for one specific NX30 candidate | Separate D `build03` candidate artifacts frozen; **no full-device acceptance** |

**The same retail model can contain different engineering hardware groups. Both B and D can use OEM machid `0x08040000`; machid alone is not sufficient to select a flash image.** The [classification evidence from photos, OEM CDT/APPSBL, and control FDTs](docs/HW-ABCD-CLASSIFICATION.md) is documented separately from the [earlier physical RT3000 A/B/C research](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md). The currently released r5 artifacts are only for the validated RT3000 B configuration. Local Native08 and D work **does not imply that additional public firmware downloads are available**.

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

This repository contains the OpenWrt build system, RT3000 porting sources, and patches. Kernel, toolchain, feeds, and other dependencies must be obtained according to the build rules. Start with the [public source build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md), which documents configuration, dependencies, past build outcomes, and clean-environment reproduction that has not yet been completed.

## Installation: from OEM firmware to the second slot

**Only RT3000 Machine B passed r5 hardware validation.** The image and flashing commands are not applicable to A/C samples or RW3000, RC3000, or NX30. Before proceeding, verify NAND, the partition table, and the OEM firmware version, then read the [full installation guide](rt3000-machine-b/release/INSTALL.md) and [r5 release notes](rt3000-machine-b/release/RELEASE-NOTES-r5.md).

The guide covers five parts: OEM Telnet, installation and readback, switching in both directions, firmware upgrades, and rescue. The documented normal procedure was repeated on Machine B on September 23, 2026. The OEM Telnet configuration import was not repeated in that round, while fault injection, power-loss behavior, and full U-Boot + TFTP rescue were not verified. Complete checksums are available in the release's `SHA256SUMS` attachment.

## r5 default management and access

- QSDK LAN address: `192.168.10.1`, with LuCI at `http://192.168.10.1/`; SSH binds only to LAN. The OEM system's management address depends on cabling and upstream DHCP.
- A fresh QSDK installation has no root password. Set one immediately on first login.
- The 2.4 GHz `RT3000` and 5 GHz `RT3000-5G` access points both use WPA2 by default, with the public default Wi-Fi password `RTRCRWNX`. Change it before everyday use.
- The r5 defaults above were checked on hardware after a fresh installation, configuration-preserving upgrade, and `sysupgrade -n`. The older RC1 / C13 test images used different defaults and must not be treated as r5.

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
