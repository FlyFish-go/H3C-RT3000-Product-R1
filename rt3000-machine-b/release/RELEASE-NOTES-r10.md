# r10 — IPv6、SQM、Wi-Fi↔LAN 桥接加速、中继修复

本项目第一个正式版。问题见 [#3](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/issues/3) 和 QQ 群反馈。

## 修复内容

1. **WAN 口 IPv6 拿不到地址**
   产品自带的防火墙配置替换了 OpenWrt 默认配置，但漏掉了 `Allow-ICMPv6-Input` / `Allow-ICMPv6-Forward` 两条规则，wan 区域也没有包含 `wan6`。上级发来的 RA/NS/NA 被拒绝，所以没有 IPv6 默认路由。r10 补上这两条规则和 `wan6`；保留配置升级时由迁移脚本自动补上，不需要恢复出厂。
2. **无 5 GHz FEM 的 D 板（如部分 RC3000）5G 信号很弱**（#3）
   HW-D 镜像首次启动时读取本机 ART，判断 5 GHz 是否带 FEM：没有 FEM 时自动改用 HW-B 的无线板数据，并在系统日志和 LuCI 状态页提示「这台应使用 HW-B 镜像」。这类机器可以直接 sysupgrade 到 HW-B 镜像，不需要 `-F`（不保留配置）；带 FEM 的 D 板会拒绝 HW-B 镜像。docs/HW-ABCD-CLASSIFICATION.md 里关于 RC3000 B0 的分类已更正。
3. **中继/桥接时上级路由器每次看到的 MAC 都不一样**
   STA 接口没有设置 MAC 时，系统用无线芯片里的占位地址 `00:03:7f:…` 生成 MAC。r10 改为由本机出厂 MAC 派生一个本地管理地址（与 AP 地址不同），重启和无线重载后保持不变。
4. **无线偶尔首次启动失败、需要重试**
   OpenWrt 21.02 随机生成 HE BSS color 的写法大约每 10 次会算出空值或 `08`/`09` 这类被当作八进制的数，射频初始化报 `arithmetic syntax error`，netifd 重试后才起来。r10 改用一个随机字节。
5. **2.4G 中继：上级路由器断开约 1 分钟后整机重启**
   2.4G 做中继（STA）时，如果上级 AP 消失，IPQ5018 的 2.4G 无线固件大约 1 分钟后就会崩溃，每次都会。驱动默认不做固件恢复，直接触发内核 panic，整机重启，这很可能就是「2.4G 中继十几分钟掉线」的原因。r10 开机后自动打开 ath11k 的固件恢复，固件崩溃时只重启 2.4G 无线（约 3 秒），上级恢复后自动重连；同时修了恢复失败时驱动清理 NSS 资源的空指针。5G 中继没有这个问题。如果中继需要长期稳定，建议用 5G。
   **中继的上级路由器请用 WPA2-AES（CCMP）加密**：测试者把光猫从 WPA/WPA2 混合加密改成 WPA2-AES 后，掉线间隔从十几分钟变成 14 小时以上。如果仍然掉线，请先不要重启无线，执行 `logread | grep -iE 'wpa|wlan|sta0|ath11k|hostapd|netifd' | tail -200` 和 `dmesg | tail -100`，把输出发到群里或 issue。
6. **内核模块里带有构建机路径**：7 个 backports 无线模块（ath11k、mac80211、cfg80211 等）里残留了构建机的目录路径，r10 已去掉。

## 新功能

- **Wi-Fi ↔ LAN 桥接加速**：无线客户端和有线 LAN 主机之间（同一网段、经过 br-lan 桥接）的流量以前全部由 CPU 转发，5 GHz 跑满时 CPU 约 55–60%；r10 恢复了 NSS ECM 的桥接钩子，这部分流量也走硬件加速，CPU 降到约 4–5%，吞吐不变（受无线链路限制）。防火墙规则对局域网内部流量的处理与以前相同。客户端在 5 GHz 和 2.4 GHz 之间切换时约 2 秒恢复。可以在「网络 → 硬件加速」关闭。
- **SQM（cake）**：LuCI「网络 → SQM QoS」，默认关闭，接口已指向本机 WAN 口。
- **硬件加速开关**：LuCI「网络 → 硬件加速」。启用任何一条 SQM 队列时会自动暂停 NSS 加速（否则加速的流量不经过 SQM，限速无效），关闭 SQM 后自动恢复。不需要重启。
- **UPnP、DDNS、网络唤醒（WoL）**：LuCI 应用，默认关闭。

## 已知情况

- **UPnP 在光猫后面不生效**：WAN 口是私网地址（如 192.168.x.x、10.x.x.x）时，miniupnpd 会拒绝端口映射（日志：`Reserved / private IP address … Port forwarding is impossible`）。这是 miniupnpd 的设计。请把光猫改成桥接、由本路由器拨号。UPnP 设置里的 STUN 只能探测公网地址，上级 NAT 不放行时仍然无效。
- **开启 SQM 后速度变慢是正常的**：SQM 由 CPU 做整形，加速会暂停；千兆宽带不建议开。
- **关闭硬件加速时，Wi-Fi ↔ LAN 桥接流量的 CPU 占用比 r9 高**（HW-D 5 GHz 约 66–86%，r9 约 55–60%），因为桥接流量现在要经过连接跟踪。默认开启加速时没有这个开销。
- **5G 160 MHz**：在 36 信道使用 160 MHz 时覆盖 DFS 信道 52–64，每次无线启动要先做 60 秒雷达检测，期间看不到 5G；路由器自己做扫描（中继向导/LuCI 扫描）时也会是空的。需要中继或扫描时请用 80 MHz。149 信道不支持 160 MHz。
- **2.4G 40 MHz**：在 6、11、13 等信道回落到 20 MHz 是 20/40 MHz 共存规则，不是故障（同 r9 说明）。
- **中继时上级断开，同频段 AP 会暂停**：STA 连不上上级时，同一频段的 AP 会一起暂停，上级恢复后自动恢复。这是 OpenWrt 的行为。

## 验证范围

- **正式版镜像（rc6）**：A/C 从 r10 测试版、D 从 r9 之前的版本保留配置升级，迁移脚本自动补上桥接加速设置；B 此前装的是 HW-D 镜像（模拟无 5G FEM 的 D 板），升级时按规则换成 HW-B 镜像、不保留配置。冷启动 A、C、D 各 5 次，换上 U-Boot v0.1.0 后 A/B/C/D 再各 3 次，无 panic/OOM，25–30 秒可以 SSH（B 全新安装后首次启动 48 秒），两个频段 AP 都起来，WAN 拿到地址。桥接加速：A 489/471、B 520/527、C 570/561、D 537/563 Mbit/s（客户端→LAN / LAN→客户端），CPU 4–5%，ECM 有连接；HW-D 关闭加速开关后 ECM 为 0、流量照常，打开后恢复；有线 NAT 双向 940 Mbit/s。
- **大分区**：HW-A 在 U-Boot v0.1.0 下切换到单系统 80 MiB 分区，写入本版，内核收到 `h3c.boot_slot=0x900000 h3c.boot_size=0x5000000`、overlay 约 57 MB；保留配置升级、冷启动 5 次通过，桥接加速 500/404 Mbit/s、CPU 3–4%；之后恢复双系统，两个槽与备份逐字节一致。
- **2.4G 中继长测（约 1 小时，每 5 秒检测一次连通）**：WPA2-AES 每 60 秒换组密钥 30 分钟 0 次掉线；上级 AP 关闭再打开 5 次，每次都自动重连（4 次约 11 秒，1 次 80 秒）；上级换信道 1→6→11→1 三次，都在约 6 秒内跟随；WPA/WPA2 混合（TKIP）每 60 秒换密钥 15 分钟 0 次掉线；全程无固件崩溃、无重启。测试者 14 小时后的那次掉线在台架上没有复现。
- 四块板实机（`0x900000` 槽，U-Boot 单次引导）：HW-A/C/D 用 RA 测试 WAN IPv6，都能拿到地址和默认路由，`ping6` 通（r9 对照不通）；有线 NAT 双向 941 Mbit/s（A、C），开 SQM（100/50M）时为 96/48 并自动暂停加速，关闭后恢复；加速开关关闭 870 Mbit/s、软中断 47%，打开 941 Mbit/s、CPU 95% 空闲。
- 中继 MAC：A 的 2.4G STA 用本机派生地址，3 次无线重载、5 次冷启动不变。
- 保留配置升级：D 从 r9 正式版升级，SSID、主机名、静态 DHCP 保留，防火墙自动补上 ICMPv6/wan6；rc3→rc4→rc5 在 A/B/C/D 上保留配置升级正常。
- 无 FEM 判定：带 FEM 的 D 识别为 fem，拒绝 HW-B 镜像；在无 5G FEM 的板子上运行 HW-D 镜像，识别为 nofem，5G 使用 HW-B 数据（board id 0x90），同一位置的客户端信号从 -71 提高到 -20 dBm，下行从 144 提高到约 720 Mbit/s；允许升级到 HW-B 镜像，不保留配置。
- 2.4G 中继：上级 AP 开关 15 轮，固件崩溃 14 次，全部只重启 2.4G，整机无重启，每轮上级恢复后都能重连（r10 之前：第一次崩溃就整机重启）。
- 冷启动：A 5/5、C 10+5、D 10+5 次，无 panic/OOM，25–29 秒可以 SSH；HE BSS color 修复后连续 20 次无线初始化 0 失败。
- UPnP：SSDP/NAT-PMP 正常，WAN 为公网地址时能添加转发规则，私网 WAN 下按 miniupnpd 设计拒绝。

## 安装与升级

需要 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) v0.1.0-pre.5 或更新，推荐同时发布的 v0.1.0 正式版。按硬件系列选择 `H3C-Magic-r10-HW-A/B/C/D-*`。`nand-factory.ubi` 在 U-Boot 救援页写入，`sysupgrade.bin` 用于系统内升级。安装前核对 SHA256SUMS。

