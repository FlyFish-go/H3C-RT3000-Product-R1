#!/usr/bin/env python3
import argparse,datetime,fcntl,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));import native_rx_gates as NG;import native_dsa_runtime_audit as NDA
R=Path(__file__).resolve().parents[2]; C=Path("<BUILDROOT>")
E=Path("<EVIDENCE>"); SEED=R/"configs/rt3000-c-2g-ram/full.config"
FINAL=NG.QCOM
PATCH={"422-mtd-qcom-c-diagnostic-readonly.patch":"a96ad0f777da1da7b45e5668583c3901841667dc78fb204703221b9dab801ae9","423-mtd-qcom-c-badblock-read-error.patch":"2f6cba16aa7c735ee6a235669f2f9a85c6d2bb8454da550c34ca4ac87facbc74","424-mtd-qcom-c-native-safe-config.patch":"8c3857e5329c4d83707a669d3229a901f44082a5637053b8aa0939f7f99a5380"}
PFX=("target/linux/ipq50xx/","target/linux/generic/","package/kernel/mac80211/","package/kernel/linux/","package/kernel/leds-rt3000-paired/","package/kernel/qca/qca-ssdk/","package/kernel/qca/qca-nss-dp/","package/firmware/rt3000-c-oem-wifi/","package/firmware/rt3000-c-mac-identity-ro/","package/firmware/rt3000-c-dsa-master/","package/kernel/button-hotplug/","package/network/services/hostapd/")
def H(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(a,c,l=None):
 f=open(l,"w") if l else None
 try:r=subprocess.run(a,cwd=c,stdout=f,stderr=subprocess.STDOUT if f else None).returncode
 finally:
  if f:f.close()
 if r:raise RuntimeError("failed "+str(a)+" log="+str(l))
def main():
 global E
 ap=argparse.ArgumentParser()
 ap.add_argument("--enable-c-native-rx-618",action="store_true")
 ap.add_argument("--enable-c-native-rx-620-621",action="store_true",help="explicitly select the pinned native C QCN6122 RX 620+621 profile")
 ap.add_argument("--enable-c-native-rx-620-621-622",action="store_true",help="explicitly select the pinned native C QCN6122 RX 620+621+622 diagnostic profile")
 ap.add_argument("--enable-c-native-rx-width-join",action="store_true",help="add pinned timestamp-only 625 correlation diagnostics; width classification remains DIAGNOSTIC_ONLY")
 ap.add_argument("--enable-c-native-ssdk-phy-notify",action="store_true",help="opt in to strict 0903 SSDK MDIO-bus PHY notifier mapping")
 ap.add_argument("--enable-c-native-tx-coherent-diag",action="store_true",help="opt in to pinned Native C TX coherent rings 623+624 and default-off diagnostics; requires RX 620+621+622")
 ap.add_argument("--c-qcn6122-axis-compat-432",action="store_true",help="explicitly select the pinned C axis-compatibility board-2 BDF")
 ap.add_argument("--evidence",type=Path,help="fresh evidence directory; required with --c-qcn6122-axis-compat-432")
 args=ap.parse_args()
 rx_profile=NG.select_native_rx_profile(args.enable_c_native_rx_618,args.enable_c_native_rx_620_621,args.enable_c_native_rx_620_621_622,args.enable_c_native_rx_width_join)
 if args.c_qcn6122_axis_compat_432 and args.evidence is None: raise RuntimeError("--c-qcn6122-axis-compat-432 requires a fresh --evidence directory")
 E=(args.evidence.expanduser().resolve() if args.evidence else E)
 if R.resolve()==E or R.resolve() in E.parents or C.resolve()==E or C.resolve() in E.parents: raise RuntimeError("evidence directory must be outside source and build trees")
 rx_patch_presence=NG.reject_unselected_native_rx_patches(R,rx_profile)
 tx_patch_presence=NG.reject_unselected_native_tx_patches(R,args.enable_c_native_tx_coherent_diag,rx_profile)
 ssdk_source_pins=NG.native_ssdk_source_gate(R,args.enable_c_native_ssdk_phy_notify)
 source_pins=NG.source_gate(R)
 native_led_source_pins=NG.native_led_source_gate(R)
 tx_source_pins=NG.native_tx_623_624_source_gate(R,rx_profile) if args.enable_c_native_tx_coherent_diag else None
 if rx_profile=="native-rx-620-621":rx_source_pins=NG.native_rx_620_621_source_gate(R)
 elif rx_profile=="native-rx-620-621-622":rx_source_pins=NG.native_rx_620_621_622_source_gate(R)
 elif rx_profile=="native-rx-620-621-622-625-width-join":rx_source_pins=NG.native_rx_625_source_gate(R)
 else:rx_source_pins=source_pins
 axis_bdf=NG.validate_axis_compat_432(R) if args.c_qcn6122_axis_compat_432 else None
 selected_bdf_sha=axis_bdf["selected_sha256"] if axis_bdf else NG.EXPECTED_FIRMWARE[NG.QCN_BOARD2_REL]
 bdf_profile="c-axis-compat-432" if axis_bdf else "oem-935"
 pas_inputs=NG.reject_active_pas_hooks(R,C)
 os.umask(0o077)
 if E.exists():raise RuntimeError("evidence exists; refuse overwrite")
 lock=(C/".c-ram-recipe.lock").open("r+");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cache_kdir=C/"build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5"
 NG.cache_source_gate(cache_kdir)
 E.mkdir(parents=True,mode=0o700)
 names=subprocess.check_output(["git","ls-files","-c","-o","--exclude-standard","-z"],cwd=R).decode().split("\0"); sums={}
 for n in sorted({x for x in names if x and x.startswith(PFX)}):
  s=R/n;d=C/n
  if not s.exists() and not s.is_symlink():continue
  same=(d.is_symlink() and os.readlink(d)==os.readlink(s)) if s.is_symlink() else (d.is_file() and not d.is_symlink() and H(s)==H(d))
  if not same:
   d.parent.mkdir(parents=True,exist_ok=True)
   if d.is_symlink():d.unlink()
   if s.is_symlink():
    if d.exists():d.unlink()
    d.symlink_to(os.readlink(s))
   else:shutil.copy2(s,d)
  sums[n]=H(s) if not s.is_symlink() else os.readlink(s)
 native=R/"rt3000-machine-c/native";shutil.copytree(native,C/"rt3000-machine-c/native",dirs_exist_ok=True,symlinks=True)
 for p in native.rglob("*"):
  if p.is_file():sums[p.relative_to(R).as_posix()]=H(p)
 native_dsa_overlay_audit=NG.verify_native_dsa_overlay(R,C)
 native_led_overlay_audit=NG.verify_native_led_overlay(R,C)
 pd=C/"target/linux/ipq50xx/patches"
 for n,d in PATCH.items():
  if H(pd/n)!=d:raise RuntimeError("patch sha mismatch "+n)
 if H(pd/"425-mtd-c-physical-map-write-guard.patch")!=NG.PINS["target/linux/ipq50xx/patches/425-mtd-c-physical-map-write-guard.patch"]:raise RuntimeError("425 patch pin mismatch")
 q=C/"build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5/drivers/mtd/nand/raw/qcom_nandc.c"
 if H(q)!=NG.QCOM:raise RuntimeError("cache qcom source is not exact post-425 C guard")
 metas=("tmp/info/.packageinfo-kernel_mac80211","tmp/info/.packageinfo-kernel_qca_qca-ssdk","tmp/info/.packageinfo-kernel_qca_qca-nss-dp","tmp/info/.targetinfo-ipq50xx","tmp/.packageinfo","tmp/.config-package.in","tmp/.targetinfo","tmp/.config-target.in")
 b=E/"metadata-before-refresh";b.mkdir(mode=0o700);old={}
 for n in metas:
  p=C/n
  if not p.is_file():raise RuntimeError("missing metadata "+n)
  d=b/n.replace("/","__");shutil.copy2(p,d);old[n]=H(d);p.unlink()
 run(["make","prepare-tmpinfo"],C,E/"prepare-tmpinfo.log")
 for n in metas:
  if not (C/n).is_file():raise RuntimeError("metadata refresh missing "+n)
 ti=(C/"tmp/.targetinfo").read_text(errors="replace")
 if any(x not in ti for x in ("h3c_rt3000_rtl8367s_native_slot1","h3c_rt3000_rtl8367s_installer_ram")):raise RuntimeError("native target metadata missing")
 pc=(C/"tmp/.config-package.in").read_text(errors="replace")
 if any(x not in pc for x in ("ATH11K_RT3000_MON_OWNER_DIAG","ATH11K_RT3000_REO_IDR_CLAIM","ATH11K_RT3000_TX_UNKNOWN_DIAG","PACKAGE_fstools","PACKAGE_ubi-utils","PACKAGE_rt3000-c-dsa-master")):raise RuntimeError("required package metadata missing")
 mods=list(C.glob("build_dir/target-*/root-ipq50xx/lib/modules"))
 if len(mods)!=1:raise RuntimeError("QCA module root ambiguous")
 qb=E/"qca-before";qb.mkdir(mode=0o700);oldq={}
 for n in ("qca-ssdk.ko","qca-nss-dp.ko"):
  fs=list(mods[0].glob("*/"+n))
  if len(fs)!=1:raise RuntimeError("prior module ambiguous "+n)
  shutil.copy2(fs[0],qb/n);oldq[n]=H(qb/n)
 removed=[]
 for pat in ("build_dir/target-*/linux-*/qca-ssdk-nohnat/qca-ssdk-*","build_dir/target-*/linux-*/qca-nss-dp-*"):
  ds=list(C.glob(pat))
  if len(ds)!=1:raise RuntimeError("QCA build dir ambiguous "+pat)
  for p in list(ds[0].glob(".configured*"))+list(ds[0].glob(".built*")):
   if p.is_file():p.unlink();removed.append(str(p.relative_to(C)))
 for n in (".config","target/linux/ipq50xx/config-5.4"):
  if (C/n).is_file():shutil.copy2(C/n,E/("prior-"+n.replace("/","__")))
 seed=SEED.read_text();oldline="CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_ram=y";new="CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_native_slot1=y"
 if seed.count(oldline)!=1:raise RuntimeError("seed profile mismatch")
 seed=seed.replace(oldline,new);seed=re.sub(r"^CONFIG_TARGET_ROOTFS_INITRAMFS=.*$","CONFIG_TARGET_ROOTFS_INITRAMFS=n",seed,flags=re.M)
 if "CONFIG_TARGET_ROOTFS_INITRAMFS=" not in seed:seed+="CONFIG_TARGET_ROOTFS_INITRAMFS=n\n"
 # Native acceptance requires actual GPIO button drivers and full WPS userspace.
 seed=re.sub(r"^CONFIG_PACKAGE_wpad-basic-wolfssl=.*$","# CONFIG_PACKAGE_wpad-basic-wolfssl is not set",seed,flags=re.M)
 for p in ("fstools","fwtool","openwrt-keyring","usign","ubi-utils","kmod-input-core","kmod-input-gpio-keys","kmod-button-hotplug","wpad-wolfssl"):
  x="CONFIG_PACKAGE_"+p+"=y";seed=re.sub(r"^# CONFIG_PACKAGE_"+p+r" is not set$",x,seed,flags=re.M)
  if x not in seed.splitlines():seed+=x+"\n"
 diag="CONFIG_ATH11K_RT3000_MON_OWNER_DIAG=y";reo="CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=y"
 seed=re.sub(r"^# CONFIG_ATH11K_RT3000_MON_OWNER_DIAG is not set$",diag,seed,flags=re.M)
 if diag not in seed.splitlines():seed+=diag+"\n"
 seed=re.sub(r"^# CONFIG_ATH11K_RT3000_REO_IDR_CLAIM is not set$",reo,seed,flags=re.M)
 if reo not in seed.splitlines():seed+=reo+"\n"
 tx_symbol="CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG"
 seed=re.sub(r"^"+tx_symbol+r"=.*$", "", seed, flags=re.M)
 seed=re.sub(r"^# "+tx_symbol+r" is not set$", "", seed, flags=re.M)
 seed+=(tx_symbol+"=y"+chr(10)) if args.enable_c_native_tx_coherent_diag else ("# "+tx_symbol+" is not set"+chr(10))
 (C/".config").write_text(seed)
 kp=C/"target/linux/ipq50xx/config-5.4";k=kp.read_text()
 opts={"CONFIG_BLOCK":"y","CONFIG_MTD":"y","CONFIG_MTD_NAND_QCOM":"y","CONFIG_MTD_UBI":"y","CONFIG_MTD_UBI_BLOCK":"y","CONFIG_UBIFS_FS":"y","CONFIG_SQUASHFS":"y","CONFIG_SQUASHFS_XZ":"y","CONFIG_OVERLAY_FS":"y","CONFIG_NET_DSA":"y","CONFIG_NET_DSA_REALTEK_RTL8365MB":"y","CONFIG_NET_DSA_TAG_RTL8_4":"y","CONFIG_MTD_PARTITIONED_MASTER":"n","CONFIG_RTL8367S_PROBE":"n"}
 for n,v in opts.items():
  k="\n".join(x for x in k.splitlines() if not x.startswith((n+"=","# "+n+" is not set")))
  k+="\n"+(("# "+n+" is not set") if v=="n" else n+"="+v)+"\n"
 kp.write_text(k)
 rx_evidence_key={"native-rx-620-621":"native_rx_620_621",
                  "native-rx-620-621-622":"native_rx_620_621_622",
                  "native-rx-620-621-622-625-width-join":"native_rx_620_621_622_625_width_join"}.get(rx_profile,"native_rx_618")
 rx_evidence={"explicit_opt_in":True,"unselected_rx_patch_preflight":rx_patch_presence,"source_closure":rx_source_pins,"pas_oem35_cache_gate":pas_inputs,"runtime":"NOT_EXECUTED","default_qcn6122_bdf":"935","selected_qcn6122_bdf_profile":bdf_profile,"selected_qcn6122_board2_sha256":selected_bdf_sha,"axis_compat_432_validation":axis_bdf,"physical_write_policy":{"native_rw_physical":"0x03100000+0x02800000","expected_rw_children":1,"expected_ro_children":20,"bootconfig_children_rw":False,"installer_only_property":"h3c,rt3000-c-installer-write-bootconfig"}}
 tx_evidence={"explicit_opt_in":args.enable_c_native_tx_coherent_diag,"unselected_tx_patch_preflight":tx_patch_presence,"source_closure":tx_source_pins,"runtime":"NOT_EXECUTED","runtime_parameter_default":"off","warning_policy":"preserve original warnings"}
 inputs={"started":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=R,text=True).strip(),"builder_sha256":H(__file__),"native_rx_gates_sha256":H(R/"rt3000-machine-c/tools/native_rx_gates.py"),"native_dsa_runtime_audit_sha256":H(R/"rt3000-machine-c/tools/native_dsa_runtime_audit.py"),"source_hashes":sums, "compiled_source_pins":{"qcom_post425":NG.QCOM,"mtdcore_post425":NG.MC,"mtdpart_post425":NG.MP,"patch_425":NG.PINS["target/linux/ipq50xx/patches/425-mtd-c-physical-map-write-guard.patch"],"cache_source_check":"PASS"},"native_dsa_overlay_copy_audit":native_dsa_overlay_audit,"native_led_source_pins":native_led_source_pins,"native_ssdk_source_pins":ssdk_source_pins,"native_ssdk_pre_fullmake_build_audit":ssdk_build_audit,"native_ssdk_build_audit":ssdk_final_build_audit,"native_led_overlay_copy_audit":native_led_overlay_audit,rx_evidence_key:rx_evidence,"metadata_before":old,"metadata_after":{n:H(C/n) for n in metas},"old_qca_modules":oldq,"qca_stamps_removed":removed,"profile":"native_slot1","kernel_options":opts,"runtime":"NOT_EXECUTED","flash_ready":False}
 if args.enable_c_native_tx_coherent_diag: inputs["native_tx_623_624"]=tx_evidence
 (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 run(["make","defconfig"],C,E/"defconfig.log")
 cfg=(C/".config").read_text().splitlines()
 selected=sorted(x for x in cfg if x.startswith("CONFIG_TARGET_ipq50xx_arm_DEVICE_") and x.endswith("=y"))
 if selected!=[new]:raise RuntimeError("resolved profile mismatch "+repr(selected))
 if "CONFIG_TARGET_ROOTFS_INITRAMFS=n" not in cfg and "# CONFIG_TARGET_ROOTFS_INITRAMFS is not set" not in cfg:raise RuntimeError("initramfs unexpectedly enabled")
 for x in ("CONFIG_PACKAGE_kmod-ath11k=y","CONFIG_PACKAGE_fstools=y","CONFIG_PACKAGE_fwtool=y","CONFIG_PACKAGE_openwrt-keyring=y","CONFIG_PACKAGE_usign=y","CONFIG_PACKAGE_ubi-utils=y","CONFIG_ATH11K_RT3000_MON_OWNER_DIAG=y","CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=y"):
  if x not in cfg:raise RuntimeError("resolved config missing "+x)
 NG.config_gate(cfg,native_tx=args.enable_c_native_tx_coherent_diag)
 native_led_config_audit=NG.native_led_config_gate(cfg)
 inputs["native_led_config_audit"]=native_led_config_audit
 (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 shutil.copy2(C/".config",E/"resolved.config")
 ssdk_build_audit=None
 ssdk_final_build_audit=None
 if args.enable_c_native_ssdk_phy_notify:
  ssdk_pkgs=list(C.glob("build_dir/target-*/linux-*/qca-ssdk-nohnat/qca-ssdk-*"))
  if len(ssdk_pkgs)!=1:raise RuntimeError("prepared SSDK package directory ambiguous")
  ssdk_pkg=ssdk_pkgs[0]
  if "CONFIG_PACKAGE_kmod-qca-ssdk-nohnat=y" not in (C/".config").read_text().splitlines():raise RuntimeError("native profile lacks selected nohnat SSDK package")
  run(["make","package/kernel/qca/qca-ssdk/clean"],C,E/"ssdk-clean.log")
  run(["make","package/kernel/qca/qca-ssdk/prepare","V=s"],C,E/"ssdk-prepare.log")
  ssdk_source_audit=NG.native_ssdk_source_gate(R,True)
  ssdk_build_started_ns=time.time_ns()
  run(["make","package/kernel/qca/qca-ssdk/compile","V=s"],C,E/"ssdk-compile.log")
  ssdk_build_audit=NG.verify_native_ssdk_build(ssdk_pkg,ssdk_build_started_ns,E/"ssdk-compile.log")
  ssdk_unstripped=E/"qca-ssdk-fresh-module.ko";shutil.copy2(ssdk_pkg/"build/bin/qca-ssdk.ko",ssdk_unstripped)
  ssdk_stage=Path(ssdk_build_audit["staged_module"]);ssdk_stage_report=E/"qca-ssdk-staged-module-binding.json"
  run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(ssdk_stage),"--unstripped",str(ssdk_unstripped),"--output",str(ssdk_stage_report)],R,E/"qca-ssdk-staged-module-binding.log")
  ssdk_build_audit["stage_elf_allocated_binding"]={"report_sha256":H(ssdk_stage_report),"status":"PASS"}
  inputs["native_ssdk_build_audit"]=ssdk_build_audit
  inputs["native_ssdk_source_audit"]=ssdk_source_audit
  inputs["native_ssdk_build_started_ns"]=ssdk_build_started_ns
  (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 # Force a clean mac80211/backports rebuild so the ath11k module trio cannot
 # be inherited from a previous RAM/profile build.
 run(["make","package/kernel/mac80211/clean"],C,E/"mac80211-clean.log")
 mac80211_started_ns=time.time_ns()
 run(["make","package/kernel/mac80211/compile","V=s"],C,E/"mac80211-clean-compile.log")
 run(["make","package/kernel/leds-rt3000-paired/clean"],C,E/"native-led-clean.log")
 native_led_compile_started_ns=time.time_ns()
 run(["make","package/kernel/leds-rt3000-paired/compile","V=s"],C,E/"native-led-clean-compile.log")
 kernel_dirs=list(C.glob("build_dir/target-*/linux-*/linux-*"))
 if len(kernel_dirs)!=1: raise RuntimeError("kernel build directory ambiguous before fresh MTD compile")
 native_led_kernel_inputs=NG.native_led_kernel_input_audit(kernel_dirs[0],E)
 inputs["native_led_kernel_inputs"]=native_led_kernel_inputs
 (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 old_native_dsa_objects=NG.prepare_fresh_native_dsa_objects(kernel_dirs[0],E)
 inputs["native_dsa_objects_before_clean"]=old_native_dsa_objects
 (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 fresh_build_started_ns=time.time_ns()
 old_mtd_objects=NG.prepare_fresh_mtd_objects(kernel_dirs[0],E)
 # OpenWrt kernel.mk enables complete compiler argv only with verbose c.
 build_cmd=["make","-j6","V=sc"]
 if axis_bdf: build_cmd.append("RT3000_C_NATIVE_QCN6122_BDF="+str(NG.AXIS_COMPAT_432_PATH))
 run(build_cmd,C,E/"native-build.log")
 if ssdk_build_audit is not None:
  ssdk_final_build_audit=NG.verify_native_ssdk_build(ssdk_pkg,fresh_build_started_ns,E/"native-build.log",dependency_proof=ssdk_build_audit)
  ssdk_final_module=E/"qca-ssdk-final-module.ko";shutil.copy2(ssdk_pkg/"build/bin/qca-ssdk.ko",ssdk_final_module)
  ssdk_final_stage=Path(ssdk_final_build_audit["staged_module"])
  ssdk_final_stage_report=E/"qca-ssdk-final-staged-module-binding.json"
  run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(ssdk_final_stage),"--unstripped",str(ssdk_final_module),"--output",str(ssdk_final_stage_report)],R,E/"qca-ssdk-final-staged-module-binding.log")
  ssdk_final_build_audit["fullmake_log_sha256"]=H(E/"native-build.log")
  ssdk_final_build_audit["fullmake_started_ns"]=fresh_build_started_ns
  ssdk_final_build_audit["final_module_sha256"]=H(ssdk_final_module)
  ssdk_final_build_audit["final_stage_elf_allocated_binding"]={"report_sha256":H(ssdk_final_stage_report),"status":"PASS"}
  inputs["native_ssdk_pre_fullmake_build_audit"]=ssdk_build_audit
  inputs["native_ssdk_build_audit"]=ssdk_final_build_audit
  inputs["native_ssdk_fullmake_started_ns"]=fresh_build_started_ns
  (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 dp=list(C.glob("build_dir/target-*/linux-*/backports-*/drivers/net/wireless/ath/ath11k/dp.c"))
 dprx=list(C.glob("build_dir/target-*/linux-*/backports-*/drivers/net/wireless/ath/ath11k/dp_rx.c"))
 bp=list(C.glob("build_dir/target-*/linux-*/backports-*/.config"))
 ah=list(C.glob("build_dir/target-*/linux-*/backports-*/backport-include/backport/autoconf.h"))
 if len(bp)!=1 or len(ah)!=1:raise RuntimeError("compiled backports config closure missing")
 rx_object_audit=None
 if rx_profile=="native-rx-620-621":
  rx_object_audit=NG.verify_native_rx_620_621_objects(bp[0].parent,bp[0],ah[0],mac80211_started_ns,E/"mac80211-clean-compile.log")
 elif rx_profile=="native-rx-620-621-622":
  overrides={"drivers/net/wireless/ath/ath11k/dp.c":NG.NATIVE_TX_623_624_SOURCES["drivers/net/wireless/ath/ath11k/dp.c"]} if args.enable_c_native_tx_coherent_diag else None
  rx_object_audit=NG.verify_native_rx_620_621_622_objects(bp[0].parent,bp[0],ah[0],mac80211_started_ns,E/"mac80211-clean-compile.log",compiled_source_overrides=overrides)
 elif rx_profile=="native-rx-620-621-622-625-width-join":
  overrides={"drivers/net/wireless/ath/ath11k/dp.c":NG.NATIVE_TX_623_624_SOURCES["drivers/net/wireless/ath/ath11k/dp.c"]} if args.enable_c_native_tx_coherent_diag else None
  rx_object_audit=NG.verify_native_rx_625_objects(bp[0].parent,bp[0],ah[0],mac80211_started_ns,E/"mac80211-clean-compile.log",compiled_source_overrides=overrides)
 else:
  if len(dp)!=1 or H(dp[0])!=NG.DP or len(dprx)!=1 or H(dprx[0])!=NG.DPRX:raise RuntimeError("compiled 618 RX source/config closure missing")
  if "CPTCFG_ATH11K_RT3000_REO_IDR_CLAIM=y" not in bp[0].read_text() or "CPTCFG_ATH11K_RT3000_REO_IDR_CLAIM 1" not in ah[0].read_text():raise RuntimeError("REO IDR claim not enabled in compiled backports")
 tx_object_audit=None
 if args.enable_c_native_tx_coherent_diag:
  tx_object_audit=NG.verify_native_tx_623_624_objects(bp[0].parent,bp[0],ah[0],mac80211_started_ns,E/"mac80211-clean-compile.log")
  tx_evidence["compiled_object_source_gate"]=tx_object_audit
  inputs["native_tx_623_624"]=tx_evidence
  (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 shutil.copy2(bp[0],E/"backports.config");shutil.copy2(ah[0],E/"backports.autoconf.h")
 if rx_object_audit is not None:
  inputs[rx_evidence_key]["compiled_object_source_gate"]=rx_object_audit
  (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 ks=list(C.glob("build_dir/target-*/linux-*/linux-*/.config"))
 if len(ks)!=1:raise RuntimeError("kernel config ambiguous")
 kc=ks[0];kl=kc.read_text().splitlines();kd=kc.parent
 native_led_kernel_config_audit=NG.native_led_kernel_config_gate(kl)
 native_dsa_compiled_audit=NG.verify_native_dsa_compiled_sources(kd,fresh_build_started_ns,E/"native-build.log")
 inputs["native_dsa_compiled_source_audit"]=native_dsa_compiled_audit
 (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 for x in ("CONFIG_BLOCK=y","CONFIG_MTD=y","CONFIG_MTD_NAND_QCOM=y","CONFIG_MTD_UBI=y","CONFIG_MTD_UBI_BLOCK=y","CONFIG_UBIFS_FS=y","CONFIG_SQUASHFS=y","CONFIG_OVERLAY_FS=y","CONFIG_NET_DSA=y","CONFIG_NET_DSA_REALTEK_RTL8365MB=y","CONFIG_NET_DSA_TAG_RTL8_4=y"):
  if x not in kl:raise RuntimeError("kernel option missing "+x)
 if "CONFIG_MTD_PARTITIONED_MASTER=y" in kl or "CONFIG_RTL8367S_PROBE=y" in kl:raise RuntimeError("forbidden kernel option")
 if any(x.startswith("CONFIG_INITRAMFS_SOURCE=") and x.split("=",1)[1] not in ('""',"") for x in kl):raise RuntimeError("native kernel has initramfs")
 shutil.copy2(kc,E/"kernel.config");im=kd/"arch/arm/boot/Image";arch=im
 if not im.is_file() or not arch.is_file() or H(im)!=H(arch):raise RuntimeError("raw Image identity fail")
 dt=list(kd.parent.glob("image-ipq5000-rt3000-rtl8367s-persistent.dtb"));rf=list(C.glob("bin/targets/ipq50xx/arm/*c-native-rootfs.squashfs"))
 if len(dt)!=1 or len(rf)!=1:raise RuntimeError("native DTB/rootfs missing")
 mtd_object_audit=NG.compiled_mtd_gate(kd,kl,fresh_build_started_ns,E/"native-build.log")
 mc=kd/"drivers/mtd/mtdcore.c";mco=kd/"drivers/mtd/mtdcore.o";mp=kd/"drivers/mtd/mtdpart.c";mpo=kd/"drivers/mtd/mtdpart.o"
 qs=kd/"drivers/mtd/nand/raw/qcom_nandc.c";qo=kd/"drivers/mtd/nand/raw/qcom_nandc.o";vm=kd/"vmlinux"
 if H(qs)!=FINAL or not qo.is_file() or not vm.is_file():raise RuntimeError("compiled QPIC closure failed")
 o=Path("<EVIDENCE>");out=E/"candidate"
 roots=list(C.glob("build_dir/target-*/root-ipq50xx"))
 if len(roots)!=1:raise RuntimeError("native rootfs tree ambiguous")
 if ssdk_final_build_audit is not None:
  rootfs_ssdk=list((roots[0]/"lib/modules").rglob("qca-ssdk.ko"))
  if len(rootfs_ssdk)!=1:raise RuntimeError("native rootfs SSDK module missing/ambiguous")
  report=E/"qca-ssdk-final-rootfs-module-binding.json"
  run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(rootfs_ssdk[0]),"--unstripped",str(E/"qca-ssdk-final-module.ko"),"--output",str(report)],R,E/"qca-ssdk-final-rootfs-module-binding.log")
  ssdk_final_build_audit["final_rootfs_elf_allocated_binding"]={"report_sha256":H(report),"status":"PASS","rootfs_module_sha256":H(rootfs_ssdk[0])}
  inputs["native_ssdk_build_audit"]=ssdk_final_build_audit
  (E/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
 led_rootfs_modules=list((roots[0]/"lib/modules").rglob(NG.NATIVE_LED_MODULE))
 if len(led_rootfs_modules)!=1:raise RuntimeError("native paired LED rootfs module missing/ambiguous")
 led_rootfs_module=led_rootfs_modules[0]
 led_rootfs_rel=led_rootfs_module.relative_to(roots[0]).as_posix()
 led_unstripped_candidates=[p for p in C.glob("build_dir/target-*/**/"+NG.NATIVE_LED_MODULE)
                            if (p.parent/"leds-rt3000-paired.c").is_file()]
 if len(led_unstripped_candidates)!=1:raise RuntimeError("native paired LED unstripped module missing/ambiguous")
 led_unstripped_module=led_unstripped_candidates[0]
 native_led_package_build_audit=NG.verify_native_led_package_build(led_unstripped_module.parent,native_led_compile_started_ns,E/"native-led-clean-compile.log",native_led_kernel_inputs)
 athmods=NG.check_rootfs(roots[0],qcn_board2_sha256=selected_bdf_sha)
 dsa_runtime_rootfs_audit=NDA.audit_native_dsa_payload(roots[0],R/"package/firmware/rt3000-c-dsa-master")
 rx_module_marker_audit=None
 if rx_profile in ("native-rx-620-621-622","native-rx-620-621-622-625-width-join"):
  ath11k_paths=[rel for rel in athmods if rel.endswith("/ath11k.ko")]
  if len(ath11k_paths)!=1:raise RuntimeError("622/625 embedded ath11k module is ambiguous")
  check_marker=NG.verify_native_rx_625_module_marker if rx_profile.endswith("width-join") else NG.verify_native_rx_622_module_marker
  rx_module_marker_audit=check_marker(roots[0]/ath11k_paths[0])
 tx_module_marker_audit=None
 if args.enable_c_native_tx_coherent_diag:
  ath11k_paths=[rel for rel in athmods if rel.endswith("/ath11k.ko")]
  if len(ath11k_paths)!=1:raise RuntimeError("native TX embedded ath11k module is ambiguous")
  tx_module_marker_audit=NG.verify_native_tx_623_624_module_marker(roots[0]/ath11k_paths[0])
 # ipkg-build normalizes packaged mtimes to SOURCE_DATE_EPOCH. Bind code/data
 # to the freshly linked unstripped modules instead of testing package mtime.
 module_binding_audit={}
 athdir=bp[0].parent/"drivers/net/wireless/ath/ath11k"
 clean_log=(E/"mac80211-clean-compile.log").read_text(errors="replace")
 for rel in athmods:
  unstripped=athdir/Path(rel).name; linkcmd=athdir/("."+unstripped.name+".cmd")
  if not unstripped.is_file() or unstripped.stat().st_mtime_ns<mac80211_started_ns:raise RuntimeError("unstripped module missing/stale: "+rel)
  if not linkcmd.is_file() or linkcmd.stat().st_mtime_ns<mac80211_started_ns:raise RuntimeError("module link command missing/stale: "+rel)
  command=linkcmd.read_text(errors="replace")
  if unstripped.name not in command or unstripped.with_suffix(".o").name not in command:raise RuntimeError("module link command source/object binding absent: "+rel)
  if "LD [M]" not in clean_log or str(unstripped) not in clean_log:raise RuntimeError("fresh module link absent from compile log: "+rel)
  binding_out=E/("module-binding-"+unstripped.name+".json")
  run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(roots[0]/rel),"--unstripped",str(unstripped),"--output",str(binding_out)],R,E/("module-binding-"+unstripped.name+".log"))
  binding=json.loads(binding_out.read_text())
  if binding["code_data_sections_match"] is not True:raise RuntimeError("packaged module code/data binding failed: "+rel)
  frozen=E/"fresh-unstripped-modules"/unstripped.name;frozen.parent.mkdir(mode=0o700,exist_ok=True);shutil.copy2(unstripped,frozen);shutil.copy2(linkcmd,frozen.parent/linkcmd.name)
  module_binding_audit[rel]={"packaged_sha256":binding["packaged_sha256"],"unstripped_sha256":binding["unstripped_sha256"],"code_data_sections_match":True,"allocated_sections_match":binding["allocated_sections_match"],"binding_report_sha256":H(binding_out),"unstripped_mtime_ns":unstripped.stat().st_mtime_ns,"link_command_sha256":H(linkcmd),"packaged_mtime_ns":(roots[0]/rel).stat().st_mtime_ns}
 rootfs_module_extract=E/"squashfs-module-extract"
 unsquashfs=C/"staging_dir/host/bin/unsquashfs"
 if not unsquashfs.is_file():
  found=shutil.which("unsquashfs")
  if not found: raise RuntimeError("unsquashfs required to audit embedded native module trio")
  unsquashfs=Path(found)
 run([str(unsquashfs),"-no-progress","-d",str(rootfs_module_extract),str(rf[0]),*sorted(athmods),*NDA.RUNTIME_FILES,NDA.RC_LINK,led_rootfs_rel],C,E/"squashfs-module-extract.log")
 squash_modules={rel:H(rootfs_module_extract/rel) for rel in athmods}
 squashfs_module_audit=NG.verify_module_sets(athmods,squash_modules)
 if not (rootfs_module_extract/led_rootfs_rel).is_file():raise RuntimeError("paired LED module absent from SquashFS")
 if H(rootfs_module_extract/led_rootfs_rel)!=H(led_rootfs_module):raise RuntimeError("paired LED rootfs/SquashFS module bytes differ")
 led_rootfs_binding=E/"native-led-rootfs-binding.json"
 run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(led_rootfs_module),"--unstripped",str(led_unstripped_module),"--output",str(led_rootfs_binding)],R,E/"native-led-rootfs-binding.log")
 led_rootfs_binding_audit=json.loads(led_rootfs_binding.read_text())
 if led_rootfs_binding_audit.get("code_data_sections_match") is not True:raise RuntimeError("paired LED rootfs module code/data differs from freshly linked module")
 led_squash_binding=E/"native-led-squashfs-binding.json"
 run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(rootfs_module_extract/led_rootfs_rel),"--unstripped",str(led_unstripped_module),"--output",str(led_squash_binding)],R,E/"native-led-squashfs-binding.log")
 led_squash_binding_audit=json.loads(led_squash_binding.read_text())
 if led_squash_binding_audit.get("code_data_sections_match") is not True:raise RuntimeError("paired LED SquashFS module code/data differs from freshly linked module")
 dsa_runtime_squashfs_audit=NDA.audit_native_dsa_payload(rootfs_module_extract,R/"package/firmware/rt3000-c-dsa-master")
 if dsa_runtime_squashfs_audit!=dsa_runtime_rootfs_audit:raise RuntimeError("native DSA runtime audit differs between rootfs tree and SquashFS")
 if rx_profile in ("native-rx-620-621-622","native-rx-620-621-622-625-width-join"):
  check_marker=NG.verify_native_rx_625_module_marker if rx_profile.endswith("width-join") else NG.verify_native_rx_622_module_marker
  rx_module_marker_audit["squashfs_embedded_module"]=check_marker(rootfs_module_extract/ath11k_paths[0])
 if args.enable_c_native_tx_coherent_diag:
  tx_module_marker_audit["squashfs_embedded_module"]=NG.verify_native_tx_623_624_module_marker(rootfs_module_extract/ath11k_paths[0])
 (E/"squashfs-module-audit.json").write_text(json.dumps(squashfs_module_audit,indent=2)+"\n")
 run([sys.executable,str(R/"rt3000-machine-c/tools/audit_native_dtb.py"),"--mode","persistent","--kernel-config",str(kc),"--output",str(E/"native-dtb-audit.json"),str(dt[0])],R,E/"native-dtb-audit.log")
 native_dtb_audit=json.loads((E/"native-dtb-audit.json").read_text())
 compiled_switch_reset_gpio=native_dtb_audit["switch_reset_gpio"]
 compiled_native_led_audit=native_dtb_audit["native_leds"]
 if not isinstance(compiled_native_led_audit,dict) or compiled_native_led_audit.get("status")!="PASS":raise RuntimeError("compiled persistent DTB lacks paired LED audit")
 compiled_wps_gpio_audit=native_dtb_audit["wps_gpio"]
 if not isinstance(compiled_wps_gpio_audit,dict) or compiled_wps_gpio_audit.get("status")!="PASS":
  raise RuntimeError("compiled persistent DTB lacks a semantically audited WPS GPIO descriptor")
 wps=compiled_wps_gpio_audit["descriptor_cells"]
 cmd=[sys.executable,str(R/"rt3000-machine-c/tools/build_native_ubi_candidate.py"),"--kernel-image",str(im),"--dtb",str(dt[0]),"--kernel-config",str(kc),"--rootfs-squashfs",str(rf[0]),"--wifi-fw",str(o/"volume-1-wifi_fw.payload"),"--bt-fw",str(o/"volume-2-bt_fw.payload"),"--mkimage",str(C/"staging_dir/host/bin/mkimage"),"--lzma",str(C/"staging_dir/host/bin/lzma"),"--mkfs-ubifs",str(C/"staging_dir/host/bin/mkfs.ubifs"),"--ubinize",str(C/"staging_dir/host/bin/ubinize"),"--output-dir",str(out)]
 run(cmd,R,E/"native-image-generation.log")
 m=json.loads((out/"manifest.json").read_text())
 report={"status":"OFFLINE_NATIVE_CANDIDATE_STATIC_PASS","profile":"Device/h3c_rt3000_rtl8367s_native_slot1","fit_sha256":m["fit_sha256"],"fit_bytes":m["fit_bytes"],"ubi_sha256":m["ubi_sha256"],"ubi_bytes":m["ubi_bytes"],"raw_Image_sha256":H(im),"dtb_sha256":H(dt[0]),"rootfs_sha256":H(rf[0]),"kernel_config_sha256":H(kc), "qcom_source_sha256":H(qs),"qcom_object_sha256":H(qo),"mtdcore_source_sha256":H(mc),"mtdcore_object_sha256":H(mco),"mtdpart_source_sha256":H(mp),"mtdpart_object_sha256":H(mpo),"compiled_wps_gpio_descriptor":wps,"compiled_wps_gpio_audit":compiled_wps_gpio_audit,"compiled_switch_reset_gpio":compiled_switch_reset_gpio,"native_dsa_overlay_copy_audit":native_dsa_overlay_audit,"native_led_source_pins":native_led_source_pins,"native_ssdk_source_pins":ssdk_source_pins,"native_ssdk_build_audit":ssdk_build_audit,"native_led_overlay_copy_audit":native_led_overlay_audit,"native_led_config_audit":native_led_config_audit,"native_led_kernel_config_audit":native_led_kernel_config_audit,"native_led_kernel_inputs":native_led_kernel_inputs,"native_led_package_build_audit":native_led_package_build_audit,"native_led_rootfs_module_binding":led_rootfs_binding_audit,"native_led_squashfs_module_binding":led_squash_binding_audit,"compiled_native_led_audit":compiled_native_led_audit,"native_dsa_compiled_source_audit":native_dsa_compiled_audit,"native_dsa_objects_before_clean":old_native_dsa_objects,"ath11k_module_sha256":athmods,"native_wifi_firmware_sha256":{rel:H(roots[0]/rel) for rel in ({**NG.EXPECTED_FIRMWARE, NG.QCN_BOARD2_REL:selected_bdf_sha})},"ath11k_squashfs_module_audit":squashfs_module_audit,"native_dsa_runtime_files":{"rootfs_tree":dsa_runtime_rootfs_audit,"squashfs":dsa_runtime_squashfs_audit},"ath11k_fresh_module_bindings":module_binding_audit,"native_rx_622_625_module_marker_audit":rx_module_marker_audit,"mac80211_clean_compile_log_sha256":H(E/"mac80211-clean-compile.log"),"mtd_object_fresh_compile_audit":mtd_object_audit,"mtd_objects_before_clean":old_mtd_objects,"mac80211_clean_compile_started_ns":mac80211_started_ns,"mtd_full_build_started_ns":fresh_build_started_ns,"vmlinux_sha256":H(vm),"flash_ready":False,"runtime":"NOT_EXECUTED","installer_profile":"NOT_BUILT","native_rx_profile":rx_profile,"native_rx_compiled_object_audit":rx_object_audit,"native_tx_623_624_compiled_object_audit":tx_object_audit,"native_tx_623_624_module_marker_audit":tx_module_marker_audit,"qcn6122_bdf_profile":bdf_profile,"qcn6122_board2_sha256":selected_bdf_sha,"axis_compat_432_validation":axis_bdf}
 (E/"artifact.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
