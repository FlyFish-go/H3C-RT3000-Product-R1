#!/usr/bin/env python3
"""Offline parser tests for 608 RX warning metadata; no device access."""
import contextlib
import hashlib
import importlib.util
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[2] /
          "rt3000-machine-c/tools/summarize_rx_warning_metadata.py")
spec = importlib.util.spec_from_file_location("rx_warning_metadata", SOURCE)
parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser_module)


def info3(pkt_type=3, mcs=12, nss_bitmap=0x05):
    value = ((pkt_type & 0xF) << 8) | ((mcs & 0xF) << 15) | ((nss_bitmap & 0xFF) << 24)
    return f"0x{value:08x}"


def invalid_vht(uptime="12.500000", valid="1", raw=None):
    if raw is None:
        raw = info3()
    return (f"[{uptime}] ath11k_pci 0000:01:00.0: rx-warning metadata "
            f"event=invalid_vht desc=0xc001 info3_valid={valid} info3={raw} "
            "pkt_type=3 info_pkt_type=3 rate_mcs=12 info_mcs=12 nss=2 "
            "nss_bitmap=0x05 info_nss=2 bw=2 sgi=0 status_encoding=2 "
            "status_rate_idx=12 status_nss=0")


def msdu_done(uptime="11.000001", first_valid="1", last_valid="1"):
    return (f"[{uptime}] ath11k_pci 0000:01:00.0: rx-warning metadata "
            f"event=msdu_done mac=0 msdu=0xc100 last=0xc200 rx_desc=0xc300 "
            f"last_desc=0xc400 cb_paddr=0x123400 first_valid={first_valid} "
            f"first_info3={info3(4, 7, 1)} last_valid={last_valid} "
            f"last_info3={info3(4, 9, 3)} attn_info0=0x0001 ppdu_id=0x1234 "
            "attn_info1=0x12345678 attn_info2=0x80000000 cookie=unavailable")


