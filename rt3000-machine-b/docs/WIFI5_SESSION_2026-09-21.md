# RT3000 5 GHz 上行优化阶段记录（2026-09-21）

本轮按用户要求暂停，停止继续扩展。最后两次手机单流上传服务端结果为 **760、789 Mbps**；四流上传为 **879 Mbps**。**重复单流上传 ≥800 Mbps 的目标尚未通过**，不将四流结果、单秒峰值或手机显示值替代验收结果。

这里的 `WIFI5` 是项目中“5 GHz”的任务名称；实际使用 **802.11ax / HE160**，不是将协议限定为 Wi-Fi 5 / 802.11ac。本记录更新了 [历史实验日志](RC1_WIFI5_PERF_001.md) 中 Candidate 10–13 的后续状态，不改变已有 R1-NET-D 验收结论。

## 当前保留状态

| 项目 | 停止时状态 |
|---|---|
| 硬件 | H3C RT3000 Machine-B，256 MiB；IPQ5018 + 外置 **QCN6102** |
| 软件目标名称 | QSDK 11.5 使用 `QCN6122` / `qcn6122` 表示该外置无线目标 |
| 系统 | Candidate 13，Linux 5.4.164，initramfs / tmpfs RAM 启动 |
| 5 GHz | CN，主信道 **44**，HE160，中心频率 **5250 MHz** |
| 2.4 GHz | 本轮性能测试期间关闭；未完成本候选的双频并发回归 |
| NSS 路径 | `ath11k nss_offload=1 frame_mode=2`；`mac80211 nss_redirect=N` |
| BDF | 沿用 C5/C6/C10 的已验证兼容 BDF；未采用 C11 OEM schema-lift BDF |
| 接收聚合覆盖 | C13 未写入 `rx_ampdu_aggr_size`，补丁 350 保持默认不生效 |
| 停止时内存 | `MemAvailable=59140 kB`；未见新增 OOM / panic / firmware assert |
| 信道 60 | 工单已取消，**未执行**信道修改或对照测试 |
| 持久化 | 本轮没有写入 RT3000 闪存、MTD、ART、BOOTCONFIG 或 `saveenv` |

停机核验时间为 2026-09-21 14:45:05 UTC（北京时间 22:45:05）。设备未关机，保留当前 RAM 配置。重启后不能假设 C13、实验地址和信道仍然存在。

## 拓扑和测量方法

最终有效性能路径为：

```text
iQOO Neo10 -- 5 GHz HE160 --> RT3000 LAN bridge -- 千兆以太网 --> Windows PC / iperf3 3.21
```

主路由连接 RT3000 WAN；跳板机板载千兆口连接 RT3000 LAN，USB 2.0 网卡连接主路由用于管理。Windows PC 有线口连接 RT3000 LAN，保留原有 Wi-Fi 管理连接。跳板机已退出最终吞吐测试的服务端角色。

每次 TCP 测试约 10 秒。上传以服务端 `receiver` 汇总为准，下载以服务端 `sender` 汇总为准；四流使用 `[SUM]` 汇总。测试编号只在本轮 PC 服务端日志内有效，与旧跳板机日志编号不同。表中的速率单位均为十进制 Mbps。

## 服务端结果

| PC 测试编号 | 客户端及条件 | 方向 / 流数 | 服务端结果 |
|---|---|---|---:|
| 1、2 | RT3000 → PC，纯有线控制 | 上传 / 1 | 937、938 |
| 3、4 | iQOO Neo10，信道 36 | 上传 / 1 | 680、649 |
| 5 | iQOO Neo10，信道 36 | 下载 / 1 | 689 |
| 6 | 小米平板 5 Pro 12.4，HE80 | 上传 / 1 | 544 |
| 7 | 小米平板 5 Pro 12.4，HE80 | 下载 / 1 | 411 |
| 8 | iQOO Neo10，信道 36 | 上传 / **4** | **879** |
| 9 | iQOO Neo10，信道 36 | 下载 / 4 | 780 |
| 10 | iQOO Neo10，信道 36 | 上传 / 1 | 738 |
| 11、12 | iQOO Neo10，信道 36，近距离无遮挡 | 上传 / 1 | 708、721 |
| 13 | iQOO Neo10，信道 36，PC 同步抓包 | 上传 / 1 | 731 |
| 14、15 | iQOO Neo10，信道 **44**，HE160 | 上传 / **1** | **760、789** |

最后两次完整 10.01 秒平均值均未达到 800；测试 14 的首秒为 358 Mbps，后续存在 909 Mbps 的单秒值，不能去掉首秒后重算成验收通过。测试 15 期间五个有效采样点上行 PHY 为 2161.3 Mbps，RSSI 为 −44/−45 dBm；PHY 速率不等于有效吞吐。

信道 44 是当前保留的较好实测配置，但测试不是充分重复、交错进行的信道 A/B，不能把全部提升归因于换信道。平板协商 HE80，与手机 HE160 条件不同，不能据此判定手机或固件优劣。

可核查数据：[完整结果 CSV](evidence/2026-09-21-wifi5/server-results.csv)、[脱敏服务端原始片段](evidence/2026-09-21-wifi5/server-selected-redacted.log)、[构建及验收清单](../manifest/wifi5-candidate13-20260921.json)。

## 已定位的限制和未确认的原因

