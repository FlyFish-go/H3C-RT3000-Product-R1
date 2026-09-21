# RB001 — Fail-closed BOOTCONFIG selector update

Status: **CLOSED_OFFLINE_PENDING_HARDWARE**

## The defect

`rt3bcwrite --set` could not guarantee the required transaction:

```
mtd3 write -> verify -> mtd2 write -> verify
```

The tool wrote both copies, but the per-copy gate was not proven, and there was
no way to demonstrate that a first-copy failure leaves the second copy untouched.

## The contract

The selector lives in two redundant copies:

| copy | partition | role | order |
|---|---|---|---|
| B | `mtd3` / `BOOTCONFIG1` | redundant | written **first** |
| A | `mtd2` / `BOOTCONFIG` | primary | written **second** |

`mtd2` shares its erase block with an OEM configuration blob at ~`0x880`, so a
whole-partition image write is **forbidden**. Every write is a live
read-modify-write of exactly one erase block.

Each copy runs the identical transaction, in order:

1. read the current live erase block
2. structurally validate it (magic / version / count / 8 records / rootfs record / tail)
3. patch **only** the 4 selector bytes at `0x080`
4. confirm every byte outside those 4 is unchanged, across the **whole** block
5. erase + write the block
6. read back the whole block
7. byte-compare the whole block against the intended image
8. re-parse the structure from the readback
9. confirm the selector is exactly the target value

The second copy is touched **only** if the first copy's transaction fully
passed. There is no path that reports success unless both copies hold the exact
target selector.

### Authority and layout

```
structure size  0x150
magic   @0x000 0xa3a2a1a0     version 1      count 8
rootfs record   offset 0x070  (record index 5, 8 x 20-byte records)
selector        offset 0x080   u32 little-endian
tail magic      @0x14c 0xb3b2b1b0
no CRC
selector: 0 = OEM / mtd15      nonzero = QSDK / mtd16
```

## Binary safety

A historical incident wrote the ASCII text `\001` (four characters) instead of
the byte `0x01`, via multi-layer Python → shell → `printf` escaping. The tool
therefore **never** constructs the selector through escapes, shell quoting or
string literals. It is materialised in exactly one place:

```c
static void put_le32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)(v & 0xff);
    p[1] = (unsigned char)((v >> 8) & 0xff);
    p[2] = (unsigned char)((v >> 16) & 0xff);
    p[3] = (unsigned char)((v >> 24) & 0xff);
}
```

Tests 01b/02b assert the on-media bytes are exactly `01 00 00 00` / `00 00 00 00`,
and test 16 asserts they are never the ASCII escape.

## Output semantics

```
copy=mtd3 write=PASS verify=PASS
copy=mtd2 write=PASS verify=PASS
final_selector=0x00000001
RESULT=PASS both copies = 0x00000001
```

Only when both copies pass does the tool exit 0. Distinct exit codes separate a
refusal from a partial write:

| code | meaning |
|---|---|
| 0 | success, both copies verified |
| 2 | usage |
| 3 | structural validation refused; nothing written |
| 4 | open/read failure; nothing written |
| 5 | first-copy write failed; **second untouched** |
| 6 | second-copy write failed; **copies divergent** |
| 7 | first-copy readback mismatch; **second untouched** |
| 8 | second-copy readback mismatch; **copies divergent** |

A failure on the first copy prints `mtd2 was NOT touched`. A failure on the
second prints `COPIES NOW DIVERGENT` — the divergence is stated, never hidden.

## Tests

`tests/rb001/run_tests.sh` — 22 assertions, all passing, against a synthetic
fixture; no real MTD is touched. Faults are injected through the
`RT3BCWRITE_MOCK_*` hooks, which are compiled out entirely in the shipped
binary (verified: `nm`/`strings` show zero mock symbols or mock environment
names in the production build).

Coverage:

* **happy path / binary safety** — `0->1`, `1->0`, exact media bytes, no ASCII
  escape, OEM blob at `0x880` byte-identical, exactly the selector bytes change,
  idempotent re-run performs 0 writes
* **structural refusal, nothing written** — bad magic, bad version, bad count,
  bad tail magic, missing rootfs record
* **first-copy failure => second copy 0 writes** — injected write failure,
  injected readback mismatch, structural failure
* **second-copy failure => nonzero exit + divergence reported** — injected write
  failure, injected readback mismatch
* **selector corruption** — invalid on-media value rejected, `--set 2` rejected

Result: `RB001_TESTS=PASS`, `FAIL_CLOSED=YES`.

## Where the live block is read from

`rt3bcwrite` reads the **current live erase block** from `/dev/mtdN` and patches
only the selector. It never restores a whole live erase block from an old
backup and never copies mtd3's erase block over mtd2's.