class EvidenceChecks(unittest.TestCase):
    def test_real_prefix_deduplicates_and_filters_inclusive_window(self):
        first = invalid_vht()
        duplicate = "Sun Sep 27 05:43:11 2026 kern.warn kernel: " + first
        out_of_range = msdu_done()
        result = parser_module.parse_text(
            "\n".join((first, duplicate, out_of_range)),
            Decimal("12.5"), Decimal("12.5"))
        self.assertEqual(result["summary"]["marker_lines"], 3)
        self.assertEqual(result["summary"]["unique_events_in_window"], 1)
        self.assertEqual(result["summary"]["unique_events_outside_window"], 1)
        event = result["events"][0]
        self.assertEqual(event["duplicate_count"], 1)
        self.assertEqual(len(event["raw_records"]), 2)
        self.assertEqual(event["decoded_info3"]["info3"]["pkt_type"], 3)
        self.assertEqual(event["decoded_info3"]["info3"]["mcs"], 12)
        self.assertEqual(event["decoded_info3"]["info3"]["nss_bitmap_value"], 5)
        self.assertEqual(event["decoded_info3"]["info3"]["nss"], 2)
        self.assertEqual(result["outside_window"][0]["event"], "msdu_done")

    def test_invalid_vht_mcs12_nss_zero_matches_expected_early_exit(self):
        result = parser_module.parse_text(invalid_vht())
        event = result["events"][0]
        decoded = event["decoded_info3"]
        self.assertEqual(decoded["comparisons"]["status"], "observational_comparison")
        self.assertEqual(decoded["comparisons"]["different_checks"], [])
        self.assertEqual(decoded["comparisons"]["checks"]["decoder_nss_vs_info3_popcount"]["status"], "equal")
        path = decoded["vht_status_path"]
        self.assertEqual(path["status"], "expected_vht_mcs_early_exit")
        self.assertEqual(path["status_nss_expected"], 0)
        self.assertEqual(path["checks"]["status_nss_stayed_zero_before_nss_assignment"]["status"], "equal")
        self.assertEqual(decoded["differences"], [])
        self.assertEqual(event["parse_errors"], [])

    def test_decoder_nss_is_popcount_for_sparse_and_multi_bit_bitmaps(self):
        cases = ((0x80, 1), (0x03, 2))
        for bitmap, nss in cases:
            line = invalid_vht(raw=info3(3, 12, bitmap))
            line = line.replace("nss_bitmap=0x05", f"nss_bitmap=0x{bitmap:02x}")
            line = line.replace("info_nss=2", f"info_nss={nss}")
            line = line.replace("nss=2", f"nss={nss}")
            result = parser_module.parse_text(line)
            decoded = result["events"][0]["decoded_info3"]
            self.assertEqual(decoded["info3"]["nss_bitmap_value"], bitmap)
            self.assertEqual(decoded["info3"]["nss"], nss)
            check = decoded["comparisons"]["checks"]["decoder_nss_vs_info3_popcount"]
            self.assertEqual(check["status"], "equal")

    def test_invalid_vht_field_disagreements_are_reported_observationally(self):
        line = invalid_vht().replace("info_pkt_type=3", "info_pkt_type=2").replace(
            "info_mcs=12", "info_mcs=9").replace("rate_mcs=12", "rate_mcs=11").replace(
            " nss=2 ", " nss=4 ").replace("status_nss=0", "status_nss=1")
        result = parser_module.parse_text(line)
        decoded = result["events"][0]["decoded_info3"]
        differences = {item["check"] for item in decoded["differences"]}
        self.assertIn("info_mcs_vs_info3", differences)
        self.assertIn("info_pkt_type_vs_info3", differences)
        self.assertIn("decoder_rate_mcs_vs_info3", differences)
        self.assertIn("decoder_nss_vs_info3_popcount", differences)
        self.assertIn("status_nss_stayed_zero_before_nss_assignment", differences)
        self.assertTrue(decoded["vht_status_path"]["not_a_root_cause_finding"])

    def test_invalid_flags_and_numeric_values_make_comparisons_unavailable(self):
        line = invalid_vht().replace("info3_valid=1", "info3_valid=2").replace(
            "rate_mcs=12", "rate_mcs=bad").replace("nss_bitmap=0x05", "nss_bitmap=0xzz")
        result = parser_module.parse_text(line)
        event = result["events"][0]
        decoded = event["decoded_info3"]
        self.assertTrue(any("invalid info3_valid flag" in error
                            for error in event["parse_errors"]))
        self.assertTrue(any("invalid rate_mcs decimal" in error for error in event["parse_errors"]))
        self.assertTrue(any("invalid nss_bitmap numeric format" in error for error in event["parse_errors"]))
        self.assertEqual(decoded["comparisons"]["status"], "skipped")
        self.assertIsNone(decoded["vht_status_path"])
        self.assertEqual(decoded["differences"], [])

    def test_invalid_info3_flag_zero_skips_comparisons(self):
        result = parser_module.parse_text(invalid_vht(valid="0"))
        decoded = result["events"][0]["decoded_info3"]
        self.assertIsNone(decoded["info3"])
        self.assertEqual(decoded["comparisons"]["status"], "skipped")
        self.assertIsNone(decoded["vht_status_path"])

    def test_echo_is_preserved_as_rejected_not_accepted(self):
        line = 'root@router:~# echo "[12.500000] ath11k_pci: rx-warning metadata event=invalid_vht"'
        result = parser_module.parse_text(line)
        self.assertEqual(result["summary"]["unique_events_in_window"], 0)
        self.assertEqual(result["rejected_marker_lines"][0]["raw"], line)

    def test_invalid_flag_keeps_raw_but_does_not_decode(self):
        result = parser_module.parse_text(invalid_vht(valid="0"))
        event = result["events"][0]
        self.assertIsNone(event["decoded_info3"]["info3"])
        self.assertEqual(event["fields"]["info3"], info3())
        self.assertEqual(event["parse_errors"], [])

    def test_msdu_valid_flags_gate_each_word_independently(self):
        result = parser_module.parse_text(msdu_done(first_valid="0", last_valid="1"))
        decoded = result["events"][0]["decoded_info3"]
        self.assertIsNone(decoded["first_info3"])
        self.assertIsNotNone(decoded["last_info3"])
        self.assertEqual(decoded["last_info3"]["nss"], 2)
        self.assertEqual(decoded["attention"]["msdu_done_bit"], True)
        self.assertEqual(decoded["attention"]["status"], "observed_only")

        no_done = msdu_done().replace("attn_info2=0x80000000", "attn_info2=0x00000000")
        result = parser_module.parse_text(no_done)
        self.assertEqual(result["events"][0]["decoded_info3"]["attention"]["msdu_done_bit"], False)

        invalid_last = parser_module.parse_text(msdu_done(last_valid="0"))
        self.assertEqual(invalid_last["events"][0]["decoded_info3"]["attention"]["status"], "skipped")

    def test_missing_or_illegal_hex_is_explicit(self):
        missing = invalid_vht().replace(f"info3={info3()} ", "")
        result = parser_module.parse_text(missing)
        self.assertIn("missing info3", result["events"][0]["parse_errors"])
        illegal = parser_module.parse_text(invalid_vht(raw="0x12xyz"))
        self.assertTrue(any("invalid info3 u32 hex" in e
                            for e in illegal["events"][0]["parse_errors"]))
        illegal_msdu = parser_module.parse_text(msdu_done().replace(
            f"first_info3={info3(4, 7, 1)}", "first_info3=garbage"))
        self.assertTrue(any("invalid first_info3 u32 hex" in e
                            for e in illegal_msdu["events"][0]["parse_errors"]))
        illegal_attention = parser_module.parse_text(msdu_done().replace(
            "attn_info2=0x80000000", "attn_info2=0x0000000g"))
        event = illegal_attention["events"][0]
        self.assertTrue(any("invalid attn_info2 numeric format" in e
                            for e in event["parse_errors"]))
        self.assertEqual(event["decoded_info3"]["attention"]["status"], "not_decoded")

    def test_duplicate_numeric_field_is_not_used_for_mismatch_guess(self):
        line = invalid_vht().replace("rate_mcs=12", "rate_mcs=12 rate_mcs=bad")
        event = parser_module.parse_text(line)["events"][0]
        self.assertIn("duplicate field: rate_mcs", event["parse_errors"])
        self.assertEqual(event["decoded_info3"]["comparisons"]["checks"][
            "decoder_rate_mcs_vs_info3"]["status"], "not_comparable")

    def test_cli_writes_new_json_output(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.txt"
            output = root / "result.json"
            source.write_bytes(invalid_vht().encode("utf-8"))
            source_bytes = source.read_bytes()
            status = parser_module.main([str(source), "--output", str(output),
                                         "--start-uptime", "12.5",
                                         "--end-uptime", "12.5"])
            self.assertEqual(status, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["summary"]["unique_events_in_window"], 1)
            self.assertEqual(result["input_evidence"]["byte_length"], len(source_bytes))
            self.assertEqual(result["input_evidence"]["sha256"],
                             hashlib.sha256(source_bytes).hexdigest())
            self.assertEqual(result["result_scope"]["kind"], "observational_summary_only")
            self.assertEqual(result["result_scope"]["root_cause"], "NOT_ASSESSED")
            self.assertEqual(result["result_scope"]["pass_fail"], "NOT_ASSESSED")

    def test_cli_refuses_to_overwrite_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.txt"
            output = root / "result.json"
            source.write_text(invalid_vht(), encoding="utf-8")
            output.write_text("keep", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                status = parser_module.main([str(source), "--output", str(output)])
            self.assertEqual(status, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
