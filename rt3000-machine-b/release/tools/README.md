# RT3000 Machine-B 安装工具

[← 安装教程](../INSTALL.md)

本目录放工具；**固件镜像不存放在源码仓库**。从 [r5 发布附件](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/tag/r5) 下载镜像和 `SHA256SUMS`，先核对校验值，再按教程操作。所有写入步骤仅针对教程已验证的 RT3000 Machine-B。

📦 用户也可直接下载 [Machine-B r5 OEM/QSDK 传输工具 ZIP](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/releases/download/r5/RT3000-Machine-B-r5-OEM-Transfer-Tools.zip)（8,569 字节；SHA-256：`8a0117f63ca7e461a2684b2602a092b09b52eafbf01dc6771ec080758778cb95`）。压缩包含 `rt3bcwrite`、本目录的 Windows 临时文件服务器批处理和中文说明；factory `.ubi` 仍需从 Release 单独下载并核验。

| 发布附件 | 用途 | 验证状态 |
|---|---|---|
| `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi` | 从原厂首次安装 | 已按教程实机写入、读回和启动 |
| `openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-sysupgrade.bin` | QSDK 内升级或恢复出厂 | 已实机验证保留配置与 `-n` |
| `openwrt-ipq50xx-arm-h3c_rt3000-initramfs-fit-uImage.itb` | RAM 启动诊断 | RAM 启动有记录；完整 NAND 救援未端到端验证 |

| 文件 | 用途 | 教程 |
|---|---|---|
| [`一键开启telnet.bat`](一键开启telnet.bat) | 从原厂配置备份生成启用 Telnet 的配置 | [第一部分](../01-GET-TELNET.md) |
| [`RT3000-开启telnet.ps1`](RT3000-开启telnet.ps1) | 上述批处理调用的 PowerShell 脚本 | [第一部分](../01-GET-TELNET.md) |
| [`1-启动文件服务器.bat`](1-启动文件服务器.bat) | 从电脑向原厂系统提供临时 HTTP 下载 | [第二部分](../02-INSTALL-QSDK.md) |
| [`rt3bcwrite`](rt3bcwrite) | 原厂环境中的双副本启动选择工具；[源码](../../../package/rt3bcwrite/src/rt3bcwrite.c) | [第二部分](../02-INSTALL-QSDK.md) |

## 校验值

```text
e23d8634af3fb20a5c383aa22ad2dc65752133ffd91d3715a70df5121d0789f5  rt3bcwrite
80e99811887ec3bedaf648a32954d93fc5e1482ab70605d6e41d791ce181c529  openwrt-ipq50xx-arm-h3c_rt3000-squashfs-nand-factory.ubi
```

Windows 可用 `certutil -hashfile 文件名 SHA256` 核对，原厂 shell 可用 `sha256sum` 再核对一次。文件服务器脚本应与 `rt3bcwrite` 和下载的 `.ubi` 镜像放在同一文件夹；它会列出可选的 IP 和镜像文件。脚本运行需要 Python 和管理员权限。

下载结束后关闭文件服务器，并在管理员命令提示符清理它创建的防火墙规则：

```cmd
netsh advfirewall firewall delete rule name="RT3000-Flash-HTTP"
```

原厂 Telnet 配置工具会另存修改后的配置；保留原始备份，不要将包含设备身份的配置文件上传到公开仓库或 Issues。工具的实际操作步骤、限制和失败处理以教程各部分为准。
