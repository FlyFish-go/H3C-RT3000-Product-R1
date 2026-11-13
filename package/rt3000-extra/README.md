# H3C Magic extra packages

Packages for the extra package repository published with each QSDK release.
They are not in the images except `luci-theme-argon`.

| Directory | Source | Changes here |
|---|---|---|
| `luci-theme-argon` | jerrykuku/luci-theme-argon v2.3.2 (last release with Lua templates, for LuCI 21.02), Apache-2.0 | Screenshots removed |
| `luci-app-argon-config` | jerrykuku/luci-app-argon-config v0.9, Apache-2.0 (LICENSE from the project, which added it after v0.9) | depends on `luci-lib-ipkg`, which it uses |
| `adguardhome` | openwrt/packages master, net/adguardhome 0.107.80 | `memlimit` is in MiB as documented (was passed to `GOMEMLIMIT` as bytes); default 64 MiB; runs as root because this procd cannot grant capabilities |
| `luci-app-adguardhome` | openwrt/luci master | include path; opkg version syntax in the dependency |
| `tailscale` | openwrt/packages master, net/tailscale 1.104.4 | include path |
| `h3c-passwall` | this tree | meta package: PassWall, Xray and the iptables transparent proxy dependencies |
| `iptables-mod-socket` | this tree | empty package: on 21.02 the socket match ships in `iptables-mod-tproxy`, PassWall looks for this name |

OpenClash and PassWall come from the feeds pinned in `feeds.conf.default`;
`scripts/h3c-extra-feeds.sh` prepares them (Go 1.27, Xray override, sing-box
without `kmod-inet-diag`).

PassWall with Xray, and OpenClash with its core, do not fit the standard
dual-system layout (about 19 MB of overlay). Use the merged single-system
layout of the H3C Magic U-Boot rescue page.
