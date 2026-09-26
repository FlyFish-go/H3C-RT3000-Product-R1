# 三台同名 H3C Magic RT3000，三套不同硬件

## H3C IPQ50xx AX3000 家族硬件变体调查

> **Hardware Research v1.0**  
> 更新日期：2026-09-26

> **研究状态：Hardware Research v1.0 audited baseline**  
> 本文以项目已审计的 Canonical Fact Base 为事实入口。内部 A / B / C 是本项目对三台实体 RT3000 的样机编号，**不是 H3C 官方硬件版本号**。  
> 本文讨论的是硬件识别、适配边界与公开证据，不把任何一台样机的验证结果自动推广到同名设备，也不提供未经验证的通刷结论。

## 目录

1. 从“一台 RT3000”到“三套硬件”
2. 三台 P0 实体样机：A / B / C
3. 为什么 `RT3000 + VER.A` 仍不足以识别硬件
4. Marketing / OEM identity 与 Hardware identity：两个维度
5. QCA8337 与 RTL8367S：两条以太网路线
6. NAND：GigaDevice / Winbond / ESMT，以及 `128+8 / 128+4` 到底说明什么
7. RF / FEM / BDF：同为 QCN6102，不等于射频配置相同
8. Boot / Partition / 双系统：为什么不能把 B 的 `mtd15/mtd16` 直接套给所有机器
9. 外部样本：NX30 / RC3000 / RW3010 / RW3000
10. Evidence / Validation：为什么“能启动”不等于“支持”
11. 对 Product R1、硬件识别工具和 OpenWrt mainline 的影响
12. 证据等级、引用规则与样本征集
13. 结论

---

# 1. 从“一台 RT3000”到“三套硬件”

这个调查最初并不是为了给 H3C Magic RT3000 做一份“全网硬件大全”。

项目一开始面对的是一个更直接的问题：**同样写着 `H3C Magic RT3000` 的机器，能不能按同一套硬件假设去做 QSDK / OpenWrt 适配？**

随着三台实体 RT3000 被拆机、拍照、启动和验证，答案逐渐变成了明确的 **不能**。

本项目内部将这三台实体样机记为 A、B、C。它们不是 H3C 官方版本号，只是为了让每一条测试记录都绑定到具体物理设备。三台机器在商品身份上都属于 RT3000，但已经确认存在明显不同的硬件组合：

| 项目 | A | B | C |
|---|---|---|---|
| SoC | IPQ5018 | **IPQ5000** | IPQ5018 |
| RAM | 独立 Winbond | **Integrated 256 MiB DDR3L** | 独立 GigaDevice |
| NAND | Winbond W25N01GWZEIG | GigaDevice GD5F1GQ5REYIG | Winbond W25N01GWZEIG |
| Ethernet Switch | **QCA8337-AL3C** | **QCA8337-AL3C** | **RTL8367S** |
| 5 GHz Radio | QCN6102 | QCN6102 | QCN6102（历史硬件记录） |
| 外置 5 GHz FEM | **未装配（NX30 对应 FEM 位置为空）** | 正反面照片未见独立 FEM | **2 × 8539SD（KCT8539SD 型号族）** |
| PCB 可读标识 | `H3C AX3000-D VER.A` | `H3C AX3000 REV:A0` | `AX3000`，revision UNKNOWN |

这里最值得注意的并不是“某颗芯片换了料”。

A / B / C 同时出现了 **SoC、RAM topology、NAND、交换机、PCB 标识和 RF 前端装配**上的差异。A 的 PCB 在 NX30 对应两颗外置 5 GHz FEM 的位置为空，和 C 已实际装配两颗 8539SD 的状态形成了直接对照。也就是说，至少在当前三台实体样本上，`RT3000` 这个商品名并不能唯一确定一套 PCB / BOM。

这也是本文后续所有讨论的起点：

> **商品型号可以作为线索，但不能直接充当硬件身份。**

因此，本项目后续不再把“RT3000 / RC3000 / RW3000 / RW3010 / NX30”直接当成固件适配单元，而是分别记录实际 SoC / RAM、交换机、NAND、PCB、RF / FEM、分区与启动状态，再决定某一台实体设备属于哪个已经验证的硬件 Profile。

这个结论同样有一个重要边界：**三台 RT3000 已经足以证明“同名设备并非唯一 BOM”，但不足以恢复 H3C 的完整生产批次规则，也不足以说明市面上只存在 A / B / C 这三种组合。**

---

# 2. 三台 P0 实体样机：A / B / C

这里的 **P0** 指本项目自己持有、拆解、拍照或实际运行过的实体样机证据。A / B / C 只是项目内部编号，用来把照片、日志、固件和测试结果绑定到具体机器；它们不对应 H3C 官方所谓的 A/B/C 硬件版本。

这一节只讨论三台 RT3000 本身。外部 RC3000、RW3010、NX30 等公开样本留到后文单独处理，避免把不同来源的器件信息拼成一台现实中并不存在的“合成机器”。

## 2.1 A：IPQ5018 + 独立 RAM + QCA8337-AL3C

A 是三台样机中较早进入项目的一台。其 PCB 可读标识为：

```text
H3C AX3000-D VER.A
```

当前确认的主要硬件为：

- SoC：**Qualcomm IPQ5018**；
- RAM：独立 **Winbond W632GU6NB**；
- NAND：**Winbond W25N01GWZEIG**；
- Ethernet Switch：**QCA8337-AL3C**；
- 5 GHz Radio：**QCN6102**；
- 外置 5 GHz FEM：**未装配**，与 NX30 两颗 FEM 对应位置相比，该区域为空；
- UART：PCB 丝印可见 `3V3 / RX / TX / GND`，以 PCB 文字正常阅读方向为基准，四个焊盘从左到右排列。

A 的一个重要意义，是它证明了 RT3000 并不天然等同于 B 后来形成的 `IPQ5000 + integrated DDR` 路线。A 明确采用 **IPQ5018 + 独立 DDR**，并且在 PCB 与 NAND 上也与 B 不同。

A 目前已经损坏且不在手边，因此不能再进行新的运行态采集。与 A 有关的新增结论必须来自既有照片、历史日志和已经保存的项目记录；不会为了“补齐表格”而从 B/C 或外部样本反推 A 的未知字段。

> **图位建议 A-1：A 机 PCB 正反面全景。**  
> **图位建议 A-2：IPQ5018 / Winbond RAM / W25N01GWZEIG 近照。**  
> **图位建议 A-3：与 NX30 的 5 GHz FEM 装配区域对照，标出 A 的空焊位置。**

## 2.2 B：IPQ5000 + Integrated DDR + QCA8337-AL3C

B 是目前 **Product R1 r5** 的发布与实机验收基线，也是三台机器中最容易被旧资料误判的一台。

B 的 PCB 可读标识为：

```text
H3C AX3000 REV:A0
```

实体芯片顶标与照片确认：

- SoC：**Qualcomm IPQ5000**；
- RAM：**Integrated 256 MiB DDR3L**，板上不存在 A/C 那样的独立 DDR 芯片；
- NAND：**GigaDevice GD5F1GQ5REYIG**；
- Ethernet Switch：**QCA8337-AL3C**；
- 5 GHz Radio：**QCN6102**；
- 外置 5 GHz FEM：正反面照片均未见独立 FEM 装配，当前判断为**未装配独立外置 FEM**；
- UART：以整机 **H3C Logo 正向**为观察基准，四个焊盘从上到下为 `3V3 / RX / TX / GND`。附近 PCB 字符相对这一观察方向是旋转/倒置的，因此公开接线图必须同时给出观察基准。

B 最值得强调的是 **IPQ5000**。早期项目资料曾把 A/B/C 一并记为 IPQ5018，但 B 的实体顶标已经推翻了这一旧结论。软件中的 `ipq5018` 平台字符串、DTS 名称或兼容路径不能覆盖芯片本体的物理丝印。

B 也是当前最成熟的一台：Product R1 r5 的安装、NAND 启动、OEM/QSDK 双系统切换、升级与基本双频网络验证，都绑定在**这台实体 B 和对应镜像**上。它们不能因为另一台机器也叫 RT3000 就自动继承过去。

> **图位建议 B-1：B 机 PCB 正反面全景 + `H3C AX3000 REV:A0`。**  
> **图位建议 B-2：IPQ5000 顶标。**  
> **图位建议 B-3：QCA8337-AL3C / QCN6102 / GD5F1GQ5REYIG 近照。**  
> **图位建议 B-4：UART 焊盘，附“H3C Logo 正向”箭头。**

## 2.3 C：IPQ5018 + RTL8367S + 两颗 5 GHz FEM

C 是目前差异最明显、也是正在继续适配的一台。

其 PCB 能稳定读到：

```text
AX3000
```

但当前原始照片不足以确认完整的 `REV/VER` 后缀，因此这里不把它补成某个不存在证据的完整 PCB 版本号。

当前确认的主要硬件为：

- SoC：**Qualcomm IPQ5018**；
- RAM：独立 **GigaDevice DDR**；
- NAND：**Winbond W25N01GWZEIG**；
- Ethernet Switch：**Realtek RTL8367S**；
- 5 GHz Radio：**QCN6102**（历史硬件记录）；
- 外置 5 GHz FEM：**两颗 `8539SD`，归入 KCT8539SD 型号族**，位于 U32/U33；
- UART：对应位置没有功能丝印，但以 PCB 文字正常阅读方向为基准，从左到右 `3V3 / RX / TX / GND`，这一 Pinout 已由项目实际串口通信验证。

C 的意义不只是“交换机从 Qualcomm 换成了 Realtek”。它同时重新引入了 **IPQ5018 + 独立 RAM**，但 RAM 厂商、交换机、RF 前端装配又都和 A 不同。因此即使 A/C 在部分布局和 SoC 层面更接近，也不能据此假定两者拥有相同的网络、RF 或 BDF 配置。

