#!/usr/bin/env python3
"""Mock-transcript tests for the fail-closed RT3000 controller."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


HERE = pathlib.Path(__file__).resolve()
MODULE_PATH = HERE.parents[2] / "tools" / "device" / "rt3000ctl.py"
SPEC = importlib.util.spec_from_file_location("rt3000ctl", MODULE_PATH)
assert SPEC and SPEC.loader
rt3000ctl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rt3000ctl
SPEC.loader.exec_module(rt3000ctl)


KERNEL = rt3000ctl.EXPECTED_KERNEL_ID
MTD15 = rt3000ctl.EXPECTED_MTD15_SHA256


PRE_OK = f"""\
runtime_system=QSDK
persistent_selector=1
bootconfig_copy_health=YES
oem_slot_status=PASS
qsdk_slot_status=PASS
RUNNING_RELEASE=Product R1 RC1
RUNNING_KERNEL_ID={KERNEL}
QSDK_SLOT_VALID=PASS
RELEASE_NAME=Product R1 RC1
RELEASE_KERNEL_ID={KERNEL}
RELEASE_NETWORK_BASELINE=R1-NET-D
mtd3(0:BOOTCONFIG1) rootfs selector = 0x00000001
mtd2(0:BOOTCONFIG) rootfs selector = 0x00000001
copies_agree=YES
KERNEL_RELEASE=5.4.164
MTD15_SHA256={MTD15}
RESULT=COMMAND_RC_0
"""

POST_OK = f"""\
KERNEL_RELEASE=4.4.60
mtd15: 02800000 00020000 "rootfs"
mtd16: 02800000 00020000 "rootfs_1"
mtd3(0:BOOTCONFIG1) rootfs selector = 0x00000000
mtd2(0:BOOTCONFIG) rootfs selector = 0x00000000
copies_agree=YES
MTD15_SHA256={MTD15}
RESULT=COMMAND_RC_0
"""


class FakeTransport:
    def __init__(self, *, pre=PRE_OK, action="Linux 4.4.60\nRESULT=TIMEOUT_NO_RC\n",
                 post=POST_OK, wait="WAIT_OK=True\nLinux 4.4.60\n"):
        self.transcripts = {
            "status": rt3000ctl.CommandResult(pre, 0),
            "enter-oem": rt3000ctl.CommandResult(action, 4),
            "post-oem": rt3000ctl.CommandResult(post, 0),
        }
        self.wait_result = rt3000ctl.CommandResult(wait, 0)
        self.calls = []

    def run_status(self, timeout):
        self.calls.append(("run", "status", timeout))
        return self.transcripts["status"]

    def run_fixed(self, name, timeout):
        self.calls.append(("run", name, timeout))
        return self.transcripts[name]

    def run_post_oem(self, timeout):
        self.calls.append(("run", "post-oem", timeout))
        return self.transcripts["post-oem"]

    def wait_for_boot_event(self, timeout):
        self.calls.append(("wait", timeout))
        return self.wait_result


class CaptureRunner:
    def __init__(self):
        self.argv = None

    def __call__(self, argv, **kwargs):
        self.argv = argv
        return type(
            "Completed",
            (),
            {"stdout": "RESULT=COMMAND_RC_0\n", "stderr": "", "returncode": 0},
        )()


class BatchRunner:
    """Return a successful owner.py batch without opening SSH or serial."""

    def __init__(self):
        self.calls = []
        self.spec = None

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        self.spec = json.loads(kwargs["input"])
        payload = {}
        for item in self.spec:
            command_id = item["id"]
            payload[command_id] = {
                "rc": 0,
                "out": f"__RT3_DONE_{command_id}__:0\n",
            }
        return type(
            "Completed",
            (),
            {
                "stdout": json.dumps(payload),
                "stderr": "",
                "returncode": 0,
            },
        )()


class ControllerTests(unittest.TestCase):
    def test_owner_batch_uses_one_ssh_and_fixed_commands(self):
        runner = BatchRunner()
        transport = rt3000ctl.SSHSerialTransport(runner=runner)

        result = transport.run_status(timeout=12)

        self.assertTrue(result.marker_ok)
        self.assertEqual(len(runner.calls), 1)
        argv, kwargs = runner.calls[0]
        self.assertEqual(
            argv[-1],
            "python3 /root/rt3000-smoke/owner.py run /dev/stdin /dev/stdout",
        )
        self.assertEqual(
            [item["id"] for item in runner.spec],
            list(rt3000ctl.OWNER_BATCHES["status"]),
        )
        self.assertEqual(
            [item["cmd"] for item in runner.spec],
            [rt3000ctl.FIXED_COMMANDS[name]
             for name in rt3000ctl.OWNER_BATCHES["status"]],
        )
        self.assertNotIn(" -- ", argv[-1])
        self.assertNotIn(";", argv[-1])
        self.assertEqual(kwargs["timeout"], 12 * 5 + 40)

    def test_post_oem_batch_uses_one_ssh_and_fixed_commands(self):
        runner = BatchRunner()
        transport = rt3000ctl.SSHSerialTransport(runner=runner)

        result = transport.run_post_oem(timeout=9)

        self.assertTrue(result.marker_ok)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(
            [item["id"] for item in runner.spec],
            list(rt3000ctl.OWNER_BATCHES["post-oem"]),
        )
        self.assertEqual(
            [item["cmd"] for item in runner.spec],
            [rt3000ctl.FIXED_COMMANDS[name]
             for name in rt3000ctl.OWNER_BATCHES["post-oem"]],
        )

    def test_owner_batch_rejects_unapproved_batch_name_without_ssh(self):
        runner = BatchRunner()
        transport = rt3000ctl.SSHSerialTransport(runner=runner)

        with self.assertRaises(rt3000ctl.ControlError):
            transport.run_owner_batch("status; rm -rf /", timeout=12)

        self.assertEqual(runner.calls, [])

    def test_owner_batch_missing_marker_fails_closed(self):
        payload = {
            name: {"rc": 0, "out": f"__RT3_DONE_{name}__:0\n"}
            for name in rt3000ctl.OWNER_BATCHES["status"]
        }
        payload["status-release"]["out"] = "KERNEL_RELEASE=5.4.164\n"

        result = rt3000ctl.owner_batch_result(payload, "status")

        self.assertFalse(result.marker_ok)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OWNER_MARKER_MISSING=status-release", result.output)

    def test_owner_batch_nonzero_item_fails_closed(self):
        payload = {
            name: {"rc": 0, "out": f"__RT3_DONE_{name}__:0\n"}
            for name in rt3000ctl.OWNER_BATCHES["post-oem"]
        }
        payload["post-labels"] = {
            "rc": 127,
            "out": "__RT3_DONE_post-labels__:127\n",
        }

        result = rt3000ctl.owner_batch_result(payload, "post-oem")

        self.assertFalse(result.marker_ok)
        self.assertEqual(result.returncode, 127)
        self.assertIn("OWNER_BATCH_RESULT=FAIL", result.output)

    def test_hexdump_raw_selector_zero_and_one_parse(self):
        status = rt3000ctl.parse_transcript(
            "SELECTOR_MTD2=00000000\nSELECTOR_MTD3=01000000\n"
        )

        self.assertEqual(status.selectors, {2: "0", 3: "1"})

    def test_raw_selector_commands_use_hexdump_not_od(self):
        for name, selector in (
            ("post-selector-raw-mtd2", "SELECTOR_MTD2"),
            ("post-selector-raw-mtd3", "SELECTOR_MTD3"),
        ):
            command = rt3000ctl.FIXED_COMMANDS[name]
            self.assertIn("hexdump", command)
            self.assertIn("4/1 \"%02x\"", command)
            self.assertNotIn("od", command)
            self.assertIn(selector, command)

    def test_transport_uses_supported_flock_syntax_and_fixed_profile(self):
        runner = CaptureRunner()
        transport = rt3000ctl.SSHSerialTransport(runner=runner)
        result = transport.run_fixed("status-slot", timeout=12)
        remote = runner.argv[-1]
        self.assertTrue(result.marker_ok)
        self.assertNotIn(" -- ", remote)
        self.assertIn("flock -n /var/lock/rt3000-serial.lock ", remote)
        self.assertIn("python3 /root/rt3_authorized_exec.py", remote)
        self.assertIn("/usr/sbin/rt3slot status 2>&1", remote)

    def test_happy_path_execute_uses_fixed_transition_and_post_gates(self):
        transport = FakeTransport()
        result = rt3000ctl.Controller(transport).enter_oem(execute=True, timeout=30)
        self.assertEqual(result.field("KERNEL_RELEASE"), "4.4.60")
        self.assertEqual(
            [call[1] for call in transport.calls if call[0] == "run"],
            ["status", "enter-oem", "post-oem"],
        )

    def test_command_rc_zero_without_event_waits_then_passes(self):
        transport = FakeTransport(action="RESULT=COMMAND_RC_0\n")
        result = rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertEqual(result.field("KERNEL_RELEASE"), "4.4.60")
        self.assertIn(("wait", 240), transport.calls)

    def test_explicit_nonzero_command_rc_fails_without_wait(self):
        transport = FakeTransport(action="RESULT=COMMAND_RC_1\n")
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertNotIn(("wait", 240), transport.calls)
        self.assertNotIn(("run", "post-oem", 240), transport.calls)

    def test_unknown_runtime_fails_closed(self):
        transport = FakeTransport(
            pre=PRE_OK.replace("runtime_system=QSDK", "runtime_system=UNKNOWN")
        )
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertNotIn(("run", "enter-oem", 240), transport.calls)

    def test_qsdk_slot_yes_is_accepted(self):
        transport = FakeTransport(
            pre=PRE_OK.replace("QSDK_SLOT_VALID=PASS", "QSDK_SLOT_VALID=YES")
        )
        result = rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertEqual(result.field("KERNEL_RELEASE"), "4.4.60")

    def test_qsdk_slot_no_is_rejected(self):
        transport = FakeTransport(
            pre=PRE_OK.replace("QSDK_SLOT_VALID=PASS", "QSDK_SLOT_VALID=NO")
        )
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertNotIn(("run", "enter-oem", 240), transport.calls)

    def test_selector_divergence_fails_closed(self):
        pre = PRE_OK.replace(
            "mtd2(0:BOOTCONFIG) rootfs selector = 0x00000001",
            "mtd2(0:BOOTCONFIG) rootfs selector = 0x00000000",
        )
        transport = FakeTransport(pre=pre)
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertNotIn(("run", "enter-oem", 240), transport.calls)

    def test_mtd15_mismatch_fails_closed(self):
        transport = FakeTransport(pre=PRE_OK.replace(MTD15, "0" * 64))
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)
        self.assertNotIn(("run", "enter-oem", 240), transport.calls)

    def test_wait_timeout_fails_closed(self):
        transport = FakeTransport(wait="RESULT=TIMEOUT_NO_RC\n")
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).wait_verify(execute=True, timeout=7)
        self.assertEqual(transport.calls, [("wait", 7)])

    def test_default_enter_oem_is_dry_run_and_execute_is_required(self):
        transport = FakeTransport()
        result = rt3000ctl.Controller(transport).enter_oem(execute=False)
        self.assertIsNone(result)
        self.assertEqual(transport.calls, [])

    def test_post_gate_rejects_wrong_oem_labels(self):
        post = POST_OK.replace('mtd16: 02800000 00020000 "rootfs_1"',
                               'mtd16: 02800000 00020000 "rootfs"')
        transport = FakeTransport(post=post)
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).enter_oem(execute=True)

    def test_verify_oem_passes_and_reports_post_fields(self):
        transport = FakeTransport()
        result = rt3000ctl.Controller(transport).verify_oem(timeout=30)
        self.assertEqual(result.field("KERNEL_RELEASE"), "4.4.60")
        self.assertEqual(transport.calls, [("run", "post-oem", 30)])

    def test_verify_oem_rejects_qsdk_post_transcript(self):
        post = (
            POST_OK.replace("KERNEL_RELEASE=4.4.60", "KERNEL_RELEASE=5.4.164")
            .replace(
                'mtd15: 02800000 00020000 "rootfs"',
                'mtd15: 02800000 00020000 "oem_rootfs"',
            )
            .replace(
                'mtd16: 02800000 00020000 "rootfs_1"',
                'mtd16: 02800000 00020000 "rootfs"',
            )
            .replace("0x00000000", "0x00000001")
        )
        transport = FakeTransport(post=post)
        with self.assertRaises(rt3000ctl.ControlError):
            rt3000ctl.Controller(transport).verify_oem()

    def test_verify_oem_rejects_execute_flag(self):
        self.assertEqual(rt3000ctl.main(["--execute", "verify-oem"]), 2)


if __name__ == "__main__":
    unittest.main()
