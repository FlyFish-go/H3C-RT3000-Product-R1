#!/usr/bin/env python3
"""Build and statically audit the private C-only network installer RAM FIT."""
import argparse,datetime,fcntl,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_rx_gates as NG
R=Path(__file__).resolve().parents[2]
SEED=R/'configs/rt3000-c-2g-ram/full.config'
PROFILE=R/'rt3000-machine-c/native/profile-installer.json'
BDF_SHA='432eb4044466712469193973ce337fee68f5c76e0dcee54dd6da1e6c9fd48bb1'
QPIC_SOURCE='9e5afc14f21b9869679db8b98644b71ed4743d921bb22ed335d055693bde1491'
MTD_BASE={'drivers/mtd/mtdpart.c':'36baf032b0f9b69a2e3a369edbcd692d3d1c4c83790e027843ffbfa7ddaffa1d','drivers/mtd/mtdcore.c':'abd16ee4dbd7c0a86186fdf17c0789e612b307a572743b07e11b9587d62a7c0c','drivers/mtd/nand/raw/qcom_nandc.c':'9e5afc14f21b9869679db8b98644b71ed4743d921bb22ed335d055693bde1491'}
MTD_PATCHED={'drivers/mtd/mtdpart.c':'d1b420452d747266caa11b0b4e800d4f2f9831dc37b9c5a9ad3c2793831ab901','drivers/mtd/mtdcore.c':'68bac9d0855f19769ed0c0efde5f0e25c179725cb80ef18ba1ba60f8e7814c1c','drivers/mtd/nand/raw/qcom_nandc.c':'1a749a7b53bdb5c9d01e5b303badaea9931607db90c4abfea6d3fa51631dfccf'}
MTD_PATCH='target/linux/ipq50xx/patches/425-mtd-c-physical-map-write-guard.patch'
PFX=('target/linux/ipq50xx/','target/linux/generic/','package/kernel/mac80211/','package/kernel/linux/','package/kernel/qca/qca-ssdk/','package/kernel/qca/qca-nss-dp/','package/firmware/rt3000-c-oem-wifi/','package/system/procd/','rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-installer.dts')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def run(cmd,cwd,log=None):
 if log:
  with Path(log).open('w') as f:r=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT).returncode
 else:r=subprocess.run(cmd,cwd=cwd).returncode
 if r:raise RuntimeError('command failed: '+repr(cmd)+' log='+str(log))
def copy_inputs(root,cache,prefixes):
 names=subprocess.check_output(['git','ls-files','-c','-o','--exclude-standard','-z'],cwd=root).decode().split('\0')
 names=sorted({n for n in names if n and n.startswith(prefixes) and (root/n).exists()})
 hashes={}; synced=[]
 for n in names:
  s=root/n;d=cache/n
  same=(d.is_symlink() and s.is_symlink() and os.readlink(d)==os.readlink(s)) if s.is_symlink() else (d.is_file() and not d.is_symlink() and sha(s)==sha(d))
  if not same:
   d.parent.mkdir(parents=True,exist_ok=True)
   if d.is_symlink():d.unlink()
   if d.exists() and d.is_dir():shutil.rmtree(d)
   if s.is_symlink():
    if d.exists():d.unlink()
    d.symlink_to(os.readlink(s))
   else:shutil.copy2(s,d)
   synced.append(n)
  hashes[n]=os.readlink(s) if s.is_symlink() else sha(s)
 return hashes,synced
def set_kconfig(text,values):
 for name,val in values.items():
  text=re.sub(r'^(?:CONFIG_'+re.escape(name)+r'=.*|# CONFIG_'+re.escape(name)+r' is not set)\n','',text,flags=re.M)
  text+='CONFIG_'+name+'='+val+'\n' if val not in ('n','unset') else '# CONFIG_'+name+' is not set\n'
 return text
def select_installer_sources(root,enable_rx622,enable_tx,enable_ssdk=False,enable_width_join=False):
 rx_profile=NG.select_native_rx_profile(False,False,enable_rx622 and not enable_width_join,enable_width_join)
 ssdk_source=NG.native_ssdk_source_gate(root,enable_ssdk)
 rx_presence=NG.reject_unselected_native_rx_patches(root,rx_profile)
 tx_presence=NG.reject_unselected_native_tx_patches(root,enable_tx,rx_profile)
 source=NG.source_gate(root)
 rx_source=(NG.native_rx_625_source_gate(root) if enable_width_join else NG.native_rx_620_621_622_source_gate(root))
 tx_source=NG.native_tx_623_624_source_gate(root,rx_profile) if enable_tx else None
 return {'rx_profile':rx_profile,'rx_patch_presence':rx_presence,
         'rx_source_pins':rx_source,'tx_patch_presence':tx_presence,
         'tx_source_pins':tx_source,'native_source_gate':source,'ssdk_source_pins':ssdk_source}