在当前私有适配中，C 已经完成 RTL8367S 有线网络、LAN 软件桥、自动 LAN/WAN、NAT/DHCP/DNS，以及 2.4 GHz 和阶段性的 5 GHz RAM 启动测试；但 C 仍没有完成持久化安装与完整长期稳定性验收，因此本文不会把它写成已经发布支持的硬件版本。

> **图位建议 C-1：C 机 PCB 正反面全景。**  
> **图位建议 C-2：RTL8367S 近照。**  
> **图位建议 C-3：U32/U33 两颗 `8539SD` 近照。**  
> **图位建议 C-4：与 A/NX30 的 FEM 区域三图对照。**

## 2.4 三台样机告诉我们的第一件事

如果只看包装或 Web 管理页，这三台机器都叫 **H3C Magic RT3000**。

如果拆到 PCB 层面，则至少可以看到两条非常不同的主路径：

```text
A: IPQ5018 + discrete DDR + QCA8337-AL3C + Winbond NAND + no external 5G FEM
B: IPQ5000 + integrated DDR + QCA8337-AL3C + GigaDevice NAND + no external 5G FEM
C: IPQ5018 + discrete DDR + RTL8367S + Winbond NAND + 2×8539SD 5G FEM
```

这也是为什么本文后续统一把“商品型号”和“硬件身份”分开处理：**真正决定适配边界的不是外壳上的 RT3000，而是板上的实际器件组合。**

需要再次强调的是，A/B/C 只是三台已掌握的实体样本，而不是 H3C 官方划分的三个 revision。它们证明的是“RT3000 不是唯一 BOM”，并不证明“市场上一共只有这三种 RT3000”。

---


# 3. 为什么 `RT3000 + VER.A` 仍不足以识别硬件

如果只看 PCB，A / B / C 已经足以说明 `RT3000` 不是唯一 BOM。原厂 Web 管理页又提供了另一条非常直观的证据：**即使产品型号、网页“硬件版本”和 Bootrom 版本都相同，也仍然不能唯一确定实际硬件或 OEM 软件分支。**

本项目保存了 B、C 两台实体 RT3000 在原厂系统下的管理页截图。两台机器都显示：

```text
产品型号：H3C Magic RT3000
硬件版本：VER.A
Bootrom版本：100
```

但其 OEM 软件版本并不相同：

| 字段 | B | C |
|---|---|---|
| 产品型号 | H3C Magic RT3000 | H3C Magic RT3000 |
| Web 硬件版本 | `VER.A` | `VER.A` |
| Bootrom | `100` | `100` |
| OEM 软件版本 | `RT3000V100R005` | `RT3000V100R007` |
| 当时在线升级状态 | 该机已是最新版本 | 该机已是最新版本 |
| 实际 SoC | IPQ5000 | IPQ5018 |
| Ethernet Switch | QCA8337-AL3C | RTL8367S |
| NAND | GD5F1GQ5REYIG | W25N01GWZEIG |
| 外置 5 GHz FEM | 未见独立装配 | 2 × 8539SD |

> **图位建议 3-1：B 原厂后台截图。** 发布版遮盖完整序列号，只保留产品型号、软件版本、Bootrom 与硬件版本。  
> **图位建议 3-2：C 原厂后台截图。** 同样遮盖完整序列号。  
> **图位建议 3-3：B/C 两张截图裁剪后的并排对照。**

这组证据有两个非常重要的含义。

## 3.1 `VER.A` 不是一个足够细的硬件识别键

从 Web 页面看，B 和 C 都是：

```text
RT3000 / VER.A / Bootrom 100
```

但拆机后，两者至少在 **SoC、RAM topology、NAND、Ethernet Switch 和 RF 前端装配**上明显不同。

因此，原厂 Web 页面里的 `VER.A` 至少在这两台实体样本上，**不足以唯一对应某一套 PCB / BOM**。

这并不意味着 `VER.A` 与硬件完全没有关系，也不意味着它只是一个随意的软件字符串。本文能够确认的边界只有：

> **不能把 Web `硬件版本 = VER.A` 当成“这台机器一定属于某个固定硬件 Profile”的充分条件。**

这点对刷机和自动识别尤其重要。如果工具只依据：

```text
产品型号 = RT3000
硬件版本 = VER.A
```

就直接选择固件，那么 B 与 C 会被错误地归为同一类，而它们实际上分别走 QCA8337 与 RTL8367S 两条不同的以太网路线。

## 3.2 “最新固件”也不是整个 RT3000 型号唯一的一条版本线

B 当时运行：

```text
RT3000V100R005
```

C 当时运行：

```text
RT3000V100R007
```

两台机器在各自原厂升级路径中都显示已经处于最新版本。

这说明至少在这两个样本上，不能建立如下简单模型：

```text
只要都是 RT3000 + VER.A
        ↓
就应该拥有同一个唯一“最新 OEM 版本”
```

但这里必须守住一个边界：**现有两台样本还不足以证明 `R005 = B 硬件`、`R007 = C 硬件` 是固定映射。**

OEM 升级路径究竟依据什么进行分流，目前仍然未知。可能相关的设备身份维度包括产品配置字段、序列/渠道信息、board/machid、OEM branch 或其他内部识别字段；本文目前没有足够证据确定具体机制。

因此，本文只保留经过实体样本直接支持的结论：

> **相同的 `H3C Magic RT3000 + VER.A + Bootrom 100`，可以对应不同的 OEM 最新软件版本，也可以对应明显不同的实际硬件。**

## 3.3 Web “硬件版本”、PCB 丝印和项目样机编号是三套不同概念

这个项目里很容易出现三个都带“A”的东西：

```text
项目内部样机 A
Web 页面硬件版本 VER.A
PCB 丝印中的 VER.A / REV:A0
```

它们不能混为一谈。

例如：

- 项目内部 **A 样机**的 PCB 是 `H3C AX3000-D VER.A`；
- **B 样机**的 PCB 是 `H3C AX3000 REV:A0`，但 Web 页面仍显示 `硬件版本：VER.A`；
- **C 样机**的 PCB 当前只能可靠读到 `AX3000`，完整 revision 未确认，但 Web 页面同样显示 `硬件版本：VER.A`。

所以本文后续采用以下纪律：

```text
Project Sample ID   → A / B / C，仅用于绑定本项目实体证据
Web Hardware Ver.   → 原厂管理页暴露的版本字段
PCB Marking         → PCB 上实际可读的 REV / VER / board string
Hardware Profile    → SoC / RAM / Switch / NAND / RF / Boot 等实际组合
```

任何一层都不能在缺少证据时自动替代另一层。

这也是为什么后续的硬件识别工具不会只问一句“你是不是 RT3000 VER.A”，而必须继续读取更底层的硬件信息。

---


# 4. Marketing / OEM identity 与 Hardware identity：两个维度

到这里已经能看出一个核心问题：如果把 `RT3000 / RC3000 / RW3000 / RW3010 / NX30` 直接当成“硬件型号”，很多现象会互相冲突；但如果把**产品 / OEM 身份**和**实际硬件身份**拆成两个维度记录，这些现象就能同时成立。

本文采用的不是“H3C 生产流程已经被还原”这一结论，而是一套用于识别和适配的工作模型：

```text
┌──────────────────────────────────────┐
│ Axis A：Marketing / OEM identity     │
│                                      │
│ RT3000 / RC3000 / RW3000 / RW3010   │
│ NX30                                 │
│ 运营商 / 渠道                        │
│ Web Hardware Version                 │
│ OEM software branch                  │
│ productname / productconfig          │
└───────────────────┬──────────────────┘
                    │
                    │  不是一一对应
                    │
┌───────────────────▼──────────────────┐
│ Axis B：Actual hardware identity     │
│                                      │
│ PCB                                  │
│ SoC / RAM                            │
│ Ethernet Switch                      │
│ NAND + physical geometry             │
│ Partition / Boot                     │
│ QCN6102 / RF / FEM                   │
│ ART / calibration / BDF              │
└──────────────────────────────────────┘
```

这里的关键不是“两个轴完全独立”，而是：

> **现有证据已经足以否定“一个商品型号唯一对应一套 PCB / BOM”这个简单模型，因此在适配时必须把产品身份与硬件身份分别记录。**

## 4.1 同一个 Marketing Model，可以对应不同硬件

最强的证据就是本项目自己的三台 RT3000。

三台机器在商品身份上都属于 `H3C Magic RT3000`，但实际硬件已经确认至少存在：

```text
A → IPQ5018 + discrete DDR + QCA8337-AL3C + Winbond NAND
B → IPQ5000 + integrated DDR + QCA8337-AL3C + GigaDevice NAND
C → IPQ5018 + discrete DDR + RTL8367S + Winbond NAND + 2×8539SD FEM
```

因此，`RT3000` 这个名字本身不能告诉我们：

- SoC 一定是 IPQ5000 还是 IPQ5018；
- Ethernet Switch 一定是 QCA8337 还是 RTL8367S；
- NAND 一定来自 GigaDevice、Winbond 还是其他批次；
- 5 GHz 路径是否装有独立 FEM；
- 甚至不能由 Web `VER.A` 唯一确定硬件 Profile。

外部社区资料又说明，这种现象不只出现在本项目的三台样机里。公开记录中，RT3000 还出现过 ESMT NAND、RTL8367S 等额外组件 / 配置线索；RC3000 也同时存在 QCA8337 样本与一台明确报告为 `IPQ5018 + RTL8367S + Winbond NAND + KCT8539SD` 的 R009 样本。

这些外部记录只能证明“存在这些样本”，不能直接统计完整硬件组数量，也不能把不同帖子里的单一元件拼成一个新的完整 BOM。但它们与 A/B/C 的 P0 证据方向一致：**Marketing Model 不是可靠的 BOM ID。**

## 4.2 不同 Marketing Model，也可能出现高度接近的硬件组合

反过来，产品名不同也不等于底层硬件一定不同。

