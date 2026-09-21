# NEXT AGENT HANDOFF — RT3000 Machine-B

**Read this first, then `PROJECT_STATE.md`, then `NETWORK_BRINGUP_CLOSURE.md`.**

---

## 1. Where the project is

```
NETWORK_BRINGUP_P0 = CLOSED
ETHERNET_P0_RESOLVED = YES
FINAL_NETWORK_BASELINE = R1-NET-D   (ACCEPTED_HARDWARE_TESTED)
NEXT_PHASE = PRODUCT_R1   (baseline = R1-NET-D)
```

The Ethernet P0 that ran through R1-NET-A/B/C is **fixed and hardware-accepted**. Do not reopen it.

---

## 2. Network baseline — use these identities

```
r1-net-d.ubi      ab076d02268ab3f73a4e916f2939b88f2252297843bf8fb065438a39699fd481
qca-ssdk.ko       d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497
patch             0902-rt3000-r1-net-d-non-force-port-clock.patch
patch sha256      f9e4065ce1569631d520364c9f6547a1312dc8a9f46a277b4ad289627b4c0ca2
```

Artifacts: `rt3000-close-work/evidence/R1_NET_D_20260919/artifacts/r1-net-d.ubi`

**Product R1 must start from R1-NET-D.** Do not fork from R0.1 or R1-NET-B. Inherit: MDIO1 pinmux,
`phy-reset-gpio`, external QCA8337 support, OEM-like two-switch model, and the NET-D qca-ssdk clock fix.

---

## 3. Device state right now

```
running   R1-NET-D (Linux 5.4.164)
selector  mtd3 = 1, mtd2 = 1
mtd15     intact (OEM, the rollback anchor)
mtd16     R1-NET-D
```

Verified working: WAN 1000baseT full-duplex, DHCP `192.0.2.2/24`, default route, gateway
reachable, internet reachable. GMAC0 RX/TX both `P_GEPHY_TX` @ 125 MHz.

---

## 4. What to do next

**Only one task is in scope: close the two P0 release blockers.**

| ID | Task |
|---|---|
| **RT3-RB001** | Make the packaged `rt3bcwrite --set` perform `mtd3 write → verify → mtd2 write → verify`, failing closed between copies. A one-shot dual-copy write is forbidden. |
| **RT3-RB002** | Replace `rt3slot`'s fixed UBI `image_seq` firmware identity with a stable content identity (FIT/kernel hash, manifest, or equivalent). **Do not** just update the constant — `ubiformat` changes `image_seq`. |

Then, in order: Wi-Fi defaults/security → deterministic MAC policy → LuCI → root/dropbear security →
ECM/NSS offload → LED/buttons → long uptime → factory reset → reboot/power-cycle → OEM Web OTA
packaging. Details and the frozen MAC policy: `PRODUCT_R1_PLAN.md`.

---

## 5. Rules that are not negotiable

### Clock acceptance
Read **`gmac0_rx_clk_src`** and **`gmac0_tx_clk_src`** parent + effective rate.
**Never** use `gephy_gcc_tx enable_count` as a pass/fail gate — it is a software shadow clock with no
`.enable` op, so its count cannot be meaningful. This was a genuine methodology error earlier; do not
reintroduce it.

### Selector writes — has a real incident behind it
A selector byte was once generated via multi-layer Python → shell → `printf` escaping; the escape
double-applied and the **literal ASCII `\001` (4 bytes)** was written instead of the byte `0x01`.
It was caught only by the structural BOOTCONFIG verify.

- **Use:** pre-generated binary bytes, or base64 encode/decode. No escape layers.
- **Never:** synthesise the byte through nested quoting.
- **Always, per copy:** write → raw readback → structural BOOTCONFIG parse → exact selector verify.
  Touch the second copy only after the first fully verifies.
- Reusable tool: `sel_flip2.py` (base64, binary-safe).

### Transport
Firmware goes over **OneCloud LAN/HTTP** — 11 MB takes under a second. **Never** over the TTL.
TTL is for the boot console and recovery only. Do not drive multi-minute downloads through it.

