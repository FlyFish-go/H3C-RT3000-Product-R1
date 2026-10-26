#!/usr/bin/env python3
"""Run the real Machine-C firstboot and PHY-add policy in a temporary sandbox.

Only absolute runtime file paths are redirected into a temporary tree.  The
policy scripts themselves are otherwise copied verbatim.  UCI, board_name,
lock and logger are isolated command stubs; host /sys and device state are not
read or modified.
"""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "target/linux/ipq50xx/base-files"
MAC_SH = BASE / "lib/rt3000/mac.sh"
WIFI_SH = BASE / "lib/rt3000/wifi-c.sh"
UCI_DEFAULTS = BASE / "etc/uci-defaults/99-rt3000-wifi"
HOTPLUG = BASE / "etc/hotplug.d/ieee80211/20-rt3000-c-wifi"
WAN_MAC = "00:11:22:33:44:55"

UCI_STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

dbpath = Path(os.environ["UCI_DB"])
data = json.loads(dbpath.read_text())
args = sys.argv[1:]
if args and args[0] == "-q": args = args[1:]
if not args: sys.exit(2)
cmd, *rest = args

def pathget(path):
    bits = path.split(".")
    if len(bits) < 2: return None
    pkg, section, *option = bits
    sec = data.get(pkg, {}).get("sections", {}).get(section)
    if sec is None: return None
    if not option: return sec.get("type")
    return sec.get("options", {}).get(".".join(option))

def split_assignment(value):
    lhs, rhs = value.split("=", 1)
    if len(rhs) >= 2 and rhs[0] == rhs[-1] and rhs[0] in "'\"":
        rhs = rhs[1:-1]
    return lhs, rhs

if cmd == "show":
    pkg = rest[0] if rest else ""
    if pkg not in data: sys.exit(1)
    for section, sec in data[pkg]["sections"].items():
        print(f"{pkg}.{section}={sec['type']}")
        for key, value in sec.get("options", {}).items():
            print(f"{pkg}.{section}.{key}={json.dumps(value)}")
    sys.exit(0)
if cmd == "get":
    value = pathget(rest[0])
    if value is None: sys.exit(1)
    print(value)
    sys.exit(0)
if cmd == "set":
    lhs, value = split_assignment(rest[0])
    bits = lhs.split(".")
    if len(bits) == 2:
        pkg, section = bits
        sec = data.setdefault(pkg, {"sections": {}})["sections"].setdefault(
            section, {"options": {}})
        sec["type"] = value
        dbpath.write_text(json.dumps(data))
        sys.exit(0)
    if len(bits) < 3: sys.exit(2)
    pkg, section, option = bits[0], bits[1], ".".join(bits[2:])
    sec = data.setdefault(pkg, {"sections": {}})["sections"].setdefault(
        section, {"type": "unknown", "options": {}})
    sec.setdefault("options", {})[option] = value
    dbpath.write_text(json.dumps(data))
    sys.exit(0)
if cmd == "delete":
    bits = rest[0].split(".")
    if len(bits) >= 3:
        sec = data.get(bits[0], {}).get("sections", {}).get(bits[1], {})
        sec.get("options", {}).pop(".".join(bits[2:]), None)
        dbpath.write_text(json.dumps(data))
    sys.exit(0)
if cmd == "commit":
    pkg = rest[0] if rest else ""
    log = Path(os.environ["UCI_COMMIT_LOG"])
    with log.open("a") as stream: stream.write(pkg + "\n")
    sys.exit(1 if os.environ.get("FAIL_COMMIT") == pkg else 0)
