# RB002 — Stable firmware identity for the QSDK slot

Status: **CLOSED_OFFLINE_PENDING_HARDWARE**

## The defect

`rt3slot` decided whether the QSDK slot was valid by reading the UBI **image
sequence** number out of the volume's EC header and comparing it against a
hardcoded constant:

```sh
QSDK_IMAGE_SEQ=${RT3SLOT_QSDK_IMAGE_SEQ:-309dc958}
image_seq() { dd if="$node" bs=1 skip=24 count=4 ... }
```

`image_seq` is **format metadata**, not firmware identity. This is wrong in both
directions:

* **false negative** — `ubiformat` (or any re-pack, or a vendor flashing tool)
  writes a *new* `image_seq` over byte-identical firmware, so a perfectly good
  slot is reported invalid;
* **false positive** — a corrupted or truncated payload keeps its `image_seq`,
  so a broken slot is reported as the expected release.

The fix is not "update the constant". The constant must stop being an input.

## The identity model

Identity comes only from **stable content**: SHA-256 over the actual payloads,
compared against a release manifest.

| half | what is hashed | why that length |
|---|---|---|
| kernel | the FIT image at its **declared** length | the UBI kernel volume is the FIT padded with `0xFF` to the erase-block boundary; hashing the declared extent makes the hash independent of volume padding and block size |
| rootfs | the squashfs rootfs payload | squashfs has no self-describing total length, so the manifest records `rootfs_size` |

`image_seq`, EC counters, VID headers and PEB placement are used **nowhere**.
Test 11 enforces this mechanically: it strips C comments (the file documents why
`image_seq` is rejected — that is not a dependency) and fails if any real code
references those fields.

### Why the external manifest exists

The manifest records the rootfs' own hash, so it cannot live *inside* that
rootfs — writing it would change the squashfs and therefore the hash. Any scheme
that "fixes" this by excluding the manifest from the measurement weakens the
guarantee.

So the identity is split:

* `scripts/rt3000-mkinrootfs-manifest.sh` writes `/etc/rt3000-release.json`
  **into** the staging rootfs. It carries the metadata and the **kernel** hash —
  self-consistent, non-circular.
* `scripts/rt3000-mkmanifest.sh` writes the **external** manifest beside the
  finished images. It additionally carries `rootfs_sha256` and `rootfs_size`.

`rt3release verify` checks the running slot against whichever manifest is
available and reports honestly which halves it could check:

```
KERNEL_MATCH=PASS
ROOTFS_MATCH=NOT_IN_MANIFEST
ROOTFS_VERIFY=UNSUPPORTED_FROM_INSIDE_ROOTFS
RELEASE_IDENTITY_MATCH=PASS_KERNEL_ONLY
```

When given the external manifest both halves are checked and it reports
`RELEASE_IDENTITY_MATCH=PASS`.

## Status UX

`rt3slot status` reports:

```
RUNNING_SLOT=            RUNNING_RELEASE=
RUNNING_KERNEL_ID=       RUNNING_ROOTFS_ID=
QSDK_SLOT_VALID=         QSDK_SLOT_RELEASE=
INACTIVE_CONTENT_VERIFY=UNSUPPORTED
```

`INACTIVE_CONTENT_VERIFY=UNSUPPORTED` is deliberate. The inactive slot's payload
is not reachable through `/dev/ubi0_0` or `/dev/ubiblock0_1`, so a lightweight
content check is genuinely not possible. It is reported as unsupported rather
than faked.

`verify_qsdk` additionally refuses to report the slot valid if the identity
backend ever reports anything other than `IMAGE_SEQ_DEPENDENCY=NONE`, so a
regression back to format-metadata identity fails closed instead of silently
passing.

## Tests

`tests/rb002/run_tests.sh` — 13 cases, all passing:

| # | case | expected |
|---|---|---|
| 01 | canonical Product R1 candidate | PASS |
| 02 | different `image_seq`, identical content | identical verdict |
| 03 | kernel payload mutation | FAIL |
| 04 | rootfs payload mutation | FAIL |
| 05 | manifest wrong kernel hash | FAIL |
| 06 | manifest wrong rootfs hash | FAIL |
| 07 | wrong machine | FAIL |
| 08 | missing manifest | FAIL |
| 09 | malformed manifest | FAIL |
| 09b | wrong schema | FAIL |
| 10a | fixture proves `image_seq` really varies | — |
| 10 | `image_seq` changed, content identical | PASS for both |
| 11 | code has no `image_seq`/EC/VID/PEB dependency | PASS |

Result: `RB002_TESTS=PASS`, `IMAGE_SEQ_DEPENDENCY=NONE`.

The SHA-256 implementation is validated against the FIPS 180-4 vectors for the
empty string, `"abc"`, and 10^6 × `"a"` before being trusted for anything else.
