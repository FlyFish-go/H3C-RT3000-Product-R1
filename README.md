# H3C Magic RT3000 · Product R1

[English](README_EN.md) · [HW-A/B/C/D 分组及 OEM 证据](docs/HW-ABCD-CLASSIFICATION.md) · [硬件变体研究](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) · [样机配置](rt3000-machine-b/docs/HARDWARE_SUPPORT.md) · [支持项目](#支持项目) · [测试记录](rt3000-machine-b/docs/WIFI5_SESSION_2026-09-21.md) · [构建说明](rt3000-machine-b/docs/BUILD_PUBLIC.md) · [已知限制](rt3000-machine-b/release/KNOWN_ISSUES.md)

这是一个**基于 Qualcomm QSDK 11.5、使用 OpenWrt 21.02.7 的设备适配项目**，采用 QSDK 的供应商内核、无线驱动与网络加速栈，**不是 OpenWrt 主线适配项目**。

以 **RT3000 / RW3000 / RC3000 / NX30 全系适配**为长期目标。从 RT3000 开始，逐台厘清硬件差异，打通网络、无线、NAND 写入与启动恢复，再把经过验证的适配能力扩展到其他机型。

**Product R1 是这条路线的第一个实机里程碑：RT3000 B 机的基本功能已完成阶段验证，NAND 写入和 OEM / QSDK 双系统启动、切换与回退流程已在该机上验证。** 这为后续机型适配建立了基础；全系支持仍是路线目标。

当前发布为 **r6 Developer Preview（QSDK 11.5 HW-A/B/C/D）**：同一套源码和配置为 HW-A（RW3000）、HW-B（RT3000）、HW-C（RT3000 RTL8367S）、HW-D（NX30）各出一个镜像。每组都在项目的一台样机上实测：经 U-Boot 救援页写入、启动、系统内升级保留配置、连续 5 次断电冷启动后双频 AP 正常。每组只有一台样机，测试范围和限制见下文。固件附件与 SHA-256 见 [r6 Release](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r6)；r5 附件仍保留，只对应 RT3000 B 的旧安装方式。

基于 [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000)，保留 OpenWrt 构建结构、上游版权和许可证。

## HW-A/B/C/D 分类与 QSDK 11.5 适配进展

| HW 工程组 | 板级特点 / OEM 代表 machid | U-Boot `v0.1.0-pre.5` | QSDK 11.5 r6 |
|---|---|---|---|
| [**HW-A**](docs/HW-ABCD-CLASSIFICATION.md#hw-a) | 长板；IPQ5018 / 外置 DDR / QCA8337；`0x08040001` | 84 候选之一；一台样机实测通过 | `h3c_rw3000_hw_a`：一台 RW3000 实测通过 |
| [**HW-B**](docs/HW-ABCD-CLASSIFICATION.md#hw-b) | 短板；IPQ5000 / 集成 DDR / QCA8337；`0x08040000` | 84 候选之一；一台样机实测通过 | `h3c_rt3000`：一台 RT3000 实测通过 |
| [**HW-C**](docs/HW-ABCD-CLASSIFICATION.md#hw-c) | 长板；IPQ5018 / 外置 DDR / RTL8367S；`0x08040101` | 84 候选之一；一台样机实测通过 | `h3c_rt3000_rtl8367s_native_slot1`：一台 RT3000 实测通过 |
| [**HW-D**](docs/HW-ABCD-CLASSIFICATION.md#hw-d) | NX30 型长板；IPQ5000 / 集成 DDR / QCA8337；`0x08040000` | 84 候选之一；一台 NX30 实测通过 | `h3c_nx30_hw_d`：一台 NX30 实测通过 |

**同一商品型号可能跨不同 HW 组。B/D 的 OEM machid 均可为 `0x08040000`，不能仅凭 machid 刷写。** 详细的 [照片、OEM CDT/APPSBL 和控制 FDT 分组依据](docs/HW-ABCD-CLASSIFICATION.md) 与 [旧版 RT3000 A/B/C 实物研究](docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) 分开保留。r6 镜像按 HW 组区分，必须与 U-Boot 识别出的组一致；用错组的镜像，网口、无线或启动都可能不正常。

## RT3000 A / B / C 样机配置

三台样机都属于 Qualcomm IPQ50xx / QCN6102 AX3000 路线，均为 256 MiB RAM、128 MiB SPI-NAND 和 1 × WAN + 3 × LAN；但实物核对已经确认它们在 **SoC、RAM topology、NAND、Ethernet Switch、PCB 与 RF 前端装配**上存在明显差异：

| 样机 | SoC / RAM | NAND | 有线交换机 | 实机进展 |
|---|---|---|---|---|
| A 机 | **IPQ5018** / 独立 Winbond DDR | Winbond **W25N01GWZEIG** / 128 MiB | Qualcomm Atheros **QCA8337-AL3C** | 曾 RAM 启动、Wi-Fi 可开启；未完成逐项功能验证 |
| B 机 | **IPQ5000** / Integrated 256 MiB DDR3L | GigaDevice **GD5F1GQ5REYIG** / 128 MiB | Qualcomm Atheros **QCA8337-AL3C** | Product R1 r5 基线，基本功能、NAND 写入与双系统流程已阶段验证 |
| C 机 | **IPQ5018** / 独立 GigaDevice DDR | Winbond **W25N01GWZEIG** / 128 MiB | Realtek **RTL8367S** | Native08 已于 RT3000 C 实机完成非原厂槽原生 NAND 安装、冷启动、配置持久化与有限网络/双频验证；首次 DHCP、速率报告和长稳仍待解决，尚未公开发布 |

A 机 NAND 芯片丝印为 `25N01GWZEIG / 2238 / 6206DS900`。A 机在早期探索中，因我对 **APPSEL 的不成熟修改而变砖**，目前无法继续测试；它并非从未运行过，但当时没有完成逐项验收，当前版本也未在 A 机上重新验证。

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

仓库包含 OpenWrt 构建系统、RT3000 适配源码及补丁；内核、工具链和 feeds 等依赖需要按构建规则获取。先阅读 [公开源码构建说明](rt3000-machine-b/docs/BUILD_PUBLIC.md)。r6 镜像用 [`configs/h3c-magic.config`](configs/h3c-magic.config) 构建：复制为 `.config`，按文件头说明追加一行机型（HW-C 另加两行），再执行 `make defconfig && make`。

## 安装（r6）：通过 U-Boot 救援页

r6 不使用 r5 的原厂 Telnet 安装流程，需要先装好 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) 的 U-Boot **v0.1.0-pre.5**。还在原厂系统的设备，用 [BootBridge 网页版](https://flyfish-go.github.io/H3C-NX30-Uboot/) 安装；已装旧版 U-Boot 的，按该项目的 pre.5 说明升级。

| HW 组 | 首次写入（救援页） | 系统内升级 |
|---|---|---|
| HW-A | `openwrt-ipq50xx-arm-h3c_rw3000_hw_a-squashfs-nand-factory.ubi` | `…-h3c_rw3000_hw_a-squashfs-sysupgrade.bin` |
| HW-B | `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi` | `…-h3c_rt3000-squashfs-sysupgrade.bin` |
| HW-C | `openwrt-ipq50xx-arm-h3c_rt3000_rtl8367s_native_slot1-squashfs-nand-factory.ubi` | `…-h3c_rt3000_rtl8367s_native_slot1-squashfs-sysupgrade.bin` |
| HW-D | `openwrt-ipq50xx-arm-h3c_nx30_hw_d-squashfs-nand-factory.ubi` | `…-h3c_nx30_hw_d-squashfs-sysupgrade.bin` |

1. 断电后按住 Reset 再通电，进入救援页；电脑用网线接 **LAN** 口，打开 `http://192.168.10.1`。
2. 在「闪存备份」先备份两个系统槽。
3. 在「固件更新」把对应组的 `nand-factory.ubi` 写入**不是原厂系统所在**的那个槽。两个槽以偏移（`0x900000` / `0x3100000`）为准。
4. 把默认启动槽设为刚写入的槽，断电重启。
5. 以后升级在 LuCI「备份/升级」上传 `sysupgrade.bin`，可保留配置。

QSDK 可从任一系统槽启动，也能用于 U-Boot「分区表更新」生成的 80 MiB 大分区。大分区会抹掉原厂系统，只在确定不再需要原厂系统时使用。r6 正式镜像本轮在非原厂槽实测；任一槽和大分区启动由同一源码的前一轮构建在四组样机上实测。

## r6 默认管理方式

- LAN 地址 `192.168.10.1`，LuCI 为 `http://192.168.10.1/`；SSH 仅绑定 LAN。
- 新装系统没有 root 密码，首次登录请立即设置。
- 2.4 GHz `OpenWrt` 与 5 GHz `OpenWrt-5G` 默认启用 WPA2，默认密码 `12345678`，国家码 CN。这是公开默认值，日常使用前应更换。
- MAC 地址与原厂编号一致：WAN 为出厂地址，LAN、2.4 GHz、5 GHz 依次为出厂地址 +1、+2、+3。从 r5 升级会改变这三个地址。
- 无线校准数据在开机时从本机 ART 分区读取，镜像中不含任何一台设备的校准数据。

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

r6：每组只在项目的一台样机上实测，其他 NAND 型号和批次未验证。有线 WAN↔LAN 路由经 NSS/ECM 加速，台架实测约 940 Mbps；LAN 内无线与有线之间的桥接流量由 CPU 转发，未加速。HW-C/HW-D 沿用原厂的 Q6 内存预留，比 HW-A/B 多约 21 MiB，空闲可用内存约 52 MB（HW-A/B 约 72 MB）。10/100 Mbps、长时间运行、LED/按键尚未完整验证。

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
