# H3C IPQ50xx：HW-A / HW-B / HW-C / HW-D 工程分组与 OEM 识别依据

> 核对日期：2026-10-19。HW-A/B/C/D 是 **FlyFish-go 的 PCB 工程分组**，不是 H3C 官方 revision、外壳背标 A1/B0/C1/D0、PCB 上的 `VER.A`、固件的 A/B 槽，也不是可通刷列表。**硬件分组**与**精确固件实机验收**须分别记录。

## 1. 一张表看懂四组与三条 OEM 路由

| HW | PCB / 芯片分组特征 | 代表 OEM machid / 控制 FDT | 代表样机 | U-Boot `v0.1.0-pre.1` | QSDK 11.5 |
|---|---|---|---|---|---|
| **HW-A** | 长板；IPQ5018、外置 DDR、QCA8337 | `0x08040001` / MP03.1 | RT3000 A、RC3000 A2 | 独立候选、**本轮未实测** | 目前无完整 QSDK 样机验收 |
| **HW-B** | 短板；IPQ5000、集成 DDR、QCA8337 | `0x08040000` / MP02.1 | RT3000 B、RC3000 D0 | 独立候选、**本轮未实测** | RT3000 B **Product R1 r5** 已完成阶段验证 |
| **HW-C** | 长板；IPQ5018、外置 DDR、RTL8367S | `0x08040101` / MP03.1-C2 | RT3000 C、RX3000 | 独立候选、**本轮未实测** | RT3000 C **Native08** 已持久化安装及有界功能验证，仍有开放问题 |
| **HW-D** | NX30 型长板；IPQ5000、集成 DDR、QCA8337 | `0x08040000` / MP02.1 | NX30、RC3000 B0 | **仅一台 NX30 指定候选有限验收通过** | 有 D 独立构建候选，未取得整机通过结论 |

**最容易误解的地方：** `0x08040000` 同时存在于 **HW-B 和 HW-D** 的 OEM 代表原始备份。四个 HW 组并没有四种唯一 machid，当前是 **四个工程组、三条已核实的 OEM 路由**。`0x8040000` 与 `0x08040000` 只是前导零写法不同。代表样机结果不可推广为组内每台都具有相同 machid。

## 2. 根据实物给四组命名

### HW-A

- 长板、IPQ5018、外置 DDR、QCA8337。RT3000 A（`RT-A01` / A1 Y2）使用 Winbond 外置 DDR、W25N01GWZEIG，历史上曾进入 RAM 系统，目前样机已损坏。
- RC3000 A2（`RC-A2-512`）外置 Samsung DDR 已扩容到 512 MiB；该结果是 OEM/U-Boot 层的内存验证，不是 QSDK 固件支持结论。`RC-A2-SBL` 为另一台故障记录。RW3000（`RW30-01`）依布局/DDR/交换机暂归 A 的研究路线，**SoC 实物顶标仍未知**。
- RC-A2-512 原始 CDT tuple `[2,8,4,0,1]` → `0x08040001`，OEM 控制 FDT 为 MP03.1，FIT 目标 `config@mp03.1`。不冒充已损坏 RT-A01 的“本次实测”。

### HW-B

- **短板**、IPQ5000、集成 DDR3L、QCA8337。RT3000 B（`RT-B01`，商品背标 **D0 Y2**）集成 256 MiB RAM、GD5F1GQ5REYIG，是 QSDK Product R1 r5 的实际验证基线。
- RC3000 D0（`RC-D0-FUDAN`）有 Fudan FM25LS01 NAND，**归 HW-B 而不是 HW-D**。RW3010（`RW31-01`）为研究归类，实物交换机型号被遮挡，暂不宣称与 RT-B01 同 BOM。
- RT-B01 原始 CDT tuple `[2,8,4,0,0]` → `0x08040000`，OEM MP02.1 / `config@mp02.1`。同一 machid **无法独立区分 B/D**。
- r5 的 NAND 写入、OEM/QSDK 双槽切换、读回、网络和双频阶段验证只覆盖对应 B 样机与对应镜像；2026-10-15 B 板 RESET、LED、启动参数的源码修复并非新镜像的整机通过证明。

### HW-C

- 长板、IPQ5018、外置 DDR、**RTL8367S**。RT3000 C（`RT-C01`，C1 Y2）记录 GigaDevice 外置 DDR、W25N01GWZEIG、双 8539SD 型号族 FEM；RX3000（`RX-01`，A0 Y2）记录 Winbond 外置 DDR 和同交换机路线。**同组不代表所有 BOM 逐件相同。**
- RT-C01 原始 CDT tuple `[2,8,4,1,1]` → `0x08040101`，OEM MP03.1-C2 / `config@mp03.1-c2`。
- QSDK Native08 已在 RT-C01 完成非原厂槽持久化安装、写后读回、断电冷启动、配置持久化以及有限三 LAN、WAN/NAT、双频实际关联测试。**首次 2.4GHz DHCP OFFER/ACK 偶发丢失与 RX 速率等事项仍 OPEN**，不能称长期稳定或已经发布整个 C 组固件；RX-01 未继承该验收。

