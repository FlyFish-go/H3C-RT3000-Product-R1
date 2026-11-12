# r11 — 软件源换阿里云、可以装内核模块、OpenVPN / WireGuard / Tailscale、zram

问题来自 [H3C-Magic-NSS #2](https://github.com/FlyFish-go/H3C-Magic-NSS/issues/2) 和群里的反馈：r10 的软件源在国内用不了；OpenVPN、Tailscale、UDPspeeder 这类软件装不上，因为缺内核模块和 C++ 运行库。

## 修复内容

1. **软件源用不了**
   r10 把 OpenWrt 21.02.7 的软件源指向上海交大镜像，现在国内访问失败。r11 改用阿里云镜像（`mirrors.aliyun.com`），它的证书能被 21.02 自带的根证书验证。从 r10 保留配置升级时会自动改写 `/etc/opkg/distfeeds.conf`，不需要手动改。
2. **内核模块（kmod）装不上**
   这个 QSDK 内核在官方没有对应的 core 源，`opkg install kmod-…` 一直找不到包。r11 起，本项目为每个版本发布自己的内核模块源（GitHub Pages），目录以内核版本命名，`opkg` 只会拿到和当前内核完全匹配的模块。源里有 WireGuard、TPROXY、ipset、BBR、macvlan、bonding、veth、dummy、sit / ip6-tunnel / gre6、L2TP、NAT6、iptables 扩展等模块，和官方软件源一样做了签名校验。
3. **WireGuard 内核模块是空的**
   21.02 的 `kmod-wireguard` 依赖内核里的 WireGuard 回移补丁，QSDK 内核没有，所以打包出来没有模块。r11 改用官方的 wireguard-linux-compat（给 5.6 以前内核用的树外模块），包名不变，官方源里的 `wireguard-tools`、`luci-proto-wireguard` 可以直接装。
4. **路由器自己发 UDP 隧道包时内核崩溃**
   高通在 QSDK 内核的 `iptunnel_xmit()` 里加了 VXLAN 判断，但没检查入口网卡是否为空。路由器本机发出的隧道包（例如 WireGuard 握手）没有入口网卡，第一次握手就会内核 panic 重启。r11 补上了这个检查。

## 新功能

- **镜像内置** `kmod-tun`（OpenVPN、Tailscale 需要）、`libstdcpp6`、`libatomic1`（UDPspeeder 等 C++ 程序需要），以及 **zram 压缩交换**（约 81 MiB，内存不足时先压缩到内存里，而不是直接触发 OOM）。
- **常用软件可以直接装**（先 `opkg update`）：
  - OpenVPN：`opkg install openvpn-openssl luci-app-openvpn`
  - WireGuard：`opkg install kmod-wireguard wireguard-tools luci-proto-wireguard`
  - Tailscale：`opkg install tailscale`
  - UDPspeeder：`opkg install UDPspeeder`

## 已知情况

- **空间有限**：双系统布局下 overlay 约 19.8 MiB。Tailscale 一个包就要十几 MiB；OpenVPN + Tailscale + UDPspeeder 装完只剩约 3.6 MiB。需要装更多软件时，可以在 U-Boot v0.1.0 下切换到单系统 80 MiB 分区（overlay 约 57 MB）。
- **Tailscale 版本旧**：21.02 软件源里只有 1.24.2（2022 年）。现在还能连上官方服务器、拿到登录链接，但 Tailscale 以后可能不再支持这么旧的客户端。
- **内存**：256 MB 机型留给 Linux 约 166 MiB。zram 能缓解，但 AdGuard Home（大规则列表）和 Tailscale 同时运行仍然很紧。
- **内核模块源在 GitHub Pages 上**：如果访问不了 GitHub，`opkg update` 只有 `h3c_magic_core` 这一项失败，其他官方源照常更新。
- 自己安装的软件在 sysupgrade 后不保留（OpenWrt 的正常行为），升级后重新安装；内核模块要用新版本对应的源。
- r10 的其他已知情况（UPnP、SQM、160 MHz、2.4G 中继等）不变，见 [r10 发布说明](RELEASE-NOTES-r10.md)。

## 验证范围

本轮台架上只有 **HW-C**。HW-A/B/D 镜像用同一份源码构建，本轮改动（软件包、软件源脚本、一个内核补丁）不涉及板级代码，但没有在实机上重新验证。

- **升级路径**：HW-C 从 r10 正式版保留配置升级，主机名等设置保留，软件源自动从交大改为阿里云并加上本项目的模块源；之后 rc1 → rc2 → rc3（发布版）继续保留配置升级正常。
- **软件源**：`opkg update` 全部源签名校验通过（台架在美国，阿里云经代理访问；模块源用与 Pages 相同的文件在局域网提供）。
- **软件**：OpenVPN 2.5.3 能创建 tun 设备；Tailscale 1.24.2 的 tailscaled 正常运行、创建 `tailscale0`，从官方控制服务器拿到登录链接；WireGuard 与局域网主机建立隧道，握手正常，iperf3 248 / 271 Mbit/s（路由器发 / 收），CPU 约 90% 空闲，无 Oops；UDPspeeder 正常链接 `libstdc++.so.6` 并运行；TPROXY、BBR、macvlan、sit 模块正常加载。
- **回归**：有线 NAT 双向 941 Mbit/s；2.4G / 5G AP 正常启动；zram 81 MiB 生效；冷启动 5 次（已装 WireGuard 等模块、开机自动加载），25–26 秒可以 SSH，两个 AP 都起来，WAN 拿到地址，无 panic / OOM。

## 安装与升级

需要 [H3C-NX30-Uboot](https://github.com/FlyFish-go/H3C-NX30-Uboot) v0.1.0-pre.5 或更新，推荐 v0.1.0。按硬件系列选择 `H3C-Magic-r11-HW-A/B/C/D-*`。`nand-factory.ubi` 在 U-Boot 救援页写入，`sysupgrade.bin` 用于系统内升级。安装前核对 SHA256SUMS。

从 r10 / r9 可以保留配置升级。

## English summary

r11 fixes package installation. The OpenWrt 21.02.7 feeds now use the Aliyun mirror (the SJTU mirror no longer works from China); a keep-settings upgrade rewrites `distfeeds.conf`. This QSDK kernel has no upstream core feed, so the project now publishes its own signed kernel-module feed on GitHub Pages, one directory per kernel version (WireGuard, TPROXY, ipset, BBR, macvlan, bonding, veth, tunnels, L2TP, NAT6, iptables extensions). `kmod-wireguard` was an empty package because the QSDK kernel lacks the WireGuard backport; it is now built from wireguard-linux-compat. A QSDK change in `iptunnel_xmit()` dereferenced a NULL input device for locally generated UDP tunnel packets, so the first WireGuard handshake panicked the kernel; fixed. The image now includes `kmod-tun`, `libstdcpp6`, `libatomic1` and zram swap (~81 MiB), so OpenVPN, Tailscale (1.24.2 from the 21.02 feed), WireGuard and C++ programs such as UDPspeeder install with `opkg`. The overlay is about 19.8 MiB in the dual-system layout (Tailscale alone takes over 10 MiB). Validated on HW-C only this round (keep-settings upgrade from r10, all of the above, wired NAT 941 Mbit/s, WireGuard 248/271 Mbit/s); HW-A/B/D images are built from the same source but were not re-tested on hardware.
