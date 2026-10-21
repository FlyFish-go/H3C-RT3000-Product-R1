#!/usr/bin/env python3
"""Prepare/build a private C-only RAM baseline in an existing external cache.

No feeds updates, device operations or flash operations. Full source, download
and toolchain hashes are recorded; a fresh-host bootstrap is not implemented.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from build_qcn6122_probe_bdf import build_schema_probe, SCHEMA_PROBE_SHA256
sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_rx_gates as NG
import sta_rxrate_profile as SR

ROOT = Path(__file__).resolve().parents[2]
QCN6122_PPDU_TS_PATCH_SHA256 = "d174ede993d65e19f844e042ed847de22a6b812e1fcb43899c5256002e7e695d"
QCN6122_PPDU_TS_HAL_RX_SHA256 = "0120bec7a5c9a411c8021933bb3ff3bea09f4cebfd3bcf0c594046f42f33e9b3"
QCN6122_PPDU_TS_CACHE_REL = "package/kernel/mac80211/patches/all-ipq50xx/626-ath11k-c-qcn6122-ppdu-ts-correlation.patch"
QCN6122_PPDU_TS_EVIDENCE_ROOT = Path("<HOME>")
QCN6122_SIG627_CACHE_REL = "package/kernel/mac80211/patches/all-ipq50xx/" + NG.NATIVE_RX_627_PATCH
QCN6122_SIG628_CACHE_REL = "package/kernel/mac80211/patches/all-ipq50xx/" + NG.NATIVE_RX_628_PATCH
QCN6122_BW629_CACHE_REL = "package/kernel/mac80211/patches/all-ipq50xx/" + NG.NATIVE_RX_629_PATCH
QCN6122_SIG_PREIMAGE = Path("<EVIDENCE>")


def validate_qcn6122_siga_step_patch(path, *, expected_sha, cache_relative_path, siga_trace, ppdu_ts_selected):
    patch_dir=ROOT/Path(cache_relative_path).parent
    prefix=Path(cache_relative_path).name[:3]
    canonical=[item for item in patch_dir.glob(prefix+"*.patch") if item.is_file() or item.is_symlink()]
    if canonical: raise ValueError("627/628 source patch must remain external: "+str(canonical[0]))
    if path is None: return None
    path=Path(path)
    if not siga_trace or not ppdu_ts_selected: raise ValueError("627/628 require complete SIG-A and 626 profile")
    if not path.is_absolute() or QCN6122_PPDU_TS_EVIDENCE_ROOT not in path.resolve().parents: raise ValueError("627/628 inputs must be external evidence files")
    if path.is_symlink() or not path.is_file() or sha(path)!=expected_sha: raise ValueError("external patch file/hash mismatch: "+cache_relative_path)
    if (ROOT/cache_relative_path).exists(): raise ValueError(cache_relative_path+" must remain external")
    return {"source_path":str(path.resolve()),"patch_sha256":expected_sha,"cache_relative_path":cache_relative_path}


def validate_qcn6122_siga_cached_patches(tree, *, select_627, select_628, select_629=False, select_629_source06=False, select_629_source07=False):
    if sum(bool(x) for x in (select_629,select_629_source06,select_629_source07))>1:
        raise ValueError("select exactly one 629 source revision")
    tree=Path(tree)
    result={}
    if select_629_source07:
        expected_629_sha=NG.NATIVE_RX_629_SOURCE07_PATCH_SHA
    elif select_629_source06:
        expected_629_sha=NG.NATIVE_RX_629_SOURCE06_PATCH_SHA
    else:
        expected_629_sha=NG.NATIVE_RX_629_PATCH_SHA
    for prefix,selected,relative,expected_sha in (
            ("627",select_627,QCN6122_SIG627_CACHE_REL,NG.NATIVE_RX_627_PATCH_SHA),
            ("628",select_628,QCN6122_SIG628_CACHE_REL,NG.NATIVE_RX_628_PATCH_SHA),
            ("629",select_629 or select_629_source06 or select_629_source07,QCN6122_BW629_CACHE_REL,expected_629_sha)):
        expected=tree/relative
        matches=[item for item in expected.parent.glob(prefix+"*.patch") if item.exists() or item.is_symlink()]
        if any(item != expected for item in matches):
            raise ValueError(f"unexpected cached {prefix} duplicate patch: {matches}")
        if matches and not selected:
            raise ValueError(f"cached {prefix} patch is unselected")
        if any(item.is_symlink() for item in matches):
            raise ValueError(f"cached {prefix} patch must not be a symlink")
        cached_sha=sha(expected) if matches else None
        superseded=False
        superseded_revision=None
        if matches and cached_sha!=expected_sha:
            revisions={
                NG.NATIVE_RX_629_SUPERSEDED_PATCH_SHA:"03",
                NG.NATIVE_RX_629_REV04_PATCH_SHA:"04",
                NG.NATIVE_RX_629_PATCH_SHA:"05",
                NG.NATIVE_RX_629_SOURCE06_PATCH_SHA:"06",
            }
            allowed=set(revisions)
            if not select_629_source07: allowed.discard(NG.NATIVE_RX_629_SOURCE06_PATCH_SHA)
            if prefix=="629" and selected and cached_sha in allowed:
                superseded=True
                superseded_revision=revisions[cached_sha]
            else:
                raise ValueError(f"cached {prefix} hash mismatch")
        result[prefix]={"selected":bool(selected),"cached":bool(matches),
                        "sha256":expected_sha if matches else None,
                        "cached_sha256":cached_sha,
                        "superseded_revision_03_replacement":superseded_revision=="03",
                        "superseded_revision_04_replacement":superseded_revision=="04",
                        "superseded_revision_05_replacement":superseded_revision=="05",
                        "superseded_revision_06_replacement":superseded_revision=="06",
                        "superseded_revision":superseded_revision}
    return result


def validate_qcn6122_siga_627_proof(path, *, selected):
    if bool(path) != bool(selected):
        raise ValueError("627 requires its pinned actual-C validation manifest, and vice versa")
    if path is None:
        return None
    proof_path=Path(path)
    if (not proof_path.is_absolute() or QCN6122_PPDU_TS_EVIDENCE_ROOT not in proof_path.resolve().parents or
        proof_path.is_symlink() or not proof_path.is_file() or
        sha(proof_path)!=NG.NATIVE_RX_627_ACTUAL_C_PROOF_SHA):
        raise ValueError("627 actual-C proof file/hash mismatch")
    proof=json.loads(proof_path.read_text())
    if (proof.get("post625",{}).get("source_sha256")!="95c6cb49f791662c107eeae1e0a52b9973eda27183cce56b33a6407c1c13b237" or
        proof.get("post626",{}).get("source_sha256")!=QCN6122_PPDU_TS_HAL_RX_SHA256 or
        not proof.get("post625",{}).get("compiled_actual_case") or
        not proof.get("post626",{}).get("compiled_actual_case") or
        not str(proof.get("post626",{}).get("result","")).startswith("PASS")):
        raise ValueError("627 actual-C proof does not bind the pinned 625/626 source cases")
    return {"source_path":str(proof_path.resolve()),"sha256":NG.NATIVE_RX_627_ACTUAL_C_PROOF_SHA}


def validate_qcn6122_bw_trace_629_patch(path, *, siga_trace, ppdu_ts_selected, patch_627, patch_628, proof_627, source06=False, source07=False):
    if source06 and source07: raise ValueError("select exactly one source06/source07 revision")
    if path is None: return None
    if (not siga_trace or not ppdu_ts_selected or patch_627 is None or patch_628 is None or
        proof_627 is None):
        raise ValueError("629 requires the complete 626/627/628 source and actual-C proof profile")
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("629 external proposal patch is missing or symlinked")
    if source07:
        sequence=NG.validate_native_rx_629_source07_patch_sequence(path)
        digest=NG.NATIVE_RX_629_SOURCE07_PATCH_SHA
    elif source06:
        sequence=NG.validate_native_rx_629_source06_patch_sequence(path)
        digest=NG.NATIVE_RX_629_SOURCE06_PATCH_SHA
    else:
        sequence=NG.validate_native_rx_629_patch_sequence(path)
        digest=NG.NATIVE_RX_629_PATCH_SHA
    return {"source_path":str(path.resolve()),"patch_sha256":digest,
            "source06_selected":source06,"source07_selected":source07,
            "cache_relative_path":QCN6122_BW629_CACHE_REL,"sequence":sequence,
            "failed_start_lifecycle":"terminal DEAD after failed startup; controls remain unavailable until reprobe",
            "runtime_validation":"NOT_EXECUTED"}

def validate_qcn6122_siga_patch_sequence(patch_627, patch_628):
    if patch_627 is None:
        if patch_628 is not None: raise ValueError("628 patch requires 627")
        return None
    if not QCN6122_SIG_PREIMAGE.is_file() or sha(QCN6122_SIG_PREIMAGE)!=QCN6122_PPDU_TS_HAL_RX_SHA256:
        raise ValueError("frozen 626 preimage is missing or has the wrong source hash")
    with tempfile.TemporaryDirectory(prefix="qcn6122-siga-627-628-") as temp_name:
        temp=Path(temp_name)
        target=temp/"drivers/net/wireless/ath/ath11k/hal_rx.c"
        target.parent.mkdir(parents=True)
        shutil.copyfile(QCN6122_SIG_PREIMAGE,target)
        chain=[(patch_627,NG.NATIVE_RX_627_HAL_SHA,"627")]
        if patch_628 is not None: chain.append((patch_628,NG.NATIVE_RX_628_HAL_SHA,"628"))
        stages=[{"stage":"626","source_sha256":QCN6122_PPDU_TS_HAL_RX_SHA256}]
        for item,expected,label in chain:
            source=Path(item["source_path"])
            if sha(source)!=item["patch_sha256"]: raise ValueError(f"external {label} patch changed before sequence validation")
            result=subprocess.run(["patch","--batch","--fuzz=0","-p1","-i",str(source)],
                                  cwd=temp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            if result.returncode: raise ValueError(f"external {label} patch failed fuzz=0 preflight: {result.stderr[-1200:]}")
            actual=sha(target)
            if actual!=expected: raise ValueError(f"external {label} postimage hash mismatch: {actual}")
            stages.append({"stage":label,"patch_sha256":item["patch_sha256"],"source_sha256":actual,"fuzz":0})
    return {"preimage_path":str(QCN6122_SIG_PREIMAGE),"preimage_sha256":QCN6122_PPDU_TS_HAL_RX_SHA256,
            "stages":stages,"status":"PASS"}


def validate_qcn6122_ppdu_ts_patch(path, *, rx_width_join, phy_width_trace):
    if (ROOT / QCN6122_PPDU_TS_CACHE_REL).exists() and path is None:
        raise ValueError("canonical 626 present without explicit external opt-in")
    if path is None: return None
    path = Path(path)
    if not rx_width_join or not phy_width_trace:
        raise ValueError("626 requires complete 622+625 flags")
    if not path.is_absolute() or QCN6122_PPDU_TS_EVIDENCE_ROOT not in path.resolve().parents:
        raise ValueError("626 must be an external <HOME> input")
    if path.is_symlink() or not path.is_file() or sha(path) != QCN6122_PPDU_TS_PATCH_SHA256:
        raise ValueError("626 patch file/hash mismatch")
    if (ROOT / QCN6122_PPDU_TS_CACHE_REL).exists():
        raise ValueError("626 must not be added to canonical patches")
    return {"source_path": str(path.resolve()), "patch_sha256": QCN6122_PPDU_TS_PATCH_SHA256,
            "cache_relative_path": QCN6122_PPDU_TS_CACHE_REL,
            "post_hal_rx_sha256": QCN6122_PPDU_TS_HAL_RX_SHA256}
SEED = ROOT / "configs/rt3000-c-2g-ram/full.config"
OEM_PAS_PATCH = ROOT / "rt3000-machine-c/experiments/c-root-pas6/root-pas6.patch"
OEM_PAS_PATCH_SHA256 = "451995e44ac2a32848024c4c6ba4e7190ba4e0b6889bad101febcc8a0c96a680"
OEM_PAS_BASE_SHA256 = "f420ad8c183f9a75c252ef115eaa7fbef49a6937c768b4a385eaf15c9f48792b"
OEM_PAS_POST_SHA256 = "42709343875cf8557b4a09ced7b33a61963417ce697511f249ef1522672ed9ed"
OEM_PAS_DTS = ROOT / "rt3000-machine-c/experiments/c-root-pas6/root-pas6-test.dtsi"
OEM_PAS_DTS_SHA256 = "9558e757939d718e2900db6da2c028cc2d30a783d42a175af98d2b610fe2950b"
C618_FW_AUDIT = Path("<EVIDENCE>")
C618_FW_AUDIT_SHA256 = "8c5c4d16a72a054364db89b4efcb020d15fcaff9db2452f6fe8e996273d0817e"
C618_FIT_SHA256 = "3a473d781f6fdeb6ac3a2816dc6a079eb2d0db140d7e01f96db0d468728e418f"
C618_FW_PREFIXES = ("lib/firmware/IPQ5018/", "lib/firmware/qcn6122/",
                    "lib/firmware/ath11k/IPQ5018/hw1.0/",
                    "lib/firmware/ath11k/qcn6122/hw1.0/")
C618_FW_BDF_SHA256 = "432eb4044466712469193973ce337fee68f5c76e0dcee54dd6da1e6c9fd48bb1"
OEM_FW_WHITELIST = ROOT / "rt3000-machine-c/experiments/c-root-pas6/same-c-oem-firmware-whitelist.json"
OEM_FW_WHITELIST_SHA256 = "978431e657eb31276521613dfbb17f29bfcc46120f9f66f7b95662a58a7b3c96"
OEM_FW_AUDIT = Path("<EVIDENCE>")
OEM_FW_AUDIT_SHA256 = "fc071e1840ad8219dc765afe5894073188c1ad9b7aa405bce9061d0ff197e593"
OEM_FW_VOLUME_SHA256 = "717825ac26ad3f83472dc5c053fae8b9fbee2021388da98ee335e242f6800831"
OEM_FW_VOLUME_SIZE = 3586048
OEM_FW_BDF_SHA256 = "935327c086275cfc559db3bd5bec6537f415e81459b32cf8108cedbf8e2af32b"
OEM_CALDATA_SHA256 = {"caldata-ipq5018.bin": "88be7e89568ccc7a3602833085077edf62a095d83e850f960bb8bd9eb9d2b622",
                      "caldata-qcn6122.bin": "345918493f88f74d0c2ce22dcb606e5aace12a758efb3df9b9b227be6519d97a"}
ROOT_PAS6_PROPERTY = "h3c,rt3000-root-pas6-experiment"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def load_618_firmware_baseline(evidence=None):
    if not C618_FW_AUDIT.is_file() or sha(C618_FW_AUDIT) != C618_FW_AUDIT_SHA256:
        raise ValueError("frozen 618 firmware baseline audit provenance mismatch")
    audit = json.loads(C618_FW_AUDIT.read_text())
    if audit.get("fit_sha256") != C618_FIT_SHA256 or audit.get("hardware_validation") != "NOT_EXECUTED":
        raise ValueError("frozen 618 firmware baseline identity/status mismatch")
    files = {name: record for name, record in audit.get("files", {}).items()
             if name.startswith(C618_FW_PREFIXES)}
    if len(files) != 41:
        raise ValueError(f"unexpected frozen 618 firmware file count: {len(files)}")
    bdf = files.get("lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin", {})
    if bdf.get("sha256") != C618_FW_BDF_SHA256:
        raise ValueError("frozen 618 C BDF 432 baseline mismatch")
    if any(record.get("mode") != "0o100644" for record in files.values()):
        raise ValueError("frozen 618 firmware baseline contains non-regular/non-0644 files")
    if evidence is not None:
        shutil.copyfile(C618_FW_AUDIT, evidence / "618-firmware-baseline-audit.json")
    return {"audit_path": str(C618_FW_AUDIT), "audit_sha256": C618_FW_AUDIT_SHA256,
            "fit_sha256": C618_FIT_SHA256, "file_count": len(files),
            "bdf_qcn6122_sha256": C618_FW_BDF_SHA256, "files": files,
            "scope": "exact active C 618 firmware/caldata tree; ordinary RAM mode only"}


def collect_firmware_snapshot(root):
    result = {}
    for prefix in C618_FW_PREFIXES:
        base = root / prefix
        if not base.exists() and not base.is_symlink():
            continue
        if base.is_symlink() or not base.is_dir():
            raise ValueError(f"firmware tree prefix is not a real directory: {prefix}")
        for path in base.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[rel] = {"type": "symlink", "target": os.readlink(path)}
            elif path.is_file():
                result[rel] = {"type": "file", "size": path.stat().st_size,
                               "sha256": sha(path), "mode": oct(path.stat().st_mode & 0o177777)}
    return result


def verify_firmware_snapshot(root, expected):
    actual = collect_firmware_snapshot(root)
    expected_files = {name: {"type": "file", "size": item["size"],
                             "sha256": item["sha256"], "mode": item["mode"]}
                      for name, item in expected.items()}
    if actual != expected_files:
        missing = sorted(set(expected_files) - set(actual))
        extra = sorted(set(actual) - set(expected_files))
        mismatched = sorted(name for name in set(actual) & set(expected_files)
                            if actual[name] != expected_files[name])
        raise ValueError(f"ordinary C firmware tree differs from frozen 618 baseline: missing={missing[:8]} extra={extra[:8]} mismatched={mismatched[:8]}")
    return {"status": "EXACT_FROZEN_618_BASELINE", "file_count": len(actual),
            "files": actual}


def output(*cmd, cwd=ROOT):
    return subprocess.check_output(cmd, cwd=cwd).decode().strip()


def record_tree(path):
    result = {}
    for p in sorted(path.rglob("*")):
        if p.is_symlink():
            result[str(p.relative_to(path))] = {"link": os.readlink(p)}
        elif p.is_file():
            result[str(p.relative_to(path))] = {"sha256": sha(p), "size": p.stat().st_size}
    return result


def load_oem_firmware_inputs(evidence):
    if sha(OEM_FW_WHITELIST) != OEM_FW_WHITELIST_SHA256:
        raise ValueError("same-C OEM firmware whitelist provenance mismatch")
    if not OEM_FW_AUDIT.is_file() or sha(OEM_FW_AUDIT) != OEM_FW_AUDIT_SHA256:
        raise ValueError("same-C Q6 firmware source audit provenance mismatch")
    whitelist = json.loads(OEM_FW_WHITELIST.read_text())
    audit = json.loads(OEM_FW_AUDIT.read_text())
    payload = audit.get("payload", {})
    if (whitelist.get("schema") != "rt3000-c-same-unit-oem-wifi-overlay-whitelist-v1" or
            whitelist.get("status") != "HASH_VERIFIED_OFFLINE_NOT_INSTALLED" or
            payload.get("sha256") != OEM_FW_VOLUME_SHA256 or
            payload.get("size") != OEM_FW_VOLUME_SIZE):
        raise ValueError("same-C OEM firmware source-volume identity mismatch")
    files = whitelist.get("firmware_files", [])
    counts = {group: sum(item.get("group") == group for item in files)
              for group in ("IPQ5018_q6_fw", "IPQ5018_m3_fw", "qcn6122_m3_fw")}
    if len(files) != 35 or counts != {"IPQ5018_q6_fw": 25, "IPQ5018_m3_fw": 5, "qcn6122_m3_fw": 5}:
        raise ValueError(f"unexpected same-C OEM firmware whitelist groups: {counts}")
    source_volume = whitelist["source_volume"]
    source_volume_path = Path(source_volume["path"])
    if (source_volume.get("sha256") != OEM_FW_VOLUME_SHA256 or
            source_volume.get("bytes") != OEM_FW_VOLUME_SIZE or
            not source_volume_path.is_file() or source_volume_path.stat().st_size != OEM_FW_VOLUME_SIZE or
            sha(source_volume_path) != OEM_FW_VOLUME_SHA256):
        raise ValueError("same-C OEM firmware source volume bytes/hash mismatch")
    extraction = Path(payload["extraction_path"])
    overlay_root = evidence / "same-c-oem-fw-overlay"
    overlay_root.mkdir(mode=0o700)
    staged = []
    seen = set()
    for item in files:
        rel_src = Path(item["source_relative_to_oem_squashfs"])
        rel_dst = Path(item["overlay_relative_to_firmware_root"])
        if rel_src.is_absolute() or rel_dst.is_absolute() or ".." in rel_src.parts or ".." in rel_dst.parts:
            raise ValueError("unsafe same-C OEM firmware whitelist path")
        src = extraction / rel_src
        dst = overlay_root / rel_dst
        if src.is_symlink() or not src.is_file() or src.stat().st_size != item["bytes"] or sha(src) != item["sha256"]:
            raise ValueError(f"same-C OEM firmware source mismatch: {rel_src}")
        if str(rel_dst) in seen:
            raise ValueError(f"duplicate same-C OEM firmware destination: {rel_dst}")
        seen.add(str(rel_dst))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        staged.append({"source_relative_to_oem_squashfs": str(rel_src),
                       "overlay_relative_to_firmware_root": str(rel_dst),
                       "group": item["group"], "bytes": item["bytes"],
                       "sha256": item["sha256"]})
    bdf = whitelist["board_data"]
    bdf_path = ROOT / bdf["source"]
    if bdf["sha256"] != OEM_FW_BDF_SHA256 or sha(bdf_path) != OEM_FW_BDF_SHA256 or bdf_path.stat().st_size != bdf["bytes"]:
        raise ValueError("same-C OEM QCN6122 BDF 935 input mismatch")
    caldata = {}
    for name, expected in OEM_CALDATA_SHA256.items():
        path = ROOT / "package/firmware/rt3000-c-oem-wifi/files" / name
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"same-C factory calibration input identity mismatch: {name}")
        caldata[name] = {"bytes": path.stat().st_size, "sha256": expected}
    identity_path = Path(source_volume["identity_manifest_path"])
    if (source_volume.get("identity_manifest_sha256") != "b4a09041e4c77c5105e4d319ac2ba940dc585232f84cefbfdf59a1f8dd8a241b" or
            not identity_path.is_file() or sha(identity_path) != source_volume["identity_manifest_sha256"]):
        raise ValueError("same-C OEM firmware identity manifest provenance mismatch")
    manifest = {"whitelist_path": str(OEM_FW_WHITELIST),
                "whitelist_sha256": OEM_FW_WHITELIST_SHA256,
                "q6_audit_path": str(OEM_FW_AUDIT),
                "q6_audit_sha256": OEM_FW_AUDIT_SHA256,
                "source_volume_sha256": OEM_FW_VOLUME_SHA256,
                "source_volume_bytes": OEM_FW_VOLUME_SIZE,
                "source_volume_path": str(source_volume_path),
                "source_identity_manifest_path": str(identity_path),
                "source_identity_manifest_sha256": source_volume["identity_manifest_sha256"],
                "source_extraction_path": str(extraction),
                "board_data": bdf, "factory_caldata_inputs": caldata,
                "files": staged, "runtime_validation": "NOT_EXECUTED"}
    (evidence / "same-c-oem-fw-inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return whitelist, overlay_root, manifest


def append_oem_firmware_install_rules(makefile, files):
    text = makefile.read_text()
    anchor = "\t$(INSTALL_DATA) ./files/caldata-qcn6122.bin $(1)/lib/firmware/ath11k/qcn6122/hw1.0/caldata_1.bin\nendef"
    if text.count(anchor) != 1:
        raise ValueError("unexpected C OEM firmware package install recipe")
    lines = ["\t$(INSTALL_DIR) $(1)/lib/firmware/IPQ5018",
             "\t$(INSTALL_DIR) $(1)/lib/firmware/qcn6122"]
    for item in files:
        rel = item["overlay_relative_to_firmware_root"]
        source = "$(RT3000_C_SAME_C_OEM_FW_ROOT)/" + rel
        lines.append(f"\t$(INSTALL_DATA) {source} $(1)/lib/firmware/{rel}")
    replacement = anchor[:-len("endef")] + "\n".join(lines) + "\nendef"
    makefile.write_text(text.replace(anchor, replacement, 1))


def prepare_pas_cache_source(tree, mode):
    source = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5/drivers/remoteproc/qcom_q6v5_mpd.c"
    if not source.is_file():
        if mode is not None:
            raise ValueError("same-C root PAS mode requires the frozen Q6 source in cache")
        return {"source_present": False, "reset": "NOT_NEEDED"}
    digest = sha(source)
    if digest == OEM_PAS_BASE_SHA256:
        return {"source_present": True, "base_sha256": digest, "reset": "NOT_NEEDED"}
    if digest == OEM_PAS_POST_SHA256:
        if mode == 6:
            return {"source_present": True, "base_sha256": OEM_PAS_BASE_SHA256,
                    "patched_sha256": digest, "reset": "REUSE_EXACT_EXPERIMENT_PATCH"}
        subprocess.run(["patch", "--silent", "--reverse", "--forward", "-p1", "--dry-run", "-i", str(OEM_PAS_PATCH)], cwd=source.parents[2], check=True)
        subprocess.run(["patch", "--silent", "--reverse", "--forward", "-p1", "-i", str(OEM_PAS_PATCH)], cwd=source.parents[2], check=True)
        if sha(source) != OEM_PAS_BASE_SHA256:
            raise ValueError("could not restore exact unmodified C Q6 source after PAS experiment")
        return {"source_present": True, "base_sha256": OEM_PAS_BASE_SHA256,
                "previous_patched_sha256": digest, "reset": "EXACT_PAS_PATCH_REVERSED"}
    probe = source.read_bytes()
    if b"RT3000_C_ROOT_PAS6_PROPERTY" in probe or b"RT3000_C_ROOT_PAS_ID" in probe:
        raise ValueError("unrecognized PAS-modified Q6 source in cache; refusing to continue")
    if mode is not None:
        raise ValueError("same-C root PAS experiment base source hash mismatch")
    return {"source_present": True, "observed_sha256": digest,
            "reset": "NO_KNOWN_PAS_PATCH_PRESENT"}


def apply_root_pas_experiment(tree, mode, evidence):
    if mode not in (13, 6):
        raise ValueError("unsupported same-C OEM PAS mode")
    if sha(OEM_PAS_PATCH) != OEM_PAS_PATCH_SHA256 or sha(OEM_PAS_DTS) != OEM_PAS_DTS_SHA256:
        raise ValueError("root PAS experiment proposal provenance mismatch")
    source = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5/drivers/remoteproc/qcom_q6v5_mpd.c"
    if not source.is_file():
        raise ValueError("same-C root PAS Q6 source disappeared before mode selection")
    if mode == 13:
        if sha(source) != OEM_PAS_BASE_SHA256:
            raise ValueError("PAS13 control requires exact stock C Q6 source f420; never apply PAS6 patch")
        patch_applied = False
    else:
        if sha(source) == OEM_PAS_BASE_SHA256:
            subprocess.run(["patch", "--silent", "--forward", "-p1", "--dry-run", "-i", str(OEM_PAS_PATCH)], cwd=source.parents[2], check=True)
            subprocess.run(["patch", "--silent", "--forward", "-p1", "-i", str(OEM_PAS_PATCH)], cwd=source.parents[2], check=True)
        elif sha(source) != OEM_PAS_POST_SHA256:
            raise ValueError("same-C PAS6 patch base source hash mismatch")
        if sha(source) != OEM_PAS_POST_SHA256:
            raise ValueError("same-C PAS6 patched source hash mismatch")
        patch_applied = True
    dts = tree / "target/linux/ipq50xx/dts/ipq5000-rt3000-rtl8367s.dts"
    text = dts.read_text()
    root_start = text.find("&q6v5_wcss {")
    if root_start < 0 or text.count("&q6v5_wcss {") != 1:
        raise ValueError("C root Q6 DTS node not uniquely found")
    root_end = text.find("\n};", root_start)
    if root_end < 0:
        raise ValueError("unterminated C root Q6 DTS node")
    root_node = text[root_start:root_end]
    if ('compatible = "qcom,ipq5018-q6-mpd";' not in root_node or
            'firmware = "IPQ5018/q6_fw.mdt";' not in root_node):
        raise ValueError("root PAS property target is not the active C Q6 root node")
    if ROOT_PAS6_PROPERTY in text:
        raise ValueError("root PAS6 property already exists before experiment overlay")
    if mode == 6:
        overlay = OEM_PAS_DTS.read_text()
        if overlay.count(ROOT_PAS6_PROPERTY) != 1 or overlay.count("&q6v5_wcss {") != 1:
            raise ValueError("root PAS6 DTS overlay content mismatch")
        prop = "\th3c,rt3000-root-pas6-experiment;"
        if prop not in overlay:
            raise ValueError("root PAS6 overlay property missing")
        text = text[:root_end] + "\n" + prop + text[root_end:]
        dts.write_text(text)
    elif ROOT_PAS6_PROPERTY in dts.read_text():
        raise ValueError("PAS13 stock control DTS must not contain PAS6 test property")
    if (mode == 6) != (ROOT_PAS6_PROPERTY in dts.read_text()):
        raise ValueError("root PAS6 property mode did not match requested experiment")
    shutil.copyfile(OEM_PAS_PATCH, evidence / "root-pas6-proposal.patch")
    shutil.copyfile(OEM_PAS_DTS, evidence / "root-pas6-test.dtsi")
    return {"mode": mode, "source_mode": "STOCK_PAS13_CONTROL" if mode == 13 else "ROOT_PAS6_EXPERIMENT",
            "patch_applied": patch_applied, "patch_sha256": OEM_PAS_PATCH_SHA256,
            "base_qcom_q6v5_mpd_sha256": OEM_PAS_BASE_SHA256,
            "selected_qcom_q6v5_mpd_sha256": sha(source),
            "patched_qcom_q6v5_mpd_sha256": OEM_PAS_POST_SHA256 if mode == 6 else None,
            "dts_overlay_sha256": OEM_PAS_DTS_SHA256,
            "test_property": ROOT_PAS6_PROPERTY if mode == 6 else None,
            "scope": "RAM-only C root Q6; child PD remains PAS13",
            "runtime_validation": "NOT_EXECUTED"}


def verify_source_snapshot(source):
    """Reject a build if its authoritative inputs changed during the run."""
    for name, recorded in source.items():
        path = ROOT / name
        if "link" in recorded:
            same = path.is_symlink() and os.readlink(path) == recorded["link"]
        else:
            same = path.is_file() and not path.is_symlink() and sha(path) == recorded["sha256"]
        if not same:
            raise RuntimeError(f"authoritative source changed during build: {name}")


def checked_make(tree, evidence, name, *args):
    log = evidence / name
    with log.open("w") as stream:
        status = subprocess.run(["make", *args], cwd=tree, stdout=stream, stderr=subprocess.STDOUT).returncode
    # V=s prints shell recipes containing e.g. echo "ERROR: module ...".
    # Those literals are not diagnostics. Match emitted diagnostic lines.
    errors = re.search(
        r"^(?:[^\n]*:\d+(?::\d+)?:\s*(?:fatal )?error:|"
        r"(?:cc1(?:plus)?|clang|gcc):\s*(?:fatal )?error:|"
        r"(?:fatal )?error:|ERROR:|"
        r"(?:make(?:\[\d+\])?:\s*)?\*\*\*.*(?:Error|Stop))",
        log.read_text(errors="replace"), re.I | re.M)
    if status or errors:
        raise RuntimeError(f"make failed or reported an error: {log} (exit {status})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True, help="new output directory")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--dual-phy-no-tx", action="store_true", help="diagnostic only; AP/TX remain gated")
    parser.add_argument("--monitor-owner-diag", action="store_true", help="opt-in C monitor-status lifecycle diagnostics; no device operations")
    parser.add_argument("--reo-idr-claim", action="store_true", help="opt-in C IPQ5018 REO IDR diagnostic trace and descriptor-lifetime source fix")
    parser.add_argument("--qcn6122-vht-siga-trace", action="store_true", help="opt-in default-off QCN6122 VHT SIG-A trace; requires the dual-PHY REO diagnostic profile")
    parser.add_argument("--ipq5018-rx-provenance-trace", action="store_true", help="opt-in default-off IPQ5018 RX layout provenance trace; requires 615 plus the dual-PHY REO diagnostic profile")
    parser.add_argument("--ipq5018-reo-coherent", action="store_true", help="C/IPQ5018 HAL_REO_DST coherent-allocation experiment; requires the complete 616 diagnostic profile")
    parser.add_argument("--ipq5018-wbm-rx-coherent", action="store_true", help="C/IPQ5018 WBM RX release ring 3 coherent-allocation experiment; requires 617 and the complete 616 profile")
    parser.add_argument("--qcn6122-rx-identity-diag", action="store_true", help="opt-in inclusion/audit of default-off QCN6122 RX identity diagnostics; requires complete 618 profile")
    parser.add_argument("--qcn6122-rx-identity-coverage", action="store_true", help="opt-in 621 bounded QCN6122 RX identity coverage; requires 619 and complete 618 profile")
    parser.add_argument("--qcn6122-rx-rings-coherent", action="store_true", help="C-only QCN6122 RX REO/WBM release-ring coherent allocation experiment; requires the complete 621 profile")
    parser.add_argument("--qcn6122-phy-width-trace", action="store_true", help="opt-in default-off C/QCN6122 PHYRX_RSSI_LEGACY width trace; requires the complete 620+621 profile")
    parser.add_argument("--qcn6122-rx-width-join", action="store_true", help="opt-in timestamp-only 625 correlation diagnostics; DIAGNOSTIC_ONLY, requires 622")
    parser.add_argument("--qcn6122-ppdu-ts-patch", type=Path, help="opt-in external 626 patch; requires complete 622+625")
    parser.add_argument("--qcn6122-vht-siga-627-patch", type=Path, help="external 627 SU NSTS/STBC parser fix; requires selected 626")
    parser.add_argument("--qcn6122-vht-siga-627-proof", type=Path, help="pinned external actual-C 627 validation manifest")
    parser.add_argument("--qcn6122-vht-siga-628-patch", type=Path, help="external 628 default-off SIG-A diagnostics; requires selected 627")
    parser.add_argument("--qcn6122-bw-trace-629-patch", type=Path, help="external default-off bounded QCN6122 monitor/REO timing trace; requires the complete 626/627/628 profile")
    parser.add_argument("--qcn6122-bw-trace-629-source06-patch", type=Path, help="external source06 raw-info3 stage capture; mutually exclusive with source05/source07")
    parser.add_argument("--qcn6122-bw-trace-629-source07-patch", type=Path, help="external full source07 package-root patch with bounded legacy printk budget; requires complete 626/627/628 profile")
    parser.add_argument("--qcn6122-sta-rxrate-display-patch", type=Path, help="external source08 display-only station RX-rate patch; requires source07 + E07 + full 629; module-load parameter only")
    parser.add_argument("--ssdk-phy-notify", action="store_true", help="opt-in strict 0903 SSDK MDIO bus PHY notifier mapping")
    parser.add_argument("--native-switch-reset", action="store_true", help="opt-in Native08 GPIO39 reset overlay in RAM cache DTS only")
    parser.add_argument("--tx-coherent-diag", action="store_true", help="opt in to Native C 623+624 coherent TX rings and default-off unknown completion diagnostics")
    parser.add_argument("--dhcp-tx-diag-patch", type=Path, help="explicit external E07 DHCP TX association diagnostic patch; requires 623/624, full 629, and 0903")
    parser.add_argument("--switch-unicast-offload", action="store_true", help="experimental C-only known-unicast bridge offload; hardware acceptance remains required")
    parser.add_argument("--bridge-vlan-filtering", action="store_true", help="diagnostic C-only kernel with bridge VLAN filtering; not VLAN offload support")
    parser.add_argument("--same-c-oem-fw-pas", type=int, choices=(13, 6), help="RAM-only same-C OEM 35-file firmware + BDF 935 root PAS experiment; never a production/native profile")
    args = parser.parse_args()
    if sum(x is not None for x in (args.qcn6122_bw_trace_629_patch,args.qcn6122_bw_trace_629_source06_patch,args.qcn6122_bw_trace_629_source07_patch))>1:
        raise ValueError("select exactly one 629 source revision")
    source06_selected=args.qcn6122_bw_trace_629_source06_patch is not None
    source07_selected=args.qcn6122_bw_trace_629_source07_patch is not None
    sta_rxrate_display_selected=args.qcn6122_sta_rxrate_display_patch is not None
    canonical_sta_rxrate_dir=ROOT/"package/kernel/mac80211/patches/all-ipq50xx"
    canonical_sta_rxrate_patches=tuple(sorted(canonical_sta_rxrate_dir.glob("631-*.patch")))
    if canonical_sta_rxrate_patches:
        raise ValueError("source08 631 patch must remain external: "+", ".join(str(x) for x in canonical_sta_rxrate_patches))
    if sta_rxrate_display_selected and not source07_selected:
        raise ValueError("station RX-rate display requires exactly source07, not source05/source06")
    if sta_rxrate_display_selected and args.dhcp_tx_diag_patch is None:
        raise ValueError("station RX-rate display requires the exact E07 integration patch")
    source_v2_selected=source06_selected or source07_selected
    rx629_sources=(NG.NATIVE_RX_629_SOURCE07_SOURCES if source07_selected else
                   NG.NATIVE_RX_629_SOURCE06_SOURCES if source06_selected else NG.NATIVE_RX_629_SOURCES)
    if sta_rxrate_display_selected:
        rx629_sources=NG.NATIVE_RX_STA_RXRATE_FINAL_SOURCE_MAP
    rx_profile=("native-rx-620-621-622-625-width-join-629-info3-stage-sta-rxrate-display" if sta_rxrate_display_selected else
                "native-rx-620-621-622-625-width-join-629-info3-stage" if source_v2_selected else
                "native-rx-620-621-622-625-width-join-629-bw-trace" if args.qcn6122_bw_trace_629_patch else
                "native-rx-620-621-622-625-width-join" if args.qcn6122_rx_width_join else
                "native-rx-620-621-622" if args.qcn6122_phy_width_trace else "native-rx-618")
    tx_patch_presence=NG.reject_unselected_native_tx_patches(ROOT,args.tx_coherent_diag,rx_profile)
    tx_source_pins=NG.native_tx_623_624_source_gate(ROOT,rx_profile) if args.tx_coherent_diag else None
    phy_width_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/622-ath11k-qcn6122-phy-width-trace.patch"
    phy_width_patch_sha = "8e7f7e3167914545ede4ed90e7ab1e84a9423fc11a34e7dac994d1ca1bc04733"
    # This check precedes path resolution, evidence mkdir, and every cache access.
    if phy_width_patch.is_file() and not args.qcn6122_phy_width_trace:
        raise ValueError("622 patch is present; pass --qcn6122-phy-width-trace before any cache operation")
    if args.qcn6122_phy_width_trace and not phy_width_patch.is_file():
        raise ValueError("--qcn6122-phy-width-trace requires the approved 622 patch")
    if args.qcn6122_phy_width_trace and sha(phy_width_patch) != phy_width_patch_sha:
        raise ValueError("622 QCN6122 PHY width trace patch provenance mismatch")
    if args.qcn6122_phy_width_trace and not all((
            args.dual_phy_no_tx, args.monitor_owner_diag, args.reo_idr_claim,
            args.qcn6122_vht_siga_trace, args.ipq5018_rx_provenance_trace,
            args.ipq5018_reo_coherent, args.ipq5018_wbm_rx_coherent,
            args.qcn6122_rx_identity_diag, args.qcn6122_rx_identity_coverage,
            args.qcn6122_rx_rings_coherent)):
        raise ValueError("622 PHY width trace requires the complete 620+621 QCN6122 profile")
    rx_width_join_patch=ROOT/"package/kernel/mac80211/patches/all-ipq50xx/625-ath11k-c-qcn6122-rx-width-join.patch"
    rx_width_join_sha="13e3057b332b7257068544cb825c266909366b24b8b791f8fb743812c1da2ba9"
    if rx_width_join_patch.is_file() and not args.qcn6122_rx_width_join:
        raise ValueError("625 patch is present; pass --qcn6122-rx-width-join before any cache operation")
    if args.qcn6122_rx_width_join and not args.qcn6122_phy_width_trace:
        raise ValueError("625 diagnostic-only width join requires the explicit 622 profile")
    if args.qcn6122_rx_width_join and (not rx_width_join_patch.is_file() or sha(rx_width_join_patch)!=rx_width_join_sha):
        raise ValueError("625 width-join patch provenance mismatch")
    rx_width_join_source_audit=NG.native_rx_625_source_gate(ROOT) if args.qcn6122_rx_width_join else None
    ppdu_ts_patch=validate_qcn6122_ppdu_ts_patch(args.qcn6122_ppdu_ts_patch, rx_width_join=args.qcn6122_rx_width_join, phy_width_trace=args.qcn6122_phy_width_trace)
    if args.qcn6122_vht_siga_628_patch is not None and args.qcn6122_vht_siga_627_patch is None: raise ValueError("628 opt-in requires external 627")
    siga_627_patch=validate_qcn6122_siga_step_patch(args.qcn6122_vht_siga_627_patch,expected_sha=NG.NATIVE_RX_627_PATCH_SHA,cache_relative_path=QCN6122_SIG627_CACHE_REL,siga_trace=args.qcn6122_vht_siga_trace,ppdu_ts_selected=bool(ppdu_ts_patch))
    siga_628_patch=validate_qcn6122_siga_step_patch(args.qcn6122_vht_siga_628_patch,expected_sha=NG.NATIVE_RX_628_PATCH_SHA,cache_relative_path=QCN6122_SIG628_CACHE_REL,siga_trace=args.qcn6122_vht_siga_trace,ppdu_ts_selected=bool(ppdu_ts_patch))
    siga_627_proof=validate_qcn6122_siga_627_proof(args.qcn6122_vht_siga_627_proof,selected=bool(siga_627_patch))
    siga_patch_sequence=validate_qcn6122_siga_patch_sequence(siga_627_patch,siga_628_patch)
    bw_trace_629_path=(args.qcn6122_bw_trace_629_source07_patch or
                       args.qcn6122_bw_trace_629_source06_patch or args.qcn6122_bw_trace_629_patch)
    bw_trace_629_patch=validate_qcn6122_bw_trace_629_patch(
        bw_trace_629_path,siga_trace=args.qcn6122_vht_siga_trace,
        ppdu_ts_selected=bool(ppdu_ts_patch),patch_627=siga_627_patch,
        patch_628=siga_628_patch,proof_627=siga_627_proof,
        source06=source06_selected,source07=source07_selected)
    dhcp_tx_diag_patch=NG.validate_native_dhcp_tx_diag_patch(
        ROOT,args.dhcp_tx_diag_patch,tx_coherent_diag=args.tx_coherent_diag,
        rx625_selected=args.qcn6122_rx_width_join,
        rx629_selected=bool(bw_trace_629_patch),ssdk_phy_notify=args.ssdk_phy_notify)
    sta_rxrate_patch=NG.validate_native_rx_sta_rxrate_patch(
        args.qcn6122_sta_rxrate_display_patch,source07=source07_selected,
        e07=bool(dhcp_tx_diag_patch),full_629=bool(bw_trace_629_patch))
    ssdk_patch=ROOT/"package/kernel/qca/qca-ssdk/patches/0903-mp-netdev-phy-map-by-bus.patch"
    ssdk_patch_sha="764bfa76da50e9ae6ea159ef0e45acc3528ccd3406126fca29a0cec5a5f11bac"
    if ssdk_patch.is_file() and not args.ssdk_phy_notify:
        raise ValueError("0903 SSDK patch is present; pass --ssdk-phy-notify before any cache operation")
    if args.ssdk_phy_notify and (not ssdk_patch.is_file() or sha(ssdk_patch)!=ssdk_patch_sha):
        raise ValueError("0903 SSDK notifier patch provenance mismatch")
    if args.same_c_oem_fw_pas is not None and not all((
            args.dual_phy_no_tx, args.monitor_owner_diag, args.reo_idr_claim,
            args.qcn6122_vht_siga_trace, args.ipq5018_rx_provenance_trace,
            args.ipq5018_reo_coherent, args.ipq5018_wbm_rx_coherent)):
        raise ValueError("same-C OEM PAS experiment requires the complete frozen 618 diagnostic profile")
    coherent_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/617-ath11k-ipq5018-reo-dst-coherent.patch"
    if coherent_patch.exists() and not args.ipq5018_reo_coherent:
        raise ValueError("617 patch is present; pass --ipq5018-reo-coherent or remove it before any cache operation")
    if args.ipq5018_reo_coherent and not coherent_patch.is_file():
        raise ValueError("--ipq5018-reo-coherent requires the approved 617 patch")
    wbm_coherent_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/618-ath11k-ipq5018-wbm-rx-coherent.patch"
    if wbm_coherent_patch.exists() and not args.ipq5018_wbm_rx_coherent:
        raise ValueError("618 patch is present; pass --ipq5018-wbm-rx-coherent or remove it before any cache operation")
    if args.ipq5018_wbm_rx_coherent and not wbm_coherent_patch.is_file():
        raise ValueError("--ipq5018-wbm-rx-coherent requires the approved 618 patch")
    if args.ipq5018_wbm_rx_coherent and not args.ipq5018_reo_coherent:
        raise ValueError("618 WBM RX coherent experiment requires --ipq5018-reo-coherent")
    identity_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/619-ath11k-qcn6122-rx-identity-diagnostic.patch"
    identity_patch_sha = "aeb2a2851f7d38f944f40e59bc8cc401aed0bc3c90c7f3ec7009fd52946e0f15"
    if identity_patch.is_file() and sha(identity_patch) != identity_patch_sha:
        raise ValueError("619 QCN6122 RX identity patch provenance mismatch")
    if identity_patch.is_file() and not args.qcn6122_rx_identity_diag:
        raise ValueError("619 patch is present; pass --qcn6122-rx-identity-diag before any cache operation")
    if args.qcn6122_rx_identity_diag and not identity_patch.is_file():
        raise ValueError("--qcn6122-rx-identity-diag requires the 619 patch")
    coverage_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/621-ath11k-qcn6122-rx-identity-diagnostic.patch"
    coverage_patch_sha = "91ef9dd4ccf48f1622b001ce7b5e4acb597e5da567c6c411eeae0829258b07b3"
    if coverage_patch.is_file() and sha(coverage_patch) != coverage_patch_sha:
        raise ValueError("621 QCN6122 RX identity patch provenance mismatch")
    coverage_patch_gates = {}
    if coverage_patch.is_file():
        patch_text = coverage_patch.read_text()
        coverage_patch_gates = {
            "issue_quota_16": "ATH11K_QCN6122_RX_ID_QUOTA_ISSUE 16" in patch_text,
            "bw3_probe_quota_4": "ATH11K_QCN6122_RX_ID_QUOTA_BW3 4" in patch_text,
            "normal_control_quota_4": "ATH11K_QCN6122_RX_ID_QUOTA_CONTROL 4" in patch_text,
            "reo_observation_cap_262144": "ATH11K_QCN6122_RX_ID_MAX_REO_OBSERVATIONS 262144" in patch_text,
            "window_30_seconds": "ATH11K_QCN6122_RX_ID_WINDOW (30 * HZ)" in patch_text,
            "raw_msdu_start_9_words_36_bytes": "__le32 words[9];" in patch_text and "FIELD_GET(HAL_TLV_HDR_LEN, tag) != sizeof(words)" in patch_text and "sizeof(desc->msdu_start) != sizeof(words)" in patch_text,
            "drop_rejected_or_truncated_raw_rows": "!ath11k_qcn6122_rx_id_diag_make_raw_msdu_start(" in patch_text and "raw[0] = 0;" in patch_text,
            "attention_info1_requires_12_byte_role": "FIELD_GET(HAL_TLV_HDR_LEN, snap->tags[1]) == sizeof(*attention)" in patch_text,
        }
        if args.qcn6122_rx_identity_coverage and not all(coverage_patch_gates.values()):
            raise ValueError(f"621 patch policy gates failed before cache mutation: {coverage_patch_gates}")
    if coverage_patch.is_file() and not args.qcn6122_rx_identity_coverage:
        raise ValueError("621 patch is present; pass --qcn6122-rx-identity-coverage before any cache operation")
    if args.qcn6122_rx_identity_coverage and not coverage_patch.is_file():
        raise ValueError("--qcn6122-rx-identity-coverage requires the approved 621 patch")
    if args.qcn6122_rx_identity_coverage and not args.qcn6122_rx_identity_diag:
        raise ValueError("621 coverage requires --qcn6122-rx-identity-diag and the 619 patch")
    rings_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/620-ath11k-qcn6122-rx-rings-coherent.patch"
    rings_patch_sha = "d6258d087ce12b14d2d4b01cc430e9442ea70f7cf5c44a054fac6a87ac6c8a2c"
    if rings_patch.is_file() and sha(rings_patch) != rings_patch_sha:
        raise ValueError("620 QCN6122 RX rings patch provenance mismatch")
    if rings_patch.is_file() and not args.qcn6122_rx_rings_coherent:
        raise ValueError("620 patch is present; pass --qcn6122-rx-rings-coherent before any cache operation")
    if args.qcn6122_rx_rings_coherent and not rings_patch.is_file():
        raise ValueError("--qcn6122-rx-rings-coherent requires the approved 620 patch")
    if args.qcn6122_rx_rings_coherent and not all((
            args.dual_phy_no_tx, args.monitor_owner_diag, args.reo_idr_claim,
            args.qcn6122_vht_siga_trace, args.ipq5018_rx_provenance_trace,
            args.ipq5018_reo_coherent, args.ipq5018_wbm_rx_coherent,
            args.qcn6122_rx_identity_diag, args.qcn6122_rx_identity_coverage)):
        raise ValueError("620 coherent ring experiment requires the complete 621 diagnostic profile")
    identity_profile = (
        args.dual_phy_no_tx and args.monitor_owner_diag and args.reo_idr_claim and
        args.qcn6122_vht_siga_trace and args.ipq5018_rx_provenance_trace and
        args.ipq5018_reo_coherent and args.ipq5018_wbm_rx_coherent)
    if args.qcn6122_rx_identity_diag and not identity_profile:
        raise ValueError("QCN6122 RX identity diagnostic requires complete 618 profile")
    if args.qcn6122_rx_identity_coverage and not identity_profile:
        raise ValueError("621 coverage requires all 618 profile flags")
    if args.qcn6122_rx_identity_diag and args.same_c_oem_fw_pas is not None:
        raise ValueError("identity profile requires ordinary frozen 618 QSDK 2.7 firmware")
    if args.ipq5018_wbm_rx_coherent and (
            not args.ipq5018_rx_provenance_trace or
            not args.qcn6122_vht_siga_trace or
            not args.reo_idr_claim or
            not args.monitor_owner_diag or
            not args.dual_phy_no_tx):
        raise ValueError("618 WBM RX coherent experiment requires 617 and the complete 616 C/IPQ5018 diagnostic profile")
    if args.ipq5018_reo_coherent and (
            not args.ipq5018_rx_provenance_trace or
            not args.qcn6122_vht_siga_trace or
            not args.reo_idr_claim or
            not args.monitor_owner_diag or
            not args.dual_phy_no_tx):
        raise ValueError("617 coherent experiment requires the complete 616 C/IPQ5018 diagnostic profile")
    os.umask(0o077)
    tree = args.tree.resolve()
    evidence = args.evidence.resolve()
    if tree == ROOT or ROOT in tree.parents or tree in ROOT.parents:
        raise ValueError("build tree must be external to the authoritative repository")
    if evidence.exists() or tree == evidence or tree in evidence.parents or ROOT in evidence.parents:
        raise ValueError("evidence must be a new external directory, outside the build tree")
    if not (tree / "staging_dir").is_dir() or not (tree / "Makefile").is_file():
        raise ValueError("this recipe requires an existing QSDK cache/toolchain tree")
    cache_626=tree/QCN6122_PPDU_TS_CACHE_REL
    if cache_626.exists() and ppdu_ts_patch is None: raise ValueError("cached 626 requires explicit --qcn6122-ppdu-ts-patch")
    if cache_626.exists() and sha(cache_626)!=QCN6122_PPDU_TS_PATCH_SHA256: raise ValueError("cached 626 hash mismatch")
    cache_627=tree/QCN6122_SIG627_CACHE_REL; cache_628=tree/QCN6122_SIG628_CACHE_REL
    cache_629=tree/QCN6122_BW629_CACHE_REL
    cached_siga_selection=validate_qcn6122_siga_cached_patches(
        tree,select_627=bool(siga_627_patch),select_628=bool(siga_628_patch),
        select_629=bool(bw_trace_629_patch) and not source_v2_selected,
        select_629_source06=bool(bw_trace_629_patch) and source06_selected,
        select_629_source07=bool(bw_trace_629_patch) and source07_selected)
    cached_dhcp_tx_diag=NG.validate_native_dhcp_tx_diag_cached_patch(tree,bool(dhcp_tx_diag_patch))
    cached_sta_rxrate=NG.validate_native_rx_sta_rxrate_cached_patch(tree,sta_rxrate_display_selected)
    evidence.mkdir(parents=True, mode=0o700)
    ordinary_fw_baseline = load_618_firmware_baseline(evidence)
    lock = (tree / ".c-ram-recipe.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    pas_cache_source_state = prepare_pas_cache_source(tree, args.same_c_oem_fw_pas)
    names = sorted(set(subprocess.check_output(
        ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")) - {""})
    names = [n for n in names if (ROOT / n).exists() or (ROOT / n).is_symlink()]
    # Refuse unnoticed tracked source files that exist only in the cache.
    cache_names = set(subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=tree).decode().split("\0")) - {""}
    approved_external_patch_paths={QCN6122_PPDU_TS_CACHE_REL}
    if siga_627_patch: approved_external_patch_paths.add(QCN6122_SIG627_CACHE_REL)
    if siga_628_patch: approved_external_patch_paths.add(QCN6122_SIG628_CACHE_REL)
    if bw_trace_629_patch: approved_external_patch_paths.add(QCN6122_BW629_CACHE_REL)
    if dhcp_tx_diag_patch: approved_external_patch_paths.add(NG.NATIVE_DHCP_TX_DIAG_CACHE_REL)
    if sta_rxrate_patch: approved_external_patch_paths.add(NG.NATIVE_RX_STA_RXRATE_CACHE_REL)
    extra = [n for n in cache_names - set(names) if (tree / n).exists() and n not in approved_external_patch_paths and n.startswith(("package/", "target/", "include/", "scripts/", "toolchain/", "tools/"))]
    if extra:
        raise ValueError(f"unaccounted cache source files: {extra[:12]}")
    manifest = {"started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source_root": str(ROOT), "source_head": output("git", "rev-parse", "HEAD"),
                "source_status": output("git", "status", "--short"), "tree": str(tree),
                "mode": "dual-phy-no-tx" if args.dual_phy_no_tx else "2g-only",
                "monitor_owner_diag": args.monitor_owner_diag,
                "reo_idr_claim": args.reo_idr_claim,
                "qcn6122_vht_siga_trace": args.qcn6122_vht_siga_trace,
                "ipq5018_rx_provenance_trace": args.ipq5018_rx_provenance_trace,
                "ipq5018_reo_coherent": args.ipq5018_reo_coherent,
                "ipq5018_wbm_rx_coherent": args.ipq5018_wbm_rx_coherent,
                "qcn6122_rx_identity_diag": args.qcn6122_rx_identity_diag,
                "qcn6122_rx_identity_coverage": args.qcn6122_rx_identity_coverage,
                "qcn6122_rx_rings_coherent": args.qcn6122_rx_rings_coherent,
                "qcn6122_phy_width_trace": args.qcn6122_phy_width_trace,
                "qcn6122_rx_width_join": args.qcn6122_rx_width_join,
                 "qcn6122_ppdu_ts_correlation": bool(ppdu_ts_patch),
                 "qcn6122_ppdu_ts_patch_sha256": QCN6122_PPDU_TS_PATCH_SHA256 if ppdu_ts_patch else None,
                 "qcn6122_ppdu_ts_post_hal_rx_sha256": QCN6122_PPDU_TS_HAL_RX_SHA256 if ppdu_ts_patch else None,
                 "qcn6122_vht_siga_627_selected": bool(siga_627_patch),
                 "qcn6122_vht_siga_627_patch_sha256": NG.NATIVE_RX_627_PATCH_SHA if siga_627_patch else None,
                 "qcn6122_vht_siga_627_actual_c_proof_sha256": siga_627_proof["sha256"] if siga_627_proof else None,
                 "qcn6122_vht_siga_627_actual_c_proof_path": siga_627_proof["source_path"] if siga_627_proof else None,
                 "qcn6122_vht_siga_627_post_hal_rx_sha256": NG.NATIVE_RX_627_HAL_SHA if siga_627_patch else None,
                 "qcn6122_vht_siga_628_selected": bool(siga_628_patch),
                 "qcn6122_vht_siga_628_patch_sha256": NG.NATIVE_RX_628_PATCH_SHA if siga_628_patch else None,
                 "qcn6122_vht_siga_628_post_hal_rx_sha256": NG.NATIVE_RX_628_HAL_SHA if siga_628_patch else None,
                 "qcn6122_bw_trace_629_selected": bool(bw_trace_629_patch),
                 "qcn6122_bw_trace_629_source06_selected": source06_selected,
                 "qcn6122_bw_trace_629_source07_selected": source07_selected,
                 "qcn6122_sta_rxrate_display_selected": sta_rxrate_display_selected,
                 "qcn6122_sta_rxrate_display_profile": ("default-off; load-only 0444; sta_rxrate_display=1" if sta_rxrate_display_selected else "disabled"),
                 "qcn6122_sta_rxrate_display_patch_sha256": NG.NATIVE_RX_STA_RXRATE_PATCH_SHA if sta_rxrate_patch else None,
                 "qcn6122_sta_rxrate_display_manifest_sha256": NG.NATIVE_RX_STA_RXRATE_MANIFEST_SHA if sta_rxrate_patch else None,
                 "qcn6122_sta_rxrate_display_postimages": NG.NATIVE_RX_STA_RXRATE_FINAL_SOURCE_MAP if sta_rxrate_patch else None,
                 "qcn6122_sta_rxrate_display_cached_state": cached_sta_rxrate,
                 "qcn6122_bw_trace_629_patch_sha256": (NG.NATIVE_RX_629_SOURCE07_PATCH_SHA if source07_selected else NG.NATIVE_RX_629_SOURCE06_PATCH_SHA if source06_selected else NG.NATIVE_RX_629_PATCH_SHA) if bw_trace_629_patch else None,
                 "qcn6122_bw_trace_629_manifest_sha256": (NG.NATIVE_RX_629_SOURCE07_MANIFEST_SHA if source07_selected else NG.NATIVE_RX_629_SOURCE06_MANIFEST_SHA if source06_selected else NG.NATIVE_RX_629_MANIFEST_SHA) if bw_trace_629_patch else None,
                 "qcn6122_bw_trace_629_schema": "rt3000c-ram629-trace-v2" if source_v2_selected else ("source05" if bw_trace_629_patch else None),
                 "qcn6122_bw_trace_629_selected_family": "source-v2" if source_v2_selected else ("source05" if bw_trace_629_patch else None),
                 "qcn6122_bw_trace_629_source_v2_parser": ({"path":str(NG.NATIVE_RX_629_SOURCE06_PARSER),"sha256":NG.NATIVE_RX_629_SOURCE06_PARSER_SHA,
                     "test_sha256":NG.NATIVE_RX_629_SOURCE06_TEST_SHA,"join_key":["generation","pdev","mac","ppdu","start_ts","pkt_type"],
                     "pairing":"only unique early and unique delivery VHT rows; duplicate stages ambiguous"} if source_v2_selected else None),
                 "qcn6122_bw_trace_629_source06_parser": ({"path":str(NG.NATIVE_RX_629_SOURCE06_PARSER),"sha256":NG.NATIVE_RX_629_SOURCE06_PARSER_SHA,
                     "test_sha256":NG.NATIVE_RX_629_SOURCE06_TEST_SHA,"join_key":["generation","pdev","mac","ppdu","start_ts","pkt_type"],
                     "pairing":"only unique early and unique delivery VHT rows; duplicate stages ambiguous"} if source06_selected else None),
                 "qcn6122_bw_trace_629_source07_delta": ({"delta_patch_sha256":NG.NATIVE_RX_629_SOURCE07_DELTA_PATCH_SHA,
                     "delta_manifest_sha256":NG.NATIVE_RX_629_SOURCE07_DELTA_MANIFEST_SHA,
                     "changed_file":"hal_rx.c","hal_rx_postimage_sha256":NG.NATIVE_RX_629_SOURCE07_SOURCES["hal_rx.c"],
                     "legacy_budget_gate":"emit_622 only; MON_PHY ring capture continues when printk cap exhausted"} if source07_selected else None),
                 "qcn6122_bw_trace_629_postimages": rx629_sources if bw_trace_629_patch else None,
                 "qcn6122_bw_trace_629_failed_start_lifecycle": bw_trace_629_patch["failed_start_lifecycle"] if bw_trace_629_patch else None,
                 "qcn6122_bw_trace_629_static_event_storage_bound": ("1024 * 40-byte events = 40 KiB logical event ring + 40 KiB snapshot copy, excluding allocator/context/seq-file overhead" if source_v2_selected else "1024 * 32-byte events = 32 KiB logical event ring, excluding allocator/context/seq-file overhead") if bw_trace_629_patch else None,
                 "qcn6122_bw_trace_629_patch_sequence": bw_trace_629_patch["sequence"] if bw_trace_629_patch else None,
                 "qcn6122_vht_siga_cached_selection": cached_siga_selection,
                 "qcn6122_vht_siga_patch_sequence": siga_patch_sequence,
                "rx_width_classification": "DIAGNOSTIC_ONLY" if args.qcn6122_rx_width_join else None,
                "ssdk_phy_notify": args.ssdk_phy_notify,
                "dhcp_tx_diag": {"explicit_opt_in":bool(dhcp_tx_diag_patch),
                    "patch_sha256":dhcp_tx_diag_patch["patch_sha256"] if dhcp_tx_diag_patch else None,
                    "external_source":dhcp_tx_diag_patch["source_path"] if dhcp_tx_diag_patch else None,
                    "cache_relative_path":NG.NATIVE_DHCP_TX_DIAG_CACHE_REL if dhcp_tx_diag_patch else None,
                    "postimages":dhcp_tx_diag_patch["postimages"] if dhcp_tx_diag_patch else None,
                    "cached_state":cached_dhcp_tx_diag,"runtime":"NOT_EXECUTED"},
                "runtime_validation": "NOT_EXECUTED",
                "rx_diagnostic_patch_provenance": ([
                    {"path": "package/kernel/mac80211/patches/all-ipq50xx/613-ath11k-qcn6122-bw-trace.patch",
                     "sha256": "dc74a497862586767fd39476c5c3ef256d6b65bd4f1631c8e04058122170701d",
                     "purpose": "opt-in C/QCN6122 VHT RX bandwidth diagnostic trace, capped at 16 records and disabled by default"},
                    {"path": "package/kernel/mac80211/patches/all-ipq50xx/614-ath11k-rx-desc-after-expand.patch",
                     "sha256": "fbeb2b21be83a22be2b8c7547100a6c1eb5b114de40462ed6ea1817efc529a95",
                     "purpose": "refresh ath11k RX descriptor pointers after skb head relocation"}
                ] if args.reo_idr_claim else []),
                "switch_unicast_offload": args.switch_unicast_offload,
                "native_switch_reset": args.native_switch_reset,
                "bridge_vlan_filtering": args.bridge_vlan_filtering,
                "same_c_oem_fw_pas": args.same_c_oem_fw_pas,
                "ordinary_firmware_baseline": {k: v for k, v in ordinary_fw_baseline.items() if k != "files"},
                "pas_cache_source_state": pas_cache_source_state,
                "seed_sha256": sha(SEED), "source": {}, "synchronized": []}
    if args.ipq5018_rx_provenance_trace:
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": "package/kernel/mac80211/patches/all-ipq50xx/616-ath11k-ipq5018-rx-layout-provenance.patch",
            "sha256": "366c53691b1597d5a35707eb91df587e85dd0b499c32350fb5896de0ed286eb6",
            "purpose": "opt-in, default-off bounded IPQ5018 RX descriptor layout provenance trace"})
    if args.ipq5018_reo_coherent:
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": "package/kernel/mac80211/patches/all-ipq50xx/617-ath11k-ipq5018-reo-dst-coherent.patch",
            "sha256": "2eed5f88274fa9a912672f8893c9e731386156354248c47033ee2fa089dbd125",
            "proposal_manifest_sha256": "9c65acc6e01de4781000a3c5fa759366494fa7ae2c727c2b22c32351c50f0c62",
            "root_review_sha256": "e58179d2103b8bd007a3331190234988ad19fca8ef98e2242555bc84203ab355",
            "purpose": "C/IPQ5018 HAL_REO_DST coherent allocation experiment"})
    if identity_patch.is_file():
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": str(identity_patch.relative_to(ROOT)), "sha256": identity_patch_sha,
            "selected": args.qcn6122_rx_identity_diag,
            "purpose": "default-off bounded C/QCN6122 RX descriptor identity diagnostic"})
    if coverage_patch.is_file():
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": str(coverage_patch.relative_to(ROOT)), "sha256": coverage_patch_sha,
            "selected": args.qcn6122_rx_identity_coverage,
            "purpose": "621 default-off bounded QCN6122 RX identity coverage and 36-byte descriptor snapshot"})
    if rings_patch.is_file():
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": str(rings_patch.relative_to(ROOT)), "sha256": rings_patch_sha,
            "selected": args.qcn6122_rx_rings_coherent,
            "purpose": "620 C/QCN6122 HAL_REO_DST and WBM release ring 3 coherent-allocation experiment"})
    if args.qcn6122_rx_width_join:
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": str(rx_width_join_patch.relative_to(ROOT)), "sha256": rx_width_join_sha,
            "purpose": "625 timestamp-only 615 correlation; DIAGNOSTIC_ONLY, no width mapping change"})
    if dhcp_tx_diag_patch:
        manifest.setdefault("tx_diagnostic_patch_provenance",[]).append({
            "path":NG.NATIVE_DHCP_TX_DIAG_CACHE_REL,
            "sha256":NG.NATIVE_DHCP_TX_DIAG_PATCH_SHA,
            "external_source":dhcp_tx_diag_patch["source_path"],
            "selected":True,
            "preimages":dhcp_tx_diag_patch["preimages"],
            "postimages":dhcp_tx_diag_patch["postimages"],
            "purpose":"E07 default-off bounded DHCP OFFER/ACK TX association metadata; C/IPQ5018 board 0x23 only"})
    if ppdu_ts_patch:
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": QCN6122_PPDU_TS_CACHE_REL, "sha256": QCN6122_PPDU_TS_PATCH_SHA256,
            "external_source": ppdu_ts_patch["source_path"], "selected": True,
            "purpose": "626 default-off timestamp correlation append; requires 622+625"})
    if siga_627_patch:
        manifest["rx_diagnostic_patch_provenance"].append({"path":QCN6122_SIG627_CACHE_REL,"sha256":NG.NATIVE_RX_627_PATCH_SHA,"external_source":siga_627_patch["source_path"],"selected":True,"post_hal_rx_sha256":NG.NATIVE_RX_627_HAL_SHA,"purpose":"627 SU NSTS mask before STBC conversion; MU parser outputs unchanged"})
    if siga_628_patch:
        manifest["rx_diagnostic_patch_provenance"].append({"path":QCN6122_SIG628_CACHE_REL,"sha256":NG.NATIVE_RX_628_PATCH_SHA,"external_source":siga_628_patch["source_path"],"selected":True,"post_hal_rx_sha256":NG.NATIVE_RX_628_HAL_SHA,"purpose":"628 bounded default-off raw and derived SIG-A fields; DIAGNOSTIC_ONLY"})
    if args.ssdk_phy_notify:
        manifest["ssdk_phy_notify_patch"] = {"path": str(ssdk_patch.relative_to(ROOT)), "sha256": ssdk_patch_sha,
                                                "target": "package/kernel/qca/qca-ssdk", "variant": "qca-ssdk-nohnat"}
    if phy_width_patch.is_file():
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": str(phy_width_patch.relative_to(ROOT)), "sha256": phy_width_patch_sha,
            "selected": args.qcn6122_phy_width_trace,
            "purpose": "622 default-off C/QCN6122 PHYRX_RSSI_LEGACY width and same-MAC parser-context trace; 16 samples maximum"})
    if args.ipq5018_wbm_rx_coherent:
        manifest["rx_diagnostic_patch_provenance"].append({
            "path": "package/kernel/mac80211/patches/all-ipq50xx/618-ath11k-ipq5018-wbm-rx-coherent.patch",
            "sha256": "008d5da91c6dac7870f848a3a1c74f1b106fcd567e64ab446eb70f11e35a6fc0",
            "proposal_manifest_sha256": "d4fc74cf71ea820d3febc8350b0c7b43d3575aa22e511e2aeb615ddb6737e677",
            "root_review_sha256": "a1ccb63a7eba07e71d5d879c07b79ed36fa881ad21a6da60651e027aa483b10d",
            "purpose": "C/IPQ5018 WBM RX release ring 3 coherent allocation experiment"})
    (evidence / "source-dirty.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT))
    with tarfile.open(evidence / "source-inputs.tar", "w") as archive:
        for name in names:
            src, dst = ROOT / name, tree / name
            archive.add(src, arcname=name, recursive=False)
            manifest["source"][name] = {"link": os.readlink(src)} if src.is_symlink() else {"sha256": sha(src)}
            same = dst.is_symlink() and src.is_symlink() and os.readlink(dst) == os.readlink(src)
            if not src.is_symlink() and dst.is_file() and not dst.is_symlink():
                same = sha(src) == sha(dst) and (src.stat().st_mode & 0o777) == (dst.stat().st_mode & 0o777)
            if same:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink():
                dst.unlink()
            if src.is_symlink():
                if dst.exists(): dst.unlink()
                dst.symlink_to(os.readlink(src))
            else:
                shutil.copy(src, dst)
            manifest["synchronized"].append(name)
    if ppdu_ts_patch:
        cache_626.parent.mkdir(parents=True, exist_ok=True)
        if sha(Path(ppdu_ts_patch["source_path"])) != QCN6122_PPDU_TS_PATCH_SHA256: raise ValueError("external 626 changed after preflight")
        shutil.copy2(Path(ppdu_ts_patch["source_path"]), cache_626)
        if sha(cache_626) != QCN6122_PPDU_TS_PATCH_SHA256: raise ValueError("copied 626 patch hash mismatch")
        manifest["synchronized"].append(QCN6122_PPDU_TS_CACHE_REL)
    for selected_patch,cache_path,expected_sha,label in ((siga_627_patch,cache_627,NG.NATIVE_RX_627_PATCH_SHA,"627"),(siga_628_patch,cache_628,NG.NATIVE_RX_628_PATCH_SHA,"628")):
        if selected_patch:
            cache_path.parent.mkdir(parents=True,exist_ok=True); source_path=Path(selected_patch["source_path"])
            if sha(source_path)!=expected_sha: raise ValueError(f"external {label} changed after preflight")
            shutil.copy2(source_path,cache_path)
            if sha(cache_path)!=expected_sha: raise ValueError(f"copied {label} hash mismatch")
            manifest["synchronized"].append(str(cache_path.relative_to(tree)))
    if bw_trace_629_patch:
        source_path=Path(bw_trace_629_patch["source_path"])
        cache_629.parent.mkdir(parents=True,exist_ok=True)
        selected_629_sha=(NG.NATIVE_RX_629_SOURCE07_PATCH_SHA if source07_selected else
                          NG.NATIVE_RX_629_SOURCE06_PATCH_SHA if source06_selected else NG.NATIVE_RX_629_PATCH_SHA)
        if sha(source_path)!=selected_629_sha: raise ValueError("external 629 changed after preflight")
        shutil.copy2(source_path,cache_629)
        if sha(cache_629)!=selected_629_sha: raise ValueError("copied 629 patch hash mismatch")
        manifest["synchronized"].append(str(cache_629.relative_to(tree)))
    if dhcp_tx_diag_patch:
        source_path=Path(dhcp_tx_diag_patch["source_path"])
        cache_patch=tree/NG.NATIVE_DHCP_TX_DIAG_CACHE_REL
        if source_path.is_symlink() or not source_path.is_file() or sha(source_path)!=NG.NATIVE_DHCP_TX_DIAG_PATCH_SHA:
            raise ValueError("external E07 patch changed after preflight")
        cache_patch.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source_path,cache_patch)
        if sha(cache_patch)!=NG.NATIVE_DHCP_TX_DIAG_PATCH_SHA: raise ValueError("copied E07 patch hash mismatch")
        manifest["synchronized"].append(NG.NATIVE_DHCP_TX_DIAG_CACHE_REL)
    if sta_rxrate_patch:
        source_path=Path(sta_rxrate_patch["source_path"])
        if source_path.is_symlink() or not source_path.is_file() or sha(source_path)!=NG.NATIVE_RX_STA_RXRATE_PATCH_SHA:
            raise ValueError("external source08 patch changed after preflight")
        cache_patch=tree/NG.NATIVE_RX_STA_RXRATE_CACHE_REL
        cache_patch.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source_path,cache_patch)
        if sha(cache_patch)!=NG.NATIVE_RX_STA_RXRATE_PATCH_SHA: raise ValueError("copied source08 patch hash mismatch")
        manifest["synchronized"].append(NG.NATIVE_RX_STA_RXRATE_CACHE_REL)
    # Only the external C cache receives these diagnostic overlays.
    config = tree / "target/linux/ipq50xx/config-5.4"
    text = config.read_text()
    for symbol, value in {"RTL8367S_PROBE": "n", "NET_DSA": "y", "NET_DSA_REALTEK_RTL8365MB": "y", "NET_DSA_TAG_RTL8_4": "y",
                          "BRIDGE_VLAN_FILTERING": "y" if args.bridge_vlan_filtering else "n"}.items():
        text = re.sub(rf"^(?:CONFIG_{symbol}=.*|# CONFIG_{symbol} is not set)\n", "", text, flags=re.M)
        text += f"CONFIG_{symbol}=y\n" if value == "y" else f"# CONFIG_{symbol} is not set\n"
    config.write_text(text)
    dts = tree / "target/linux/ipq50xx/dts/ipq5000-rt3000-rtl8367s.dts"
    text = dts.read_text()
    if "realtek,rt3000-unicast-offload" in text:
        raise ValueError("authoritative DTS must keep experimental switch offload disabled")
    if args.switch_unicast_offload:
        text, count = re.subn(r'(switch@1d\s*\{\s*compatible = "realtek,rtl8365mb";)',
                             r'\1\n\t\trealtek,rt3000-unicast-offload;', text)
        if count != 1:
            raise ValueError("unexpected C switch DTS")
    if args.native_switch_reset:
        native_dts = ROOT / "rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-persistent.dts"
        native_sha = "8e4449256b6317908b257dd41e69e6013c124f3d3d4d82018be7b23766aec977"
        if sha(native_dts) != native_sha:
            raise ValueError("Native08 reset overlay source pin mismatch")
        native_nodes = re.findall(r"switch@1d\s*\{([^}]*)\}", native_dts.read_text(), re.S)
        reset_property = "reset-gpios = <&tlmm 39 GPIO_ACTIVE_LOW>;"
        if len(native_nodes) != 1 or native_nodes[0].count(reset_property) != 1:
            raise ValueError("pinned Native08 switch node lacks its single GPIO39 active-low reset")
        if "#include <dt-bindings/gpio/gpio.h>" not in text:
            text = text.replace("/dts-v1/;", "/dts-v1/;\n\n#include <dt-bindings/gpio/gpio.h>", 1)
        switch_nodes = re.findall(r"switch@1d\s*\{([^}]*)\}", text, re.S)
        if len(switch_nodes) != 1:
            raise ValueError("unexpected RAM switch DTS node for Native08 reset overlay")
        if "reset-gpios" in switch_nodes[0]:
            if switch_nodes[0].count(reset_property) != 1:
                raise ValueError("RAM switch already has an unexpected reset-gpios property")
        else:
            text, count = re.subn(r'(switch@1d\s*\{[^}]*?reg\s*=\s*<29>;)',
                                 r'\1\n\t\treset-gpios = <&tlmm 39 GPIO_ACTIVE_LOW>;', text, count=1, flags=re.S)
            if count != 1:
                raise ValueError("unable to add pinned Native08 reset to RAM switch node")
        manifest["native_switch_reset_overlay"] = {
            "source": "rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-persistent.dts",
            "source_sha256": native_sha, "property": reset_property,
            "include": "<dt-bindings/gpio/gpio.h>",
            "scope": "external RAM cache DTS only; LEDs/buttons excluded"}
    if not args.dual_phy_no_tx:
        text, count = re.subn(r'(&wifi1\s*\{[^}]*?status = )"okay"', r'\1"disabled"', text, flags=re.S)
        if count != 1: raise ValueError("unexpected wifi1 DTS")
    dts.write_text(text)
    if args.same_c_oem_fw_pas is None:
        os.environ.pop("RT3000_C_SAME_C_OEM_FW_ROOT", None)
        os.environ.pop("RT3000_C_INSTALLER_QCN6122_BDF", None)
    if args.same_c_oem_fw_pas is not None:
        manifest["same_c_oem_pas"] = apply_root_pas_experiment(tree, args.same_c_oem_fw_pas, evidence)
    ath = tree / "package/kernel/mac80211/ath.mk"
    ath.write_text(ath.read_text() + "\n# External C-only RAM baseline: dynamic country request support.\nconfig-y += ATH_REG_DYNAMIC_USER_REG_HINTS\n")
    if args.monitor_owner_diag:
        ath.write_text(ath.read_text() + "\n# Opt-in C monitor-status owner diagnostics.\nconfig-y += ATH11K_RT3000_MON_OWNER_DIAG\n")
    if args.tx_coherent_diag:
        ath.write_text(ath.read_text() + "\n# Opt-in Native C 623+624 TX diagnostics.\nconfig-y += ATH11K_RT3000_TX_UNKNOWN_DIAG\n")
    if dhcp_tx_diag_patch:
        ath_text=ath.read_text()
        option_anchor='\tconfig ATH11K_RT3000_TX_UNKNOWN_DIAG\n\t\tbool "Enable bounded C TX completion diagnostic"\n\t\tdefault n\n'
        depends_anchor='\tCONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG '+chr(92)+'\n'
        if ath_text.count(option_anchor)!=1 or ath_text.count(depends_anchor)!=1:
            raise ValueError("E07 RAM ath.mk OpenWrt option anchors differ")
        ath_text=ath_text.replace(option_anchor,option_anchor+'\n\tconfig ATH11K_RT3000_DHCP_TX_DIAG\n\t\tbool "Enable bounded C DHCP TX association diagnostic"\n\t\tdefault n\n')
        ath_text=ath_text.replace(depends_anchor,depends_anchor+'\tCONFIG_ATH11K_RT3000_DHCP_TX_DIAG '+chr(92)+'\n')
        ath.write_text(ath_text + "\n# Opt-in E07 bounded DHCP TX association diagnostics.\nconfig-y += ATH11K_RT3000_DHCP_TX_DIAG\n")
        manifest["dhcp_tx_diag"]["openwrt_option_source"]={"ath_mk_sha256":sha(ath),"default":"n","symbol":"CONFIG_ATH11K_RT3000_DHCP_TX_DIAG"}
    sta_rxrate_autoload_source=None
    if sta_rxrate_display_selected:
        sta_rxrate_autoload_source=SR.apply_module_load_parameter(ath,selected=True)
        manifest["qcn6122_sta_rxrate_display_autoload_source"]={
            "ath_mk_sha256":sha(ath),"parameter":sta_rxrate_autoload_source["parameter_line"],
            "default_off":True,"mode":"0444","load_only":True}
        if dhcp_tx_diag_patch:
            manifest["dhcp_tx_diag"]["openwrt_option_source"]["ath_mk_sha256"]=sha(ath)
    bdf = tree / "package/firmware/rt3000-c-oem-wifi/files/board-2-qcn6122.bin"
    original = bdf.read_bytes()
    if args.same_c_oem_fw_pas is None:
        bdf.write_bytes(build_schema_probe(original[84:], original))
        sums = bdf.parent / "SHA256SUMS"
        sums.write_text(sums.read_text().replace(hashlib.sha256(original).hexdigest(), SCHEMA_PROBE_SHA256))
    else:
        if sha(bdf) != OEM_FW_BDF_SHA256:
            raise ValueError("same-C OEM PAS mode requires exact local BDF 935")
        os.environ["RT3000_C_INSTALLER_QCN6122_BDF"] = str(bdf.resolve())
        whitelist, oem_overlay_root, oem_fw_manifest = load_oem_firmware_inputs(evidence)
        manifest["same_c_oem_firmware"] = oem_fw_manifest
        package_makefile = tree / "package/firmware/rt3000-c-oem-wifi/Makefile"
        append_oem_firmware_install_rules(package_makefile, oem_fw_manifest["files"])
        os.environ["RT3000_C_SAME_C_OEM_FW_ROOT"] = str(oem_overlay_root.resolve())
        shutil.copyfile(package_makefile, evidence / "rt3000-c-oem-wifi-cache-Makefile")
    if args.reo_idr_claim and (not args.monitor_owner_diag or not args.dual_phy_no_tx):
        raise ValueError("REO IDR claim profile requires dual PHY and monitor diagnostics")
    if args.qcn6122_vht_siga_trace and (not args.reo_idr_claim or not args.monitor_owner_diag or not args.dual_phy_no_tx):
        raise ValueError("QCN6122 SIG-A trace requires dual PHY, monitor diagnostics, and REO IDR profile")
    if args.ipq5018_rx_provenance_trace and (not args.qcn6122_vht_siga_trace or not args.reo_idr_claim or not args.monitor_owner_diag or not args.dual_phy_no_tx):
        raise ValueError("IPQ5018 RX provenance trace requires 615 SIG-A, dual PHY, monitor diagnostics, and REO IDR profile")
    if args.reo_idr_claim:
        pinned_rx_patches = {
            "package/kernel/mac80211/patches/all-ipq50xx/613-ath11k-qcn6122-bw-trace.patch": "dc74a497862586767fd39476c5c3ef256d6b65bd4f1631c8e04058122170701d",
            "package/kernel/mac80211/patches/all-ipq50xx/614-ath11k-rx-desc-after-expand.patch": "fbeb2b21be83a22be2b8c7547100a6c1eb5b114de40462ed6ea1817efc529a95",
        }
        if args.qcn6122_vht_siga_trace:
            pinned_rx_patches["package/kernel/mac80211/patches/all-ipq50xx/615-ath11k-qcn6122-vht-siga-trace.patch"] = "7db6ff4a94d192f483f755bb896a63fc914646ce9e764a7ece4d4667e9b832fd"
        if args.ipq5018_rx_provenance_trace:
            pinned_rx_patches["package/kernel/mac80211/patches/all-ipq50xx/616-ath11k-ipq5018-rx-layout-provenance.patch"] = "366c53691b1597d5a35707eb91df587e85dd0b499c32350fb5896de0ed286eb6"
        if args.ipq5018_reo_coherent:
            pinned_rx_patches["package/kernel/mac80211/patches/all-ipq50xx/617-ath11k-ipq5018-reo-dst-coherent.patch"] = "2eed5f88274fa9a912672f8893c9e731386156354248c47033ee2fa089dbd125"
        if args.ipq5018_wbm_rx_coherent:
            pinned_rx_patches["package/kernel/mac80211/patches/all-ipq50xx/618-ath11k-ipq5018-wbm-rx-coherent.patch"] = "008d5da91c6dac7870f848a3a1c74f1b106fcd567e64ab446eb70f11e35a6fc0"
        if args.qcn6122_rx_identity_diag:
            pinned_rx_patches[str(identity_patch.relative_to(ROOT))] = identity_patch_sha
        if args.qcn6122_rx_identity_coverage:
            pinned_rx_patches[str(coverage_patch.relative_to(ROOT))] = coverage_patch_sha
        if args.qcn6122_phy_width_trace:
            pinned_rx_patches[str(phy_width_patch.relative_to(ROOT))] = phy_width_patch_sha
        if args.qcn6122_rx_width_join:
            pinned_rx_patches[str(rx_width_join_patch.relative_to(ROOT))] = rx_width_join_sha
        for relpath, expected in pinned_rx_patches.items():
            if sha(ROOT / relpath) != expected:
                raise ValueError(f"approved RX patch provenance hash mismatch: {relpath}")
        if args.qcn6122_vht_siga_trace:
            proposal_manifest = Path("<EVIDENCE>")
            proposal_sha = "af13920ccd1223fa1ad3a0b835c757bee9ea73ddc30dadc2236adc814d84ab83"
            if not proposal_manifest.is_file() or sha(proposal_manifest) != proposal_sha:
                raise ValueError("615 proposal manifest provenance mismatch")
        if args.ipq5018_rx_provenance_trace:
            proposal_manifest = Path("<EVIDENCE>")
            proposal_sha = "b43ce43aa8f9da181a62d682997847ca0d531b7889eaa6c89ac08ffd9b1a8b83"
            if not proposal_manifest.is_file() or sha(proposal_manifest) != proposal_sha:
                raise ValueError("616 proposal manifest provenance mismatch")
        if args.ipq5018_wbm_rx_coherent:
            proposal_manifest = Path("<EVIDENCE>")
            proposal_sha = "d4fc74cf71ea820d3febc8350b0c7b43d3575aa22e511e2aeb615ddb6737e677"
            if not proposal_manifest.is_file() or sha(proposal_manifest) != proposal_sha:
                raise ValueError("618 proposal manifest provenance mismatch")
            source_review = Path("<EVIDENCE>")
            review_sha = "a1ccb63a7eba07e71d5d879c07b79ed36fa881ad21a6da60651e027aa483b10d"
            if not source_review.is_file() or sha(source_review) != review_sha:
                raise ValueError("618 root source approval provenance mismatch")
            review_record = json.loads(source_review.read_text())
            if (review_record.get("status") != "ROOT_SOURCE_REVIEW_PASS_APPROVED_INTEGRATION_ONLY" or
                    review_record.get("runtime") != "NOT_EXECUTED" or
                    review_record.get("build") != "NOT_EXECUTED" or
                    review_record.get("patch_sha256") != "008d5da91c6dac7870f848a3a1c74f1b106fcd567e64ab446eb70f11e35a6fc0" or
                    review_record.get("proposal_manifest_sha256") != "d4fc74cf71ea820d3febc8350b0c7b43d3575aa22e511e2aeb615ddb6737e677" or
                    review_record.get("post_dp_sha256") != "cf9060e854a0d85b25215a4dc354df68850a4416bcd27130cc3600a728b08e19"):
                raise ValueError("618 root source approval status/content mismatch")
        if args.ipq5018_reo_coherent:
            proposal_manifest = Path("<EVIDENCE>")
            proposal_sha = "9c65acc6e01de4781000a3c5fa759366494fa7ae2c727c2b22c32351c50f0c62"
            if not proposal_manifest.is_file() or sha(proposal_manifest) != proposal_sha:
                raise ValueError("617 proposal manifest provenance mismatch")
            source_review = Path("<EVIDENCE>")
            review_sha = "e58179d2103b8bd007a3331190234988ad19fca8ef98e2242555bc84203ab355"
            if not source_review.is_file() or sha(source_review) != review_sha:
                raise ValueError("617 root source approval provenance mismatch")
            review_record = json.loads(source_review.read_text())
            if (review_record.get("status") != "ROOT_SOURCE_EXPERIMENT_APPROVED_BUILDER_REVIEW_PENDING" or
                    review_record.get("writes") is not False or
                    review_record.get("patch_sha256") != "2eed5f88274fa9a912672f8893c9e731386156354248c47033ee2fa089dbd125" or
                    review_record.get("post_dp_c") != "b4eb71eafb877bcdc2f1167914f70390dd59452dff72b74702b393a8c1ba8844"):
                raise ValueError("617 root source approval status/content mismatch")
        metadata_paths = [tree / "tmp/info/.packageinfo-kernel_mac80211",
                          tree / "tmp/info/.packageinfo-system_procd",
                          tree / "tmp/.packageinfo", tree / "tmp/.config-package.in"]
        backup = evidence / "metadata-before-reo-idr-refresh"
        backup.mkdir(mode=0o700)
        metadata_hashes = {}
        for p in metadata_paths:
            if p.is_file():
                out = backup / p.name
                shutil.copyfile(p, out)
                metadata_hashes[str(p.relative_to(tree))] = sha(out)
                p.unlink()
        manifest["metadata_before_reo_idr_refresh"] = metadata_hashes
        checked_make(tree, evidence, "prepare-tmpinfo-reo-idr.log", "prepare-tmpinfo")
        for p in metadata_paths:
            if not p.is_file():
                raise ValueError(f"metadata refresh did not regenerate {p.relative_to(tree)}")
        if "ATH11K_RT3000_REO_IDR_CLAIM" not in (tree / "tmp/info/.packageinfo-kernel_mac80211").read_text():
            raise ValueError("refreshed mac80211 package metadata lacks REO IDR option")
        if "ATH11K_RT3000_REO_IDR_CLAIM" not in (tree / "tmp/.config-package.in").read_text():
            raise ValueError("refreshed config package metadata lacks REO IDR option")
        if dhcp_tx_diag_patch:
            for metadata in (tree/"tmp/info/.packageinfo-kernel_mac80211",tree/"tmp/.config-package.in"):
                if "ATH11K_RT3000_DHCP_TX_DIAG" not in metadata.read_text():
                    raise ValueError("refreshed RAM package metadata lacks E07 DHCP TX option")
        if "Package: procd" not in (tree / "tmp/info/.packageinfo-system_procd").read_text():
            raise ValueError("refreshed procd package metadata is incomplete")
    if args.qcn6122_vht_siga_trace:
        test_source = ROOT / "rt3000-machine-c/tests/test_qcn6122_vht_siga_policy.c"
        expected_test = "1d0f3740400d0ca2f175bf7c84ca4a1b5c68a172bf86b86bff35f4d421aff767"
        if sha(test_source) != expected_test:
            raise ValueError("615 host policy fixture hash mismatch")
        integration_patch = ROOT / "package/kernel/mac80211/patches/all-ipq50xx/615-ath11k-qcn6122-vht-siga-trace.patch"
        if sha(integration_patch) != "7db6ff4a94d192f483f755bb896a63fc914646ce9e764a7ece4d4667e9b832fd":
            raise ValueError("615 integration patch changed after provenance check")
        host_binary = evidence / "test-qcn6122-vht-siga-policy"
        with (evidence / "qcn6122-policy-host-test.log").open("w") as stream:
            subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "rt3000-machine-c/tests"),
                            str(test_source), "-o", str(host_binary)],
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
            subprocess.run([str(host_binary)], stdout=stream, stderr=subprocess.STDOUT, check=True)
        manifest["qcn6122_vht_siga_trace_provenance"] = {
            "proposal_manifest_sha256": "af13920ccd1223fa1ad3a0b835c757bee9ea73ddc30dadc2236adc814d84ab83",
            "proposal_patch_sha256": "42ac7efd279e68f016b881340012939dff1e9c224e690fb9d205b1b42b4c5574",
            "integration_patch_sha256": "7db6ff4a94d192f483f755bb896a63fc914646ce9e764a7ece4d4667e9b832fd",
            "patch_path": "package/kernel/mac80211/patches/all-ipq50xx/615-ath11k-qcn6122-vht-siga-trace.patch",
            "test_source_sha256": expected_test, "host_test": "PASS"}
        manifest["native_tx_623_624"]={"explicit_opt_in":args.tx_coherent_diag,"patch_presence":tx_patch_presence,
                                   "source_pins":tx_source_pins,"runtime":"NOT_EXECUTED"}
    manifest["qcn6122_rx_width_join_source_audit"]=rx_width_join_source_audit
    (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copy(SEED, tree / ".config")
    tx_symbol="CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG"
    tx_text=(tree/".config").read_text()
    tx_text=re.sub(r"^(?:CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG=.*|# CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG is not set)\n","",tx_text,flags=re.M)
    tx_text += tx_symbol+"=y\n" if args.tx_coherent_diag else "# "+tx_symbol+" is not set\n"
    (tree/".config").write_text(tx_text)
    if dhcp_tx_diag_patch:
        dhcp_symbol="CONFIG_ATH11K_RT3000_DHCP_TX_DIAG"
        dhcp_text=(tree/".config").read_text()
        dhcp_text=re.sub(r"^(?:CONFIG_ATH11K_RT3000_DHCP_TX_DIAG=.*|# CONFIG_ATH11K_RT3000_DHCP_TX_DIAG is not set)\n","",dhcp_text,flags=re.M)
        dhcp_text += dhcp_symbol+"=y\n"
        (tree/".config").write_text(dhcp_text)
    if args.reo_idr_claim:
        config = tree / ".config"
        text = re.sub(r"^(?:CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=.*|# CONFIG_ATH11K_RT3000_REO_IDR_CLAIM is not set)\n", "", config.read_text(), flags=re.M)
        config.write_text(text + "CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=y\n")
    checked_make(tree, evidence, "defconfig.log", "defconfig")
    generated = (tree / ".config").read_text()
    required = ["CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_ram=y", "CONFIG_TARGET_ROOTFS_INITRAMFS=y", "CONFIG_PACKAGE_netifd=y", "CONFIG_PACKAGE_firewall=y", "CONFIG_PACKAGE_dnsmasq=y", "CONFIG_PACKAGE_wpad-basic-wolfssl=y", "CONFIG_ATH11K_MEM_PROFILE_256M=y"]
    if args.reo_idr_claim:
        required.extend(["CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=y", "CONFIG_PACKAGE_procd=y"])
    if dhcp_tx_diag_patch:
        required.append("CONFIG_ATH11K_RT3000_DHCP_TX_DIAG=y")
    if any(line not in generated.splitlines() for line in required) or "CONFIG_TARGET_MULTI_PROFILE=y" in generated:
        raise ValueError("C-only configuration guard failed")
    profiles = re.findall(r"^CONFIG_TARGET_.*_DEVICE_.*=y$", generated, re.M)
    if profiles != [required[0]]: raise ValueError(f"unexpected profiles: {profiles}")
    shutil.copy(tree / ".config", evidence / "resolved.config")
    manifest["resolved_config_sha256"] = sha(tree / ".config")
    manifest["effective_source"] = {n: ({"link": os.readlink(tree / n)} if (tree / n).is_symlink() else {"sha256": sha(tree / n)}) for n in names}
    if ppdu_ts_patch: manifest["effective_source"][QCN6122_PPDU_TS_CACHE_REL]={"sha256":sha(cache_626),"external_source":ppdu_ts_patch["source_path"]}
    if siga_627_patch: manifest["effective_source"][QCN6122_SIG627_CACHE_REL]={"sha256":sha(cache_627),"external_source":siga_627_patch["source_path"]}
    if siga_628_patch: manifest["effective_source"][QCN6122_SIG628_CACHE_REL]={"sha256":sha(cache_628),"external_source":siga_628_patch["source_path"]}
    if bw_trace_629_patch: manifest["effective_source"][QCN6122_BW629_CACHE_REL]={"sha256":sha(cache_629),"external_source":bw_trace_629_patch["source_path"]}
    if dhcp_tx_diag_patch: manifest["effective_source"][NG.NATIVE_DHCP_TX_DIAG_CACHE_REL]={"sha256":sha(tree/NG.NATIVE_DHCP_TX_DIAG_CACHE_REL),"external_source":dhcp_tx_diag_patch["source_path"]}
    manifest["downloads"] = record_tree((tree / "dl").resolve())
    manifest["toolchains"] = {p.name: record_tree(p.resolve()) for p in (tree / "staging_dir").glob("toolchain-*")}
    expected_toolchain = json.loads((SEED.parent / "toolchain-lock.json").read_text())
    actual_toolchain = hashlib.sha256(json.dumps(manifest["toolchains"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual_toolchain != expected_toolchain["toolchain_tree_sha256"]:
        raise ValueError("toolchain cache differs from the frozen baseline; review before updating the lock")
    manifest["toolchain_lock_verified"] = actual_toolchain
    (evidence / "host-packages.txt").write_text(output("dpkg-query", "-W", "-f=${Package}=${Version}\n") + "\n")
    manifest["host"] = {"uname": output("uname", "-a"), "python": output("python3", "--version"), "make": output("make", "--version"), "source_date_epoch_env": os.environ.get("SOURCE_DATE_EPOCH")}
    (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(names)} source files; inputs: {evidence / 'inputs.json'}", flush=True)
    if args.build:
        checked_make(tree, evidence, "oem-wifi-package-clean.log", "package/firmware/rt3000-c-oem-wifi/clean")
        ssdk_build_audit = None
        if args.ssdk_phy_notify:
            ssdk_pkgs = list(tree.glob("build_dir/target-*/linux-*/qca-ssdk-nohnat/qca-ssdk-*"))
            if len(ssdk_pkgs) != 1:
                raise ValueError("prepared SSDK package directory ambiguous")
            ssdk_pkg = ssdk_pkgs[0]
            if "CONFIG_PACKAGE_kmod-qca-ssdk-nohnat=y" not in (tree / ".config").read_text().splitlines():
                raise ValueError("RAM profile lacks selected nohnat SSDK package")
            checked_make(tree, evidence, "ssdk-clean.log", "package/kernel/qca/qca-ssdk/clean")
            checked_make(tree, evidence, "ssdk-prepare.log", "package/kernel/qca/qca-ssdk/prepare", "V=s")
            ssdk_source_audit = NG.native_ssdk_source_gate(ROOT, True)
            ssdk_started_ns = time.time_ns()
            checked_make(tree, evidence, "ssdk-compile.log", "package/kernel/qca/qca-ssdk/compile", "V=s")
            ssdk_build_audit = NG.verify_native_ssdk_build(ssdk_pkg, ssdk_started_ns, evidence / "ssdk-compile.log")
            ssdk_unstripped = evidence / "qca-ssdk-fresh-module.ko"
            shutil.copy2(ssdk_pkg / "build/bin/qca-ssdk.ko", ssdk_unstripped)
            ssdk_stage = Path(ssdk_build_audit["staged_module"])
            ssdk_report = evidence / "qca-ssdk-staged-module-binding.json"
            with (evidence / "qca-ssdk-staged-module-binding.log").open("w") as audit_log:
                subprocess.run([sys.executable, str(ROOT / "rt3000-machine-c/tools/audit_ath11k_symbols.py"),
                                "--packaged", str(ssdk_stage), "--unstripped", str(ssdk_unstripped),
                                "--output", str(ssdk_report)], cwd=ROOT, stdout=audit_log,
                               stderr=subprocess.STDOUT, check=True)
            ssdk_build_audit["stage_elf_allocated_binding"] = {"report_sha256": sha(ssdk_report), "status": "PASS"}
            manifest["ssdk_source_audit"] = ssdk_source_audit
            manifest["ssdk_build_audit"] = ssdk_build_audit
            manifest["ssdk_build_started_ns"] = ssdk_started_ns
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if args.same_c_oem_fw_pas is not None:
            q6_source = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5/drivers/remoteproc/qcom_q6v5_mpd.c"
            q6_source.touch()
            manifest["same_c_oem_pas"]["q6_source_mtime_ns_before_build"] = q6_source.stat().st_mtime_ns
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if args.qcn6122_vht_siga_trace or args.ipq5018_rx_provenance_trace or args.qcn6122_rx_identity_diag or args.tx_coherent_diag or dhcp_tx_diag_patch:
            checked_make(tree, evidence, "mac80211-clean.log", "package/kernel/mac80211/clean")
        mac80211_started_ns = time.time_ns()
        build_started_ns = time.time_ns()
        checked_make(tree, evidence, "build.log", f"-j{args.jobs}", "V=s")
        if ssdk_build_audit is not None:
            # The world build may either relink a fresh SSDK output or retain the
            # already-audited package output. The verifier accepts the latter
            # only when every object, dependency, source, archive and module
            # snapshot remains byte/metadata-identical to the fresh package audit.
            final_ssdk_audit = NG.verify_native_ssdk_build(
                ssdk_pkg, build_started_ns, evidence / "build.log", dependency_proof=ssdk_build_audit)
            final_ssdk_unstripped = evidence / "qca-ssdk-final-module.ko"
            shutil.copy2(ssdk_pkg / "build/bin/qca-ssdk.ko", final_ssdk_unstripped)
            final_stage_report = evidence / "qca-ssdk-final-staged-module-binding.json"
            with (evidence / "qca-ssdk-final-staged-module-binding.log").open("w") as audit_log:
                subprocess.run([sys.executable, str(ROOT / "rt3000-machine-c/tools/audit_ath11k_symbols.py"),
                                "--packaged", final_ssdk_audit["staged_module"],
                                "--unstripped", str(final_ssdk_unstripped),
                                "--output", str(final_stage_report)], cwd=ROOT,
                               stdout=audit_log, stderr=subprocess.STDOUT, check=True)
            final_ssdk_audit["stage_elf_allocated_binding"] = {
                "report_sha256": sha(final_stage_report), "status": "PASS"}
            ssdk_build_audit["final_packaging_build_audit"] = final_ssdk_audit
            manifest["ssdk_final_build_started_ns"] = build_started_ns
            rootfs_ssdk = list(tree.glob("build_dir/target-*/root-ipq50xx/lib/modules/*/qca-ssdk.ko"))
            if len(rootfs_ssdk) != 1:
                raise ValueError("RAM rootfs SSDK module missing/ambiguous")
            report = evidence / "qca-ssdk-rootfs-module-binding.json"
            with (evidence / "qca-ssdk-rootfs-module-binding.log").open("w") as audit_log:
                subprocess.run([sys.executable, str(ROOT / "rt3000-machine-c/tools/audit_ath11k_symbols.py"),
                                "--packaged", str(rootfs_ssdk[0]), "--unstripped",
                                str(final_ssdk_unstripped), "--output", str(report)],
                               cwd=ROOT, stdout=audit_log, stderr=subprocess.STDOUT, check=True)
            ssdk_build_audit["rootfs_elf_allocated_binding"] = {
                "report_sha256": sha(report), "status": "PASS", "rootfs_module_sha256": sha(rootfs_ssdk[0])}
        verify_source_snapshot(manifest["source"])
        kernel_configs = list((tree / "build_dir").glob("target-*/linux-*/linux-*/.config"))
        if len(kernel_configs) != 1:
            raise ValueError(f"expected one target kernel config, got {kernel_configs}")
        actual_vlan_filtering = "CONFIG_BRIDGE_VLAN_FILTERING=y" in kernel_configs[0].read_text().splitlines()
        if actual_vlan_filtering != args.bridge_vlan_filtering:
            raise ValueError("compiled kernel bridge VLAN filtering differs from requested mode")
        shutil.copy(kernel_configs[0], evidence / "kernel.config")
        if args.same_c_oem_fw_pas is not None:
            kernel_config_text = kernel_configs[0].read_text().splitlines()
            required_pas_kernel = ["CONFIG_QCOM_Q6V5_WCSS=y", "CONFIG_QCOM_Q6V5_MPD=y"]
            if any(item not in kernel_config_text for item in required_pas_kernel):
                raise ValueError("same-C root PAS mode lacks the required compiled Q6/MPD kernel profile")
            kernel_dir = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5"
            q6_source = kernel_dir / "drivers/remoteproc/qcom_q6v5_mpd.c"
            q6_object = kernel_dir / "drivers/remoteproc/qcom_q6v5_mpd.o"
            if not (kernel_dir / "vmlinux").is_file() or not q6_object.is_file():
                raise ValueError("same-C PAS mode lacks built vmlinux/Q6 object")
            if q6_object.stat().st_mtime_ns < manifest["same_c_oem_pas"]["q6_source_mtime_ns_before_build"]:
                raise ValueError("Q6 object predates selected source; refusing stale PAS mode artifact")
        fits = sorted((tree / "bin/targets/ipq50xx/arm").glob("*rtl8367s_ram-initramfs*.itb"))
        if len(fits) != 1: raise ValueError(f"expected one C FIT, got {fits}")
        fit = fits[0]
        shutil.copy(fit, evidence / fit.name)
        modules = list((tree / "build_dir").glob("**/ipkg-*/kmod-ath11k/lib/modules/*/ath11k.ko"))
        if len(modules) != 1:
            raise ValueError(f"expected one built ath11k module, got {modules}")
        if args.qcn6122_rx_width_join:
            manifest["qcn6122_rx_width_join_module_marker"] = NG.verify_native_rx_625_module_marker(modules[0],diagnostic_628=bool(siga_628_patch))
            if bw_trace_629_patch:
                manifest["qcn6122_bw_trace_629_module_markers"]=NG.verify_native_rx_629_module_marker(
                    modules[0],source06=source06_selected,source07=source07_selected)
            if ppdu_ts_patch:
                mod=modules[0].read_bytes()
                if siga_627_patch:
                    manifest["qcn6122_vht_siga_627_628_module_markers"]=NG.verify_native_rx_627_628_module_marker(
                        modules[0],diagnostic_628=bool(siga_628_patch))
                else:
                    marker_ok=all(x in mod for x in (b"parser_ppdu_start_ts=0x%08x", b"siga_bw=%u ppdu_start_ts=0x%08x"))
                    if not marker_ok: raise ValueError("626 compiled module timestamp markers missing")
                    manifest["qcn6122_ppdu_ts_module_markers"]={"parser_ppdu_start_ts":True,"ppdu_start_ts":True}
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if args.tx_coherent_diag:
            manifest["native_tx_623_624"]["module_marker"] = NG.verify_native_tx_623_624_module_marker(modules[0])
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        backport_configs = list((tree / "build_dir").glob("target-*/linux-*/backports-*/.config"))
        if len(backport_configs) != 1:
            raise ValueError("expected one backports configuration")
        diag_selected = "CPTCFG_ATH11K_RT3000_MON_OWNER_DIAG=y" in backport_configs[0].read_text().splitlines()
        if diag_selected != args.monitor_owner_diag:
            raise ValueError("monitor owner diagnostic selection differs from requested build mode")
        dhcp_diag_selected="CPTCFG_ATH11K_RT3000_DHCP_TX_DIAG=y" in backport_configs[0].read_text().splitlines()
        if dhcp_diag_selected != bool(dhcp_tx_diag_patch): raise ValueError("E07 backports selection differs from explicit patch opt-in")
        if sta_rxrate_display_selected:
            selected_lines=backport_configs[0].read_text(errors="replace").splitlines()
            nss_disabled=("# CPTCFG_ATH11K_NSS_SUPPORT is not set" in selected_lines and
                          "CPTCFG_ATH11K_NSS_SUPPORT=y" not in selected_lines)
            manifest["qcn6122_sta_rxrate_display_profile_audit"]=SR.select_sta_rxrate_display_profile(
                selected=True,source07=source07_selected,e07=bool(dhcp_tx_diag_patch),
                full_629=bool(bw_trace_629_patch),nss_support_disabled=nss_disabled)
        shutil.copy(backport_configs[0], evidence / "backports.config")
        autoconf = backport_configs[0].parent / "backport-include/backport/autoconf.h"
        actual_diag = "#define CPTCFG_ATH11K_RT3000_MON_OWNER_DIAG 1" in autoconf.read_text().splitlines()
        if actual_diag != args.monitor_owner_diag:
            raise ValueError("generated autoconf diagnostic macro differs from requested build mode")
        dhcp_macro="#define CPTCFG_ATH11K_RT3000_DHCP_TX_DIAG 1" in autoconf.read_text().splitlines()
        if dhcp_macro != bool(dhcp_tx_diag_patch): raise ValueError("generated E07 autoconf macro differs from explicit patch opt-in")
        reo_selected = "CPTCFG_ATH11K_RT3000_REO_IDR_CLAIM=y" in backport_configs[0].read_text().splitlines()
        if reo_selected != args.reo_idr_claim:
            raise ValueError("REO IDR backports selection differs from requested build mode")
        reo_macro = "#define CPTCFG_ATH11K_RT3000_REO_IDR_CLAIM 1" in autoconf.read_text().splitlines()
        if reo_macro != args.reo_idr_claim:
            raise ValueError("generated REO IDR autoconf macro differs from requested build mode")
        if args.reo_idr_claim:
            ram_init = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq50xx/sbin/init"
            if not ram_init.exists():
                raise ValueError("RAM rootfs lacks /sbin/init required by generic /init switch_root")
        shutil.copy(autoconf, evidence / "backports-autoconf.h")
        if sta_rxrate_display_selected:
            rootfs = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq50xx"
            cpio_candidates = sorted(tree.glob("build_dir/**/initramfs_data.cpio.lzma"))
            if len(cpio_candidates) != 1:
                raise ValueError(f"source08 requires exactly one generated initramfs_data.cpio.lzma, found {cpio_candidates}")
            autoconf_text=autoconf.read_text(errors="replace")
            if "#define CPTCFG_ATH11K_NSS_SUPPORT 1" in autoconf_text:
                raise ValueError("source08 requires compile-time NSS support disabled")
            manifest["qcn6122_sta_rxrate_display_autoload_audit"]=SR.audit_modules_autoload(
                ath_mk=tree/"package/kernel/mac80211/ath.mk",rootfs=rootfs,
                initramfs_cpio_lzma=cpio_candidates[0],backports_config=backport_configs[0],module=modules[0])
            manifest["qcn6122_sta_rxrate_display_autoload_audit"].update({
                "generated_initramfs_path":str(cpio_candidates[0]),
                "generated_initramfs_sha256":sha(cpio_candidates[0]),
                "compile_time_nss_autoconf":"disabled",
                "module_load_parameter_argument_source":sta_rxrate_autoload_source})
            manifest["qcn6122_sta_rxrate_display_elf_audit"]=NG.verify_native_rx_sta_rxrate_elf(modules[0],require_symbols=False)
            (evidence/"inputs.json").write_text(json.dumps(manifest,indent=2)+"\n")
        tx_object_audit = None
        if args.tx_coherent_diag:
            tx_overrides={"drivers/net/wireless/ath/ath11k/dp_tx.c":NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/dp_tx.c"]} if dhcp_tx_diag_patch else None
            tx_kconfig_override=NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/Kconfig"] if dhcp_tx_diag_patch else None
            tx_object_audit=NG.verify_native_tx_623_624_objects(backport_configs[0].parent,backport_configs[0],autoconf,build_started_ns,evidence/"build.log",compiled_source_overrides=tx_overrides,kconfig_source_override=tx_kconfig_override)
            manifest["native_tx_623_624"]["compiled_object_source_gate"]=tx_object_audit
            (evidence/"inputs.json").write_text(json.dumps(manifest,indent=2)+"\n")
        if dhcp_tx_diag_patch:
            manifest["dhcp_tx_diag"]["compiled_objects"]=NG.verify_native_dhcp_tx_diag_objects(
                backport_configs[0].parent,backport_configs[0],autoconf,build_started_ns,evidence/"build.log",source08=sta_rxrate_display_selected)
            (evidence/"inputs.json").write_text(json.dumps(manifest,indent=2)+"\n")
        rx_width_join_object_audit = None
        if args.qcn6122_rx_width_join:
            rx_overrides={}
            if args.tx_coherent_diag: rx_overrides["drivers/net/wireless/ath/ath11k/dp.c"]=NG.NATIVE_TX_623_624_SOURCES["drivers/net/wireless/ath/ath11k/dp.c"]
            if bw_trace_629_patch:
                rx_sources=rx629_sources
                rx_overrides["drivers/net/wireless/ath/ath11k/hal_rx.c"]=rx_sources["hal_rx.c"]
                rx_overrides["drivers/net/wireless/ath/ath11k/dp_rx.c"]=rx_sources["dp_rx.c"]
            elif siga_628_patch: rx_overrides["drivers/net/wireless/ath/ath11k/hal_rx.c"]=NG.NATIVE_RX_628_HAL_SHA
            elif siga_627_patch: rx_overrides["drivers/net/wireless/ath/ath11k/hal_rx.c"]=NG.NATIVE_RX_627_HAL_SHA
            elif ppdu_ts_patch: rx_overrides["drivers/net/wireless/ath/ath11k/hal_rx.c"]=QCN6122_PPDU_TS_HAL_RX_SHA256
            rx_width_join_object_audit = NG.verify_native_rx_625_objects(
                backport_configs[0].parent, backport_configs[0], autoconf,
                mac80211_started_ns, evidence / "build.log",compiled_source_overrides=rx_overrides or None,diagnostic_628=bool(siga_628_patch),diagnostic_629=bool(bw_trace_629_patch),source08=sta_rxrate_display_selected)
            manifest["qcn6122_rx_width_join_compiled_objects"] = rx_width_join_object_audit
            if siga_627_patch:
                expected_siga_hal=rx629_sources["hal_rx.c"] if bw_trace_629_patch else NG.NATIVE_RX_628_HAL_SHA if siga_628_patch else NG.NATIVE_RX_627_HAL_SHA
                siga_overrides={"drivers/net/wireless/ath/ath11k/hal_rx.c":expected_siga_hal}
                if bw_trace_629_patch: siga_overrides["drivers/net/wireless/ath/ath11k/dp_rx.c"]=rx629_sources["dp_rx.c"]
                if args.tx_coherent_diag: siga_overrides["drivers/net/wireless/ath/ath11k/dp.c"]=rx_overrides["drivers/net/wireless/ath/ath11k/dp.c"]
                manifest["qcn6122_vht_siga_627_628_compiled_objects"]=NG.verify_native_rx_627_628_objects(
                    backport_configs[0].parent,backport_configs[0],autoconf,
                    mac80211_started_ns,evidence/"build.log",expected_hal_sha=expected_siga_hal,
                    diagnostic_628=bool(siga_628_patch),diagnostic_629=bool(bw_trace_629_patch),
                    source06=source06_selected,source07=source07_selected,source08=sta_rxrate_display_selected,
                    compiled_source_overrides=siga_overrides)
                if bw_trace_629_patch:
                    rx629_overrides={"core.c":NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/core.c"],"Makefile":NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/Makefile"]} if dhcp_tx_diag_patch else None
                    if sta_rxrate_display_selected:
                        rx629_overrides=None
                    manifest["qcn6122_bw_trace_629_compiled_objects"]=NG.verify_native_rx_629_objects(
                        backport_configs[0].parent,mac80211_started_ns,evidence/"build.log",compiled_source_overrides=rx629_overrides,source06=source06_selected,source07=source07_selected,source08=sta_rxrate_display_selected)
                    unstripped_ath11k=backport_configs[0].parent/"drivers/net/wireless/ath/ath11k/ath11k.ko"
                    final_link=NG.verify_native_rx_629_link(
                        backport_configs[0].parent,unstripped_ath11k,mac80211_started_ns)
                    final_link.update({"unstripped_module_path":str(unstripped_ath11k),
                        "unstripped_module_sha256":sha(unstripped_ath11k),
                        "packaged_module_path":str(modules[0]),
                        "packaged_module_sha256":sha(modules[0]),
                        "allocated_elf_binding_report":"ath11k-symbol-audit.json"})
                    manifest["qcn6122_bw_trace_629_final_link"]=final_link
                    if sta_rxrate_display_selected:
                        ath11k_dir=backport_configs[0].parent/"drivers/net/wireless/ath/ath11k"
                        manifest["qcn6122_sta_rxrate_display_compiled_objects"]=NG.verify_native_rx_sta_rxrate_objects(
                            backport_configs[0].parent,mac80211_started_ns,evidence/"build.log",
                            e07_core_sha=NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/core.c"])
                        manifest["qcn6122_sta_rxrate_display_source_policy"]=NG.validate_native_rx_sta_rxrate_source_policy(
                            ath11k_dir,e07_core_sha=NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/core.c"])
                        manifest["qcn6122_sta_rxrate_display_final_link_elf"]=NG.verify_native_rx_sta_rxrate_elf(unstripped_ath11k)
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        reo_source = backport_configs[0].parent / "drivers/net/wireless/ath/ath11k/dp_rx.c"
        if args.reo_idr_claim:
            expected_rx_source = (rx629_sources["dp_rx.c"]
                                  if bw_trace_629_patch else
                                  "2732ef10d06871d6ad203312fba9ba90501410fb3d576f45bdd199f6a319e1c2"
                                  if args.qcn6122_rx_identity_coverage else
                                  "4b9688111d8db4d9f51173b22e1981a59bc1412baf96da8e97bc156c950f860e"
                                  if identity_patch.is_file() else
                                  "c4e15c4deceebaad587b1a822b4ca3e498134371d5c8e783fd295da934b6f786"
                                  if args.ipq5018_rx_provenance_trace else
                                  "d8c25ef6364a0df9045968dd43aef7db9cd45b21e0d919209d4f0d643c0df3e5"
                                  if args.qcn6122_vht_siga_trace else
                                  "90b86324358f74a3f351378256a05d0b97fb03fa2b44fd9ff869af4a77aa5023")
            actual_rx_source = sha(reo_source)
            if actual_rx_source != expected_rx_source:
                raise ValueError("combined post-611 RX diagnostic dp_rx.c source hash mismatch")
            if args.qcn6122_rx_identity_coverage:
                coverage_source = reo_source.read_text()
                coverage_gates = {
                    "issue_quota_16": "#define ATH11K_QCN6122_RX_ID_QUOTA_ISSUE 16" in coverage_source,
                    "bw3_probe_quota_4": "#define ATH11K_QCN6122_RX_ID_QUOTA_BW3 4" in coverage_source,
                    "normal_control_quota_4": "#define ATH11K_QCN6122_RX_ID_QUOTA_CONTROL 4" in coverage_source,
                    "reo_observation_cap_262144": "#define ATH11K_QCN6122_RX_ID_MAX_REO_OBSERVATIONS 262144" in coverage_source,
                    "window_30_seconds": "#define ATH11K_QCN6122_RX_ID_WINDOW (30 * HZ)" in coverage_source,
                    "raw_msdu_start_9_words_36_bytes": "__le32 words[9];" in coverage_source and "FIELD_GET(HAL_TLV_HDR_LEN, tag) != sizeof(words)" in coverage_source and "sizeof(desc->msdu_start) != sizeof(words)" in coverage_source,
                    "drop_rejected_or_truncated_raw_rows": "!ath11k_qcn6122_rx_id_diag_make_raw_msdu_start(" in coverage_source and "raw[0] = 0;" in coverage_source,
                    "attention_info1_requires_12_byte_role": "FIELD_GET(HAL_TLV_HDR_LEN, snap->tags[1]) == sizeof(*attention)" in coverage_source,
                    "default_off_mode_0600": bool(re.search(r"static bool ath11k_qcn6122_rx_id_diag_enable;", coverage_source)) and bool(re.search(r"module_param_cb\(qcn6122_rx_identity_diag,.*?0600\);", coverage_source, re.S)),
                }
                if not all(coverage_gates.values()):
                    raise ValueError(f"621 coverage source gates failed: {coverage_gates}")
                manifest["qcn6122_rx_identity_coverage_compiled_source"] = {
                    "dp_rx.c_sha256": actual_rx_source,
                    "patch_sha256": coverage_patch_sha,
                    "same_C_QCN6122_scope_default_off_0600": True,
                    "issue_quota": 16, "bw3_probe_quota": 4,
                    "normal_control_quota": 4,
                    "reo_observation_cap": 262144, "window_seconds": 30,
                    "raw_msdu_start_body_bytes": 9 * 4,
                    "source_gates": coverage_gates,
                    "patch_policy_gates": coverage_patch_gates,
                }
            if args.qcn6122_vht_siga_trace:
                ath11k_dir = backport_configs[0].parent / "drivers/net/wireless/ath/ath11k"
                expected_hal_rx = (rx629_sources["hal_rx.c"] if bw_trace_629_patch else
                                   NG.NATIVE_RX_628_HAL_SHA if siga_628_patch else
                                   NG.NATIVE_RX_627_HAL_SHA if siga_627_patch else
                                   QCN6122_PPDU_TS_HAL_RX_SHA256 if ppdu_ts_patch else
                                   NG.NATIVE_RX_625_HAL_SHA if args.qcn6122_rx_width_join else
                                   "95f7dda3809e83d91cb72943ccb0391c8fc491cb9b535ed16e3779ede38c4393" if args.qcn6122_phy_width_trace else
                                   "115d18469af4eaaa92d8bdd472bfe0d54c31ec343a173f9a81d24563cfd927f8")
                expected_files = {"hal_rx.c": expected_hal_rx,
                                  "hal_rx.h": (rx629_sources["hal_rx.h"] if bw_trace_629_patch else
                                                "6c12a9ea8adcabd309ca2c2f586990bc9b03d1e1afe05d1366a33e9786f9b207")}
                actual_files = {name: sha(ath11k_dir / name) for name in expected_files}
                if actual_files != expected_files:
                    raise ValueError(f"615 compiled source hash mismatch: {actual_files}")
                policy_header = ath11k_dir / "qcn6122_vht_siga_trace_policy.h"
                if sha(policy_header) != "bf79df9e8fdaa39cd3e6a34a2e00e1c906e92d55af9400eec4d571057b30b188":
                    raise ValueError("615 compiled policy header hash mismatch")
                source = (ath11k_dir / "hal_rx.c").read_text()
                if not re.search(r"static bool ath11k_qcn6122_vht_siga_trace_enable;", source) or not re.search(r"module_param_cb\(qcn6122_vht_siga_trace,.*?0600\);", source, re.S):
                    raise ValueError("615 default-off, mode-0600 module parameter source gate missing")
                if siga_627_patch:
                    siga_source_gates=NG.validate_native_rx_628_source_policy(source) if siga_628_patch else NG.validate_native_rx_627_source_policy(source)
                    manifest["qcn6122_vht_siga_627_628_source_policy"]={"hal_rx.c_sha256":expected_hal_rx,"gates":siga_source_gates,"width_classification":"DIAGNOSTIC_ONLY"}
                if bw_trace_629_patch:
                    rx629_overrides={"core.c":NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/core.c"],"Makefile":NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/Makefile"]} if dhcp_tx_diag_patch else None
                    if sta_rxrate_display_selected:
                        rx629_overrides=None
                        bw629_gates={"source07_composed_semantics":NG.validate_native_rx_629_source07_policy(ath11k_dir,source08=True),
                            "source08_final":NG.validate_native_rx_sta_rxrate_source_policy(
                                ath11k_dir,e07_core_sha=NG.NATIVE_DHCP_TX_DIAG_POSTIMAGES["drivers/net/wireless/ath/ath11k/core.c"])}
                    else:
                        bw629_gates=(NG.validate_native_rx_629_source07_policy(ath11k_dir,compiled_source_overrides=rx629_overrides) if source07_selected else
                                 NG.validate_native_rx_629_source06_policy(ath11k_dir,compiled_source_overrides=rx629_overrides) if source06_selected else
                                 NG.validate_native_rx_629_source_policy(ath11k_dir))
                    manifest["qcn6122_bw_trace_629_source_policy"]={
                        "gates":bw629_gates,"source_sha256":{**rx629_sources,**(rx629_overrides or {})},
                        "capture":("source08 opts in to peer-specific station_info.rxrate display only; packet RX status/delivery and width decoder remain unchanged" if sta_rxrate_display_selected else "bounded metadata timing only; no packet/rate/width/filter changes"),
                        "static_event_storage_bound":("40 KiB ring + 40 KiB snapshot logical arrays; other bounded overhead excluded" if source_v2_selected else "32 KiB logical event ring; other bounded overhead excluded"),
                        "failed_start_lifecycle":"terminal DEAD; diagnostic controls unavailable until reprobe"}
                manifest["qcn6122_vht_siga_compiled_sources"] = {"dp_rx.c": actual_rx_source, **actual_files, "qcn6122_vht_siga_trace_policy.h": sha(policy_header)}
                if args.qcn6122_phy_width_trace:
                    source = ath11k_dir / "hal_rx.c"
                    source_text = source.read_text()
                    source_gates = {
                        "default_off_mode_0600": bool(re.search(r"static bool ath11k_qcn6122_rssi_legacy_trace_enable;", source_text)) and bool(re.search(r"module_param_cb\(qcn6122_rssi_legacy_trace,.*?0600\);", source_text, re.S)),
                        "C_QCN6122_runtime_scope": "ATH11K_HW_QCN6122" in source_text and 'of_machine_is_compatible("h3c,rt3000-rtl8367s")' in source_text and "READ_ONCE(ath11k_qcn6122_rssi_legacy_trace_enable)" in source_text,
                        "sixteen_sample_bound": "atomic_t ath11k_qcn6122_rssi_legacy_trace_remaining = ATOMIC_INIT(16)" in source_text and "atomic_dec_if_positive" in source_text,
                        "allocated_skb_capacity_and_header_bounds": "skb_end_pointer(skb)" in source_text and "skb->len + skb_tailroom(skb)" in source_text and "header_bounds_valid" in source_text,
                        "independent_dword_length_and_buffer_bounds": all(x in source_text for x in ("word0_len_valid", "word0_bounds_valid", "word35_len_valid", "word35_bounds_valid", "word36_len_valid", "word36_bounds_valid")),
                        "same_mac_parser_context_and_no_join_claim": "parser_mac_match = ppdu_info->qcn6122_vht_siga_mac_id == mac_id" in source_text and "parser_context_valid = parser_start_seen && parser_mac_match" in source_text and "same_ppdu_join_asserted=0" in source_text,
                    }
                    if not all(source_gates.values()):
                        raise ValueError(f"622 compiled source policy gates failed: {source_gates}")
                    phy_object = ath11k_dir / "hal_rx.o"
                    phy_command = ath11k_dir / ".hal_rx.o.cmd"
                    if not phy_object.is_file() or not phy_command.is_file():
                        raise ValueError("622 hal_rx.c source/object command evidence is incomplete")
                    command_text = phy_command.read_text(errors="replace")
                    if "hal_rx.c" not in command_text or "hal_rx.o" not in command_text:
                        raise ValueError("622 hal_rx.o command does not bind the selected source/object")
                    manifest["qcn6122_phy_width_trace_compiled_source"] = {
                        "hal_rx.c_sha256": actual_files["hal_rx.c"],
                        "hal_rx.h_sha256": actual_files["hal_rx.h"],
                        "patch_sha256": phy_width_patch_sha,
                        "hal_rx.o_sha256": sha(phy_object),
                        "hal_rx.o_command_sha256": sha(phy_command),
                        "command_mentions_source_and_object": True,
                        "source_gates": source_gates,
                        "default_off_mode_0600": True,
                        "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_QCN6122",
                        "sample_cap": 16, "parser_join_asserted": False,
                        "runtime_validation": "NOT_EXECUTED"}
            if args.ipq5018_reo_coherent:
                combined_tx_rx_policy = None
                dp_source = backport_configs[0].parent / "drivers/net/wireless/ath/ath11k/dp.c"
                dp_text = dp_source.read_text()
                expected_dp = (NG.NATIVE_TX_623_624_SOURCES["drivers/net/wireless/ath/ath11k/dp.c"]
                               if args.tx_coherent_diag else
                               "1e30667eefd4d70612edb3f5949d7395e867070bfdde52d63c862ca6b1119993"
                               if args.qcn6122_rx_rings_coherent else
                               "cf9060e854a0d85b25215a4dc354df68850a4416bcd27130cc3600a728b08e19"
                               if args.ipq5018_wbm_rx_coherent else
                               "b4eb71eafb877bcdc2f1167914f70390dd59452dff72b74702b393a8c1ba8844")
                if sha(dp_source) != expected_dp:
                    raise ValueError("selected 617/618/620/623/624 compiled dp.c source hash mismatch")
                if args.qcn6122_rx_rings_coherent and args.tx_coherent_diag:
                    combined_tx_rx_policy = NG.validate_native_tx_623_624_source_policy(
                        dp_text, (dp_source.parent / "dp_tx.c").read_text(),
                        (dp_source.parent / "Kconfig").read_text())
                elif args.qcn6122_rx_rings_coherent:
                    coherent_scope = (r"if\s*\(\(\s*type\s*==\s*HAL_REO_DST\s*\|\|\s*"
                                      r"\(\s*type\s*==\s*HAL_WBM2SW_RELEASE\s*&&\s*ring_num\s*==\s*3\s*\)\s*\)\s*&&\s*"
                                      r"\(\s*ab->hw_rev\s*==\s*ATH11K_HW_IPQ5018\s*\|\|\s*"
                                      r"ab->hw_rev\s*==\s*ATH11K_HW_QCN6122\s*\)\s*&&\s*"
                                      r'of_machine_is_compatible\("h3c,rt3000-rtl8367s"\)\)\s*\{[^}]*?'
                                      r"cached\s*=\s*false\s*;[^}]*?ring->cached\s*=\s*0\s*;")
                elif args.ipq5018_wbm_rx_coherent:
                    coherent_scope = (r"if\s*\(\(\s*type\s*==\s*HAL_REO_DST\s*\|\|\s*"
                                      r"\(\s*type\s*==\s*HAL_WBM2SW_RELEASE\s*&&\s*ring_num\s*==\s*3\s*\)\s*\)\s*&&\s*"
                                      r"ab->hw_rev\s*==\s*ATH11K_HW_IPQ5018\s*&&\s*"
                                      r'of_machine_is_compatible\("h3c,rt3000-rtl8367s"\)\)\s*\{[^}]*?'
                                      r"cached\s*=\s*false\s*;[^}]*?ring->cached\s*=\s*0\s*;")
                    if "HAL_REO_DST" not in dp_text or not re.search(r"HAL_WBM2SW_RELEASE\s*&&\s*ring_num\s*==\s*3", dp_text):
                        raise ValueError("618 WBM RX scope is not limited to release ring 3 alongside the retained REO scope")
                else:
                    coherent_scope = (r"if\s*\(type\s*==\s*HAL_REO_DST\s*&&\s*"
                                      r"ab->hw_rev\s*==\s*ATH11K_HW_IPQ5018\s*&&\s*"
                                      r'of_machine_is_compatible\("h3c,rt3000-rtl8367s"\)\)\s*\{[^}]*?'
                                      r"cached\s*=\s*false\s*;[^}]*?ring->cached\s*=\s*0\s*;")
                if not (args.qcn6122_rx_rings_coherent and args.tx_coherent_diag) and not re.search(coherent_scope, dp_text, re.S):
                    raise ValueError("617/618/620 C/IPQ5018 coherent allocation scope or cached=0 gate missing")
                if not re.search(r"if\s*\(!cached\)\s*\{\s*ring->vaddr_unaligned\s*=\s*dma_alloc_coherent\(", dp_text, re.S):
                    raise ValueError("617 REO ring does not use the coherent allocator")
                if not re.search(r"if\s*\(!ring->cached\)\s*dma_free_coherent\(", dp_text, re.S):
                    raise ValueError("617 REO ring coherent free lifecycle is incomplete")
                manifest["ipq5018_reo_coherent_compiled_source"] = {
                    "dp.c_sha256": expected_dp,
                    "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_IPQ5018 + HAL_REO_DST",
                    "ring_cached_forced_zero": True,
                    "coherent_allocator_gate_verified": True,
                    "dma_free_coherent_lifecycle_verified": True,
                    "ownership_mismatch_evidence": "ACTUAL16REORECORDS_CONFIRMED",
                    "root_cause": "CACHE_COHERENCE_HYPOTHESIS_NOT_YET_PROVEN",
                    "runtime_validation": "NOT_EXECUTED"}
                if args.ipq5018_wbm_rx_coherent:
                    manifest["ipq5018_wbm_rx_coherent_compiled_source"] = {
                        "dp.c_sha256": expected_dp,
                        "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_IPQ5018 + HAL_WBM2SW_RELEASE ring_num=3; retains HAL_REO_DST scope",
                        "ring_cached_forced_zero": True,
                        "coherent_allocator_gate_verified": True,
                        "dma_free_coherent_lifecycle_verified": True,
                        "wbm_reject_evidence": "REPEATED_RING109_ZERO_INFO_COOKIE_SOURCE",
                        "root_cause": "CACHE_VISIBILITY_HYPOTHESIS_NOT_YET_PROVEN",
                        "runtime_validation": "NOT_EXECUTED"}
                if args.qcn6122_rx_rings_coherent:
                    dp_object = dp_source.parent / "dp.o"
                    dp_command = dp_source.parent / ".dp.o.cmd"
                    if not dp_object.is_file() or not dp_command.is_file():
                        raise ValueError("620 dp.c source/object command binding is incomplete")
                    command_text = dp_command.read_text()
                    if "dp.c" not in command_text or "dp.o" not in command_text:
                        raise ValueError("620 dp.c source/object command binding is incomplete")
                    manifest["qcn6122_rx_rings_coherent_compiled_source"] = {
                        "dp.c_sha256": expected_dp,
                        "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_IPQ5018 or ATH11K_HW_QCN6122; HAL_REO_DST and HAL_WBM2SW_RELEASE ring_num=3",
                        "combined_tx_rx_policy": combined_tx_rx_policy,
                        "TX_ring_scope": bool(args.tx_coherent_diag),
                        "selected_coherent_scopes": (["HAL_REO_DST", "HAL_WBM2SW_RELEASE ring_num=3",
                                                       "HAL_WBM2SW_RELEASE TX rings 0-2"]
                                                      if args.tx_coherent_diag else
                                                      ["HAL_REO_DST", "HAL_WBM2SW_RELEASE ring_num=3"]),
                        "ring_cached_forced_zero": True,
                        "coherent_allocator_gate_verified": True,
                        "dma_free_coherent_lifecycle_verified": True,
                        "dp.o_sha256": sha(dp_object),
                        "dp.o_command_sha256": sha(dp_command),
                        "command_mentions_dp_source_and_object": True,
                        "mac80211_clean_before_build": True,
                        "causal_status": "CORRECTNESS_HYPOTHESIS_NOT_PROVEN",
                        "runtime_validation": "NOT_EXECUTED"}
            if args.ipq5018_rx_provenance_trace:
                source_text = reo_source.read_text()
                expected_param = (r"static bool ath11k_ipq5018_rx_layout_diag_enable;\s*"
                                  r"module_param_named\(ipq5018_rx_layout_diag,\s*"
                                  r"ath11k_ipq5018_rx_layout_diag_enable,\s*bool,\s*0600\);")
                if not re.search(expected_param, source_text, re.S):
                    raise ValueError("616 default-off mode-0600 module parameter source gate missing")
                if ("ATH11K_HW_IPQ5018" not in source_text or
                        'of_machine_is_compatible("h3c,rt3000-rtl8367s")' not in source_text or
                        "READ_ONCE(ath11k_ipq5018_rx_layout_diag_enable)" not in source_text):
                    raise ValueError("616 C/IPQ5018 runtime scope source gate missing")
                manifest["ipq5018_rx_provenance_compiled_source_sha256"] = actual_rx_source
                manifest["ipq5018_rx_provenance_default_off_source_gate"] = {
                    "module_parameter": "ipq5018_rx_layout_diag",
                    "default": False, "mode": "0600",
                    "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_IPQ5018 + MON_OWNER_DIAG",
                    "quotas": {"reo_control": 4, "reo_issue": 16,
                               "process_control": 4, "process_issue": 16},
                    "source_sha256": actual_rx_source
                }
            if args.qcn6122_rx_identity_diag:
                text = reo_source.read_text()
                declared = re.search(r"static bool ath11k_qcn6122_rx_id_diag_enable;", text)
                param = re.search(r"module_param_cb\(qcn6122_rx_identity_diag,.*?0600\);", text, re.S)
                if not declared or not param:
                    raise ValueError("619 default-off mode-0600 identity parameter missing")
                if ("ATH11K_HW_QCN6122" not in text or
                        'of_machine_is_compatible("h3c,rt3000-rtl8367s")' not in text or
                        "READ_ONCE(ath11k_qcn6122_rx_id_diag_enable)" not in text):
                    raise ValueError("619 QCN6122/C runtime scope gate missing")
                manifest["qcn6122_rx_identity_diag_source_gate"] = {
                    "source_sha256": actual_rx_source, "default": False, "mode": "0600",
                    "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_QCN6122",
                    "quotas": {"reo_control": 4, "reo_issue": 16,
                               "process_control": 4, "process_issue": 16},
                    "window_seconds": 30, "reo_observation_cap": (262144 if args.qcn6122_rx_identity_coverage else 4096)}
                if args.qcn6122_rx_identity_coverage:
                    manifest["qcn6122_rx_identity_diag_source_gate"]["quotas"].update(
                        {"reo_bw3_probe": 4, "process_bw3_probe": 4})
            manifest["reo_idr_dp_rx_sha256"] = actual_rx_source
            manifest["rx_trace_default_off_source_gate"] = {
                "module_parameter": "qcn6122_rx_bw_trace",
                "default": False,
                "scope": "h3c,rt3000-rtl8367s + ATH11K_HW_QCN6122",
                "max_records": 16,
                "source_sha256": actual_rx_source
            }
        # Save matching symbols before a later OFF build replaces the cache.
        unstripped = backport_configs[0].parent / "drivers/net/wireless/ath/ath11k/ath11k.ko"
        if not unstripped.is_file():
            raise ValueError("missing unstripped ath11k module")
        shutil.copy(unstripped, evidence / "ath11k-unstripped.ko")
        subprocess.run([sys.executable, str(ROOT / "rt3000-machine-c/tools/audit_ath11k_symbols.py"),
                        "--packaged", str(modules[0]), "--unstripped", str(unstripped),
                        "--output", str(evidence / "ath11k-symbol-audit.json")], check=True)
        if bw_trace_629_patch:
            symbol_report=evidence/"ath11k-symbol-audit.json"
            binding=json.loads(symbol_report.read_text())
            link=manifest["qcn6122_bw_trace_629_final_link"]
            if (binding.get("packaged_sha256")!=link["packaged_module_sha256"] or
                    binding.get("unstripped_sha256")!=link["unstripped_module_sha256"] or
                    binding.get("code_data_sections_match") is not True):
                raise ValueError("629 packaged/unstripped allocated ELF binding mismatch")
            link["packaged_unstripped_allocated_elf_binding"]={
                "report_path":str(symbol_report),"report_sha256":sha(symbol_report),
                "packaged_sha256":binding["packaged_sha256"],
                "unstripped_sha256":binding["unstripped_sha256"],
                "code_data_sections_match":True,
                "allocated_sections_match_including_build_id":binding.get("allocated_sections_match"),
                "build_id_notes":binding.get("build_id_notes"),
                "allocated_section_count":len(binding.get("allocated_sections",{}))}
        if dhcp_tx_diag_patch:
            manifest["dhcp_tx_diag"]["module_binding"]=NG.verify_native_dhcp_tx_diag_module(
                unstripped,modules[0],evidence/"ath11k-symbol-audit.json")
            (evidence/"inputs.json").write_text(json.dumps(manifest,indent=2)+"\n")
        rootfs = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq50xx"
        if args.same_c_oem_fw_pas is None:
            manifest["ordinary_firmware_baseline_result"] = verify_firmware_snapshot(rootfs, ordinary_fw_baseline["files"])
            (evidence / "ordinary-firmware-baseline.json").write_text(json.dumps(manifest["ordinary_firmware_baseline_result"], indent=2) + "\n")
        if args.same_c_oem_fw_pas is not None:
            for item in manifest["same_c_oem_firmware"]["files"]:
                root_path = rootfs / "lib/firmware" / item["overlay_relative_to_firmware_root"]
                if (root_path.is_symlink() or not root_path.is_file() or
                        root_path.stat().st_size != item["bytes"] or sha(root_path) != item["sha256"]):
                    raise ValueError(f"same-C OEM firmware rootfs file mismatch: {item['overlay_relative_to_firmware_root']}")
            if sha(rootfs / "lib/firmware/ath11k/qcn6122/hw1.0/board-2.bin") != OEM_FW_BDF_SHA256:
                raise ValueError("same-C OEM firmware rootfs BDF is not exact 935")
            for rel, source_name in (("lib/firmware/ath11k/IPQ5018/hw1.0/caldata.bin", "caldata-ipq5018.bin"),
                                     ("lib/firmware/ath11k/qcn6122/hw1.0/caldata_1.bin", "caldata-qcn6122.bin")):
                source_cal = ROOT / "package/firmware/rt3000-c-oem-wifi/files" / source_name
                root_cal = rootfs / rel
                if (not root_cal.is_file() or sha(root_cal) != OEM_CALDATA_SHA256[source_name] or
                        sha(source_cal) != OEM_CALDATA_SHA256[source_name]):
                    raise ValueError(f"same-C OEM experiment changed local ART calibration: {rel}")
        if args.same_c_oem_fw_pas is not None:
            q6_source = tree / "build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5/drivers/remoteproc/qcom_q6v5_mpd.c"
            expected_q6 = OEM_PAS_POST_SHA256 if args.same_c_oem_fw_pas == 6 else OEM_PAS_BASE_SHA256
            if sha(q6_source) != expected_q6:
                raise ValueError("built kernel Q6 source does not match selected stock PAS13/PAS6 mode")
            shutil.copyfile(q6_source, evidence / "qcom_q6v5_mpd.c")
            kernel_dir = q6_source.parents[2]
            q6_object = kernel_dir / "drivers/remoteproc/qcom_q6v5_mpd.o"
            vmlinux = kernel_dir / "vmlinux"
            if q6_object.stat().st_mtime_ns < manifest["same_c_oem_pas"]["q6_source_mtime_ns_before_build"]:
                raise ValueError("compiled Q6 object freshness check failed")
            shutil.copyfile(q6_object, evidence / "qcom_q6v5_mpd.o")
            manifest["same_c_oem_pas"]["compiled_source_sha256"] = sha(q6_source)
            manifest["same_c_oem_pas"]["q6_object_sha256"] = sha(q6_object)
            manifest["same_c_oem_pas"]["q6_object_mtime_ns"] = q6_object.stat().st_mtime_ns
            manifest["same_c_oem_pas"]["vmlinux_sha256"] = sha(vmlinux)
            manifest["same_c_oem_pas"]["matched_pair"] = "NOT_GENERATED; compare separately frozen PAS13/PAS6 FIT kernel and CPIO bytes before claiming matched control"
            (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (evidence / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
        audit_cmd = [sys.executable, str(ROOT / "rt3000-machine-c/tools/audit_ram_fit.py"),
                     str(evidence / fit.name), str(evidence / "fit-audit"), "--module", str(modules[0]),
                     "--kernel-marker", "realtek,rt3000-unicast-offload"]
        if args.dual_phy_no_tx:
            audit_cmd.append("--dual-phy")
        if args.same_c_oem_fw_pas is not None:
            audit_cmd += ["--same-c-oem-fw-pas", str(args.same_c_oem_fw_pas)]
        if args.monitor_owner_diag:
            audit_cmd += ["--module-marker", "mon-owner first-mismatch",
                          "--module-marker", "rx-warning metadata"]
        if args.qcn6122_vht_siga_trace:
            audit_cmd += ["--module-marker", "qcn6122_vht_siga_trace"]
        if args.ipq5018_rx_provenance_trace:
            audit_cmd += ["--module-marker", "ipq5018_rx_layout_diag"]
        if args.qcn6122_rx_identity_diag:
            audit_cmd += ["--module-marker", "qcn6122_rx_identity_diag"]
        if args.qcn6122_rx_identity_coverage:
            audit_cmd += ["--module-marker", "qcn6122-rx-identity stage=reo-msdu-start",
                          "--module-marker", "qcn6122-rx-identity stage=stop"]
        if args.qcn6122_phy_width_trace:
            audit_cmd += ["--module-marker", "qcn6122-rssi-legacy-622 sample="]
        if bw_trace_629_patch:
            audit_cmd += ["--module-marker", "MON_DP_DONE", "--module-marker", "REO_FAST_DELIVER"]
            if source_v2_selected:
                audit_cmd += ["--module-marker", "rt3000c-ram629-trace-v2", "--module-marker", "REO_INFO3_EARLY"]
        if not args.monitor_owner_diag and any(marker in modules[0].read_bytes() for
                marker in (b"mon-owner mismatch", b"mon-owner first-mismatch",
                           b"rx-warning metadata")):
            raise ValueError("diagnostic code unexpectedly present in non-diagnostic build")
        with (evidence / "fit-audit.log").open("w") as stream:
            subprocess.run(audit_cmd, stdout=stream, stderr=subprocess.STDOUT, check=True)
        dtb = evidence / "fit-audit/fdt.dtb"
        switch_nodes = []
        tlmm_nodes = []
        def visit(node):
            children = subprocess.check_output(["fdtget", "-l", str(dtb), node], text=True).splitlines()
            for child in children:
                path = node.rstrip("/") + "/" + child
                if child == "switch@1d":
                    switch_nodes.append(path)
                properties = subprocess.check_output(["fdtget", "-p", str(dtb), path], text=True).splitlines()
                if "gpio-controller" in properties:
                    try:
                        compatible = subprocess.check_output(["fdtget", "-t", "s", str(dtb), path, "compatible"], text=True)
                    except subprocess.CalledProcessError:
                        compatible = ""
                    if "qcom,ipq5018-pinctrl" in compatible.split():
                        tlmm_nodes.append(path)
                visit(path)
        visit("/")
        if len(switch_nodes) != 1:
            raise ValueError(f"unexpected compiled switch nodes: {switch_nodes}")
        properties = subprocess.check_output(["fdtget", "-p", str(dtb), switch_nodes[0]], text=True).splitlines()
        selected = "realtek,rt3000-unicast-offload" in properties
        if selected != args.switch_unicast_offload:
            raise ValueError("compiled FIT switch offload property differs from requested mode")
        if args.native_switch_reset:
            if len(tlmm_nodes) != 1:
                raise ValueError(f"compiled DTB has unexpected TLMM GPIO controller nodes: {tlmm_nodes}")
            reset_cells = subprocess.check_output(
                ["fdtget", "-t", "x", str(dtb), switch_nodes[0], "reset-gpios"],
                text=True).split()
            tlmm_phandle = subprocess.check_output(
                ["fdtget", "-t", "x", str(dtb), tlmm_nodes[0], "phandle"],
                text=True).split()
            if len(reset_cells) != 3 or len(tlmm_phandle) != 1 or [int(x, 16) for x in reset_cells] != [int(tlmm_phandle[0], 16), 39, 1]:
                raise ValueError(f"compiled FIT reset-gpios is not <&tlmm 39 GPIO_ACTIVE_LOW>: {reset_cells}")
        (evidence / "switch-dt-audit.json").write_text(json.dumps({
            "fdt_sha256": sha(dtb), "node": switch_nodes[0],
            "unicast_offload_selected": selected,
            "native_switch_reset_selected": args.native_switch_reset,
            "reset_gpio_cells_verified": [reset_cells if args.native_switch_reset else None][0],
            "hardware_validation": "NOT_EXECUTED"}, indent=2) + "\n")
        (evidence / "artifact.json").write_text(json.dumps({"fit": fit.name, "size": fit.stat().st_size, "sha256": sha(fit), "inputs_sha256": sha(evidence / "inputs.json"), "fit_audit_sha256": sha(evidence / "fit-audit/audit.json"), "kernel_config_sha256": sha(evidence / "kernel.config"), "bridge_vlan_filtering": actual_vlan_filtering, "monitor_owner_diag": args.monitor_owner_diag,
                "reo_idr_claim": args.reo_idr_claim, "qcn6122_vht_siga_trace": args.qcn6122_vht_siga_trace, "ipq5018_rx_provenance_trace": args.ipq5018_rx_provenance_trace, "ipq5018_reo_coherent": args.ipq5018_reo_coherent, "ipq5018_wbm_rx_coherent": args.ipq5018_wbm_rx_coherent, "qcn6122_rx_identity_diag": args.qcn6122_rx_identity_diag, "qcn6122_rx_identity_coverage": args.qcn6122_rx_identity_coverage, "qcn6122_rx_rings_coherent": args.qcn6122_rx_rings_coherent, "qcn6122_phy_width_trace": args.qcn6122_phy_width_trace,
                "qcn6122_rx_width_join": args.qcn6122_rx_width_join,
                 "qcn6122_sta_rxrate_display_selected": sta_rxrate_display_selected,
                 "qcn6122_sta_rxrate_display_patch_sha256": NG.NATIVE_RX_STA_RXRATE_PATCH_SHA if sta_rxrate_patch else None,
                 "qcn6122_ppdu_ts_correlation": bool(ppdu_ts_patch),
                 "qcn6122_ppdu_ts_patch_sha256": QCN6122_PPDU_TS_PATCH_SHA256 if ppdu_ts_patch else None,
                 "qcn6122_ppdu_ts_post_hal_rx_sha256": QCN6122_PPDU_TS_HAL_RX_SHA256 if ppdu_ts_patch else None,
                 "qcn6122_vht_siga_627_selected": bool(siga_627_patch),
                 "qcn6122_vht_siga_627_patch_sha256": NG.NATIVE_RX_627_PATCH_SHA if siga_627_patch else None,
                 "qcn6122_vht_siga_627_actual_c_proof_sha256": siga_627_proof["sha256"] if siga_627_proof else None,
                 "qcn6122_vht_siga_627_actual_c_proof_path": siga_627_proof["source_path"] if siga_627_proof else None,
                 "qcn6122_vht_siga_627_post_hal_rx_sha256": NG.NATIVE_RX_627_HAL_SHA if siga_627_patch else None,
                 "qcn6122_vht_siga_628_selected": bool(siga_628_patch),
                 "qcn6122_vht_siga_628_patch_sha256": NG.NATIVE_RX_628_PATCH_SHA if siga_628_patch else None,
                 "qcn6122_vht_siga_628_post_hal_rx_sha256": NG.NATIVE_RX_628_HAL_SHA if siga_628_patch else None,
                 "qcn6122_vht_siga_cached_selection": cached_siga_selection,
                 "qcn6122_vht_siga_patch_sequence": siga_patch_sequence,
                "rx_width_classification": "DIAGNOSTIC_ONLY" if args.qcn6122_rx_width_join else None,
                "ssdk_phy_notify": args.ssdk_phy_notify, "same_c_oem_fw_pas": args.same_c_oem_fw_pas, "runtime_validation": "NOT_EXECUTED", "switch_unicast_offload": selected, "native_switch_reset": args.native_switch_reset, "switch_dt_audit_sha256": sha(evidence / "switch-dt-audit.json"), "same_c_oem_firmware_audit_sha256": sha(evidence / "fit-audit/audit.json") if args.same_c_oem_fw_pas is not None else None, "hardware_validation": "NOT_EXECUTED"}, indent=2) + "\n")
        print(f"Build PASS: {fit.name} {sha(fit)}", flush=True)


if __name__ == "__main__":
    main()