### HW-D

- **NX30 型长板**、IPQ5000、集成 DDR、QCA8337。NX30（`NX-01`，A2 Y2）记录 GigaDevice NAND 与双 KCT8539S FEM；RC3000 B0（`RC-B0-ESMT`，B0 Y2）记录 ESMT F50D1G41LB、`NX30_B0` 板印、独立 5GHz FEM 焊盘空置。是否同一裸板需保留未知。
- NX30 原始 CDT tuple `[2,8,4,0,0]` → `0x08040000`，OEM MP02.1 / `config@mp02.1`。这与 HW-B 代表备份相同；**主要依靠长短板、布局、器件组合将 B、D 分开**，不拿 FEM 或 NAND 品牌单独判组。
- U-Boot `v0.1.0-pre.1` 的有限验收仅绑定**一台 NX30**：Winbond W25N01GWZEIG（EF:BA:21）、128 MiB、page 2048、spare 64、ECC4、R012 SBL。安装事务、写后读回、默认原厂 B 启动及维护网页部分流程已验证。其他 NX30 或其他 NAND/ECC/启动链不自动继承。
- QSDK D 独立候选已出现 `h3c_nx30_hw_d`、`h3c_nx30_hw_d_ram`、`h3c_nx30_hw_d_installer_ram` 等 profile。2026-10-19 的 `build03` 冻结回执明确标注 **BUILD/ARTIFACT BASELINE ONLY**；它不是 NAND INSTALL PASS，更不是整个 HW-D 的验收结论。

### 三个典型“字母陷阱”

- **RC3000 D0 Y2 → HW-B**；**RC3000 B0 Y2 → HW-D**；商品背标 D0/B0 与工程 HW 字母不是同一套编号。
- 丝印 `H3C AX3000-D VER.A` 不等于 HW-D；原厂 Web 显示 `VER.A` 也不能唯一决定板级 BOM。
- FEM 是否焊接、GD/ESMT/Winbond NAND、ECC4/ECC8、256/512 MiB DDR 是需要记录的**样机差异与刷写边界**，不等于四组唯一的分类规则。

## 3. 从 OEM machid 得到什么、得不到什么

| 与原始备份绑定的代表样机 | CDT tuple（离线解析） | machid | OEM 控制 FDT | Linux FIT 配置候选 |
|---|---|---|---|---|
| RC3000 A2（RC-A2-512）启动区备份 | `[2,8,4,0,1]` | `0x08040001` | MP03.1 | `config@mp03.1` |
| RT3000 B（RT-B01）CDT/APPSBL 备份 | `[2,8,4,0,0]` | `0x08040000` | MP02.1 | `config@mp02.1` |
| RT3000 C（RT-C01）CDT/APPSBL 备份 | `[2,8,4,1,1]` | `0x08040101` | MP03.1-C2 | `config@mp03.1-c2` |
| NX30 原厂启动链备份 | `[2,8,4,0,0]` | `0x08040000` | MP02.1 | `config@mp02.1` |

原始 CDT、APPSBL、整 NAND、ART 和设备唯一标识均**未作为公开附件上传**。上表是本项目对对应原始样机备份进行离线解析和核对的结果，公开读者可核对下列脱敏结论、源码入口和处理照片；**不能声称本 GitHub 已提供全部原始字节用于独立重复提取**。

**OEM 启动链的三个不同动作：**

1. `SoC/PBL/SBL → CDT/SMEM → APPSBL`。已核对 APPSBL 优先尝试 `SMEM item 425`，失败时使用 `SMEM item 137` 的平台信息；**SBL 写入 item 425 的完整链路仍待闭合**。
2. APPSBL 用已取得的 machid 路由到 **MP02.1 / MP03.1 / MP03.1-C2 控制 FDT**。这发生在 Linux FIT 目标选择之前。
3. `config@mp02.1` 等 FIT 配置、`SOC := ipq5000` 构建变量、环境变量 `machid` 均不是“改个值就能变一块主板”。Linux 跳转时传递的参数也不会重新决定此前 U-Boot 的 GPIO/设备树选择。

**识别原则：** `0x08040000` 只筛出 B/D 候选。如果无法从 PCB 身份、器件布局、NAND/ECC 与完整启动链证明精确匹配，工具应该拒绝不确定目标，而非猜一个 HW 组执行写入。

## 4. 实物照片与证据边界

下列图片来自项目自有 **RT3000 A/B/C 实机照片的公开去识别衍生图**；公开原始研究文档见 [Hardware Research v1.0](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/blob/main/docs/H3C-IPQ50xx-Hardware-Research-v1.0.md)。

