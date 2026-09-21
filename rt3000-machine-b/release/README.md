# H3C Magic RT3000 (Machine-B) — OpenWrt / QSDK Developer Preview

OpenWrt 21.02.7 with the Qualcomm QSDK 11.5 stack, ported to the H3C Magic
RT3000 (Machine-B revision).

| | |
|---|---|
| SoC | Qualcomm IPQ5018 |
| Platform | QSDK 11.5 (NHSS.QSDK.11.5.0.5) |
| Kernel | Linux 5.4.164 |
| Userspace | OpenWrt 21.02.7 (r16847-f8282da11e) |
| RAM / flash | 256 MiB / 128 MiB NAND |
| Release | **Product R1 RC1 — Developer Preview** |

## What this is

A dual-slot firmware for the RT3000. The OEM firmware stays in its own flash
slot and is preserved; this image occupies the second slot. A hardware-validated
selector decides which slot boots, so a bad flash is recoverable — see
[RECOVERY.md](RECOVERY.md).

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

- Default LAN address: `192.168.1.1` (within this device's own LAN)
- LuCI: `http://192.168.1.1/`
- **No root password is set on a fresh install.** Set one immediately, before
  connecting the device to any untrusted network. See [INSTALL.md](INSTALL.md).
- WAN management (SSH and LuCI) is **denied by default**.
- Current source defaults: **2.4 GHz enabled**, SSID `RT3000`, open authentication,
  bridged to LAN for debugging. **5 GHz remains disabled**. Configure wireless
  encryption before daily use. This source change has not been rebuilt or
  hardware-validated; earlier RC1 images used different defaults.

## Documentation

- [INSTALL.md](INSTALL.md) — installation and first-time setup
- [RECOVERY.md](RECOVERY.md) — returning to the OEM firmware
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — open issues and limitations
- Release-specific SHA256SUMS accompanies a binary release; this source snapshot does not publish one.

## License

OpenWrt components retain their upstream licenses. Qualcomm QSDK components are
subject to Qualcomm's license terms and are not redistributed here.