目前最值得关注的一组对照，是内部 B 与公开 RW3010 样本。

在已经能够从照片确认的字段上，两者都出现：

| 字段 | 内部 B | 外部 RW3010 样本 |
|---|---|---|
| PCB | `H3C AX3000 REV:A0` | `H3C AX3000 REV:A0` |
| SoC | IPQ5000 | IPQ5000 |
| Ethernet Switch | QCA8337-AL3C | QCA8337（照片可确认基础型号） |
| 5 GHz Radio | QCN6102 | QCN6102 |
| NAND | GigaDevice GD5F1GQ5REYIG | GigaDevice 5F1GQ5REYIG |
| 外置 FEM | B 正反面未见独立 FEM | 外部照片未见独立 FEM |

这使 RW3010 成为一个很强的 **B-like / high-similarity candidate**。

但这里仍然不能写成：

```text
B = RW3010
```

因为我们还没有 RW3010 这台样本的：

- `/proc/mtd` / UBI 布局；
- boot selector / U-Boot 环境；
- ART / calibration；
- BDF；
- GPIO / LED / key；
- 真实运行与升级验收。

因此，“主要器件高度接近”只意味着它**值得优先研究代码与配置复用**，不意味着它已经继承 B 的 Product R1 r5 支持状态。

> **图位建议 4-1：B 与 RW3010 的 `AX3000 REV:A0`、IPQ5000、QCA8337、QCN6102、GigaDevice NAND 对照。**

## 4.3 软件可见的产品身份确实具有一定可修改性

社区跨刷资料还提供了另一类证据：部分 H3C OEM 产品身份字段可以通过 U-Boot / Linux 环境进行修改。

早在 2022 年的 RC3000 / RT3000 / RW3000 → NX30 社区记录中，就已经出现过：

```text
productname
productconfig
```

这类字段的修改；2026 年另一篇 OEM 迁移记录中又出现了相同思路。

这说明至少有一部分**软件可见产品身份**并不是焊死在某颗芯片里的不可变属性，它们会参与 OEM 配置和升级路径。

但这类证据只能支持：

> **部分产品 / OEM identity 字段可以被软件修改。**

它不能支持：

> “产品身份完全由软件决定。”

更不能支持：

> “既然能把 `productname` 改成 NX30，那硬件就等于 NX30。”

事实上，早期社区教程自己就已经提醒先核对硬件；后来的迁移记录同样把“硬件相同 / 分区布局吻合”当成作者自己的前提条件，而不是通过改 `productname` 自动获得的能力。

换句话说：

```text
修改 software-visible identity
        ≠
改变 SoC / Switch / NAND / RF / calibration
```

这也是为什么“跨刷成功”只能说明某个具体样本在某个具体条件下达到了某些运行状态，不能反推所有同名或异名设备硬件一致。

## 4.4 我们不从这个模型推出什么

为了避免把一个好用的识别模型写成制造流程故事，本文明确不做下面这些断言：

- 不写“RT / RC / RW 只是同一块板随机刷不同运营商系统”；
- 不写“产品身份与硬件身份完全解耦”；
- 不写“H3C 先生产一块通用板，再靠软件决定最终型号”；
- 不写“两个不同产品只要主芯片一样就能互刷”；
- 不写“同一产品的 R005 / R007 就分别固定对应某一个硬件组”。

现有证据能支持的是更克制、但对工程更有用的一句话：

> **Marketing / OEM identity 与实际 PCB / BOM 不是一一对应关系；因此设备识别、固件选择和支持声明必须建立在实际硬件 Profile 上，而不能只依赖商品名或 Web 版本字段。**

## 4.5 这套双轴模型如何进入后续适配

因此，本项目不再把一个“机型字符串”直接映射到固件，而是把每台设备拆成至少九个独立 Profile 维度：

```text
1. SoC / RAM
2. PCB
3. Ethernet Switch
4. NAND + physical geometry
5. Partition / Boot
6. 5 GHz radio
7. RF / FEM
8. ART / calibration / BDF
9. Software / OEM identity
```

一个新的 RT3000 / RC3000 / RW3000 / RW3010 样本进入项目时，首先回答的是：

> **“它实际是什么硬件？”**

而不是：

> **“它外壳上写什么型号？”**

只有当这些字段与某个已验证 Profile 的差异已经清楚，才讨论代码复用、RAM 启动、持久化安装和最终支持状态。

这套模型也直接决定了未来硬件识别工具的方向：工具需要读取真实 SoC、NAND、Switch、分区 / boot state 和射频 Profile，而不能只根据 `RT3000 / VER.A` 直接选择镜像。

---


# 5. QCA8337 与 RTL8367S：两条以太网路线

如果说前四节回答的是“为什么商品型号不能直接当硬件身份”，那么 Ethernet Switch 是目前最能把这一问题落到实际适配上的字段之一。

在本项目三台 P0 RT3000 样机中，A / B 使用 **Qualcomm Atheros QCA8337-AL3C**，C 使用 **Realtek RTL8367S**。这不是一个可以忽略的小料号差异：交换机芯片直接影响 CPU-facing link、端口初始化、VLAN / bridge 组织、驱动路径，以及后续 mainline 设备树和网络拓扑的表达方式。

因此，本文把它们称为两条 **Ethernet adaptation route**：

```text
QCA8337 route
  ├─ RT3000 A   [P0 hardware]
  └─ RT3000 B   [P0 hardware + Product R1 r5 validated baseline]

RTL8367S route
  └─ RT3000 C   [P0 hardware + RAM-stage wired validation]
```

这里的“route”不是在宣布整个 H3C 家族只存在两种网络设计，也不是说只要交换机相同就属于同一块板。它只表示：**在当前已经掌握的实体样本里，QCA8337 与 RTL8367S 已经构成两条需要分别验证的 Ethernet 适配路径。**

## 5.1 QCA8337-AL3C：A / B 的 Qualcomm Switch 路线

A 和 B 都已经确认使用 **QCA8337-AL3C**。

其中 B 是目前最成熟的参考样本：Product R1 r5 的 QSDK / NSS、NAND 启动、双系统切换和基本 LAN/WAN 功能，都绑定在 B 这台 `IPQ5000 + QCA8337-AL3C` 实体设备上。

A 同样采用 QCA8337-AL3C，但它并不因此等于 B。A/B 至少还存在：

- IPQ5018 vs IPQ5000；
- 独立 DDR vs integrated DDR；
- Winbond NAND vs GigaDevice NAND；
- 不同 PCB 标识；
- 不同 RF 装配线索。

因此，QCA8337-AL3C 只能说明两台机器在 Ethernet Switch 这一维度属于同一路线，不能让 A 自动继承 B 的整机适配结论。

这也是本文后续会反复强调的一个原则：

> **Switch identity 是重要的 Profile 维度，但不是完整 board identity。**

对未来工具来说，检测到 `QCA8337` 只意味着“进入 QCA route 的候选范围”，后续仍需要继续核对 SoC、NAND、partition、RF / BDF 和 boot state。

> **图位建议 5-1：A / B 的 QCA8337-AL3C 对照。** 公开版只在能够清楚确认完整料号的图片上标 `QCA8337-AL3C`；软件 / 驱动讨论中可简称 `QCA8337`。

## 5.2 RTL8367S：C 把同名 RT3000 拉到了另一条路线

C 的 Ethernet Switch 已由近照确认是 **Realtek RTL8367S**。

这件事之所以重要，是因为它直接否定了一个在早期资料中很容易形成的默认假设：

```text
RT3000
   ↓
一定是 QCA8337
```

至少对本项目 C 样机，这个假设是错误的。

C 当前的 RAM-stage 适配已经验证过：

- RTL8367S 路线下三口数据通信；
- LAN 软件桥；
- 自动 LAN/WAN；
- 客户端 DHCP；
- DNS / NAT / Internet 出口；
- 短时断开 / 重连与基础网络恢复。

这些结果说明 RTL8367S 并不是“这台机器不能做 OpenWrt / QSDK”的同义词；真正的问题是目标固件必须对这条板级网络路径有对应支持。

但 C 当前仍处于 **RAM-stage / PARTIAL**：持久化安装、完整长稳、全部 reboot / recovery 路径还没有完成，所以本文不会把“C 的 RTL 路线已经打通”写成完整发布支持。

> **图位建议 5-2：C 的 RTL8367S 近照。**

## 5.3 RTL8367S 并不是 C 的孤立现象

公开资料中还存在至少两类 RTL8367S 线索：

1. 社区存在 RT3000 RTL8367S 样本 / 刷目标固件失败记录；
2. 一台明确自述为 **中国电信 RC3000 / R009** 的公开样本报告了：

```text
SoC:       IPQ5018
Switch:    RTL8367S
5 GHz:     QCN6102
5 GHz FEM: KCT8539SD
RAM:       W632GU6NB-11
NAND:      W25N01GW
```

该 RC3000 R009 用户随后报告强制刷 NX30 后设备失效，并在后续确认没有正常 TTL 输出。

这类公开记录的价值在于：它们说明 **RTL8367S 不是只出现在本项目 C 这一台 RT3000 上的偶然孤例**，而且已经跨 `RT3000 / RC3000` 两个 Marketing Model 出现。

因此，本项目保留一个识别层面的工作模型：

> **RTL8367S 是值得单独识别和研究的一条 hardware-family candidate。**

但这个工作模型明确**不证明**：

- C 与 RC3000 R009 是同一 PCB；
- CPU-facing interface 完全相同；
- GPIO / reset 连接相同；
- partition / boot layout 相同；
- BDF / calibration 相同；
- 固件可以直接互刷。

换句话说，“都用了 RTL8367S”足以告诉我们**不要把它们塞进 QCA8337 的目标固件假设里**，但远远不足以告诉我们“它们就是同一块板”。

## 5.4 “RTL 刷后失败”目前能说明什么，不能说明什么

