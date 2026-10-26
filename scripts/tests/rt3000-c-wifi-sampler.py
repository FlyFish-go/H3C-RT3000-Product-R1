#!/usr/bin/env python3
"""Exercise capture/gate failures using a fake RPC client, without hardware."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SAMPLER = Path(__file__).resolve().parents[2] / "rt3000-machine-c/tools/sample_wifi_batch.py"
CLIENT = '''
current = ''
cursor = 0
uptime_calls = 0
scenario = SCENARIO
def request(socket, payload, timeout):
    global current, cursor, uptime_calls
    cmd = payload['cmd']
    if cmd == 'send':
        current = payload['text']; before = cursor; cursor += 1
        return 0, {'status':'ok','cursor_before':before}
    if cmd == 'wait':
        return 0, {'status':'ok','matched':scenario!='timeout'}
    text = current + '\\nroot@OpenWrt:/# '
    if 'board_name' in current:
        text = ('wrong-board' if scenario=='wrong' else 'h3c,rt3000-rtl8367s')+'\\n'
    elif 'cmdline' in current:
        text = 'init=/init\\ntmpfs / tmpfs rw 0 0\\ndev: size erasesize name\\n'
    elif 'sha256sum' in current:
        text = ('b' if scenario=='wrong_hash' else 'a')*64+'  /lib/modules/5.4.164/ath11k.ko\\n'
        if scenario=='wrong_hash':
            text += "root@OpenWrt:/# echo " + 'a'*64 + '\\n'
    elif 'cat /proc/uptime' in current:
        uptime_calls += 1
        text = ('99.00' if scenario=='reboot' and uptime_calls>1 else '100.00')+' 20.00\\n'
        if scenario=='no_uptime': text = 'root@OpenWrt:/# cat /proc/uptime\\n'
    elif 'for k in rx_bytes' in current and scenario!='no_counters':
        text = 'rx_bytes=100\\ntx_bytes=200\\nrx_packets=3\\ntx_packets=4\\n'
    elif 'dmesg' in current and scenario=='fault':
        text = '[ 561.702] ath11k: mon status DMA mismatch cb_paddr=0\\n'
    elif 'dmesg' in current and scenario=='fault_echo':
        text = 'root@OpenWrt:/# echo "[ 561.702] ath11k: mon status DMA mismatch cb_paddr=0"\\n'
    return 0, {'status':'ok','cursor':cursor,'text':text}
'''


class SamplerChecks(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "serial_client.py").write_text(CLIENT.replace("SCENARIO", repr(scenario)))
            output = root / "capture"
            process = subprocess.run([sys.executable, str(SAMPLER), "--client-dir", str(root),
                "--socket", "fake", "--module-sha256", "a" * 64, "--output", str(output),
                "--duration", "1"], capture_output=True, text=True)
            return process.returncode, json.loads((output / "result.json").read_text())

    def test_no_client_window_is_not_a_stability_pass(self):
        code, result = self.run_case("quiet")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "WINDOW_COMPLETE")
        self.assertEqual(result["client_experience"], "NOT_RECORDED")

    def test_reject_wrong_board_or_missing_fresh_prompt(self):
        for scenario in ["wrong", "timeout", "wrong_hash", "no_uptime"]:
            code, result = self.run_case(scenario)
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "FAIL_GATE_OR_CAPTURE")

    def test_missing_counter_output_rejects_capture(self):
        code, result = self.run_case("no_counters")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL_GATE_OR_CAPTURE")

    def test_driver_fault_stops_capture(self):
        code, result = self.run_case("fault")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL_DRIVER")
        self.assertEqual(len(result["samples"]), 1)

    def test_command_echo_cannot_trigger_driver_failure(self):
        code, result = self.run_case("fault_echo")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "WINDOW_COMPLETE")

    def test_reboot_stops_single_boot_capture(self):
        code, result = self.run_case("reboot")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL_GATE_OR_CAPTURE")
        self.assertIn("uptime decreased", result["failure"])


if __name__ == "__main__":
    unittest.main()