def installer_rx_622_compiled_source_overrides(enable_tx):
 if not enable_tx:return None
 return {"drivers/net/wireless/ath/ath11k/dp.c":NG.NATIVE_TX_623_624_SOURCES["drivers/net/wireless/ath/ath11k/dp.c"]}
def verify_installer_ath11k_module_bindings(modules,backports_root,fresh_after_ns,compile_log,evidence):
 d=Path(backports_root)/"drivers/net/wireless/ath/ath11k";log=Path(compile_log).read_text(errors="replace");out={}
 for name,pkg in modules.items():
  u=d/name;c=d/("."+name+".cmd")
  if not u.is_file() or u.stat().st_mtime_ns<fresh_after_ns:raise RuntimeError("unstripped module missing/stale: "+name)
  if not c.is_file() or c.stat().st_mtime_ns<fresh_after_ns:raise RuntimeError("module link command missing/stale: "+name)
  cmd=c.read_text(errors="replace")
  if name not in cmd or name.replace(".ko",".o") not in cmd:raise RuntimeError("module link command binding absent: "+name)
  if "LD [M]" not in log or str(u) not in log:raise RuntimeError("fresh module link absent from log: "+name)
  report=Path(evidence)/("module-binding-"+name+".json")
  run([sys.executable,str(R/"rt3000-machine-c/tools/audit_ath11k_symbols.py"),"--packaged",str(pkg),"--unstripped",str(u),"--output",str(report)],R,Path(evidence)/("module-binding-"+name+".log"))
  b=json.loads(report.read_text())
  if b["code_data_sections_match"] is not True:raise RuntimeError("packaged module code/data mismatch: "+name)
  f=Path(evidence)/"fresh-unstripped-modules"/name;f.parent.mkdir(mode=0o700,exist_ok=True);shutil.copy2(u,f);shutil.copy2(c,f.parent/c.name)
  out[name]={"packaged_sha256":b["packaged_sha256"],"unstripped_sha256":b["unstripped_sha256"],"code_data_sections_match":True,"allocated_sections_match":b["allocated_sections_match"],"binding_report_sha256":sha(report),"unstripped_mtime_ns":u.stat().st_mtime_ns,"link_command_sha256":sha(c),"packaged_mtime_ns":pkg.stat().st_mtime_ns}
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--tree',type=Path,required=True);ap.add_argument('--evidence',type=Path,required=True);ap.add_argument('--jobs',type=int,default=6)
 ap.add_argument('--enable-c-native-rx-620-621-622',action='store_true',help='explicitly select pinned installer RX 620+621+622 source/object profile')
 ap.add_argument('--enable-c-native-rx-width-join',action='store_true',help='opt in to timestamp-only 625 correlation diagnostics; width classification remains DIAGNOSTIC_ONLY')
 ap.add_argument('--enable-c-native-ssdk-phy-notify',action='store_true',help='opt in to strict 0903 SSDK MDIO bus notifier mapping')
 ap.add_argument('--enable-c-native-tx-coherent-diag',action='store_true',help='explicitly select pinned installer TX 623+624 source/object profile; requires RX 620+621+622')
 a=ap.parse_args();os.umask(0o077)
 rx622=a.enable_c_native_rx_620_621_622 or a.enable_c_native_rx_width_join
 source_closure=select_installer_sources(R,rx622,a.enable_c_native_tx_coherent_diag,a.enable_c_native_ssdk_phy_notify,a.enable_c_native_rx_width_join)
 cache=a.tree.resolve();ev=a.evidence.resolve()
 if ev.exists() or ev in cache.parents or cache in ev.parents or ev==R or R in ev.parents:raise ValueError('evidence must be a new private path outside source/cache')
 if not (cache/'staging_dir').is_dir() or not (cache/'Makefile').is_file():raise ValueError('existing locked QSDK cache required')
 bdf=os.environ.get('RT3000_C_INSTALLER_QCN6122_BDF')
 if not bdf or not Path(bdf).is_file() or sha(bdf)!=BDF_SHA:raise ValueError('installer-only 432 BDF identity/env gate failed')
 ev.mkdir(parents=True,mode=0o700)
 lock=(cache/'.c-ram-recipe.lock').open('r+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 treehashes,synced=copy_inputs(R,cache,PFX)
 installer_dts=R/'rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-installer.dts'
 cached_installer_dts=cache/'rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-installer.dts'
 if not cached_installer_dts.is_file() or sha(cached_installer_dts)!=sha(installer_dts):raise RuntimeError('installer native DTS was not synchronized exactly')
 dsa_overlay=NG.verify_native_dsa_overlay(R,cache)
 for n in ('rt3000-machine-c/native/profile-installer.json','rt3000-machine-c/native/ipq5000-rt3000-rtl8367s-installer.dts','rt3000-machine-c/native/patches/424-mtd-qcom-c-native-safe-config.patch','rt3000-machine-c/tools/build_installer_ram.py','rt3000-machine-c/tools/native_rx_gates.py','rt3000-machine-c/tools/native_dsa_runtime_audit.py','rt3000-machine-c/tools/audit_ath11k_symbols.py','rt3000-machine-c/tests/test_installer_builder_profiles.py','rt3000-machine-c/tools/audit_native_dtb.py','rt3000-machine-c/tools/c_mtd_target_preflight_ro.c','rt3000-machine-c/tests/test_c_mtd_target_preflight_ro.c',MTD_PATCH,'rt3000-machine-c/tools/audit_c_installer_initramfs.py','rt3000-machine-c/experiments/installer-runtime-contract/audit_installer_runtime.py','rt3000-machine-c/tools/c_installer_launch.sh'):
  treehashes[n]=sha(R/n)
 prof=json.loads(PROFILE.read_text())
 if prof['profile']!='Device/h3c_rt3000_rtl8367s_installer_ram' or prof['wireless_probe_only']['qcn6122_bdf_sha256']!=BDF_SHA or prof['native_dts_sha256']!=sha(installer_dts):raise ValueError('installer profile/probe/DTS identity mismatch')
 qdir=cache/'build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5'
 mtd_before={rel:sha(qdir/rel) for rel in MTD_BASE}
 if mtd_before==MTD_BASE:mtd_state='PRE_425_PATCH'
 elif mtd_before==MTD_PATCHED:mtd_state='425_PATCH_ALREADY_APPLIED_BY_PRIOR_FAILED_AUDIT_RUN'
 else:raise ValueError('cache MTD source hashes are neither frozen pre-patch nor exact 425 result: '+repr(mtd_before))
 qsrc=qdir/'drivers/mtd/nand/raw/qcom_nandc.c'
 if sha(qsrc) not in (QPIC_SOURCE,MTD_PATCHED['drivers/mtd/nand/raw/qcom_nandc.c']):raise ValueError('cache qcom_nandc.c does not match audited pre/post-425 input')
 patch_file=R/MTD_PATCH
 if not patch_file.is_file():raise ValueError('425 physical-map guard patch missing')
 oldmeta=['tmp/info/.packageinfo-kernel_mac80211','tmp/info/.packageinfo-system_procd','tmp/info/.packageinfo-kernel_qca_qca-ssdk','tmp/info/.packageinfo-kernel_qca_qca-nss-dp','tmp/.packageinfo','tmp/.config-package.in','tmp/info/.targetinfo-ipq50xx','tmp/.targetinfo','tmp/.config-target.in']
 backup=ev/'metadata-before-refresh';backup.mkdir(mode=0o700);meta_before={}
 for n in oldmeta:
  p=cache/n
  if p.is_file():shutil.copy2(p,backup/n.replace('/','__'));meta_before[n]=sha(p);p.unlink()
 run(['make','prepare-tmpinfo'],cache,ev/'prepare-tmpinfo.log')
 for n in oldmeta:
  if not (cache/n).is_file():raise RuntimeError('metadata refresh failed to regenerate '+n)
 checks={'procd':'Package: procd' in (cache/'tmp/info/.packageinfo-system_procd').read_text(errors='replace'),'ath11k_option':'ATH11K_RT3000_MON_OWNER_DIAG' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'mtd_package':'PACKAGE_mtd' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'ubi_utils':'PACKAGE_ubi-utils' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'fstools':'PACKAGE_fstools' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'fwtool':'PACKAGE_fwtool' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'openwrt_keyring':'PACKAGE_openwrt-keyring' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'usign':'PACKAGE_usign' in (cache/'tmp/.config-package.in').read_text(errors='replace'),'installer_profile':'h3c_rt3000_rtl8367s_installer_ram' in (cache/'tmp/.config-target.in').read_text(errors='replace')}
 if not all(checks.values()):raise RuntimeError('refreshed package/target metadata gate failed '+repr(checks))
 seed=SEED.read_text();old='CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_ram=y';new='CONFIG_TARGET_ipq50xx_arm_DEVICE_h3c_rt3000_rtl8367s_installer_ram=y'
 if seed.count(old)!=1:raise RuntimeError('C single profile seed not unique')
 seed=seed.replace(old,new)
 seed=set_kconfig(seed,{'TARGET_ROOTFS_INITRAMFS':'y','PACKAGE_procd':'y','PACKAGE_netifd':'y','PACKAGE_kmod-ath11k':'y','PACKAGE_wpad-basic-wolfssl':'y','PACKAGE_mtd':'y','PACKAGE_ubi-utils':'y','PACKAGE_fstools':'y','PACKAGE_fwtool':'y','PACKAGE_openwrt-keyring':'y','PACKAGE_usign':'y','ATH11K_RT3000_MON_OWNER_DIAG':'y','ATH11K_RT3000_REO_IDR_CLAIM':'y','ATH11K_RT3000_TX_UNKNOWN_DIAG':'y' if a.enable_c_native_tx_coherent_diag else 'n'})
 (cache/'.config').write_text(seed)
 opts={'BLOCK':'y','MTD':'y','MTD_OF_PARTS':'y','MTD_NAND_CORE':'y','MTD_RAW_NAND':'y','MTD_NAND_QCOM':'y','QCOM_BAM_DMA':'y','MTD_PARTITIONED_MASTER':'n','MTD_UBI':'n','MTD_UBI_BLOCK':'n','UBIFS_FS':'n','SQUASHFS':'n','SQUASHFS_XZ':'n','OVERLAY_FS':'n','NET_DSA':'y','NET_DSA_REALTEK_RTL8365MB':'y','NET_DSA_TAG_RTL8_4':'y','RTL8367S_PROBE':'n','BRIDGE_VLAN_FILTERING':'n'}
 kp=cache/'target/linux/ipq50xx/config-5.4';kp.write_text(set_kconfig(kp.read_text(),opts))
 base_inputs=json.loads((Path('<EVIDENCE>')).read_text())
 lock=json.loads((R/'configs/rt3000-c-2g-ram/toolchain-lock.json').read_text())
 if lock['toolchain_tree_sha256']!=base_inputs.get('toolchain_lock_verified'):raise RuntimeError('existing toolchain lock differs from frozen RAM build')
 inputs={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'source_hashes':treehashes,'cache_sync_paths':synced,'profile':prof['profile'],'profile_sha256':sha(PROFILE),'toolchain_lock_verified':lock['toolchain_tree_sha256'],'installer_bdf_sha256':sha(bdf),'installer_bdf_source':'external reviewed C-only schema probe; RAM diagnostic use only','qpic_source_before_build_sha256':sha(qsrc),'mtd_source_state_before_build':mtd_state,'mtd_source_before_build_sha256':mtd_before,'mtd_guard_patch_sha256':sha(patch_file),'mtd_guard_patch_path':MTD_PATCH,'mtd_source_base_sha256':MTD_BASE,'metadata_before':meta_before,'metadata_after':{n:sha(cache/n) for n in oldmeta},'metadata_checks':checks,'kernel_fragment_overrides':opts,'installer_source_closure':source_closure,'native_dsa_overlay':dsa_overlay,'runtime':'NOT_EXECUTED','flash_ready':False}
 (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 run(['make','defconfig'],cache,ev/'defconfig.log')
 cfg=(cache/'.config').read_text().splitlines();profiles=sorted(x for x in cfg if x.startswith('CONFIG_TARGET_ipq50xx_arm_DEVICE_') and x.endswith('=y'))
 if profiles!=[new] or 'CONFIG_TARGET_ROOTFS_INITRAMFS=y' not in cfg:raise RuntimeError('resolved installer profile/initramfs gate failed '+repr(profiles))
 for x in ('CONFIG_PACKAGE_procd=y','CONFIG_PACKAGE_netifd=y','CONFIG_PACKAGE_kmod-ath11k=y','CONFIG_PACKAGE_wpad-basic-wolfssl=y','CONFIG_PACKAGE_mtd=y','CONFIG_PACKAGE_ubi-utils=y','CONFIG_PACKAGE_fstools=y','CONFIG_PACKAGE_fwtool=y','CONFIG_PACKAGE_openwrt-keyring=y','CONFIG_PACKAGE_usign=y','CONFIG_ATH11K_RT3000_MON_OWNER_DIAG=y'):
  if x not in cfg:raise RuntimeError('resolved package missing '+x)
 if 'CONFIG_ATH11K_RT3000_REO_IDR_CLAIM=y' not in cfg:raise RuntimeError('610 REO IDR ownership repair must be enabled in installer candidate')
 if a.enable_c_native_tx_coherent_diag and 'CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG=y' not in cfg:raise RuntimeError('623/624 TX diagnostic Kconfig must be selected for the pinned source profile')
 if not a.enable_c_native_tx_coherent_diag and 'CONFIG_ATH11K_RT3000_TX_UNKNOWN_DIAG=y' in cfg:raise RuntimeError('unselected TX diagnostic Kconfig is enabled')
 shutil.copy2(cache/'.config',ev/'resolved.config')
 ssdk_build_audit=None
 ssdk_final_build_audit=None
 if a.enable_c_native_ssdk_phy_notify:
  ssdk_pkgs=list(cache.glob('build_dir/target-*/linux-*/qca-ssdk-nohnat/qca-ssdk-*'))
  if len(ssdk_pkgs)!=1:raise RuntimeError('prepared SSDK package directory ambiguous')
  ssdk_pkg=ssdk_pkgs[0]
  if 'CONFIG_PACKAGE_kmod-qca-ssdk-nohnat=y' not in (cache/'.config').read_text().splitlines():raise RuntimeError('installer profile lacks selected nohnat SSDK package')
  run(['make','package/kernel/qca/qca-ssdk/clean'],cache,ev/'ssdk-clean.log')
  run(['make','package/kernel/qca/qca-ssdk/prepare','V=s'],cache,ev/'ssdk-prepare.log')
  ssdk_source=NG.native_ssdk_source_gate(R,True)
  ssdk_started_ns=time.time_ns()
  run(['make','package/kernel/qca/qca-ssdk/compile','V=s'],cache,ev/'ssdk-compile.log')
  ssdk_build_audit=NG.verify_native_ssdk_build(ssdk_pkg,ssdk_started_ns,ev/'ssdk-compile.log')
  ssdk_unstripped=ev/'qca-ssdk-fresh-module.ko';shutil.copy2(ssdk_pkg/'build/bin/qca-ssdk.ko',ssdk_unstripped)
  ssdk_stage=Path(ssdk_build_audit['staged_module']);ssdk_report=ev/'qca-ssdk-staged-module-binding.json'
  with (ev/'qca-ssdk-staged-module-binding.log').open('w') as audit_log:
   subprocess.run([sys.executable,str(R/'rt3000-machine-c/tools/audit_ath11k_symbols.py'),'--packaged',str(ssdk_stage),'--unstripped',str(ssdk_unstripped),'--output',str(ssdk_report)],cwd=R,stdout=audit_log,stderr=subprocess.STDOUT,check=True)
  ssdk_build_audit['stage_elf_allocated_binding']={'report_sha256':sha(ssdk_report),'status':'PASS'}
  inputs['ssdk_source_audit']=ssdk_source;inputs['ssdk_build_audit']=ssdk_build_audit;inputs['ssdk_build_started_ns']=ssdk_started_ns
  (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 run(['make','package/kernel/mac80211/clean'],cache,ev/'mac80211-clean.log')
 mac80211_started_ns=time.time_ns()
 run(['make','package/kernel/mac80211/compile','V=s'],cache,ev/'mac80211-clean-compile.log')
 bp=cache/'build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/backports-20210222-5.4-qsdk-11.5.0.5/.config'
 ah=bp.parent/'backport-include/backport/autoconf.h'
 if not bp.is_file() or not ah.is_file():raise RuntimeError('fresh ath11k backports config/autoconf missing')
 bpcfg=bp.read_text().splitlines()
 if 'CPTCFG_ATH11K_RT3000_REO_IDR_CLAIM=y' not in bpcfg:raise RuntimeError('610 ownership repair is not compiled in')
 if a.enable_c_native_tx_coherent_diag and 'CPTCFG_ATH11K_RT3000_TX_UNKNOWN_DIAG=y' not in bpcfg:raise RuntimeError('623/624 TX diagnostic not compiled')
 rx_source_overrides=installer_rx_622_compiled_source_overrides(a.enable_c_native_tx_coherent_diag)
 rx_compiled=(NG.verify_native_rx_625_objects(bp.parent,bp,ah,mac80211_started_ns,ev/"mac80211-clean-compile.log",compiled_source_overrides=rx_source_overrides) if a.enable_c_native_rx_width_join else NG.verify_native_rx_620_621_622_objects(bp.parent,bp,ah,mac80211_started_ns,ev/"mac80211-clean-compile.log",compiled_source_overrides=rx_source_overrides))
 tx_compiled=NG.verify_native_tx_623_624_objects(bp.parent,bp,ah,mac80211_started_ns,ev/'mac80211-clean-compile.log') if a.enable_c_native_tx_coherent_diag else None
 dsa_before=NG.prepare_fresh_native_dsa_objects(qdir,ev)
 dsa_started_ns=time.time_ns()
 inputs['fresh_source_build_policy']={'mac80211_clean':True,'rx_620_621_622':rx_compiled,'tx_623_624':tx_compiled,'dsa_objects_removed_before_build':dsa_before}
 (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 full_make_started_ns=time.time_ns()
 run(['make','-j'+str(a.jobs),'V=sc'],cache,ev/'installer-build.log')
 if ssdk_build_audit is not None:
  ssdk_final_build_audit=NG.verify_native_ssdk_build(ssdk_pkg,full_make_started_ns,ev/'installer-build.log',dependency_proof=ssdk_build_audit)
  ssdk_final_module=ev/'qca-ssdk-final-module.ko';shutil.copy2(ssdk_pkg/'build/bin/qca-ssdk.ko',ssdk_final_module)
  ssdk_final_stage=Path(ssdk_final_build_audit['staged_module']);ssdk_final_report=ev/'qca-ssdk-final-staged-module-binding.json'
  with (ev/'qca-ssdk-final-staged-module-binding.log').open('w') as audit_log:
   subprocess.run([sys.executable,str(R/'rt3000-machine-c/tools/audit_ath11k_symbols.py'),'--packaged',str(ssdk_final_stage),'--unstripped',str(ssdk_final_module),'--output',str(ssdk_final_report)],cwd=R,stdout=audit_log,stderr=subprocess.STDOUT,check=True)
  ssdk_final_build_audit['fullmake_log_sha256']=sha(ev/'installer-build.log')
  ssdk_final_build_audit['fullmake_started_ns']=full_make_started_ns
  ssdk_final_build_audit['final_module_sha256']=sha(ssdk_final_module)
  ssdk_final_build_audit['final_stage_elf_allocated_binding']={'report_sha256':sha(ssdk_final_report),'status':'PASS'}
  inputs['ssdk_pre_fullmake_build_audit']=ssdk_build_audit
  inputs['ssdk_build_audit']=ssdk_final_build_audit
  inputs['ssdk_fullmake_started_ns']=full_make_started_ns
  (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 if ssdk_final_build_audit is not None:
  rootfs_ssdk=list(cache.glob('build_dir/target-*/root-ipq50xx/lib/modules/*/qca-ssdk.ko'))
  if len(rootfs_ssdk)!=1:raise RuntimeError('installer rootfs SSDK module missing/ambiguous')
  report=ev/'qca-ssdk-final-rootfs-module-binding.json'
  with (ev/'qca-ssdk-final-rootfs-module-binding.log').open('w') as audit_log:
   subprocess.run([sys.executable,str(R/'rt3000-machine-c/tools/audit_ath11k_symbols.py'),'--packaged',str(rootfs_ssdk[0]),'--unstripped',str(ev/'qca-ssdk-final-module.ko'),'--output',str(report)],cwd=R,stdout=audit_log,stderr=subprocess.STDOUT,check=True)
  ssdk_final_build_audit['final_rootfs_elf_allocated_binding']={'report_sha256':sha(report),'status':'PASS','rootfs_module_sha256':sha(rootfs_ssdk[0])}
  inputs['ssdk_build_audit']=ssdk_final_build_audit
  (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 dsa_compiled=NG.verify_native_dsa_compiled_sources(qdir,dsa_started_ns,ev/'installer-build.log')
 bwpatch=R/'package/kernel/mac80211/patches/all-ipq50xx/613-ath11k-qcn6122-bw-trace.patch'
 if not bwpatch.is_file() or 'static bool ath11k_qcn6122_rx_bw_trace_enable;' not in bwpatch.read_text():raise RuntimeError('613 trace source missing or no longer default-off')
 if 'static bool ath11k_qcn6122_rx_bw_trace_enable = true;' in bwpatch.read_text():raise RuntimeError('613 trace default must remain off')
 module_names=('ath11k.ko','ath11k_ahb.ko','ath11k_pci.ko')
 module_dir=cache/'build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq50xx/lib/modules/5.4.164'
 modules={name:module_dir/name for name in module_names}
 if any(not p.is_file() for p in modules.values()):raise RuntimeError('ath11k module trio missing from installer rootfs')
 module_binding_audit=verify_installer_ath11k_module_bindings(modules,bp.parent,mac80211_started_ns,ev/'mac80211-clean-compile.log',ev)
 module_marker_audit=NG.verify_native_rx_625_module_marker(modules['ath11k.ko']) if a.enable_c_native_rx_width_join else None
 module_out=ev/'modules';module_out.mkdir(mode=0o700)
 for name,src in modules.items():shutil.copy2(src,module_out/name)
 if b'qcn6122_rx_bw_trace' not in modules['ath11k.ko'].read_bytes():raise RuntimeError('compiled ath11k lacks 613 trace parameter marker')
 rx_module=NG.verify_native_rx_622_module_marker(modules['ath11k.ko'])
 tx_module=NG.verify_native_tx_623_624_module_marker(modules['ath11k.ko']) if a.enable_c_native_tx_coherent_diag else None
 shutil.copy2(bp,ev/'backports.config')
 kdir_src=cache/'build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5'
 for rel,want in MTD_PATCHED.items():
  p=kdir_src/rel
  if sha(p)!=want:raise RuntimeError('425 patched kernel source hash mismatch '+rel)
 qobj=kdir_src/'drivers/mtd/nand/raw/qcom_nandc.o'
 if not qobj.is_file() or qobj.stat().st_mtime_ns < (kdir_src/'drivers/mtd/nand/raw/qcom_nandc.c').stat().st_mtime_ns:raise RuntimeError('qcom_nandc.o missing or stale relative to guarded source')
 # Cross-compile the preflight helper with this cache's locked ARM compiler; retain only in evidence.
 toolchain=cache/'staging_dir/toolchain-arm_cortex-a7+neon-vfpv4_gcc-8.4.0_musl_eabi/bin/arm-openwrt-linux-muslgnueabi-gcc'
 if not toolchain.is_file():raise RuntimeError('locked ARM compiler missing')
 helper=R/'rt3000-machine-c/tools/c_mtd_target_preflight_ro.c'; helper_bin=ev/'c_mtd_target_preflight_ro.arm'
 run([str(toolchain),'-Wall','-Wextra','-Werror','-O2','-o',str(helper_bin),str(helper)],R,ev/'preflight-helper-arm-build.log')
 if not helper_bin.is_file():raise RuntimeError('ARM preflight helper output missing')
 kcs=list(cache.glob('build_dir/target-*/linux-*/linux-*/.config'))
 if len(kcs)!=1:raise RuntimeError('kernel config ambiguous')
 kc=kcs[0];kl=kc.read_text().splitlines()
 for x in ('CONFIG_BLOCK=y','CONFIG_MTD=y','CONFIG_MTD_OF_PARTS=y','CONFIG_MTD_NAND_CORE=y','CONFIG_MTD_RAW_NAND=y','CONFIG_MTD_NAND_QCOM=y','CONFIG_QCOM_BAM_DMA=y'):
  if x not in kl:raise RuntimeError('required NAND probe config missing '+x)
 for x in ('CONFIG_MTD_UBI','CONFIG_MTD_UBI_BLOCK','CONFIG_UBIFS_FS','CONFIG_SQUASHFS','CONFIG_OVERLAY_FS'):
  if x+'=y' in kl:raise RuntimeError('installer kernel must keep '+x+' disabled')
 if 'CONFIG_MTD_PARTITIONED_MASTER=y' in kl:raise RuntimeError('master MTD exposure enabled')
 shutil.copy2(kc,ev/'kernel.config')
 kdir=kc.parent;vmlinux=kdir/'vmlinux';image=kdir/'arch/arm/boot/Image'
 if not vmlinux.is_file() or not image.is_file():raise RuntimeError('kernel output missing')
 fitlist=list(cache.glob('bin/targets/ipq50xx/arm/*rtl8367s_installer_ram-initramfs*.itb'))
 if len(fitlist)!=1:raise RuntimeError('installer FIT missing/ambiguous '+repr([str(x) for x in fitlist]))
 fit=fitlist[0];shutil.copy2(fit,ev/fit.name);fit=ev/fit.name
 root=cache/'build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq50xx'
 dtb_raw=subprocess.check_output(['fdtget','-t','bx',str(fit),'/images/fdt@1','data'])
 dtb=ev/'installer.dtb';dtb.write_bytes(bytes(int(x,16) for x in dtb_raw.split()))
 bootargs='console=ttyMSM0,115200n8 init=/init panic=0'
 run([sys.executable,str(R/'rt3000-machine-c/tools/audit_native_dtb.py'),str(dtb),'--mode','installer','--kernel-config',str(ev/'kernel.config'),'--output',str(ev/'installer-dtb-audit.json')],R,ev/'installer-dtb-audit.log')
 run([sys.executable,str(R/'rt3000-machine-c/tools/audit_c_installer_initramfs.py'),'--openwrt-config',str(ev/'resolved.config'),'--kernel-config',str(ev/'kernel.config'),'--rootfs',str(root),'--vmlinux',str(vmlinux),'--kernel-image',str(image),'--dumpimage',str(cache/'build_dir/host/u-boot-2021.01/tools/dumpimage'),'--bootargs',bootargs,'--fit',str(fit),'--fit-config','config@mp03.1-c2','--output',str(ev/'initramfs-audit.json')],R,ev/'initramfs-audit.log')
 cpio=list(kdir.glob('usr/initramfs_data.cpio.lzma'))
 if len(cpio)!=1:raise RuntimeError('compressed initramfs cpio missing/ambiguous')
 shutil.copy2(cpio[0],ev/'initramfs_data.cpio.lzma');shutil.copy2(ev/'resolved.config',ev/'openwrt.config')
 run([sys.executable,str(R/'rt3000-machine-c/experiments/installer-runtime-contract/audit_installer_runtime.py'),str(ev), '--dtc',(shutil.which('dtc') or 'dtc')],R,ev/'runtime-contract-audit.log')
 inputs['compiled_source_closure']={'rx_620_621_622':rx_compiled,'tx_623_624':tx_compiled,'native_dsa':dsa_compiled}
 inputs['ath11k_module_binding_audit']=module_binding_audit
 (ev/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 report={'status':'C_INSTALLER_STATIC_PASS','profile':prof['profile'],'fit':fit.name,'fit_sha256':sha(fit),'fit_size':fit.stat().st_size,'input_manifest_sha256':sha(ev/'inputs.json'),'resolved_config_sha256':sha(ev/'resolved.config'),'kernel_config_sha256':sha(ev/'kernel.config'),'dtb_sha256':sha(dtb),'installer_dtb_audit_sha256':sha(ev/'installer-dtb-audit.json'),'initramfs_audit_sha256':sha(ev/'initramfs-audit.json'),'runtime_contract_audit_sha256':sha(ev/'runtime-contract-audit.log'),'qcom_source_sha256':sha(kdir/'drivers/mtd/nand/raw/qcom_nandc.c'),'mtd_source_sha256':{rel:sha(kdir_src/rel) for rel in MTD_PATCHED},'qcom_object_rebuilt':True,'preflight_helper_arm_sha256':sha(helper_bin),'backports_config_sha256':sha(ev/'backports.config'),'ath11k_modules':{name:sha(module_out/name) for name in module_names},'ath11k_module_binding_audit':module_binding_audit,'ssdk_pre_fullmake_build_audit':ssdk_build_audit,'ssdk_build_audit':ssdk_final_build_audit,'ath11k_rx_622_marker':rx_module,'ath11k_tx_623_624_marker':tx_module,'native_dsa_source_object_audit':dsa_compiled,'reo_idr_claim_enabled':True,'qcn6122_bw_trace_default_off':True,'tx_diag_runtime_default_off':True,'qcom_object_sha256':sha(kdir/'drivers/mtd/nand/raw/qcom_nandc.o'),'vmlinux_sha256':sha(vmlinux),'kernel_image_sha256':sha(image),'flash_ready':False,'device_runtime':'NOT_EXECUTED','wireless_probe_only':True,'wifi_runtime':'NOT_EXECUTED'}
 (ev/'artifact.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