![RT3000 A/B/C PCB 正面对照](https://raw.githubusercontent.com/FlyFish-go/H3C-RT3000-Product-R1/44d9667aec865ec1098c5910837ce292325736b6/docs/images/hardware-research-v1/rt3000-abc-board-front-comparison.webp)

*图 1：PCB 整体布局对照。不能以一幅代表图覆盖同组所有主板。*

![RT3000 A/B/C SoC 顶标](https://raw.githubusercontent.com/FlyFish-go/H3C-RT3000-Product-R1/44d9667aec865ec1098c5910837ce292325736b6/docs/images/hardware-research-v1/rt3000-soc-comparison.webp)

*图 2：实物顶标 A=IPQ5018、B=IPQ5000、C=IPQ5018，优先于早期软件命名。*

![RT3000 B/C 交换芯片对照](https://raw.githubusercontent.com/FlyFish-go/H3C-RT3000-Product-R1/44d9667aec865ec1098c5910837ce292325736b6/docs/images/hardware-research-v1/rt3000-switch-comparison.webp)

*图 3：B=QCA8337，C=RTL8367S；A 的 QCA8337 由另行保存的实物记录支持。*

![RT3000 C 的双 FEM](https://raw.githubusercontent.com/FlyFish-go/H3C-RT3000-Product-R1/44d9667aec865ec1098c5910837ce292325736b6/docs/images/hardware-research-v1/rt3000-c-fem-8539sd-pair.webp)

*图 4：HW-C 代表样机的 8539SD 装配位置；不推定所有同组样机完全一样。*

NX30 与 RC3000 B0 的板级照片、`NX30_B0` 丝印照片已经归档在项目私有样机档案中，公开稿仅引用脱敏文字和 OEM 备份分析结论；**未将含设备唯一二维码/标签的私人原图推送至 GitHub**。A/B/C 的公开照片不是 D 的直接实物证明。

## 5. U-Boot 和 QSDK 11.5 的实际代码映射

| HW | U-Boot `build-release.sh` 对应 defconfig | QSDK 11.5 的实际软件入口 |
|---|---|---|
| A | `ipq5018_h3c_hw_a_production_defconfig` | 未见已经通过 A 机完整验收的独立 H3C A 生产 profile |
| B | `ipq5018_h3c_rt3000_b_defconfig` | `h3c_rt3000`；Product R1 r5 仅限 RT-B01 精确基线 |
| C | `ipq5018_h3c_hw_c_production_defconfig` | `h3c_rt3000_rtl8367s_ram`、`_mtd_discovery_ram`、`_native_slot1`、`_installer_ram`；Native08 绑定 RT-C01 |
| D | `ipq5018_h3c_hw_d_production_defconfig` | 隔离开发树 `h3c_nx30_hw_d` 及 RAM、installer RAM profile；build03 尚不是实机验收 |

四份 U-Boot defconfig 都沿用了 `ipq5018_*` **软件命名前缀**；QSDK C 的 `SOC := ipq5000` 也是构建目标字段。不能因为这些字符串就否定实物 HW-B/D 为 IPQ5000、HW-A/C 为 IPQ5018 的结论。

## 6. 可追溯来源与更新方式

- [U-Boot 四组构建分派（固定提交）](https://github.com/FlyFish-go/H3C-NX30-Uboot/blob/4019e5bff95d6f2061bdf25be387766c26ad6546/build-release.sh#L18-L21)、[v0.1.0-pre.1 实机验收范围](https://github.com/FlyFish-go/H3C-NX30-Uboot/blob/main/docs/VALIDATION.md)。
- [Product R1 r5 实测/勘误](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/blob/44d9667aec865ec1098c5910837ce292325736b6/rt3000-machine-b/release/RELEASE-NOTES-r5.md)、[RT3000 A/B/C 实物调查（历史快照）](https://github.com/FlyFish-go/H3C-RT3000-Product-R1/blob/main/docs/H3C-IPQ50xx-Hardware-Research-v1.0.md)。
- 本地研究底稿：2026-10-13 `projects/h3c-qsdk11.5/BOARD-MATRIX.md`（11 个内部 UID）、RC-A2/RT-B/RT-C/NX30 的原厂启动链离线记录、RT-C01 Native08 2026-10-05/06 有限实测、HW-D 2026-10-19 `build03` 冻结回执。这些本地记录**不是公开固件附件**。
- **维护建议：** 两仓共用四组定义，发布版本、芯片/NAND/ECC 和实机资格各自记账；更新某一 UID 的测试结果时不得自动扩大整个 HW 组适用范围。

[U-Boot 项目首页](https://github.com/FlyFish-go/H3C-NX30-Uboot) · [QSDK Product R1 项目首页](https://github.com/FlyFish-go/H3C-RT3000-Product-R1)