社区里已经出现多条带有类似“RTL8367S 版本刷某目标固件失败 / 变砖”的记录。一些回复者将原因归因于目标固件缺少 RTL8367S 支持。

这种解释在工程上是合理的候选原因，但目前仍属于 **community attribution**，不是本项目已经独立确认的 root cause。

原因在于多数社区记录只能直接观察到：

```text
刷入某镜像
    ↓
设备未达到预期运行状态 / 失去正常启动能力
```

而不能完整回答：

```text
Bootloader 是否正常？
Kernel 是否已经启动？
RTL8367S 初始化在哪一步失败？
CPU-facing link 是否建立？
只是 LAN 不工作，还是系统更早就失败？
是否同时存在 NAND / partition / header / boot-selector 不匹配？
```

因此本文不会写：

> “RTL8367S 机器必砖，因为目标固件没有驱动。”

更准确的表述是：

> **RTL8367S 样本已经存在明确的目标固件失败记录；其中有社区回复将原因归因于缺少 RTL8367S 支持，但具体失败层次和 root cause 需要绑定具体样本与日志确认。**

这也是为什么后文在讨论“跨刷成功 / 失败”时，不会把一个“砖了”的结果自动填成 LAN、WAN、Wi-Fi、DHCP 等所有 capability 都 FAIL。

## 5.5 为什么未来识别工具必须先看 Switch，而不是只看型号

假设未来工具只做下面的判断：

```text
if model == "RT3000":
    flash(rt3000_image)
```

那么 A/B/C 这种样本差异会立刻让这种设计失效。

更合理的流程至少应该是：

```text
Marketing model
      ↓
只作为候选范围
      ↓
probe SoC
probe NAND
probe Ethernet Switch
probe partition / boot state
probe RF / BDF profile
      ↓
match validated hardware profile
      ↓
ALLOW / EXPERIMENTAL / UNKNOWN
```

其中 Ethernet Switch 是一个非常有区分力的字段：

```text
QCA8337-AL3C → QCA route candidate
RTL8367S     → RTL route candidate
```

但它仍然只是**一个字段**，不是完整的固件选择器。

这套逻辑也解释了为什么未来的 `h3c-probe` / toolbox 更适合做“先识别，再选择已验证方案”，而不是维护一个简单的“型号 → 固件”对照表。

## 5.6 对 OpenWrt mainline 的意义

对 mainline 来说，这个差异同样不能只靠产品字符串解决。

B 已经提供了一条成熟的 QCA8337 样本路径；C 则表明同名 RT3000 至少还存在 RTL8367S 网络架构。未来 upstream 设计需要把真正的 board-level 网络拓扑表达清楚，而不能假定：

```text
compatible = "h3c,rt3000"
```

就天然代表唯一一种 Switch / port topology。

这并不意味着现在就已经决定 mainline 最终应该拆成几个 `compatible`、几个 device target，或采用怎样的自动检测机制。那些设计应等到 B 的 upstream 支持与 C 的 RTL 路线都进入可审查状态后，再根据实际 DTS / driver / boot layout 决定。

当前能够确定的是：

> **QCA8337 与 RTL8367S 的差异已经足以进入 upstream 设计约束，而不能在提交设备支持时被当成“同型号的小批次换料”而忽略。**

---


# 6. NAND：GigaDevice / Winbond / ESMT，以及 `128+8 / 128+4` 到底说明什么

在这批设备的资料里，NAND 是最容易被“一个数字”带偏的字段之一。

社区恢复帖里经常能看到：

```text
128+8
128+4
132 MB
136 MB
GD 版
ESMT 版
```

这些说法如果不拆开，很容易被理解成：

> “不同 NAND = 不同分区表。”

但当前证据并不支持这么简单的等式。

本项目现在把 NAND 相关信息至少拆成五层：

```text
1. exact NAND part
2. physical geometry：capacity / page / OOB / ECC
3. MTD partition layout
4. UBI layout：PEB / LEB / volume
5. programmer raw dump size：data + OOB
```

这五层彼此有关，但不是同一个概念。

## 6.1 三台 P0 RT3000 已经出现两种 NAND 路线

三台实体样机中：

| 样机 | NAND | 容量 | 历史运行记录中的 page / OOB |
|---|---|---:|---|
| **A** | Winbond `W25N01GWZEIG` | 128 MiB | 2048 B / **64 B OOB** |
| **B** | GigaDevice `GD5F1GQ5REYIG` | 128 MiB | 2048 B / **128 B OOB** |
| **C** | Winbond `W25N01GWZEIG` | 128 MiB | 2048 B / **64 B OOB** |

这里要区分证据类型：A / B / C 的 NAND **料号**来自实物照片或顶标确认；page / OOB 数值属于本项目的 **historical runtime evidence**，不是从照片上直接读出来的。

公开资料还出现了第三种值得单独记录的器件：

- ESMT `F50D1G41LB`

它已经在 RT3000 / RC3000 的社区样本中出现；但这不意味着“ESMT = 第四硬件组”，也不意味着它天然绑定某一种 SoC、Switch 或 PCB。

因此，NAND 应继续作为一个**独立 Profile 维度**记录，而不是直接拿 NAND 厂牌替代整机硬件身份。

## 6.2 三种已确认器件都属于 1.8 V-class SPI NAND

本轮研究进一步核对了三家厂商官方器件资料：

| 料号 | 厂商 | 官方电压范围 | Page / Spare 信息 | 封装 |
|---|---|---|---|---|
| `W25N01GWZEIG` | Winbond | **1.7–1.95 V** | 2048 B + **64 B spare** | SON-8 |
| `GD5F1GQ5RE` family | GigaDevice | **1.7–2.0 V** | 2 KB；官方产品页未列 spare | WSON8 8×6 mm |
| `F50D1G41LB` | ESMT | **1.8 V（1.7–1.95 V）** | **2K + 64** | 8-contact WSON 8×6 mm |

因此，对目前已经确认出现在这套研究里的三种 SPI-NAND，可以得到一个很实际的安全结论：

> **它们都是 1.8 V-class 器件，不能因为“都是 SPI NAND / WSON8”就直接使用 3.3 V 编程器供电。**

编程器、转接板和供电必须按 **exact part datasheet** 配置。

ESMT 官方数据表还有一个很有意思的字段：

```text
Memory Cell Array = (128M + 4M) × 8 bit
Page Size         = (2K + 64) Byte
```

它正好为后面的 `128+4` 数值提供了器件级的独立印证。

## 6.3 `128+8 / 128+4`：先做一遍最简单的算术

假设是一颗：

```text
128 MiB NAND
2048 B / page
```

那么总页数为：

```text
128 MiB = 134,217,728 B
134,217,728 / 2048 = 65,536 pages
```

如果每页 OOB 是 128 B：

```text
65,536 × 128 B = 8 MiB
128 MiB data + 8 MiB OOB = 136 MiB
```

如果每页 OOB 是 64 B：

```text
65,536 × 64 B = 4 MiB
128 MiB data + 4 MiB OOB = 132 MiB
```

也就是：

```text
OOB 128 B/page → 128 + 8 → 136 MiB raw dump
OOB  64 B/page → 128 + 4 → 132 MiB raw dump
```

社区里“GD 版需要 136 MB、ESMT 版是 132 MB”的记录，与这组 **raw NAND data + OOB** 算术高度吻合。

因此，目前最有证据支持的解释是：

> **社区 shorthand `128+8 / 128+4` 主要是在描述带 OOB 的 programmer raw dump 体积，而不是一张 MTD partition table。**

但这里仍然保留一个重要边界：本文不会把社区作者的 shorthand 语义反过来“定义死”。我们能够确定的是：

> **这些数值不能作为“partition geometry 不同”的证据。**

要证明分区表是否真的不同，需要的是目标机器自身的：

- `/proc/mtd`
- SMEM partition table
- 完整 NAND dump 解析
- 或其它能够直接还原 partition layout 的证据

而不是只看一个 `132 / 136 MB` 文件大小。

## 6.4 “GD vs ESMT”这个社区二分本身也不够准确

如果只按照社区常见说法，很容易写成：

```text
GD   → 128+8
ESMT → 128+4
```

但我们自己的 A / C 已经给出一个反例：

```text
Winbond W25N01GWZEIG → OOB 64 B → 132 MiB raw size
```

也就是说，**OOB 64 B 一侧不只有 ESMT，还包括 Winbond**。

所以更准确的内部表达应该是：

```text
OOB-128 profile
OOB-64 profile
```

而不是：

```text
GD profile
ESMT profile
```

NAND 厂牌和 OOB geometry 可能相关，但它们不是同一个字段。

同理，也不能从两台 RTL8367S 样本恰好都出现 Winbond NAND，就进一步写成：

> “RTL8367S 版就是 Winbond。”

目前样本数量和证据都不足以建立这种绑定关系。

## 6.5 NAND geometry、MTD partition 与 UBI layout 是三套不同信息

这是整个 NAND 章节最重要的概念边界。

### NAND physical geometry

描述的是器件本身，例如：

```text
capacity
page size
OOB / spare size
ECC capability
voltage
```

### MTD partition layout

描述的是闪存被系统切成了哪些区域，例如：

```text
APPSBL
APPSBLENV
ART
rootfs
rootfs_1
plugin
...
```

### UBI layout

则是在某个 MTD / UBI container 内进一步出现：

```text
PEB
LEB
UBI volumes
```

所以完全可能出现这样的情况：

```text
NAND physical geometry 不同
但高层 partition 名称仍然相近
```

也可能出现：

```text
NAND exact part 相同
但 OEM / image 定义的 partition layout 不同
```

这也是为什么恢复工具和未来 toolbox 不能把：

```text
NAND model
```

直接翻译成：

```text
固定 mtd number
```

## 6.6 `mtd15 / mtd16` 不能成为跨设备常量

公开社区记录已经出现过类似：

