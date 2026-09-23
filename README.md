# H3C Magic RT3000 · Product R1

[English](README_EN.md) · [样机配置](rt3000-machine-b/docs/HARDWARE_SUPPORT.md) · [支持项目](#支持项目) · [测试记录](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md) · [构建说明](rt3000-machine-b/docs/BUILD_PUBLIC.md) · [已知限制](rt3000-machine-b/release/KNOWN_ISSUES.md)

这是一个**基于 Qualcomm QSDK 11.5、使用 OpenWrt 21.02.7 的设备适配项目**，采用 QSDK 的供应商内核、无线驱动与网络加速栈，**不是 OpenWrt 主线适配项目**。

以 **RT3000 / RW3000 / RC3000 / NX30 全系适配**为长期目标。从 RT3000 开始，逐台厘清硬件差异，打通网络、无线、NAND 写入与启动恢复，再把经过验证的适配能力扩展到其他机型。

**Product R1 是这条路线的第一个实机里程碑：RT3000 B 机的基本功能已完成阶段验证，NAND 写入和 OEM / QSDK 双系统启动、切换与回退流程已在该机上验证。** 这为后续机型适配建立了基础；全系支持仍是路线目标。

当前发布为 **Product R1 r5 Developer Preview**。r5 已在 RT3000 B 机从原厂写入 NAND、读回校验、启动、双向切换、保留配置升级及恢复出厂后验证；双频手机连接通过。更早的 Wi-Fi Candidate 13 只属于 RAM 启动性能实验，不能代表 r5 镜像的验收。固件附件与 SHA-256 见 [r5 Release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r5)。

基于 [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000)，保留 OpenWrt 构建结构、上游版权和许可证。

## 适配路线与当前状态

| 机型 / 样机 | 当前状态 | 后续工作 |
|---|---|---|
| RT3000 · B 机 | **首个实机里程碑：基本功能阶段验证完成** | 完善功能覆盖、稳定性与性能验证 |
| RT3000 · A 机 | **曾 RAM 启动、Wi-Fi 可开启；未完成逐项验证**。早期修改 APPSEL 后变砖 | 获得可用样机后继续验证 |
| RT3000 · C 机 | **未通过、暂未支持**：有线交换机适配尚未完成 | 完成交换机适配，再进行整机验收 |
| RW3000 | **规划支持，尚未验证** | 核对硬件版本、建立板级配置和实机证据 |
| RC3000 | **规划支持，尚未验证** | 核对硬件版本、建立板级配置和实机证据 |
| NX30 | **规划支持，尚未验证** | 核对硬件版本、建立板级配置和实机证据 |

A / B / C 是项目内部的实体样机编号，不是厂商硬件版本号。每一种交换机、NAND 和板级组合都需要单独确认；不会把 B 机的通过结果直接套到其他样机或机型。硬件记录与证据边界见 [样机配置](rt3000-machine-b/docs/HARDWARE_SUPPORT.md)。

## RT3000 A / B / C 样机配置

三台样机的主要配置一致：**Qualcomm IPQ5018 / ARMv7、256 MiB RAM、128 MiB SPI-NAND、集成 2.4 GHz 无线和外置 QCN6102 5 GHz 无线**，均为 1 × WAN + 3 × LAN。差异集中在 NAND 和有线交换机：

| 样机 | NAND | 有线交换机 | 实机进展 |
|---|---|---|---|
| A 机 | Winbond **W25N01GWZEIG** / 128 MiB | Qualcomm **QCA8337** | 曾 RAM 启动，Wi-Fi 可开启，观察期间未出现 kernel panic；未完成逐项功能验证 |
| B 机 | GigaDevice **GD5F1GQ5REYIG** / 128 MiB | Qualcomm **QCA8337** | 当前主力样机，基本功能、NAND 写入与双系统流程已完成阶段验证 |
| C 机 | Winbond **W25N01GWZEIG** / 128 MiB，与 A 机相同 | Realtek **RTL8367S** | 有线交换机适配未完成，整机未通过、暂未支持 |

A 机 NAND 芯片丝印为 `25N01GWZEIG / 2238 / 6205DS900`。A 机在早期探索中，因我对 **APPSEL 的不成熟修改而变砖**，目前无法继续测试；它并非从未运行过，但当时没有完成逐项验收，当前版本也未在 A 机上重新验证。

5 GHz 硬件为 **QCN6102**，QSDK 软件目标名为 `QCN6122` / `qcn6122`。软件基础为 QSDK 11.5、Linux 5.4.164、OpenWrt 21.02.7。完整参数、验证范围和记录来源见 [样机配置](rt3000-machine-b/docs/HARDWARE_SUPPORT.md)。

以上配置结合项目记录和我对实体样机的补充确认整理。配置相近不等于固件可直接通用；B 机的验收结果不覆盖 A/C 机或其他批次。仓库中的 Redmi / Xiaomi 等上游目标也不代表本项目重新验证了这些设备。

## 已完成的工作

- 修复 WAN 千兆接收路径的时钟配置问题，完成链路、DHCP、路由和 CRC 检查。
- 接入 RT3000 板级配置、QCA8337 交换机及三个 LAN 口。
- 完成 B 机 QSDK 槽位的 NAND 写入与内容校验，保留 OEM 槽位，并实测 OEM / QSDK 双系统启动和回退。
- 实现校验失败即停止的双副本启动选择流程，以及基于镜像内容的运行身份检查。
- 实现基于设备自身工厂 MAC 的稳定 LAN / Wi-Fi 地址派生，避免使用开发样机的固定地址。
- 修复 5 GHz BDF 兼容和信号问题，接入完整 ath11k NSS/WIFILI 路径。
- 保留 WAN 管理隔离和每台设备自身的身份配置；r5 镜像默认开启 WPA2 双频 AP，安装和恢复出厂后均已在手机上实测关联。

此前 R1-NET-D 和 Product R1 预发布验收，与最新 Wi-Fi 实验的验收范围不同。详见 [网络基线](rt3000-machine-b/docs/NETWORK_BRINGUP_CLOSURE.md)、[预发布验收](rt3000-machine-b/docs/PRODUCT_R1_PRERELEASE_1_ACCEPTANCE.md) 和 [最新阶段记录](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md)。

## 无线性能：当前进展

路径：iQOO Neo10 → RT3000 5 GHz HE160 → 千兆有线 Windows PC。使用 iperf3，每轮约 10 秒，以下均为服务端结果。

| 条件 | TCP 上传 |
|---|---:|
| 单流，主信道 44，两次测试 | **760 / 789 Mbps** |
| 四流，主信道 36，对照测试 | **879 Mbps** |
| RT3000 → PC 纯有线单流控制 | **937 / 938 Mbps** |

基本功能之后，我进行了 5 GHz 吞吐优化，目前按计划暂停扩展。**重复单流上传 ≥800 Mbps 的阶段目标尚未通过。** 四流、PHY 协商速率和单秒峰值不能替代单流验收。信道 44 是当前保留的实测配置，尚未通过充分重复的 A/B 证明收益来源；也不能据此宣称已经达到硬件绝对上限。

最新配置使用 `nss_offload=1 frame_mode=2`，关闭通用 `nss_redirect`。C13 的 RXDMA 扩容已生效，但没有证据证明它解决了上行瓶颈。完整 [CSV 和脱敏原始日志](rt3000-machine-b/docs/evidence/2026-09-21-wifi5/) 与 [镜像身份清单](rt3000-machine-b/manifest/wifi5-candidate13-20260921.json) 随源码提供。

## 获取源码与构建

```sh
git clone https://github.com/FlyFish-go/H3C-RT3000-Product-R1.git
cd H3C-RT3000-Product-R1
```

仓库包含 OpenWrt 构建系统、RT3000 适配源码及补丁；内核、工具链和 feeds 等依赖需要按构建规则获取。先阅读 [公开源码构建说明](rt3000-machine-b/docs/BUILD_PUBLIC.md)，其中列出配置、依赖、历史构建结果和尚未完成的全新环境复现验证。

## 安装：从原厂系统进入第二槽位

**仅 RT3000 B 机通过 r5 实机验证。** A/C 样机和 RW3000、RC3000、NX30 不适用本镜像或刷写命令。开始前请先核对 NAND、分区表和原厂版本，阅读 [完整安装教程](rt3000-machine-b/release/INSTALL.md) 与 [r5 发布说明](rt3000-machine-b/release/RELEASE-NOTES-r5.md)。

教程分为原厂 Telnet、安装与读回、双向切换、固件升级和救援五部分。2026-09-23 已按当前教程在 B 机复走正常路径；原厂 Telnet 配置导入本轮未重复执行，故障注入、断电和完整 U-Boot + TFTP 救援未验证。完整校验值见 Release 附件 `SHA256SUMS`。

## r5 默认管理方式

- QSDK LAN 地址 `192.168.10.1`，LuCI 为 `http://192.168.10.1/`；SSH 仅绑定 LAN。原厂系统的管理地址取决于接线和上游 DHCP。
- 新装 QSDK 没有 root 密码，首次登录请立即设置。
- 2.4 GHz `RT3000` 与 5 GHz `RT3000-5G` 默认均启用 WPA2，默认 Wi-Fi 密码 `RTRCRWNX`。这是公开默认值，日常使用前应更换。
- 上述 r5 默认值在重新安装、保留配置升级和 `sysupgrade -n` 后均有实机验证；旧 RC1 / C13 测试镜像的默认值不同，不应套用。

## 目录

| 路径 | 内容 |
|---|---|
| `target/linux/ipq50xx/` | RT3000 DTS、网络及系统集成 |
| `package/kernel/mac80211/` | ath11k、NSS/WIFILI 和诊断补丁 |
| `package/firmware/ipq-wifi/` | 型号级 BDF 文件和封装规则 |
| `rt3000-machine-b/tools/` | BDF 构造与受限设备控制工具 |
| `rt3000-machine-b/tests/`、`tests/wifi/` | 离线回归和配置检查 |
| `rt3000-machine-b/docs/` | 验收、实验、构建及脱敏说明 |
| `rt3000-machine-b/manifest/` | 已测试镜像与证据的身份记录 |

## 已知限制

当前没有完成 10/100 Mbps 以太网、WAN 物理拔插、长时间运行、LED/按键及 C13 双频并发等完整验证。最新有线控制和 LAN bridge 无线测速不等同于 WAN/NAT 所有场景的验收。详见 [KNOWN_ISSUES](rt3000-machine-b/release/KNOWN_ISSUES.md)。

## 支持项目

这个项目目前由我个人开发和维护。要把适配范围从 RT3000 扩展到 RW3000、RC3000 和 NX30，我最需要的是能放到桌面上反复验证的实体设备。欢迎通过以下方式支持项目：

1. **实体样机支持（最优先）。** 如果你有闲置的 RT3000 / RW3000 / RC3000 / NX30，尤其是不同 NAND、交换机或 PCB 批次的设备，欢迎联系我捐赠或借测。能正常启动的整机最有帮助；故障机、主板或配件也可以先提供型号和故障情况，确认是否适合用于修复与研究。
2. **资金赞助 / 捐献。** 用于购买和维修样机、补充调试配件、承担运输等开发成本，让我能持续推进适配与实机验证。目前请通过邮箱联系，沟通赞助方式。
3. **测试与资料支持。** 硬件照片、芯片丝印、原厂版本信息和脱敏测试日志，也能帮助我减少重复摸索。

**联系邮箱：[yufeiyang45@qq.com](mailto:yufeiyang45@qq.com)**。提供样机时请注明型号、硬件版本、设备状态，以及希望捐赠还是借测；寄送安排请先通过邮件确认。

赞助是对持续开发的支持，不能保证某个机型的完成时间或适配结果。感谢愿意提供设备、资料或资金，让这条适配路线继续向前的人。

## 贡献者

目前本项目的开发与维护由 [FlyFish-go](https://github.com/FlyFish-go) 独立完成。

## 反馈与脱敏

欢迎在 [Issues](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues) 中提供硬件版本、镜像 SHA256、复现步骤和脱敏日志。吞吐问题请标明上传/下载、流数、服务器拓扑及服务端汇总。

公开快照不包含本地开发历史、通知 Token、SSH 私钥、设备原始 ART/分区备份、完整抓包或开发环境目录。文档里的样机身份和测试样例已脱敏，生产代码仍读取设备自身身份；详见 [脱敏范围](rt3000-machine-b/docs/PUBLICATION.md)。

## 上游与许可证

感谢 [OpenWrt](https://github.com/openwrt/openwrt)、[hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000) 和相关 Qualcomm/QSDK 维护者。上游版权、作者信息、SPDX 声明和许可证均保留；许可文本见 [COPYING](COPYING) 与 [LICENSES](LICENSES/)。各组件继续适用其原有许可证，本次公开不会改变第三方组件的授权范围。

本项目为独立适配项目，与 H3C 官方无关。
