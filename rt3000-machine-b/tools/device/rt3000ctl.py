#!/usr/bin/env python3
"""Fail-closed Product R1 Machine-B serial control client.

The client runs on the WSL build host and reaches the existing OneCloud
jumpbox through the fixed ``rt3000-jumpbox`` SSH alias.  It deliberately has
no generic remote-command option: every command sent to the device is a
constant in this file and every serial session is wrapped in the jumpbox's
existing flock.

``status`` is read-only.  ``enter-oem`` and ``wait-verify`` are dry-run unless
``--execute`` is explicitly supplied.  This module does not implement OEM to
QSDK installation or any raw MTD operation.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence


EXPECTED_KERNEL_ID = (
    "95254958dadcbe9c5630fd258543874b1a92d66a5bb4791fcbbf60c8839134de"
)
EXPECTED_MTD15_SHA256 = (
    "4889f26cb9d2a1c45397ab5d493a2ff610ef65e296ee3c015c739cddcecaa5bd"
)
EXPECTED_RELEASE = "Product R1 RC1"


@dataclass(frozen=True)
class MachineProfile:
    name: str
    jump_host: str
    serial_device: str
    serial_lock: str
    authorized_exec: str
    owner_script: str


MACHINE_B = MachineProfile(
    name="machine-b",
    jump_host="rt3000-jumpbox",
    serial_device=(
        "/dev/serial/by-id/"
        "REPLACE_WITH_YOUR_SERIAL_ADAPTER"
    ),
    serial_lock="/var/lock/rt3000-serial.lock",
    authorized_exec="/root/rt3_authorized_exec.py",
    owner_script="/root/rt3000-smoke/owner.py",
)


# These are the only target commands this controller can select.  They are
# intentionally written as constants rather than accepting shell text from a
# caller.  All operations other than the explicit OEM transition are reads.
FIXED_COMMANDS = {
    # Keep each line short enough for the target's serial shell input buffer.
    # A prior long read-only probe was observed truncated on this device.
    "status-slot": "/usr/sbin/rt3slot status 2>&1",
    "status-release": "/usr/sbin/rt3release verify 2>&1",
    "status-selector": "/usr/sbin/rt3bcwrite --show 2>&1",
    "status-kernel": "printf 'KERNEL_RELEASE='; uname -r",
    "status-mtd15": (
        "printf 'MTD15_SHA256='; "
        "sha256sum /dev/mtd15 | cut -d' ' -f1"
    ),
    "enter-oem": "/usr/sbin/rt3slot oem --reboot",
    "post-kernel": "printf 'KERNEL_RELEASE='; uname -r",
    "post-labels": "grep -E '^mtd(15|16):' /proc/mtd",
    # Read-only fallback for OEM, where the packaged helper may be absent.
    # BusyBox hexdump is present in the audited OEM transcript; the bytes are
    # decoded as little-endian by parse_transcript().
    "post-selector-raw-mtd2": (
        "printf 'SELECTOR_MTD2='; "
        "dd if=/dev/mtd2 bs=1 skip=128 count=4 2>/dev/null | "
        "hexdump -v -e '4/1 \"%02x\"'; printf '\\n'"
    ),
    "post-selector-raw-mtd3": (
        "printf 'SELECTOR_MTD3='; "
        "dd if=/dev/mtd3 bs=1 skip=128 count=4 2>/dev/null | "
        "hexdump -v -e '4/1 \"%02x\"'; printf '\\n'"
    ),
    "post-mtd15": (
        "printf 'MTD15_SHA256='; "
        "sha256sum /dev/mtd15 | cut -d' ' -f1"
    ),
}

OWNER_BATCHES = {
    "status": (
        "status-slot",
        "status-release",
        "status-selector",
        "status-kernel",
        "status-mtd15",
    ),
    "post-oem": (
        "post-kernel",
        "post-labels",
        "post-selector-raw-mtd2",
        "post-selector-raw-mtd3",
        "post-mtd15",
    ),
}

BOOT_EVENT = "Linux 4.4.60"


class ControlError(RuntimeError):
    """A fail-closed control or verification failure."""


@dataclass(frozen=True)
class CommandResult:
    output: str
    returncode: int
    complete: bool = True

    @property
    def marker_ok(self) -> bool:
        """Whether the authorized helper completed the target command."""

        return self.complete and "RESULT=COMMAND_RC_0" in self.output


@dataclass(frozen=True)
class DeviceStatus:
    fields: Mapping[str, str]
    selectors: Mapping[int, str]
    mtd_labels: Mapping[int, str]
    raw: str = ""

    def field(self, name: str) -> Optional[str]:
        value = self.fields.get(name)
        return value.strip() if value is not None else None


def parse_transcript(text: str) -> DeviceStatus:
    """Extract only auditable fields from a serial transcript.

    Prompts and command echoes may prefix a line, so key/value and MTD
    patterns are searched rather than assumed to start at column zero.
    Unknown or missing fields remain absent and are rejected by the gates.
    """

    fields: dict[str, str] = {}
    key_value = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)=([^\r\n]*)")
    for match in key_value.finditer(text):
        fields[match.group(1)] = match.group(2).strip()

    selectors: dict[int, str] = {}
    selector_re = re.compile(
        r"mtd([23])\([^)]*\).*?rootfs selector\s*=\s*0x([0-9a-fA-F]+)"
    )
    for match in selector_re.finditer(text):
        value = match.group(2).lower().lstrip("0") or "0"
        selectors[int(match.group(1))] = value

    raw_selector_re = re.compile(
        r"SELECTOR_MTD([23])\s*=\s*([0-9a-fA-F]{8})"
    )
    for match in raw_selector_re.finditer(text):
        try:
            selectors[int(match.group(1))] = str(
                int.from_bytes(bytes.fromhex(match.group(2)), "little")
            )
        except ValueError:
            continue

    mtd_labels: dict[int, str] = {}
    mtd_re = re.compile(
        r"mtd(\d+):\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+\"([^\"]+)\""
    )
    for match in mtd_re.finditer(text):
        mtd_labels[int(match.group(1))] = match.group(2)

    # Keep support for a bare sha256sum line in addition to the explicit
    # MTD15_SHA256= prefix emitted by FIXED_COMMANDS["status"].
    if "MTD15_SHA256" not in fields:
        match = re.search(
            r"\b([0-9a-fA-F]{64})\s+/dev/mtd15(?:ro)?\b", text
        )
        if match:
            fields["MTD15_SHA256"] = match.group(1).lower()

    return DeviceStatus(fields=fields, selectors=selectors,
                         mtd_labels=mtd_labels, raw=text)


def _first(status: DeviceStatus, *names: str) -> Optional[str]:
    for name in names:
        value = status.field(name)
        if value is not None and value != "":
            return value
    return None


def preflight_failures(status: DeviceStatus) -> tuple[str, ...]:
    """Return every failed QSDK-to-OEM precondition; never infer unknowns."""

    failures: list[str] = []

    exact = (
        ("runtime_system", status.field("runtime_system"), "QSDK"),
        ("selector_mtd3", status.selectors.get(3), "1"),
        ("selector_mtd2", status.selectors.get(2), "1"),
        ("copies_agree", status.field("copies_agree"), "YES"),
        ("bootconfig_copy_health", status.field("bootconfig_copy_health"), "YES"),
        ("oem_slot_status", status.field("oem_slot_status"), "PASS"),
        ("qsdk_slot_status", status.field("qsdk_slot_status"), "PASS"),
        ("release", _first(status, "RUNNING_RELEASE", "RELEASE_NAME"), EXPECTED_RELEASE),
        ("kernel_id", _first(status, "RUNNING_KERNEL_ID", "RELEASE_KERNEL_ID"), EXPECTED_KERNEL_ID),
        ("mtd15_sha256", status.field("MTD15_SHA256"), EXPECTED_MTD15_SHA256),
    )
    for name, actual, expected in exact:
        if actual != expected:
            failures.append(f"{name}={actual or 'UNKNOWN'} (need {expected})")
    qsdk_valid = status.field("QSDK_SLOT_VALID")
    if qsdk_valid not in {"PASS", "YES"}:
        failures.append(
            f"QSDK_SLOT_VALID={qsdk_valid or 'UNKNOWN'} (need PASS or YES)"
        )
    return tuple(failures)


def post_oem_failures(status: DeviceStatus) -> tuple[str, ...]:
    """Return every failed post-reboot OEM verification gate."""

    failures: list[str] = []
    selector_mtd3 = status.selectors.get(3)
    selector_mtd2 = status.selectors.get(2)
    copies_agree = status.field("copies_agree")
    if copies_agree is None and selector_mtd3 is not None and selector_mtd2 is not None:
        copies_agree = "YES" if selector_mtd3 == selector_mtd2 else "NO"
    exact = (
        ("kernel_release", status.field("KERNEL_RELEASE"), "4.4.60"),
        ("selector_mtd3", selector_mtd3, "0"),
        ("selector_mtd2", selector_mtd2, "0"),
        ("copies_agree", copies_agree, "YES"),
        ("mtd15_label", status.mtd_labels.get(15), "rootfs"),
        ("mtd16_label", status.mtd_labels.get(16), "rootfs_1"),
        ("mtd15_sha256", status.field("MTD15_SHA256"), EXPECTED_MTD15_SHA256),
    )
    for name, actual, expected in exact:
        if actual != expected:
            failures.append(f"{name}={actual or 'UNKNOWN'} (need {expected})")
    return tuple(failures)


def has_boot_event(output: str) -> bool:
    return BOOT_EVENT in output or "KERNEL_RELEASE=4.4.60" in output


def has_nonzero_command_rc(output: str) -> bool:
    match = re.search(r"RESULT=COMMAND_RC_(-?\d+)", output)
    return bool(match and int(match.group(1)) != 0)


def owner_batch_result(payload: object, batch_name: str) -> CommandResult:
    """Validate every owner.py item marker and return one merged transcript."""

    names = OWNER_BATCHES.get(batch_name)
    if names is None:
        raise ControlError(f"unapproved owner batch: {batch_name}")
    if not isinstance(payload, dict):
        return CommandResult("OWNER_BATCH_JSON_INVALID\n", 1, complete=False)

    outputs: list[str] = []
    failed = False
    failure_rc = 1
    for name in names:
        entry = payload.get(name)
        if not isinstance(entry, dict):
            outputs.append(f"OWNER_ITEM_MISSING={name}\n")
            failed = True
            continue
        rc = entry.get("rc")
        out = entry.get("out")
        if not isinstance(rc, int) or isinstance(rc, bool) or not isinstance(out, str):
            outputs.append(f"OWNER_ITEM_INVALID={name}\n")
            failed = True
            continue
        outputs.append(out)
        marker = f"__RT3_DONE_{name}__:{rc}"
        if marker not in out:
            outputs.append(f"OWNER_MARKER_MISSING={name}\n")
            failed = True
        if rc != 0:
            failure_rc = rc
            failed = True

    if failed:
        outputs.append("OWNER_BATCH_RESULT=FAIL\n")
        return CommandResult("\n".join(outputs), failure_rc, complete=False)
    outputs.append("RESULT=COMMAND_RC_0\n")
    return CommandResult("\n".join(outputs), 0)


class SSHSerialTransport:
    """Run fixed serial operations through the existing jumpbox helpers."""

    def __init__(
        self,
        profile: MachineProfile = MACHINE_B,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.profile = profile
        self.runner = runner

    def _ssh_process(
        self,
        remote_command: str,
        timeout: int,
        input_text: Optional[str] = None,
    ) -> tuple[int, str, str]:
        ssh_command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            self.profile.jump_host,
            remote_command,
        ]
        kwargs = {
            "text": True,
            "capture_output": True,
            "check": False,
            "timeout": timeout + 20,
        }
        if input_text is not None:
            kwargs["input"] = input_text
        try:
            completed = self.runner(ssh_command, **kwargs)
        except subprocess.TimeoutExpired as exc:
            output = "".join(
                part.decode(errors="replace") if isinstance(part, bytes) else str(part)
                for part in (exc.stdout, exc.stderr)
                if part
            )
            return 124, output, "RESULT=TIMEOUT_HOST\n"
        return completed.returncode, completed.stdout or "", completed.stderr or ""

    def _ssh(
        self,
        remote_command: str,
        timeout: int,
        input_text: Optional[str] = None,
    ) -> CommandResult:
        rc, stdout, stderr = self._ssh_process(remote_command, timeout, input_text)
        return CommandResult(output=stdout + stderr, returncode=rc)

    def _locked_helper(self, helper_command: str, timeout: int) -> CommandResult:
        remote = (
            f"flock -n {shlex.quote(self.profile.serial_lock)} "
            f"{helper_command}"
        )
        return self._ssh(remote, timeout)

    def run_fixed(self, name: str, timeout: int) -> CommandResult:
        try:
            command = FIXED_COMMANDS[name]
        except KeyError as exc:  # pragma: no cover - internal misuse guard
            raise ControlError(f"unapproved command template: {name}") from exc
        helper = (
            f"python3 {shlex.quote(self.profile.authorized_exec)} "
            f"{shlex.quote(command)} {int(timeout)}"
        )
        return self._locked_helper(helper, timeout)

    def run_status(self, timeout: int) -> CommandResult:
        return self.run_owner_batch("status", timeout)

    def run_post_oem(self, timeout: int) -> CommandResult:
        return self.run_owner_batch("post-oem", timeout)

    def run_owner_batch(self, batch_name: str, timeout: int) -> CommandResult:
        names = OWNER_BATCHES.get(batch_name)
        if names is None:
            raise ControlError(f"unapproved owner batch: {batch_name}")
        spec = json.dumps(
            [
                {"id": name, "cmd": FIXED_COMMANDS[name], "timeout": int(timeout)}
                for name in names
            ],
            separators=(",", ":"),
        )
        remote = (
            f"python3 {shlex.quote(self.profile.owner_script)} "
            "run /dev/stdin /dev/stdout"
        )
        overall_timeout = int(timeout) * len(names) + 20
        rc, stdout, stderr = self._ssh_process(remote, overall_timeout, spec)
        if rc != 0:
            return CommandResult(stdout + stderr, rc, complete=False)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return CommandResult(stdout + stderr + "\nOWNER_BATCH_JSON_INVALID\n",
                                 1, complete=False)
        return owner_batch_result(payload, batch_name)

    def wait_for_boot_event(self, timeout: int) -> CommandResult:
        # owner.py's wait mode is marker-driven and does not transmit.  It
        # appends to its existing owner.log; no new remote file is created.
        helper = (
            f"python3 {shlex.quote(self.profile.owner_script)} wait "
            f"{shlex.quote(BOOT_EVENT)} {int(timeout)}"
        )
        return self._locked_helper(helper, timeout)


class Controller:
    def __init__(self, transport: SSHSerialTransport) -> None:
        self.transport = transport

    def _status(self, timeout: int) -> DeviceStatus:
        result = self.transport.run_status(timeout)
        if not result.marker_ok:
            raise ControlError(
                "status helper did not complete successfully; refusing to infer state"
            )
        return parse_transcript(result.output)

    @staticmethod
    def _require_no_failures(kind: str, failures: Sequence[str]) -> None:
        if failures:
            raise ControlError(f"{kind} gate failed: " + "; ".join(failures))

    def status(self, *, dry_run: bool = False, timeout: int = 120) -> DeviceStatus | None:
        if dry_run:
            print("DRY_RUN=PASS command=status (no serial access)")
            return None
        status = self._status(timeout)
        print("PROFILE=machine-b")
        print("STATUS_TRANSCRIPT=PASS")
        for name in (
            "runtime_system",
            "persistent_selector",
            "bootconfig_copy_health",
            "oem_slot_status",
            "qsdk_slot_status",
            "RUNNING_RELEASE",
            "RUNNING_KERNEL_ID",
            "RELEASE_NETWORK_BASELINE",
            "KERNEL_RELEASE",
            "MTD15_SHA256",
        ):
            value = status.field(name)
            if value is not None:
                print(f"{name}={value}")
        for mtd in (3, 2):
            if mtd in status.selectors:
                print(f"selector_mtd{mtd}={status.selectors[mtd]}")
        return status

    def enter_oem(self, *, execute: bool = False, timeout: int = 240) -> DeviceStatus | None:
        if not execute:
            print("DRY_RUN=PASS command=enter-oem (use --execute to permit the transition)")
            return None

        before = self._status(timeout)
        self._require_no_failures("QSDK→OEM preflight", preflight_failures(before))

        action = self.transport.run_fixed("enter-oem", timeout)
        if not has_boot_event(action.output):
            if has_nonzero_command_rc(action.output):
                raise ControlError(
                    "OEM transition returned an explicit nonzero command result"
                )
            wait = self.transport.wait_for_boot_event(timeout)
            if not has_boot_event(wait.output) and "WAIT_OK=True" not in wait.output:
                raise ControlError("OEM boot event wait timed out; refusing verification")

        after_result = self.transport.run_post_oem(timeout)
        if not after_result.marker_ok:
            raise ControlError(
                "post-OEM verification helper did not complete; refusing PASS"
            )
        after = parse_transcript(after_result.output)
        self._require_no_failures("OEM post-boot", post_oem_failures(after))
        print("ENTER_OEM=PASS")
        return after

    def verify_oem(self, *, dry_run: bool = False, timeout: int = 240) -> DeviceStatus | None:
        if dry_run:
            print("DRY_RUN=PASS command=verify-oem (no serial access)")
            return None
        result = self.transport.run_post_oem(timeout)
        if not result.marker_ok:
            raise ControlError(
                "post-OEM verification helper did not complete; refusing PASS"
            )
        status = parse_transcript(result.output)
        self._require_no_failures("OEM post-boot", post_oem_failures(status))
        print("VERIFY_OEM=PASS")
        for name in ("KERNEL_RELEASE", "MTD15_SHA256"):
            value = status.field(name)
            if value is not None:
                print(f"{name}={value}")
        for mtd in (15, 16):
            if mtd in status.mtd_labels:
                print(f"mtd{mtd}_label={status.mtd_labels[mtd]}")
        for mtd in (3, 2):
            if mtd in status.selectors:
                print(f"selector_mtd{mtd}={status.selectors[mtd]}")
        return status

    def wait_verify(self, *, execute: bool = False, timeout: int = 240) -> DeviceStatus | None:
        if not execute:
            print("DRY_RUN=PASS command=wait-verify (use --execute to read the boot event)")
            return None
        wait = self.transport.wait_for_boot_event(timeout)
        if not has_boot_event(wait.output) and "WAIT_OK=True" not in wait.output:
            raise ControlError("wait-verify timed out or serial owner was unavailable")
        after_result = self.transport.run_post_oem(timeout)
        if not after_result.marker_ok:
            raise ControlError(
                "post-OEM verification helper did not complete; refusing PASS"
            )
        after = parse_transcript(after_result.output)
        self._require_no_failures("OEM post-boot", post_oem_failures(after))
        print("WAIT_VERIFY=PASS")
        return after


def _positive_timeout(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be an integer") from exc
    if not 1 <= parsed <= 900:
        raise argparse.ArgumentTypeError("timeout must be between 1 and 900 seconds")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(MACHINE_B.name,), default=MACHINE_B.name)
    parser.add_argument("--dry-run", action="store_true", help="do not access the serial link")
    parser.add_argument(
        "--execute", action="store_true", help="permit the selected transition/wait"
    )
    parser.add_argument("--timeout", type=_positive_timeout, default=240)
    parser.add_argument(
        "command", choices=("status", "enter-oem", "verify-oem", "wait-verify")
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run and args.execute:
        print("ERROR: --dry-run and --execute are mutually exclusive", file=sys.stderr)
        return 2
    if args.command == "status" and args.execute:
        print("ERROR: status is read-only; omit --execute", file=sys.stderr)
        return 2
    if args.command == "verify-oem" and args.execute:
        print("ERROR: verify-oem is read-only; omit --execute", file=sys.stderr)
        return 2
    controller = Controller(SSHSerialTransport(MACHINE_B))
    try:
        if args.command == "status":
            controller.status(dry_run=args.dry_run, timeout=args.timeout)
        elif args.command == "enter-oem":
            controller.enter_oem(execute=args.execute, timeout=args.timeout)
        elif args.command == "verify-oem":
            controller.verify_oem(dry_run=args.dry_run, timeout=args.timeout)
        else:
            controller.wait_verify(execute=args.execute, timeout=args.timeout)
    except (ControlError, OSError, subprocess.SubprocessError) as exc:
        print(f"RESULT=FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
