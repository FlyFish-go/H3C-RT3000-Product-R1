# 公开源码构建与验证

本仓库保留 OpenWrt 构建系统和 RT3000 集成，未包含下载缓存、工具链、构建产物或设备原始备份。2026-09-21 的 C13 在既有开发环境执行 `make -j8 V=s` 成功；本次源码脱敏运行离线回归，不重新构建或部署固件，也不宣称已完成全新环境的构建认证。

## 环境与依赖

历史构建使用 Ubuntu 22.04 / WSL2、ARM GCC 8.4.0、QSDK 11.5 和 Linux 5.4.164。构建所需的常见主机依赖包括 GCC/G++、make、git、Python 3、flex、bison、gawk、gettext、ncurses/SSL 开发包、rsync、unzip、zlib 和 coccinelle。旧 SDK 可能还需要 Python distutils、multilib 或其特定版本的依赖；请按主机系统和构建检查补齐。

`feeds.conf.default` 已固定 packages、LuCI、routing 和 telephony 的提交，不应直接换成最新分支后声称复现了原镜像。

```sh
./scripts/feeds update -a
./scripts/feeds install -a
cp rt3000-machine-b/config/candidate13.config .config
make defconfig
make -j8 download
make -j8 V=s
```

`candidate13.config` 保存当前目标、内存 profile、NSS 和软件包选择，需由 `make defconfig` 补齐依赖；它不包含运行中的 SSID、密码或私有地址。完整历史 `.config` 的哈希见 [C13 清单](../manifest/wifi5-candidate13-20260921.json)。

本地旧 feeds 缓存曾使 `scripts/diffconfig.sh` 报递归依赖（LuCI QoS、splash、dnsmasq 等）；因此没有把该脚本的部分输出当成可靠配置。公开片段直接从已保存的配置选择项提取。若新环境遇到同类问题，应核对固定 feeds、重复的软件包来源和安装链接，不能忽略错误后宣布构建成功。

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

构建成功不等于硬件验收。C13 应先用 initramfs 在 RAM 内验证，检查实际运行镜像、BDF、模块参数、网络、无线和健康状态。不要照搬其他机型的分区、环境变量或刷写命令。参见 [最新阶段记录](WIFI5_SESSION_2026-09-21.md) 和 [恢复说明](../release/RECOVERY.md)。
