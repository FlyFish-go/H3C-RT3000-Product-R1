# Known issues — Product R1 r5 (Developer Preview)

The r5 installation and upgrade path is verified on Machine-B. Earlier RAM-only
C13 performance measurements remain separate: [2026-09-21 session](../docs/WIFI5_SESSION_2026-09-21.md).
Repeated single-stream 800 Mbps Wi-Fi upload has not been established for this release.

## Not yet qualified

| Area | Status |
|---|---|
| 100BASE-T | **Not qualified.** Only 1000BASE-T was exercised. |
| 10BASE-T | **Not qualified.** |
| Physical WAN unplug/replug | **Not qualified.** Link re-negotiation after a cable event has not been tested. |
| Long uptime / soak | **Not qualified.** No multi-day run has been performed. |
| NSS / ECM offload performance | **Not validated.** Offload is not tuned in this release. |

## Known limitations in this release

- **Wi-Fi defaults were changed in r5 and are now verified on hardware.**
  Both bands come up as WPA2 APs: 2.4 GHz `RT3000` and 5 GHz `RT3000-5G`,
  key `RTRCRWNX`. **Change this key before daily use** — it is a published
  default, not a secret.
  Earlier RC1/C13 test images used different defaults and do not describe this build.
- **Wi-Fi association bug fixed in r5.** r4 clients could authenticate and
  associate but never completed the key handshake. Root cause and the fix are
  described in the release notes and in
  `package/network/services/hostapd/patches/803-nl80211-only-set-VLAN-ID-when-non-zero.patch`.
  Note that **not every earlier build showed this symptom**, and why some builds
  did not is still not fully determined.
- **A previously RAM-booted with Wi-Fi enabled but was not fully tested; an early APPSEL modification later bricked it. The current release remains unverified on A. C is unsupported:**
  Ethernet switch adaptation is incomplete. RW3000, RC3000 and NX30 are planned
  targets, not validated devices. See [hardware records](../docs/HARDWARE_SUPPORT.md).
- **No root password on a fresh install.** Set one on first boot.
  WAN management is blocked regardless, but LAN access is unprotected until
  you do.
- **LEDs and buttons are not supported.** The device tree does not wire them.
- **No OEM web-OTA integration.** Use the slot workflow described in
  [RECOVERY.md](RECOVERY.md).
- **Per-unit LAN/Wi-Fi MAC addresses are derived, not factory.** Only the WAN
  address is the factory-assigned value. LAN and Wi-Fi addresses are derived
  deterministically from it so that they are stable across reboots and factory
  resets; they are locally-administered addresses and carry no vendor claim.
- **The WAN address is the only globally unique per-unit identity.** If the
  factory environment is missing or invalid, the system refuses to invent one
  and falls back to kernel defaults rather than generating addresses.

## Reporting

Include the release identifier, the artifact SHA256, and the output of
`cat /etc/rt3000-release.json` with any report.