从 r9 可以保留配置升级：无线、DHCP、主机名等设置保留，防火墙自动补上 IPv6 规则。

**无 FEM 的 D 板用户**：可以直接升级 r10 的 HW-D 镜像（5G 会自动改用 HW-B 数据），也可以改装 HW-B 镜像（推荐，不保留配置）。r9 的 HW-D 系统还不认识这条规则，从 r9 直接换 HW-B 镜像时需要 `sysupgrade -F -n` 一次。

## English summary

r10 is the first stable release. Bridged Wi-Fi <-> LAN traffic is now NSS-accelerated (CPU ~55-60 % -> ~4-5 % on 5 GHz at the same throughput; firewall behaviour for LAN-internal traffic unchanged; can be switched off under Network > Hardware acceleration). For 2.4 GHz repeaters use WPA2-AES on the upstream router. IPv6 on WAN now works: the product firewall lacked the ICMPv6 input/forward rules and wan6 (a keep-settings upgrade migrates old configs). HW-D images detect a board without 5 GHz FEMs from ART and use the HW-B board data, warn in the log and LuCI, and accept a sysupgrade to the HW-B image (#3). Repeater/STA interfaces get a stable MAC derived from the factory MAC instead of one built from the 00:03:7f placeholder. In 2.4 GHz repeater mode the IPQ5018 WLAN firmware crashes about a minute after the upstream AP disappears; ath11k's default (no firmware recovery) turned that into a kernel panic and reboot. r10 enables ath11k firmware recovery at boot (the radio restarts in ~3 s; bench: 14 crashes in 15 upstream drops, no reboot) and fixes a NULL dereference in the NSS teardown after a failed recovery. The random HE BSS color no longer fails shell arithmetic about one radio setup in ten. Build-host paths were removed from the backports modules. New: SQM (cake, off by default), a hardware-acceleration switch that pauses NSS acceleration while any SQM queue is enabled, and UPnP/DDNS/WoL (off by default). Note: miniupnpd refuses mappings when WAN has a private address (behind an ISP router).
