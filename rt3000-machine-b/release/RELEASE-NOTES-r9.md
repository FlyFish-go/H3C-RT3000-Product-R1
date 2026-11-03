# r9 — 修复无线默认配置、AP 下扫描、客户端互通和升级保留设置

本版修复 r8 引入的无线默认配置问题，以及两个一直存在的无线问题。问题见 [#2](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues/2) 和 QQ 群反馈。

## 修复内容

1. **HW-A/B/C 无线默认配置丢失（r8 回归）**
   r8 的四个镜像都误用了为 HW-D 构建的 base-files，HW-A/B/C 因此缺少首次启动的无线初始化脚本：两个频段默认关闭、SSID 不加密、没有国家码，无线 MAC 是通用的 `00:03:7f:…`（每台都一样）。r9 每块板单独重建 base-files，A/B/C 恢复与 r7 相同的默认配置。HW-D 不受影响。
2. **AP 运行时扫描结果为空**
   路由器开着 AP 时，LuCI「扫描」和中继/桥接向导看不到任何网络。QSDK 的驱动要求 AP 接口上的扫描带 `NL80211_SCAN_FLAG_AP` 标志，而 iwinfo 没带。r9 给 iwinfo 打了补丁，AP 接口上扫描会带这个标志。
3. **同一 AP 下的无线客户端互相不通**（#2，感谢 @Keridium 的详细分析）
   netifd 在没有设置 `multicast_to_unicast` 时会强制打开 `ap_isolate`，依赖网桥 hairpin 转发客户端之间的流量；但 NSS 无线加速绕过了 hairpin，所以客户端之间连 ARP 都不通，LuCI 里也关不掉。r9 不再强制隔离；在无线接口上勾选「隔离客户端」（`isolate=1`）仍然有效。
4. **保留配置升级不再重置无线设置**
   以前每次保留配置 sysupgrade 后，HW-A/B/D 的首次启动脚本都会把 SSID、密码、国家码和频宽改回默认值。现在和 HW-C 一样，只改系统新生成、从没被设置过的默认无线配置，其余一律保留。
5. **HW-D 状态灯**：加入红灯（GPIO23）和绿灯（GPIO24）的设备树节点。
6. **HW-D 全新安装后 LAN/WAN 反了、无线没开（r8 起）**
   r8 开始 U-Boot 把 ECC8 / spare 128 交给内核，HW-D 的 ENV 分区 OOB 大小从 64 变成 128，读出厂 MAC 的工具 `hwd-factory-mac` 因此拒绝读取，首次启动的网络和无线脚本提前退出：LAN 跑到了 WAN 口上，两个频段关闭、SSID 不加密、没有国家码。r9 接受两种 OOB 大小（工具只读数据区）。

## 说明：2.4G 40 MHz

2.4G 设为 40 MHz 后在 6、11、13 等信道上回落到 20 MHz，是 hostapd 按 802.11 的 20/40 MHz 共存规则检测到周围有重叠网络，不是故障。在 1 信道或自动信道下通常能用 40 MHz；确需强制使用，可在 LuCI 勾选「强制 40MHz 模式」（`noscan=1`），但这会干扰周围网络，也不符合规范。

## 验证范围

正式版镜像与测试版 r9rc3 逐字节相同，只改了文件名；下文的 rc2 / rc3 指测试版。

- 源码离线测试：WAN 链路、MAC 策略与配置路径、Wi-Fi 首启策略、5G BDF、静态源码检查、设备控制模拟共 7 组全部通过（两组旧 Wi-Fi 测试已按 r9 的新首启策略更新，断言未放宽）；新的首启策略测试 12/12 通过。
- 四块板镜像离线检查：首次启动脚本、uboot_env、pin 工具的文件集合与 r7 一致；netifd 不再强制隔离；iwinfo 含 AP 扫描标志；HW-D 设备树含红/绿状态灯。
- HW-A 实机（全新写入）：首次启动两个频段开启、WPA2 加密、国家码 CN，无线 MAC 来自本机；AP 运行时扫描 3/3 次有结果（2.4G 8 个、5G 6 个），无崩溃；同一 5G AP 下两个客户端互 ping 双向 4/4（r8 为 0/4）；2.4G 40 MHz 在 1 信道和自动信道生效，6 信道因共存回落 20 MHz；运行 5 分钟无 panic/OOM，可用内存约 70 MB。
- HW-A 升级（r9rc2）：r8 原样配置保留配置升级 → 自动改为默认值；r8 上手动设置过无线（US、自定义 SSID/密码、149 信道 HE40、主机名）→ 全部保留，只把通用 MAC 换成本机 MAC；r9 上修改 5G 设置后再次保留配置升级 → 修改保留；恢复出厂 → 回到默认值。
- HW-D 实机（r9rc3，GD5F1GQ5 + ECC8 交接，U-Boot 6d377e7d 单次引导）：全新写入 → LAN=eth1（交换机口）、WAN=eth0，SSH 直接从 LAN 口可达；两个频段开启、WPA2、国家码 CN，信标 BSSID 为本机 MAC +2/+3；绿灯亮。r9rc2 首启的错误状态保留配置升级到 rc3 → 无线自动修正为默认值（网络配置按规则保留，见下）。
- HW-B / HW-C 实机（全新写入，单次引导）：B（ECC8）LAN=eth1、WAN=eth0，两个频段开启、WPA2、国家码 CN，无线 MAC 来自本机，hostapd 正常，可用内存约 72 MB；C（RTL8367S，ECC4）同样的默认无线配置和本机 MAC，LAN 口 SSH 可达，可用内存约 52 MB。均无崩溃。

## 安装与升级

与 r8 相同：需要 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) v0.1.0-pre.5 或更新（推荐最新版）。按硬件系列选择 `H3C-Magic-r9-HW-A/B/C/D-*`。`nand-factory.ubi` 在 U-Boot 救援页写入，`sysupgrade.bin` 用于系统内升级。安装前核对 SHA256SUMS。

