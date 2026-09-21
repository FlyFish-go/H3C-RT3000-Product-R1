# NETWORK BRING-UP CLOSURE — RT3000 Machine-B

```
NETWORK_BRINGUP_P0 = CLOSED
ETHERNET_P0_RESOLVED = YES
FINAL_NETWORK_BASELINE = R1-NET-D (ACCEPTED_HARDWARE_TESTED)
```

**Device writes during preparation of this document: 0.**

---

## 1. Authoritative network baseline

| | |
|---|---|
| Candidate | `r1-net-d.ubi` |
| SHA256 | `ab076d02268ab3f73a4e916f2939b88f2252297843bf8fb065438a39699fd481` |
| Size | 11010048 |
| Packaged `qca-ssdk.ko` | `d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497` |
| Patch | `0902-rt3000-r1-net-d-non-force-port-clock.patch` |
| Patch SHA256 | `f9e4065ce1569631d520364c9f6547a1312dc8a9f46a277b4ad289627b4c0ca2` |
| Artifact | `rt3000-close-work/evidence/R1_NET_D_20260919/artifacts/r1-net-d.ubi` |
| Build report | `rt3000-close-work/evidence/R1_NET_D_20260919/R1_NET_D_BUILD.md` |
| Acceptance | `rt3000-close-work/evidence/R1_NET_D_INSTALL_20260919/R1_NET_D_ACCEPTANCE.md` |

**R1-NET-D is the starting point for Product R1.** Do not fork from R0.1 or R1-NET-B.

---

## 2. Verified on hardware

```
BOOT_R1_NET_D = PASS                      Linux 5.4.164, root=/dev/ubiblock0_1
RUNTIME_MODULE_IDENTITY_PASS = YES        d493b3bd… (exact packaged module)

GMAC0 RX   P_GEPHY_TX   125000000
GMAC0 TX   P_GEPHY_TX   125000000

WAN        1000baseT full-duplex
           rx_packets 717 · rx_bytes 75525 · rx_errors 0 · rx_crc_errors 0
           RxGoodByte 75397 · RxFcsErr 0 · RxFragment 0

DHCP       PASS   192.0.2.2/24
ROUTE      PASS   default via 192.0.2.1 dev eth0
GATEWAY    PASS   0% loss, 0.37 ms
INTERNET   PASS   0% loss, 9.3 ms

QCA8337    registered, LAN1/2/3 previously hardware-accepted
```

**Authoritative clock criterion — use these, and only these:**

```
gmac0_rx_clk_src   parent + effective rate
gmac0_tx_clk_src   parent + effective rate
```

> **Do not use `gephy_gcc_tx enable_count` as a pass/fail gate.** It is a software shadow clock with
> no `.enable` op — its count is structurally incapable of being meaningful. This was a real
> methodology error earlier in the project and must not be reintroduced.

---

## 3. Authoritative root cause (archive — do not re-open)

> Machine-B WAN = **SSDK port 1 / GMAC0 / PHY-managed non-force port**.
> The MP adapter's boot speed path bound `ssdk_port_speed_clock_set()` to
> `force_port == A_TRUE`. Because WAN is not a force port, GMAC0's speed clock was **never
> programmed**; the RCG stayed on `xo / 24 MHz`, so every 1000BASE-T frame failed CRC.

Proven on hardware by R1-PROBE-I: port 1 had **no** clock setter
(`force_port=0 branch_clock_set=0 reason=not_force_port`), while port 2 **was** programmed
(`force_port=1`, `rate=125000000`, `ret=0`). Runtime link-event path never fired for port 1 either.
Final state `xo / 24 MHz`, no later overwrite.

**R1-NET-D fix:** decouple speed-clock programming from the force-only gate; keep the force-only MAC
operations gated; remove the now-duplicate runtime clock call so each port programs exactly once per
speed-setup event.

### Explicitly NOT the root cause — never cite these again

| Rejected hypothesis | Status |
|---|---|
| state-aliasing / NET-C first-apply guard | refuted on hardware (R1-NET-C installed, module verified, clocks unchanged) |
| missing DTS clocks / `clock-names` | refuted (byte-identical to the working reference board) |
| `qcom,link-poll` | refuted |
| `rx-page-mode` | refuted |
| EEE | refuted |
| hardware / BOM / PCB | refuted by the OEM same-hardware control experiment |

---

## 4. Closed items

| ID | Item | Status |
|---|---|---|
| **RT3-B002** | WAN RX corruption — no good frames on port 1 | **CLOSED** |
| — | `ETHERNET_P0_RESOLVED` | **YES** |
| — | `NETWORK_BRINGUP_P0` | **CLOSED** |

---

## 5. Open network qualifications (NOT Ethernet P0)

These are **open**, and must never be recorded as PASS:

| ID | Item | State |
|---|---|---|
| **NET-QUAL-001** | physical WAN unplug/replug at 1 Gbps | **NOT TESTED** — deferred; the runtime link-event path is known absent for port 1, so re-plug behaviour is genuinely unverified |
| **NET-QUAL-002** | 100BASE-T qualification | **NOT TESTED** |
| **NET-QUAL-003** | 10BASE-T qualification | **NOT TESTED** |

```
SPEED_1000_QUALIFIED = YES   (initial bring-up only)
SPEED_100_QUALIFIED  = NO
SPEED_10_QUALIFIED   = NO
```

Pre-unplug reference captured for the future re-plug test: `port:1 up 1000baseT`, both GMAC0 clocks
125 MHz, `eth0 rx_packets 842`.

---

## 6. Historical candidates — evidence only

**R1-NET-A, R1-NET-B, R1-NET-C, Probe H, Probe I are NOT candidates for further development.**
They are retained solely as historical evidence and root-cause provenance.

| Candidate | Final role |
|---|---|
| R1-NET-A | MDIO1 pinmux investigation |
| R1-NET-B | first working external switch; WAN still broken |
| R1-NET-C | state-aliasing hypothesis — refuted on hardware |
| R1-PROBE-H | static init-path analysis; located the real clock path |
| R1-PROBE-I | live trace that proved the root cause (and its trace build) |

---

## 7. Selector safety — historical incident, standing rule

**Incident:** during R1-PROBE-I a selector byte was generated through multi-layer
Python → shell → `printf` escaping. The escape was double-applied and the literal **ASCII text
`\001` (4 bytes)** was written into the selector field instead of the byte `0x01`. It was caught by
the structural BOOTCONFIG verify, which refused to accept the result.

**Standing rule — binary selector generation must be binary-safe:**
- preferred: **pre-generated binary bytes**, or **base64 encode/decode** (no escape layer anywhere);
- **forbidden**: multi-layer shell/Python/`printf` escaping to synthesise the byte;
- every copy must still be: **write → raw readback → structural BOOTCONFIG parse → exact selector
  verify**, and the second copy may only be touched after the first fully verifies.

The R1-NET-D run used the base64 method and verified the decoded payload was exactly `01 00 00 00`
before writing. Reuse that tool: `sel_flip2.py`.

---

## 8. What remains before release

See `PRODUCT_R1_PLAN.md`. The two release blockers in scope for Product R1 are **RT3-RB001** and
**RT3-RB002**, both still **OPEN**.
