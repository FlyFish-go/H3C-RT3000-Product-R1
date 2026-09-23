# B 机系统内升级适配记录（2026-09-22）

> **2026-09-23 补记**：下文“待执行”是 09-22 的历史进度。随后 r5 在 RT3000 Machine-B 上完成 NAND 安装、保留配置 `sysupgrade`、`sysupgrade -n` 和双频手机连接实测；详情见 [r5 发布说明](../release/RELEASE-NOTES-r5.md) 与 [安装教程](../release/INSTALL.md)。故障注入及断电恢复仍未实测。

本轮目标是把中文界面、TTYD 和专用升级流程集成到 QSDK 11.5 / OpenWrt 21.02.7 固件，并在 B 机验证 NAND 启动与保留配置升级。这是开发验收记录，不能替代尚待编写的原厂安装教程。

## 适用范围

仅限本项目 RT3000 B 机：GigaDevice NAND，2048 字节页、128 字节 OOB、128 KiB 擦除块，第二槽位 mtd16 为 40 MiB。A/C 机及其他型号不在本轮支持范围。

升级包为 `*-h3c_rt3000-squashfs-nand-sysupgrade.bin`，虽然扩展名是 `.bin`，内容是带 fwtool 元数据的专用 tar 包。`nand-factory.ubi` 是工厂 UBI 镜像，不能拿来直接替代系统内升级包。

## 写入流程

1. 检查板型、运行分区映射、NAND 几何、原厂槽位 UBI 头及两份 BOOTCONFIG。
2. 验证 fwtool 兼容元数据、严格的归档成员列表、manifest 中的板型和槽位，以及 kernel/root 的长度、格式和 SHA-256。
3. 系统进入 RAM 升级环境后再次执行检查；`sysupgrade -F` 不能绕过写入前的检查。
4. 通过现有 RB001 工具逐副本选择原厂槽位，读回验证成功后才允许擦写 mtd16。
5. 仅在 `/dev/mtd16` 重建 UBI，卷 0 为 kernel、卷 1 为 ubi_rootfs、卷 2 为 rootfs_data。每个命令检查退出状态。
6. 写入后从 UBI 卷读回 kernel/root 并核对长度与 SHA-256。若保留配置，将 sysupgrade 备份写入新 overlay，并验证复制内容。
7. 所有检查成功后才逐副本选择 QSDK 并重启。

不会写入 mtd15，不修改 bootloader、分区表或 U-Boot 环境。镜像校验用于识别格式错误、损坏及不匹配的镜像；不等同于发布者身份认证。只应安装可信发布的固件。

若在载荷写入阶段失败，启动选择保留为原厂槽位；若 BOOTCONFIG 事务自身失败，保留错误证据，不把结果称为完整成功。硬件掉电和故障后的实际恢复仍需实机验证，离线模拟不代替此项。

## 中文、网页终端与国内源

- 内置 LuCI、基础/防火墙/软件包管理中文，以及 TTYD、LuCI 终端页面和终端中文翻译。
- TTYD 使用上游配置：监听 LAN、执行 `/bin/login`，使用系统账号密码登录，不配置免认证 root shell。
- 国内通用软件包源使用上海交大 SJTUG 的 21.02.7 / arm_cortex-a7_neon-vfpv4 镜像；五个索引已实际请求并解压检查成功。
- 首次启动脚本只迁移原有 OpenWrt 官方 21.02.7 通用包地址，保留自定义地址与签名检查。
- 官方没有本项目的 `ipq50xx/arm` 内核包仓库，该失效 core 源会被注释。QSDK 内核模块和驱动需使用本项目同次构建的包；通用镜像并不意味着其中每个包都已完成 QSDK 兼容性验收。

## 构建补正

验收前追加检查发现，历史普通 `make` 没有自动生成 `/etc/rt3000-release.json`，该文件原来依赖外部发布脚本补入。本轮为 RT3000 squashfs 增加了显式构建依赖：先生成 FIT，再写入仅包含内核哈希的身份清单，最后生成根文件系统。最终镜像反向解包已验证身份清单与实际内核一致。

本次实机候选继续通过既有发布流程固定已验收的 `qca-ssdk.ko`，并从最终 UBI 解包核对模块字节。最初未带身份清单的候选已作废，从未启动或刷写。

首次从 RAM 环境安装时，自动配置备份对 tmpfs 有特殊限制，需显式提供当前 RAM 配置归档；从 NAND 中正常升级则使用系统自带的配置保留流程。

## 验证进度

- 专用升级 shell 的隔离故障测试：44 项通过，使用真实 BusyBox ash/tar、fwtool、jsonfilter，仅模拟 flash/BOOTCONFIG/mount 操作。
- 既有 RB001 逐副本事务回归：通过。
- 最终固件构建与镜像审计：通过。已核对中文目录、TTYD、国内源脚本和升级脚本；工厂 UBI 与升级包的内核及根文件系统内容一致。TTYD 的 ARM 程序已通过 QEMU 版本启动检查。
- NAND 刷写、实际 NAND 启动、保留配置的第二轮升级及最小网络测试：**待执行，不视为通过**。

本轮本地证据保存在 `artifacts/r1-sysupgrade-20260922` 与 `artifacts/machine-b/sysupgrade-20260922`，发布时只摘录脱敏结果。
