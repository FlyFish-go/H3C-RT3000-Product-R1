# Installation — H3C Magic RT3000 (Machine-B)

**This is a Developer Preview. Read this whole page before starting.**

## 从原厂系统写入并启动第二槽位

**状态：教程预留，待研究与实机确认后补充。** 本页当前不提供可执行的刷写步骤，也不对应新的固件二进制发布。B 机已有 NAND 写入与双系统启动验证记录，但面向用户的原厂安装流程还需要整理和确认。

### 1. 安装前准备

待补充：支持的机型与硬件版本、原厂固件版本、镜像类型与 SHA256、所需工具、连接方式。

### 2. 备份与第二槽位确认

待补充：需要备份的内容、备份校验、第二槽位的识别方法、恢复准备及可继续操作的判据。

### 3. 从原厂系统写入第二槽位

待补充：原厂系统进入方式、镜像传输、写入操作、完整性校验、完成与失败的判据。

### 4. 切换并启动第二槽位

待补充：启动选择操作、重启过程、首次启动的预期输出、未正常启动时的处理方式。

### 5. 安装后验证与原厂回退

待补充：运行镜像身份、网络与无线检查、返回原厂系统的方法及回退成功判据。

已有 B 机机制与验收记录：[RECOVERY](RECOVERY.md)、[Product R1 预发布验收](../docs/PRODUCT_R1_PRERELEASE_1_ACCEPTANCE.md)。这些记录供理解已验证机制使用，不替代上面的待补安装教程。

---

以下是启动成功后的管理配置说明，不是刷写步骤。

## First-time setup — do this before anything else

1. Connect a computer to a **LAN** port (not the WAN port).
2. Open `http://192.168.1.1/`.
3. **Set a root password immediately**: System → Administration.
   A fresh install has no root password. Until you set one, anyone who can
   reach the LAN can log in as root.
4. Current source defaults enable the open 2.4 GHz `RT3000` debugging AP on LAN.
   Set WPA2/WPA3 encryption in Network → Wireless before daily use.
   5 GHz remains disabled; configure it before enabling it.
5. Connect the WAN port to your uplink.

## Security defaults

- WAN management is denied by default. SSH and LuCI are not reachable from the
  WAN side and there is no supported way to change that in this release.
- Current source enables 2.4 GHz `RT3000` without a password for debugging;
  5 GHz remains disabled. These fresh-install / factory-reset defaults are
  source changes, not yet rebuilt or tested on hardware. No live-device
  settings were changed during this source update; historical RC1/C13 test
  results retain their original scope.
- No shared or factory-wide credential is built into this firmware.