sys.exit(2)
'''


class FirstbootPolicyChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "uci").write_text(UCI_STUB)
        (self.bin / "uci").chmod(0o755)
        for name, body in {
            "board_name": '#!/bin/sh\nprintf "%s\\n" "$TEST_BOARD"\n',
            "logger": "#!/bin/sh\nexit 0\n",
            "lock": '#!/bin/sh\n[ "${LOCK_FAIL:-0}" != 1 ]\n',
        }.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)

        self.sys_class = self.root / "sys/class/ieee80211"
        self.sys_devices = self.root / "sys/devices"
        self.sys_class.mkdir(parents=True)
        self.sys_devices.mkdir(parents=True)
        eth = self.root / "sys/class/net/eth0/address"
        eth.parent.mkdir(parents=True)
        eth.write_text(WAN_MAC + "\n")

        self.lib = self.root / "lib/rt3000"
        self.lib.mkdir(parents=True)
        self.mac_copy = self.lib / "mac.sh"
        self.wifi_copy = self.lib / "wifi-c.sh"
        self.mac_copy.write_text(MAC_SH.read_text())
        wifi_text = WIFI_SH.read_text().replace(
            "/sys/class/ieee80211", str(self.sys_class))
        self.wifi_copy.write_text(wifi_text)

        self.functions_stub = self.root / "lib/functions.sh"
        self.functions_stub.parent.mkdir(parents=True, exist_ok=True)
        self.functions_stub.write_text(":\n")
        self.default_copy = self.root / "99-rt3000-wifi"
        self.hotplug_copy = self.root / "20-rt3000-c-wifi"
        self.default_copy.write_text(self._rewrite(UCI_DEFAULTS.read_text()))
        self.hotplug_copy.write_text(self._rewrite(HOTPLUG.read_text()))

        self.db = self.root / "uci.json"
        self.commit_log = self.root / "commits"
        self.commit_log.write_text("")

    def tearDown(self):
        self.temp.cleanup()

    def _rewrite(self, text):
        return (text.replace("/lib/rt3000/mac.sh", str(self.mac_copy))
                    .replace("/lib/rt3000/wifi-c.sh", str(self.wifi_copy))
                    .replace("/lib/functions.sh", str(self.functions_stub))
                    .replace("/sys/class/ieee80211", str(self.sys_class))
                    .replace("/sys/class/net/eth0/address",
                             str(self.root / "sys/class/net/eth0/address")))

    def add_phy(self, phy, node):
        path = self.sys_class / phy
        path.mkdir(parents=True, exist_ok=True)
        target = self.sys_devices / node
        target.mkdir(parents=True, exist_ok=True)
        (path / "device").symlink_to(target)

    @staticmethod
    def config(*sections):
        return {"wireless": {"sections": {name: {
            "type": kind, "options": dict(opts)}
            for name, kind, opts in sections}}}

    def write_config(self, config):
        self.db.write_text(json.dumps(copy.deepcopy(config)))
        self.commit_log.write_text("")

    def state(self):
        return json.loads(self.db.read_text())

    def run_script(self, script, *, board="h3c,rt3000-rtl8367s", action="add",
                   lock_fail=False, fail_commit=""):
        env = os.environ.copy()
        env.update({
            "PATH": str(self.bin) + os.pathsep + "/usr/bin:/bin",
            "UCI_DB": str(self.db),
            "UCI_COMMIT_LOG": str(self.commit_log),
            "TEST_BOARD": board,
            "ACTION": action,
            "LOCK_FAIL": "1" if lock_fail else "0",
            "FAIL_COMMIT": fail_commit,
        })
        return subprocess.run(["/bin/sh", str(script)], env=env,
                              capture_output=True, text=True)

    def stock_radio(self, section, path, iface, extra_device=None,
                    extra_iface=None):
        opts = {"path": path, "disabled": "1"}
        if extra_device:
            opts.update(extra_device)
        iface_opts = {"device": section, "mode": "ap", "network": "lan",
                      "ssid": "OpenWrt", "encryption": "none", "disabled": "1"}
        if extra_iface:
            iface_opts.update(extra_iface)
        return [(section, "wifi-device", opts),
                (iface, "wifi-iface", iface_opts)]

    def policy(self, board="h3c,rt3000-rtl8367s"):
        return self.run_script(self.default_copy, board=board)

    def test_swapped_phy_enumeration_matches_physical_paths(self):
        self.add_phy("phy0", "soc:wifi1@c000000")
        self.add_phy("phy1", "c000000.wifi")
        cfg = self.config(
            *self.stock_radio("radio0", "platform/soc/c000000.wifi", "default_radio0"),
            *self.stock_radio("radio1", "platform/soc/soc:wifi1@c000000", "default_radio1"))
        self.write_config(cfg)
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.state()["wireless"]["sections"]
        self.assertEqual(out["default_radio0"]["options"]["ssid"], "RT3000")
        self.assertEqual(out["radio0"]["options"]["band"], "2g")
        self.assertEqual(out["default_radio1"]["options"]["ssid"], "RT3000-5G")
        self.assertEqual(out["radio1"]["options"]["band"], "5g")

    def test_2g_first_then_late_5g_hotplug(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(*self.stock_radio(
            "radio0", "platform/soc/c000000.wifi", "default_radio0"))
        self.write_config(cfg)
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        after_first = self.state()["wireless"]["sections"]
        self.assertEqual(after_first["default_radio0"]["options"]["ssid"], "RT3000")
        self.assertNotIn("radio1", after_first)

        self.add_phy("phy1", "soc:wifi1@c000000")
        state = self.state()
        after_first = state["wireless"]["sections"]
        after_first["radio1"] = {"type": "wifi-device", "options": {
            "path": "platform/soc/soc:wifi1@c000000", "disabled": "1"}}
        after_first["default_radio1"] = {"type": "wifi-iface", "options": {
            "device": "radio1", "mode": "ap", "network": "lan", "ssid": "OpenWrt",
            "encryption": "none", "disabled": "1"}}
        self.db.write_text(json.dumps(state))
        result = self.run_script(self.hotplug_copy)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.state()["wireless"]["sections"]
        self.assertEqual(out["default_radio1"]["options"]["ssid"], "RT3000-5G")
        self.assertEqual(out["radio1"]["options"]["band"], "5g")

    def test_unknown_board_and_no_phy_do_not_create_sections(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(*self.stock_radio(
            "radio0", "platform/soc/c000000.wifi", "default_radio0"))
        self.write_config(cfg)
        before = self.state()
        result = self.policy(board="vendor,unknown")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.state(), before)

        self.sys_class.joinpath("phy0/device").unlink()
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["wireless"]["sections"], before["wireless"]["sections"])

    def test_stock_templates_become_disabled_psk2_with_key(self):
        self.add_phy("phy0", "c000000.wifi")
        self.add_phy("phy1", "soc:wifi1@c000000")
        cfg = self.config(
            *self.stock_radio("radio0", "platform/soc/c000000.wifi", "default_radio0"),
            *self.stock_radio("radio1", "platform/soc/soc:wifi1@c000000", "default_radio1"))
        self.write_config(cfg)
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        for radio in ("radio0", "radio1"):
            self.assertEqual(self.state()["wireless"]["sections"][radio]["options"]["disabled"], "1")
        for section in ("default_radio0", "default_radio1"):
            iface = self.state()["wireless"]["sections"][section]["options"]
            self.assertEqual(iface["disabled"], "1")
            self.assertEqual(iface["encryption"], "psk2")
            self.assertTrue(iface["key"])
            self.assertGreaterEqual(len(iface["key"]), 8)
        cpu = self.state()["network"]["sections"]["rt3000_c_cpu"]
        self.assertEqual(cpu["type"], "device")
        self.assertEqual(cpu["options"]["name"], "eth1")
        self.assertRegex(cpu["options"]["macaddr"], r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")

    def test_custom_open_wpa_and_sta_sections_are_preserved(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(
            ("radio0", "wifi-device", {"path": "platform/soc/c000000.wifi", "disabled": "0"}),
            ("custom_open", "wifi-iface", {"device": "radio0", "mode": "ap", "ssid": "Guest", "encryption": "none", "network": "guest", "disabled": "0"}),
            ("custom_wpa", "wifi-iface", {"device": "radio0", "mode": "ap", "ssid": "Mine", "encryption": "psk2", "key": "custom-secret", "network": "lan", "disabled": "0"}),
            ("client", "wifi-iface", {"device": "radio0", "mode": "sta", "ssid": "upstream", "encryption": "psk2", "key": "client-secret"}))
        self.write_config(cfg)
        result = self.policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.state()["wireless"]["sections"]
        self.assertEqual(out["custom_open"]["options"]["ssid"], "Guest")
        self.assertEqual(out["custom_open"]["options"]["encryption"], "none")
        self.assertEqual(out["custom_open"]["options"]["rt3000_c_policy"], "preserve")
        self.assertEqual(out["custom_wpa"]["options"]["key"], "custom-secret")
        self.assertEqual(out["custom_wpa"]["options"]["rt3000_c_policy"], "preserve")
        self.assertEqual(out["client"]["options"]["mode"], "sta")
        self.assertNotIn("rt3000_c_policy", out["client"]["options"])

    def test_repeated_hotplug_does_not_change_radio_enable_state(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(*self.stock_radio(
            "radio0", "platform/soc/c000000.wifi", "default_radio0"))
        self.write_config(cfg)
        self.assertEqual(self.policy().returncode, 0)
        first = self.state()
        for _ in range(2):
            result = self.run_script(self.hotplug_copy)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = self.state()
            self.assertEqual(state["wireless"]["sections"]["radio0"]["options"]["disabled"], "1")
            self.assertEqual(state["wireless"]["sections"]["default_radio0"]["options"]["disabled"], "1")
        self.assertEqual(self.state()["wireless"]["sections"], first["wireless"]["sections"])

    def test_managed_macs_refresh_but_preserved_mac_is_untouched(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(
            ("radio0", "wifi-device", {"path": "platform/soc/c000000.wifi", "disabled": "1"}),
            ("default_radio0", "wifi-iface", {"device": "radio0", "mode": "ap", "network": "lan", "ssid": "OpenWrt", "encryption": "none", "disabled": "1"}),
            ("radio1", "wifi-device", {"path": "platform/soc/soc:wifi1@c000000", "disabled": "0"}),
            ("owned", "wifi-iface", {"device": "radio1", "mode": "ap", "ssid": "mine", "encryption": "psk2", "key": "x", "disabled": "0", "macaddr": "02:aa:bb:cc:dd:ee"}))
        self.write_config(cfg)
        self.assertEqual(self.policy().returncode, 0)
        before = self.state()["wireless"]["sections"]
        old_managed = before["default_radio0"]["options"]["macaddr"]
        preserved = before["owned"]["options"]["macaddr"]
        new_wan = "00:11:22:33:44:66"
        (self.root / "sys/class/net/eth0/address").write_text(new_wan + "\n")
        result = self.run_script(self.hotplug_copy)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.state()["wireless"]["sections"]
        self.assertNotEqual(after["default_radio0"]["options"]["macaddr"], old_managed)
        self.assertEqual(after["radio0"]["options"]["macaddr"],
                         after["default_radio0"]["options"]["macaddr"])
        self.assertEqual(after["owned"]["options"]["macaddr"], preserved)

    def test_lock_and_commit_failures_are_reported(self):
        self.add_phy("phy0", "c000000.wifi")
        cfg = self.config(*self.stock_radio(
            "radio0", "platform/soc/c000000.wifi", "default_radio0"))
        self.write_config(cfg)
        locked = self.run_script(self.default_copy, lock_fail=True)
        self.assertNotEqual(locked.returncode, 0)

        self.write_config(cfg)
        network_commit = self.run_script(self.default_copy, fail_commit="network")
        self.assertNotEqual(network_commit.returncode, 0)

        self.write_config(cfg)
        committed = self.run_script(self.default_copy, fail_commit="wireless")
        self.assertNotEqual(committed.returncode, 0)

        self.write_config(cfg)
        hotplug = self.run_script(self.hotplug_copy, lock_fail=True)
        self.assertNotEqual(hotplug.returncode, 0)
        hotplug_commit = self.run_script(self.hotplug_copy, fail_commit="wireless")
        self.assertNotEqual(hotplug_commit.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
