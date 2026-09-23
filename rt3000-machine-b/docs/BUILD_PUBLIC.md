# 公开源码构建与验证

本仓库保留 OpenWrt 构建系统和 RT3000 集成，未包含下载缓存、工具链、构建产物或设备原始备份。2026-09-21 的 C13 在既有开发环境执行 `make -j8 V=s` 成功；2026-09-22 的独立简体中文增量构建记录见 [中文构建记录](CHINESE_UI_2026-09-22.md)。随后打包的 **r5** 已在 RT3000 Machine-B 完成安装、升级、恢复出厂与双频连接实测，详见 [r5 发布说明](../release/RELEASE-NOTES-r5.md)。**公开源码尚未在全新环境完成独立构建认证，也不保证重建二进制与已发布附件逐字节相同。**

## 环境与依赖

历史构建使用 Ubuntu 22.04 / WSL2、ARM GCC 8.4.0、QSDK 11.5 和 Linux 5.4.164。构建所需的常见主机依赖包括 GCC/G++、make、git、Python 3、flex、bison、gawk、gettext、ncurses/SSL 开发包、rsync、unzip、zlib 和 coccinelle。旧 SDK 可能还需要 Python distutils、multilib 或其特定版本的依赖；请按主机系统和构建检查补齐。

`feeds.conf.default` 已固定 packages、LuCI、routing 和 telephony 的提交，不应直接换成最新分支后声称复现了原镜像。

```sh
./scripts/feeds update -a
./scripts/feeds install -a
cp rt3000-machine-b/config/candidate13.config .config
cat rt3000-machine-b/config/luci-zh-cn.config >> .config
cat rt3000-machine-b/config/ttyd.config >> .config
make defconfig
make -j8 download
make -j8 V=s
```

`candidate13.config` 保存当前目标、内存 profile、NSS 和软件包选择，需由 `make defconfig` 补齐依赖；它不包含运行中的 SSID、密码或私有地址。完整历史 `.config` 的哈希见 [C13 清单](../manifest/wifi5-candidate13-20260921.json)。

本地旧 feeds 缓存曾使 `scripts/diffconfig.sh` 报递归依赖（LuCI QoS、splash、dnsmasq 等）；因此没有把该脚本的部分输出当成可靠配置。公开片段直接从已保存的配置选择项提取。若新环境遇到同类问题，应核对固定 feeds、重复的软件包来源和安装链接，不能忽略错误后宣布构建成功。

## 简体中文界面

当前 RT3000 目标包含 `luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn` 和 `luci-i18n-opkg-zh-cn`，覆盖 LuCI 系统、网络、状态、防火墙及软件包管理界面。首次初始化默认选择简体中文；已有明确语言选择会保留，也可在“系统 → 系统 → 语言和界面”中修改。

`luci-zh-cn.config` 是新的中文配置叠加片段，历史 `candidate13.config` 和 C13 镜像身份保持原有含义。中文配置的构建及镜像检查另行记录，不代表历史 C13 已包含中文。

## TTYD、国内源与系统内升级

当前目标还内置 TTYD、LuCI 终端页面及中文翻译。首次启动会把原有官方 21.02.7 通用包源改为上海交大镜像，并注释不存在的官方 ipq50xx 内核源；自定义源和签名检查保持原设置。QSDK 内核模块仍需同次构建。

目标新增带完整载荷清单的 `nand-sysupgrade.bin`，专用流程仅接受 B 机并只更新第二槽位。构建、镜像审计和 44 项离线升级检查已通过；2026-09-23 的实机升级验收见 [系统内升级记录补记](SYSUPGRADE_2026-09-22.md)。镜像生成器 [`scripts/rt3000-sysupgrade.py`](../../scripts/rt3000-sysupgrade.py) 和 [隔离测试](../tests/sysupgrade/README.md) 随源码提供。

## 本次包含的源码

- `ipq50xx/arm`、RT3000 多 profile 目标、256M ath11k profile 与 NSS 支持。
- C5/C6/C10 兼容 BDF；外置硬件是 QCN6102，QSDK 名称是 QCN6122。
- 350 补丁：默认不生效的 RX A-MPDU 诊断写入接口。
- 604 补丁：仅针对 256M / QCN6122 的 RXDMA 2048 和配套 NSS 描述符数量。
- RT3000 网络、稳定身份、双副本启动选择及运行版本验证工具。

C11 的完整 OEM BDF 诊断输入不随公开导出分发；C11 生成器和测试只是历史工具，依赖该输入时会停止，不能把它纳入本次默认测试。当前 BDF 和 C13 不依赖这个被排除的输入。

某些历史发布工具引用字节固定的 `qca-ssdk.ko.b64`，该文件不在 Git 中。它用于旧发布镜像的二进制身份复现，不能用随意重编译的模块冒充相同哈希。源代码重编译与历史镜像逐字节复现是两个不同验证项目。

## 离线检查

以下命令使用本地合成样例或 mock transport，不连接路由器：

```sh
bash rt3000-machine-b/tests/mac/run_mac_tests.sh
bash rt3000-machine-b/tests/mac/run_config_path_tests.sh
bash tests/wifi/run_wifi_dup_tests.sh
python3 rt3000-machine-b/tests/wifi5_bdf/run_tests.py
sh rt3000-machine-b/tests/candidate10/run_static_checks.sh
python3 rt3000-machine-b/tests/device_control/run_tests.py
```

GitHub workflow 仅提供上述离线检查，不自动编译和发布固件、不自动操作设备或推送 gh-pages。

## 硬件验证边界

构建成功不等于硬件验收。C13 是历史 RAM 性能候选，r5 是后续在 B 机实测刷写与升级的发布附件；二者的哈希与验证范围不能互换。新构建应先核对镜像身份，再按其硬件范围做 RAM 与实机验证。不要照搬其他机型的分区、环境变量或刷写命令。参见 [C13 阶段记录](WIFI5_SESSION_2026-09-21.md) 和 [r5 恢复边界](../release/RECOVERY.md)。
