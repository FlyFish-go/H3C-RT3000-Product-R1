# r8 — 更多 NAND 闪存可以运行 QSDK

本版修复内核对 NAND 闪存的识别：以前只有少数闪存型号能启动本固件，其余机器内核挂不上 rootfs，开机后回到救援页。问题见 [#1](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues/1)。

## 修复内容

H3C-NX30-Uboot 会按自己审核过的闪存表识别本机 NAND，并在内核命令行里传入这台机器的物理 spare 大小和写入时用的 ECC（`nandspare=64|128 nandeccbits=4|8`），原厂内核就是这样读取的。以前的 QSDK 内核不看这两个参数，只按 `nand_ids.c` 的固定表配置，而这张表分辨不了下面几种情况：

- 同一颗 GD5F1GQ5REYIG（c8:41）出厂时有按 ECC4 写入的，也有按 ECC8 写入的；
- DS35M1GA（e5:21）、GD5F4GQ6（c8:45）的 spare 是 128，表里写的是 64；
- TC58CYG0S3HRAIG（98:d2）、TC58CYG1S3HRAIJ（98:db）、FM25LS01（a1:a5）、GD5F1GM7REYIG（c8:81）、DS35Q2GA（e5:72）、DS35M4GM（e5:a4）表里没有。

另外 HW-D 的内核只认 Winbond W25N01GWZEIG（EF:BA:21）。

本版：

- 四类主板：U-Boot 传入有效的组合（64/4、128/4、128/8）时，内核按它配置 OOB 大小和 ECC 强度；补上上面 6 种闪存。
- HW-D：有 U-Boot 传参时，要求闪存参数与 U-Boot 核对的一致，不再限定固定的型号名单；没有传参时仍只接受 W25N01GWZEIG、F50D1G41LB（c8:11）、GD5F1GQ5REYIH（c8:21）、GD5F1GQ4RE9IH（c8:c9）、MX35UF1GE4AC（c2:92）、W25N01JW（ef:bc），并要求 OOB64/ECC4。
- HW-C、HW-D 的分区写保护检查接受同样的三种组合，以及容量大于 128 MiB 的闪存（只使用前 128 MiB）。

分区表、系统槽选择、网络、无线和升级写入范围都没有改变。

## 验证范围

- HW-D（GD5F1GQ5REYIG，spare128，ECC4，以前的内核无法使用）：在 U-Boot pre.6 的 RAM 救援版下加载只读的 RAM 验证内核，内核按传参配置为 OOB128/ECC4，读出 APPSBL、ART 和两个系统槽无 ECC 错误，UBI 可正常挂载。没有在这台机器上写入或长期运行。
- HW-A（W25N01GWZEIG，64/4）、HW-B（GD5F1GQ5REYIG，128/8）、HW-C（W25N01GWZEIG，64/4）：从 r7 保留配置 sysupgrade 到本版的同源构建，rootfs 正常挂载；写入 1 MiB 文件后断电冷启动，读回一致，无 ECC 错误。
- 新增的其他闪存型号没有实物，只有构建与主机测试结论。
- 离线检查（WAN、MAC、配置路径、Wi-Fi、BDF、candidate10、设备控制模拟）全部通过。

## 安装

需要 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) **v0.1.0-pre.5 或更新**（推荐 [pre.6](https://github.com/FlyFish-go/H3C-NX30-Uboot/releases/tag/uboot-v0.1.0-pre.6)），由它传入闪存参数。

按硬件系列选择 `H3C-Magic-r8-HW-A/B/C/D-*`，不要只按机身商品型号选择。`nand-factory.ubi` 用于在 U-Boot 救援页写入；`sysupgrade.bin` 用于已经运行本固件的系统内升级。使用稳定电源，升级前备份。安装前核对随包 SHA256SUMS。

## English summary

The H3C U-Boot passes the NAND spare size and the ECC each unit was written with (`nandspare=` / `nandeccbits=`); QSDK ignored them and used the fixed `nand_ids.c` table, so units with an ECC4-written GD5F1GQ5REYIG, spare128 parts listed as spare64, or parts missing from the table could not mount rootfs, and HW-D only accepted the Winbond W25N01GWZEIG. r8 uses the U-Boot handoff on all four boards, adds six missing parts, and makes the HW-D check follow the geometry U-Boot verified. Tested on HW-D (GD5F1GQ5REYIG spare128/ECC4, read-only RAM kernel) and with sysupgrade plus a cold-boot readback on HW-A, HW-B and HW-C. Requires H3C-NX30-Uboot v0.1.0-pre.5 or later.
