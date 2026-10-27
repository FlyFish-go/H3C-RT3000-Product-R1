# r7 — WAN PHY 链路与速率跟踪修复

本版修复 HW-A、HW-B、HW-D 的 WAN 设备树缺少 `qcom,link-poll` 的问题。HW-C 已启用该属性，本次不改变其 WAN 节点。

## 修复内容

WAN 节点已有 MDIO 总线和 PHY 地址，但缺少 PHY 轮询开关。QSDK NSS-DP 驱动因此不连接 PHY，而在接口启动时直接报告 carrier up；PHY 的链路和速率变化也无法沿该路径通知 SSDK。现场表现为百兆链路已建立但接收包为零、DHCP 无法取得地址，千兆连接则可以接收数据。

本版在 A/B/D 的 WAN 节点添加 `qcom,link-poll = <1>;`，不改变 PHY 接口模式、MDIO 地址、MAC 派生、无线、分区表、系统槽选择或升级写入范围。增加设备树回归检查并纳入离线 CI。

## 验证范围

- HW-B 的单独修复构建已完成百兆/千兆故障对照，用户在升级后报告恢复有效。这是本次修复的现场依据。
- 此前的校园定制镜像不是本次公开 Release 附件；公开固件使用常规 `configs/h3c-magic.config`，不包含校园认证、防护或用户配置。
- r6 的四板验收与吞吐记录仅属于 r6，不能视为 r7 的硬件验收。新 Release 附件的离线构建、DTB 和镜像检查结果由随包构建清单记录；A/C/D 的本轮硬件回归、10 Mbps、长稳和各 NAND 批次仍待验证。
- 保留配置升级仍建议先导出备份。本轮现场的配置保留完整性未取得独立验收证据。

## 安装

按硬件系列选择 `H3C-Magic-r7-HW-A/B/C/D-*`，不要只按机身商品型号选择。`nand-factory.ubi` 用于匹配硬件的 U-Boot 救援安装；`sysupgrade.bin` 用于已有匹配系统的正常升级。使用稳定电源，升级前备份。安装前核对随包 SHA256SUMS。

## English summary

Enable WAN PHY link polling on HW-A/B/D; HW-C already has it. This allows NSS-DP to attach the PHY and propagate negotiated link/speed changes instead of treating the WAN as permanently up. The observed HW-B failure was zero receive traffic on a 100 Mbps link while a 1 Gbps PC link received normally. A separate HW-B fix build received positive user feedback; this does not establish hardware acceptance for all new public release images. Partition layout, slot selection, PHY mode and radio settings are unchanged by this fix. No campus packages or private configuration are included.
