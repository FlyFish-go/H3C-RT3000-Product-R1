# Known Issues

This document tracks known limitations and unqualified areas for
H3C Magic RT3000 Machine-B Product R1 Developer Preview releases.

## Current Developer Preview Limitations

The following items have not completed full qualification:

- 10BASE-T operation
- 100BASE-T operation
- Long-duration stability / soak testing
- LED behaviour
- Hardware button behaviour
- Final NSS / ECM performance tuning

These items are not currently considered blockers for the first
Developer Preview unless later testing identifies a functional
regression.

## 5 GHz Wireless Configuration

The current development image may expose more than one 5 GHz-related
radio section in the OpenWrt wireless configuration.

The actual QCN6122 5 GHz radio must be correctly identified by the
release configuration.

This area is being reviewed before the first public Developer Preview.

## Hardware Compatibility

Only **H3C Magic RT3000 Machine-B** is currently supported.

Other RT3000 hardware revisions, NAND variants, PCB revisions, or
related H3C models must not be assumed compatible.

Do not flash a Product R1 image on another hardware revision unless
that revision is explicitly listed as supported.

## Reporting New Issues

Please open a GitHub Issue and include:

- Hardware revision
- Product R1 release version
- Firmware SHA256
- Original firmware version
- Installation method
- WAN / LAN status
- 2.4 GHz / 5 GHz status
- Relevant logs

Do not include passwords, Wi-Fi keys, private keys, or other secrets.
