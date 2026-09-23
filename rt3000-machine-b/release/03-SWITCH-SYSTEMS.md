# RT3000 刷机教程 · 第三部分：双向切换

[← 教程总览](INSTALL.md)

> **适用范围**：仅在 RT3000 Machine-B（`GD5F1GQ5REYIG` NAND、原厂软件版本 `RT3000V100R005`）验证。A/C 样机以及 RW3000、RC3000、NX30 请勿套用镜像或刷写命令；无法确认硬件时先停下。


> **本部分目标**：在 **QSDK** 和**原厂系统**之间来回切换。
>
> **前置条件**：已完成 [第二部分：安装 QSDK](02-INSTALL-QSDK.md)，设备上两个槽位都有系统。
>
> 本部分不重写两个系统槽位，但会修改 `mtd2`、`mtd3` 中的 BOOTCONFIG selector。
> 两个副本各有 4 个目标字节，工具会逐副本读改写并校验；仍须按本部分的检查执行。

---

## 目录

- [0. 先理解「切换」和「重装」的区别](#0-先理解切换和重装的区别)
- [1. 查看当前状态](#1-查看当前状态)
- [2. QSDK → 原厂](#2-qsdk-原厂)
- [3. 原厂 → QSDK](#3-原厂-qsdk)
- [4. 切换后网络会怎么变](#4-切换后网络会怎么变)
- [5. 验证清单](#5-验证清单)
- [常见问题](#常见问题)

---

## 0. 先理解「切换」和「重装」的区别

这两个操作**看起来结果一样**（都是从原厂变成 QSDK），但**代价完全不同**：

| | **切换**（本部分） | **重装**（第二部分） |
|---|---|---|
| 改什么 | 改两个 BOOTCONFIG 副本的 selector | 擦除并重写整个 `mtd16`（40 MB） |
| 耗时 | 修改 selector 通常几秒；重启另算 | 写入通常 1~2 分钟；重启另算 |
| 会丢配置吗 | 切换命令不清除配置；仍应在往返后核对 | ⚠️ 原有 QSDK 配置会被覆盖；保留配置升级见第四部分 |
| 会丢系统吗 | ❌ 两个系统都在 | ✅ 目标槽被覆盖 |
| 风险 | 低，但涉及 BOOTCONFIG 双副本写入 | 中（写入过程断电等） |
| 需要传文件吗 | QSDK → 原厂不需要；原厂 → QSDK 需传入 `rt3bcwrite` | ✅ 需要 |

**关键**：
> **两个系统一直同时存在于设备里**（`mtd15` 和 `mtd16`）。
> selector 只是告诉设备「下次启动哪一个」。

所以**来回切换是免费的** —— 不需要重新刷机。

---

## 1. 查看当前状态

### 1.1 在 QSDK 里查看

```sh
rt3slot status
```

**输出示例**：

```
runtime_system=QSDK
persistent_selector=1
next_boot_target=QSDK
bootconfig_copy_health=YES
oem_slot_status=PASS
qsdk_slot_status=PASS
running_slot=QSDK
RUNNING_SLOT=QSDK
RUNNING_RELEASE=Product R1 Upgrade Preview
RUNNING_KERNEL_ID=7a7c048e92bcd53bfdba554770195adbbaf4cf4deb0d383d4f3c85ba881c31c9
RUNNING_ROOTFS_ID=NOT_IN_MANIFEST
RELEASE_NETWORK_BASELINE=R1-NET-D
QSDK_SLOT_VALID=PASS
QSDK_SLOT_RELEASE=Product R1 Upgrade Preview
INACTIVE_CONTENT_VERIFY=UNSUPPORTED
oem_partition=mtd15:oem_rootfs
qsdk_partition=mtd16:rootfs
```

> **读输出时注意**：小写 `running_slot` 是工具历史字段，实际按 selector 推导，切换后尚未重启时可能表示**下次目标**。判断当前运行系统请看 `runtime_system`、大写 `RUNNING_SLOT`，并结合内核/挂载信息。示例中的 `RUNNING_ROOTFS_ID=NOT_IN_MANIFEST` 与 `INACTIVE_CONTENT_VERIFY=UNSUPPORTED` 也明确表示相关 rootfs 内容并未在这条状态命令中得到完整哈希验证；不能把 `PASS` 扩展成“所有载荷已验证”。

### 1.2 关键字段怎么读

| 字段 | 含义 | 关注点 |
|---|---|---|
| `RUNNING_SLOT` | **当前运行**的是哪个系统 | `QSDK` 或 `OEM` |
| `persistent_selector` | selector 的值 | `0`=原厂，`1`=QSDK |
| `next_boot_target` | **下次启动**会进哪个 | 切换后看这个 |
| `bootconfig_copy_health` | 两个副本是否一致 | 必须是 `YES` |
| `oem_slot_status` | 原厂分区的几何参数、名称和 UBI 头是否符合预期；**不校验完整载荷或能否启动** | `PASS` 才继续 |
| `qsdk_slot_status` | QSDK 槽的结构与实现所支持的内容校验状态；具体范围看详细字段 | `PASS` 才继续 |

> ⚠️ **如果 `oem_slot_status=FAIL`**，说明原厂槽可能有问题。
> **先不要切换**，把输出发出来确认。

### 1.3 单独校验某个槽位

```sh
rt3slot verify oem      # 检查原厂分区几何、名称及 UBI 头；不证明可启动
rt3slot verify qsdk     # 检查 QSDK 槽；结合详细字段判断载荷校验范围
```

**期望输出**：

```
OEM_SLOT_VERIFY=PASS
QSDK_SLOT_VERIFY=PASS
```

原厂 `PASS` 只是结构门槛，不读取 OEM kernel/rootfs 全部内容，也不保证原厂一定能启动。QSDK `PASS` 也应结合 `rt3slot status` 中的 `RUNNING_ROOTFS_ID`、`INACTIVE_CONTENT_VERIFY` 等字段解释；当输出 `NOT_IN_MANIFEST` 或 `UNSUPPORTED` 时，不能称为完整 rootfs 哈希验收。本教程安装阶段的 kernel/rootfs 完整读回校验见第二部分第 5.5 节。

---

## 2. QSDK → 原厂

> ⚠️ **必须在正在运行的 QSDK Linux shell 里操作**。通常用 SSH 或 TTYD；若网络管理服务不可用、手边有 TTL，也可以在串口确认出现 QSDK 的 `root@OpenWrt:/#` 提示符后操作。不要把 U-Boot 提示符当作 Linux shell。

### 2.1 连接 QSDK

```bash
ssh root@192.168.10.1
```

> 首次登录**密码为空**，直接回车。
> 如果你已经设过密码，用你设的。

**或者**用浏览器打开 TTYD 网页终端：

```
http://192.168.10.1:7681
```

若 SSH 和 TTYD 都连不上，先确认 LAN 地址和接线；有 TTL 时，可观察启动日志并确认已进入 QSDK 的 Linux shell。端口关闭本身不能说明设备已回到原厂。

### 2.2 执行切换

```sh
rt3slot oem --reboot
```

**这一条命令做了三件事**：
1. **先检查原厂分区结构门槛**（失败会拒绝切换；通过不等于证明原厂能启动）
2. 改 selector 指向原厂
3. **自动重启**

### 2.3 期望输出

```
PRE  mtd3(0:BOOTCONFIG1) = 0x00000001
PRE  mtd2(0:BOOTCONFIG) = 0x00000001
copy=mtd3 FIRST (redundant)
copy=mtd3 write=PASS verify=PASS
copy=mtd2 SECOND (primary)
copy=mtd2 write=PASS verify=PASS
POST mtd3(0:BOOTCONFIG1) = 0x00000000
POST mtd2(0:BOOTCONFIG) = 0x00000000
final_selector=0x00000000
RESULT=PASS both copies = 0x00000000
VERIFY_ONLY want=0x00000000 -> PASS
SWITCH_RESULT=PASS
next_boot_target=OEM
```

**然后设备自动重启。**

### 2.4 关键行解读

| 输出 | 含义 |
|---|---|
| `copy=mtd3 write=PASS verify=PASS` | 副本一：**写完立即读回校验**，通过 |
| `copy=mtd2 write=PASS verify=PASS` | 副本二：同样 |
| `RESULT=PASS both copies = 0x00000000` | 两个副本都指向原厂（0） |
| `SWITCH_RESULT=PASS` | **切换成功** |

> 🛑 **如果看到 `RESULT=FAIL`**：selector 写入未完整通过校验。
> `rt3slot` 在报告成功前不会执行 `--reboot` 请求；不要自行重启。
> 保留完整输出，并在仍可访问的系统里查看 `rt3slot status`。

### 2.5 不想自动重启？

```sh
rt3slot oem
```

（不带 `--reboot`）—— 只改 selector，**不重启**。

**注意**：这样设备**还在运行 QSDK**，只是「下次启动会进原厂」。
你可以稍后手动重启：

```sh
reboot
```

---

## 3. 原厂 → QSDK

> ⚠️ **必须在原厂系统里操作**（用 telnet）。

**这里比上一节多一步** —— 因为**原厂固件里没有 `rt3bcwrite` 工具**。

### 3.1 连接原厂

**先用第 2 节的方法切到原厂**，然后：

```bash
telnet <原厂的IP>
```

**原厂 IP 怎么找**？用第一部分第 2 节的方法（按 MAC 扫描）。

> 📌 **提醒**：切到原厂后，`192.168.10.1` 会消失，
> 管理地址变成**上游路由器分配**的那个（如 `192.168.1.200`）。

登录：
- 密码：`admin`（或贴纸上的 WiFi 密码）

进去后：

```
<H3C_RT3000>debugshell
```

### 3.2 传入 `rt3bcwrite`

**原厂里没有这个工具，需要先传进去。**
`/tmp` 是内存盘，每次重启都会清空；即使第二部分安装时传过，下一次从原厂回切仍需重新下载并校验。
这一步只写临时文件，不会重装 `mtd16`。

**在电脑上起文件服务器**。复用第二部分的工具目录，保留镜像文件供脚本检查；
**这次设备只下载 `rt3bcwrite`，不下载或写入镜像**：

```
D:\RT3000\
├── 1-启动文件服务器.bat
├── rt3bcwrite
└── r5-factory.ubi
```

**双击运行**（管理员身份），记下它打印的 IP。脚本还会打印镜像下载命令；
本节不要执行那一行。

**在设备的 telnet 窗口里**：

```sh
cd /tmp
wget http://<电脑IP>:8899/rt3bcwrite -O /tmp/rt3bcwrite
chmod +x /tmp/rt3bcwrite
```

**校验**：

```sh
sha256sum /tmp/rt3bcwrite
```

**必须是**：

```
e23d8634af3fb20a5c383aa22ad2dc65752133ffd91d3715a70df5121d0789f5
```

> ❌ **不一致就别继续** —— 重新下载。

### 3.3 ⚠️ 原厂里必须加前缀

**这是一定会踩的坑**：

```sh
$ /tmp/rt3bcwrite --show
/bin/sh: /tmp/rt3bcwrite: not found     ← 报「找不到」
```

**其实文件在**，是**加载器名字不匹配**：

| | 加载器 |
|---|---|
| 我们的工具需要 | `/lib/ld-musl-armhf.so.1`（带 `hf`） |
| 原厂提供 | `/lib/ld-musl-arm.so.1`（**不带 `hf`**） |

**解决**：显式指定原厂的加载器：

```sh
/lib/ld-musl-arm.so.1 /tmp/rt3bcwrite --show
```

> 📌 **在原厂里的每一条 `rt3bcwrite` 命令都要加这个前缀。**
> （QSDK 里不需要 —— 加载器名字是对的。）

### 3.4 确认当前在原厂槽

```sh
/lib/ld-musl-arm.so.1 /tmp/rt3bcwrite --show
```

**期望**：

```
mtd3(0:BOOTCONFIG1) rootfs selector = 0x00000000
mtd2(0:BOOTCONFIG) rootfs selector = 0x00000000
copies_agree=YES
current_slot=A(rootfs/OEM)
```

### 3.5 切换到 QSDK

```sh
/lib/ld-musl-arm.so.1 /tmp/rt3bcwrite --set 1
```

**期望输出**：

```
PRE  mtd3(0:BOOTCONFIG1) = 0x00000000
PRE  mtd2(0:BOOTCONFIG) = 0x00000000
copy=mtd3 FIRST (redundant)
copy=mtd3 write=PASS verify=PASS
copy=mtd2 SECOND (primary)
copy=mtd2 write=PASS verify=PASS
POST mtd3(0:BOOTCONFIG1) = 0x00000001
POST mtd2(0:BOOTCONFIG) = 0x00000001
final_selector=0x00000001
RESULT=PASS both copies = 0x00000001
```

> 🛑 **必须是 `RESULT=PASS`。** 如果是 `FAIL`，**不要重启**，把输出发出来。

### 3.6 确认并重启

```sh
/lib/ld-musl-arm.so.1 /tmp/rt3bcwrite --show
```

**期望**：

```
copies_agree=YES
current_slot=B(rootfs_1/QSDK)
```

然后：

```sh
sync
reboot
```

---

## 4. 切换后网络会怎么变

**这是最容易让人以为「刷坏了」的地方。**

| 项 | QSDK 时 | 原厂时 |
|---|---|---|
| **LAN 管理地址** | **`192.168.10.1`** | **上游路由器分配的地址**（如 `192.168.1.200`） |
| 22 (SSH) | ✅ | ❌ |
| 23 (telnet) | ❌ | ✅ |
| 80 (网页) | ✅ LuCI | ✅ H3C 后台 |
| 443 | ❌ | ✅ |
| 7681 (网页终端) | ✅ | ❌ |

### 4.1 为什么会这样

| 系统 | 网络模式 |
|---|---|
| **QSDK** | 路由模式，自己管 LAN 网段（`192.168.10.1`），管理口**只绑 LAN** |
| **原厂（恢复出厂后）** | **有线桥接**，LAN 口和上游同一网段，管理地址由上游 DHCP 分配 |

### 4.2 ⚠️ 重要：网线要插在 LAN 口

**QSDK 的管理口只绑 LAN 侧。** 所以：

```
❌ 电脑接在 WAN 侧（和上游路由器一起）
   → 访问不了 QSDK 的 192.168.10.1

✅ 电脑接在 RT3000 的 LAN 口
   → 能访问 QSDK（拿到 192.168.10.x）
   → 切到原厂后，也能访问（拿到 192.168.1.x）
```

**推荐接线**：

```
   上游路由器
       │
   ┌───┴────┐
   │ RT3000 │
   │ WAN 口 │ ← 接上游
   │ LAN 口 │ ← 接电脑 ⭐
   └────────┘
```

**这样接，两种系统下都能访问设备，不用拔线。**

### 4.3 如何自动找到设备

因为地址会变，**建议按 MAC 地址找**：

```bash
# Linux / macOS
arp -a | grep -i "58:b3:8f"

# Windows
arp -a | findstr "58-b3-8f"
```

**RT3000 的 MAC 以 `58:B3:8F` 开头。**

---

## 5. 验证清单

切换后，确认以下几点：

### 5.1 切到原厂后

```sh
# 1. 找到原厂 IP（按 MAC 扫）
# 2. 确认端口
#    23 / 80 / 443 应该是 OPEN
# 3. telnet 进去，确认是原厂
```

telnet 进去后能执行 `debugshell` 并看到：

```
   For those about to rock... (Chaos Calmer, unknown)     ← Chaos Calmer = 原厂
 -----------------------------------------------------
root@OpenWrt:/#
```

```sh
uname -r
# 期望: 4.4.60         ← 原厂内核
```

### 5.2 切到 QSDK 后

```sh
ssh root@192.168.10.1

uname -r                    # 5.4.164
rt3slot status              # RUNNING_SLOT=QSDK
rt3slot verify oem          # OEM_SLOT_VERIFY=PASS
rt3slot verify qsdk         # QSDK_SLOT_VERIFY=PASS
```

### 5.3 配置是否保留

**两个系统的配置是独立的**，各自保留：

- QSDK 的配置在 `mtd16` 的 `rootfs_data` 卷里
- 原厂的配置在它自己的存储里

切换命令只更新启动目标，不执行配置清除。2026-09-22 的实机往返中，
QSDK 的标记文件及三个配置文件在切换前后哈希一致；
原厂侧当时使用的标记文件位于 `/tmp`，重启即失，**不能**作为原厂持久配置逐字节保留的证据。
本轮重新进入原厂后，已确认此前开启的 telnet 仍可使用，这是原厂设置保留的一个实际观察。
需要证明某个具体设置时，应在切换前后读取该设置并比对；不要把一项观察推广为所有配置逐字节不变。

例如，在 QSDK 离开前记录下面三项的哈希与大小，并把结果保存到电脑；
切回 QSDK 后在相同路径重做一次，比对每个文件。无需展示配置正文或 WiFi 密码。

```sh
wc -c /etc/config/network /etc/config/wireless /etc/config/dhcp
sha256sum /etc/config/network /etc/config/wireless /etc/config/dhcp
```

如需核对原厂设置，切换前后检查同一个持久设置；只看到原厂 `/tmp` 文件存在，不能证明重启后保留。

### 5.4 怎么确认「切换」没有重写固件

**先说清楚：没有任何单一检查能证明「整个槽位一个字节都没变」。**
下面给两个方法，各自能说明什么、不能说明什么，都写明白。

#### 方法 A：检查 UBI 镜像序列号（快速，但证明力很弱）

**切换前后分别执行**：

```sh
dd if=/dev/mtd16 bs=1 skip=24 count=4 2>/dev/null | hexdump -C
```

**两次输出应该相同**（例如 `7b a5 a2 b2`）。

> ✅ **能说明的**：**本次读取的这个字段，前后两次读到的值相同。**
>
> ❌ **不能说明的**（重要）：
> - ❌ 不能证明「该擦除块未被重新格式化」——
>   **值相同并不排除「被重写过、但写回了相同内容」**。
> - ❌ 更不能证明「其它 319 个擦除块未变」。
>
> 📌 **准确的说法**：这只是「该字段在两次读取之间没有变化」的记录。
> **它既不是「未重写」的证明，也不是完整性的证明。**
>
> **不要用它来下「固件没被动过」的结论。**

#### 方法 B：固件载荷哈希比对（慢，但范围明确）

**如果要核对 QSDK 的 kernel/rootfs 有效载荷是否改变**，可在原厂系统里先按第二部分 §5.5
读取 `mtd16` 的 kernel/rootfs 卷并记录哈希；完成「原厂 → QSDK → 原厂」往返后，
在**同一个原厂环境**里用相同卷、相同长度再读一次。
这需要两次读回操作。第二部分 §5.5 的 OEM 命令序列已于 2026-09-23 实机走通。
两项哈希一致只能证明所读的有效载荷一致，不能证明 `mtd16` 的每个字节都未改变。

> ⚠️ **注意**：
> - 直接对 `/dev/mtd16` 做 `sha256sum`（裸分区）不适合代替载荷校验：
>   UBI 的擦除计数和空闲区域也会参与哈希，前后值不同不能直接说明固件载荷变了。
> - **要比较就必须使用相同的卷和载荷长度**；往返重启后，UBI 设备号可能变化，
>   每次都要重新确认 `mtd16` 对应的 `ubiN`，不能照抄旧设备节点。
>
> 💡 **实用建议**：多数人不需要重复做载荷哈希比对。
>
> **要判断「切换是不是轻量操作」，更可靠的依据是**：
> - `rt3bcwrite` 对两个 BOOTCONFIG 副本逐个写入和读回校验
> - 切换前后对需要保留的具体配置逐项比对（见 5.3 节）
> - 切换过程不执行 `ubiformat`，无需重新写入整槽固件
>
> **而不是**上面那个字段比对。

---

## 常见问题

### Q1: `rt3slot: not found`

**原因**：你在**原厂系统**里。原厂没有这个工具。

**解决**：原厂里没有 `rt3slot`，只能用 `rt3bcwrite`（见第 3 节）。

---

### Q2: 切到原厂后完全连不上

**排查顺序**：

| 检查 | 方法 |
|---|---|
| 1. 网线插在 LAN 口吗 | 见 4.2 节 |
| 2. 电脑拿到 IP 了吗 | `ipconfig` / `ip addr`，看是不是 `192.168.10.x` 或 `192.168.1.x` |
| 3. 设备起来了吗 | 等 1~2 分钟（原厂启动要 1 分钟以上） |
| 4. 按 MAC 找设备 | 见 4.3 节 |

**最可能的原因**：网线插在 WAN 侧，而 QSDK/原厂的管理口在 LAN 侧。

---

### Q3: 切到原厂后 23 端口不通

**可能**：
1. 设备的 telnet 没开（例如原厂配置曾被恢复出厂或导入了关闭 telnet 的备份）
2. 还在启动中

**解决**：重新用第一部分的方法开一次 telnet。

---

### Q4: 原厂里 `wget` 下载失败

**排查**：

1. 电脑上的文件服务器窗口还开着吗？
2. 电脑 IP 填对了吗？（用脚本打印的那个）
3. 设备能 ping 通电脑吗？

```sh
ping <电脑IP>
```

---

### Q5: 我能不能只用网页后台切换？

**不能。**

- 原厂后台**没有**切换槽位的功能
- QSDK 的 LuCI **默认也没有**（`rt3slot` 是命令行工具）

**所以切换需要命令行。** 但只有一条命令，不算复杂。

---

### Q6: 切换会不会影响另一边的配置？

**不会。** 两边的配置**完全独立**：

| 系统 | 配置存放位置 |
|---|---|
| QSDK | `mtd16` 里的 `rootfs_data` 卷 |
| 原厂 | 原厂自己的存储 |

切换命令不执行配置清除或固件槽位重写。启动后的系统仍可能正常写入自己的日志和运行数据。

---

### Q7: 我想让设备默认进原厂

```sh
rt3slot oem
```

（**不带** `--reboot`）—— 只改 selector，不立即重启。
下次设备启动（无论什么原因）就会进原厂。

---

### Q8: 两个系统能同时运行吗？

**不能。** 同一时刻只有一个在运行。

selector 决定**下次启动**用哪个 —— 类似电脑的「双系统启动项」。

---

### Q9: 切换失败（`RESULT=FAIL`）怎么办

**先不要重启。** 把完整输出记下来。

**如果已经重启了**：

1. 等待启动完成
2. 先确认运行的是哪个系统；若仍在 QSDK，用 `rt3slot status` 看当前状态
3. 如果还在能用的系统里 → 保留输出，核对两个 BOOTCONFIG 副本和目标槽状态，再决定下一步；不要盲目重试
4. 如果起不来 → 见[第五部分：救援](05-RECOVERY.md)

> selector 有**两个副本**，写入工具会分别校验；`RESULT=FAIL` 仍需按实际副本状态处理。
> 本方案不写原厂槽 `mtd15`，但槽位内容保留并不保证此刻一定能启动原厂。
>
> ⚠️ **但「内容还在」不等于「一定能启动它」** ——
> 如果两边都起不来，需要串口救援（见[第五部分](05-RECOVERY.md)）。

---

## ✅ 本部分完成

你现在可以：

| 操作 | 命令 | 在哪执行 |
|---|---|---|
| 看状态 | `rt3slot status` | QSDK |
| **切到原厂** | `rt3slot oem --reboot` | QSDK |
| **切到 QSDK** | `/lib/ld-musl-arm.so.1 /tmp/rt3bcwrite --set 1` | 原厂 |

---

## 下一步

- **固件升级**：更新 QSDK 版本
- **救援**：出问题怎么办