### Device identity fence
`192.0.2.1` on the **jumpbox main netns is the JCQ30Pro, not the RT3000.** Confirm identity before
any IP-based action. The RT3000 is MAC `00:11:22:33:44:55`, DT model `H3C Magic RT3000`, reached via
the jumpbox `flash` netns USB NIC.

### OEM is the golden reference
If hardware/BOM/PCB is ever suspected, run a same-hardware OEM control experiment **first**. Do not
start by disassembling.

### Rollback anchor
OEM mtd15 + selector 0. Keep intact.

---

## 6. Closed — do not reopen

| Hypothesis | Status |
|---|---|
| state-aliasing / NET-C first-apply guard | refuted on hardware |
| missing DTS clocks / `clock-names` | refuted (identical to the working reference board) |
| `qcom,link-poll` | refuted |
| `rx-page-mode` | refuted |
| EEE | refuted |
| hardware / BOM / PCB | refuted by OEM same-hardware control |

**Historical candidates — evidence only, not for further development:**
R1-NET-A, R1-NET-B, R1-NET-C, R1-PROBE-H, R1-PROBE-I.

### Authoritative WAN root cause (archived)

> Machine-B WAN = SSDK port 1 / GMAC0 / PHY-managed **non-force** port. The MP adapter's boot speed
> path bound `ssdk_port_speed_clock_set()` to `force_port == A_TRUE`, so WAN's speed clock was never
> programmed, the RCG stayed on `xo / 24 MHz`, and every 1000BASE-T frame failed CRC. Proven live by
> R1-PROBE-I (port 1: no setter; port 2: setter called, 125 MHz, ret=0). Fixed in R1-NET-D by
> decoupling clock programming from the force gate and removing the duplicate runtime clock call.

---

## 7. Open qualifications — never record as PASS

```
SPEED_1000_QUALIFIED = YES   (initial bring-up only)
SPEED_100_QUALIFIED  = NO
SPEED_10_QUALIFIED   = NO
```

| ID | Item |
|---|---|
| NET-QUAL-001 | physical WAN unplug/replug at 1 Gbps |
| NET-QUAL-002 | 100BASE-T |
| NET-QUAL-003 | 10BASE-T |

NET-QUAL-001 matters because the Probe-I trace showed **no runtime link-event path fires for the WAN
port**. NET-D programs the clock at boot, which suffices for initial bring-up; re-plug behaviour is
genuinely unverified. Reference before unplug: `port:1 up 1000baseT`, both clocks 125 MHz,
`eth0 rx_packets 842`.

---

## 8. Product R1 — release blocker closure (this round)

Branch `product-r1`, from the immutable tag `rt3000-machine-b-r1-net-d`
(`ba18b661a46f4b8d5fc1aa806d616bd98b319c81`). The tag itself was not moved,
rewritten or re-pointed.

### RT3-RB001 — CLOSED_OFFLINE_PENDING_HARDWARE

`package/rt3bcwrite.c` now runs a real per-copy transaction, in order:
read live erase block -> structural validate -> patch only the 4 selector bytes
-> prove no other byte moved -> erase/write -> read back whole block ->
byte-compare -> re-parse structure -> confirm exact selector.

mtd3 is written **first**; mtd2 is touched **only** if mtd3 fully passed. Exit
codes distinguish refusal from partial write (5/7 = first copy failed, second
untouched; 6/8 = second copy failed, copies divergent and reported as such).

Binary safety: the selector is materialised only through `put_le32()`. No
`printf` escapes, no shell quoting, no string literals — the historical ASCII
`\001` incident cannot recur.

`tests/rb001/run_tests.sh`: **22 assertions, all passing**, `FAIL_CLOSED=YES`.
Fault injection is compiled out of the shipped binary (verified with
`nm`/`strings`).

### RT3-RB002 — CLOSED_OFFLINE_PENDING_HARDWARE

`package/rt3release` replaces the fixed `image_seq` with stable content
identity: SHA-256 over the FIT kernel payload at its **declared** length, and
over the squashfs rootfs payload, compared against a release manifest.
`image_seq`, EC counters, VID headers and PEB placement are used nowhere; test
11 enforces this mechanically by stripping comments and grepping the real code.

`tests/rb002/run_tests.sh`: **13 assertions, all passing**,
`IMAGE_SEQ_DEPENDENCY=NONE`.

