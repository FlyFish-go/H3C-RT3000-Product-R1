# Product R1 r5 — Developer Preview

> ⚠️ **实验性预发布。** 请在动手前完整阅读 [已更正的安装教程](INSTALL.md)。`r5` 标签保留发布当时的源码快照，旧版教程中把 B 机配置头 D009 误写成原厂软件版本；请以此处更正说明和最新教程为准。
>
> 2026-09-23 已在 RT3000 Machine-B 上按当前教程复走安装、读回、主动双向切换、保留配置升级和恢复出厂。原厂 Telnet 配置导入本轮未重复执行；配套工具已在三份不同配置头的 RT3000 原厂备份上离线复核，输出分别与已有启用版逐字节一致。故障注入、断电和完整 U-Boot + TFTP 救援仍未实测。

**版本勘误**：B 机网页和 `display version` 的软件版本是 `RT3000V100R005`；同一台 B 机导出的配置文件第二行是 `RT3000/RT3000V100D009`。这两个字段用途不同，不能据 D009 将 B 机备份认作另一台设备。另两台样机的配置头字段为 `RT3000V100D012`、`RT3000V100D023`；这些字段也不能直接替代各自网页／CLI 的软件版本。**下述固件镜像仍只在 B 机实测，配置工具的离线兼容结果不扩大镜像适用范围。**

📦 **[直接下载原厂 Telnet 一键工具 ZIP](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/download/r5/RT3000-OEM-Telnet-OneClick-r5-corrected.zip)**（SHA-256：`3a28ef6bd025caee0b58136fedcc530ecf95b63565e2d582592168679d170120`）。解压后按[第一部分教程](01-GET-TELNET.md)操作；ZIP 不包含用户配置备份。

---

## 这是什么

H3C Magic RT3000（**Machine-B**）的双槽位固件。

在**不改动原厂系统**的前提下，把 OpenWrt 21.02.7 + Qualcomm QSDK 11.5 装进第二个 NAND 槽位，
并支持在原厂系统与 QSDK 之间**双向切换**。

**版本识别**：`r5` 是本次对外发布标签；已实机验证的镜像内部清单仍写作 `Product R1 Upgrade Preview`。这是同一组镜像的内部构建名称，不代表另一款硬件或另一个可互换版本。识别附件请以本页文件大小、SHA-256 和内部 kernel/rootfs 校验值为准；本次没有为了改名称重新构建镜像。

| | |
|---|---|
| SoC | Qualcomm IPQ5018 |
| 平台 | QSDK 11.5（NHSS.QSDK.11.5.0.5） |
| 内核 | Linux 5.4.164 |
| 用户空间 | OpenWrt 21.02.7（r16847-f8282da11e） |
| NAND | 128 MiB（GigaDevice `GD5F1GQ5REYIG`） |
| 槽位 | A = 原厂（`mtd15`）／B = QSDK（`mtd16`） |
| 界面 | 中文 LuCI + 网页终端（TTYD） |

---

## 本版修复了什么

### WiFi 关联缺陷（重要）

**r4 版本存在 WiFi 无法连接的问题**：设备能广播、客户端能认证、能关联，
但**无法完成密钥握手** —— 表现为「连不上 WiFi」、反复重连，日志里是：

```
nl80211: NL80211_ATTR_STA_VLAN (... vlan_id=0) failed: -34
```

**根因**：`ath11k` 声明了 `VLAN_OFFLOAD` 能力，导致 hostapd 在关联时
多发一个内核不接受的属性值（`vlan_id=0`），整条设置命令被内核以 `-ERANGE` 拒绝。

**修复**：让 hostapd 在「不绑定 VLAN」时不发送该属性。

| | |
|---|---|
| 补丁 | `package/network/services/hostapd/patches/803-nl80211-only-set-VLAN-ID-when-non-zero.patch` |

> ⚠️ **说明**：这个问题**并非所有历史版本都存在**。
> 更早的测试版本有真实客户端成功关联并跑出吞吐的记录。
> **为什么某些版本正常、r4 不正常，原因尚未完全确定。**
> r5 已通过上述补丁消除了该现象。

