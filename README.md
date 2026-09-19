# H3C Magic RT3000 Product R1

[English](README_EN.md)

适用于部分硬件配置的 **H3C Magic RT3000** 的第三方固件项目。

目前项目处于 **Developer Preview（开发者预览）** 阶段。

> [!WARNING]
> 本项目不是 H3C 官方固件。
>
> 刷写第三方固件存在设备无法启动、配置丢失等风险。
> 在刷写前，请务必阅读安装与恢复文档，并确认你的设备硬件配置与已验证机型一致。

---

## 已验证硬件配置

当前 Product R1 仅在以下 RT3000 硬件配置上完成实际测试：

| 项目 | 已验证配置 |
|---|---|
| 设备 | H3C Magic RT3000 |
| SoC | Qualcomm IPQ5018 |
| RAM | 256 MiB |
| Flash | 128 MiB SPI-NAND |
| NAND 型号 | GigaDevice GD5F1GQ5REYIG |
| 5 GHz Wi-Fi | Qualcomm QCN6122 |
| Ethernet Switch | Qualcomm QCA8337 |
| 有线接口 | 1 × WAN + 3 × LAN |
| 系统架构 | ARMv7 |

**只有硬件配置与上述信息匹配的设备，才属于目前已经验证的支持范围。**

RT3000 可能存在不同生产批次、PCB/BOM、Flash 型号或其他硬件差异。

在尚未确认兼容性之前，请不要将 Product R1 固件刷入其他硬件配置的 RT3000。

后续如果有用户提供其他硬件批次并完成验证，我们会逐步扩充兼容列表。

---

## Product R1

当前固件基于：

- Qualcomm QSDK 11.5
- Linux 5.4.164
- OpenWrt 21.02.7

Product R1 并非简单的 OpenWrt 默认编译，而是针对 RT3000 硬件进行了适配、网络修复、启动与恢复机制以及产品化配置。

首个公开版本将以：

**Product R1 Developer Preview**

的形式发布。

---

## 当前已验证功能

目前已经在真实硬件上验证：

- NAND / UBI 启动
- Product R1 正常启动
- LAN1 / LAN2 / LAN3
- WAN 1000BASE-T
- WAN DHCP
- Internet 访问
- WAN 收发
- 2.4 GHz Wi-Fi
- 5 GHz Wi-Fi
- LuCI Web 管理界面
- SSH
- WAN 管理访问隔离
- OEM 原厂系统保留
- OEM / Product R1 启动切换
- Product R1 回滚与恢复机制
- 设备 MAC 地址策略
- 重启后配置持久化
- 固件运行身份检查

---

## 尚未完成完整验证

以下项目目前尚未完成完整 qualification：

- 10BASE-T
- 100BASE-T
- WAN 物理拔插长期测试
- 长时间运行 / soak test
- LED 行为
- 硬件按键
- NSS / ECM 最终性能调优

这些项目目前不作为 Developer Preview 的发布阻塞项。

它们不代表已经确认存在故障，只表示尚未完成完整测试。

详见：

[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)

---

## 下载

固件将在 GitHub Releases 页面发布：

[Releases](../../releases)

发布的每一个固件都会提供对应的 SHA256。

**刷写前请务必核对固件 SHA256。**

---

## 安装

在刷写之前，请完整阅读：

- [`INSTALL.md`](INSTALL.md)
- [`RECOVERY.md`](RECOVERY.md)
- [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)

尤其建议在刷写 Developer Preview 前确认自己具备基本的路由器恢复能力。

---

## 安全默认设置

Product R1 当前采用以下默认安全策略：

- WAN 侧禁止访问 LuCI
- WAN 侧禁止访问 SSH
- Dropbear SSH 仅允许 LAN 侧访问
- Wi-Fi 默认关闭
- 用户需要自行设置 SSID 和无线密码后启用 Wi-Fi
- 不使用统一的出厂密码
- 不使用 MAC 地址派生管理密码

首次启动后，请尽快设置 root 管理密码。

---

## 问题反馈

欢迎通过 GitHub Issues 或发布帖反馈实际使用情况。

提交问题时，请尽量提供：

- RT3000 硬件信息
- NAND / Flash 型号（如可确认）
- 原厂固件版本
- Product R1 版本
- 固件 SHA256
- 安装结果
- WAN 状态
- LAN 状态
- 2.4 GHz Wi-Fi 状态
- 5 GHz Wi-Fi 状态
- 是否能够进入 LuCI
- 是否能够正常重启
- 与问题相关的日志

请勿在公开 Issue 中提交：

- 管理密码
- Wi-Fi 密码
- SSH 私钥
- Token
- 其他个人凭据或敏感信息

---

## 源码与许可证

本仓库当前作为 Product R1 的：

- 固件发布入口
- 使用文档
- 问题追踪
- 用户反馈平台

使用。

当前内部开发仓库暂未公开。

Product R1 中包含 Linux、OpenWrt 以及其他采用不同许可证的软件组件。

与实际发布版本相关的许可证信息、第三方组件信息以及适用的对应源码提供方式，将随发布版本单独说明。

内部开发记录、硬件 bring-up 日志、测试证据和开发环境并不等同于公开发行所要求提供的对应源码。

---

## 项目状态

当前阶段：

**Product R1 Developer Preview 准备中**

目标是首先向具备一定路由器刷机和恢复经验的用户开放测试，根据不同硬件批次和真实网络环境中的反馈逐步完善固件。

---

## Disclaimer / 免责声明

本项目为个人 / 社区独立开发项目，与 H3C 官方无关。

H3C、Magic 及相关名称和商标归其各自权利人所有。

刷写第三方固件具有风险。使用本项目固件即表示你理解并接受相关风险。