> rootfs 有时对应 `mtd15`，有时对应 `mtd16`。

而本项目自己的 Product R1 里，B 的 OEM slot / QSDK slot 也有绑定该实体设备的已验证编号。

这两类信息不能混成一句：

> “RT3000 的 OEM 一定在 mtd15。”

正确的原则是：

> **B 的已验证 MTD 编号只属于 B / Product R1 baseline；新的实体设备必须根据本机当前 runtime evidence 重新确认 partition name、offset、size 和 boot state。**

以后工具箱也应该按：

```text
partition name + runtime evidence
```

定位，而不是按历史教程里某个固定 `mtdXX` 硬编码。

## 6.7 对恢复和刷写来说，NAND 差异不是“只是换颗 Flash”

NAND exact part 与 geometry 的差异至少会影响：

- programmer raw image 的正确体积；
- page / OOB 组织；
- ECC / controller 使用方式；
- 恢复镜像是否与目标器件匹配；
- 工具应该如何识别和验证读回结果。

但它**不自动证明**：

- partition layout 一定不同；
- boot selector 一定不同；
- Switch / SoC 一定绑定某一种 NAND；
- 同厂牌 NAND 的机器就能互刷。

所以未来 `h3c-probe` / toolbox 在 NAND 侧至少需要得到：

```text
exact part / JEDEC identity
physical geometry
current partition names / sizes
UBI state（如存在）
current boot state
```

之后才能进入镜像匹配和持久化流程。

这也与整个项目的基本原则一致：

> **先识别真实硬件和当前布局，再选择已验证方案；不要让商品名、NAND 厂牌或历史 MTD 编号替代实际 probe。**

---

## 7. RF / FEM / BDF：同样是 QCN6102，为什么射频仍然不能直接互套

如果只看无线主芯片，A / B / C 和经典 NX30 很容易被归到一起：

```text
5 GHz radio: QCN6102
```

但把 PCB 射频区放到一起之后，会看到完全不同的前端装配：

| 样本 | 5 GHz radio | 独立 5 GHz FEM | 当前证据 |
|---|---|---|---|
| RT3000 A | QCN6102 | **未装配** | 与 NX30 对应的两颗 FEM 位置为空 |
| RT3000 B | QCN6102 | **未见独立 FEM，当前判断未装配** | 正反面照片未见类似 C / NX30 的外置 FEM 装配 |
| RT3000 C | QCN6102（历史硬件记录） | **2 × 8539SD，KCT8539SD 型号族** | U32 / U33 近照直接可见 |
| NX30 classic reference | QCN6102 | **2 × KCT8539S** | 公开拆机报告 |

这张表已经足够说明：
> **“都是 QCN6102”只说明无线主芯片接近，不等于 RF profile 相同。**

<!-- IMAGE TODO: A 与 NX30 对应 5 GHz FEM 区域对照，突出 A 的空焊位置 -->
<!-- IMAGE TODO: C 的 U32/U33 8539SD 近照与 NX30 KCT8539S 公开拆机位置对照 -->

## 7.1 `KCT8539S` 与 `8539SD` 不能当成同一个料号

经典 NX30 的公开拆机资料报告两颗 **KCT8539S**。

C 机的实物近照则能直接读到两颗：

```text
8539SD
```

本项目目前将其记录为 **KCT8539SD 型号族**。在没有厂商料号映射或其它一手资料之前，不把 `8539S` 与 `8539SD` 合并成同一个 exact part。

这不是文字洁癖，而是因为射频前端适配里，以下差异都可能重要：

- FEM 本身的控制方式；
- PA / LNA 路径；
- 控制 GPIO / PAEN / C1 / C2；
- board data 中与前端配置有关的参数；
- PCB 射频走线与天线链路；
- 本机 calibration data。

所以：

```text
QCN6102 相同
```

不能推出：

```text
FEM 相同
BDF 相同
控制脚相同
射频参数相同
```

## 7.2 “无外置 FEM”和“有外置 FEM”是不同 RF profile

A / B 与 C / NX30 的一个非常直观的差异，就是 5 GHz 射频链路上是否装配独立 FEM。

这里也要避免另一个常见误解：

> **没有独立 FEM，不等于“没有功放能力”；有独立 FEM，也不等于只需要把 `txpower` 调高。**

本文只记录板级可见的**独立外置 FEM 装配**。芯片内部的 PA/LNA 能力、完整 RF chain 以及各档位功率表现，需要另外的电路和实测证据。

对适配来说，更合理的分类不是：

```text
QCN6102 device
```

而是继续向下拆：

```text
QCN6102
├── RF profile: no external 5G FEM
├── RF profile: KCT8539S ×2
└── RF profile: KCT8539SD-family ×2
```

这也是为什么 B 的无线配置不能因为“同样是 QCN6102”就直接继承给 C，NX30 的射频参数也不能因为 FEM 位置相似就直接套给 C。

## 7.3 BDF 与 ART / calibration 不是一回事

在这类 Qualcomm 平台上，讨论无线适配时经常会把：

```text
BDF
ART
caldata
```

揉成一句“无线参数”。这会掩盖一个很重要的边界。

本项目当前采用的工作模型是：

### BDF：board / hardware-profile 级数据

BDF 更接近：

> **“这套板级 RF 设计应该怎样被固件理解。”**

因此，同一套真正一致的硬件 variant **可能共享 BDF**；BDF 并不天然要求“每台物理机器一份唯一文件”。

但共享 BDF 的前提是板级 RF profile 足够一致，例如：

```text
5G radio
FEM type
RF chain
control line
board-level configuration
```

而不能只因为两台机器都写着 QCN6102 就假定可共用。

### ART / calibration：设备校准敏感数据

ART / caldata 则需要保留每台设备自身的校准信息。

因此项目采用的原则是：

> **可以研究同硬件 Profile 的 BDF 复用，但不直接用另一台机器的 ART / calibration 覆盖本机。**

这也是未来工具箱里应该把：

```text
BDF identity
ART / calibration identity
```

分成两个字段的原因。

## 7.4 为什么“补两颗 FEM”并不等于把板子变成 NX30

公开 DIY 记录里，有用户尝试在原本没有外置 FEM 的 RC / RT / RW 类板上补装 KCT8539S，但随后观察到 PAEN / C1 / C2 没有按预期使能。

这是社区样本，不足以证明所有此类改装都会得到同样结果；但它至少提供了一个很有价值的工程提醒：

> **FEM 不是单纯焊上器件，再把发射功率参数调高就能完成的。**

一个完整的 RF profile 至少需要同时考虑：

```text
BDF
QCN6102 firmware / board configuration
FEM exact part
GPIO / PAEN / C1 / C2 control
PCB RF path
ART / calibration
```

所以即使两块 PCB 上存在相似的 FEM 焊盘，也不能仅靠“补件”推断它们会得到相同的无线行为。

## 7.5 射频适配应该怎样验证

仅仅做到：

```text
radio created
SSID visible
client associated
```

还不足以证明 RF profile 已经正确。

一个更完整的无线验证至少要继续观察：

- AP 能否稳定启动；
- 认证与 DHCP 是否正常；
- 断开 / 重连是否正常；
- RSSI / 信号强度是否与 OEM 基线合理接近；
- 吞吐与带宽模式是否正常；
- 长时间流量下是否稳定；
- 重启后配置与校准是否仍正确加载。

C 当前仍处在这一类持续验证中，所以本文只把它作为**硬件与 RF profile 的直接证据**，不把 C 的 5 GHz 状态写成“已完成正式支持”。

## 7.6 对未来 `h3c-probe` / mainline 的意义

未来识别工具在无线侧不能只输出：

```text
5G radio = QCN6102
```

更有用的输出应该接近：

```text
5G radio:      QCN6102
external FEM:  none / KCT8539S / KCT8539SD-family / UNKNOWN
BDF identity:  <hash / board profile>
ART identity:  <redacted identity / hash>
RF profile:    <matched / unknown>
```

然后把 Support Gate 绑定到具体 Profile，而不是营销型号。

对 OpenWrt mainline 也是一样：

> **设备支持不仅需要“无线芯片驱动能加载”，还需要 board-level RF data、calibration 来源和实际射频装配匹配。**

这也是整个硬件谱系研究里，RF/FEM 必须和 Ethernet、NAND、PCB 一样被独立记录的原因。

---

## 8. Boot / Partition / 双系统：为什么不能把 B 的 `mtd15/mtd16` 直接套给所有机器

B 机 Product R1 已经走通了一条非常实用的双系统路径：保留原厂系统，同时把 QSDK 放到独立槽位，并验证安装、NAND 启动、主动切换、保留配置升级和恢复出厂等流程。

但这里最容易产生一个危险的误解：

> **既然 B 上是 `mtd15` 原厂、`mtd16` QSDK，那其他 RT3000 也照这个编号做就行。**

这恰恰是本文最不建议做的事情之一。

### 8.1 B 的 `mtd15 / mtd16` 是“样机绑定事实”，不是全系列接口

在当前已验证的 B / Product R1 基线中：

```text
mtd15  -> 受保护的 OEM 槽
mtd16  -> Product R1 / QSDK 目标槽
```

这套映射已经经过 B 实机安装、启动和切换流程验证，因此对 **B 这台已知实体样机和对应镜像基线**是有意义的。

但是这个结论的 Scope 必须写完整：

> **B / Product R1 baseline only。**

它不自动继承到：

- RT3000 A；
- RT3000 C；
- 其他批次 RT3000；
- RC3000 / RW3000 / RW3010 / NX30；
- 任何只因为网页型号相同、PCB 看起来相似或 OEM 能互刷的设备。

社区跨刷记录本身也能看到 `rootfs / rootfs_1` 对应的 MTD 编号会随样机或运行布局变化，因此未来工具不能把固定数字当成设备 ABI。fileciteturn43file1L1-L12

### 8.2 先把四个层次分开

