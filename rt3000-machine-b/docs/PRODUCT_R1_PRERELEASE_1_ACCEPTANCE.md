# Product R1 prerelease 1 — hardware acceptance

Status: **ACCEPTED_HARDWARE_TESTED**
Date: 2026-09-19
Device: H3C Magic RT3000 Machine-B (unit MAC redacted; examples use synthetic identities)

## Artifact under test

```
openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi
sha256 : 162d84ae74528bbee19f46e0079a3c86a4c88b935fd9679a01b83fe63fdedf8c
size   : 11010048
```

## 1. Network baseline regression — PASS

The kernel volume is byte-identical to R1-NET-D and `qca-ssdk.ko` is unchanged,
so NET-D behaviour was expected to reproduce; it did.

| check | result |
|---|---|
| `gmac0_rx_clk_src` | `gephy_gcc_tx` @ `125000000` |
| `gmac0_tx_clk_src` | `gephy_gcc_tx` @ `125000000` |
| WAN link (SSDK port 1) | `link:up speed:1000baseT full-duplex` |
| `eth0 rx_packets` | 1382 (> 0) |
| `eth0 rx_bytes` | 139869 (> 0) |
| `eth0 rx_errors` | **0** |
| `eth0 rx_crc_errors` | **0** |
| DHCP | PASS — `192.0.2.2/24` |
| default route | `default via 192.0.2.1 dev eth0` |
| gateway ping | 0% loss, 0.35 ms |
| internet ping (`223.5.5.5`) | 0% loss, 9.2 ms |
| QCA8337 | registered (`switch1 - QCA AR8337`) |
| LAN smoke | ports 0 and 2 `link:up speed:1000baseT full-duplex` |
| Wi-Fi 2.4G | `wlan0` AP, ch1 (2412 MHz), 25 dBm |
| Wi-Fi 5G | `wlan1` AP, ch36 (5180 MHz) 80 MHz, 24 dBm |

The clock criterion was read from `gmac0_*_clk_src` parent + rate, never from
`gephy_gcc_tx enable_count`.

Wi-Fi was enabled RAM-only for the smoke test. No Wi-Fi default was changed and
nothing was committed from it.

## 2. RT3-RB001 — HARDWARE_ACCEPTED

The packaged tool was exercised on the device, not the development helper.

```
$ rt3slot oem
PRE  mtd3(0:BOOTCONFIG1) = 0x00000001
PRE  mtd2(0:BOOTCONFIG) = 0x00000001
copy=mtd3 FIRST (redundant)
copy=mtd3 write=PASS verify=PASS
copy=mtd2 SECOND (primary)
copy=mtd2 write=PASS verify=PASS
POST mtd3(0:BOOTCONFIG1) = 0x00000000
POST mtd2(0:BOOTCONFIG) = 0x00000000
final_selector=0x00000000
RESULT=PASS both copies = 0x00000000
PRE  mtd3(0:BOOTCONFIG1) = 0x00000000
PRE  mtd2(0:BOOTCONFIG) = 0x00000000
VERIFY_ONLY want=0x00000000 -> PASS
SWITCH_RESULT=PASS
```

**Ordering was proven directly, not inferred from the final 0/0.**
`copy=mtd3 write=PASS verify=PASS` is emitted before `copy=mtd2 SECOND`, so the
second copy's transaction provably began only after the first copy verified.

Post-write raw reads:

| check | result |
|---|---|
| mtd2 selector bytes | `00 00 00 00` |
| mtd3 selector bytes | `00 00 00 00` |
| mtd2 structure | magic `0xa3a2a1a0`, ver 1, count 8 |
| mtd3 structure | magic `0xa3a2a1a0`, ver 1, count 8, tail `0xb3b2b1b0` |
| mtd2 OEM blob @0x880 | byte-identical (`_icmp_sen...` preserved) |
| OEM boot after rollback | **Linux 4.4.60**, selectors 0/0 |
| mtd15 after the whole cycle | intact (`UBI#`, image_seq `0x2600e9d0` unchanged) |

Together with the offline 22/22 fail-closed suite (covering target 0↔1,
structural refusal, first-copy failure leaving the second copy untouched, and
second-copy failure reporting divergence):

**RT3-RB001 = HARDWARE_ACCEPTED**

The packaged binary was deliberately *not* used for its own first installation;
the manual binary-safe RMW did that. It was accepted only after Product R1 was
up and stable.

## 3. RT3-RB002 — HARDWARE_ACCEPTED

### Flashed-content identity

| item | from flashed content | external manifest | result |
|---|---|---|---|
| kernel (FIT declared length) | `95254958…9134de` | `95254958…9134de` | **PASS** |
| rootfs (squashfs payload) | `f0d49c44…c8b70f` | `f0d49c44…c8b70f` | **PASS** |

