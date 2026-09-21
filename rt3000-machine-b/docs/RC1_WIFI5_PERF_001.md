# RC1-WIFI5-PERF-001 — QCN6102 5 GHz performance repair

> Latest status (2026-09-21): see [Candidate 13 session results](WIFI5_SESSION_2026-09-21.md).
> Optimization is paused at the user's request. Latest phone single-stream upload:
> 760 / 789 Mbps; repeated >=800 Mbps is not yet achieved. Candidate 13 remains
> RAM-only on channel 44 / HE160. The sections below are historical snapshots,
> not current deployment instructions. Physical hardware is QCN6102; QSDK names
> its software target QCN6122.

## Classification

The same Machine-B hardware, phone position and OneCloud server produced:

- Product R1 5 GHz downlink: 0.429 Mbit/s, 57 TCP retransmissions;
- OEM 5 GHz downlink: 172 Mbit/s server-side, zero TCP retransmissions;
- OEM negotiated link rate: 2401 Mbit/s with full phone signal.

The OneCloud USB 2.0 NIC limits the measured OEM ceiling, but it does not
explain the Product R1 collapse.  The defect is scoped to the Product R1
QCN6122 software path.

## First repair candidate

Product R1 currently uses the CMCC RAX3000Q QCN6122 BDF payload under the
RT3000 board-id 0x90 container.  This was an intentional bring-up compromise:
the complete OEM `bdwlan.b90` data makes WLAN.HK.2.7.0.1 assert in
`phyrf_bdf.c`, while the CMCC structure boots reliably.  The historical
handover explicitly left RT3000 power-table transplantation as follow-up work.

Candidate 1 therefore keeps the complete ath11k-compatible CMCC structure and
replaces only board-payload bytes `[0x2494, 0x2758)` with the corresponding
Machine-B OEM bytes.  The structurally divergent/axis-sensitive area beginning
near `0x2760` remains byte-identical to CMCC.

The first hardware trial exposed a construction defect in that candidate: the
power-table bytes were changed without recomputing the QCA board-data XOR
checksum at payload offset `0x000a`.  Its complete 128 KiB BDF body XOR was
`0x33c4`; every unmodified OEM, ART and CMCC reference body is `0xffff`.
Candidate 3 keeps the exact same bounded OEM window and CMCC-compatible axis
structure, but deterministically repairs the checksum word to `0x8479`.  Its
expected full container SHA256 is
`81ac536f43ce5a6d21652c276cf8d7a54d5a26e47a0094fb79c43d6c3d1909af`.

Candidate 3 booted cleanly and its corrected checksum was verified on the
running device, but the phone still received the AP at `-84 dBm` versus the
OEM's full-signal control.  It improved only about 3 dB over Candidate 2's
`-87 dBm`, so checksum repair alone is not the RF fix.

Candidate 4 adds only the 57 non-checksum bytes by which the OEM and CMCC BDF
modal/header area `[0x0000,0x1000)` differs.  This bounded region is the next
diagnostic scope for board-level front-end, antenna and gain configuration.
The proven OEM power window remains installed, the incompatible axis area at
`0x2760` remains CMCC-identical, and the complete BDF checksum is recomputed.
Its expected checksum word is `0xf71b` and full container SHA256 is
`7857fe4326bebc3063b923bb3bf035e75da94258aef1e6d5a26d4f8dde2a8f1e`.

Candidate 4 failed its hardware boot gate.  WLAN.HK.2.7.0.1 asserted at
`phyrf_bdf.c:6245` (`axis_value == ANTENNACHAIN_AXIS_Z`) and the remoteproc
recovery ended in a kernel panic.  The experiment exposed a flaw in the
candidate design: the transplanted H3C header selects the OEM `0x50.52` BDF
layout, while the remainder still contains the CMCC `0x60`-family structure.
The two payload families differ in about 18,000 bytes, so the 32-byte axis
window cannot safely be considered independent of the layout header.

Candidate 5 stops cross-family transplantation.  Its complete structural
donor is the upstream Elecom WRC-X3000GS2 QCN6122 BDF (`0x50.51` family),
whose modal/front-end area is nearly byte-identical to the H3C OEM data but is
already consumed by ath11k.  The donor is pinned at OpenWrt qca-wireless commit
`04dff0ab979f153a4605095b5e449a9ac5494a17`, full SHA256
`5ca4e0151b0801f3dd23a87a41e3679122359e68e5144bd668200ab0ca245811`.
Only the previously bounded H3C OEM power window `[0x2494,0x2758)` is then
installed and the XOR checksum repaired.  The RT3000 board-id wrapper and the
device's external ART caldata remain unchanged.  Expected checksum word is
`0x38f0`; expected full container SHA256 is
`085a6cca54714ed8387341869bbf1f75b257198e87bd590ddf58f7d155c772fb`.

Candidate 5 is a RAM-boot diagnostic first.  It must not replace `mtd16` until
it passes the firmware boot/assert gate and the same-position phone RSSI gate.

Candidate 5 passed those RAM-boot gates on Machine B.  The loaded board file
matched the expected SHA256, both radios registered, QCN6122 firmware booted
without an assertion, and the 5 GHz AP remained stable.  The phone observed
`-43 dBm` at the test position, versus approximately `-84` to `-87 dBm` for
the earlier QSDK candidates.  Router-local 10-second iperf3 tests measured
247 Mbit/s upload and 258 Mbit/s download on average.