**实机验证**：2.4G / 5G 均可连接、能上网、能断开重连、能双频切换。

---

## 本版还包含

| 项 | 内容 |
|---|---|
| 默认 LAN | `192.168.10.1`（与 OEM 一致，避免与常见家用网关冲突） |
| 默认 WiFi | 2.4G `RT3000` / 5G `RT3000-5G`，**均开启**，WPA2，密码 `RTRCRWNX` |
| 5G 频宽 | `HE80`（比 HE160 更易落在非 DFS 信道；**是否需要 DFS 取决于实际选用信道**，不能仅凭频宽保证） |
| 中文界面 | 首次启动自动选择中文（保留用户显式选择） |
| 软件源 | 用户空间包指向国内镜像；内核包走本项目构建 |
| 升级脚本 | `rt3000.sh`：修复 `/dev/ubi*` 节点缺失、NAND→NAND 升级、配置保留 |

> 🔑 **首次登录请立即设置 root 密码。**
> 新装的 QSDK 没有 root 密码，且 SSH 只绑 LAN 口。
> 在设置密码前，任何能访问 LAN 的人都能以 root 登录。

---

## 附件

| 文件 | 大小 | 用途 |
|---|---:|---|
| `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi` | 13,107,200 | **首次安装**（从原厂写入第二槽位） |
| `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-sysupgrade.bin` | 12,299,027 | **升级**（QSDK → 新 QSDK） |
| `openwrt-ipq50xx-arm-h3c_rt3000-initramfs-fit-uImage.itb` | 10,988,236 | **救援**（内存系统） |
| `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-release.json` | 398 | 发布身份清单 |
| `openwrt-ipq50xx-arm.manifest` | 4,522 | 包清单 |
| `SHA256SUMS` | — | 校验值 |
| [`RT3000-OEM-Telnet-OneClick-r5-corrected.zip`](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/download/r5/RT3000-OEM-Telnet-OneClick-r5-corrected.zip) | 5,263 | Windows 原厂配置一键开启 Telnet 工具；更正说明，不含用户配置 |

### 校验值

```
80e99811887ec3bedaf648a32954d93fc5e1482ab70605d6e41d791ce181c529  openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi
7f8f9e5dca42bc0b1fdb0c5dc9d01f8863878631202d2d325df6cd659bf1d65a  openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-sysupgrade.bin
65a374d29ab533788e2b51e96878ace57c582034a1ce2f8329747cd78a043a31  openwrt-ipq50xx-arm-h3c_rt3000-initramfs-fit-uImage.itb
51d17fbd3a93a0e9d20b60003e9467f00cb7bcdc5d69198885a191a3435e1359  openwrt-ipq50xx-arm-h3c_rt3000-squashfs-release.json
258ae87574d4b0a9bf48b570aebc5d12600e385b025369c73f167727c43d3764  openwrt-ipq50xx-arm.manifest
3a28ef6bd025caee0b58136fedcc530ecf95b63565e2d582592168679d170120  RT3000-OEM-Telnet-OneClick-r5-corrected.zip
```

**下载后请核对**：

```bash
sha256sum -c SHA256SUMS      # Linux
```

macOS 可用 `shasum -a 256 文件名`，逐项对照上面的校验值。

```cmd
certutil -hashfile openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi SHA256
```

### 镜像内部载荷

| 载荷 | 长度 | SHA-256 |
|---|---:|---|
| `kernel` | 3,474,820 | `7a7c048e92bcd53bfdba554770195adbbaf4cf4deb0d383d4f3c85ba881c31c9` |
| `rootfs` | 8,810,094 | `31115a4c01c29357f6ed1e27a1f5007ef6e25904342054be48542610c5605f74` |

### 槽位切换工具

**不在附件里，在仓库中**：`rt3000-machine-b/release/tools/rt3bcwrite`

```
e23d8634af3fb20a5c383aa22ad2dc65752133ffd91d3715a70df5121d0789f5
```

> 原厂固件里没有这个工具，首次安装时需要从电脑传进设备。

---

## 安装

完整步骤见 **[rt3000-machine-b/release/INSTALL.md](INSTALL.md)**。

概要：

