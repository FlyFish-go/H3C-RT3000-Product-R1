# Known issues — Product R1 RC1 (Developer Preview)

Latest RAM-only C13 status: [2026-09-21 session](../docs/WIFI5_SESSION_2026-09-21.md).
NSS/WIFILI and wired capacity have now been exercised; repeated single-stream
800 Mbps Wi-Fi upload remains unachieved. The table below describes the earlier RC1 release scope.

## Not yet qualified

| Area | Status |
|---|---|
| 100BASE-T | **Not qualified.** Only 1000BASE-T was exercised. |
| 10BASE-T | **Not qualified.** |
| Physical WAN unplug/replug | **Not qualified.** Link re-negotiation after a cable event has not been tested. |
| Long uptime / soak | **Not qualified.** No multi-day run has been performed. |
| NSS / ECM offload performance | **Not validated.** Offload is not tuned in this release. |

## Known limitations in this release

- **Current source uses an open 2.4 GHz debugging AP (`RT3000`) on LAN; 5 GHz remains disabled.**
  This default-policy change has passed offline tests but has not been rebuilt
  or tested on hardware. Configure encryption before daily use. Earlier RC1
  acceptance records retain their original disabled-by-default policy.
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
