#!/usr/bin/env python3
"""Reject unsafe/incomplete read-only boot-table evidence; no device access."""
import importlib.util
from pathlib import Path
import struct
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "rt3000-machine-c/tools/audit_boot_chain.py"
spec = importlib.util.spec_from_file_location("boot_audit", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def table(selector=0):
    data = bytearray(audit.TABLE_BYTES)
    struct.pack_into("<III", data, 0, 0xA3A2A1A0, 1, 1)
    data[12:19] = b"rootfs\0"
    struct.pack_into("<I", data, 28, selector)
    struct.pack_into("<I", data, 0x14C, 0xB3B2B1B0)
    return bytes(data)


def dump(address, data):
    result = []
    for i in range(0, len(data), 16):
        words = struct.unpack("<" + "I" * (len(data[i:i + 16]) // 4), data[i:i + 16])
        result.append(f"{address+i:08x}: " + " ".join(f"{w:08x}" for w in words) + "    ................")
    return "\r\n".join(result)


class EvidenceChecks(unittest.TestCase):
    def test_code_selector_zero_and_nonzero(self):
        self.assertEqual(audit.bootconfig(table())["rootfs_code_branch"], "rootfs")
        self.assertEqual(audit.bootconfig(table(7))["rootfs_code_branch"], "rootfs_1")

    def test_live_table_matches_allocated_region(self):
        entry = struct.pack("<4I", 1, 0x5D28, audit.TABLE_BYTES, 0)
        log = dump(audit.SMEM_ENTRY, entry) + "\r\n" + dump(audit.SMEM_BASE + 0x5D28, table())
        self.assertEqual(audit.live_table(log)["data"], table())

    def test_reject_unallocated_wrong_size_and_outside_region(self):
        for entry in [(0, 0x5D28, 336, 0), (1, 0x5D28, 340, 0), (1, 0xFFFFFF00, 336, 0), (1, 0x5D29, 336, 0)]:
            with self.assertRaises(ValueError):
                audit.live_table(dump(audit.SMEM_ENTRY, struct.pack("<4I", *entry)))

    def test_reject_incomplete_and_conflicting_dump(self):
        entry = dump(audit.SMEM_ENTRY, struct.pack("<4I", 1, 0x5D28, 336, 0))
        with self.assertRaisesRegex(ValueError, "missing table dump"):
            audit.live_table(entry)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            audit.words_from_log(entry + "\n" + dump(audit.SMEM_ENTRY, struct.pack("<4I", 0, 0x5D28, 336, 0)))

    def test_reject_bad_magic_and_missing_selector(self):
        for position in [0, 0x14C]:
            data = bytearray(table()); data[position] ^= 1
            with self.assertRaises(ValueError):
                audit.bootconfig(data)
        data = bytearray(table()); data[12:19] = b"unused\0"
        with self.assertRaisesRegex(ValueError, "missing rootfs"):
            audit.bootconfig(data)


if __name__ == "__main__":
    unittest.main()