```
第一部分  获取 telnet          （改一个配置开关；不刷写系统镜像，但会修改并保存原厂配置）
刷写前    保存 OEM 备份       （原厂 .cfg 与本机 mtd15 读取备份；大小和 SHA-256 核对）
第二部分  安装 QSDK            （写入 mtd16，含保命检查与读回校验）
第三部分  双向切换             （只更新两份 BOOTCONFIG 中的启动选择；不刷写系统镜像）
第四部分  固件升级
第五部分  救援
```

### 适用范围

**仅在下列硬件上实机验证**：

| 项 | 值 |
|---|---|
| 型号 | H3C Magic RT3000 |
| 硬件平台 | **Machine-B** |
| NAND | GigaDevice `GD5F1GQ5REYIG`（128 MiB） |
| 原厂固件 | Chaos Calmer 15.05.1 / Linux 4.4.60；网页／CLI 软件版本 `RT3000V100R005` |
| 同机导出配置的第二行 | `RT3000/RT3000V100D009`（配置头字段，不是软件版本） |
| U-Boot | `H3C RT3000 Boot, Version 100`，启动配置 `config@mp02.1` |

> 🔴 **RT3000 存在不同硬件批次。**
> 如果你的分区表或 NAND 型号与上表不同，**请先停下** ——
> 尤其**分区表不同**时，教程里的 `mtd15` / `mtd16` 引用可能指向错误的分区。

---

## ⚠️ 安全边界（必读）

本方案有多重保护，但**保护机制不等于「一定救得回来」**。

### 已实测

| 能力 | 验证方式 |
|---|---|
| 从原厂安装 QSDK 到 `mtd16` | ✅ 完整走通 |
| 从 NAND 启动 QSDK | ✅ |
| **主动双向切换**（只更新启动选择，不刷写系统镜像） | ✅ 含配置逐字节保留证据 |
| 保留配置升级（`sysupgrade`） | ✅ |
| 恢复出厂（`sysupgrade -n`） | ✅ |

### 🔴 未实测 / 无法保证

| 事项 | 实际状态 |
|---|---|
| **切到 QSDK 后启动失败，是否自动回退原厂** | **未验证**。机制上 U-Boot 会读 selector，但失败时的行为未实测。 |
| **写入 / 升级过程中断电** | **未实测**。机制上启动目标仍指向原厂，但这只是推断。 |
| **原厂内容完好 ⇒ 无需串口就能切回** | **不成立**。切回需要能运行命令的环境。 |
| **两个系统都无法启动** | 需要 **TTL 串口 + U-Boot**。该救援路径**未端到端验证**。 |

> **结论**：
> **保护机制降低风险，但不能替代两件事 —— 备份，以及串口救援的准备（TTL 线）。**

### 从不触碰

| 项 | 状态 |
|---|---|
| `mtd15`（原厂系统） | 全程不写入 |
| bootloader | 不修改 |
| 分区表 | 不修改 |
| U-Boot 持久化环境 | 不执行任何 `saveenv` |

---

## 已知问题

见 **[rt3000-machine-b/release/KNOWN_ISSUES.md](KNOWN_ISSUES.md)**。

---

## 回退到原厂

在 QSDK 里执行一条命令：

```sh
rt3slot oem --reboot
```

**这只更新启动选择，不重写、不删除 QSDK**。需要从原厂返回时，先确认原厂正常启动且能进入 shell，再按教程第三部分操作。

详见[第三部分：双向切换](03-SWITCH-SYSTEMS.md)。

---

## 反馈

欢迎反馈，尤其是**照着教程走时卡住的地方**。请附上：

- 卡在哪一步
- **实际输出** vs 文档预期
- 你的**硬件版本**（`cat /proc/mtd` 和 `uname -r` 的输出）

维护者联系方式见 [PUBLICATION.md](../docs/PUBLICATION.md)。

---

## 上游与许可证

本项目基于 OpenWrt 21.02.7 与 Qualcomm QSDK 11.5。
原有上游许可证与署名保留，见 [LICENSES/](../../LICENSES/) 与 [COPYING](../../COPYING)。

> ⚠️ **本发布为实验性 Developer Preview，不提供任何担保。**
