# H3C Magic RT3000 · Product R1

[简体中文](README.md) · [Support the project](#support-the-project)

This is a **Qualcomm QSDK 11.5–based device adaptation project using OpenWrt 21.02.7**. It uses the QSDK vendor kernel, wireless drivers and network acceleration stack; **it is not a mainline OpenWrt port**.

The long-term goal is support for the **RT3000 / RW3000 / RC3000 / NX30 family**, starting with physical RT3000 hardware. Based on [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000), the repository publishes sanitized board integration, network fixes, NAND and boot-selection tooling, tests and development records.

**Product R1 is the first hardware milestone:** RT3000 Machine B has passed initial basic-function validation, including NAND installation and OEM / QSDK dual-system boot, switching and rollback. Family-wide support remains the roadmap.

**Developer Preview.** Earlier Product R1 builds have NAND and dual-system acceptance records. The latest Candidate 13 was tested through an initramfs RAM boot and is not an accepted flash release. This publication contains source and evidence, not a new firmware binary release.

## Support roadmap

| Target | Status |
|---|---|
| RT3000 Machine B | First hardware milestone; basic functions validated within the recorded test scope |
| RT3000 Machine A | Previously RAM-booted with Wi-Fi enabled and no kernel panic observed; not fully tested; later bricked after an early APPSEL change |
| RT3000 Machine C | Not passed / unsupported; Ethernet switch adaptation is incomplete |
| RW3000 | Planned; unverified |
| RC3000 | Planned; unverified |
| NX30 | Planned; unverified |

A/B/C identify project samples, not vendor revisions. Each board, switch and NAND combination needs its own validation. See [hardware records and evidence boundaries](rt3000-machine-b/docs/HARDWARE_SUPPORT.md).

## RT3000 A / B / C hardware

All three samples use **Qualcomm IPQ5018 / ARMv7, 256 MiB RAM, 128 MiB SPI-NAND, integrated 2.4 GHz Wi-Fi and external QCN6102 5 GHz Wi-Fi**, with one WAN and three LAN ports. The differences are:

| Sample | NAND | Ethernet switch |
|---|---|---|
| A | Winbond **W25N01GWZEIG**, 128 MiB | Qualcomm **QCA8337** |
| B | GigaDevice **GD5F1GQ5REYIG**, 128 MiB | Qualcomm **QCA8337** |
| C | Winbond **W25N01GWZEIG**, 128 MiB; same model as A | Realtek **RTL8367S** |

Sample A's chip markings are `25N01GWZEIG / 2238 / 6205DS900`. It could boot from RAM, enable Wi-Fi and run without a kernel panic during observation, but I had not completed detailed functional testing. **An immature APPSEL modification I made during early development subsequently bricked A**, preventing further testing. The current Product R1 / Candidate 13 has not been validated on A. C remains unsupported because Ethernet switch adaptation is incomplete.

This hardware mapping combines project records with my confirmation of the physical samples on September 22, 2026. QSDK represents QCN6102 as `QCN6122` / `qcn6122`. The software baseline is QSDK 11.5, Linux 5.4.164 and OpenWrt 21.02.7. Similar hardware does not establish cross-variant firmware compatibility. See the [detailed hardware records](rt3000-machine-b/docs/HARDWARE_SUPPORT.md).

## Progress

The project fixes the gigabit WAN RX clock path, integrates the LAN switch, has exercised NAND installation and OEM / QSDK dual-system boot and rollback, preserves the OEM fallback slot, validates redundant boot-selector updates, provides stable per-device MAC derivation, and improves BDF compatibility and the ath11k NSS/WIFILI path.

Wi-Fi performance work is currently paused. Latest server-side TCP upload results, approximately 10 seconds per test:

| Test | Mbps |
|---|---:|
| iQOO Neo10, one stream, HE160, primary channel 44 | **760 / 789** |
| Same phone, four streams, primary channel 36 | **879** |
| Router-to-PC wired one-stream controls | **937 / 938** |

**Repeated single-stream upload of at least 800 Mbps has not been achieved.** Four streams and one-second peaks do not satisfy that target. Channel 44 is the retained experimental configuration; a causal improvement and a hardware ceiling have not been established. See the [session report](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md), [CSV](rt3000-machine-b/docs/evidence/2026-09-21-wifi5/server-results.csv) and [manifest](rt3000-machine-b/manifest/wifi5-candidate13-20260921.json).

## Getting started

```sh
git clone https://github.com/FlyFish-go/H3C-RT3000-Product-R1.git
cd H3C-RT3000-Product-R1
```

Read the [build guide](rt3000-machine-b/docs/BUILD_PUBLIC.md). Kernel, toolchain and feed dependencies must be obtained separately. A clean-environment rebuild of the public export has not yet been certified.

## Installation: OEM firmware to the second slot

**Reserved section — procedure pending.** A verified guide will cover writing Product R1 from the OEM system to the second slot, booting it and retaining OEM rollback. No installation commands or new installable firmware release are supplied here yet.

| Step | Content to be added |
|---|---|
| Preparation | Hardware/OEM versions, image verification and tools |
| Backup and slot identification | Backup scope, second-slot identification and recovery preparation |
| Write from OEM firmware | Access method, image transfer, write steps and completion checks |
| Select and boot | Boot selection, first-boot expectations and failure handling |
| Verify and roll back | Runtime identity, basic checks and returning to OEM |

See the reserved [installation guide](rt3000-machine-b/release/INSTALL.md), existing B-machine [recovery records](rt3000-machine-b/release/RECOVERY.md) and [known issues](rt3000-machine-b/release/KNOWN_ISSUES.md). B-machine dual-system validation is already recorded; the user-facing OEM installation guide is still pending and cannot be applied to other variants. Candidate 13 remains a RAM-only diagnostic candidate.

## Default access

Default LAN management is `http://192.168.1.1/`. Set a root password on first use. WAN SSH/LuCI access is blocked by default and there is no shared factory password.

**The current source enables a 2.4 GHz debugging AP named `RT3000`, without a password, bridged to LAN.** Configure wireless encryption and a management password before daily use. 5 GHz remains disabled until configured.

This default-policy change applies to fresh initialization / factory reset with a newly built image. It has not been rebuilt or tested on hardware and does not alter the running device. Historical Candidate 13 measurements used 2.4 GHz disabled and do not validate simultaneous dual-band operation under these new defaults.

## Scope and privacy

10/100 Mbps Ethernet, physical WAN reconnects, long-duration operation, LEDs/buttons and C13 simultaneous dual-band operation are not fully qualified. LAN bridge measurements do not validate every WAN/NAT scenario.

Private development history, credentials, unit-specific ART/partition backups and packet captures are excluded. Test fixtures use synthetic identities; production code reads each device's own identity. See [publication notes](rt3000-machine-b/docs/PUBLICATION.md).

Report reproducible issues through [GitHub Issues](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues), including hardware revision, image hash, topology and sanitized logs. Upstream licenses and attribution are retained: [COPYING](COPYING), [LICENSES](LICENSES/). This is an independent project, unaffiliated with H3C.

## Support the project

I currently develop and maintain this project on my own. Expanding support to the RT3000 / RW3000 / RC3000 / NX30 family requires hardware I can repeatedly test. Support is welcome in the following order:

1. **Physical devices — my highest priority.** Donations or loans of RT3000 / RW3000 / RC3000 / NX30 units, especially different NAND, switch or PCB variants, are particularly useful. Working devices are most helpful; please describe faulty boards or spare parts first so I can assess their research or repair value.
2. **Financial sponsorship / donations.** Contributions can help cover sample purchases, repairs, debugging accessories and shipping. Please contact me by email to discuss how to contribute.
3. **Testing and documentation.** Hardware photographs, chip markings, OEM version information and sanitized test logs can also advance the work.

**Email: [yufeiyang45@qq.com](mailto:yufeiyang45@qq.com).** For hardware offers, include the model, revision, condition and whether you are offering a donation or a loan. Please arrange shipping with me first.

Support helps sustain development; it does not guarantee compatibility or a completion date for any model.

## Contributors

This project's current development and maintenance are carried out independently by [FlyFish-go](https://github.com/FlyFish-go). Upstream copyright, attribution and licenses remain intact.