### Runtime identity (on the running device)

```
$ rt3release verify
RELEASE_KERNEL_ID=95254958dadcbe9c5630fd258543874b1a92d66a5bb4791fcbbf60c8839134de
RELEASE_ROOTFS_ID=NOT_IN_MANIFEST
MACHINE_MATCH=PASS
KERNEL_FIT_DECLARED_BYTES=3476396
RUNNING_KERNEL_ID=95254958dadcbe9c5630fd258543874b1a92d66a5bb4791fcbbf60c8839134de
RUNNING_ROOTFS_ID=f0d49c448a7f00ec694c90aa5cb54051544395804203fe708b2773d7b8c8b70f
KERNEL_MATCH=PASS
ROOTFS_MATCH=NOT_IN_MANIFEST
ROOTFS_VERIFY=UNSUPPORTED_FROM_INSIDE_ROOTFS
IMAGE_SEQ_DEPENDENCY=NONE
QSDK_SLOT_VALID=YES
RELEASE_IDENTITY_MATCH=PASS_KERNEL_ONLY
```

`PASS_KERNEL_ONLY` is the **correct and expected** result here. The in-rootfs
manifest deliberately does not carry the rootfs' own hash — embedding it would
be circular. With the external manifest both halves verify and the result is a
full `PASS`. The tool reports the honest scope rather than a fake full pass.

The runtime kernel and rootfs IDs read from the live `/dev/ubi0_0` and
`/dev/ubiblock0_1` match both the flashed content and the manifest — three-way
agreement.

### image_seq is not identity

```
mtd16 image_seq BEFORE flash : 0x2a967962
mtd16 image_seq AFTER  flash : 0x58c99d30
```

The value changed across a flash of byte-identical firmware content. A fixed
`image_seq` would have produced a false result; identity derived from content
did not. `IMAGE_SEQ_USED_FOR_IDENTITY=NO`.

`rt3slot status` no longer reads any `image_seq`:

```
RUNNING_SLOT=QSDK
RUNNING_RELEASE=Product R1 prerelease 1
RUNNING_KERNEL_ID=95254958…9134de
QSDK_SLOT_VALID=PASS
QSDK_SLOT_RELEASE=Product R1 prerelease 1
INACTIVE_CONTENT_VERIFY=UNSUPPORTED
oem_partition=mtd15:oem_rootfs
qsdk_partition=mtd16:rootfs
```

`INACTIVE_CONTENT_VERIFY=UNSUPPORTED` is honest: the inactive slot's payload is
not reachable through `/dev/ubi0_0` or `/dev/ubiblock0_1`.

All six acceptance criteria met:

1. flashed FIT content hash matches the external manifest — PASS
2. flashed squashfs content hash matches the external manifest — PASS
3. runtime in-rootfs manifest correct — PASS
4. `rt3release` reports honest scope — PASS
5. `rt3slot` no longer uses a fixed `image_seq` — PASS
6. changing `image_seq` is irrelevant to the identity result — PASS

**RT3-RB002 = HARDWARE_ACCEPTED**

## 4. Final device state

| item | value |
|---|---|
| running | Product R1 prerelease 1 (Linux 5.4.164) |
| selector mtd3 | `1` |
| selector mtd2 | `1` |
| copies agree | YES |
| mtd15 | intact, OEM rollback anchor untouched |

The device is deliberately left on Product R1, not switched back to OEM.

## 5. Failed-closed events recorded as safety evidence

Two refusals occurred during the run and are kept as positive evidence that the
safety gates work rather than being installation failures:

1. The original manual helper refused to write because the QSDK runtime has no
   `base64`, `xxd` or `od`, so it could not establish a binary-safe payload
   (`EXPECTED_FAIL_CLOSED=PASS`). The selector payload was moved to a
   pre-generated 4-byte HTTP artifact instead.
2. An early RMW attempt refused with only 1 differing byte. That was a wrong
   assertion in the harness (a `1 → 0` flip legitimately changes only byte 0),
   not a transaction fault; the invariant was corrected to "differing offsets
   must lie inside the selector field". A subsequent read that appeared to show
   an ASCII-escaped selector was an offset-alignment error in my own analysis —
   the selector was `00 00 00 00` at offset 0x80 all along.

## 6. Not claimed

| item | status |
|---|---|
| SPEED_100_QUALIFIED | NO |
| SPEED_10_QUALIFIED | NO |
| NET-QUAL-001 physical WAN replug at 1 Gbps | NOT_TESTED |
| NET-QUAL-002 100BASE-T | NOT_TESTED |
| NET-QUAL-003 10BASE-T | NOT_TESTED |

Deliberately out of scope this round: LuCI, Wi-Fi defaults, MAC policy,
security hardening, ECM/NSS, LED/buttons.
