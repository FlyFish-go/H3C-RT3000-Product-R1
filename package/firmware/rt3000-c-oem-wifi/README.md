# RT3000 C2 OEM Wi-Fi data (private)

This package is selected only by the `h3c_rt3000_rtl8367s_ram` image. It
supplies ath11k board containers and C2 calibration data; the generic IPQ5018
and QCN6122 firmware packages supply executable radio firmware. Do not use
these board or ART bytes on Machine B or another C sample.

The current C2 OEM active FDT (`/sys/firmware/fdt`, SHA-256
`dd6a92c09ffd70cbf4e6407f9dbfa553d2da3524e2e1627417d0f2d6197ee21b`)
reports wifi0 board ID `0x23`, BDF address `0x4c400000`, and wifi1 board ID
`0xb0`, BDF address `0x4d300000` in 256 MiB target-memory mode. OEM runtime
files and original backups were compared before packaging:

| File in this package | Origin | SHA-256 |
|---|---|---|
| `board-2-ipq5018.bin` | C OEM `IPQ5018/bdwlan.b23` (128 KiB body unchanged) | `aff390f102a1ef9e07ccfce207abf639c36daec04a7ff99dcd33ebb95abc1df2` |
| `board-2-qcn6122.bin` | C OEM `qcn6122/bdwlan.bb0` (128 KiB body unchanged) | `935327c086275cfc559db3bd5bec6537f415e81459b32cf8108cedbf8e2af32b` |
| `caldata-ipq5018.bin` | C ART offset `0x1000`, length `0x20000` | `88be7e89568ccc7a3602833085077edf62a095d83e850f960bb8bd9eb9d2b622` |
| `caldata-qcn6122.bin` | C ART offset `0x26800`, length `0x20000` | `345918493f88f74d0c2ce22dcb606e5aace12a758efb3df9b9b227be6519d97a` |

The two board containers reuse only the 84-byte ath11k container header from
the Machine B files. The C OEM BDF bodies are preserved byte for byte. The
5 GHz header selects decimal board ID 176 (`0xb0`), while the 2.4 GHz header
selects decimal 35 (`0x23`). Rebuild and validate them with
`rt3000-machine-c/tools/build_oem_bdf_containers.py` and its offline tests.
The raw OEM BDFs were extracted from the C OEM rootfs `wifi_fw` image, whose
backing `mtd15` SHA-256 was
`8576670fa1d778af8ab22ec2f3de3b36feccb4a8cf80356c711d9c355beba99c`.
The ART backup SHA-256 was
`12746b4204f8940410486985506051c086cd0902271ad4f2ec1d7b1e957977cf`.

All four installed files have pinned hashes in `files/SHA256SUMS`; the package
install fails if any source byte changes. Their presence and hashes do not
establish QSDK ath11k compatibility; that requires a controlled C RAM boot.

## Native default: `board-2-qcn6122-axis0.bin`

The `h3c_rt3000_rtl8367s_native_slot1` image installs `board-2-qcn6122-axis0.bin`
instead of the raw OEM container. It differs from `board-2-qcn6122.bin` in two
bytes only: BDF body offset `0x45c` (antenna-chain axis gate) is `0x00` instead
of `0x03`, and the body checksum is recomputed. With the raw body the
`WLAN.HK.2.7.0.1-01744` firmware asserts `phyrf_bdf.c:6245
ANTENNACHAIN_AXIS_Z` and the ath11k recovery path panics the kernel. This is the
BDF that ran on Native08 (2026-10-05, built via `RT3000_C_NATIVE_QCN6122_BDF`)
and on build01 (2026-10-23). RAM profiles keep the raw container.
