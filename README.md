# H3C RT3000 Product R1

Community firmware project for the **H3C Magic RT3000 Machine-B** router.

> [!WARNING]
> This project is currently in **Developer Preview**.
>
> Firmware published here is intended for users who understand router
> flashing and recovery procedures.
>
> **Do not flash this firmware on hardware revisions other than the
> explicitly supported RT3000 Machine-B.**

## Current Status

Product R1 is based on:

- Qualcomm IPQ5018
- QSDK 11.5
- Linux 5.4.164
- OpenWrt 21.02.7

The project is currently preparing its first public Developer Preview.

## Verified Functionality

Current hardware validation includes:

- System boot
- NAND / UBI boot
- LAN networking
- WAN 1000BASE-T
- WAN DHCP and Internet connectivity
- 2.4 GHz Wi-Fi
- 5 GHz Wi-Fi
- LuCI web interface
- LAN-only management access
- OEM firmware rollback path
- Product/OEM boot selection and recovery tooling

## Not Fully Qualified Yet

The following items are not currently considered Developer Preview
blockers, but have not completed full qualification:

- 10BASE-T
- 100BASE-T
- Long-duration stability testing
- LED behaviour
- Hardware buttons
- Final NSS / ECM performance tuning

See `KNOWN_ISSUES.md` for release-specific details.

## Downloads

Firmware downloads will be published through
[GitHub Releases](../../releases).

Always verify the SHA256 checksum before flashing.

## Installation

Installation instructions will be available in:

- `INSTALL.md`
- `RECOVERY.md`

Read both documents before flashing.

## Bug Reports

Please use GitHub Issues for bug reports and installation feedback.

When reporting a problem, include as much of the following as possible:

- Hardware revision
- Original firmware version
- Product R1 release version
- Firmware SHA256
- Installation result
- WAN / LAN status
- 2.4 GHz / 5 GHz Wi-Fi status
- Relevant logs

Please do not post passwords, Wi-Fi keys, private keys, or other
credentials in public Issues.

## Source Code

This repository currently serves as the public release, documentation,
and issue-tracking portal for Product R1.

The internal development repository is not public at this stage.

Source-code availability and licensing information for distributed
components will be documented alongside applicable releases.

## Disclaimer

This is an independent community project and is not an official
firmware release from H3C.

Flashing third-party firmware carries a risk of data loss or device
failure. Make sure you understand the recovery procedure before
installing a Developer Preview build.
