# r14 — 中继信道修复、在线更新、Argon 主题、温度显示、插件源

r12、r13 只是在线更新功能的内部测试版本号，没有发布。

## 修复内容

1. **中继（STA）连上级以后，本机 5G Wi-Fi 起不来，LuCI 保存后回滚**（群里反馈）
   STA 连上上级 AP 后，hostapd 会把本机 AP 切到上级的信道，但 21.02 的 hostapd 只改了信道号，80 MHz / 160 MHz 的中心频点还是按原来的信道算的。上级是 20 MHz、在另一个 80 MHz 频段，或者本机信道设成 auto 时，本机 AP 就一直起不来，LuCI 等不到确认便回滚。r14 按本机设置的带宽重新推算副信道和中心频点：信道设 36 或 auto，连上 40 信道的上级后，本机 AP 都会跟到 40 信道、80 MHz。auto 时如果先选到了 DFS 信道，第一次要多等约 1 分钟雷达检测。

## 新功能

- **在线更新**：系统 → 备份与升级 → 在线更新。检测、下载、校验签名、安装，可选保留配置；默认不自动检测，可在页面里打开（默认间隔 12 小时）。版本清单同时放在 GitHub 和 Gitee，路由器自动选能连上的那个。只有发现新版本时，概览页才会多出一行提示。
- **温度显示**：概览页新增"温度"一节，显示处理器（4 个传感器中最高的那个）、2.4 GHz 和 5 GHz 无线的温度（[H3C-Magic-NSS #2](https://github.com/FlyFish-go/H3C-Magic-NSS/issues/2)）。
- **Argon 主题**：默认使用 Argon（v2.3.2，支持 LuCI 21.02 的最后一版），Bootstrap 仍可在 系统 → 系统 → 语言和界面 里切换。
- **插件源**：本项目新增一个软件源（`h3c_magic_extra`，GitHub Pages），放 21.02 官方源里没有或太旧的插件：
  - PassWall：`opkg install h3c-passwall`（PassWall、Xray 和透明代理需要的全部组件一次装好）；sing-box、hysteria 等可另外安装
  - OpenClash：`opkg install luci-app-openclash`（内核在 OpenClash 页面里下载）
  - Tailscale 1.104.4（官方 21.02 源里只有 2022 年的 1.24.2）：`opkg install tailscale`
  - AdGuard Home 0.107.80 和 LuCI 页面：`opkg install luci-app-adguardhome luci-i18n-adguardhome-zh-cn`。默认内存软限制 64 MiB（上游的 `memlimit` 写着 MB，实际按字节传给 Go，等于没设，这里改对了）
  - Argon 主题设置：`opkg install luci-app-argon-config luci-i18n-argon-config-zh-cn`
- **精简**：DDNS、UPnP、WoL、ttyd（网页终端）和 iperf3 不再预装，需要时用 `opkg install luci-app-ddns` 等安装。SQM 继续预装（它依赖的 tc 和 iptables 模块官方源里没有，而且开启时会自动暂停 NSS 加速）。`dnsmasq` 换成 `dnsmasq-full`，代理插件可以一步装好。

## 已知情况

- **代理插件需要大分区**：Xray 一个程序就有约 30 MB，双系统布局的 overlay 约 19 MB，装不下。用 U-Boot v0.1.0 救援页的"大分区（单 rootfs 80 MiB）"后 overlay 约 57 MB，够装 PassWall + Xray。r14 内核也已支持下一版 U-Boot 的"超大分区（116 MiB，overlay 约 83 MB）"，等那一版 U-Boot 发布后可用。大分区下不能运行原厂固件。
- **AdGuard Home 以 root 运行**：上游包用 procd 给普通用户授予绑定 53 端口的权限，21.02 的 procd 不支持，所以改成 root。
- **sing-box** 不支持"按进程分流"（这个内核没有 `inet_diag`）；shadowsocks-rust、shadow-tls 需要 Rust 工具链，SSR 在 21.02 上编译不过，本版不提供。
- **路由器时间不对时 HTTPS 会失败**（在线更新、opkg、插件下载都受影响）。正常联网后 NTP 会自动校时。
- 自己安装的插件在 sysupgrade 后不保留（OpenWrt 的正常行为），在线更新安装新版本后也要重新安装。
- r11 的其他已知情况不变，见 [r11 发布说明](RELEASE-NOTES-r11.md)。

## 验证范围

本轮台架上只有 **HW-B**。HW-A/C/D 镜像用同一份源码构建；本轮改动里 hostapd、温度上报、主题和插件源对四种主板都一样，但没有在 A/C/D 实机上重新验证。

- **升级路径**：HW-B 从 r11 正式版保留配置升级到 r14：主机名、Wi-Fi 名保留，主题自动换成 Argon，软件源自动改为 r14 的内核模块源并加上插件源，dnsmasq-full 正常运行；之后冷启动 3 次，35–38 秒可以 SSH，两个 AP 和 WAN 都正常。
- **中继**：本机 5G 设为 36 信道（HE80）或 auto，STA 连 40 信道的上级（20 MHz）后，本机 AP 跟到 40 信道 80 MHz，客户端在 5200 MHz 连接并 ping 通。
- **在线更新**：r12 → r13 测试版本上，检测（路由器和浏览器两种方式）、下载、签名校验、保留配置安装、不保留配置安装、已是最新、只用 Gitee、服务器不通都正常；路由器从 GitHub 真实下载 Release 附件，sha256 一致。
- **温度**：处理器 51–58 °C，2.4 GHz（IPQ5018 内置）约 65 °C，5 GHz（QCN6122）约 43 °C；打开温度上报后两个射频照常工作。
- **插件**（大分区上）：`h3c-passwall` 一步装好，配置一个节点后 PassWall（iptables 模式）从 LAN 访问 GitHub 返回 200，流量确实经过节点；OpenClash、Tailscale 1.104.4、AdGuard Home 0.107.80（`GOMEMLIMIT=64MiB` 生效，常驻约 22 MB）都能安装和运行，LuCI 页面正常。
- **精简**：DDNS、UPnP、ttyd、iperf3 从阿里云源装回后可以正常使用。

## 安装与升级

需要 [U-Boot](https://github.com/FlyFish-go/IPQ50XX-Uboot) v0.1.0-pre.5 或更新，推荐 v0.1.0。按硬件系列选择 `H3C-Magic-r14-HW-A/B/C/D-*`。`nand-factory.ubi` 在 U-Boot 救援页写入，`sysupgrade.bin` 用于系统内升级。安装前核对 SHA256SUMS。

可以从 r11 保留配置升级。

## English summary

r14 fixes repeater mode: when a client (STA) interface joined an uplink on another channel, 21.02's hostapd moved the local AP to that channel without recomputing the VHT/HE centre frequency (and kept ACS on for channel auto), so the 5 GHz AP stayed down and LuCI rolled the change back; the AP now follows the uplink at its configured width. New: an online updater (System -> Backup / Flash Firmware -> Online update; signed manifest on GitHub and Gitee, automatic checks off by default), SoC and Wi-Fi temperatures on the status overview, the Argon theme by default (v2.3.2, the last release for LuCI 21.02), and an extra package feed with OpenClash, PassWall (`opkg install h3c-passwall` pulls in Xray and the transparent proxy pieces), Tailscale 1.104.4 and AdGuard Home 0.107.80 with its LuCI page (its `memlimit` option is now really in MiB, default 64). DDNS, UPnP, WoL, ttyd and iperf3 are no longer preinstalled (install them with opkg); dnsmasq-full replaces dnsmasq. Proxy plugins need the merged single-system layout of U-Boot v0.1.0 (80 MiB, about 57 MB overlay); the kernel already supports the coming 116 MiB layout. Validated on HW-B only (keep-settings upgrade from r11, repeater, updater, temperatures, plugins, cold boots); HW-A/C/D are built from the same source but were not re-tested on hardware.