“分区”这个词在刷机讨论里经常被用得过宽。为了避免把不同层混在一起，本项目现在至少区分：

```text
1. boot metadata / identity
2. boot-selection state
3. physical MTD / NAND partition layout
4. UBI container / UBI volume / gluebi exposure
```

它们之间可能有关联，但**当前不能把它们画成一条已经完全证明的固定控制链**。

#### Boot metadata / identity

包括启动日志里的产品字符串、machine/config ID、环境变量等。

它们能告诉我们 bootloader 当前看到的身份和配置线索，但不能单独证明 PCB/BOM。

#### Boot-selection state

社区和本项目记录里出现过：

```text
flag_boot_rootfs
flag_try_sys1_failed
flag_try_sys2_failed
flag_last_success
```

这些变量名强烈提示它们可能参与双系统选择、失败状态或成功状态记录；但在没有完整 bootloader 控制流证据之前，本文只把它们记录为 **selection/fallback-related state candidates**，不宣称已经还原完整自动回退算法。

#### Physical MTD / NAND partition layout

这一层才是：

```text
kernel
rootfs
rootfs_1
ART
pdt_data
plugin
...
```

在 NAND 上真正如何切分、各自容量和边界在哪里。

它必须以**当前实体机器**的 `/proc/mtd`、SMEM/bootloader partition 信息、dump 解析等证据为准。

#### UBI / gluebi 视图

部分社区记录中，后半段 MTD 条目的 erase size 为 `0x1f000`；这与同一记录里 UBI 的 LEB size `126976 = 0x1f000` 完全吻合，并且能够解释 `pdt_data`、`plugin` 等名称在不同层重复出现的现象。

因此目前最合理的解释是：

> **其中一些条目高度符合 UBI volume 经 gluebi 暴露为 MTD 的视图。**

但这仍然属于 **high-confidence interpretation**；在没有 `ubinfo`、sysfs 和逐条映射证据之前，不把 `mtd21–mtd28` 全部写死成“已经证明就是 gluebi”。

### 8.3 “双系统”也不是看到 `rootfs_1` 就算成立

对一个新样机，真正值得进入持久化设计之前，需要先回答：

```text
是否真的存在两个可独立启动的系统槽？
OEM 槽是哪一个？
目标槽是哪一个？
selector 依据什么切换？
失败状态如何记录？
是否有可信的回退路径？
目标槽容量是否足够？
坏块如何处理？
刷写后能否读回校验？
```

所以本项目的阶段门里专门把 **G5 双系统可行性审查**放在持久化之前：如果目标机没有可靠独立槽位或恢复路径，就继续停留在 RAM 实验，不照搬 B 的双系统流程。fileciteturn43file9L1-L14

这也是 C 当前仍然保持 RAM-stage 的原因之一：有线、无线和网络服务可以先在不改持久存储的情况下验证；等板级 Profile、分区、selector 和恢复条件都明确后，再讨论 NAND 写入。

### 8.4 B 已经验证了什么，哪些还没有验证

B / Product R1 r5 当前已经有实机记录支持：

- 正常安装；
- 从 NAND 启动 Product R1；
- OEM / QSDK 主动切换；
- `sysupgrade` 保留配置；
- `sysupgrade -n` 恢复出厂；
- 原厂槽保留策略。

这些结果说明：

> **在 B 这个明确硬件 Profile 上，保留 OEM 的双系统方案是可行的。**

但这并不等于已经验证：

- 任意断电点都能自动回退；
- 任意坏块场景都能恢复；
- bootloader 自动 fallback 的完整语义已经还原；
- 所有 H3C 同系设备都能沿用相同槽位编号。

所以即便对 B，我们也把“主动切换 PASS”和“自动故障回退是否完整实测”分开记录。

### 8.5 为什么固定 MTD 编号对一键工具尤其危险

如果未来工具写成：

```text
if model == RT3000:
    protect mtd15
    flash mtd16
```

那么只要遇到另一个分区布局不同的 RT3000，就可能把“安全双系统工具”变成“精准写错分区工具”。

更合理的流程应该是：

```text
Marketing model
      ↓
只用于候选范围
      ↓
read-only probe
      ↓
SoC / NAND / switch / PCB
partition names + sizes
UBI layout
boot-selection state
OEM slot identity
      ↓
match validated profile
      ↓
only then allow write path
```

而且即便 Profile 匹配，写入前仍要重新确认：

```text
physical sample
current running system
target partition
image identity / SHA-256
backup / recovery condition
```

这与项目当前的 G5/G6 原则一致：先证明双系统条件，再做受控持久化；写入后做读回校验、NAND 启动和主动切换验证。fileciteturn43file3L1-L15

### 8.6 对 OpenWrt mainline 的意义

这一层研究也不仅仅服务于“刷机工具”。

进入 mainline 后，设备支持需要明确：

- NAND partition 定义；
- UBI / image layout；
- sysupgrade 行为；
- calibration / ART 来源；
- bootloader 环境和升级路径；
- recovery 边界。

如果把 B 的布局未经验证就复制给 C 或其他型号，即使系统偶尔能启动，也会把错误写进长期维护的 DTS / image recipe / upgrade logic。

因此这里和前面的 Ethernet、NAND、RF 一样，最终原则仍然是：

> **每个可发布支持声明都绑定到实际硬件 Profile，而不是绑定到外壳上的商品型号。**

---


# 9. 外部样本：NX30 / RC3000 / RW3010 / RW3000

A / B / C 是本文最强的 P0 实体证据，但如果只看这三台 RT3000，我们仍然无法判断这些差异究竟只存在于 RT3000，还是贯穿更大的 H3C IPQ50xx AX3000 产品群。

因此，本轮研究又把 NX30、RC3000、RW3010、RW3000 的公开资料按“**具体样本**”重新整理。这里最重要的纪律是：**外部帖子只证明帖子里那一台机器，不代表整个型号。**

## 9.1 NX30：公版参考基线，而不是“第四台 RT3000”

经典 NX30 公开拆机样本提供了一套相对完整的参考组合：

```text
SoC / RAM:    IPQ5000 / Integrated 256 MiB DDR3L
Ethernet:     QCA8337-AL3C
NAND:         GD5F1GQ5REYIG
5 GHz radio:  QCN6102
5 GHz FEM:    2 × KCT8539S
2.4 GHz FEM:  未装独立外置 FEM
```

它与 B 在若干主要器件维度高度接近，但又明确装有两颗 KCT8539S，而 B 的整板照片未见对应独立 FEM。

因此，NX30 在本项目里更适合作为：

> **`NX30_PUBLIC_BASELINE` —— H3C 公版参考产品。**

而不是 A/B/C 旁边再编号一个“D 类”。

当前公开资料仍不足以证明：

- 所有 NX30 批次都永久保持同一 BOM；
- NX30 与 B 是同一 PCB；
- B 只要补两颗 FEM 就会变成 NX30；
- NX30 的 BDF、ART、GPIO、partition 可以直接继承给 B 或 C。

更准确的说法是：**经典 NX30 与 B 在已知主要器件组合上高度接近，5 GHz 外置 FEM 是目前确认的一项显著差异。**

> **图位建议 9-1：经典 NX30 拆机图，只引用原文链接；如未获授权，不直接转载外部作者图片。**

## 9.2 RW3010：目前最强的 B-like 外部候选

数码之家公开 RW3010 样本的照片可以核对到：

```text
Model:        H3C Magic RW3010 / China Unicom
PCB:          H3C AX3000 REV:A0
SoC:          IPQ5000
Switch:       QCA8337
5 GHz radio:  QCN6102
NAND:         GigaDevice 5F1GQ5REYIG
5 GHz FEM:    正反面照片未见独立外置 FEM
```

其中 `AX3000 REV:A0 + IPQ5000 + QCA8337 + QCN6102 + GigaDevice NAND` 与内部 B 的主要字段高度接近。

因此 RW3010 可以被描述为：

> **B-like / high-similarity candidate。**

但它仍然没有继承 B 的 Product R1 验收，因为当前缺少该具体 RW3010 样本的：

- partition / UBI；
- boot selector；
- ART / calibration；
- BDF；
- GPIO；
- sysupgrade / recovery；
- 实机运行测试。

而且必须强调：**RW3010 ≠ RW3000**。一个型号的拆机图不能拿来替另一个型号补 BOM。

## 9.3 RC3000：同一 Marketing Model 内也已经出现不同路线

RC3000 的公开资料很能说明“Marketing Model 不是 BOM ID”。

早期拆机样本报告过：

```text
IPQ5000
QCA8337-AL3C
QCN6102
GigaDevice NAND
未装独立 5 GHz FEM
```

社区恢复帖又出现过 ESMT `F50D1G41LB` 批次。

更重要的是，2025 年底一条中国电信 RC3000 R009 用户报告给出了另一套明显不同的组合：

```text
IPQ5018
RTL8367S
QCN6102
KCT8539SD
W632GU6NB-11
Winbond W25N01GW
```

该用户随后报告强制刷 NX30 后设备失效，并在后续称“全砖，无输出”。

这条记录的意义不是“RC3000 都是 RTL8367S”，而是恰恰相反：

> **RC3000 已经同时出现 QCA8337 与 RTL8367S 的公开样本，因此不能再用商品名直接猜交换机。**

目前可以保留一个识别层的工作模型：RTL8367S 已跨 RT3000 / RC3000 出现，值得作为独立 Ethernet profile 候选；但这不证明这些 RTL 样本同 PCB、同 boot、同 BDF，也不证明固件可互刷。

## 9.4 RW3000：研究范围内，但暂不归组

RW3000 是本项目明确关注的目标之一，但当前高质量可复核的独立拆机材料不足。

社区跨刷资料说明它与 RT/RC/NX30 存在软件关系线索，但这不能替代：

```text
铭牌
PCB 正反面
SoC 顶标
Ethernet Switch
NAND exact part
RF / FEM
OEM partition / boot
```