1. **旧跳板机服务端有接收处理瓶颈。** 原拓扑有线控制为 636 Mbps；RPS 调整后 642、IRQ 迁移后 649 Mbps，满载 softirq 随中断迁移到对应 CPU。换线后直连 LAN 仍约 617 Mbps。恢复中断/RPS设置后，改用 PC 得到 937/938 Mbps，排除了 PC 有线路径达不到 800 的问题。旧服务端下 C12 的 566 和 C13 的 595 Mbps 不能用来推断新拓扑的无线能力。
2. **没有观测到 RT3000 主 CPU 满载。** 有效采样中，738 Mbps 单流上传时两核分别约 34–39% 和 49–55%。这不能排除无线固件或 NSS 内部局部处理限制。
3. **PC 接收窗口过小没有获得证据支持。** 测试 13 抓包保存 779856 个报文，采集丢包为 0，接收窗口中位数约 2 MiB，无 window-full / zero-window 事件。Wireshark 标记了 78 次快速重传、89 次乱序和 115 个重复 ACK；这些是分析器判定，不等同于路由器丢包计数，也没有直接证明根因。
4. **无线接收错误仍存在。** 信道 44 两次上传前后，DP Overflow 增加 2199、FCS 增加 57981、BA duplicate 增加 7、Frame OOR 增加 1996。该区间包含两次测试和空闲流量，不能换算成手机专属丢包率。RXPCU FIFO 溢出不能直接等同于主机 RXDMA 描述符不足。
5. **不继续盲目扩大 ring。** 外置无线的完整 WIFILI 记录中分配失败、描述符不可用和交付丢弃计数为 0；HTT SRNG 空闲快照中远端 RX buffer ring 没有 consumer-empty。C13 扩容已应用，但未证明它是性能提升来源。
6. **未证明信道 44 更空闲。** 不同时刻十个 1 秒 CCA 样本的 OBSS 占用中位数为信道 36 约 11.17%、信道 44 约 18.13%。后续被动扫描返回 `Not supported (-95)`，未继续重试。没有信道 60 的性能结论。

已纠正并排除的无效证据：`nohup` 不存在造成的未运行采样、被工具截断的采样、包含空闲段的 CPU 总平均、测试 13 结束后才获取的所谓“前置”DP快照。完整 WIFILI 输出会对不同 SoC 重复显示 `wifili[0]`，不能用首段零值代表外置无线。`iw` 的 `authorized: no` 与 NSS 状态不一致时，已用 hostapd 的 `authorized: true` 和实际数据流验证关联。

## 候选变更、构建与复现边界

本次构建源提交为 `73c3b3d146c832106b75578a67f35002a881328c`，另含以下两个尚未提交的补丁，上传源码时需要显式纳入：

- [350-ath11k-add-rx-ampdu-aggr-debugfs.patch](../../package/kernel/mac80211/patches/all-ipq50xx/350-ath11k-add-rx-ampdu-aggr-debugfs.patch)：新增按 vdev 写入 RX A-MPDU 上限的诊断接口，未写入时不发 WMI 命令。C12 曾写 255，未取得决定性收益；C13 保持默认。写入成功不能证明实际协商窗口等于该值。
- [604-ath11k-qcn6122-rxdma-ring-2048.patch](../../package/kernel/mac80211/patches/all-ipq50xx/604-ath11k-qcn6122-rxdma-ring-2048.patch)：仅在 256M profile 的 QCN6122 软件目标上将 RXDMA ring 从 1024 增至 2048，主机分配与 NSS 使用相同 helper，WIFILI 软件描述符数量从 3072 增至 6144。仍是诊断性改动，不宣称它修复了上行瓶颈。

实际执行 `make -j8 V=s`，构建退出码为 0；已审计最终 FIT 内部 rootfs、模块、BDF、选中 DTB 及镜像校验，不仅检查 staging 文件。关键身份：

```text
FIT bytes   9786536
FIT SHA256  fe4a72af55b63bb90cbc03288ce1fce5629da933159a0603836d4655eef6c00d
BDF SHA256  085a6cca54714ed8387341869bbf1f75b257198e87bd590ddf58f7d155c772fb
ath11k SHA  3fbf31ae0b8f68cbeb6b0d17bf2207e8610677e7af2c5a26f7eb08ef6276a846
```

内外无线 DTB NSS priority 分别为 0 和 1。当前源码 BDF 与上述哈希一致，C11 的提交标题并不代表最终镜像使用 C11 BDF。基础 SDK 依赖见 [BASE-SDK.md](../BASE-SDK.md)；本记录保存现有构建身份，不宣称已经执行全新目录的可重复构建认证。

性能复测使用实际 PC 地址替换 `<server-ip>`，将 `<router-lan-ip>` 用于正常管理。先通过当前运行态确认 RAM root、BDF、模块参数和 HE160，再执行：

```sh
# 千兆有线 PC 上运行服务端
iperf3 -s -B <server-ip> -p 5201

# 手机单流上传；每轮保留服务端 receiver 汇总，至少重复两轮
iperf3 -c <server-ip> -p 5201 -t 10 -P 1

# 下载为独立对照，不能替代上传验收
iperf3 -c <server-ip> -p 5201 -t 10 -P 1 -R
```

继续工作时应先复核实际拓扑和运行镜像；本次跳板机端口配置为临时 NetworkManager profile，RAM 系统和地址也不应当作持久配置。Windows PC 的 iperf3 服务及已授权的局域网 TCP 5201 防火墙规则保留。最终吞吐路径为 LAN bridge，本记录不证明 WAN/NAT、2.4 GHz、长期稳定性或正式闪存发布已全部验收。

## 发布范围

本文件、CSV、脱敏日志、manifest 和上述源码补丁可作为本轮 GitHub 变更审阅材料。原始 pcap、完整串口/SSH日志、设备密钥、通知凭据和本地工具目录留在本地证据库；公开 manifest 记录关键原始证据的哈希。没有自动执行 Git 提交、推送、PR 或固件发布。

状态是 **用户暂停优化 / 保存诊断成果 / 性能目标未通过**，不是宣布硬件已经达到绝对上限，也不是可直接刷入的正式发布版本。
