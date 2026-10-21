#!/usr/bin/env python3
"""Build offline C native FIT + five-volume UBI; never opens MTD/device nodes."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIT_AUDIT = ROOT / "rt3000-machine-c/tools/audit_native_ubi_profile.py"
DTB_AUDIT = ROOT / "rt3000-machine-c/tools/audit_native_dtb.py"
TARGET, SLOT = 0x03100000, 0x02800000
PEB, PAGE, VID, DATA = 131072, 2048, 2048, 4096
LEB, IMAGE_SEQ, LOAD = PEB - DATA, 1932197556, 0x41208000
CONFIG = "config@mp03.1-c2"
ROOTFS_DATA_PEBS, ROOTFS_DATA_MAX_LEBS = 13, 61
MKFS_UBIFS_SHA256 = "de77d6d1b0ecea8591c29a0af41417246c4f9cbc21192baae18fea5acaf67572"
UBINIZE_SHA256 = "7eb9503535b82a7f8ad6c6d2d19016e567272e5b6341b2e100d794483015736c"
UBI_FORMAT = (
    (0, "kernel", "static", 50, 0),
    (1, "wifi_fw", "static", 50, 0),
    (2, "bt_fw", "static", 3, 0),
    (3, "ubi_rootfs", "dynamic", 153, 0),
    (4, "rootfs_data", "dynamic", ROOTFS_DATA_PEBS, 1),
)
FIRMWARE_SHA = {
    "wifi_fw": "717825ac26ad3f83472dc5c053fae8b9fbee2021388da98ee335e242f6800831",
    "bt_fw": "ba286468aa9ba35186c24f63911861d7a2a482ed37e7a56dd354f3dcbac5e0e2",
}

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def regular(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or path.is_symlink():
        raise ValueError("input must be a regular non-symlink file")
    return resolved

def make_its(kernel_lzma, dtb):
    q = json.dumps
    lines = [
        "/dts-v1/;", "/ {",
        '  description = "RT3000 C native persistent slot-1 candidate";',
        "  #address-cells = <1>;", "  images {",
        "    kernel-1 {",
        '      description = "C slot-1 Linux Image";',
        f"      data = /incbin/({q(str(kernel_lzma))});",
        '      type = "kernel"; arch = "arm"; os = "linux"; compression = "lzma";',
        f"      load = <0x{LOAD:08x}>; entry = <0x{LOAD:08x}>;",
        '      hash-1 { algo = "sha256"; };', "    };",
        "    fdt-c-native {",
        '      description = "RT3000 C native slot-1 FDT";',
        f"      data = /incbin/({q(str(dtb))});",
        '      type = "flat_dt"; arch = "arm"; compression = "none";',
        '      hash-1 { algo = "sha256"; };', "    };", "  };",
        "  configurations {", f'    default = "{CONFIG}";',
        f"    {CONFIG} {{",
        '      description = "Explicit C native configuration; APPSBL selection unproven";',
        '      kernel = "kernel-1"; fdt = "fdt-c-native";',
        "    };", "  };", "};", "",
    ]
    return "\n".join(lines)

def lzma_command(binary, image, output):
    # Match include/image-commands.mk Build/lzma: legacy 7-Zip LZMA stream.
    return [str(binary), "e", str(image), "-lc1", "-lp2", "-pb2", str(output)]

def write_ubinize_cfg(out, files):
    lines = []
    for vol_id, name, kind, reserved, autoresize in UBI_FORMAT:
        lines.extend([
            f"[vol-{vol_id}-{name}]", "mode=ubi", f"vol_id={vol_id}",
            f"vol_type={kind}", f"vol_name={name}", "vol_alignment=1",
            f"vol_size={reserved * LEB}",
            "image=" + str(files[name]),
        ])
        if autoresize:
            lines.append("vol_flags=autoresize")
        lines.append("")
    cfg = out / "ubinize.cfg"
    cfg.write_text("\n".join(lines))
    os.chmod(cfg, 0o600)
    return cfg

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("kernel_image", "dtb", "kernel_config", "rootfs_squashfs",
                 "wifi_fw", "bt_fw", "mkimage", "lzma", "mkfs_ubifs",
                 "ubinize", "output_dir"):
        ap.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    a = ap.parse_args()
    inputs = {n: regular(getattr(a, n)) for n in (
        "kernel_image", "dtb", "kernel_config", "rootfs_squashfs", "wifi_fw",
        "bt_fw", "mkimage", "lzma", "mkfs_ubifs", "ubinize")}
    if sha(inputs["mkfs_ubifs"]) != MKFS_UBIFS_SHA256:
        raise SystemExit("refuse unreviewed mkfs.ubifs binary")
    if sha(inputs["ubinize"]) != UBINIZE_SHA256:
        raise SystemExit("refuse unreviewed ubinize binary")
    uv = subprocess.run([str(inputs["ubinize"]), "-V"], capture_output=True, text=True)
    if uv.returncode or "mtd-utils) 2.1.2" not in uv.stdout + uv.stderr:
        raise SystemExit("refuse unexpected ubinize version")
    version = subprocess.run([str(inputs["mkfs_ubifs"]), "-V"],
                             capture_output=True, text=True)
    if version.returncode or "mtd-utils) 2.1.2" not in version.stdout + version.stderr:
        raise SystemExit("refuse unexpected mkfs.ubifs version")
    for name, digest in FIRMWARE_SHA.items():
        if sha(inputs[name]) != digest:
            raise SystemExit("refuse non-C-source firmware input: " + name)
    if inputs["rootfs_squashfs"].read_bytes()[:4] not in (b"hsqs", b"sqsh"):
        raise SystemExit("refuse rootfs input without SquashFS magic")
    out = a.output_dir.absolute()
    repo = ROOT.resolve()
    if out.exists() or out.is_symlink() or out == repo or repo in out.parents:
        raise SystemExit("refuse existing/unsafe output directory")
    dtb_audit = out.with_name(out.name + ".dtb-audit.json")
    subprocess.run([
        sys.executable, str(DTB_AUDIT), str(inputs["dtb"]), "--mode",
        "persistent", "--kernel-config", str(inputs["kernel_config"]),
        "--output", str(dtb_audit)], check=True, stdout=subprocess.DEVNULL)
    out.mkdir(parents=True, mode=0o700)
    os.chmod(out, 0o700)
    dtb_audit.replace(out / "dtb-audit.json")

    kernel_lzma = out / "kernel.Image.lzma"
    result = subprocess.run(
        lzma_command(inputs["lzma"], inputs["kernel_image"], kernel_lzma),
        capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("Image LZMA compression failed: " + result.stderr[-500:])
    os.chmod(kernel_lzma, 0o600)
    if kernel_lzma.stat().st_size > 50 * LEB:
        raise SystemExit("compressed Image exceeds kernel static-volume reservation")
    its = out / "native.its"
    its.write_text(make_its(kernel_lzma, inputs["dtb"]))
    os.chmod(its, 0o600)
    fit = out / "kernel.fit"
    result = subprocess.run([str(inputs["mkimage"]), "-f", str(its), str(fit)],
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("mkimage failed: " + result.stderr[-700:])
    os.chmod(fit, 0o600)

    empty_root = out / "empty-rootfs-data"
    empty_root.mkdir(mode=0o700)
    overlay = out / "rootfs_data.ubifs"
    mkfs = [
        str(inputs["mkfs_ubifs"]), "-m", str(PAGE), "-e", str(LEB),
        "-c", str(ROOTFS_DATA_MAX_LEBS), "-r", str(empty_root), "-F",
        "-o", str(overlay),
    ]
    result = subprocess.run(mkfs, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("mkfs.ubifs failed: " + result.stderr[-500:])
    os.chmod(overlay, 0o600)
    if overlay.stat().st_size != ROOTFS_DATA_PEBS * LEB:
        raise SystemExit("empty UBIFS initializer differs from pinned 13-PEB layout")

    files = {
        "kernel": fit, "wifi_fw": inputs["wifi_fw"], "bt_fw": inputs["bt_fw"],
        "ubi_rootfs": inputs["rootfs_squashfs"], "rootfs_data": overlay,
    }
    limits = {"kernel": 50, "wifi_fw": 50, "bt_fw": 3,
              "ubi_rootfs": 153, "rootfs_data": ROOTFS_DATA_PEBS}
    for name, path in files.items():
        if path.stat().st_size > limits[name] * LEB:
            raise SystemExit("volume exceeds reviewed reservation: " + name)
    cfg = write_ubinize_cfg(out, files)
    ubi = out / "c-native-slot1.ubi"
    ubinize = [
        str(inputs["ubinize"]),
        "-p", str(PEB), "-m", str(PAGE), "-s", str(PAGE), "-O", str(VID),
        "-e", "0", "-Q", "1932197556", "-o", str(ubi), str(cfg),
    ]
    result = subprocess.run(ubinize, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("ubinize failed: " + result.stderr[-700:])
    os.chmod(ubi, 0o600)
    if ubi.stat().st_size % PEB or ubi.stat().st_size > SLOT:
        raise SystemExit("UBI candidate violates inactive-slot capacity/alignment")
    audit = out / "native-ubi-audit.json"
    result = subprocess.run([
        sys.executable, str(FIT_AUDIT), str(ubi), "--sha256", sha(ubi),
        "--fit-config", CONFIG, "--strict-native-fit", "--native-overlay",
        "--output", str(audit)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("native FIT/UBI static audit failed: " +
                         result.stdout[-600:] + result.stderr[-600:])
    manifest = {
        "status": "NATIVE_C_IMAGE_STATIC_PASS",
        "profile": "Device/h3c_rt3000_rtl8367s_native_slot1",
        "kernel_input_kind": "raw OpenWrt KERNEL_NAME=Image before LZMA/FIT",
        "fit_sha256": sha(fit), "fit_bytes": fit.stat().st_size,
        "fit_config": CONFIG, "default_is_runtime_selection_evidence": False,
        "ubi_sha256": sha(ubi), "ubi_bytes": ubi.stat().st_size,
        "ubi_pebs": ubi.stat().st_size // PEB,
        "inputs": {n: {"sha256": sha(inputs[n]), "bytes": inputs[n].stat().st_size}
                   for n in ("kernel_image", "dtb", "kernel_config",
                             "rootfs_squashfs", "wifi_fw", "bt_fw")},
        "rootfs_data_ubifs": {
            "sha256": sha(overlay), "bytes": overlay.stat().st_size,
            "initial_reserved_pebs": ROOTFS_DATA_PEBS,
            "max_leb_count": ROOTFS_DATA_MAX_LEBS,
            "autoresize": True, "space_fixup": True,
        },
        "geometry": {"page": PAGE, "peb": PEB, "vid_offset": VID,
                     "data_offset": DATA, "ecc_strength": 4, "oob": 64},
        "physical_target": {"offset": TARGET, "size": SLOT, "end": TARGET + SLOT},
        "protected_original": {"offset": 0x00900000, "size": SLOT,
                               "end": 0x00900000 + SLOT},
        "same_unit_wifi_bt": True, "fresh_badblock_map_included": False,
        "flash_ready": False, "runtime_config_selection": "NOT_PROVEN",
        "rootfs_data_runtime_mount": "NOT_PROVEN",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(out / "manifest.json", 0o600)
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