因此本文对 RW3000 的处理很简单：

> **UNKNOWN / insufficiently verified。**

不为了把表格填满而把 RW3010、RT3000 或聚合网站的数据套给它。

## 9.5 外部样本带来的真正结论

把这些资料与 A/B/C 放在一起后，最稳的结论不是“我们已经还原出 H3C 一共有几版硬件”，而是：

1. **同一 Marketing Model 下可以出现不同 SoC / Switch / NAND / RF 组合；**
2. **不同 Marketing Model 之间又可能出现高度接近的 PCB / 主器件组合；**
3. **所以产品名只能用于缩小搜索范围，不能直接当固件选择器。**

这也是本文采用“Observed Sample + Independent Profile Dimensions”而不是“型号 = 固定 BOM”的原因。

---

# 10. Evidence / Validation：为什么“能启动”不等于“支持”

硬件谱系研究的另一半不是“找到多少料号”，而是**如何描述一个固件到底验证到了什么程度**。

社区刷机讨论里经常出现：

```text
能进系统
有 Wi-Fi
后台能开
刷成功
变砖
```

这些词都很有信息量，但如果不拆开，很容易把一个局部现象误写成整机结论。

因此，本项目不再使用简单的“成功 / 失败”二分，而采用 capability matrix。

## 10.1 十一个能力维度分别记录

当前跨刷 / 运行记录至少拆成：

| Capability | 含义 |
|---|---|
| `BOOT` | 是否观察到目标系统正常启动，而不是只停在 Bootloader |
| `SHELL/WEB` | 是否实际进入 Shell 或 Web 管理面 |
| `LAN` | LAN 是否有真实双向数据通信 |
| `WAN` | WAN 是否能正常工作 |
| `WIFI_BCAST` | SSID 是否实际广播 |
| `WIFI_ASSOC` | 客户端是否实际关联成功 |
| `DHCP` | 客户端是否实际取得地址 |
| `INTERNET` | 是否实际完成互联网访问 |
| `MESH` | 是否完成真实 Mesh 组网，而不是“等待配对” |
| `REBOOT` | 是否验证重启后仍可工作 |
| `STABILITY` | 是否做过有意义的持续运行 / 流量稳定性测试 |

每一项只能取：

```text
PASS
FAIL
NOT_EXECUTED
UNKNOWN
```

最关键的规则是：

> **只有被实际观察或测试到的维度，才允许写 PASS / FAIL；没有证据就写 UNKNOWN。**

## 10.2 `NOT_EXECUTED != PASS`

例如一个用户说：

> “系统启动了，Wi-Fi 也广播了。”

这最多直接支持：

```text
BOOT       = PASS
WIFI_BCAST = PASS
```

它不能自动变成：

```text
LAN        = PASS
WAN        = PASS
DHCP       = PASS
INTERNET   = PASS
STABILITY  = PASS
```

同样，“网页能打开”也不等于 WAN / NAT / Wi-Fi association 已经通过。

## 10.3 “变砖”也不等于所有 capability 都 FAIL

如果一条社区记录只说：

> “刷后砖了。”

那么除非原文明确给出“不开机”“无任何输出”等可定位到 BOOT 层的证据，否则不能把：

```text
LAN
WAN
Wi-Fi
DHCP
Internet
```

全部填成 FAIL。

因为这些能力可能根本没有进入可测试阶段。

即使能够确认 `BOOT = FAIL`，其它字段也通常仍应保持 `UNKNOWN`。

这条纪律听起来很保守，但它能避免把一个“早期启动失败”伪装成“无线、网络、DHCP 全部测试失败”。

## 10.4 本轮 19 条公开跨刷 / 运行记录的审计结果

在本轮实际纳入 capability matrix 的 19 条公开记录中，经过逐条按原文重新取值后：

| 状态 | 数量 |
|---|---:|
| `VALIDATED_SUPPORT` | **0** |
| `PARTIAL` | **7** |
| `FAIL` | **3** |
| `CLAIMED_ONLY` | **5** |
| `UNKNOWN` | **4** |

其中三个 `FAIL` 都只在 `BOOT` 维度有足够直接证据；没有把“变砖”传播成整行 FAIL。

更值得注意的是：

> **这些公开记录中，没有一条达到本项目定义的 `VALIDATED_SUPPORT`。**

这不意味着这些社区教程“没用”。它们对软件身份、分区、刷机路径和硬件变体都提供了大量线索；只是它们的原始目标往往不是做一套完整工程验收，所以不能由“作者说刷成功”直接推导成“硬件完整支持”。

## 10.5 什么情况下才允许写 `VALIDATED_SUPPORT`

`VALIDATED_SUPPORT` 不是“开机成功”的同义词，而是一个预定义 Gate。

对本项目而言，一个面向发布的 Profile 至少要根据实际范围覆盖：

```text
boot
wired ports
WAN/LAN separation
DHCP / DNS / routing / NAT
2.4G association
5G association
MAC / calibration source
reboot
upgrade / factory reset
persistent boot
recovery boundary
stability
```

不同开发阶段可以有不同 Gate，但必须在文档中写清楚。

例如 C 当前已经有多项 RAM-stage 网络 PASS，但只要持久化、长稳和完整无线回归没有完成，就继续保持 `PARTIAL`。这比一句“C 已经搞定”更准确，也方便后来者复现实验边界。

## 10.6 Evidence 与 Capability 必须同时存在

一个高质量支持声明至少回答两件事：

```text
Evidence：这条结论是谁、在哪台实体、用什么证据得到的？
Capability：它具体通过了哪些能力，哪些没有测试？
```

这也是本文把“硬件考据”和“固件验收”放在一起讨论的原因。

如果硬件身份都没确认，Capability 很可能绑定错对象；如果 Capability 没拆开，硬件表再精确也无法告诉用户“这台机器到底能不能放心刷”。

---

# 11. 对 Product R1、硬件识别工具和 OpenWrt mainline 的影响

这项调查并不是为了做一张越来越大的芯片表。它已经反过来改变了 Product R1 的发布方式、未来工具箱的安全模型，以及 mainline 适配路线。

## 11.1 Product R1：从“RT3000 固件”变成“绑定 Profile 的发布”

B 当前仍然是 Product R1 r5 的已验证发布基线。

这意味着公开支持声明应该写成类似：

> **RT3000 B-class validated baseline / 实体 B 样机及匹配硬件 Profile 已验证。**

而不是：

> **所有 RT3000 已支持。**

C 的 RTL8367S 路线已经证明很多功能可以工作，但在 NAND 持久化、完整长稳与恢复门槛通过之前，仍然属于研究 / PARTIAL 状态。

这种写法的好处是：新增样机不需要重新发明一套项目，而是先回答：

```text
它匹配哪个已知 Profile？
哪些字段一致？
哪些字段未知？
哪些 Gate 必须重新跑？
```

## 11.2 `h3c-probe` / toolbox：先识别，再放行

未来一键工具不应该只是一个更漂亮的刷写脚本。

更重要的工作其实发生在刷写之前：**只读识别。**

理想的 probe 输出可以接近：

```text
Marketing / OEM
  model: RT3000
  web_hw_version: VER.A
  oem_version: R007

SoC / RAM
  soc: IPQ5018
  ram_topology: discrete

Ethernet
  switch: RTL8367S
  cpu_link: <detected / unknown>

NAND
  vendor: Winbond
  part: W25N01GWZEIG
  geometry: 2048 + 64

Boot / Partition
  physical_mtd: <current mapping>
  ubi: <current mapping>
  oem_slot: <resolved by name / evidence>
  selector_state: <observed>

Wi-Fi / RF
  5g_radio: QCN6102
  external_fem: KCT8539SD-family ×2
  bdf_identity: <hash/profile>
  calibration_identity: <redacted hash>

Detected profile
  <matched / candidate / unknown>

Support state
  VALIDATED / EXPERIMENTAL / UNSUPPORTED / UNKNOWN
```

然后才进入：

```text
match validated profile
        ↓
verify image identity
        ↓
verify backup / recovery
        ↓
explicitly allow write path
```

对于未知组合，正确动作不是“猜一个最像的镜像”，而是：

> **停止持久化，收集资料。**

## 11.3 识别逻辑不能只看一个字段

本文已经出现很多“单字段会误导”的例子：

```text
model = RT3000          → A/B/C 都可能
web hardware = VER.A    → B/C 仍明显不同
switch = QCA8337        → A/B 仍不是同一整机
nand = Winbond          → A/C 仍不是同一整机
radio = QCN6102         → A/B/C/NX30 RF profile 仍不同
```

所以工具识别必须是多字段匹配，并保留 `UNKNOWN`。

一个可信的 probe 甚至应该比“识别成功”更愿意说：

> `PROFILE_UNKNOWN — persistent write blocked`

这比误判后“一键成功写错槽”更有价值。

## 11.4 对 OpenWrt mainline 的意义

在本轮审计覆盖的 OpenWrt `25.12.0-rc4` `qualcommax/ipq50xx` 设备清单中，没有 RT3000 / RC3000 / RW3000 / RW3010 / NX30(IPQ50xx) 的正式设备支持。

与此同时，OpenWrt 已经存在其它 IPQ5000 + QCA8337 + QCN6102 平台的量产设备支持，例如 CMCC PZ-L8。这说明平台级能力并不是空白；真正需要完成的是 H3C 这些板子的**板级表达与验证**。

对于本项目，比较自然的 upstream 顺序是：

1. **先把 B 的已知成熟 Profile 做成可审查的 mainline device support；**
2. 再处理 C 的 RTL8367S variant；
3. 对 RW3010 / NX30 / RC3000 等新增实体，按各自 Profile 验证，不从 Marketing Model 自动继承。

最终 upstream 是否使用多个 `compatible`、是否共享 DTSI、哪些内容可以抽成 common profile，应该由真实板级差异决定，而不是为了“一个型号一个文件”或“全家桶一个文件”提前定答案。

