# 文档导航

[项目首页](../../README.md) · [English overview](../../README_EN.md)

当前发布为 **Product R1 r5 Developer Preview**，发布固件仍只在本项目的 **RT3000 B 机（IPQ5000 / 集成 256 MiB DDR3L）**验证。C 机已有 RAM-stage 阶段结果，但尚未发布支持；A/C 与其他机型不能套用 B 机的刷写命令。各文档保留原有路径，按以下入口阅读。

## r5：安装、使用与恢复边界

| 入口 | 内容 |
|---|---|
| [发布概览](../release/README.md) | B 机发布范围、管理默认值与未完成验证 |
| [安装总览](../release/INSTALL.md) | 适用范围、风险、刷写前备份与五篇操作指南 |
| [r5 发布说明](../release/RELEASE-NOTES-r5.md) | 版本与硬件勘误、修复背景、附件及校验值 |
| [备份正文](../release/05-RECOVERY.md#4-你的备份资产) | 原厂配置及本机 `mtd15` 备份；须在刷写前完成，传输与恢复验证边界见正文 |
| [已知问题](../release/KNOWN_ISSUES.md) | 已知限制与待验证事项 |
| [配套工具](../release/tools/README.md) | 原厂 Telnet、文件传输与 selector 工具说明 |

## 硬件研究与样机证据

| 入口 | 内容 |
|---|---|
| [Hardware Research v1.0](../../docs/H3C-IPQ50xx-Hardware-Research-v1.0.md) | A/B/C 硬件差异、OEM 身份与硬件身份、来源与能力边界 |
| [硬件记录与适配路线](HARDWARE_SUPPORT.md) | 当前样机配置、B 机发布范围、C 机 RAM-stage 进展与后续路线 |
| [研究图片索引](../../docs/images/hardware-research-v1/README.md) | 公开硬件研究插图及来源 |

## 开发与构建

| 入口 | 内容 |
|---|---|
| [公开源码构建](BUILD_PUBLIC.md) | 构建树、依赖与复现边界；全新环境构建尚未认证 |
| [基础 SDK 记录](../BASE-SDK.md) | 历史基础版本、环境与 delta 复现记录 |
| [公开范围](PUBLICATION.md) | 已发布内容、依赖边界与不公开的设备数据 |
| [2026-09-21 Candidate 13 无线实验](WIFI5_SESSION_2026-09-21.md) | RAM-only 5 GHz 测试、公开证据与清单；性能扩展保持暂停，重复单流上传 ≥800 Mbps 尚未通过 |
| [RC1 5 GHz 性能记录](RC1_WIFI5_PERF_001.md) | 较早无线测试与当时的判断边界 |
| [2026-09-22 中文界面记录](CHINESE_UI_2026-09-22.md) | LuCI 中文默认值验证 |
| [2026-09-22 升级记录](SYSUPGRADE_2026-09-22.md) | NAND 升级、配置保留与恢复出厂记录 |

## 历史验收与冻结记录

以下文档保留各自的历史版本、样机和测试范围。历史 PASS 不扩大 r5 支持范围，也不代替当前安装指南。

| 入口 | 内容 |
|---|---|
| [R1-NET-D 基线首页与勘误](../README.md) | 早期基线、哈希与保留的原始描述；页首说明 IPQ5000 及当前仓库结构 |
| [网络闭环](NETWORK_BRINGUP_CLOSURE.md) | Ethernet P0 关闭、已验证结果与根因 |
| [Product R1 预发布验收](PRODUCT_R1_PRERELEASE_1_ACCEPTANCE.md) | 较早闪存、双系统与配置验收 |
| [Product R1 计划](PRODUCT_R1_PLAN.md) | 当时的范围、阻塞项与 MAC 策略 |
| [RB001 fail-closed selector](RB001_FAIL_CLOSED_SELECTOR.md) | 冗余 BOOTCONFIG 写入与验证记录 |
| [RB002 stable identity](RB002_STABLE_IDENTITY.md) | 固件稳定内容身份记录 |
| [冻结项目状态](PROJECT_STATE.md) | R1-NET-D 冻结时的状态 |
| [历史交接](NEXT-AGENT-HANDOFF.md) | 当时的交接与规则记录 |
| [冻结问题清单](BUG_BACKLOG.json) | 当时的 bug / blocker 登记 |
| [历史 vault 入口](VAULT_README.md) | 经清理的历史入口副本，仅供背景参考 |

冻结记录是公开副本；原始记录位于项目 vault 的 `00-START-HERE/`。本导航只整理公开仓库，不改变这些原始记录。
