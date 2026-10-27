#!/usr/bin/env python3
"""Check WAN polling on each RT3000 board's NAND and RAM DTS paths."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DTS = ROOT / "target/linux/ipq50xx/dts"
IMAGE = ROOT / "target/linux/ipq50xx/image/Makefile"
C_NATIVE = ROOT / "rt3000-machine-c/native"


def uncomment(text):
    # Keep quoted values intact while removing both styles of DTS comments.
    token = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', re.S)
    return token.sub(lambda m: m.group() if m.group().startswith('"') else " ", text)


def mask_strings(text):
    return re.sub(r'"(?:\\.|[^"\\])*"', lambda m: ' ' * len(m.group()), text)


def dp1_properties(text):
    text = uncomment(text)
    masked = mask_strings(text)
    matches = list(re.finditer(r'\bmac0\s*:\s*dp1\s*\{', masked))
    all_dp1 = re.findall(r'\bdp1\s*\{', masked)
    if len(matches) != 1 or len(all_dp1) != 1:
        raise AssertionError("expected one mac0: dp1 node")
    if re.search(r'&\s*(?:mac0\b|\{\s*/dp1\s*\})\s*\{|/delete-node/\s*(?:&mac0\b|dp1\b)', masked):
        raise AssertionError("dp1 overridden or deleted")
    start = matches[0].end()
    # The node must be a direct child of /, rather than a decoy nested node.
    if masked[:start].count("{") - masked[:start].count("}") != 2:
        raise AssertionError("dp1 is not a direct root child")
    depth = 1
    for end in range(start, len(masked)):
        if masked[end] == "{":
            depth += 1
        elif masked[end] == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        raise AssertionError("unterminated dp1 node")
    block = text[start:end]
    # These profiles have no child nodes; avoid accepting properties in children.
    if "{" in mask_strings(block):
        raise AssertionError("unexpected child node in dp1")
    return block


def check_dp1(text):
    block = dp1_properties(text)
    for name, value in {
        "qcom,link-poll": r"<\s*1\s*>",
        "qcom,phy-mdio-addr": r"<\s*7\s*>",
        "mdio-bus": r"<\s*&mdio0\s*>",
    }.items():
        assignments = re.findall(
            r'(?m)^\s*' + re.escape(name) + r'\s*(?:=\s*([^;]+))?\s*;',
            block,
        )
        if len(assignments) != 1 or not re.fullmatch(value, assignments[0].strip()):
            raise AssertionError(f"dp1 {name}: expected exactly one {value}")
    if re.search(r'/delete-property/|^\s*status\s*=\s*"disabled"\s*;', block, re.M):
        raise AssertionError("dp1 properties deleted or node disabled")


def check_no_dp1_override(text):
    text = mask_strings(uncomment(text))
    # A wrapper may change other nodes, but it must not redefine or remove WAN.
    if re.search(
        r'&\s*(?:mac0\b|\{\s*/dp1\s*\})|'
        r'(?:\bmac0\s*:\s*)?\bdp1\s*\{|'
        r'/delete-node/\s*(?:&mac0\b|dp1\b)',
        text,
    ):
        raise AssertionError("wrapper changes dp1")


def assignment(body, name):
    matches = re.findall(r'(?m)^\s*' + re.escape(name) + r'\s*[:?+]?=\s*(.*?)\s*$', body)
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} assignment")
    return matches[0]


def device(name):
    text = IMAGE.read_text()
    match = re.search(
        r'(?ms)^define Device/' + re.escape(name) + r'\s*\n(.*?)^endef\s*$',
        text,
    )
    if not match:
        raise AssertionError(f"missing Device/{name}")
    return match.group(1)


class WanLinkPoll(unittest.TestCase):
    def test_board_dp1(self):
        boards = {
            "A NAND": DTS / "ipq5018-rw3000-hw-a.dts",
            "B NAND": DTS / "ipq5000-rt3000.dts",
            "C RAM": DTS / "ipq5000-rt3000-rtl8367s.dts",
            "C MTD RAM": DTS / "ipq5000-rt3000-rtl8367s-mtd-discovery.dts",
            "C NAND": C_NATIVE / "ipq5000-rt3000-rtl8367s-persistent.dts",
            "C installer RAM": C_NATIVE / "ipq5000-rt3000-rtl8367s-installer.dts",
            "D NAND": DTS / "ipq5000-nx30-hw-d.dts",
        }
        for label, path in boards.items():
            with self.subTest(board=label):
                check_dp1(path.read_text())

    def test_ram_wrappers_inherit_board_dp1(self):
        wrappers = {
            "ipq5018-rw3000-hw-a-initramfs.dts": "ipq5018-rw3000-hw-a.dts",
            "ipq5000-rt3000-initramfs.dts": "ipq5000-rt3000.dts",
            "ipq5000-nx30-hw-d-initramfs.dts": "ipq5000-nx30-hw-d.dts",
            "ipq5000-nx30-hw-d-installer-initramfs.dts": "ipq5000-nx30-hw-d.dts",
        }
        for wrapper, parent in wrappers.items():
            with self.subTest(wrapper=wrapper):
                text = uncomment((DTS / wrapper).read_text())
                includes = re.findall(r'(?m)^\s*#\s*include\s*"([^"]+)"', text)
                self.assertEqual(includes, [parent])
                self.assertEqual(len(re.findall(r'(?m)^\s*#\s*include\b', text)), 1)
                check_no_dp1_override(text)
                check_dp1((DTS / parent).read_text())

    def test_image_profiles_choose_checked_dts(self):
        profiles = {
            "h3c_rw3000_hw_a": ("ipq5018-rw3000-hw-a", "ipq5018-rw3000-hw-a-initramfs"),
            "h3c_rt3000": ("ipq5000-rt3000", "ipq5000-rt3000-initramfs"),
            "h3c_nx30_hw_d": ("ipq5000-nx30-hw-d", "ipq5000-nx30-hw-d-initramfs"),
        }
        for name, (nand, ram) in profiles.items():
            with self.subTest(profile=name):
                body = device(name)
                self.assertIn(nand, assignment(body, "DEVICE_DTS").split())
                self.assertIn(ram, assignment(body, "DEVICE_DTS").split())
                self.assertRegex(assignment(body, "KERNEL"), re.escape("/image-" + nand + ".dtb") + r'$')
                self.assertRegex(assignment(body, "KERNEL_INITRAMFS"), re.escape("/image-" + ram + ".dtb") + r'$')

        direct = {
            "h3c_nx30_hw_d_ram": "ipq5000-nx30-hw-d-initramfs",
            "h3c_nx30_hw_d_installer_ram": "ipq5000-nx30-hw-d-installer-initramfs",
            "h3c_rt3000_rtl8367s_ram": "ipq5000-rt3000-rtl8367s",
            "h3c_rt3000_rtl8367s_mtd_discovery_ram": "ipq5000-rt3000-rtl8367s-mtd-discovery",
            "h3c_rt3000_rtl8367s_native_slot1": "ipq5000-rt3000-rtl8367s-persistent",
            "h3c_rt3000_rtl8367s_installer_ram": "ipq5000-rt3000-rtl8367s-installer",
        }
        for name, expected in direct.items():
            with self.subTest(profile=name):
                self.assertEqual(assignment(device(name), "DEVICE_DTS"), expected)
        for name in ("h3c_rt3000_rtl8367s_native_slot1", "h3c_rt3000_rtl8367s_installer_ram"):
            self.assertEqual(assignment(device(name), "DEVICE_DTS_DIR"), "$(TOPDIR)/rt3000-machine-c/native")

    def test_decoys_and_overrides_are_rejected(self):
        source = '''
        / {
            mac0: dp1 { mdio-bus = <&mdio0>; };
            dp2 { qcom,link-poll = <1>; qcom,phy-mdio-addr = <7>; };
        };
        '''
        with self.assertRaises(AssertionError):
            check_dp1(source)
        with self.assertRaises(AssertionError):
            check_no_dp1_override('&mac0 { /delete-property/ qcom,link-poll; };')


if __name__ == "__main__":
    unittest.main()
