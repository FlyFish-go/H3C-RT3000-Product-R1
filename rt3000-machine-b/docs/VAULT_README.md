# RT3000/QSDK Project Vault — START HERE

This vault is a **non-destructive reorganization** of RT3000 (H3C Magic, IPQ5018) project
material gathered from Mac (M1), WSL (`t4` → `Ubuntu-22.04`), and NAS (`royaldisk`).

**No original file anywhere was modified, moved, or deleted.** Everything here is a copy or a
reference. Hashes in `03-canonical-artifacts/` were verified against their sources at copy time.

## Layout

| Directory | Contents |
|---|---|
| `00-START-HERE/` | State, roadmap, canonical paths, machine separation |
| `01-firmware-repo/rt3000-qsdk/` | Project-quality QSDK material (NOT a wholesale OEM source copy) |
| `02-lab-environment/` | Jumpbox, power, serial, network, runbooks (documentation + templates only) |
| `03-canonical-artifacts/` | Hash-verified canonical binaries/images selected by milestone evidence |
| `04-evidence-vault/` | `EVIDENCE_INDEX.tsv` + pointers into the preserved original evidence tree |
| `05-archive-lab/` | Superseded/old/failed material (copies or references; originals untouched) |
| `06-private/` | What private material exists, where it lives authoritatively, and why it is not here |
| `07-manifests/` | Inventories, host comparison, duplicates, SHA256SUMS, sync status |

## Safety state

```
SAFE_TO_FLASH=NO
REAL_DEVICE_IO_SCOPE=NONE
NAND_WRITE_EXECUTED=NO          (Stage-1 packet remains PREPARED_NOT_EXECUTED)
```

Nothing in this vault authorizes or performs device writes. Runbooks document the exact
procedures that were validated in RAM-only scope; they are records, not invitations.

## Key entry points

**Network baseline and current phase (read these first):**

- `NEXT-AGENT-HANDOFF.md` — what to do next, and the rules that are not negotiable
- `NETWORK_BRINGUP_CLOSURE.md` — the closed Ethernet P0, verified hardware results, authoritative root cause
- `PRODUCT_R1_PLAN.md` — Product R1 scope, P0 release blockers, frozen MAC policy
- `PROJECT_STATE.md` — current project truth
- `../../BUG_BACKLOG.json` — live bug/blocker register

**Reference:**

- Which physical machine produced which fact: `MACHINES.md`
- What is canonical and why: `03-canonical-artifacts/CANONICAL_SELECTION.md`
- Evidence index: `04-evidence-vault/EVIDENCE_INDEX.tsv`
- What still needs independent audit: `07-manifests/SYNC_STATUS.md`

## Current phase

```
NETWORK_BRINGUP_P0     = CLOSED
ETHERNET_P0_RESOLVED   = YES
FINAL_NETWORK_BASELINE = R1-NET-D   (ACCEPTED_HARDWARE_TESTED)
NEXT_PHASE             = PRODUCT_R1  (baseline = R1-NET-D)
```

Product R1 starts from **R1-NET-D**. R1-NET-A/B/C and Probe H/I are historical evidence only and are
not candidates for further development.
