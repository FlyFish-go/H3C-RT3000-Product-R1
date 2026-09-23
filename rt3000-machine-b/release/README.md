# H3C Magic RT3000 (Machine-B) — OpenWrt / QSDK Developer Preview

OpenWrt 21.02.7 with the Qualcomm QSDK 11.5 stack, ported to the H3C Magic
RT3000 test unit designated Machine-B by this project.

| | |
|---|---|
| SoC | Qualcomm IPQ5018 |
| Platform | QSDK 11.5 (NHSS.QSDK.11.5.0.5) |
| Kernel | Linux 5.4.164 |
| Userspace | OpenWrt 21.02.7 (r16847-f8282da11e) |
| RAM / flash | 256 MiB / 128 MiB NAND |
| Release | **Product R1 r5 — Developer Preview** |

## What this is

A dual-slot firmware validated on one RT3000 Machine-B. The installation writes
the second flash slot (`mtd16`) and leaves the OEM system slot (`mtd15`) untouched.
The boot selector chooses the next slot. Automatic recovery after a failed QSDK
boot and power loss during writing have not been tested; see
[the recovery guide](05-RECOVERY.md).

Current family roadmap and A/B/C support status: [project README](../../README.md)
and [hardware records](../docs/HARDWARE_SUPPORT.md). This page describes the B-machine release line.

## Hardware validated

These were exercised on physical hardware for this release line:

- **WAN 1000BASE-T** — link, RX datapath, FCS/CRC clean, DHCP lease obtained
- **WAN RX / DHCP / routing** — gateway and internet reachable
- **LAN 1/2/3** — baseline link and throughput
- **QCA8337** external switch — registers and forwards
- **Wi-Fi 2.4 GHz** — brings up as an AP
- **Wi-Fi 5 GHz** — brings up as an AP
- **OEM rollback** — the OEM slot still boots after this firmware is installed

## Explicitly NOT claimed

- 100BASE-T qualification
- 10BASE-T qualification
- Physical WAN unplug/replug qualification
- Long-uptime / soak qualification
- Final NSS/ECM offload performance validation
- LED and button support

Only 1000BASE-T was exercised. 100 Mbit and 10 Mbit operation is *not* claimed
to work, and neither is link re-negotiation after a physical cable event.

## Management

- Default LAN address: `192.168.10.1` (within this device's own LAN).
  This is the QSDK LAN default; the OEM management address depends on how it is connected.
- LuCI: `http://192.168.10.1/` · web terminal (TTYD): `http://192.168.10.1:7681/`
- **No root password is set on a fresh install.** Set one immediately, before
  connecting the device to any untrusted network. See [INSTALL.md](INSTALL.md).
- **SSH is bound to the LAN interface by default.** The tested WAN-side connection
  did not expose SSH or LuCI.
- Wi-Fi defaults in r5: **both bands enabled as WPA2 APs** —
  2.4 GHz `RT3000` and 5 GHz `RT3000-5G`, key `RTRCRWNX`.
  **Change this key before daily use**; it is a published default, not a secret.
  These defaults are hardware-validated in r5. Earlier RC1/C13 test images used
  different defaults; their records do not describe this build.

## Documentation

- **[INSTALL.md](INSTALL.md) — 完整安装教程（获取 telnet → 安装 QSDK → 双向切换 → 升级 → 救援）**
- [tools/README.md](tools/README.md) — Windows helper scripts and the slot-selector tool
- [05-RECOVERY.md](05-RECOVERY.md) — failure triage and recovery boundaries
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — open issues and limitations
- [RELEASE-NOTES-r5.md](RELEASE-NOTES-r5.md) — this release and asset checksums
- Release binaries are published as **GitHub Release assets**, together with a
  `SHA256SUMS` file. Firmware images are not committed to the source tree.
- [../docs/PUBLICATION.md](../docs/PUBLICATION.md) — what is and is not published

## License

OpenWrt components retain their upstream licenses. Qualcomm QSDK components are
subject to Qualcomm's license terms and are not redistributed here.
