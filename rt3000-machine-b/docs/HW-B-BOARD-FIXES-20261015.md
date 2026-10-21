# HW-B QSDK11.5：RESET、LED 与高槽/RAM 启动参数修复

日期：2026-10-15（北京时间）。用户授权在 WSL QSDK11.5 权威仓库修改这三项，明确先不操作设备、不影响另一窗口的 U-Boot 与 OEM 过渡包适配。

本轮完成源码修复与离线验证。**未完整构建新固件、未进行设备验收、未更新 r5 发布附件。**

## 源码与范围

- 权威仓库：`<QSDK11.5-ROOT>`。
- 分支：`codex/phase1-rt3000-c-rtl8367s`；HEAD：`e2e30b264dde5b677535c0adf59ac4fa28497f27`。既有未提交修改保留；本轮未提交或推送。
- 硬件依据限 HW-B RT-B01，IPQ5000 / 256 MiB / QCA8337 / GD5F1GQ5REYIG，历史现存格式 ECC8。不以它替代 A/C/D 或其他 NAND/ECC 资格。
- 仅修改本 QSDK 的 B 设备树、B image profile、显式 opt-in 的内核参数处理及对应测试/记录。未访问设备、串口、网页、供电，也未写外部 U-Boot 工程或 `projects/nx30-oem-bridge`。

## RESET 与 LED

`target/linux/ipq50xx/dts/ipq5000-rt3000.dts` 的 RESET pinctrl 与 gpio-keys 均从 GPIO27 改为 GPIO34，低有效；WPS GPIO38 保持。沿用目标已有的 `kmod-gpio-button-hotplug` 和标准 reset handler，不新增会竞争 GPIO 的第二套按键驱动。

新增标准 `gpio-leds`：绿色 GPIO24、红色 GPIO23，均高有效。绿色默认亮、红色默认灭；`led-boot`/`led-running` 指向绿色，`led-failsafe`/`led-upgrade` 指向红色，交给现有 OpenWrt `diag.sh`。未把 GPIO17/19 当作已确认灯路。B profile 显式加入 `kmod-leds-gpio`；目标当前内核配置已有 `CONFIG_LEDS_GPIO=y` 和 timer trigger。

依据：[RESET 实测](../../../docs/H3C-HW-B-UBOOT-R2-RESET-20261008.md)、[R7.1 灯色实测](../../../docs/H3C-HW-B-R7.1-POWER-LED-LIVE-20261010.md)。这些是引脚输入证据，不代表新 Linux 镜像已运行。

## 高槽与 RAM 启动契约

旧 B 镜像的 cmdline map 把高槽命名为 `rootfs`，但继承参数可能是 `ubi.mtd=rootfs_1`；内核会累加 UBI attach 参数，单纯再追加一个正确值不能可靠修复。旧 initramfs DTB 还带 NAND root/ubiblock 参数。

本轮保留既有物理安装范围：低 `0x900000+0x2800000` 为只读 `oem_rootfs`，高 `0x3100000+0x2800000` 为 QSDK `rootfs`。原 mtdparts 字节串与物理范围不变；fallback fixed-partitions 的槽名和 BOOTCONFIG/高槽可写属性与既有 cmdline map 对齐，启动链、ENV、ART、低 OEM 槽继续只读。没有建立任意槽安装/升级功能，`lib/upgrade/rt3000.sh` 完全未改。

- NAND FIT 使用 `ipq5000-rt3000.dts`：明确 `ubi.mtd=rootfs ubi.block=0,1 root=/dev/ubiblock0_1 rootfstype=squashfs rootwait`。
- RAM FIT 使用新增 `ipq5000-rt3000-initramfs.dts`：保留相同分区视图，使用 `rdinit=/init`，不自动 attach NAND 或创建 NAND root ubiblock。
- B image profile 注册两个 DTB，并为 `KERNEL` / `KERNEL_INITRAMFS` 显式指定各自 DTB；原 `config@mp02.1` 保留。

新增 `030-of-h3c-rt3000-storage-bootargs.patch` 和 `files/drivers/of/h3c_rt3000_bootargs.h`。仅根 compatible 含 `h3c,rt3000` 且 `/chosen` 有 `h3c,storage-bootargs` 时启用。非 B 和无该属性的旧 DT 沿用原行为。

该属性是本项目私有启动契约，必须与本轮内核补丁一起构建，不能只移植 DTS。过滤器按完整参数名移除所有旧 `mtdparts`、`ubi.mtd`、`ubi.block`、`root*`（明确列表）、`init`/`rdinit`、`ro`/`rw`，再采用当前镜像的确定参数。`nandspare`、`nandeccbits`、console、无线参数和其他非冲突参数保留。过滤发生于旧长参数复制前及 CONFIG_CMDLINE 处理后，避免旧长分区表把尾部 ECC 参数截掉；引号/字符串非法或最终超过 ARM 的 1024 字节容量时明确拒绝，不静默截断。

## 离线验证

证据目录：`<EVIDENCE>`，含写前文件、原 tracked diff、输入/输出哈希和独立编译目录。

| 检查 | 结果 |
|---|---|
| NAND/RAM × 两种 ath11k 内存宏的实际 DTB 编译 | PASS，4 个 DTB |
| 实际补丁应用、真实 chosen 函数与 helper 的主机编译/UBSan | PASS，135 项；覆盖重复 attach、错误槽名、RAM、不误删相似键、引号、1024 边界、超长旧分区表尾部 ECC8、ECC4 保留、CONFIG_CMDLINE default/extend/force、非 B/无属性 |
| 补丁后真实 `drivers/of/fdt.c` 独立 ARM 编译 | PASS，输出 ARM ELF `fdt.o`；不是整个内核/固件构建 |
| 实际 Device/Init、B image 定义的隔离 Make 展开 | PASS，NAND/RAM 分别选定正确 DTB |
| 实际 mkits.sh/mkimage 的两个 FIT 夹具 | PASS，`config@mp02.1` 内嵌 DTB 与对应编译输入逐字节一致；载荷明确为不可启动测试文本，非安装镜像 |
| 新旧 DTB 逐属性比较 | PASS，20 个预期属性差异；原物理 mtdparts 字节串保持；原有 DTC 警告无增量 |
| SDK 实际 PATCH_DIR 表达式 | PASS，当前没有 patches-5.4，正式使用 `target/linux/ipq50xx/patches/` |
| 无关原 tracked 修改、`.config`、目标内核配置、缓存 fdt.c、升级 helper | 哈希保持；image Makefile 内既有 C profile 修改保留 |
| git diff --check | PASS |

初次独立测试遇到测试 include 顺序/旧 DTS wrapper 路径问题、以及手工 ARM 编译缺架构宏，失败目录保留；修正独立测试环境后通过。没有通过重建/清理共享缓存解决。

主测试可复跑：

```sh
python3 rt3000-machine-b/tests/board/test_board.py \
  --kernel build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq50xx_arm/linux-5.4-qsdk-11.5.0.5 \
  --output-dir /tmp/hwb-board-new-unique-directory
```

## 停点

本轮未运行 `make defconfig`、完整 OpenWrt build、feeds 操作或共享缓存清理；后续完整构建应解析包含 B 新 LED 包的配置，并把该内核补丁、overlay 与两种 DTS 一起纳入新候选。现有 r5 文件和正在运行的设备不会随源码变化。

新 Linux 的实体 RESET、LED、NAND/RAM 启动、双频与升级仍待后续用户授权的设备阶段验收；本轮未执行任何设备动作，也未改已有安装范围。