**从 r8 保留配置升级**：HW-A/B/C 上 r8 留下的无线配置（关闭、未加密、无国家码）会在升级后首次启动时自动改成上面的默认值，无需恢复出厂。如果你已经在 r8 上手动设置过无线，你的 SSID、密码、国家码、频宽和信道都会保留，只会补上本机的无线 MAC（替换 `00:03:7f:…`）。

**HW-D 用户注意**：如果你是在 r8 上**全新安装**的 HW-D，网络配置里 LAN/WAN 是反的。保留配置升级不会改动你的网络设置（无线会自动修正），请升级时**不保留配置**，或升级后恢复出厂设置。从 r7 或更早版本保留配置升级上来的 HW-D 不受影响。

已经在 r8 上手动去掉 `isolate` 的用户，升级后无需再改 netifd 脚本。

## English summary

r8 shipped HW-D base-files in all four images, so HW-A/B/C booted with both radios disabled, open SSIDs, no country code and the same generic wlan MAC on every unit; r9 rebuilds base-files per board. iwinfo now sets NL80211_SCAN_FLAG_AP when scanning on an AP interface, so scans work while the AP is up. netifd no longer forces ap_isolate when multicast_to_unicast is unset (with NSS Wi-Fi offload the bridge hairpin was bypassed, so clients of the same AP could not reach each other, #2); an explicit isolate=1 still works. A keep-settings sysupgrade no longer resets the user's Wi-Fi on HW-A/B/D: only the untouched mac80211 template gets the product defaults (as HW-C already did), other APs only gain a missing factory MAC. HW-D gets its status LED nodes. On HW-D, since r8 the ENV partition reports a 128-byte OOB (ECC8 handoff), which hwd-factory-mac rejected, so a fresh install came up with LAN/WAN swapped and radios disabled; r9 accepts 64 and 128 (only the data area is read). HW-D units that were freshly installed with r8 should upgrade without keeping settings (network config is kept as-is by sysupgrade). 2.4 GHz 40 MHz falling back to 20 MHz on busy channels is hostapd 20/40 coexistence, not a bug. The release images are byte-identical to the tested r9rc3 build. Tested on all four boards with a fresh install, keep-settings upgrades on HW-A and HW-D, AP scanning and client-to-client traffic on HW-A. Requires H3C-NX30-Uboot v0.1.0-pre.5 or later.