Details: `RB001_FAIL_CLOSED_SELECTOR.md`, `RB002_STABLE_IDENTITY.md`.

### Product R1 prerelease 1

```
artifact : openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi
sha256   : 162d84ae74528bbee19f46e0079a3c86a4c88b935fd9679a01b83fe63fdedf8c
size     : 11010048
kernel vol : 52d8e38fc4f4bb22403d98231d140507702e26f161cb942c3a0b77afce9c07c7  (== R1-NET-D)
rootfs vol : f0d49c448a7f00ec694c90aa5cb54051544395804203fe708b2773d7b8c8b70f
qca-ssdk.ko: d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497  (== NET-D accepted)
```

The kernel volume is byte-identical to R1-NET-D and `qca-ssdk.ko` is unchanged,
so the hardware-accepted NET-D network baseline is retained. Only the rootfs
changed, and only by the three Product R1 tools plus the release manifest.

Not included, deliberately: LuCI, Wi-Fi defaults, MAC policy, security
hardening, ECM/NSS, LED/buttons. One variable set per round.

### Hardware acceptance still required

`CLOSED_OFFLINE` means the implementation and its tests pass — **not** that the
device was exercised. Both blockers need on-hardware confirmation:

| ID | Item |
|---|---|
| RB001-HW-001 | `rt3bcwrite --set` dual-copy transaction on real MTD |
| RB002-HW-001 | `rt3release verify` on the running device |

Neither was performed: `DEVICE_WRITES=0` this round. Do not record either as
hardware-accepted.

---

## 9. HARDWARE ACCEPTANCE — Product R1 prerelease 1 (2026-09-19)

**FINAL_SYSTEM = Product R1 prerelease 1, selector 1/1, mtd15 intact.**

Full detail: `PRODUCT_R1_PRERELEASE_1_ACCEPTANCE.md`.

### RT3-RB001 = HARDWARE_ACCEPTED / CLOSED

The *packaged* `rt3slot oem` was run on the device and produced:

```
copy=mtd3 write=PASS verify=PASS     <- emitted BEFORE the mtd2 lines
copy=mtd2 write=PASS verify=PASS
RESULT=PASS both copies = 0x00000000
```

The required ordering was proven directly from the output rather than inferred
from the final 0/0. Raw post-reads confirmed both selectors, both BOOTCONFIG
structures, and byte-identical preservation of the OEM blob at `0x880` on
`mtd2`. OEM booted afterwards (Linux 4.4.60) and mtd15 stayed intact. Combined
with the offline 22/22 fail-closed suite.

The packaged tool was deliberately NOT used for its own first install — the
manual binary-safe RMW did that — and was accepted only once Product R1 was up
and stable.

### RT3-RB002 = HARDWARE_ACCEPTED / CLOSED

Flashed-content identity matched the external manifest on both halves
(kernel `95254958…`, rootfs `f0d49c44…`). Runtime `rt3release verify` reported
`KERNEL_MATCH=PASS`, `ROOTFS_VERIFY=UNSUPPORTED_FROM_INSIDE_ROOTFS`,
`IMAGE_SEQ_DEPENDENCY=NONE`, `RELEASE_IDENTITY_MATCH=PASS_KERNEL_ONLY` — the
honest scope, not a fake full pass.

Decisive evidence that `image_seq` is not identity: it changed from
`0x2a967962` to `0x58c99d30` across a flash of byte-identical firmware content.
A fixed `image_seq` would have misreported; content identity did not.

### Network baseline — no regression

`gmac0_rx_clk_src` and `gmac0_tx_clk_src` both `gephy_gcc_tx` @ `125000000`.
WAN `1000baseT full-duplex`, `eth0 rx_packets` advancing with
`rx_errors=0` and `rx_crc_errors=0`, DHCP `192.0.2.2/24`, gateway 0.35 ms,
internet 9.2 ms, QCA8337 registered, LAN ports 1000baseT, both Wi-Fi bands up.

### Still open — unchanged by this round

`SPEED_100_QUALIFIED=NO`, `SPEED_10_QUALIFIED=NO`, NET-QUAL-001/002/003.
