<div align="center">

# H3C Magic · QSDK 11.5 固件

**H3C RT3000 / RW3000 / RC3000 / NX30 的高通 QSDK 11.5 OpenWrt 固件**

四种主板全部实机跑通 · NSS 硬件加速有线 NAT 约 940 Mbps · Wi-Fi 6 双频 · 与原厂系统共存

[![Release](https://img.shields.io/badge/release-r6-e76f51)](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6)
[![QSDK](https://img.shields.io/badge/QSDK-11.5-2a9d8f)](#)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-21.02.7-00a3e0)](#)
[![Kernel](https://img.shields.io/badge/Linux-5.4.164-555)](#)
[![QQ群](https://img.shields.io/badge/QQ群-1131957442-12b7f5)](#交流与反馈)
[![Stars](https://img.shields.io/github/stars/FlyFish-go/H3C-RT3000-Product-R1?style=social)](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/stargazers)

### [⬇️ 下载 r6 固件](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6)

[安装教程](#安装) · [先装 U-Boot（BootBridge）](https://github.com/FlyFish-go/H3C-NX30-Uboot) · [性能](#性能) · [QQ 群 1131957442](#交流与反馈) · [English](README_EN.md)

</div>

## 为什么是 QSDK

RT3000 这一系列用的是高通 IPQ50xx（IPQ5018 / IPQ5000）+ QCN6102。本项目用高通官方 SDK 的供应商内核、无线驱动和 NSS 网络加速栈，而不是 OpenWrt 主线：

- **⚡ NSS 硬件加速**：有线 WAN↔LAN 路由由 NSS/ECM 转发，四种主板实测 939～942 Mbps，CPU 占用很低（HW-A 实测约 1.5%）。
- **📶 Wi-Fi 6 双频**：2.4 GHz + 5 GHz（QCN6102），ath11k 2.7 固件，开机从本机 ART 分区读取校准数据，每台设备用自己的出厂校准。
- **🧩 一套源码，四种主板**：同一份源码和配置为 HW-A/B/C/D 各出一个镜像，出厂默认值和系统内升级方式一致。
- **🔀 不动原厂系统**：配合 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) 写进另一个系统槽，原厂系统随时可以切回。也支持 80 MiB 大分区。
- **🏷️ 保留设备身份**：MAC 地址按原厂规则从本机出厂地址派生，镜像不含任何一台设备的私有数据。

## 支持的设备

| 主板 | 商品型号 | 芯片 / 交换机 | r6 镜像 | 实机测试 |
|---|---|---|---|:---:|
| **HW-A** | RW3000 / RC3000 | IPQ5018 · QCA8337 | `H3C-Magic-r6-HW-A-*` | ✅ RW3000 |
| **HW-B** | RT3000 | IPQ5000 · QCA8337 | `H3C-Magic-r6-HW-B-*` | ✅ RT3000 |
| **HW-C** | RT3000 | IPQ5018 · RTL8367S | `H3C-Magic-r6-HW-C-*` | ✅ RT3000 |
| **HW-D** | NX30 / RX3000 | IPQ5000 · QCA8337 | `H3C-Magic-r6-HW-D-*` | ✅ NX30 |

同一商品型号可能用不同主板（RT3000 有 HW-B 和 HW-C 两种），**请按 U-Boot 救援页显示的「硬件系列」选镜像，不要按型号或 machid 猜**。用错组的镜像，网口、无线或启动都可能不正常。分组依据见 [HW-A/B/C/D 分类](docs/HW-ABCD-CLASSIFICATION.md)。

## 性能

r6 正式镜像，每种主板一台样机。iperf3 4 流，客户端为 MT7921（Wi-Fi 6，2×2，近距离）；有线 NAT 为 LAN → 路由器 NAT → WAN。单位 Mbps，上行 / 下行：

| 主板 | 5 GHz HE80 | 2.4 GHz HE20 | 有线 NAT | 空闲可用内存 |
|---|---|---|---|---|
| HW-A | 646 / 729 | 216 / 102 | **942 / 942** | 约 73 MB |
| HW-B | 727 / 692 | 200 / 114 | **941 / 942** | 约 72 MB |
| HW-C | 672 / 774 | 213 / 187 | **941 / 942** | 约 52 MB |
| HW-D | 727 / 729 | 188 / 174 | **939 / 939** | 约 53 MB |

无线速率受测试客户端限制（2×2 网卡、HE80），不代表硬件上限。早期在 RT3000 上用手机测过 HE160 单流上传 760～789 Mbps，见下方[项目历程](#项目历程)。

## 安装

**前提：** 先装好 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) 的 U-Boot **v0.1.0-pre.5**。还在原厂系统的设备用 [BootBridge 网页版](https://flyfish-go.github.io/H3C-NX30-Uboot/)安装，不用拆机、不用 TTL。

| 主板 | 首次写入（救援页） | 系统内升级（LuCI） |
|---|---|---|
| HW-A | `H3C-Magic-r6-HW-A-nand-factory.ubi` | `H3C-Magic-r6-HW-A-sysupgrade.bin` |
| HW-B | `H3C-Magic-r6-HW-B-nand-factory.ubi` | `H3C-Magic-r6-HW-B-sysupgrade.bin` |
| HW-C | `H3C-Magic-r6-HW-C-nand-factory.ubi` | `H3C-Magic-r6-HW-C-sysupgrade.bin` |
| HW-D | `H3C-Magic-r6-HW-D-nand-factory.ubi` | `H3C-Magic-r6-HW-D-sysupgrade.bin` |

1. 断电后按住 Reset 再通电，进入救援页；电脑用网线接 **LAN** 口，打开 `http://192.168.10.1`。
2. 在「闪存备份」先备份两个系统槽。
3. 在「固件更新」把对应主板的 `nand-factory.ubi` 写入**不是原厂系统所在**的那个槽。两个槽以偏移（`0x900000` / `0x3100000`）为准。
4. 把默认启动槽设为刚写入的槽，断电重启。
5. 以后升级在 LuCI「备份/升级」上传 `sysupgrade.bin`，可保留配置。

想回原厂：在救援页把默认启动槽改回原厂系统所在的槽即可。

QSDK 也能装进 U-Boot「分区表更新」生成的 80 MiB 大分区。大分区会抹掉原厂系统，只在确定不再需要原厂系统时使用。

### 默认设置

- LAN 地址 `192.168.10.1`，LuCI 为 `http://192.168.10.1/`；SSH 只在 LAN 侧开放。
- 新装系统没有 root 密码，首次登录请立即设置。
- 2.4 GHz `OpenWrt` 与 5 GHz `OpenWrt-5G` 默认启用 WPA2，密码 `12345678`，国家码 CN。这是公开默认值，请尽快更换。
- MAC 地址与原厂编号一致：WAN 为出厂地址，LAN、2.4 GHz、5 GHz 依次为出厂地址 +1、+2、+3。从 r5 升级会改变这三个地址。

## 测试范围与已知限制

每种主板一台样机，测试的就是 r6 Release 里的附件：救援页写入非原厂槽 → 启动检查（型号、槽位、MTD 映射、UBI 无错误）→ 系统内升级并保留配置 → 连续 5 次断电冷启动，每次两个射频、两个 AP 都正常，无固件断言。四种主板全部通过。

- 每种主板只有一台样机，其他 NAND 型号和批次还没验证。
- LAN 内无线与有线之间的桥接流量由 CPU 转发，没有 NSS 加速；WAN↔LAN 路由有加速。
- HW-C / HW-D 沿用原厂的 Q6 内存预留，可用内存比 HW-A / HW-B 少约 20 MB。
- 10/100 Mbps、长时间运行、LED / 按键还没完整验证。

详见 [KNOWN_ISSUES](rt3000-machine-b/release/KNOWN_ISSUES.md)。

## 从源码构建

```sh
git clone https://github.com/FlyFish-go/H3C-RT3000-Product-R1.git
cd H3C-RT3000-Product-R1
```

先阅读[公开源码构建说明](rt3000-machine-b/docs/BUILD_PUBLIC.md)。r6 镜像用 [`configs/h3c-magic.config`](configs/h3c-magic.config) 构建：复制为 `.config`，按文件头说明追加一行机型（HW-C 另加两行），再执行 `make defconfig && make`。

| 路径 | 内容 |
|---|---|
| `target/linux/ipq50xx/` | 四种主板的 DTS、网络及系统集成 |
| `package/kernel/mac80211/` | ath11k、NSS/WIFILI 和诊断补丁 |
| `package/firmware/ipq-wifi/` | 型号级 BDF 文件和封装规则 |
| `configs/` | r6 构建配置 |
| `docs/` | 硬件分组与硬件研究 |
| `rt3000-machine-b/` | 工具、测试、验收记录和镜像身份清单 |

## 交流与反馈

- **QQ 群：1131957442**（交流、提问、反馈问题都可以）
- [GitHub Issues](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues)：请附上主板（HW-A/B/C/D）、镜像 SHA-256、复现步骤和去掉序列号的日志。吞吐问题请注明上传/下载、流数和测试拓扑。

**如果这个固件让你的路由器焕发了第二春，欢迎点一个 ⭐ Star，让更多同型号的用户看到它。**

## 支持项目

这个项目由我个人开发和维护。最需要的是能放到桌面上反复验证的实体设备：

1. **实体样机（最优先）。** 闲置的 RT3000 / RW3000 / RC3000 / NX30，尤其是不同 NAND、交换机或 PCB 批次的设备，欢迎捐赠或借测。能正常启动的整机最有帮助；故障机、主板也可以先说明型号和故障情况。
2. **资金赞助。** 用于购买和维修样机、调试配件和运输等开发成本。请通过邮箱联系。
3. **测试与资料。** 硬件照片、芯片丝印、原厂版本信息和脱敏测试日志，都能减少重复摸索。

**联系邮箱：[yufeiyang45@qq.com](mailto:yufeiyang45@qq.com)**。提供样机时请注明型号、硬件版本、设备状态，以及捐赠还是借测；寄送前请先邮件确认。赞助是对持续开发的支持，不能保证某个机型的完成时间或适配结果。

## 项目历程

<details>
<summary>从一台 RT3000 到四种主板（点击展开）</summary>

- **r5（2026-09）**：Product R1 第一个实机里程碑。RT3000 B 机（HW-B）完成基本功能阶段验证：WAN 千兆接收时钟修复、QCA8337 三个 LAN 口、NAND 写入、OEM / QSDK 双系统启动与回退、基于设备工厂 MAC 的地址派生、5 GHz BDF 修复和完整 ath11k NSS/WIFILI 路径。r5 使用原厂 Telnet 安装，附件仍保留在 [r5 Release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r5)。
- **5 GHz 吞吐实验（2026-09-21）**：iQOO Neo10 → RT3000 5 GHz HE160 → 千兆有线 PC，单流上传 760 / 789 Mbps，四流 879 Mbps；纯有线控制 937 / 938 Mbps。单流 ≥800 Mbps 的阶段目标当时未达成。记录见 [WIFI5 阶段记录](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md)和[原始数据](rt3000-machine-b/docs/evidence/2026-09-21-wifi5/)。
- **硬件研究**：实物核对确认 RT3000 存在 SoC、内存、NAND、交换机和射频前端都不同的版本，最终归纳为 HW-A/B/C/D 四组。见[硬件变体研究](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md)和[样机配置](rt3000-machine-b/docs/HARDWARE_SUPPORT.md)。
- **r6（2026-10-26）**：同一套源码支持 HW-A（RW3000）、HW-B（RT3000）、HW-C（RT3000 RTL8367S）、HW-D（NX30），改用 U-Boot 救援页安装，新增任一槽和大分区启动、RTL8367S 驱动、各组 BDF。

</details>

## 上游与许可证

基于 [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000)。感谢 [OpenWrt](https://github.com/openwrt/openwrt)、hzyitc 和相关 Qualcomm/QSDK 维护者。上游版权、作者信息、SPDX 声明和许可证均保留；许可文本见 [COPYING](COPYING) 与 [LICENSES](LICENSES/)。

公开快照不包含开发历史、密钥、设备原始 ART/分区备份或开发环境目录，详见[脱敏范围](rt3000-machine-b/docs/PUBLICATION.md)。

本项目由 [FlyFish-go](https://github.com/FlyFish-go) 独立开发，与 H3C 官方无关。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=FlyFish-go/H3C-RT3000-Product-R1,FlyFish-go/H3C-NX30-Uboot&type=Date)](https://star-history.com/#FlyFish-go/H3C-RT3000-Product-R1&FlyFish-go/H3C-NX30-Uboot&Date)