The router-local flow does not exercise routed/NAT offload.  Runtime evidence
shows that the NSS firmware, `qca_nss_drv`, NSS dataplane and NSS IRQs are
healthy, but no ECM module is present.  Candidate 6 therefore keeps Candidate
5's BDF unchanged and adds the standard QSDK 11.5 NSS ECM package to the
RT3000 device profile.  It also includes iperf3 for repeatable RAM-boot
diagnostics.  Candidate 6 must be RAM-booted and prove ECM/NSS counter growth
on a LAN-to-WAN flow before any persistent promotion decision.

Candidate 6 passed the RAM-boot and routed-offload gates on Machine B.  The
runtime BDF remained byte-for-byte identical to Candidate 5, NSS and ECM
loaded cleanly, and the 5 GHz AP retained its known-good radio state.  A phone
LAN-to-WAN test through ECM measured 53.2 Mbit/s upload and 543 Mbit/s download
with one TCP connection.  During the capture ECM reported 12 accelerated IPv4
connections, including 8 TCP connections, with 7,124 successful acceleration
operations, zero failures and zero NACKs.  NSS queue 0 advanced by 1,105,376
interrupts while average non-idle CPU was approximately 4.46 percent.  This
proves that routed/NAT NSS offload is active.  The low single-stream upload is
a separate performance follow-up; the phone application's quick test did not
apply the requested four parallel streams.

This is a bounded diagnostic candidate, not yet a release fix.  It must pass:

1. offline container, provenance, byte-window and hash gates;
2. a clean QCN6122 firmware boot without assertion or recovery;
3. the same-phone 5 GHz throughput test with station PHY/retry evidence;
4. regression checks for 2.4 GHz, LAN/WAN, release identity and rollback.

No BDF candidate may be promoted on throughput alone; regulatory and transmit
power evidence must also be reviewed before release acceptance.

## Candidate 10 — full ath11k NSS/WIFILI source-only axis

Candidate 10 returns to the Candidate 6 BDF and changes only the full ath11k
NSS/WIFILI path. The ath11k module is loaded with
`nss_offload=1 frame_mode=2`; generic mac80211 NSS redirect remains disabled
by the QSDK source default (`nss_redirect=false`) and the prior
`611-ath11k-Enable-NSS-Redirect-by-default.patch` is removed, so there is one
NSS path rather than a redirect fallback. The RT3000 DTS marks the internal
IPQ5018 radio as priority 0 and the external QCN6102 5 GHz radio as priority 1.

This candidate is source/build-only until all static audits pass. Hardware
testing remains RAM-only: no MTD, ART, bootloader, environment, selector or
BOOTCONFIG writes are permitted. The startup gate requires the Candidate 6
BDF hash, exact ath11k module parameters, both radio priority properties in
the final DTB, absence of the rejected Candidate 7 RXDMA change and absence
of Candidate 8/9 modal payload changes. Any assert, remoteproc recovery,
OOM, missing AP or BDF mismatch requires immediate return to Candidate 6.

The first Candidate 10 static check was corrected after an audit found that
the 611 default-enable patch was still present and could override the 207
default. The corrected check now requires that patch to be absent and checks
both the source patch chain and any prepared mac80211 source for
`nss_redirect=false`.

## Offline-accepted diagnostic artifact

Candidate 2 passed the complete static gate and is the only image authorised
for the first hardware trial:

```text
file    product-r1-rc1-wifi5-perf-001-candidate2.ubi
size    11665408
sha256  3c27d08170dacc9cfc6812e8b14e3c130203b7ac78cd0036c336234735714126
```

It preserves the hardware-accepted Product R1 kernel/FIT and R1-NET-D
`qca-ssdk.ko` byte-for-byte.  Its 124-package set, DTB, LuCI content, security
defaults and release identity match the accepted RC1 baseline.  The intended
rootfs change is the QCN6122 BDF, whose final SHA256 is
`91aac77ffe4c86dd7418c24620cfa4082767a86524a417c3a13f169fb34dcf4c`.

The artifact, sidecar manifest, checksums and full audit are stored under
`artifacts/machine-b/rc1-wifi5-perf-001/candidate2/` outside the Git worktree.

The first hardware trial must boot OEM before replacing the inactive QSDK
partition.  It may write only the QSDK slot (`mtd16`) and the already accepted
BOOTCONFIG selector transaction.  The OEM rollback anchor (`mtd15`) must not be
written.  After boot, acceptance begins with release identity, kernel, BDF,
`qca-ssdk.ko`, firmware-assert and regulatory checks before any throughput test.

## Candidate 11 OEM-body schema-lift (offline only)

Candidate 11 uses the complete Machine-B OEM `bdwlan.b90` body and applies
only the WLAN 2.7 schema lift: `0x045c..0x045d` changes from `03 00` to
`00 00`, followed by the little-endian XOR16 checksum update at `0x000a`
(`0x4fbd`). The fail-closed generator fixes input size/hash, version 50.52,
schema, checksum, preserved ranges, and output hashes. It retains Candidate
10's full-WIFILI source axis, radio priorities, and `nss_redirect=false`; no
Candidate 7/8/9 modal or RXDMA variables are included. This candidate is
source/build-only and remains RAM-only for any future hardware gate.