## 11.5 公开研究与私有实现可以分层

硬件差异、照片证据、Profile 方法和支持边界适合尽早公开，因为它们能：

- 给研究成果建立公开时间线；
- 让社区用户补充新批次样本；
- 降低别人按商品名误刷的风险；
- 为未来 upstream review 提供可引用的硬件依据。

而尚未稳定的实现细节可以继续留在开发流程中，等达到 reviewable / reproducible 状态再公开。

因此，本项目的长期结构更接近：

```text
Public hardware research / evidence
            ↓
Canonical hardware profiles
            ↓
Private / experimental implementation
            ↓
Validated Product R1 / upstream patch
```

公开“发现”与谨慎发布“实现”并不冲突。

---

# 12. 证据等级、引用规则与样本征集

这份调查里最容易出错的事情，不是芯片型号本身，而是**把不同强度的证据写成同一种语气**。

因此，本项目采用两条互相独立的证据轴。

## 12.1 Axis 1：Source Authority

| 等级 | 定义 | 典型用途 |
|---|---|---|
| **P0** | 本项目实体样机：原始照片、实机日志、运行测试 | 支持项目自己的硬件事实和发布 Gate |
| **P1** | 厂商官方资料、上游已合入代码 / 提交 | 器件规格、平台能力、上游事实 |
| **P2** | 高质量公开拆机 / 开发记录 | 具体外部样本的较强旁证 |
| **P3** | 社区用户明确样机报告 / bootlog / 刷机记录 | 样本线索、失败记录、跨刷经验 |
| **P4** | 聚合、搜索摘要、无原始材料的二手描述 | 只用于继续查找，不作为硬件认证 |

P3 并不是“没价值”。RC3000 R009 / RTL8367S 这种样本就是非常重要的 P3 线索。

关键在于：

> **P3 证明“有人明确报告过这一台”，不证明“整个型号都如此”。**

## 12.2 Axis 2：Retrieval / Verification State

同一个网站很权威，也不代表本轮已经完整读过它。

所以第二条轴单独记录：

```text
FULL_TEXT
FULL_TEXT_IMAGE
ARCHIVED_IMAGE
SEARCH_SNIPPET
NOT_OPENED
```

例如：

```text
Authority = P1
Retrieval = SEARCH_SNIPPET
```

意味着“来源站点很权威，但本轮只拿到了搜索摘要”，这时就不能写成“官网全文明确说明……”。

这套双轴规则能避免两个常见错误：

1. 因为来源是官网，就把没打开的网页当成已经完整核验；
2. 因为把外部作者照片下载到本地并算了 SHA-256，就把它升级成自己的 P0。

## 12.3 外部图片的引用原则

外部作者的照片，即使本项目已经：

```text
下载
归档
计算 SHA-256
逐张识别
```

它仍然是**外部作者的图片**。

保存原件 ≠ 获得公开转载许可。

因此本文公开发布时默认：

- 优先文字总结；
- 给出原帖 / 原文链接；
- 需要直接转载图片时先确认许可；
- 不把外部作者照片署成“本项目实拍”。

本项目自己的 A/B/C 原始照片则可以作为 P0 图版，但发布前仍会检查序列号、MAC、账号等隐私信息。

## 12.4 当前主要公开来源

下面列出本文会用到的主要公开入口；它们分别承担不同证据角色，不应被简单加总成“多个独立来源”。

### 拆机 / 硬件

- NX30 经典拆机原文入口：  
  https://www.acwifi.net/15584.html
- NX30 拆机转载（本轮曾用于全文核对）：  
  https://www.jb51.net/network/787218.html
- RC3000 拆机与简测：  
  https://www.163.com/dy/article/GUJDQFNU0512MJDN.html
- RW3010 拆机：  
  https://www.mydigit.cn/thread-369604-1-1.html
- RT3000 板型 / 补 FEM 社区记录：  
  https://www.mydigit.cn/thread-467610-1-1.html

### 跨刷 / 运营商版 / 恢复

- 2022-01 的 RC / RT / RW3000 → NX30 社区记录：  
  https://www.right.com.cn/forum/thread-7753062-1-1.html
- RC3000 ESMT / TTL 讨论：  
  https://www.right.com.cn/forum/thread-8383537-1-1.html
- RC3000 programmer recovery / `132/136 MiB` 记录：  
  https://www.right.com.cn/forum/thread-8419774-1-1.html
- RT3000 / RC3000 交换机差异记录：  
  https://www.right.com.cn/forum/thread-8441648-1-1.html
- ESMT / QCA8337 与目标固件记录：  
  https://www.right.com.cn/forum/thread-8467854-1-1.html
- RC3000 R009 / RTL8367S：  
  https://www.chinadsl.net/thread-181780-1-1.html
- OEM 跨身份迁移记录：  
  https://blog.csdn.net/gongcheng521/article/details/156914114

### NAND 厂商资料

- Winbond W25N01GW：  
  https://www.winbond.com/hq/product/code-storage-flash/qspi-nand/w25n-gw/?__locale=en&partNo=W25N01GWZEIG
- GigaDevice GD5F1GQ5RE：  
  https://www.gigadevice.com/product/flash/spi-nand-flash/gd5f1gq5re
- ESMT F50D1G41LB 产品页：  
  https://www.esmt.com.tw/cn/product/item/F50D1G41LB-2M

## 12.5 如果你手里有这批 H3C，什么资料最有价值

比“我的也是 RT3000”更有价值的是一套可绑定到具体样本的资料。

### 最优先：照片

请尽量提供：

- 整机型号 / 运营商版本；
- PCB 正面全景；
- PCB 背面全景；
- SoC 顶标；
- Ethernet Switch 顶标；
- NAND 顶标；
- QCN6102 与 5 GHz FEM 区域；
- 完整 PCB `REV / VER` 丝印。

### 如果设备仍可运行：只读信息

例如：

```text
原厂 Web 软件版本 / Hardware Version / Bootrom
bootlog
/proc/mtd
fw_printenv（只读）
SMEM partition 信息（只读）
ubinfo -a（如系统存在 UBI）
```

请不要为了投稿硬件资料而进行任何不熟悉的写入、拆焊或跨刷操作。

### 隐私

公开前请遮盖：

```text
完整 SN
MAC账号
密码 / token
运营商个人信息
```

型号、PCB 丝印和芯片顶标通常应保留，因为它们正是这项研究需要的硬件证据。

## 12.6 如何处理新的反例

本文不是为了证明一个“永远正确的四类表”。

如果未来出现：

- 第四种 RT3000 完整 PCB；
- NX30 不同 Switch / NAND / FEM 批次；
- RW3000 的可靠拆机；
- RC3000 新 SoC 或新 PCB；

正确动作不是把反例解释掉，而是：

```text
记录具体实体
→ 评估证据等级
→ 更新 Canonical Fact Base
→ 必要时新建 / 调整 Profile
→ 重新评估公开支持边界
```

“未找到”永远不等于“不存在”。

---

# 13. 结论

这项调查最初只是为了回答一个很实际的问题：

> **同样叫 RT3000 的机器，能不能直接按同一套 QSDK / OpenWrt 配置处理？**

三台实体样机已经给出了否定答案。

目前最重要的事实可以压缩成下面几条：

1. **同名 H3C Magic RT3000 已经实物确认至少存在三套明显不同的硬件组合。**
2. **A/B 使用 QCA8337-AL3C，C 使用 RTL8367S；Ethernet route 已出现实质分叉。**
3. **NAND 同样存在 GigaDevice / Winbond / ESMT 等变体；`128+8 / 128+4` 最有证据支持的解释是 raw data + OOB dump size，而不是分区表大小。**
4. **同样使用 QCN6102，不代表 5 GHz RF profile 相同；无外置 FEM、KCT8539S、KCT8539SD-family 应分别记录。**
5. **B 与 C 都可显示 `RT3000 / VER.A / Bootrom 100`，却对应不同 OEM 最新软件版本与不同实际硬件，因此 Web “Hardware Version”不能作为硬件 Profile 判据。**
6. **不同 Marketing Model 之间又可能出现高度接近的 PCB / 主器件组合，例如 B 与某 RW3010 样本。**
7. **跨刷记录必须按 Capability 拆开；“能启动”“有 Wi-Fi”“变砖”都不能替代完整支持验证。**
8. **任何持久化工具都应该先识别 SoC / Switch / NAND / partition / RF / boot state，再匹配已验证 Profile，而不是按商品名或固定 MTD 编号写入。**

因此，本项目当前采用的核心模型是：

```text
Marketing / OEM identity
          +
Actual hardware profile
          +
Capability evidence
          ↓
     support decision
```

这套模型不是对 H3C 工厂生产流程的猜测，也不是“全家桶通刷表”。它只是把目前已经观察到的现实硬件差异，转化为一种更安全、更容易复现、也更适合后续 mainline 的工程方法。

下一阶段，这份硬件研究会继续服务于三个方向：

- **Product R1**：让发布支持绑定具体硬件 Profile；
- **h3c-probe / toolbox**：先识别，再决定能否进入写入流程；
- **OpenWrt mainline**：把 B 的成熟路线与 C 的 RTL8367S 路线分别整理成可审查的板级支持，而不是把“RT3000”三个字当成唯一硬件定义。

如果你手里有不同批次的 RT3000 / RC3000 / RW3000 / RW3010 / NX30，欢迎提供经过脱敏的 PCB 正反面与芯片近照。新的反例不会“破坏”这项研究；恰恰相反，**每一个能够绑定到具体实体的新样本，都会让这张硬件地图更接近真实世界。**

---

## 项目

H3C RT3000 Product R1：  
https://github.com/FlyFish-go/H3C-RT3000-Product-R1

> 本文为 Hardware Research v1.0 公开版本。具体固件支持范围、安装方式和风险说明以对应 Release / 安装文档为准；本文本身不是跨刷教程。