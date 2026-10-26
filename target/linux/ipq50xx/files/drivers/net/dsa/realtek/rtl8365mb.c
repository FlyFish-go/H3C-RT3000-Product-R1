// SPDX-License-Identifier: GPL-2.0
/* Realtek SMI subdriver for the Realtek RTL8365MB-VC ethernet switch.
 *
 * Copyright (C) 2021 Alvin Šipraga <alsi@bang-olufsen.dk>
 * Copyright (C) 2021 Michael Rasmussen <mir@bang-olufsen.dk>
 *
 * The RTL8365MB-VC is a 4+1 port 10/100/1000M switch controller. It includes 4
 * integrated PHYs for the user facing ports, and an extension interface which
 * can be connected to the CPU - or another PHY - via either MII, RMII, or
 * RGMII. The switch is configured via the Realtek Simple Management Interface
 * (SMI), which uses the MDIO/MDC lines.
 *
 * Below is a simplified block diagram of the chip and its relevant interfaces.
 *
 *                          .-----------------------------------.
 *                          |                                   |
 *         UTP <---------------> Giga PHY <-> PCS <-> P0 GMAC   |
 *         UTP <---------------> Giga PHY <-> PCS <-> P1 GMAC   |
 *         UTP <---------------> Giga PHY <-> PCS <-> P2 GMAC   |
 *         UTP <---------------> Giga PHY <-> PCS <-> P3 GMAC   |
 *                          |                                   |
 *     CPU/PHY <-MII/RMII/RGMII--->  Extension  <---> Extension |
 *                          |       interface 1        GMAC 1   |
 *                          |                                   |
 *     SMI driver/ <-MDC/SCL---> Management    ~~~~~~~~~~~~~~   |
 *        EEPROM   <-MDIO/SDA--> interface     ~REALTEK ~~~~~   |
 *                          |                  ~RTL8365MB ~~~   |
 *                          |                  ~GXXXC TAIWAN~   |
 *        GPIO <--------------> Reset          ~~~~~~~~~~~~~~   |
 *                          |                                   |
 *      Interrupt  <----------> Link UP/DOWN events             |
 *      controller          |                                   |
 *                          '-----------------------------------'
 *
 * The driver uses DSA to integrate the 4 user and 1 extension ports into the
 * kernel. Netdevices are created for the user ports, as are PHY devices for
 * their integrated PHYs. The device tree firmware should also specify the link
 * partner of the extension port - either via a fixed-link or other phy-handle.
 * See the device tree bindings for more detailed information. Note that the
 * driver has only been tested with a fixed-link, but in principle it should not
 * matter.
 *
 * NOTE: Currently, only the RGMII interface is implemented in this driver.
 *
 * The interrupt line is asserted on link UP/DOWN events. The driver creates a
 * custom irqchip to handle this interrupt and demultiplex the events by reading
 * the status registers via SMI. Interrupts are then propagated to the relevant
 * PHY device.
 *
 * The EEPROM contains initial register values which the chip will read over I2C
 * upon hardware reset. It is also possible to omit the EEPROM. In both cases,
 * the driver will manually reprogram some registers using jam tables to reach
 * an initial state defined by the vendor driver.
 *
 * This Linux driver is written based on an OS-agnostic vendor driver from
 * Realtek. The reference GPL-licensed sources can be found in the OpenWrt
 * source tree under the name rtl8367c. The vendor driver claims to support a
 * number of similar switch controllers from Realtek, but the only hardware we
 * have is the RTL8365MB-VC. Moreover, there does not seem to be any chip under
 * the name RTL8367C. Although one wishes that the 'C' stood for some kind of
 * common hardware revision, there exist examples of chips with the suffix -VC
 * which are explicitly not supported by the rtl8367c driver and which instead
 * require the rtl8367d vendor driver. With all this uncertainty, the driver has
 * been modestly named rtl8365mb. Future implementors may wish to rename things
 * accordingly.
 *
 * In the same family of chips, some carry up to 8 user ports and up to 2
 * extension ports. Where possible this driver tries to make things generic, but
 * more work must be done to support these configurations. According to
 * documentation from Realtek, the family should include the following chips:
 *
 *  - RTL8363NB
 *  - RTL8363NB-VB
 *  - RTL8363SC
 *  - RTL8363SC-VB
 *  - RTL8364NB
 *  - RTL8364NB-VB
 *  - RTL8365MB-VC
 *  - RTL8366SC
 *  - RTL8367RB-VB
 *  - RTL8367SB
 *  - RTL8367S
 *  - RTL8370MB
 *  - RTL8310SR
 *
 * Some of the register logic for these additional chips has been skipped over
 * while implementing this driver. It is therefore not possible to assume that
 * things will work out-of-the-box for other chips, and a careful review of the
 * vendor driver may be needed to expand support. The RTL8365MB-VC seems to be
 * one of the simpler chips.
 */

#include <linux/bitfield.h>
#include <linux/bitops.h>
#include <linux/ctype.h>
#include <linux/interrupt.h>
#include <linux/irqdomain.h>
#include <linux/ktime.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/slab.h>
#include <linux/regmap.h>
#include <linux/rtnetlink.h>
#include <linux/sort.h>
#include <linux/workqueue.h>
#include <linux/if_bridge.h>
#include <linux/mii.h>
#include <net/switchdev.h>

#include "realtek.h"
#include "rtl8367s_uc_offload.h"
#include "rtl8367s_uc_fdb_sync.h"

/* Chip-specific data and limits */
#define RTL8365MB_CHIP_ID_8365MB_VC	0x6367
#define RTL8365MB_CHIP_VER_8365MB_VC	0x0040

#define RTL8365MB_CHIP_ID_8367S		0x6367
#define RTL8365MB_CHIP_VER_8367S	0x00A0

/* One-shot, RAM-only Machine-C LUT age calibration; disabled by default. */
static bool rtl8365mb_rt3000_age_calibration;
module_param_named(rt3000_age_calibration,
		   rtl8365mb_rt3000_age_calibration, bool, 0);
MODULE_PARM_DESC(rt3000_age_calibration,
		 "Apply the guarded Machine-C RTL8367S LUT age calibration at setup");

#define RTL8367S_UC_FDB_SYNC_MAX_ROWS	4096
#define RTL8367S_UC_FDB_SYNC_INTERVAL	(5 * HZ)

/*
 * Read-only LUT aging diagnostic for RTL8367S (0x6367:0x00a0). The
 * vendor SDK maps chip ID 0x6367 to its RTL8367C control path and defines
 * this register and fields in
 * target/linux/mediatek/files-5.4/drivers/net/phy/rtk/rtl8367c/include/rtl8367c_reg.h
 * (RTL8367C_REG_LUT_CFG, speed [9:8], timer [2:0]).
 */
#define RTL8367S_LUT_AGE_CFG_REG	0x0a30

#define RTL8365MB_CHIP_ID_8367RB	0x6367
#define RTL8365MB_CHIP_VER_8367RB	0x0020

/* Family-specific data and limits */
#define RTL8365MB_PHYADDRMAX		7
#define RTL8365MB_NUM_PHYREGS		32
#define RTL8365MB_PHYREGMAX		(RTL8365MB_NUM_PHYREGS - 1)
/* RTL8370MB and RTL8310SR, possibly suportable by this driver, have 10 ports */
#define RTL8365MB_MAX_NUM_PORTS		10
#define RTL8365MB_LEARN_LIMIT_MAX	2112

/* valid for all 6-port or less variants */
static const int rtl8365mb_extint_port_map[]  = { -1, -1, -1, -1, -1, -1, 1, 2, -1, -1};

/* Chip identification registers */
#define RTL8365MB_CHIP_ID_REG		0x1300

#define RTL8365MB_CHIP_VER_REG		0x1301

#define RTL8365MB_MAGIC_REG		0x13C2
#define   RTL8365MB_MAGIC_VALUE		0x0249

/* Chip reset register */
#define RTL8365MB_CHIP_RESET_REG	0x1322
#define RTL8365MB_CHIP_RESET_SW_MASK	0x0002
#define RTL8365MB_CHIP_RESET_HW_MASK	0x0001
#define RTL8365MB_CHIP_RESET_DW8051_MASK	0x0010

/* RTL8367S SerDes registers used by the upstream SGMII implementation. */
#define RTL8365MB_BYPASS_LINE_RATE_REG		0x03F7
#define RTL8365MB_SDS_BYPASS_LINE_RATE_MASK	BIT(1) /* external port 6 */
#define RTL8365MB_SDS_INDACS_CMD_REG		0x6600
#define RTL8365MB_SDS_INDACS_CMD_BUSY_MASK	0x0100
#define RTL8365MB_SDS_INDACS_CMD_RUN_MASK	0x0080
#define RTL8365MB_SDS_INDACS_CMD_WR_MASK	0x0040
#define RTL8365MB_SDS_INDACS_ADR_REG		0x6601
#define RTL8365MB_SDS_INDACS_DATA_REG		0x6602
#define RTL8365MB_SDS_MISC_REG			0x1D11
#define RTL8365MB_SDS_MISC_SGMII_TXFC_MASK	0x2000
#define RTL8365MB_SDS_MISC_SGMII_FDUP_MASK	0x0400
#define RTL8365MB_SDS_MISC_SGMII_LINK_MASK	0x0200
#define RTL8365MB_SDS_MISC_SGMII_SPD_MASK	0x0180
#define RTL8365MB_SDS_MISC_MAC8_SEL_HSGMII_MASK	0x0800
#define RTL8365MB_SDS_MISC_MAC8_SEL_SGMII_MASK	0x0040
#define RTL8365MB_SDS_REG_BMCR			0x0000
#define RTL8365MB_SDS_BMCR_DPRST_PHASE1	(BMCR_ANENABLE | BMCR_ISOLATE | 0x1)
#define RTL8365MB_SDS_BMCR_DPRST_PHASE2	(BMCR_ANENABLE | BMCR_ISOLATE | 0x3)
#define RTL8365MB_SDS_REG_NWAY			0x0002
#define RTL8365MB_SDS_NWAY_EN_MASK		0x0200
#define RTL8365MB_SDS_NWAY_RESTART_MASK	0x0100
#define RTL8365MB_SDS_REG_RESET			0x0003
#define RTL8365MB_SDS_RESET_DEASSERT		0x7106
#define RTL8365MB_SDS_OPTION_ARM_REG		0x13C0
#define RTL8365MB_SDS_OPTION_ARM_KEY		0x0249
#define RTL8365MB_SDS_OPTION_REG		0x13C1
#define RTL8365MB_MISC_CFG0_REG			0x130C
#define RTL8365MB_MISC_CFG0_DW8051_EN_MASK	0x0020
#define RTL8365MB_DW8051_RDY_REG		0x1336
#define RTL8365MB_DW8051_ACS_IROM_ENABLE_MASK	0x0002
#define RTL8365MB_DW8051_IROM_MSB_MASK		0x000C
#define RTL8365MB_SDS_HSGMII_FW_BASE		0xE000
#define RTL8365MB_SDS_EXT_INTERFACE_ID		1

/* Interrupt polarity register */
#define RTL8365MB_INTR_POLARITY_REG	0x1100
#define   RTL8365MB_INTR_POLARITY_MASK	0x0001
#define   RTL8365MB_INTR_POLARITY_HIGH	0
#define   RTL8365MB_INTR_POLARITY_LOW	1

/* Interrupt control/status register - enable/check specific interrupt types */
#define RTL8365MB_INTR_CTRL_REG			0x1101
#define RTL8365MB_INTR_STATUS_REG		0x1102
#define   RTL8365MB_INTR_SLIENT_START_2_MASK	0x1000
#define   RTL8365MB_INTR_SLIENT_START_MASK	0x0800
#define   RTL8365MB_INTR_ACL_ACTION_MASK	0x0200
#define   RTL8365MB_INTR_CABLE_DIAG_FIN_MASK	0x0100
#define   RTL8365MB_INTR_INTERRUPT_8051_MASK	0x0080
#define   RTL8365MB_INTR_LOOP_DETECTION_MASK	0x0040
#define   RTL8365MB_INTR_GREEN_TIMER_MASK	0x0020
#define   RTL8365MB_INTR_SPECIAL_CONGEST_MASK	0x0010
#define   RTL8365MB_INTR_SPEED_CHANGE_MASK	0x0008
#define   RTL8365MB_INTR_LEARN_OVER_MASK	0x0004
#define   RTL8365MB_INTR_METER_EXCEEDED_MASK	0x0002
#define   RTL8365MB_INTR_LINK_CHANGE_MASK	0x0001
#define   RTL8365MB_INTR_ALL_MASK                      \
		(RTL8365MB_INTR_SLIENT_START_2_MASK |  \
		 RTL8365MB_INTR_SLIENT_START_MASK |    \
		 RTL8365MB_INTR_ACL_ACTION_MASK |      \
		 RTL8365MB_INTR_CABLE_DIAG_FIN_MASK |  \
		 RTL8365MB_INTR_INTERRUPT_8051_MASK |  \
		 RTL8365MB_INTR_LOOP_DETECTION_MASK |  \
		 RTL8365MB_INTR_GREEN_TIMER_MASK |     \
		 RTL8365MB_INTR_SPECIAL_CONGEST_MASK | \
		 RTL8365MB_INTR_SPEED_CHANGE_MASK |    \
		 RTL8365MB_INTR_LEARN_OVER_MASK |      \
		 RTL8365MB_INTR_METER_EXCEEDED_MASK |  \
		 RTL8365MB_INTR_LINK_CHANGE_MASK)

/* Per-port interrupt type status registers */
#define RTL8365MB_PORT_LINKDOWN_IND_REG		0x1106
#define   RTL8365MB_PORT_LINKDOWN_IND_MASK	0x07FF

#define RTL8365MB_PORT_LINKUP_IND_REG		0x1107
#define   RTL8365MB_PORT_LINKUP_IND_MASK	0x07FF

/* PHY indirect access registers */
#define RTL8365MB_INDIRECT_ACCESS_CTRL_REG			0x1F00
#define   RTL8365MB_INDIRECT_ACCESS_CTRL_RW_MASK		0x0002
#define   RTL8365MB_INDIRECT_ACCESS_CTRL_RW_READ		0
#define   RTL8365MB_INDIRECT_ACCESS_CTRL_RW_WRITE		1
#define   RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_MASK		0x0001
#define   RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_VALUE		1
#define RTL8365MB_INDIRECT_ACCESS_STATUS_REG			0x1F01
#define RTL8365MB_INDIRECT_ACCESS_ADDRESS_REG			0x1F02
#define   RTL8365MB_INDIRECT_ACCESS_ADDRESS_OCPADR_5_1_MASK	GENMASK(4, 0)
#define   RTL8365MB_INDIRECT_ACCESS_ADDRESS_PHYNUM_MASK		GENMASK(7, 5)
#define   RTL8365MB_INDIRECT_ACCESS_ADDRESS_OCPADR_9_6_MASK	GENMASK(11, 8)
#define   RTL8365MB_PHY_BASE					0x2000
#define RTL8365MB_INDIRECT_ACCESS_WRITE_DATA_REG		0x1F03
#define RTL8365MB_INDIRECT_ACCESS_READ_DATA_REG			0x1F04

/* PHY OCP address prefix register */
#define RTL8365MB_GPHY_OCP_MSB_0_REG			0x1D15
#define   RTL8365MB_GPHY_OCP_MSB_0_CFG_CPU_OCPADR_MASK	0x0FC0
#define RTL8365MB_PHY_OCP_ADDR_PREFIX_MASK		0xFC00

/* The PHY OCP addresses of PHY registers 0~31 start here */
#define RTL8365MB_PHY_OCP_ADDR_PHYREG_BASE		0xA400

/* EXT interface port mode values - used in DIGITAL_INTERFACE_SELECT */
#define RTL8365MB_EXT_PORT_MODE_DISABLE		0
#define RTL8365MB_EXT_PORT_MODE_RGMII		1
#define RTL8365MB_EXT_PORT_MODE_MII_MAC		2
#define RTL8365MB_EXT_PORT_MODE_MII_PHY		3
#define RTL8365MB_EXT_PORT_MODE_TMII_MAC	4
#define RTL8365MB_EXT_PORT_MODE_TMII_PHY	5
#define RTL8365MB_EXT_PORT_MODE_GMII		6
#define RTL8365MB_EXT_PORT_MODE_RMII_MAC	7
#define RTL8365MB_EXT_PORT_MODE_RMII_PHY	8
#define RTL8365MB_EXT_PORT_MODE_SGMII		9
#define RTL8365MB_EXT_PORT_MODE_HSGMII		10
#define RTL8365MB_EXT_PORT_MODE_1000X_100FX	11
#define RTL8365MB_EXT_PORT_MODE_1000X		12
#define RTL8365MB_EXT_PORT_MODE_100FX		13

/* Realtek docs and driver uses logic number as EXT_PORT0=16, EXT_PORT1=17,
 * EXT_PORT2=18, to interact with switch ports. That logic number is internally
 * converted to either a physical port number (0..9) or an external interface id (0..2),
 * depending on which function was called. The external interface id is calculated as
 * (ext_id=logic_port-15), while the logical to physical map depends on the chip id/version.
 *
 * EXT_PORT0 mentioned in datasheets and rtl8367c driver is used in this driver
 * as extid==1, EXT_PORT2, mentioned in Realtek rtl8367c driver for 10-port switches,
 * would have an ext_id of 3 (out of range for most extint macros) and ext_id 0 does
 * not seem to be used as well for this family.
 */

/* EXT interface mode configuration registers 0~1 */
#define RTL8365MB_DIGITAL_INTERFACE_SELECT_REG0		0x1305 /* EXT1 */
#define RTL8365MB_DIGITAL_INTERFACE_SELECT_REG1		0x13C3 /* EXT2 */
#define RTL8365MB_DIGITAL_INTERFACE_SELECT_REG(_extint) \
		((_extint) == 1 ? RTL8365MB_DIGITAL_INTERFACE_SELECT_REG0 : \
		 (_extint) == 2 ? RTL8365MB_DIGITAL_INTERFACE_SELECT_REG1 : \
		 0x0)
#define   RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_MASK(_extint) \
		(0xF << (((_extint) % 2) * 4))
#define   RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_OFFSET(_extint) \
		(((_extint) % 2) * 4)

/* EXT interface RGMII TX/RX delay configuration registers 0~2 */
#define RTL8365MB_EXT_RGMXF_REG0		0x1306 /* EXT0 */
#define RTL8365MB_EXT_RGMXF_REG1		0x1307 /* EXT1 */
#define RTL8365MB_EXT_RGMXF_REG2		0x13C5 /* EXT2 */
#define RTL8365MB_EXT_RGMXF_REG(_extint) \
		((_extint) == 0 ? RTL8365MB_EXT_RGMXF_REG0 : \
		 (_extint) == 1 ? RTL8365MB_EXT_RGMXF_REG1 : \
		 (_extint) == 2 ? RTL8365MB_EXT_RGMXF_REG2 : \
		 0x0)
#define   RTL8365MB_EXT_RGMXF_RXDELAY_MASK	0x0007
#define   RTL8365MB_EXT_RGMXF_TXDELAY_MASK	0x0008

/* External interface port speed values - used in DIGITAL_INTERFACE_FORCE */
#define RTL8365MB_PORT_SPEED_10M	0
#define RTL8365MB_PORT_SPEED_100M	1
#define RTL8365MB_PORT_SPEED_1000M	2

/* EXT interface force configuration registers 0~2 */
#define RTL8365MB_DIGITAL_INTERFACE_FORCE_REG0		0x1310 /* EXT0 */
#define RTL8365MB_DIGITAL_INTERFACE_FORCE_REG1		0x1311 /* EXT1 */
#define RTL8365MB_DIGITAL_INTERFACE_FORCE_REG2		0x13C4 /* EXT2 */
#define RTL8365MB_DIGITAL_INTERFACE_FORCE_REG(_extint) \
		((_extint) == 0 ? RTL8365MB_DIGITAL_INTERFACE_FORCE_REG0 : \
		 (_extint) == 1 ? RTL8365MB_DIGITAL_INTERFACE_FORCE_REG1 : \
		 (_extint) == 2 ? RTL8365MB_DIGITAL_INTERFACE_FORCE_REG2 : \
		 0x0)
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_EN_MASK		0x1000
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_NWAY_MASK		0x0080
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_TXPAUSE_MASK	0x0040
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_RXPAUSE_MASK	0x0020
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_LINK_MASK		0x0010
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_DUPLEX_MASK		0x0004
#define   RTL8365MB_DIGITAL_INTERFACE_FORCE_SPEED_MASK		0x0003

/* CPU port mask register - controls which ports are treated as CPU ports */
#define RTL8365MB_CPU_PORT_MASK_REG	0x1219
#define   RTL8365MB_CPU_PORT_MASK_MASK	0x07FF

/* CPU control register */
#define RTL8365MB_CPU_CTRL_REG			0x121A
#define   RTL8365MB_CPU_CTRL_TRAP_PORT_EXT_MASK	0x0400
#define   RTL8365MB_CPU_CTRL_TAG_FORMAT_MASK	0x0200
#define   RTL8365MB_CPU_CTRL_RXBYTECOUNT_MASK	0x0080
#define   RTL8365MB_CPU_CTRL_TAG_POSITION_MASK	0x0040
#define   RTL8365MB_CPU_CTRL_TRAP_PORT_MASK	0x0038
#define   RTL8365MB_CPU_CTRL_INSERTMODE_MASK	0x0006
#define   RTL8365MB_CPU_CTRL_EN_MASK		0x0001

/* Maximum packet length register */
#define RTL8365MB_CFG0_MAX_LEN_REG	0x088C
#define   RTL8365MB_CFG0_MAX_LEN_MASK	0x3FFF

/* Port learning limit registers */
#define RTL8365MB_LUT_PORT_LEARN_LIMIT_BASE		0x0A20
#define RTL8365MB_LUT_PORT_LEARN_LIMIT_REG(_physport) \
		(RTL8365MB_LUT_PORT_LEARN_LIMIT_BASE + (_physport))

/* Port extended filter ID, used by the bridge L2 key. */
#define RTL8365MB_PORT_EFID_REG_BASE		0x0A32
#define RTL8365MB_PORT_EFID_REG(_physport) \
		(RTL8365MB_PORT_EFID_REG_BASE + ((_physport) >> 2))
#define   RTL8365MB_PORT_EFID_OFFSET(_physport) 	(((_physport) & 0x3) << 2)
#define   RTL8365MB_PORT_EFID_MASK(_physport) \
		(0x7 << RTL8365MB_PORT_EFID_OFFSET(_physport))

/* Port isolation (forwarding mask) registers */
#define RTL8365MB_PORT_ISOLATION_REG_BASE		0x08A2
#define RTL8365MB_PORT_ISOLATION_REG(_physport) \
		(RTL8365MB_PORT_ISOLATION_REG_BASE + (_physport))
#define   RTL8365MB_PORT_ISOLATION_MASK			0x07FF

/* MSTP port state registers - indexed by tree instance */
#define RTL8365MB_MSTI_CTRL_BASE			0x0A00
#define RTL8365MB_MSTI_CTRL_REG(_msti, _physport) \
		(RTL8365MB_MSTI_CTRL_BASE + ((_msti) << 1) + ((_physport) >> 3))
#define   RTL8365MB_MSTI_CTRL_PORT_STATE_OFFSET(_physport) ((_physport) << 1)
#define   RTL8365MB_MSTI_CTRL_PORT_STATE_MASK(_physport) \
		(0x3 << RTL8365MB_MSTI_CTRL_PORT_STATE_OFFSET((_physport)))

/* MIB counter value registers */
#define RTL8365MB_MIB_COUNTER_BASE	0x1000
#define RTL8365MB_MIB_COUNTER_REG(_x)	(RTL8365MB_MIB_COUNTER_BASE + (_x))

/* MIB counter address register */
#define RTL8365MB_MIB_ADDRESS_REG		0x1004
#define   RTL8365MB_MIB_ADDRESS_PORT_OFFSET	0x007C
#define   RTL8365MB_MIB_ADDRESS(_p, _x) \
		(((RTL8365MB_MIB_ADDRESS_PORT_OFFSET) * (_p) + (_x)) >> 2)

#define RTL8365MB_MIB_CTRL0_REG			0x1005
#define   RTL8365MB_MIB_CTRL0_RESET_MASK	0x0002
#define   RTL8365MB_MIB_CTRL0_BUSY_MASK		0x0001

/* The DSA callback .get_stats64 runs in atomic context, so we are not allowed
 * to block. On the other hand, accessing MIB counters absolutely requires us to
 * block. The solution is thus to schedule work which polls the MIB counters
 * asynchronously and updates some private data, which the callback can then
 * fetch atomically. Three seconds should be a good enough polling interval.
 */
#define RTL8365MB_STATS_INTERVAL_JIFFIES	(3 * HZ)

enum rtl8365mb_mib_counter_index {
	RTL8365MB_MIB_ifInOctets,
	RTL8365MB_MIB_dot3StatsFCSErrors,
	RTL8365MB_MIB_dot3StatsSymbolErrors,
	RTL8365MB_MIB_dot3InPauseFrames,
	RTL8365MB_MIB_dot3ControlInUnknownOpcodes,
	RTL8365MB_MIB_etherStatsFragments,
	RTL8365MB_MIB_etherStatsJabbers,
	RTL8365MB_MIB_ifInUcastPkts,
	RTL8365MB_MIB_etherStatsDropEvents,
	RTL8365MB_MIB_ifInMulticastPkts,
	RTL8365MB_MIB_ifInBroadcastPkts,
	RTL8365MB_MIB_inMldChecksumError,
	RTL8365MB_MIB_inIgmpChecksumError,
	RTL8365MB_MIB_inMldSpecificQuery,
	RTL8365MB_MIB_inMldGeneralQuery,
	RTL8365MB_MIB_inIgmpSpecificQuery,
	RTL8365MB_MIB_inIgmpGeneralQuery,
	RTL8365MB_MIB_inMldLeaves,
	RTL8365MB_MIB_inIgmpLeaves,
	RTL8365MB_MIB_etherStatsOctets,
	RTL8365MB_MIB_etherStatsUnderSizePkts,
	RTL8365MB_MIB_etherOversizeStats,
	RTL8365MB_MIB_etherStatsPkts64Octets,
	RTL8365MB_MIB_etherStatsPkts65to127Octets,
	RTL8365MB_MIB_etherStatsPkts128to255Octets,
	RTL8365MB_MIB_etherStatsPkts256to511Octets,
	RTL8365MB_MIB_etherStatsPkts512to1023Octets,
	RTL8365MB_MIB_etherStatsPkts1024to1518Octets,
	RTL8365MB_MIB_ifOutOctets,
	RTL8365MB_MIB_dot3StatsSingleCollisionFrames,
	RTL8365MB_MIB_dot3StatsMultipleCollisionFrames,
	RTL8365MB_MIB_dot3StatsDeferredTransmissions,
	RTL8365MB_MIB_dot3StatsLateCollisions,
	RTL8365MB_MIB_etherStatsCollisions,
	RTL8365MB_MIB_dot3StatsExcessiveCollisions,
	RTL8365MB_MIB_dot3OutPauseFrames,
	RTL8365MB_MIB_ifOutDiscards,
	RTL8365MB_MIB_dot1dTpPortInDiscards,
	RTL8365MB_MIB_ifOutUcastPkts,
	RTL8365MB_MIB_ifOutMulticastPkts,
	RTL8365MB_MIB_ifOutBroadcastPkts,
	RTL8365MB_MIB_outOampduPkts,
	RTL8365MB_MIB_inOampduPkts,
	RTL8365MB_MIB_inIgmpJoinsSuccess,
	RTL8365MB_MIB_inIgmpJoinsFail,
	RTL8365MB_MIB_inMldJoinsSuccess,
	RTL8365MB_MIB_inMldJoinsFail,
	RTL8365MB_MIB_inReportSuppressionDrop,
	RTL8365MB_MIB_inLeaveSuppressionDrop,
	RTL8365MB_MIB_outIgmpReports,
	RTL8365MB_MIB_outIgmpLeaves,
	RTL8365MB_MIB_outIgmpGeneralQuery,
	RTL8365MB_MIB_outIgmpSpecificQuery,
	RTL8365MB_MIB_outMldReports,
	RTL8365MB_MIB_outMldLeaves,
	RTL8365MB_MIB_outMldGeneralQuery,
	RTL8365MB_MIB_outMldSpecificQuery,
	RTL8365MB_MIB_inKnownMulticastPkts,
	RTL8365MB_MIB_END,
};

struct rtl8365mb_mib_counter {
	u32 offset;
	u32 length;
	const char *name;
};

#define RTL8365MB_MAKE_MIB_COUNTER(_offset, _length, _name) \
		[RTL8365MB_MIB_ ## _name] = { _offset, _length, #_name }

static struct rtl8365mb_mib_counter rtl8365mb_mib_counters[] = {
	RTL8365MB_MAKE_MIB_COUNTER(0, 4, ifInOctets),
	RTL8365MB_MAKE_MIB_COUNTER(4, 2, dot3StatsFCSErrors),
	RTL8365MB_MAKE_MIB_COUNTER(6, 2, dot3StatsSymbolErrors),
	RTL8365MB_MAKE_MIB_COUNTER(8, 2, dot3InPauseFrames),
	RTL8365MB_MAKE_MIB_COUNTER(10, 2, dot3ControlInUnknownOpcodes),
	RTL8365MB_MAKE_MIB_COUNTER(12, 2, etherStatsFragments),
	RTL8365MB_MAKE_MIB_COUNTER(14, 2, etherStatsJabbers),
	RTL8365MB_MAKE_MIB_COUNTER(16, 2, ifInUcastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(18, 2, etherStatsDropEvents),
	RTL8365MB_MAKE_MIB_COUNTER(20, 2, ifInMulticastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(22, 2, ifInBroadcastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(24, 2, inMldChecksumError),
	RTL8365MB_MAKE_MIB_COUNTER(26, 2, inIgmpChecksumError),
	RTL8365MB_MAKE_MIB_COUNTER(28, 2, inMldSpecificQuery),
	RTL8365MB_MAKE_MIB_COUNTER(30, 2, inMldGeneralQuery),
	RTL8365MB_MAKE_MIB_COUNTER(32, 2, inIgmpSpecificQuery),
	RTL8365MB_MAKE_MIB_COUNTER(34, 2, inIgmpGeneralQuery),
	RTL8365MB_MAKE_MIB_COUNTER(36, 2, inMldLeaves),
	RTL8365MB_MAKE_MIB_COUNTER(38, 2, inIgmpLeaves),
	RTL8365MB_MAKE_MIB_COUNTER(40, 4, etherStatsOctets),
	RTL8365MB_MAKE_MIB_COUNTER(44, 2, etherStatsUnderSizePkts),
	RTL8365MB_MAKE_MIB_COUNTER(46, 2, etherOversizeStats),
	RTL8365MB_MAKE_MIB_COUNTER(48, 2, etherStatsPkts64Octets),
	RTL8365MB_MAKE_MIB_COUNTER(50, 2, etherStatsPkts65to127Octets),
	RTL8365MB_MAKE_MIB_COUNTER(52, 2, etherStatsPkts128to255Octets),
	RTL8365MB_MAKE_MIB_COUNTER(54, 2, etherStatsPkts256to511Octets),
	RTL8365MB_MAKE_MIB_COUNTER(56, 2, etherStatsPkts512to1023Octets),
	RTL8365MB_MAKE_MIB_COUNTER(58, 2, etherStatsPkts1024to1518Octets),
	RTL8365MB_MAKE_MIB_COUNTER(60, 4, ifOutOctets),
	RTL8365MB_MAKE_MIB_COUNTER(64, 2, dot3StatsSingleCollisionFrames),
	RTL8365MB_MAKE_MIB_COUNTER(66, 2, dot3StatsMultipleCollisionFrames),
	RTL8365MB_MAKE_MIB_COUNTER(68, 2, dot3StatsDeferredTransmissions),
	RTL8365MB_MAKE_MIB_COUNTER(70, 2, dot3StatsLateCollisions),
	RTL8365MB_MAKE_MIB_COUNTER(72, 2, etherStatsCollisions),
	RTL8365MB_MAKE_MIB_COUNTER(74, 2, dot3StatsExcessiveCollisions),
	RTL8365MB_MAKE_MIB_COUNTER(76, 2, dot3OutPauseFrames),
	RTL8365MB_MAKE_MIB_COUNTER(78, 2, ifOutDiscards),
	RTL8365MB_MAKE_MIB_COUNTER(80, 2, dot1dTpPortInDiscards),
	RTL8365MB_MAKE_MIB_COUNTER(82, 2, ifOutUcastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(84, 2, ifOutMulticastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(86, 2, ifOutBroadcastPkts),
	RTL8365MB_MAKE_MIB_COUNTER(88, 2, outOampduPkts),
	RTL8365MB_MAKE_MIB_COUNTER(90, 2, inOampduPkts),
	RTL8365MB_MAKE_MIB_COUNTER(92, 4, inIgmpJoinsSuccess),
	RTL8365MB_MAKE_MIB_COUNTER(96, 2, inIgmpJoinsFail),
	RTL8365MB_MAKE_MIB_COUNTER(98, 2, inMldJoinsSuccess),
	RTL8365MB_MAKE_MIB_COUNTER(100, 2, inMldJoinsFail),
	RTL8365MB_MAKE_MIB_COUNTER(102, 2, inReportSuppressionDrop),
	RTL8365MB_MAKE_MIB_COUNTER(104, 2, inLeaveSuppressionDrop),
	RTL8365MB_MAKE_MIB_COUNTER(106, 2, outIgmpReports),
	RTL8365MB_MAKE_MIB_COUNTER(108, 2, outIgmpLeaves),
	RTL8365MB_MAKE_MIB_COUNTER(110, 2, outIgmpGeneralQuery),
	RTL8365MB_MAKE_MIB_COUNTER(112, 2, outIgmpSpecificQuery),
	RTL8365MB_MAKE_MIB_COUNTER(114, 2, outMldReports),
	RTL8365MB_MAKE_MIB_COUNTER(116, 2, outMldLeaves),
	RTL8365MB_MAKE_MIB_COUNTER(118, 2, outMldGeneralQuery),
	RTL8365MB_MAKE_MIB_COUNTER(120, 2, outMldSpecificQuery),
	RTL8365MB_MAKE_MIB_COUNTER(122, 2, inKnownMulticastPkts),
};

static_assert(ARRAY_SIZE(rtl8365mb_mib_counters) == RTL8365MB_MIB_END);

struct rtl8365mb_jam_tbl_entry {
	u16 reg;
	u16 val;
};

/* Lifted from the vendor driver sources */
static const struct rtl8365mb_jam_tbl_entry rtl8365mb_init_jam_8365mb_vc[] = {
	{ 0x13EB, 0x15BB }, { 0x1303, 0x06D6 }, { 0x1304, 0x0700 },
	{ 0x13E2, 0x003F }, { 0x13F9, 0x0090 }, { 0x121E, 0x03CA },
	{ 0x1233, 0x0352 }, { 0x1237, 0x00A0 }, { 0x123A, 0x0030 },
	{ 0x1239, 0x0084 }, { 0x0301, 0x1000 }, { 0x1349, 0x001F },
	{ 0x18E0, 0x4004 }, { 0x122B, 0x241C }, { 0x1305, 0xC000 },
	{ 0x13F0, 0x0000 },
};

static const struct rtl8365mb_jam_tbl_entry rtl8365mb_init_jam_common[] = {
	{ 0x1200, 0x7FCB }, { 0x0884, 0x0003 }, { 0x06EB, 0x0001 },
	{ 0x03Fa, 0x0007 }, { 0x08C8, 0x00C0 }, { 0x0A30, 0x020E },
	{ 0x0800, 0x0000 }, { 0x0802, 0x0000 }, { 0x09DA, 0x0013 },
	{ 0x1D32, 0x0002 },
};

enum rtl8365mb_stp_state {
	RTL8365MB_STP_STATE_DISABLED = 0,
	RTL8365MB_STP_STATE_BLOCKING = 1,
	RTL8365MB_STP_STATE_LEARNING = 2,
	RTL8365MB_STP_STATE_FORWARDING = 3,
};

enum rtl8365mb_cpu_insert {
	RTL8365MB_CPU_INSERT_TO_ALL = 0,
	RTL8365MB_CPU_INSERT_TO_TRAPPING = 1,
	RTL8365MB_CPU_INSERT_TO_NONE = 2,
};

enum rtl8365mb_cpu_position {
	RTL8365MB_CPU_POS_AFTER_SA = 0,
	RTL8365MB_CPU_POS_BEFORE_CRC = 1,
};

enum rtl8365mb_cpu_format {
	RTL8365MB_CPU_FORMAT_8BYTES = 0,
	RTL8365MB_CPU_FORMAT_4BYTES = 1,
};

enum rtl8365mb_cpu_rxlen {
	RTL8365MB_CPU_RXLEN_72BYTES = 0,
	RTL8365MB_CPU_RXLEN_64BYTES = 1,
};

/**
 * struct rtl8365mb_cpu - CPU port configuration
 * @enable: enable/disable hardware insertion of CPU tag in switch->CPU frames
 * @mask: port mask of ports that parse should parse CPU tags
 * @trap_port: forward trapped frames to this port
 * @insert: CPU tag insertion mode in switch->CPU frames
 * @position: position of CPU tag in frame
 * @rx_length: minimum CPU RX length
 * @format: CPU tag format
 *
 * Represents the CPU tagging and CPU port configuration of the switch. These
 * settings are configurable at runtime.
 */
struct rtl8365mb_cpu {
	bool enable;
	u32 mask;
	u32 trap_port;
	enum rtl8365mb_cpu_insert insert;
	enum rtl8365mb_cpu_position position;
	enum rtl8365mb_cpu_rxlen rx_length;
	enum rtl8365mb_cpu_format format;
};

/**
 * struct rtl8365mb_port - private per-port data
 * @priv: pointer to parent realtek_priv data
 * @index: DSA port index, same as dsa_port::index
 * @stats: link statistics populated by rtl8365mb_stats_poll, ready for atomic
 *         access via rtl8365mb_get_stats64
 * @stats_lock: protect the stats structure during read/update
 * @mib_work: delayed work for polling MIB counters
 */
struct rtl8365mb_port {
	struct realtek_priv *priv;
	unsigned int index;
	struct rtnl_link_stats64 stats;
	spinlock_t stats_lock;
	struct delayed_work mib_work;
};

/**
 * struct rtl8365mb - private chip-specific driver data
 * @priv: pointer to parent realtek_priv data
 * @irq: registered IRQ or zero
 * @chip_id: chip identifier
 * @chip_ver: chip silicon revision
 * @port_mask: mask of all ports
 * @learn_limit_max: maximum number of L2 addresses the chip can learn
 * @cpu: CPU tagging and CPU port configuration for this chip
 * @mib_lock: prevent concurrent reads of MIB counters
 * @ports: per-port data
 * @jam_table: chip-specific initialization jam table
 * @jam_size: size of the chip's jam table
 *
 * Private data for this driver.
 */
struct rtl8365mb {
	struct realtek_priv *priv;
	int irq;
	u32 chip_id;
	u32 chip_ver;
	u32 port_mask;
	u32 learn_limit_max;
	struct rtl8365mb_cpu cpu;
	struct mutex mib_lock;
	struct rtl8365mb_port ports[RTL8365MB_MAX_NUM_PORTS];
	const struct rtl8365mb_jam_tbl_entry *jam_table;
	size_t jam_size;
	bool sgmii_configured;
	bool hsgmii_configured;
	/* Optional Machine-C known-unicast-only bridge offload. */
	bool uc_enabled;
	int uc_fault;
	const struct dsa_switch_ops *uc_orig_ops;
	struct dsa_switch_ops uc_ops;
	struct net_device *uc_bridge;
	u32 uc_members;
	u32 uc_user_mask;
	struct mutex uc_lock;
	struct delayed_work uc_fdb_sync_work;
	struct rt3000_uc_fdb_row *uc_fdb_rows;
	struct rt3000_uc_fdb_row *uc_fdb_scan_rows;
	struct rt3000_uc_fdb_event *uc_fdb_events;
	unsigned int uc_fdb_row_count;
	unsigned long uc_fdb_epoch;
	unsigned long uc_fdb_last_scan_ms;
	unsigned long uc_fdb_max_scan_ms;
	unsigned int uc_fdb_max_rows;
	u32 uc_fdb_sync_domain;
	bool uc_fdb_sync_ready;
	bool uc_fdb_sync_logged;
};

static int rtl8365mb_phy_poll_busy(struct realtek_priv *priv)
{
	u32 val;

	return regmap_read_poll_timeout(priv->map_nolock,
					RTL8365MB_INDIRECT_ACCESS_STATUS_REG,
					val, !val, 10, 100);
}

static int rtl8365mb_phy_ocp_prepare(struct realtek_priv *priv, int phy,
				     u32 ocp_addr)
{
	u32 val;
	int ret;

	/* Set OCP prefix */
	val = FIELD_GET(RTL8365MB_PHY_OCP_ADDR_PREFIX_MASK, ocp_addr);
	ret = regmap_update_bits(
		priv->map_nolock, RTL8365MB_GPHY_OCP_MSB_0_REG,
		RTL8365MB_GPHY_OCP_MSB_0_CFG_CPU_OCPADR_MASK,
		FIELD_PREP(RTL8365MB_GPHY_OCP_MSB_0_CFG_CPU_OCPADR_MASK, val));
	if (ret)
		return ret;

	/* Set PHY register address */
	val = RTL8365MB_PHY_BASE;
	val |= FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_ADDRESS_PHYNUM_MASK, phy);
	val |= FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_ADDRESS_OCPADR_5_1_MASK,
			  ocp_addr >> 1);
	val |= FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_ADDRESS_OCPADR_9_6_MASK,
			  ocp_addr >> 6);
	ret = regmap_write(priv->map_nolock,
			   RTL8365MB_INDIRECT_ACCESS_ADDRESS_REG, val);
	if (ret)
		return ret;

	return 0;
}

static int rtl8365mb_phy_ocp_read(struct realtek_priv *priv, int phy,
				  u32 ocp_addr, u16 *data)
{
	u32 val;
	int ret;

	mutex_lock(&priv->map_lock);

	ret = rtl8365mb_phy_poll_busy(priv);
	if (ret)
		goto out;

	ret = rtl8365mb_phy_ocp_prepare(priv, phy, ocp_addr);
	if (ret)
		goto out;

	/* Execute read operation */
	val = FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_MASK,
			 RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_VALUE) |
	      FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_CTRL_RW_MASK,
			 RTL8365MB_INDIRECT_ACCESS_CTRL_RW_READ);
	ret = regmap_write(priv->map_nolock, RTL8365MB_INDIRECT_ACCESS_CTRL_REG,
			   val);
	if (ret)
		goto out;

	ret = rtl8365mb_phy_poll_busy(priv);
	if (ret)
		goto out;

	/* Get PHY register data */
	ret = regmap_read(priv->map_nolock,
			  RTL8365MB_INDIRECT_ACCESS_READ_DATA_REG, &val);
	if (ret)
		goto out;

	*data = val & 0xFFFF;

out:
	mutex_unlock(&priv->map_lock);

	return ret;
}

static int rtl8365mb_phy_ocp_write(struct realtek_priv *priv, int phy,
				   u32 ocp_addr, u16 data)
{
	u32 val;
	int ret;

	mutex_lock(&priv->map_lock);

	ret = rtl8365mb_phy_poll_busy(priv);
	if (ret)
		goto out;

	ret = rtl8365mb_phy_ocp_prepare(priv, phy, ocp_addr);
	if (ret)
		goto out;

	/* Set PHY register data */
	ret = regmap_write(priv->map_nolock,
			   RTL8365MB_INDIRECT_ACCESS_WRITE_DATA_REG, data);
	if (ret)
		goto out;

	/* Execute write operation */
	val = FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_MASK,
			 RTL8365MB_INDIRECT_ACCESS_CTRL_CMD_VALUE) |
	      FIELD_PREP(RTL8365MB_INDIRECT_ACCESS_CTRL_RW_MASK,
			 RTL8365MB_INDIRECT_ACCESS_CTRL_RW_WRITE);
	ret = regmap_write(priv->map_nolock, RTL8365MB_INDIRECT_ACCESS_CTRL_REG,
			   val);
	if (ret)
		goto out;

	ret = rtl8365mb_phy_poll_busy(priv);
	if (ret)
		goto out;

out:
	mutex_unlock(&priv->map_lock);

	return 0;
}

static int rtl8365mb_phy_read(struct realtek_priv *priv, int phy, int regnum)
{
	u32 ocp_addr;
	u16 val;
	int ret;

	if (phy > RTL8365MB_PHYADDRMAX)
		return -EINVAL;

	if (regnum > RTL8365MB_PHYREGMAX)
		return -EINVAL;

	ocp_addr = RTL8365MB_PHY_OCP_ADDR_PHYREG_BASE + regnum * 2;

	ret = rtl8365mb_phy_ocp_read(priv, phy, ocp_addr, &val);
	if (ret) {
		dev_err(priv->dev,
			"failed to read PHY%d reg %02x @ %04x, ret %d\n", phy,
			regnum, ocp_addr, ret);
		return ret;
	}

	dev_dbg(priv->dev, "read PHY%d register 0x%02x @ %04x, val <- %04x\n",
		phy, regnum, ocp_addr, val);

	return val;
}

static int rtl8365mb_phy_write(struct realtek_priv *priv, int phy, int regnum,
			       u16 val)
{
	u32 ocp_addr;
	int ret;

	if (phy > RTL8365MB_PHYADDRMAX)
		return -EINVAL;

	if (regnum > RTL8365MB_PHYREGMAX)
		return -EINVAL;

	ocp_addr = RTL8365MB_PHY_OCP_ADDR_PHYREG_BASE + regnum * 2;

	ret = rtl8365mb_phy_ocp_write(priv, phy, ocp_addr, val);
	if (ret) {
		dev_err(priv->dev,
			"failed to write PHY%d reg %02x @ %04x, ret %d\n", phy,
			regnum, ocp_addr, ret);
		return ret;
	}

	dev_dbg(priv->dev, "write PHY%d register 0x%02x @ %04x, val -> %04x\n",
		phy, regnum, ocp_addr, val);

	return 0;
}

static int rtl8365mb_dsa_phy_read(struct dsa_switch *ds, int phy, int regnum)
{
	return rtl8365mb_phy_read(ds->priv, phy, regnum);
}

static int rtl8365mb_dsa_phy_write(struct dsa_switch *ds, int phy, int regnum,
				   u16 val)
{
	return rtl8365mb_phy_write(ds->priv, phy, regnum, val);
}

static enum dsa_tag_protocol
rtl8365mb_get_tag_protocol(struct dsa_switch *ds, int port)
{
	return DSA_TAG_PROTO_RTL8_4;
}

static int rtl8365mb_ext_config_rgmii(struct realtek_priv *priv, int port,
				      phy_interface_t interface)
{
	struct device_node *dn;
	const struct dsa_port *dp;
	int tx_delay = 0;
	int rx_delay = 0;
	int ext_int;
	u32 val;
	int ret;

	ext_int = rtl8365mb_extint_port_map[port];

	if (ext_int <= 0) {
		dev_err(priv->dev, "Port %d is not an external interface port\n", port);
		return -EINVAL;
	}

	dp = dsa_to_port(priv->ds, port);
	dn = dp->dn;

	/* Set the RGMII TX/RX delay
	 *
	 * The Realtek vendor driver indicates the following possible
	 * configuration settings:
	 *
	 *   TX delay:
	 *     0 = no delay, 1 = 2 ns delay
	 *   RX delay:
	 *     0 = no delay, 7 = maximum delay
	 *     Each step is approximately 0.3 ns, so the maximum delay is about
	 *     2.1 ns.
	 *
	 * The vendor driver also states that this must be configured *before*
	 * forcing the external interface into a particular mode, which is done
	 * in the rtl8365mb_phylink_mac_link_{up,down} functions.
	 *
	 * Only configure an RGMII TX (resp. RX) delay if the
	 * tx-internal-delay-ps (resp. rx-internal-delay-ps) OF property is
	 * specified. We ignore the detail of the RGMII interface mode
	 * (RGMII_{RXID, TXID, etc.}), as this is considered to be a PHY-only
	 * property.
	 */
	if (!of_property_read_u32(dn, "tx-internal-delay-ps", &val)) {
		val = val / 1000; /* convert to ns */

		if (val == 0 || val == 2)
			tx_delay = val / 2;
		else
			dev_warn(priv->dev,
				 "EXT interface TX delay must be 0 or 2 ns\n");
	}

	if (!of_property_read_u32(dn, "rx-internal-delay-ps", &val)) {
		val = DIV_ROUND_CLOSEST(val, 300); /* convert to 0.3 ns step */

		if (val <= 7)
			rx_delay = val;
		else
			dev_warn(priv->dev,
				 "EXT interface RX delay must be 0 to 2.1 ns\n");
	}

	ret = regmap_update_bits(
		priv->map, RTL8365MB_EXT_RGMXF_REG(ext_int),
		RTL8365MB_EXT_RGMXF_TXDELAY_MASK |
			RTL8365MB_EXT_RGMXF_RXDELAY_MASK,
		FIELD_PREP(RTL8365MB_EXT_RGMXF_TXDELAY_MASK, tx_delay) |
			FIELD_PREP(RTL8365MB_EXT_RGMXF_RXDELAY_MASK, rx_delay));
	if (ret)
		return ret;

	ret = regmap_update_bits(
		priv->map, RTL8365MB_DIGITAL_INTERFACE_SELECT_REG(ext_int),
		RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_MASK(ext_int),
		RTL8365MB_EXT_PORT_MODE_RGMII
			<< RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_OFFSET(
				   ext_int));
	if (ret)
		return ret;

	return 0;
}

/* SGMII initialization sequence derived from Linux commit
 * 0b577e2fe06c023ab996c3d7684538dbbf6e99bc. QSDK 5.4 has no phylink_pcs
 * interface, so this C-only fixed-link path runs the same SerDes setup from
 * mac_config and forces the 1G/full link from mac_link_up.
 */
static const struct rtl8365mb_jam_tbl_entry rtl8365mb_sds_jam_sgmii[] = {
	{ 0x0480, 0x04D7 }, { 0x0481, 0xF994 }, { 0x0482, 0x2420 },
	{ 0x0483, 0x6960 }, { 0x0484, 0x9728 }, { 0x0423, 0x9D85 },
	{ 0x0424, 0xD810 }, { 0x002E, 0x83F2 },
};

static int rtl8365mb_sds_write(struct realtek_priv *priv, u16 addr, u16 data)
{
	int ret;

	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_DATA_REG, data);
	if (ret)
		return ret;
	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_ADR_REG, addr);
	if (ret)
		return ret;

	return regmap_write(priv->map, RTL8365MB_SDS_INDACS_CMD_REG,
			    RTL8365MB_SDS_INDACS_CMD_RUN_MASK |
			    RTL8365MB_SDS_INDACS_CMD_WR_MASK);
}

static int rtl8365mb_sds_read(struct realtek_priv *priv, u16 addr, u16 *data)
{
	u32 val;
	int ret;

	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_ADR_REG, addr);
	if (ret)
		return ret;
	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_CMD_REG,
			   RTL8365MB_SDS_INDACS_CMD_RUN_MASK);
	if (ret)
		return ret;
	ret = regmap_read_poll_timeout(priv->map, RTL8365MB_SDS_INDACS_CMD_REG,
				       val,
				       !(val & RTL8365MB_SDS_INDACS_CMD_BUSY_MASK),
				       10, 1000);
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_SDS_INDACS_DATA_REG, &val);
	if (ret)
		return ret;

	*data = val;
	return 0;
}

/* 1183-byte DW8051 image copied from the GPL-2.0 Realtek RTL8367C vendor
 * source: rtl8367c_asicdrv_port.c, Sgmii_Init (SGMII_INIT_SIZE). This image is
 * also loaded by the vendor type-1 RTL8367S EXT_HSGMII initialization path.
 */
static const u8 rtl8365mb_hsgmii_init_firmware[1183] = {
	0x02, 0x03, 0x81, 0xE4, 0xF5, 0xA8, 0xD2, 0xAF, 0x22, 0x00, 0x00, 0x02,
	0x04, 0x0D, 0xC5, 0xF0, 0xF8, 0xA3, 0xE0, 0x28, 0xF0, 0xC5, 0xF0, 0xF8,
	0xE5, 0x82, 0x15, 0x82, 0x70, 0x02, 0x15, 0x83, 0xE0, 0x38, 0xF0, 0x22,
	0x75, 0xF0, 0x08, 0x75, 0x82, 0x00, 0xEF, 0x2F, 0xFF, 0xEE, 0x33, 0xFE,
	0xCD, 0x33, 0xCD, 0xCC, 0x33, 0xCC, 0xC5, 0x82, 0x33, 0xC5, 0x82, 0x9B,
	0xED, 0x9A, 0xEC, 0x99, 0xE5, 0x82, 0x98, 0x40, 0x0C, 0xF5, 0x82, 0xEE,
	0x9B, 0xFE, 0xED, 0x9A, 0xFD, 0xEC, 0x99, 0xFC, 0x0F, 0xD5, 0xF0, 0xD6,
	0xE4, 0xCE, 0xFB, 0xE4, 0xCD, 0xFA, 0xE4, 0xCC, 0xF9, 0xA8, 0x82, 0x22,
	0xB8, 0x00, 0xC1, 0xB9, 0x00, 0x59, 0xBA, 0x00, 0x2D, 0xEC, 0x8B, 0xF0,
	0x84, 0xCF, 0xCE, 0xCD, 0xFC, 0xE5, 0xF0, 0xCB, 0xF9, 0x78, 0x18, 0xEF,
	0x2F, 0xFF, 0xEE, 0x33, 0xFE, 0xED, 0x33, 0xFD, 0xEC, 0x33, 0xFC, 0xEB,
	0x33, 0xFB, 0x10, 0xD7, 0x03, 0x99, 0x40, 0x04, 0xEB, 0x99, 0xFB, 0x0F,
	0xD8, 0xE5, 0xE4, 0xF9, 0xFA, 0x22, 0x78, 0x18, 0xEF, 0x2F, 0xFF, 0xEE,
	0x33, 0xFE, 0xED, 0x33, 0xFD, 0xEC, 0x33, 0xFC, 0xC9, 0x33, 0xC9, 0x10,
	0xD7, 0x05, 0x9B, 0xE9, 0x9A, 0x40, 0x07, 0xEC, 0x9B, 0xFC, 0xE9, 0x9A,
	0xF9, 0x0F, 0xD8, 0xE0, 0xE4, 0xC9, 0xFA, 0xE4, 0xCC, 0xFB, 0x22, 0x75,
	0xF0, 0x10, 0xEF, 0x2F, 0xFF, 0xEE, 0x33, 0xFE, 0xED, 0x33, 0xFD, 0xCC,
	0x33, 0xCC, 0xC8, 0x33, 0xC8, 0x10, 0xD7, 0x07, 0x9B, 0xEC, 0x9A, 0xE8,
	0x99, 0x40, 0x0A, 0xED, 0x9B, 0xFD, 0xEC, 0x9A, 0xFC, 0xE8, 0x99, 0xF8,
	0x0F, 0xD5, 0xF0, 0xDA, 0xE4, 0xCD, 0xFB, 0xE4, 0xCC, 0xFA, 0xE4, 0xC8,
	0xF9, 0x22, 0xEB, 0x9F, 0xF5, 0xF0, 0xEA, 0x9E, 0x42, 0xF0, 0xE9, 0x9D,
	0x42, 0xF0, 0xE8, 0x9C, 0x45, 0xF0, 0x22, 0xE0, 0xFC, 0xA3, 0xE0, 0xFD,
	0xA3, 0xE0, 0xFE, 0xA3, 0xE0, 0xFF, 0x22, 0xE0, 0xF8, 0xA3, 0xE0, 0xF9,
	0xA3, 0xE0, 0xFA, 0xA3, 0xE0, 0xFB, 0x22, 0xEC, 0xF0, 0xA3, 0xED, 0xF0,
	0xA3, 0xEE, 0xF0, 0xA3, 0xEF, 0xF0, 0x22, 0xE4, 0x90, 0x06, 0x2C, 0xF0,
	0xFD, 0x7C, 0x01, 0x7F, 0x3F, 0x7E, 0x1D, 0x12, 0x04, 0x6B, 0x7D, 0x40,
	0x7C, 0x00, 0x7F, 0x36, 0x7E, 0x13, 0x12, 0x04, 0x6B, 0xE4, 0xFF, 0xFE,
	0xFD, 0x80, 0x25, 0xE4, 0x7F, 0xFF, 0x7E, 0xFF, 0xFD, 0xFC, 0x90, 0x06,
	0x24, 0x12, 0x01, 0x0F, 0xC3, 0x12, 0x00, 0xF2, 0x50, 0x1B, 0x90, 0x06,
	0x24, 0x12, 0x01, 0x03, 0xEF, 0x24, 0x01, 0xFF, 0xE4, 0x3E, 0xFE, 0xE4,
	0x3D, 0xFD, 0xE4, 0x3C, 0xFC, 0x90, 0x06, 0x24, 0x12, 0x01, 0x1B, 0x80,
	0xD2, 0xE4, 0xF5, 0xA8, 0xD2, 0xAF, 0x7D, 0x1F, 0xFC, 0x7F, 0x49, 0x7E,
	0x13, 0x12, 0x04, 0x6B, 0x12, 0x04, 0x92, 0x7D, 0x41, 0x7C, 0x00, 0x7F,
	0x36, 0x7E, 0x13, 0x12, 0x04, 0x6B, 0xE4, 0xFF, 0xFE, 0xFD, 0x80, 0x25,
	0xE4, 0x7F, 0x20, 0x7E, 0x4E, 0xFD, 0xFC, 0x90, 0x06, 0x24, 0x12, 0x01,
	0x0F, 0xC3, 0x12, 0x00, 0xF2, 0x50, 0x1B, 0x90, 0x06, 0x24, 0x12, 0x01,
	0x03, 0xEF, 0x24, 0x01, 0xFF, 0xE4, 0x3E, 0xFE, 0xE4, 0x3D, 0xFD, 0xE4,
	0x3C, 0xFC, 0x90, 0x06, 0x24, 0x12, 0x01, 0x1B, 0x80, 0xD2, 0xC2, 0x00,
	0xC2, 0x01, 0xD2, 0xA9, 0xD2, 0x8C, 0x7F, 0x01, 0x7E, 0x62, 0x12, 0x04,
	0x47, 0xEF, 0x30, 0xE2, 0x07, 0xE4, 0x90, 0x06, 0x2C, 0xF0, 0x80, 0xEE,
	0x90, 0x06, 0x2C, 0xE0, 0x70, 0x12, 0x12, 0x02, 0xDB, 0x90, 0x06, 0x2C,
	0x74, 0x01, 0xF0, 0xE4, 0x90, 0x06, 0x2F, 0xF0, 0xA3, 0xF0, 0x80, 0xD6,
	0xC3, 0x90, 0x06, 0x30, 0xE0, 0x94, 0x62, 0x90, 0x06, 0x2F, 0xE0, 0x94,
	0x00, 0x40, 0xC7, 0xE4, 0xF0, 0xA3, 0xF0, 0x12, 0x02, 0xDB, 0x90, 0x06,
	0x2C, 0x74, 0x01, 0xF0, 0x80, 0xB8, 0x75, 0x0F, 0x80, 0x75, 0x0E, 0x7E,
	0x75, 0x0D, 0xAA, 0x75, 0x0C, 0x83, 0xE4, 0xF5, 0x10, 0x7F, 0x36, 0x7E,
	0x13, 0x12, 0x04, 0x47, 0xEE, 0xC4, 0xF8, 0x54, 0xF0, 0xC8, 0xEF, 0xC4,
	0x54, 0x0F, 0x48, 0x54, 0x07, 0xFB, 0x7A, 0x00, 0xEA, 0x70, 0x4A, 0xEB,
	0x14, 0x60, 0x1C, 0x14, 0x60, 0x27, 0x24, 0xFE, 0x60, 0x31, 0x14, 0x60,
	0x3C, 0x24, 0x05, 0x70, 0x38, 0x75, 0x0B, 0x00, 0x75, 0x0A, 0xC2, 0x75,
	0x09, 0xEB, 0x75, 0x08, 0x0B, 0x80, 0x36, 0x75, 0x0B, 0x40, 0x75, 0x0A,
	0x59, 0x75, 0x09, 0x73, 0x75, 0x08, 0x07, 0x80, 0x28, 0x75, 0x0B, 0x00,
	0x75, 0x0A, 0xE1, 0x75, 0x09, 0xF5, 0x75, 0x08, 0x05, 0x80, 0x1A, 0x75,
	0x0B, 0xA0, 0x75, 0x0A, 0xAC, 0x75, 0x09, 0xB9, 0x75, 0x08, 0x03, 0x80,
	0x0C, 0x75, 0x0B, 0x00, 0x75, 0x0A, 0x62, 0x75, 0x09, 0x3D, 0x75, 0x08,
	0x01, 0x75, 0x89, 0x11, 0xE4, 0x7B, 0x60, 0x7A, 0x09, 0xF9, 0xF8, 0xAF,
	0x0B, 0xAE, 0x0A, 0xAD, 0x09, 0xAC, 0x08, 0x12, 0x00, 0x60, 0xAA, 0x06,
	0xAB, 0x07, 0xC3, 0xE4, 0x9B, 0xFB, 0xE4, 0x9A, 0xFA, 0x78, 0x17, 0xF6,
	0xAF, 0x03, 0xEF, 0x08, 0xF6, 0x18, 0xE6, 0xF5, 0x8C, 0x08, 0xE6, 0xF5,
	0x8A, 0x74, 0x0D, 0x2B, 0xFB, 0xE4, 0x3A, 0x18, 0xF6, 0xAF, 0x03, 0xEF,
	0x08, 0xF6, 0x75, 0x88, 0x10, 0x53, 0x8E, 0xC7, 0xD2, 0xA9, 0x22, 0x7D,
	0x02, 0x7C, 0x00, 0x7F, 0x4A, 0x7E, 0x13, 0x12, 0x04, 0x6B, 0x7D, 0x46,
	0x7C, 0x71, 0x7F, 0x02, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D, 0x03, 0x7C,
	0x00, 0x7F, 0x01, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D, 0xC0, 0x7C, 0x00,
	0x7F, 0x00, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0xE4, 0xFF, 0xFE, 0x0F, 0xBF,
	0x00, 0x01, 0x0E, 0xEF, 0x64, 0x64, 0x4E, 0x70, 0xF5, 0x7D, 0x04, 0x7C,
	0x00, 0x7F, 0x02, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D, 0x00, 0x7C, 0x04,
	0x7F, 0x01, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D, 0xC0, 0x7C, 0x00, 0x7F,
	0x00, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0xE4, 0xFD, 0xFC, 0x7F, 0x02, 0x7E,
	0x66, 0x12, 0x04, 0x6B, 0x7D, 0x00, 0x7C, 0x04, 0x7F, 0x01, 0x7E, 0x66,
	0x12, 0x04, 0x6B, 0x7D, 0xC0, 0x7C, 0x00, 0x7F, 0x00, 0x7E, 0x66, 0x12,
	0x04, 0x6B, 0xE4, 0xFD, 0xFC, 0x7F, 0x4A, 0x7E, 0x13, 0x12, 0x04, 0x6B,
	0x7D, 0x06, 0x7C, 0x71, 0x7F, 0x02, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D,
	0x03, 0x7C, 0x00, 0x7F, 0x01, 0x7E, 0x66, 0x12, 0x04, 0x6B, 0x7D, 0xC0,
	0x7C, 0x00, 0x7F, 0x00, 0x7E, 0x66, 0x02, 0x04, 0x6B, 0x78, 0x7F, 0xE4,
	0xF6, 0xD8, 0xFD, 0x75, 0x81, 0x3C, 0x02, 0x03, 0xC8, 0x02, 0x01, 0x27,
	0xE4, 0x93, 0xA3, 0xF8, 0xE4, 0x93, 0xA3, 0x40, 0x03, 0xF6, 0x80, 0x01,
	0xF2, 0x08, 0xDF, 0xF4, 0x80, 0x29, 0xE4, 0x93, 0xA3, 0xF8, 0x54, 0x07,
	0x24, 0x0C, 0xC8, 0xC3, 0x33, 0xC4, 0x54, 0x0F, 0x44, 0x20, 0xC8, 0x83,
	0x40, 0x04, 0xF4, 0x56, 0x80, 0x01, 0x46, 0xF6, 0xDF, 0xE4, 0x80, 0x0B,
	0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x90, 0x04, 0x87, 0xE4,
	0x7E, 0x01, 0x93, 0x60, 0xBC, 0xA3, 0xFF, 0x54, 0x3F, 0x30, 0xE5, 0x09,
	0x54, 0x1F, 0xFE, 0xE4, 0x93, 0xA3, 0x60, 0x01, 0x0E, 0xCF, 0x54, 0xC0,
	0x25, 0xE0, 0x60, 0xA8, 0x40, 0xB8, 0xE4, 0x93, 0xA3, 0xFA, 0xE4, 0x93,
	0xA3, 0xF8, 0xE4, 0x93, 0xA3, 0xC8, 0xC5, 0x82, 0xC8, 0xCA, 0xC5, 0x83,
	0xCA, 0xF0, 0xA3, 0xC8, 0xC5, 0x82, 0xC8, 0xCA, 0xC5, 0x83, 0xCA, 0xDF,
	0xE9, 0xDE, 0xE7, 0x80, 0xBE, 0xC0, 0xE0, 0xC0, 0xF0, 0xC0, 0x83, 0xC0,
	0x82, 0xC0, 0xD0, 0x75, 0xD0, 0x00, 0xC0, 0x00, 0x78, 0x17, 0xE6, 0xF5,
	0x8C, 0x78, 0x18, 0xE6, 0xF5, 0x8A, 0x90, 0x06, 0x2D, 0xE4, 0x75, 0xF0,
	0x01, 0x12, 0x00, 0x0E, 0x90, 0x06, 0x2F, 0xE4, 0x75, 0xF0, 0x01, 0x12,
	0x00, 0x0E, 0xD0, 0x00, 0xD0, 0xD0, 0xD0, 0x82, 0xD0, 0x83, 0xD0, 0xF0,
	0xD0, 0xE0, 0x32, 0xC2, 0xAF, 0xAD, 0x07, 0xAC, 0x06, 0x8C, 0xA2, 0x8D,
	0xA3, 0x75, 0xA0, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	0x00, 0x00, 0x00, 0xAE, 0xA1, 0xBE, 0x00, 0xF0, 0xAE, 0xA6, 0xAF, 0xA7,
	0xD2, 0xAF, 0x22, 0xC2, 0xAF, 0xAB, 0x07, 0xAA, 0x06, 0x8A, 0xA2, 0x8B,
	0xA3, 0x8C, 0xA4, 0x8D, 0xA5, 0x75, 0xA0, 0x03, 0x00, 0x00, 0x00, 0xAA,
	0xA1, 0xBA, 0x00, 0xF8, 0xD2, 0xAF, 0x22, 0x42, 0x06, 0x2F, 0x00, 0x00,
	0x42, 0x06, 0x2D, 0x00, 0x00, 0x00, 0x12, 0x04, 0x9B, 0x12, 0x02, 0x16,
	0x02, 0x00, 0x03, 0xE4, 0xF5, 0x8E, 0x22,
};

static int rtl8365mb_sgmii_config(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	u32 option, val;
	u16 nway;
	int ret, i;

	/* Restrict this unverified SerDes path to RTL8367S, extension port 6. */
	if (mb->chip_ver != RTL8365MB_CHIP_VER_8367S)
		return -EOPNOTSUPP;
	if (mb->sgmii_configured)
		return 0;

	ret = regmap_write(priv->map, RTL8365MB_SDS_OPTION_ARM_REG,
			   RTL8365MB_SDS_OPTION_ARM_KEY);
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_SDS_OPTION_REG, &option);
	if (ret) {
		int disarm_ret = regmap_write(priv->map,
					      RTL8365MB_SDS_OPTION_ARM_REG, 0);

		if (disarm_ret)
			dev_err(priv->dev, "failed to disarm SGMII option read: %d\n",
				disarm_ret);
		return ret;
	}
	ret = regmap_write(priv->map, RTL8365MB_SDS_OPTION_ARM_REG, 0);
	if (ret)
		return ret;
	if (!option) {
		dev_err(priv->dev, "unsupported RTL8367S SerDes option 0\n");
		return -EOPNOTSUPP;
	}

	/* Keep the switch's firmware controller disabled to avoid register races. */
	ret = regmap_update_bits(priv->map, RTL8365MB_CHIP_RESET_REG,
				 RTL8365MB_CHIP_RESET_DW8051_MASK,
				 RTL8365MB_CHIP_RESET_DW8051_MASK);
	if (ret)
		return ret;
	ret = regmap_update_bits(priv->map, RTL8365MB_MISC_CFG0_REG,
				 RTL8365MB_MISC_CFG0_DW8051_EN_MASK, 0);
	if (ret)
		return ret;
	ret = regmap_update_bits(priv->map, RTL8365MB_BYPASS_LINE_RATE_REG,
				 RTL8365MB_SDS_BYPASS_LINE_RATE_MASK, 0);
	if (ret)
		return ret;

	for (i = 0; i < ARRAY_SIZE(rtl8365mb_sds_jam_sgmii); i++) {
		ret = rtl8365mb_sds_write(priv, rtl8365mb_sds_jam_sgmii[i].reg,
					  rtl8365mb_sds_jam_sgmii[i].val);
		if (ret)
			return ret;
	}

	ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
				 RTL8365MB_SDS_MISC_MAC8_SEL_SGMII_MASK |
				 RTL8365MB_SDS_MISC_MAC8_SEL_HSGMII_MASK,
				 RTL8365MB_SDS_MISC_MAC8_SEL_SGMII_MASK);
	if (ret)
		return ret;
	val = RTL8365MB_EXT_PORT_MODE_SGMII <<
	      RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_OFFSET(
				RTL8365MB_SDS_EXT_INTERFACE_ID);
	ret = regmap_update_bits(priv->map,
			 RTL8365MB_DIGITAL_INTERFACE_SELECT_REG(
				 RTL8365MB_SDS_EXT_INTERFACE_ID),
			 RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_MASK(
				 RTL8365MB_SDS_EXT_INTERFACE_ID), val);
	if (ret)
		return ret;
	ret = rtl8365mb_sds_write(priv, RTL8365MB_SDS_REG_RESET,
				  RTL8365MB_SDS_RESET_DEASSERT);
	if (ret)
		return ret;
	ret = rtl8365mb_sds_write(priv, RTL8365MB_SDS_REG_BMCR,
				  RTL8365MB_SDS_BMCR_DPRST_PHASE1);
	if (ret)
		return ret;
	ret = rtl8365mb_sds_write(priv, RTL8365MB_SDS_REG_BMCR,
				  RTL8365MB_SDS_BMCR_DPRST_PHASE2);
	if (ret)
		return ret;
	ret = rtl8365mb_sds_read(priv, RTL8365MB_SDS_REG_NWAY, &nway);
	if (ret)
		return ret;
	nway &= ~RTL8365MB_SDS_NWAY_EN_MASK;
	nway |= RTL8365MB_SDS_NWAY_RESTART_MASK;
	ret = rtl8365mb_sds_write(priv, RTL8365MB_SDS_REG_NWAY, nway);
	if (ret)
		return ret;

	mb->sgmii_configured = true;
	return 0;
}

/* RTL8367C vendor type-1 EXT_HSGMII redDataHB jam for option != 0. */
static const struct rtl8365mb_jam_tbl_entry rtl8365mb_sds_jam_hsgmii[] = {
	{ 0x0500, 0x82F0 }, { 0x0501, 0xF195 }, { 0x0502, 0x31A2 },
	{ 0x0503, 0x7960 }, { 0x0504, 0x9728 }, { 0x0423, 0x9D85 },
	{ 0x0424, 0xD810 }, { 0x0001, 0x0F80 }, { 0x002E, 0x83F2 },
};

static int rtl8365mb_sds_write_wait(struct realtek_priv *priv, u16 addr,
				    u16 data)
{
	u32 val;
	int ret;

	ret = regmap_read_poll_timeout(priv->map,
				       RTL8365MB_SDS_INDACS_CMD_REG, val,
				       !(val & RTL8365MB_SDS_INDACS_CMD_BUSY_MASK),
				       10, 1000);
	if (ret)
		return ret;

	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_DATA_REG, data);
	if (ret)
		return ret;
	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_ADR_REG, addr);
	if (ret)
		return ret;
	ret = regmap_write(priv->map, RTL8365MB_SDS_INDACS_CMD_REG,
			   RTL8365MB_SDS_INDACS_CMD_RUN_MASK |
			   RTL8365MB_SDS_INDACS_CMD_WR_MASK);
	if (ret)
		return ret;

	return regmap_read_poll_timeout(priv->map,
				       RTL8365MB_SDS_INDACS_CMD_REG, val,
				       !(val & RTL8365MB_SDS_INDACS_CMD_BUSY_MASK),
				       10, 1000);
}

static int rtl8365mb_hsgmii_config(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	u32 option, val;
	bool irom_enabled = false;
	bool reset_asserted = false;
	int ret, cleanup_ret, i;

	if (mb->chip_ver != RTL8365MB_CHIP_VER_8367S)
		return -EOPNOTSUPP;
	if (mb->hsgmii_configured)
		return 0;

	ret = regmap_write(priv->map, RTL8365MB_SDS_OPTION_ARM_REG,
			   RTL8365MB_SDS_OPTION_ARM_KEY);
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_SDS_OPTION_REG, &option);
	cleanup_ret = regmap_write(priv->map, RTL8365MB_SDS_OPTION_ARM_REG, 0);
	if (ret)
		return ret;
	if (cleanup_ret)
		return cleanup_ret;
	if (!option) {
		dev_err(priv->dev, "unsupported RTL8367S HSGMII option 0\n");
		return -EOPNOTSUPP;
	}

	/* Type-1 RTL8367S EXT_PORT0/id1 only; option != 0 selects redDataHB. */
	ret = regmap_update_bits(priv->map, RTL8365MB_BYPASS_LINE_RATE_REG,
				 RTL8365MB_SDS_BYPASS_LINE_RATE_MASK, 0);
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(rtl8365mb_sds_jam_hsgmii); i++) {
		ret = rtl8365mb_sds_write_wait(priv,
				rtl8365mb_sds_jam_hsgmii[i].reg,
				rtl8365mb_sds_jam_hsgmii[i].val);
		if (ret)
			return ret;
	}

	ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
				 RTL8365MB_SDS_MISC_MAC8_SEL_SGMII_MASK |
				 RTL8365MB_SDS_MISC_MAC8_SEL_HSGMII_MASK,
				 RTL8365MB_SDS_MISC_MAC8_SEL_HSGMII_MASK);
	if (ret)
		return ret;
	val = RTL8365MB_EXT_PORT_MODE_HSGMII <<
	      RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_OFFSET(
				RTL8365MB_SDS_EXT_INTERFACE_ID);
	ret = regmap_update_bits(priv->map,
			 RTL8365MB_DIGITAL_INTERFACE_SELECT_REG(
				 RTL8365MB_SDS_EXT_INTERFACE_ID),
			 RTL8365MB_DIGITAL_INTERFACE_SELECT_MODE_MASK(
				 RTL8365MB_SDS_EXT_INTERFACE_ID), val);
	if (ret)
		return ret;

	/* Vendor type-1 sequence: release SDS, then download Sgmii_Init to IROM. */
	ret = rtl8365mb_sds_write_wait(priv, RTL8365MB_SDS_REG_RESET,
				       RTL8365MB_SDS_RESET_DEASSERT);
	if (ret)
		return ret;
	ret = regmap_update_bits(priv->map, RTL8365MB_CHIP_RESET_REG,
				 RTL8365MB_CHIP_RESET_DW8051_MASK,
				 RTL8365MB_CHIP_RESET_DW8051_MASK);
	if (ret)
		return ret;
	reset_asserted = true;
	ret = regmap_update_bits(priv->map, RTL8365MB_MISC_CFG0_REG,
				 RTL8365MB_MISC_CFG0_DW8051_EN_MASK,
				 RTL8365MB_MISC_CFG0_DW8051_EN_MASK);
	if (ret)
		goto err_cleanup;
	ret = regmap_update_bits(priv->map, RTL8365MB_DW8051_RDY_REG,
				 RTL8365MB_DW8051_ACS_IROM_ENABLE_MASK,
				 RTL8365MB_DW8051_ACS_IROM_ENABLE_MASK);
	if (ret)
		goto err_cleanup;
	irom_enabled = true;
	ret = regmap_update_bits(priv->map, RTL8365MB_DW8051_RDY_REG,
				 RTL8365MB_DW8051_IROM_MSB_MASK, 0);
	if (ret)
		goto err_cleanup;
	for (i = 0; i < ARRAY_SIZE(rtl8365mb_hsgmii_init_firmware); i++) {
		ret = regmap_write(priv->map, RTL8365MB_SDS_HSGMII_FW_BASE + i,
				   rtl8365mb_hsgmii_init_firmware[i]);
		if (ret)
			goto err_cleanup;
	}
	ret = regmap_update_bits(priv->map, RTL8365MB_DW8051_RDY_REG,
				 RTL8365MB_DW8051_IROM_MSB_MASK, 0);
	if (ret)
		goto err_cleanup;
	ret = regmap_update_bits(priv->map, RTL8365MB_DW8051_RDY_REG,
				 RTL8365MB_DW8051_ACS_IROM_ENABLE_MASK, 0);
	if (ret)
		goto err_cleanup;
	irom_enabled = false;
	ret = regmap_update_bits(priv->map, RTL8365MB_CHIP_RESET_REG,
				 RTL8365MB_CHIP_RESET_DW8051_MASK, 0);
	if (ret)
		goto err_cleanup;
	reset_asserted = false;

	mb->hsgmii_configured = true;
	return 0;

err_cleanup:
	if (irom_enabled) {
		cleanup_ret = regmap_update_bits(priv->map, RTL8365MB_DW8051_RDY_REG,
					 RTL8365MB_DW8051_ACS_IROM_ENABLE_MASK, 0);
		if (cleanup_ret)
			dev_err(priv->dev, "failed to close HSGMII IROM access: %d\n",
				cleanup_ret);
	}
	if (reset_asserted) {
		cleanup_ret = regmap_update_bits(priv->map, RTL8365MB_CHIP_RESET_REG,
					 RTL8365MB_CHIP_RESET_DW8051_MASK,
					 RTL8365MB_CHIP_RESET_DW8051_MASK);
		if (cleanup_ret)
			dev_err(priv->dev, "failed to keep DW8051 reset asserted: %d\n",
				cleanup_ret);
	}
	return ret;
}

/* RTL8367S vendor rtk_port_sgmiiNway_set(EXT_PORT0, DISABLED).
 * The DW8051 must pause while the host updates the SerDes register.
 */
static int rtl8365mb_hsgmii_disable_nway(struct realtek_priv *priv)
{
	u32 misc_cfg0;
	u16 nway;
	bool running;
	int ret, restore_ret;

	ret = regmap_read(priv->map, RTL8365MB_MISC_CFG0_REG, &misc_cfg0);
	if (ret)
		return ret;
	running = !!(misc_cfg0 & RTL8365MB_MISC_CFG0_DW8051_EN_MASK);
	if (running) {
		ret = regmap_update_bits(priv->map, RTL8365MB_MISC_CFG0_REG,
				 RTL8365MB_MISC_CFG0_DW8051_EN_MASK, 0);
		if (ret)
			return ret;
	}

	ret = rtl8365mb_sds_read(priv, RTL8365MB_SDS_REG_NWAY, &nway);
	if (!ret) {
		nway &= ~RTL8365MB_SDS_NWAY_EN_MASK;
		nway |= RTL8365MB_SDS_NWAY_RESTART_MASK;
		ret = rtl8365mb_sds_write_wait(priv, RTL8365MB_SDS_REG_NWAY,
						 nway);
	}

	if (running) {
		restore_ret = regmap_update_bits(priv->map, RTL8365MB_MISC_CFG0_REG,
					 RTL8365MB_MISC_CFG0_DW8051_EN_MASK,
					 RTL8365MB_MISC_CFG0_DW8051_EN_MASK);
		if (restore_ret && !ret)
			ret = restore_ret;
	}

	return ret;
}

static int rtl8365mb_ext_config_forcemode(struct realtek_priv *priv, int port,
					  bool link, int speed, int duplex,
					  bool tx_pause, bool rx_pause)
{
	u32 r_tx_pause;
	u32 r_rx_pause;
	u32 r_duplex;
	u32 r_speed;
	u32 r_link;
	int ext_int;
	int val;
	int ret;

	ext_int = rtl8365mb_extint_port_map[port];

	if (ext_int <= 0) {
		dev_err(priv->dev, "Port %d is not an external interface port\n", port);
		return -EINVAL;
	}

	if (link) {
		/* Force the link up with the desired configuration */
		r_link = 1;
		r_rx_pause = rx_pause ? 1 : 0;
		r_tx_pause = tx_pause ? 1 : 0;

		if (speed == SPEED_1000) {
			r_speed = RTL8365MB_PORT_SPEED_1000M;
		} else if (speed == SPEED_100) {
			r_speed = RTL8365MB_PORT_SPEED_100M;
		} else if (speed == SPEED_10) {
			r_speed = RTL8365MB_PORT_SPEED_10M;
		} else {
			dev_err(priv->dev, "unsupported port speed %s\n",
				phy_speed_to_str(speed));
			return -EINVAL;
		}

		if (duplex == DUPLEX_FULL) {
			r_duplex = 1;
		} else if (duplex == DUPLEX_HALF) {
			r_duplex = 0;
		} else {
			dev_err(priv->dev, "unsupported duplex %s\n",
				phy_duplex_to_str(duplex));
			return -EINVAL;
		}
	} else {
		/* Force the link down and reset any programmed configuration */
		r_link = 0;
		r_tx_pause = 0;
		r_rx_pause = 0;
		r_speed = 0;
		r_duplex = 0;
	}

	val = FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_EN_MASK, 1) |
	      FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_TXPAUSE_MASK,
			 r_tx_pause) |
	      FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_RXPAUSE_MASK,
			 r_rx_pause) |
	      FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_LINK_MASK, r_link) |
	      FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_DUPLEX_MASK,
			 r_duplex) |
	      FIELD_PREP(RTL8365MB_DIGITAL_INTERFACE_FORCE_SPEED_MASK, r_speed);
	ret = regmap_write(priv->map,
			   RTL8365MB_DIGITAL_INTERFACE_FORCE_REG(ext_int),
			   val);
	if (ret)
		return ret;

	return 0;
}

static bool rtl8365mb_phy_mode_supported(struct dsa_switch *ds, int port,
					 phy_interface_t interface)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;
	int ext_int;

	ext_int = rtl8365mb_extint_port_map[port];

	if (ext_int < 0 &&
	    (interface == PHY_INTERFACE_MODE_NA ||
	     interface == PHY_INTERFACE_MODE_INTERNAL ||
	     interface == PHY_INTERFACE_MODE_GMII))
		/* Internal PHY */
		return true;
	else if ((ext_int >= 1) &&
		 phy_interface_mode_is_rgmii(interface))
		/* Extension MAC */
		return true;
	else if (port == 6 && mb->chip_ver == RTL8365MB_CHIP_VER_8367S &&
		 (interface == PHY_INTERFACE_MODE_SGMII ||
		  interface == PHY_INTERFACE_MODE_2500BASEX))
		return true;

	return false;
}

static void rtl8365mb_phylink_validate(struct dsa_switch *ds, int port,
				       unsigned long *supported,
				       struct phylink_link_state *state)
{
	__ETHTOOL_DECLARE_LINK_MODE_MASK(mask) = { 0, };
	int ext_int = rtl8365mb_extint_port_map[port];
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;

	if (ext_int < 0) {
		if (state->interface != PHY_INTERFACE_MODE_NA &&
		    state->interface != PHY_INTERFACE_MODE_INTERNAL &&
		    state->interface != PHY_INTERFACE_MODE_GMII)
			goto unsupported;
	} else if (state->interface == PHY_INTERFACE_MODE_SGMII ||
		   state->interface == PHY_INTERFACE_MODE_2500BASEX) {
		if (port != 6 || mb->chip_ver != RTL8365MB_CHIP_VER_8367S)
			goto unsupported;
		phylink_set_port_modes(mask);
		if (state->interface == PHY_INTERFACE_MODE_SGMII)
			phylink_set(mask, 1000baseT_Full);
		else
			phylink_set(mask, 2500baseX_Full);
		linkmode_and(supported, supported, mask);
		linkmode_and(state->advertising, state->advertising, mask);
		return;
	} else if (!phy_interface_mode_is_rgmii(state->interface)) {
		goto unsupported;
	}

	phylink_set_port_modes(mask);
	phylink_set(mask, Autoneg);
	phylink_set(mask, 10baseT_Half);
	phylink_set(mask, 10baseT_Full);
	phylink_set(mask, 100baseT_Half);
	phylink_set(mask, 100baseT_Full);
	phylink_set(mask, 1000baseT_Full);
	phylink_set(mask, Pause);
	phylink_set(mask, Asym_Pause);

	linkmode_and(supported, supported, mask);
	linkmode_and(state->advertising, state->advertising, mask);
	return;

unsupported:
	linkmode_zero(supported);
}

static void rtl8365mb_phylink_mac_config(struct dsa_switch *ds, int port,
					 unsigned int mode,
					 const struct phylink_link_state *state)
{
	struct realtek_priv *priv = ds->priv;
	int ret;

	if (!rtl8365mb_phy_mode_supported(ds, port, state->interface)) {
		dev_err(priv->dev, "phy mode %s is unsupported on port %d\n",
			phy_modes(state->interface), port);
		return;
	}

	if (mode != MLO_AN_PHY && mode != MLO_AN_FIXED) {
		dev_err(priv->dev,
			"port %d supports only conventional PHY or fixed-link\n",
			port);
		return;
	}
	if ((state->interface == PHY_INTERFACE_MODE_SGMII ||
	     state->interface == PHY_INTERFACE_MODE_2500BASEX) &&
	    (port != 6 || mode != MLO_AN_FIXED)) {
		dev_err(priv->dev,
			"serial interfaces are supported only as fixed links on port 6\n");
		return;
	}

	if (phy_interface_mode_is_rgmii(state->interface)) {
		ret = rtl8365mb_ext_config_rgmii(priv, port, state->interface);
		if (ret)
			dev_err(priv->dev,
				"failed to configure RGMII mode on port %d: %d\n",
				port, ret);
		return;
	}
	if (state->interface == PHY_INTERFACE_MODE_SGMII) {
		ret = rtl8365mb_sgmii_config(priv);
		if (ret)
			dev_err(priv->dev,
				"failed to configure SGMII on RTL8367S port 6: %d\n",
				ret);
		return;
	}
	if (state->interface == PHY_INTERFACE_MODE_2500BASEX) {
		ret = rtl8365mb_hsgmii_config(priv);
		if (ret)
			dev_err(priv->dev,
				"failed to configure HSGMII on RTL8367S port 6: %d\n",
				ret);
		return;
	}

	/* TODO: Implement MII and RMII modes, which the RTL8365MB-VC also
	 * supports
	 */
}

static void rtl8365mb_phylink_mac_link_down(struct dsa_switch *ds, int port,
					    unsigned int mode,
					    phy_interface_t interface)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb_port *p;
	struct rtl8365mb *mb;
	int ret;

	mb = priv->chip_data;
	p = &mb->ports[port];
	cancel_delayed_work_sync(&p->mib_work);

	if (phy_interface_mode_is_rgmii(interface)) {
		ret = rtl8365mb_ext_config_forcemode(priv, port, false, 0, 0,
						     false, false);
		if (ret)
			dev_err(priv->dev,
				"failed to reset forced mode on port %d: %d\n",
				port, ret);

		return;
	}
	if (interface == PHY_INTERFACE_MODE_SGMII) {
		ret = rtl8365mb_ext_config_forcemode(priv, port, false, 0, 0,
						     false, false);
		if (ret)
			dev_err(priv->dev,
				"failed to reset SGMII mode on port %d: %d\n",
				port, ret);
		ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK, 0);
		if (ret)
			dev_err(priv->dev,
				"failed to clear SGMII SerDes link on port 6: %d\n",
				ret);
		return;
	}
	if (interface == PHY_INTERFACE_MODE_2500BASEX) {
		ret = rtl8365mb_ext_config_forcemode(priv, port, false, 0, 0,
						     false, false);
		if (ret)
			dev_err(priv->dev,
				"failed to reset HSGMII mode on port %d: %d\n",
				port, ret);
		ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK, 0);
		if (ret)
			dev_err(priv->dev,
				"failed to clear HSGMII SerDes link on port 6: %d\n",
				ret);
		return;
	}
}

static void rtl8365mb_phylink_mac_link_up(struct dsa_switch *ds, int port,
					  unsigned int mode,
					  phy_interface_t interface,
					  struct phy_device *phydev)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb_port *p;
	struct rtl8365mb *mb;
	int speed = phydev ? phydev->speed : SPEED_1000;
	int duplex = phydev ? phydev->duplex : DUPLEX_FULL;
	bool tx_pause = phydev && phydev->pause;
	bool rx_pause = false;
	int ret;

	mb = priv->chip_data;
	p = &mb->ports[port];
	if (!phydev && interface == PHY_INTERFACE_MODE_2500BASEX)
		speed = SPEED_2500;
	schedule_delayed_work(&p->mib_work, 0);

	if (phy_interface_mode_is_rgmii(interface)) {
		ret = rtl8365mb_ext_config_forcemode(priv, port, true, speed,
						     duplex, tx_pause,
						     rx_pause);
		if (ret)
			dev_err(priv->dev,
				"failed to force mode on port %d: %d\n", port,
				ret);

		return;
	}
	if (interface == PHY_INTERFACE_MODE_2500BASEX) {
		if (port != 6 || mb->chip_ver != RTL8365MB_CHIP_VER_8367S ||
		    !mb->hsgmii_configured) {
			dev_err(priv->dev, "HSGMII link requested outside RTL8367S port 6 setup\n");
			return;
		}
		if (speed != SPEED_2500 || duplex != DUPLEX_FULL) {
			dev_err(priv->dev,
				"C experiment requires fixed 2500/full HSGMII link on port 6\n");
			return;
		}
		/* The vendor EXT-force encoding remains 1G for HSGMII's 2.5G PCS. */
		ret = rtl8365mb_ext_config_forcemode(priv, port, true, SPEED_1000,
						     DUPLEX_FULL, false, false);
		if (ret) {
			dev_err(priv->dev, "failed to force HSGMII MAC link on port 6: %d\n",
				ret);
			return;
		}
		ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
					 RTL8365MB_SDS_MISC_SGMII_FDUP_MASK |
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK |
					 RTL8365MB_SDS_MISC_SGMII_SPD_MASK,
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK |
					 FIELD_PREP(RTL8365MB_SDS_MISC_SGMII_SPD_MASK,
						    RTL8365MB_PORT_SPEED_1000M) |
					 RTL8365MB_SDS_MISC_SGMII_FDUP_MASK);
		if (ret)
			dev_err(priv->dev, "failed to force HSGMII SerDes link: %d\n", ret);
		else {
			ret = rtl8365mb_hsgmii_disable_nway(priv);
			if (ret)
				dev_err(priv->dev,
					"failed to disable HSGMII Nway on port 6: %d\n",
					ret);
		}
		return;
	}
	if (interface == PHY_INTERFACE_MODE_SGMII) {
		/* This is only used by the C fixed-link DTS, which specifies
		 * 1000/full. QSDK 5.4's callback does not pass fixed-link state.
		 */
		if (port != 6 || mb->chip_ver != RTL8365MB_CHIP_VER_8367S ||
		    !mb->sgmii_configured) {
			dev_err(priv->dev, "SGMII link requested outside RTL8367S port 6 setup\n");
			return;
		}
		if (speed != SPEED_1000 || duplex != DUPLEX_FULL) {
			dev_err(priv->dev,
				"C experiment requires fixed 1000/full SGMII link on port 6\n");
			return;
		}
		ret = rtl8365mb_ext_config_forcemode(priv, port, true, speed,
						     duplex, false, false);
		if (ret) {
			dev_err(priv->dev, "failed to force SGMII MAC link on port 6: %d\n",
				ret);
			return;
		}
		ret = regmap_update_bits(priv->map, RTL8365MB_SDS_MISC_REG,
					 RTL8365MB_SDS_MISC_SGMII_FDUP_MASK |
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK |
					 RTL8365MB_SDS_MISC_SGMII_SPD_MASK,
					 RTL8365MB_SDS_MISC_SGMII_LINK_MASK |
					 FIELD_PREP(RTL8365MB_SDS_MISC_SGMII_SPD_MASK,
						    RTL8365MB_PORT_SPEED_1000M) |
					 RTL8365MB_SDS_MISC_SGMII_FDUP_MASK);
		if (ret)
			dev_err(priv->dev, "failed to force SGMII SerDes link: %d\n", ret);
		return;
	}
}

static void rtl8365mb_port_stp_state_set(struct dsa_switch *ds, int port,
					 u8 state)
{
	struct realtek_priv *priv = ds->priv;
	enum rtl8365mb_stp_state val;
	int msti = 0;

	switch (state) {
	case BR_STATE_DISABLED:
		val = RTL8365MB_STP_STATE_DISABLED;
		break;
	case BR_STATE_BLOCKING:
	case BR_STATE_LISTENING:
		val = RTL8365MB_STP_STATE_BLOCKING;
		break;
	case BR_STATE_LEARNING:
		val = RTL8365MB_STP_STATE_LEARNING;
		break;
	case BR_STATE_FORWARDING:
		val = RTL8365MB_STP_STATE_FORWARDING;
		break;
	default:
		dev_err(priv->dev, "invalid STP state: %u\n", state);
		return;
	}

	regmap_update_bits(priv->map, RTL8365MB_MSTI_CTRL_REG(msti, port),
			   RTL8365MB_MSTI_CTRL_PORT_STATE_MASK(port),
			   val << RTL8365MB_MSTI_CTRL_PORT_STATE_OFFSET(port));
}

static int rtl8365mb_port_set_learning(struct realtek_priv *priv, int port,
				       bool enable)
{
	struct rtl8365mb *mb = priv->chip_data;

	/* Enable/disable learning by limiting the number of L2 addresses the
	 * port can learn. Realtek documentation states that a limit of zero
	 * disables learning. When enabling learning, set it to the chip's
	 * maximum.
	 */
	return regmap_write(priv->map, RTL8365MB_LUT_PORT_LEARN_LIMIT_REG(port),
			    enable ? mb->learn_limit_max : 0);
}

static int rtl8365mb_port_set_isolation(struct realtek_priv *priv, int port,
					u32 mask)
{
	return regmap_write(priv->map, RTL8365MB_PORT_ISOLATION_REG(port), mask);
}

static int rtl8365mb_uc_io_read(void *ctx, unsigned int reg,
				unsigned int *val)
{
	struct realtek_priv *priv = ctx;

	return regmap_read(priv->map, reg, val);
}

static int rtl8365mb_uc_io_write(void *ctx, unsigned int reg,
				 unsigned int val)
{
	struct realtek_priv *priv = ctx;

	return regmap_write(priv->map, reg, val);
}

static int rtl8365mb_uc_set_stp(struct realtek_priv *priv, int port, u8 state)
{
	unsigned int value, check;
	int ret;

	switch (state) {
	case BR_STATE_DISABLED:
		value = RTL8365MB_STP_STATE_DISABLED;
		break;
	case BR_STATE_BLOCKING:
	case BR_STATE_LISTENING:
		value = RTL8365MB_STP_STATE_BLOCKING;
		break;
	case BR_STATE_LEARNING:
		value = RTL8365MB_STP_STATE_LEARNING;
		break;
	case BR_STATE_FORWARDING:
		value = RTL8365MB_STP_STATE_FORWARDING;
		break;
	default:
		return -EINVAL;
	}

	ret = regmap_update_bits(priv->map,
			  RTL8365MB_MSTI_CTRL_REG(0, port),
			  RTL8365MB_MSTI_CTRL_PORT_STATE_MASK(port),
			  value << RTL8365MB_MSTI_CTRL_PORT_STATE_OFFSET(port));
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_MSTI_CTRL_REG(0, port), &check);
	if (ret)
		return ret;
	return (check & RTL8365MB_MSTI_CTRL_PORT_STATE_MASK(port)) ==
		(value << RTL8365MB_MSTI_CTRL_PORT_STATE_OFFSET(port)) ? 0 : -EIO;
}

static int rtl8365mb_uc_set_efid(struct realtek_priv *priv, int port, u8 efid)
{
	unsigned int check;
	int ret;

	ret = regmap_update_bits(priv->map,
			  RTL8365MB_PORT_EFID_REG(port),
			  RTL8365MB_PORT_EFID_MASK(port),
			  efid << RTL8365MB_PORT_EFID_OFFSET(port));
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_PORT_EFID_REG(port), &check);
	if (ret)
		return ret;
	return (check & RTL8365MB_PORT_EFID_MASK(port)) ==
		(efid << RTL8365MB_PORT_EFID_OFFSET(port)) ? 0 : -EIO;
}

static int rtl8365mb_uc_set_learning(struct realtek_priv *priv, int port,
				     bool enable)
{
	struct rtl8365mb *mb = priv->chip_data;
	unsigned int val;
	int ret;

	ret = rtl8365mb_port_set_learning(priv, port, enable);
	if (ret)
		return ret;
	ret = regmap_read(priv->map, RTL8365MB_LUT_PORT_LEARN_LIMIT_REG(port),
			  &val);
	if (ret)
		return ret;
	return val == (enable ? mb->learn_limit_max : 0) ? 0 : -EIO;
}

static int rtl8365mb_uc_flush_port(struct realtek_priv *priv, int port,
				   bool include_static)
{
	struct rtl8367s_uc_l2 entry;
	u16 data[RTL8367S_UC_L2_WORDS];
	u16 addr = 0;
	unsigned int n;
	int ret;

	for (n = 0; n < 4096; n++) {
		u16 start = addr;

		ret = rtl8367s_uc_table_access(priv,
			RTL8367S_UC_TABLE_READ_UC_PORT | ((u16)port << 8),
			&addr, data, false, true);
		if (ret == -ENOENT)
			return 0;
		if (ret)
			return ret;
		if (n && rt3000_uc_dump_wrapped(start, addr))
			return 0;
		rtl8367s_uc_l2_decode(data, &entry);
		if (entry.port == port && (include_static || !entry.is_static)) {
			entry.age = 0;
			entry.is_static = false;
			ret = rtl8367s_uc_l2_write(priv, &entry);
			if (ret && ret != -ENOENT)
				return ret;
		}
		if (addr == 0x0fff)
			return 0;
		addr++;
	}

	return -ELOOP;
}

static int rtl8365mb_uc_set_flood_masks(struct realtek_priv *priv,
					unsigned int cpu_mask)
{
	struct rt3000_uc_reg_io io = {
		.ctx = priv, .read = rtl8365mb_uc_io_read,
		.write = rtl8365mb_uc_io_write,
	};

	return rt3000_uc_set_flood_cpu_only(&io, cpu_mask);
}

static int rtl8365mb_uc_vlan_setup(struct realtek_priv *priv,
				   unsigned int available)
{
	u16 data[RTL8367S_UC_CVLAN_WORDS], check[RTL8367S_UC_CVLAN_WORDS];
	u16 mcdata[4], mccheck[4];
	u32 reg, mask, value;
	int port, vid, ret;

	/* Disable port-based FID selection so the explicit VLAN table's
	 * SVL/FID-0 fields define the lookup domain. The vendor
	 * setAsicPortBasedFidEn API maps this selector to register 0x07ac.
	 */
	ret = regmap_update_bits(priv->map, 0x07ac, available, 0);
	if (ret)
		return ret;
	ret = regmap_read(priv->map, 0x07ac, &value);
	if (ret || (value & available))
		return ret ? ret : -EIO;

	/* Explicit SVL/FID-0 membership for every C-VLAN key; each table write
	 * and read uses the upstream RTL8365MB table-3 layout.
	 */
	rtl8367s_uc_cvlan_encode(available, data);
	for (vid = 0; vid <= 4095; vid++) {
		u16 key = vid;

		ret = rtl8367s_uc_cvlan_access(priv, key, data, true);
		if (ret)
			return ret;
	}
	for (vid = 0; vid <= 4095; vid++) {
		u16 key = vid;

		ret = rtl8367s_uc_cvlan_access(priv, key, check, false);
		if (ret)
			return ret;
		if (memcmp(check, data, sizeof(data)))
			return -EIO;
	}

	/* VLAN MC entry 0 is the PVID index for every port: EVID=0, FID=0,
	 * all configured ports are members. Remaining words are reserved zero.
	 */
	memset(mcdata, 0, sizeof(mcdata));
	mcdata[0] = available & 0x07ff;
	ret = regmap_bulk_write(priv->map, 0x0728, mcdata, ARRAY_SIZE(mcdata));
	if (ret)
		return ret;
	ret = regmap_bulk_read(priv->map, 0x0728, mccheck,
			       ARRAY_SIZE(mccheck));
	if (ret)
		return ret;
	if (memcmp(mccheck, mcdata, sizeof(mcdata)))
		return -EIO;

	for (port = 0; port < RTL8365MB_MAX_NUM_PORTS; port++) {
		if (!(available & BIT(port)))
			continue;
		reg = 0x0700 + (port >> 1);
		mask = (port & 1) ? 0x1f00 : 0x001f;
		ret = regmap_update_bits(priv->map, reg, mask, 0);
		if (ret)
			return ret;
		ret = regmap_read(priv->map, reg, &value);
		if (ret || (value & mask))
			return ret ? ret : -EIO;
	}

	for (port = 0; port < RTL8365MB_MAX_NUM_PORTS; port++) {
		if (!(available & BIT(port)))
			continue;
		/* Disable ingress membership rejection; preserve every ingress
		 * VLAN tag through each egress using REAL_KEEP (value 3).
		 */
		ret = regmap_update_bits(priv->map, 0x07a9, BIT(port), 0);
		if (ret)
			return ret;
		ret = regmap_read(priv->map, 0x07a9, &value);
		if (ret || (value & BIT(port)))
			return ret ? ret : -EIO;
		ret = regmap_update_bits(priv->map, 0x07aa + (port >> 3),
					 3 << ((port & 7) * 2), 0);
		if (ret)
			return ret;
		ret = regmap_read(priv->map, 0x07aa + (port >> 3), &value);
		if (ret || (value & (3 << ((port & 7) * 2))))
			return ret ? ret : -EIO;
		ret = regmap_update_bits(priv->map, 0x000e + (port << 5),
					  0x0030, 0x0030);
		if (ret)
			return ret;
		ret = regmap_read(priv->map, 0x000e + (port << 5), &value);
		if (ret || (value & 0x0030) != 0x0030)
			return ret ? ret : -EIO;
		ret = rt3000_uc_write_verify(&(struct rt3000_uc_reg_io) {
			.ctx = priv, .read = rtl8365mb_uc_io_read,
			.write = rtl8365mb_uc_io_write,
		}, 0x09d0 + port, available, 0x07ff);
		if (ret)
			return ret;
	}

	ret = rt3000_uc_write_verify(&(struct rt3000_uc_reg_io) {
		.ctx = priv, .read = rtl8365mb_uc_io_read,
		.write = rtl8365mb_uc_io_write,
	}, 0x07a8, 1, 1);
	return ret;
}

static int rtl8365mb_uc_fail_closed(struct dsa_switch *ds, int error)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	int port;

	mb->uc_fault = true;
	for (port = 0; port < RTL8365MB_MAX_NUM_PORTS; port++) {
		if (!(mb->uc_user_mask & BIT(port)))
			continue;
		rtl8365mb_port_set_isolation(priv, port, mb->cpu.mask);
		rtl8365mb_uc_set_learning(priv, port, false);
		/* Best effort only; bus failures cannot prove hardware state. */
		rtl8365mb_uc_set_stp(priv, port, BR_STATE_BLOCKING);
	}
	dev_err(priv->dev,
		"known-unicast offload terminal fault (%d); best-effort block applied\n",
		error);
	return error;
}

static DEFINE_MUTEX(rtl8365mb_uc_domain_lock);
static u32 rtl8365mb_uc_domain_next;
static bool rtl8365mb_uc_domain_exhausted;

static int rtl8365mb_uc_domain_alloc(u32 *domain)
{
	int ret = 0;

	mutex_lock(&rtl8365mb_uc_domain_lock);
	if (rtl8365mb_uc_domain_exhausted ||
	    rtl8365mb_uc_domain_next == U32_MAX) {
		rtl8365mb_uc_domain_exhausted = true;
		ret = -EOVERFLOW;
	} else {
		*domain = ++rtl8365mb_uc_domain_next;
	}
	mutex_unlock(&rtl8365mb_uc_domain_lock);
	return ret;
}

static void rtl8365mb_uc_fdb_sync_schedule(struct rtl8365mb *mb,
					   unsigned long delay);

static int rtl8365mb_uc_bridge_join(struct dsa_switch *ds, int port,
				    struct net_device *bridge)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct rt3000_uc_reg_io io = {
		.ctx = priv, .read = rtl8365mb_uc_io_read,
		.write = rtl8365mb_uc_io_write,
	};
	unsigned int next, committed;
	int ret;

	mutex_lock(&mb->uc_lock);
	if (mb->uc_fault) {
		ret = -EIO;
		goto out_unlock;
	}
	if (port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    dsa_is_cpu_port(ds, port) || dsa_is_dsa_port(ds, port) ||
	    !(mb->uc_user_mask & BIT(port)) || br_vlan_enabled(bridge)) {
		ret = -EOPNOTSUPP;
		goto out_unlock;
	}
	if ((mb->uc_bridge && mb->uc_bridge != bridge) ||
	    (mb->uc_members & BIT(port))) {
		ret = -EOPNOTSUPP;
		goto out_unlock;
	}

	ret = rtl8365mb_uc_set_stp(priv, port, BR_STATE_BLOCKING);
	if (ret)
		goto fault;
	ret = rtl8365mb_uc_set_learning(priv, port, false);
	if (ret)
		goto fault;
	ret = rtl8365mb_uc_flush_port(priv, port, true);
	if (ret)
		goto fault;
	ret = rtl8365mb_uc_set_efid(priv, port, RTL8367S_UC_FID_EFID);
	if (ret)
		goto fault;

	next = mb->uc_members | BIT(port);
	committed = mb->uc_members;
	ret = rt3000_uc_program_peer_matrix(&io, mb->uc_user_mask, mb->cpu.mask,
					   next, &committed, &mb->uc_fault);
	if (ret)
		goto fault;
	ret = rtl8365mb_uc_set_learning(priv, port, true);
	if (ret)
		goto fault;
	mb->uc_members = committed;
	mb->uc_fdb_epoch++;
	if (!mb->uc_bridge)
		mb->uc_bridge = bridge;
	ret = 0;
	goto out_unlock;

fault:
	ret = rtl8365mb_uc_fail_closed(ds, ret);
out_unlock:
	mutex_unlock(&mb->uc_lock);
	if (!ret)
		rtl8365mb_uc_fdb_sync_schedule(mb, 0);
	return ret;
}

static void rtl8365mb_uc_bridge_leave(struct dsa_switch *ds, int port,
				       struct net_device *bridge)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct rt3000_uc_reg_io io = {
		.ctx = priv, .read = rtl8365mb_uc_io_read,
		.write = rtl8365mb_uc_io_write,
	};
	unsigned int next, committed;
	bool reschedule = false;
	int ret;

	mutex_lock(&mb->uc_lock);
	if (mb->uc_fault || mb->uc_bridge != bridge ||
	    port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_user_mask & BIT(port)) || !(mb->uc_members & BIT(port))) {
		rtl8365mb_uc_fail_closed(ds, -EINVAL);
		goto out_unlock;
	}
	ret = rtl8365mb_uc_set_stp(priv, port, BR_STATE_BLOCKING);
	if (!ret)
		ret = rtl8365mb_uc_set_learning(priv, port, false);
	if (!ret)
		ret = rtl8365mb_uc_flush_port(priv, port, true);
	if (!ret)
		ret = rtl8365mb_uc_set_efid(priv, port, 0);
	if (ret) {
		rtl8365mb_uc_fail_closed(ds, ret);
		goto out_unlock;
	}

	next = mb->uc_members & ~BIT(port);
	committed = mb->uc_members;
	ret = rt3000_uc_program_peer_matrix(&io, mb->uc_user_mask, mb->cpu.mask,
					   next, &committed, &mb->uc_fault);
	if (ret) {
		rtl8365mb_uc_fail_closed(ds, ret);
		goto out_unlock;
	}
	mb->uc_members = committed;
	mb->uc_fdb_epoch++;
	if (!next) {
		mb->uc_bridge = NULL;
		mb->uc_fdb_row_count = 0;
	}
	reschedule = !!next;
	out_unlock:
	mutex_unlock(&mb->uc_lock);
	if (reschedule)
		rtl8365mb_uc_fdb_sync_schedule(mb,
					      RTL8367S_UC_FDB_SYNC_INTERVAL);
	else
		cancel_delayed_work(&mb->uc_fdb_sync_work);
}

static int rtl8365mb_uc_egress_floods(struct dsa_switch *ds, int port,
				      bool unicast, bool multicast)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;

	/* Linux bridge flooding remains on CPU; only the controlled known-UC
	 * destination path is switched among DSA bridge peers.
	 */
	if (mb->uc_fault || port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_user_mask & BIT(port)))
		return -EIO;
	return 0;
}

static int rtl8365mb_uc_vlan_filtering(struct dsa_switch *ds, int port,
				       bool vlan_filtering)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;

	if (mb->uc_fault)
		return -EIO;

	/* Linux 5.4 bridge ignores -EOPNOTSUPP when toggling filtering. */
	if (vlan_filtering || port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_user_mask & BIT(port)))
		return -EINVAL;
	return 0;
}

static int rtl8365mb_uc_fdb_add_inner(struct dsa_switch *ds, int port,
				      const unsigned char *addr, u16 vid)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct rtl8367s_uc_l2 entry = { 0 };

	if (mb->uc_fault || vid || !is_valid_ether_addr(addr) ||
	    port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_members & BIT(port)))
		return -EOPNOTSUPP;
	ether_addr_copy(entry.mac, addr);
	entry.port = port;
	entry.age = 1;
	entry.is_static = true;
	entry.vid = 0;
	entry.efid = RTL8367S_UC_FID_EFID;
	entry.fid = 0;
	entry.ivl = false;
	{
		int ret = rtl8367s_uc_l2_write(priv, &entry);

		if (ret == -ENOENT)
			return -ENOSPC;
		if (ret)
			return rtl8365mb_uc_fail_closed(ds, ret);
	}
	return 0;
}

static int rtl8365mb_uc_fdb_del_inner(struct dsa_switch *ds, int port,
				      const unsigned char *addr, u16 vid)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct rtl8367s_uc_l2 entry = { 0 }, found;
	int ret;

	if (mb->uc_fault || vid || !is_valid_ether_addr(addr) ||
	    port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_members & BIT(port)))
		return -EOPNOTSUPP;
	ether_addr_copy(entry.mac, addr);
	entry.vid = 0;
	entry.efid = RTL8367S_UC_FID_EFID;
	entry.fid = 0;
	entry.ivl = false;
	ret = rtl8367s_uc_l2_read_key(priv, &entry);
	if (ret == -ENOENT)
		return 0;
	if (ret)
		return rtl8365mb_uc_fail_closed(ds, ret);
	found = entry;
	if (found.port != port)
		return 0;
	found.age = 0;
	found.is_static = false;
	ret = rtl8367s_uc_l2_write(priv, &found);
	if (ret == -ENOENT)
		return 0;
	if (ret)
		return rtl8365mb_uc_fail_closed(ds, ret);
	return 0;
}

static int rtl8365mb_uc_fdb_dump_inner(struct dsa_switch *ds, int port,
				       dsa_fdb_dump_cb_t *cb, void *data)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct rtl8367s_uc_l2 entry;
	u16 words[RTL8367S_UC_L2_WORDS], addr = 0;
	unsigned int count;
	bool first = true;
	int ret;

	if (mb->uc_fault || port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_members & BIT(port)))
		return -EOPNOTSUPP;
	for (count = 0; count < 4096; count++) {
		u16 start = addr;

		ret = rtl8367s_uc_table_access(priv,
			RTL8367S_UC_TABLE_READ_UC_PORT | ((u16)port << 8),
			&addr, words, false, true);
		if (ret == -ENOENT)
			return 0;
		if (ret)
			return rtl8365mb_uc_fail_closed(ds, ret);
		if (!first && rt3000_uc_dump_wrapped(start, addr))
			return 0;
		first = false;
		rtl8367s_uc_l2_decode(words, &entry);
		if (entry.port == port && entry.fid == 0 &&
		    entry.efid == RTL8367S_UC_FID_EFID && !entry.ivl &&
		    !is_multicast_ether_addr(entry.mac)) {
			ret = cb(entry.mac, 0, entry.is_static, data);
			if (ret)
				return ret;
		}
		if (addr == 0x0fff)
			return 0;
		addr++;
	}
	return -ELOOP;
}

static int rtl8365mb_uc_fdb_add(struct dsa_switch *ds, int port,
				const unsigned char *addr, u16 vid)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;
	int ret;

	mutex_lock(&mb->uc_lock);
	ret = rtl8365mb_uc_fdb_add_inner(ds, port, addr, vid);
	if (!ret)
		mb->uc_fdb_epoch++;
	mutex_unlock(&mb->uc_lock);
	return ret;
}

static int rtl8365mb_uc_fdb_del(struct dsa_switch *ds, int port,
				const unsigned char *addr, u16 vid)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;
	int ret;

	mutex_lock(&mb->uc_lock);
	ret = rtl8365mb_uc_fdb_del_inner(ds, port, addr, vid);
	if (!ret)
		mb->uc_fdb_epoch++;
	mutex_unlock(&mb->uc_lock);
	return ret;
}

static int rtl8365mb_uc_fdb_dump(struct dsa_switch *ds, int port,
				 dsa_fdb_dump_cb_t *cb, void *data)
{
	struct rtl8365mb *mb = ((struct realtek_priv *)ds->priv)->chip_data;
	int ret;

	mutex_lock(&mb->uc_lock);
	ret = rtl8365mb_uc_fdb_dump_inner(ds, port, cb, data);
	mutex_unlock(&mb->uc_lock);
	return ret;
}

struct rtl8365mb_uc_fdb_scan_ctx {
	struct rt3000_uc_fdb_row *rows;
	unsigned int count;
	unsigned int port;
};

static int rtl8365mb_uc_fdb_scan_cb(const unsigned char *addr, u16 vid,
				    bool is_static, void *data)
{
	struct rtl8365mb_uc_fdb_scan_ctx *ctx = data;
	struct rt3000_uc_fdb_row *row;

	if (is_static || vid || !is_valid_ether_addr(addr) ||
	    is_multicast_ether_addr(addr))
		return 0;
	if (ctx->count >= RTL8367S_UC_FDB_SYNC_MAX_ROWS)
		return -ENOSPC;

	row = &ctx->rows[ctx->count++];
	ether_addr_copy(row->mac, addr);
	row->port = ctx->port;
	return 0;
}

static int rtl8365mb_uc_fdb_row_cmp(const void *a, const void *b)
{
	const struct rt3000_uc_fdb_row *ra = a, *rb = b;
	int ret = rt3000_uc_fdb_mac_cmp(ra->mac, rb->mac);

	if (ret)
		return ret;
	return (int)ra->port - (int)rb->port;
}

static int rtl8365mb_uc_fdb_notify(struct dsa_switch *ds,
				   const struct rt3000_uc_fdb_event *event)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	struct net_device *slave;
	struct switchdev_notifier_fdb_info info = {
		.addr = event->mac,
		.vid = 0,
		.external_learn_domain = mb->uc_fdb_sync_domain,
		.added_by_user = false,
		.offloaded = true,
	};
	unsigned long notify_event;
	int ret;

	if (event->port >= RTL8365MB_MAX_NUM_PORTS ||
	    !dsa_is_user_port(ds, event->port))
		return -EOPNOTSUPP;

	slave = dsa_to_port(ds, event->port)->slave;
	if (!slave)
		return -ENODEV;

	info.info.dev = slave;
	if (event->action == RT3000_UC_FDB_SYNC_ADD)
		notify_event = SWITCHDEV_RT3000_FDB_SYNC_ADD_TO_BRIDGE;
	else if (event->action == RT3000_UC_FDB_SYNC_DEL)
		notify_event = SWITCHDEV_RT3000_FDB_SYNC_DEL_TO_BRIDGE;
	else
		return -EINVAL;

	ret = call_switchdev_notifiers(notify_event, slave, &info.info, NULL);
	return notifier_to_errno(ret);
}

struct rtl8365mb_uc_fdb_apply_ctx {
	struct rtl8365mb *mb;
	struct dsa_switch *ds;
	const struct rt3000_uc_fdb_row *rows;
	unsigned int members;
	unsigned long epoch;
};

static int rtl8365mb_uc_fdb_sync_notify(void *data,
		const struct rt3000_uc_fdb_event *event)
{
	struct rtl8365mb_uc_fdb_apply_ctx *ctx = data;

	return rtl8365mb_uc_fdb_notify(ctx->ds, event);
}

static int rtl8365mb_uc_fdb_sync_commit(void *data,
		const struct rt3000_uc_fdb_row *rows, unsigned int count)
{
	struct rtl8365mb_uc_fdb_apply_ctx *ctx = data;
	struct rtl8365mb *mb = ctx->mb;
	int ret = 0;

	mutex_lock(&mb->uc_lock);
	if (!mb->uc_fdb_sync_ready || mb->uc_fault ||
	    mb->uc_fdb_epoch != ctx->epoch || mb->uc_members != ctx->members) {
		ret = -EAGAIN;
	} else {
		memcpy(mb->uc_fdb_rows, rows, count * sizeof(*rows));
		mb->uc_fdb_row_count = count;
	}
	mutex_unlock(&mb->uc_lock);
	return ret;
}

static void rtl8365mb_uc_fdb_sync_schedule(struct rtl8365mb *mb,
					   unsigned long delay)
{
	bool active;

	mutex_lock(&mb->uc_lock);
	active = mb->uc_fdb_sync_ready && !mb->uc_fault &&
		 mb->uc_members && mb->uc_bridge;
	/* Serialize the enqueue itself with teardown's ready=false gate. An
	 * unlocked enqueue could run after cancel_sync and private-state free.
	 */
	if (active)
		mod_delayed_work(system_wq, &mb->uc_fdb_sync_work, delay);
	mutex_unlock(&mb->uc_lock);
}

static void rtl8365mb_uc_fdb_sync_work(struct work_struct *work)
{
	struct rtl8365mb *mb = container_of(to_delayed_work(work),
						    struct rtl8365mb,
						    uc_fdb_sync_work);
	struct realtek_priv *priv = mb->priv;
	struct dsa_switch *ds = priv->ds;
	struct rtl8365mb_uc_fdb_apply_ctx apply = {
		.mb = mb,
		.ds = ds,
	};
	struct rtl8365mb_uc_fdb_scan_ctx scan = {
		.rows = mb->uc_fdb_scan_rows,
		.count = 0,
	};
	ktime_t scan_start = ktime_get();
	unsigned int members, i, event_count = 0;
	unsigned long epoch;
	unsigned long elapsed_ms;
	bool valid = false;
	int ret = 0;

	mutex_lock(&mb->uc_lock);
	if (!mb->uc_fdb_sync_ready || mb->uc_fault || !mb->uc_members ||
	    !mb->uc_bridge)
		goto out_unlock_scan;
	members = mb->uc_members;
	epoch = mb->uc_fdb_epoch;
	scan.count = 0;
	for (i = 0; i < RTL8365MB_MAX_NUM_PORTS; i++) {
		if (!(members & BIT(i)))
			continue;
		scan.port = i;
		ret = rtl8365mb_uc_fdb_dump_inner(ds, i,
						 rtl8365mb_uc_fdb_scan_cb, &scan);
		if (ret)
			break;
	}
	if (!ret) {
		sort(scan.rows, scan.count, sizeof(*scan.rows),
		     rtl8365mb_uc_fdb_row_cmp, NULL);
		if (!rt3000_uc_fdb_rows_valid(scan.rows, scan.count))
			ret = -EEXIST;
	}
	if (!ret && epoch == mb->uc_fdb_epoch && members == mb->uc_members)
		valid = true;
out_unlock_scan:
	elapsed_ms = (unsigned long)ktime_to_ms(
		ktime_sub(ktime_get(), scan_start));
	mb->uc_fdb_last_scan_ms = elapsed_ms;
	mb->uc_fdb_max_scan_ms = max(mb->uc_fdb_max_scan_ms, elapsed_ms);
	mb->uc_fdb_max_rows = max(mb->uc_fdb_max_rows, scan.count);
	mutex_unlock(&mb->uc_lock);
	if (!valid)
		goto out_retry;

	/* Never wait for RTNL while holding uc_lock: callbacks take them in this
	 * order. If RTNL is busy, discard this snapshot and retry next interval.
	 */
	if (!rtnl_trylock())
		goto out_retry;
	mutex_lock(&mb->uc_lock);
	valid = mb->uc_fdb_sync_ready && !mb->uc_fault &&
		mb->uc_bridge && mb->uc_members == members &&
		mb->uc_fdb_epoch == epoch;
	mutex_unlock(&mb->uc_lock);
	if (!valid)
		goto out_unlock_rtnl;

	ret = rt3000_uc_fdb_diff(mb->uc_fdb_rows, mb->uc_fdb_row_count,
				 scan.rows, scan.count, mb->uc_fdb_events,
				 RTL8367S_UC_FDB_SYNC_MAX_ROWS * 2,
				 &event_count);
	if (ret)
		goto out_unlock_rtnl;

	/* A source can be learned while the per-port cursors are being walked.
	 * Recheck every prospective deletion by MAC before emitting it. If it now
	 * exists on a current member, repair it with an ADD on that owner instead.
	 */
	mutex_lock(&mb->uc_lock);
	for (i = 0; i < event_count; i++) {
		struct rt3000_uc_fdb_event *event = &mb->uc_fdb_events[i];
		struct rtl8367s_uc_l2 entry = { 0 };
		int lookup;

		if (event->action != RT3000_UC_FDB_SYNC_DEL)
			continue;
		ether_addr_copy(entry.mac, event->mac);
		entry.vid = 0;
		entry.efid = RTL8367S_UC_FID_EFID;
		entry.fid = 0;
		entry.ivl = false;
		lookup = rtl8367s_uc_l2_read_key(priv, &entry);
		if (lookup == -ENOENT)
			continue;
		if (lookup) {
			ret = rtl8365mb_uc_fail_closed(ds, lookup);
			break;
		}
		if (entry.is_static || entry.port >= RTL8365MB_MAX_NUM_PORTS ||
		    !(members & BIT(entry.port)))
			continue;
		if (scan.count >= RTL8367S_UC_FDB_SYNC_MAX_ROWS) {
			ret = -ENOSPC;
			break;
		}
		ether_addr_copy(scan.rows[scan.count].mac, entry.mac);
		scan.rows[scan.count].port = entry.port;
		scan.count++;
	}
	mutex_unlock(&mb->uc_lock);
	if (ret)
		goto out_unlock_rtnl;

	sort(scan.rows, scan.count, sizeof(*scan.rows),
	     rtl8365mb_uc_fdb_row_cmp, NULL);
	if (!rt3000_uc_fdb_rows_valid(scan.rows, scan.count))
		goto out_unlock_rtnl;
	ret = rt3000_uc_fdb_diff(mb->uc_fdb_rows, mb->uc_fdb_row_count,
				 scan.rows, scan.count, mb->uc_fdb_events,
				 RTL8367S_UC_FDB_SYNC_MAX_ROWS * 2,
				 &event_count);
	if (ret)
		goto out_unlock_rtnl;

	apply.rows = scan.rows;
	apply.members = members;
	apply.epoch = epoch;
	ret = rt3000_uc_fdb_sync_apply(true, mb->uc_fdb_rows,
				       mb->uc_fdb_row_count, scan.rows,
				       scan.count, mb->uc_fdb_events,
				       RTL8367S_UC_FDB_SYNC_MAX_ROWS * 2,
				       rtl8365mb_uc_fdb_sync_notify,
				       rtl8365mb_uc_fdb_sync_commit, &apply);
	if (ret)
		goto out_unlock_rtnl;

	if (!mb->uc_fdb_sync_logged) {
		dev_info(priv->dev,
			 "UC FDB sync first scan: rows=%u events=%u scan_ms=%lu\n",
			 scan.count, event_count, elapsed_ms);
		mb->uc_fdb_sync_logged = true;
	} else {
		dev_dbg(priv->dev,
			"UC FDB sync: rows=%u events=%u scan_ms=%lu max_ms=%lu max_rows=%u\n",
			scan.count, event_count, elapsed_ms,
			mb->uc_fdb_max_scan_ms, mb->uc_fdb_max_rows);
	}

out_unlock_rtnl:
	rtnl_unlock();
out_retry:
	rtl8365mb_uc_fdb_sync_schedule(mb, RTL8367S_UC_FDB_SYNC_INTERVAL);
}

static void rtl8365mb_uc_fast_age(struct dsa_switch *ds, int port)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	int ret;

	mutex_lock(&mb->uc_lock);
	if (mb->uc_fault || port < 0 || port >= RTL8365MB_MAX_NUM_PORTS ||
	    !(mb->uc_members & BIT(port)))
		goto out_unlock;
	ret = rtl8365mb_uc_flush_port(priv, port, false);
	if (ret)
		rtl8365mb_uc_fail_closed(ds, ret);
	else
		mb->uc_fdb_epoch++;
out_unlock:
	mutex_unlock(&mb->uc_lock);
}

static void rtl8365mb_uc_stp_state_set(struct dsa_switch *ds, int port,
				       u8 state)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	int ret;

	mutex_lock(&mb->uc_lock);
	if (mb->uc_fault)
		goto out_unlock;
	if (port < 0 || port >= RTL8365MB_MAX_NUM_PORTS) {
		rtl8365mb_uc_fail_closed(ds, -EINVAL);
		goto out_unlock;
	}
	ret = rtl8365mb_uc_set_stp(priv, port, state);
	if (!ret)
		ret = rtl8365mb_uc_set_learning(priv, port,
					  (mb->uc_members & BIT(port)) &&
					  (state == BR_STATE_LEARNING ||
					   state == BR_STATE_FORWARDING));
	if (ret)
		rtl8365mb_uc_fail_closed(ds, ret);
	else
		mb->uc_fdb_epoch++;
out_unlock:
	mutex_unlock(&mb->uc_lock);
}

static int rtl8365mb_uc_enable(struct dsa_switch *ds,
			       struct rtl8365mb *mb, unsigned int cpu_mask)
{
	struct realtek_priv *priv = ds->priv;
	unsigned int available = 0;
	u32 age_cfg;
	int port, ret;

	if (!of_machine_is_compatible("h3c,rt3000-rtl8367s") ||
	    mb->chip_ver != RTL8365MB_CHIP_VER_8367S ||
	    cpu_mask != BIT(RT3000_UC_CPU_PORT) ||
	    dsa_is_unused_port(ds, RT3000_UC_CPU_PORT))
		return -EOPNOTSUPP;
	for (port = 0; port < RTL8365MB_MAX_NUM_PORTS; port++) {
		if (dsa_is_dsa_port(ds, port))
			return -EOPNOTSUPP;
		if (dsa_is_user_port(ds, port))
			mb->uc_user_mask |= BIT(port);
	}
	if (!mb->uc_user_mask)
		return -EOPNOTSUPP;
	available = mb->uc_user_mask | cpu_mask;

	ret = rtl8365mb_uc_vlan_setup(priv, available);
	if (ret)
		return ret;
	ret = rtl8365mb_uc_set_flood_masks(priv, cpu_mask);
	if (ret)
		return ret;
	for (port = 0; port < RTL8365MB_MAX_NUM_PORTS; port++) {
		if (!(available & BIT(port)))
			continue;
		ret = rtl8365mb_uc_set_efid(priv, port, 0);
		if (ret)
			return ret;
	}

	/* This probe is confined to the explicit offload opt-in and exact ID. */
	if (mb->chip_id == RTL8365MB_CHIP_ID_8367S &&
	    mb->chip_ver == RTL8365MB_CHIP_VER_8367S) {
		ret = regmap_read(priv->map, RTL8367S_LUT_AGE_CFG_REG, &age_cfg);
		if (ret) {
			dev_warn(priv->dev,
				 "failed to read RTL8367S LUT age config 0x%04x: %d\n",
				 RTL8367S_LUT_AGE_CFG_REG, ret);
		} else {
			dev_info(priv->dev,
				 "RTL8367S LUT age config: raw=0x%04x timer=%u speed=%u\n",
				 age_cfg, age_cfg & 0x7, (age_cfg >> 8) & 0x3);
		}
	}

	ret = rtl8365mb_uc_domain_alloc(&mb->uc_fdb_sync_domain);
	if (ret)
		return rtl8365mb_uc_fail_closed(ds, ret);

	mb->uc_fdb_rows = kvcalloc(RTL8367S_UC_FDB_SYNC_MAX_ROWS,
				   sizeof(*mb->uc_fdb_rows), GFP_KERNEL);
	mb->uc_fdb_scan_rows = kvcalloc(RTL8367S_UC_FDB_SYNC_MAX_ROWS,
					 sizeof(*mb->uc_fdb_scan_rows), GFP_KERNEL);
	mb->uc_fdb_events = kvcalloc(RTL8367S_UC_FDB_SYNC_MAX_ROWS * 2,
				     sizeof(*mb->uc_fdb_events), GFP_KERNEL);
	if (!mb->uc_fdb_rows || !mb->uc_fdb_scan_rows ||
	    !mb->uc_fdb_events) {
		kvfree(mb->uc_fdb_rows);
		kvfree(mb->uc_fdb_scan_rows);
		kvfree(mb->uc_fdb_events);
		mb->uc_fdb_rows = NULL;
		mb->uc_fdb_scan_rows = NULL;
		mb->uc_fdb_events = NULL;
		return rtl8365mb_uc_fail_closed(ds, -ENOMEM);
	}
	mb->uc_fdb_sync_ready = true;

	mb->uc_orig_ops = ds->ops;
	mb->uc_ops = *ds->ops;
	mb->uc_ops.port_bridge_join = rtl8365mb_uc_bridge_join;
	mb->uc_ops.port_bridge_leave = rtl8365mb_uc_bridge_leave;
	mb->uc_ops.port_egress_floods = rtl8365mb_uc_egress_floods;
	mb->uc_ops.port_vlan_filtering_prepare = rtl8365mb_uc_vlan_filtering;
	mb->uc_ops.port_vlan_filtering = rtl8365mb_uc_vlan_filtering;
	mb->uc_ops.port_fdb_add = rtl8365mb_uc_fdb_add;
	mb->uc_ops.port_fdb_del = rtl8365mb_uc_fdb_del;
	mb->uc_ops.port_fdb_dump = rtl8365mb_uc_fdb_dump;
	mb->uc_ops.port_fast_age = rtl8365mb_uc_fast_age;
	mb->uc_ops.port_stp_state_set = rtl8365mb_uc_stp_state_set;
	ds->ops = &mb->uc_ops;
	mb->uc_enabled = true;
	dev_info(priv->dev,
		 "RTL8367S known-unicast bridge offload enabled; VLAN filtering and flood offload are disabled\n");
	return 0;
}

static int rtl8365mb_mib_counter_read(struct realtek_priv *priv, int port,
				      u32 offset, u32 length, u64 *mibvalue)
{
	u64 tmpvalue = 0;
	u32 val;
	int ret;
	int i;

	/* The MIB address is an SRAM address. We request a particular address
	 * and then poll the control register before reading the value from some
	 * counter registers.
	 */
	ret = regmap_write(priv->map, RTL8365MB_MIB_ADDRESS_REG,
			   RTL8365MB_MIB_ADDRESS(port, offset));
	if (ret)
		return ret;

	/* Poll for completion */
	ret = regmap_read_poll_timeout(priv->map, RTL8365MB_MIB_CTRL0_REG, val,
				       !(val & RTL8365MB_MIB_CTRL0_BUSY_MASK),
				       10, 100);
	if (ret)
		return ret;

	/* Presumably this indicates a MIB counter read failure */
	if (val & RTL8365MB_MIB_CTRL0_RESET_MASK)
		return -EIO;

	/* There are four MIB counter registers each holding a 16 bit word of a
	 * MIB counter. Depending on the offset, we should read from the upper
	 * two or lower two registers. In case the MIB counter is 4 words, we
	 * read from all four registers.
	 */
	if (length == 4)
		offset = 3;
	else
		offset = (offset + 1) % 4;

	/* Read the MIB counter 16 bits at a time */
	for (i = 0; i < length; i++) {
		ret = regmap_read(priv->map,
				  RTL8365MB_MIB_COUNTER_REG(offset - i), &val);
		if (ret)
			return ret;

		tmpvalue = ((tmpvalue) << 16) | (val & 0xFFFF);
	}

	/* Only commit the result if no error occurred */
	*mibvalue = tmpvalue;

	return 0;
}

/* CPU port is not a netdev; append its counters to slave ethtool stats. */
static const enum rtl8365mb_mib_counter_index rtl8365mb_cpu6_mib_stats[] = {
	RTL8365MB_MIB_ifInOctets,
	RTL8365MB_MIB_dot3StatsFCSErrors,
	RTL8365MB_MIB_dot3StatsSymbolErrors,
	RTL8365MB_MIB_etherStatsFragments,
	RTL8365MB_MIB_etherStatsJabbers,
	RTL8365MB_MIB_ifInUcastPkts,
	RTL8365MB_MIB_ifInMulticastPkts,
	RTL8365MB_MIB_ifInBroadcastPkts,
	RTL8365MB_MIB_etherStatsDropEvents,
	RTL8365MB_MIB_etherStatsUnderSizePkts,
	RTL8365MB_MIB_etherStatsPkts64Octets,
	RTL8365MB_MIB_etherStatsPkts65to127Octets,
	RTL8365MB_MIB_ifOutOctets,
	RTL8365MB_MIB_ifOutUcastPkts,
	RTL8365MB_MIB_ifOutBroadcastPkts,
	RTL8365MB_MIB_ifOutDiscards,
	RTL8365MB_MIB_dot1dTpPortInDiscards,
};

#define RTL8365MB_CPU6_MIB_STATS ARRAY_SIZE(rtl8365mb_cpu6_mib_stats)

static bool rtl8365mb_has_cpu6(struct dsa_switch *ds, struct rtl8365mb *mb)
{
	return mb->chip_ver == RTL8365MB_CHIP_VER_8367S &&
	       dsa_is_cpu_port(ds, 6);
}

static void rtl8365mb_get_ethtool_stats(struct dsa_switch *ds, int port, u64 *data)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;
	int ret;
	int i;

	mutex_lock(&mb->mib_lock);
	for (i = 0; i < RTL8365MB_MIB_END; i++) {
		struct rtl8365mb_mib_counter *mib = &rtl8365mb_mib_counters[i];

		ret = rtl8365mb_mib_counter_read(priv, port, mib->offset,
						 mib->length, &data[i]);
		if (ret) {
			dev_err(priv->dev,
				"failed to read port %d counters: %d\n", port,
				ret);
			while (i < RTL8365MB_MIB_END)
				data[i++] = U64_MAX;
			break;
		}
	}

	if (rtl8365mb_has_cpu6(ds, mb)) {
		for (i = 0; i < RTL8365MB_CPU6_MIB_STATS; i++) {
			struct rtl8365mb_mib_counter *mib =
				&rtl8365mb_mib_counters[rtl8365mb_cpu6_mib_stats[i]];

			ret = rtl8365mb_mib_counter_read(priv, 6, mib->offset,
							 mib->length,
							 &data[RTL8365MB_MIB_END + i]);
			if (ret) {
				dev_err(priv->dev,
					"failed to read CPU port 6 counters: %d\n", ret);
				while (i < RTL8365MB_CPU6_MIB_STATS)
					data[RTL8365MB_MIB_END + i++] = U64_MAX;
				break;
			}
		}
	}
	mutex_unlock(&mb->mib_lock);
}

static void rtl8365mb_get_strings(struct dsa_switch *ds, int port, u32 stringset, u8 *data)
{
	int i;

	if (stringset != ETH_SS_STATS)
		return;

	for (i = 0; i < RTL8365MB_MIB_END; i++) {
		struct rtl8365mb_mib_counter *mib = &rtl8365mb_mib_counters[i];

		strncpy(data + i * ETH_GSTRING_LEN, mib->name, ETH_GSTRING_LEN);
	}
	if (rtl8365mb_has_cpu6(ds, ((struct realtek_priv *)ds->priv)->chip_data)) {
		static const char * const names[RTL8365MB_CPU6_MIB_STATS] = {
			"cpu6_ifInOctets", "cpu6_dot3StatsFCSErrors",
			"cpu6_dot3StatsSymbolErrors", "cpu6_etherStatsFragments",
			"cpu6_etherStatsJabbers", "cpu6_ifInUcastPkts",
			"cpu6_ifInMulticastPkts", "cpu6_ifInBroadcastPkts",
			"cpu6_etherStatsDropEvents", "cpu6_etherStatsUnderSizePkts",
			"cpu6_etherStatsPkts64Octets",
			"cpu6_etherStatsPkts65to127Octets", "cpu6_ifOutOctets",
			"cpu6_ifOutUcastPkts", "cpu6_ifOutBroadcastPkts",
			"cpu6_ifOutDiscards", "cpu6_dot1dTpPortInDiscards",
		};

		for (i = 0; i < ARRAY_SIZE(names); i++)
			strncpy(data + (RTL8365MB_MIB_END + i) * ETH_GSTRING_LEN,
				names[i], ETH_GSTRING_LEN);
	}
}

static int rtl8365mb_get_sset_count(struct dsa_switch *ds, int port, int sset)
{
	if (sset != ETH_SS_STATS)
		return -EOPNOTSUPP;

	if (rtl8365mb_has_cpu6(ds, ((struct realtek_priv *)ds->priv)->chip_data))
		return RTL8365MB_MIB_END + RTL8365MB_CPU6_MIB_STATS;

	return RTL8365MB_MIB_END;
}

static void rtl8365mb_stats_update(struct realtek_priv *priv, int port)
{
	u64 cnt[RTL8365MB_MIB_END] = {
		[RTL8365MB_MIB_ifOutOctets] = 1,
		[RTL8365MB_MIB_ifOutUcastPkts] = 1,
		[RTL8365MB_MIB_ifOutMulticastPkts] = 1,
		[RTL8365MB_MIB_ifOutBroadcastPkts] = 1,
		[RTL8365MB_MIB_ifOutDiscards] = 1,
		[RTL8365MB_MIB_ifInOctets] = 1,
		[RTL8365MB_MIB_ifInUcastPkts] = 1,
		[RTL8365MB_MIB_ifInMulticastPkts] = 1,
		[RTL8365MB_MIB_ifInBroadcastPkts] = 1,
		[RTL8365MB_MIB_etherStatsDropEvents] = 1,
		[RTL8365MB_MIB_etherStatsCollisions] = 1,
		[RTL8365MB_MIB_etherStatsFragments] = 1,
		[RTL8365MB_MIB_etherStatsJabbers] = 1,
		[RTL8365MB_MIB_dot3StatsFCSErrors] = 1,
		[RTL8365MB_MIB_dot3StatsLateCollisions] = 1,
	};
	struct rtl8365mb *mb = priv->chip_data;
	struct rtnl_link_stats64 *stats;
	int ret;
	int i;

	stats = &mb->ports[port].stats;

	mutex_lock(&mb->mib_lock);
	for (i = 0; i < RTL8365MB_MIB_END; i++) {
		struct rtl8365mb_mib_counter *c = &rtl8365mb_mib_counters[i];

		/* Only fetch required MIB counters (marked = 1 above) */
		if (!cnt[i])
			continue;

		ret = rtl8365mb_mib_counter_read(priv, port, c->offset,
						 c->length, &cnt[i]);
		if (ret)
			break;
	}
	mutex_unlock(&mb->mib_lock);

	/* Don't update statistics if there was an error reading the counters */
	if (ret)
		return;

	spin_lock(&mb->ports[port].stats_lock);

	stats->rx_packets = cnt[RTL8365MB_MIB_ifInUcastPkts] +
			    cnt[RTL8365MB_MIB_ifInMulticastPkts] +
			    cnt[RTL8365MB_MIB_ifInBroadcastPkts] -
			    cnt[RTL8365MB_MIB_ifOutDiscards];

	stats->tx_packets = cnt[RTL8365MB_MIB_ifOutUcastPkts] +
			    cnt[RTL8365MB_MIB_ifOutMulticastPkts] +
			    cnt[RTL8365MB_MIB_ifOutBroadcastPkts];

	/* if{In,Out}Octets includes FCS - remove it */
	stats->rx_bytes = cnt[RTL8365MB_MIB_ifInOctets] - 4 * stats->rx_packets;
	stats->tx_bytes =
		cnt[RTL8365MB_MIB_ifOutOctets] - 4 * stats->tx_packets;

	stats->rx_dropped = cnt[RTL8365MB_MIB_etherStatsDropEvents];
	stats->tx_dropped = cnt[RTL8365MB_MIB_ifOutDiscards];

	stats->multicast = cnt[RTL8365MB_MIB_ifInMulticastPkts];
	stats->collisions = cnt[RTL8365MB_MIB_etherStatsCollisions];

	stats->rx_length_errors = cnt[RTL8365MB_MIB_etherStatsFragments] +
				  cnt[RTL8365MB_MIB_etherStatsJabbers];
	stats->rx_crc_errors = cnt[RTL8365MB_MIB_dot3StatsFCSErrors];
	stats->rx_errors = stats->rx_length_errors + stats->rx_crc_errors;

	stats->tx_aborted_errors = cnt[RTL8365MB_MIB_ifOutDiscards];
	stats->tx_window_errors = cnt[RTL8365MB_MIB_dot3StatsLateCollisions];
	stats->tx_errors = stats->tx_aborted_errors + stats->tx_window_errors;

	spin_unlock(&mb->ports[port].stats_lock);
}

static void rtl8365mb_stats_poll(struct work_struct *work)
{
	struct rtl8365mb_port *p = container_of(to_delayed_work(work),
						struct rtl8365mb_port,
						mib_work);
	struct realtek_priv *priv = p->priv;

	rtl8365mb_stats_update(priv, p->index);

	schedule_delayed_work(&p->mib_work, RTL8365MB_STATS_INTERVAL_JIFFIES);
}

static void rtl8365mb_stats_setup(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	int i;

	/* Per-chip global mutex to protect MIB counter access, since doing
	 * so requires accessing a series of registers in a particular order.
	 */
	mutex_init(&mb->mib_lock);

	for (i = 0; i < priv->num_ports; i++) {
		struct rtl8365mb_port *p = &mb->ports[i];

		if (dsa_is_unused_port(priv->ds, i))
			continue;

		/* Per-port spinlock to protect the stats64 data */
		spin_lock_init(&p->stats_lock);

		/* This work polls the MIB counters and keeps the stats64 data
		 * up-to-date.
		 */
		INIT_DELAYED_WORK(&p->mib_work, rtl8365mb_stats_poll);
	}
}

static void rtl8365mb_stats_teardown(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	int i;

	for (i = 0; i < priv->num_ports; i++) {
		struct rtl8365mb_port *p = &mb->ports[i];

		if (dsa_is_unused_port(priv->ds, i))
			continue;

		cancel_delayed_work_sync(&p->mib_work);
	}
}

static int rtl8365mb_get_and_clear_status_reg(struct realtek_priv *priv, u32 reg,
					      u32 *val)
{
	int ret;

	ret = regmap_read(priv->map, reg, val);
	if (ret)
		return ret;

	return regmap_write(priv->map, reg, *val);
}

static irqreturn_t rtl8365mb_irq(int irq, void *data)
{
	struct realtek_priv *priv = data;
	unsigned long line_changes = 0;
	struct rtl8365mb *mb;
	u32 stat;
	int line;
	int ret;

	mb = priv->chip_data;

	ret = rtl8365mb_get_and_clear_status_reg(priv, RTL8365MB_INTR_STATUS_REG,
						 &stat);
	if (ret)
		goto out_error;

	if (stat & RTL8365MB_INTR_LINK_CHANGE_MASK) {
		u32 linkdown_ind;
		u32 linkup_ind;
		u32 val;

		ret = rtl8365mb_get_and_clear_status_reg(
			priv, RTL8365MB_PORT_LINKUP_IND_REG, &val);
		if (ret)
			goto out_error;

		linkup_ind = FIELD_GET(RTL8365MB_PORT_LINKUP_IND_MASK, val);

		ret = rtl8365mb_get_and_clear_status_reg(
			priv, RTL8365MB_PORT_LINKDOWN_IND_REG, &val);
		if (ret)
			goto out_error;

		linkdown_ind = FIELD_GET(RTL8365MB_PORT_LINKDOWN_IND_MASK, val);

		line_changes = (linkup_ind | linkdown_ind) & mb->port_mask;
	}

	if (!line_changes)
		goto out_none;

	for_each_set_bit(line, &line_changes, priv->num_ports) {
		int child_irq = irq_find_mapping(priv->irqdomain, line);

		handle_nested_irq(child_irq);
	}

	return IRQ_HANDLED;

out_error:
	dev_err(priv->dev, "failed to read interrupt status: %d\n", ret);

out_none:
	return IRQ_NONE;
}

static struct irq_chip rtl8365mb_irq_chip = {
	.name = "rtl8365mb",
	/* The hardware doesn't support masking IRQs on a per-port basis */
};

static int rtl8365mb_irq_map(struct irq_domain *domain, unsigned int irq,
			     irq_hw_number_t hwirq)
{
	irq_set_chip_data(irq, domain->host_data);
	irq_set_chip_and_handler(irq, &rtl8365mb_irq_chip, handle_simple_irq);
	irq_set_nested_thread(irq, 1);
	irq_set_noprobe(irq);

	return 0;
}

static void rtl8365mb_irq_unmap(struct irq_domain *d, unsigned int irq)
{
	irq_set_nested_thread(irq, 0);
	irq_set_chip_and_handler(irq, NULL, NULL);
	irq_set_chip_data(irq, NULL);
}

static const struct irq_domain_ops rtl8365mb_irqdomain_ops = {
	.map = rtl8365mb_irq_map,
	.unmap = rtl8365mb_irq_unmap,
	.xlate = irq_domain_xlate_onecell,
};

static int rtl8365mb_set_irq_enable(struct realtek_priv *priv, bool enable)
{
	return regmap_update_bits(priv->map, RTL8365MB_INTR_CTRL_REG,
				  RTL8365MB_INTR_LINK_CHANGE_MASK,
				  FIELD_PREP(RTL8365MB_INTR_LINK_CHANGE_MASK,
					     enable ? 1 : 0));
}

static int rtl8365mb_irq_enable(struct realtek_priv *priv)
{
	return rtl8365mb_set_irq_enable(priv, true);
}

static int rtl8365mb_irq_disable(struct realtek_priv *priv)
{
	return rtl8365mb_set_irq_enable(priv, false);
}

static int rtl8365mb_irq_setup(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	struct device_node *intc;
	u32 irq_trig;
	int virq;
	int irq;
	u32 val;
	int ret;
	int i;

	intc = of_get_child_by_name(priv->dev->of_node, "interrupt-controller");
	if (!intc) {
		dev_err(priv->dev, "missing child interrupt-controller node\n");
		return -EINVAL;
	}

	/* rtl8365mb IRQs cascade off this one */
	irq = of_irq_get(intc, 0);
	if (irq <= 0) {
		if (irq != -EPROBE_DEFER)
			dev_err(priv->dev, "failed to get parent irq: %d\n",
				irq);
		ret = irq ? irq : -EINVAL;
		goto out_put_node;
	}

	priv->irqdomain = irq_domain_add_linear(intc, priv->num_ports,
						&rtl8365mb_irqdomain_ops, priv);
	if (!priv->irqdomain) {
		dev_err(priv->dev, "failed to add irq domain\n");
		ret = -ENOMEM;
		goto out_put_node;
	}

	for (i = 0; i < priv->num_ports; i++) {
		virq = irq_create_mapping(priv->irqdomain, i);
		if (!virq) {
			dev_err(priv->dev,
				"failed to create irq domain mapping\n");
			ret = -EINVAL;
			goto out_remove_irqdomain;
		}

		irq_set_parent(virq, irq);
	}

	/* Configure chip interrupt signal polarity */
	irq_trig = irqd_get_trigger_type(irq_get_irq_data(irq));
	switch (irq_trig) {
	case IRQF_TRIGGER_RISING:
	case IRQF_TRIGGER_HIGH:
		val = RTL8365MB_INTR_POLARITY_HIGH;
		break;
	case IRQF_TRIGGER_FALLING:
	case IRQF_TRIGGER_LOW:
		val = RTL8365MB_INTR_POLARITY_LOW;
		break;
	default:
		dev_err(priv->dev, "unsupported irq trigger type %u\n",
			irq_trig);
		ret = -EINVAL;
		goto out_remove_irqdomain;
	}

	ret = regmap_update_bits(priv->map, RTL8365MB_INTR_POLARITY_REG,
				 RTL8365MB_INTR_POLARITY_MASK,
				 FIELD_PREP(RTL8365MB_INTR_POLARITY_MASK, val));
	if (ret)
		goto out_remove_irqdomain;

	/* Disable the interrupt in case the chip has it enabled on reset */
	ret = rtl8365mb_irq_disable(priv);
	if (ret)
		goto out_remove_irqdomain;

	/* Clear the interrupt status register */
	ret = regmap_write(priv->map, RTL8365MB_INTR_STATUS_REG,
			   RTL8365MB_INTR_ALL_MASK);
	if (ret)
		goto out_remove_irqdomain;

	ret = request_threaded_irq(irq, NULL, rtl8365mb_irq, IRQF_ONESHOT,
				   "rtl8365mb", priv);
	if (ret) {
		dev_err(priv->dev, "failed to request irq: %d\n", ret);
		goto out_remove_irqdomain;
	}

	/* Store the irq so that we know to free it during teardown */
	mb->irq = irq;

	ret = rtl8365mb_irq_enable(priv);
	if (ret)
		goto out_free_irq;

	of_node_put(intc);

	return 0;

out_free_irq:
	free_irq(mb->irq, priv);
	mb->irq = 0;

out_remove_irqdomain:
	for (i = 0; i < priv->num_ports; i++) {
		virq = irq_find_mapping(priv->irqdomain, i);
		irq_dispose_mapping(virq);
	}

	irq_domain_remove(priv->irqdomain);
	priv->irqdomain = NULL;

out_put_node:
	of_node_put(intc);

	return ret;
}

static void rtl8365mb_irq_teardown(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	int virq;
	int i;

	if (mb->irq) {
		free_irq(mb->irq, priv);
		mb->irq = 0;
	}

	if (priv->irqdomain) {
		for (i = 0; i < priv->num_ports; i++) {
			virq = irq_find_mapping(priv->irqdomain, i);
			irq_dispose_mapping(virq);
		}

		irq_domain_remove(priv->irqdomain);
		priv->irqdomain = NULL;
	}
}

static int rtl8365mb_cpu_config(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	struct rtl8365mb_cpu *cpu = &mb->cpu;
	u32 val;
	int ret;

	ret = regmap_update_bits(priv->map, RTL8365MB_CPU_PORT_MASK_REG,
				 RTL8365MB_CPU_PORT_MASK_MASK,
				 FIELD_PREP(RTL8365MB_CPU_PORT_MASK_MASK,
					    cpu->mask));
	if (ret)
		return ret;

	val = FIELD_PREP(RTL8365MB_CPU_CTRL_EN_MASK, cpu->enable ? 1 : 0) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_INSERTMODE_MASK, cpu->insert) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_TAG_POSITION_MASK, cpu->position) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_RXBYTECOUNT_MASK, cpu->rx_length) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_TAG_FORMAT_MASK, cpu->format) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_TRAP_PORT_MASK, cpu->trap_port & 0x7) |
	      FIELD_PREP(RTL8365MB_CPU_CTRL_TRAP_PORT_EXT_MASK,
			 cpu->trap_port >> 3 & 0x1);
	ret = regmap_write(priv->map, RTL8365MB_CPU_CTRL_REG, val);
	if (ret)
		return ret;

	return 0;
}

static int rtl8365mb_switch_init(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	int ret;
	int i;

	/* Do any chip-specific init jam before getting to the common stuff */
	if (mb->jam_table) {
		for (i = 0; i < mb->jam_size; i++) {
			ret = regmap_write(priv->map, mb->jam_table[i].reg,
					   mb->jam_table[i].val);
			if (ret)
				return ret;
		}
	}

	/* Common init jam */
	for (i = 0; i < ARRAY_SIZE(rtl8365mb_init_jam_common); i++) {
		ret = regmap_write(priv->map, rtl8365mb_init_jam_common[i].reg,
				   rtl8365mb_init_jam_common[i].val);
		if (ret)
			return ret;
	}

	return 0;
}

static int rtl8365mb_reset_chip(struct realtek_priv *priv)
{
	u32 val;

	priv->write_reg_noack(priv, RTL8365MB_CHIP_RESET_REG,
			      FIELD_PREP(RTL8365MB_CHIP_RESET_HW_MASK, 1));

	/* Realtek documentation says the chip needs 1 second to reset. Sleep
	 * for 100 ms before accessing any registers to prevent ACK timeouts.
	 */
	msleep(100);
	return regmap_read_poll_timeout(priv->map, RTL8365MB_CHIP_RESET_REG, val,
					!(val & RTL8365MB_CHIP_RESET_HW_MASK),
					20000, 1e6);
}

/*
 * The timer-only tuple 5/2 is an opt-in diagnostic point, not a seconds
 * mapping. Keep this independent of the optional unicast-offload worker.
 */
#define RTL8365MB_RT3000_AGE_REG		0x0a30
#define RTL8365MB_RT3000_AGE_TIMER_MASK	0x0007
#define RTL8365MB_RT3000_AGE_OLD_RAW		0x020e
#define RTL8365MB_RT3000_AGE_NEW_RAW		0x020d

static int rtl8365mb_rt3000_age_check_bootargs(void)
{
	struct device_node *chosen;
	const char *bootargs;
	const char *p;
	unsigned int init_count = 0;
	int ret = 0;

	chosen = of_find_node_by_path("/chosen");
	if (!chosen)
		return -ENODEV;

	if (of_property_read_string(chosen, "bootargs", &bootargs)) {
		ret = -EINVAL;
		goto out_put;
	}

	p = bootargs;
	while (*p) {
		const char *start;
		size_t len;

		while (*p && isspace(*p))
			p++;
		if (!*p)
			break;
		start = p;
		while (*p && !isspace(*p))
			p++;
		len = p - start;

		if (len >= 5 && !strncmp(start, "init=", 5)) {
			if (len != sizeof("init=/init") - 1 ||
			    strncmp(start, "init=/init", len)) {
				ret = -EINVAL;
				goto out_put;
			}
			init_count++;
		} else if ((len >= 5 && !strncmp(start, "root=", 5)) ||
			   (len >= 11 && !strncmp(start, "rootfstype=", 11)) ||
			   (len >= 8 && !strncmp(start, "ubi.mtd=", 8)) ||
			   (len >= 9 && !strncmp(start, "mtdparts=", 9))) {
			ret = -EPERM;
			goto out_put;
		}
	}

	if (init_count != 1)
		ret = -EINVAL;

out_put:
	of_node_put(chosen);
	return ret;
}

static int rtl8365mb_rt3000_age_check_guards(
	struct realtek_priv *priv, struct rtl8365mb *mb, u32 cpu_mask)
{
	struct device_node *nand;
	const char *status;
	int ret;

	if (!of_machine_is_compatible("h3c,rt3000-rtl8367s") ||
	    mb->chip_id != RTL8365MB_CHIP_ID_8367S ||
	    mb->chip_ver != RTL8365MB_CHIP_VER_8367S ||
	    cpu_mask != BIT(6) || !priv->dev->of_node ||
	    !of_property_read_bool(priv->dev->of_node,
				   "realtek,rt3000-unicast-offload"))
		return -EPERM;

	ret = rtl8365mb_rt3000_age_check_bootargs();
	if (ret)
		return ret;

	nand = of_find_node_by_path("/soc/qpic-nand@79b0000");
	if (!nand)
		return -ENODEV;

	if (!of_device_is_compatible(nand, "qcom,ebi2-nandc-bam-v2.1.1") ||
	    of_property_read_string(nand, "status", &status) ||
	    strcmp(status, "disabled") || of_device_is_available(nand))
		ret = -EPERM;
	else
		ret = 0;

	of_node_put(nand);
	return ret;
}

static int rtl8365mb_rt3000_age_apply(struct realtek_priv *priv)
{
	u32 before, after, restored;
	int ret, rollback_ret;

	ret = regmap_read(priv->map, RTL8365MB_RT3000_AGE_REG, &before);
	if (ret) {
		dev_err(priv->dev,
			"age calibration initial register read failed: %d; no write attempted\n",
			ret);
		return ret;
	}
	if (before != RTL8365MB_RT3000_AGE_OLD_RAW) {
		dev_err(priv->dev,
			"age calibration refused unexpected raw value 0x%04x (expected 0x%04x)\n",
			before, RTL8365MB_RT3000_AGE_OLD_RAW);
		return -EINVAL;
	}

	ret = regmap_update_bits(priv->map, RTL8365MB_RT3000_AGE_REG,
				 RTL8365MB_RT3000_AGE_TIMER_MASK, 5);
	if (!ret) {
		ret = regmap_read(priv->map, RTL8365MB_RT3000_AGE_REG, &after);
		if (!ret && after == RTL8365MB_RT3000_AGE_NEW_RAW) {
			dev_info(priv->dev,
				 "age calibration applied: raw before=0x%04x after=0x%04x; timer=5 speed=2\n",
				 before, after);
			return 0;
		}
		if (!ret)
			ret = -EIO;
	}

	rollback_ret = regmap_update_bits(priv->map,
					  RTL8365MB_RT3000_AGE_REG,
					  RTL8365MB_RT3000_AGE_TIMER_MASK,
					  before & RTL8365MB_RT3000_AGE_TIMER_MASK);
	if (!rollback_ret) {
		rollback_ret = regmap_read(priv->map,
					   RTL8365MB_RT3000_AGE_REG, &restored);
		if (!rollback_ret && restored != before)
			rollback_ret = -EIO;
	}
	if (!rollback_ret)
		dev_err(priv->dev,
			"age calibration failed (%d); rollback readback confirmed raw=0x%04x\n",
			ret, restored);
	else
		dev_err(priv->dev,
			"age calibration failed (%d); rollback unverified (%d); aborting setup\n",
			ret, rollback_ret);

	return ret;
}

static int rtl8365mb_rt3000_age_calibration_setup(
	struct realtek_priv *priv, struct rtl8365mb *mb, u32 cpu_mask)
{
	int ret;

	if (!rtl8365mb_rt3000_age_calibration)
		return 0;

	ret = rtl8365mb_rt3000_age_check_guards(priv, mb, cpu_mask);
	if (ret) {
		dev_err(priv->dev,
			"age calibration opt-in rejected by board/RAM guards: %d\n",
			ret);
		return ret;
	}

	return rtl8365mb_rt3000_age_apply(priv);
}

static int rtl8365mb_setup(struct dsa_switch *ds)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb_cpu *cpu;
	struct rtl8365mb *mb;
	bool uc_optin;
	int ret;
	int i;

	mb = priv->chip_data;
	cpu = &mb->cpu;
	mutex_init(&mb->uc_lock);
	INIT_DELAYED_WORK(&mb->uc_fdb_sync_work,
			  rtl8365mb_uc_fdb_sync_work);
	uc_optin = of_property_read_bool(priv->dev->of_node,
					 "realtek,rt3000-unicast-offload");

	ret = rtl8365mb_reset_chip(priv);
	if (ret) {
		dev_err(priv->dev, "failed to reset chip: %d\n", ret);
		goto out_error;
	}

	/* Configure switch to vendor-defined initial state */
	ret = rtl8365mb_switch_init(priv);
	if (ret) {
		dev_err(priv->dev, "failed to initialize switch: %d\n", ret);
		goto out_error;
	}

	/* Set up cascading IRQs */
	ret = rtl8365mb_irq_setup(priv);
	if (ret == -EPROBE_DEFER)
		return ret;
	else if (ret)
		dev_info(priv->dev, "no interrupt support\n");

	/* Configure CPU tagging */
	for (i = 0; i < priv->num_ports; i++) {
		if (!dsa_is_cpu_port(priv->ds, i))
			continue;

		cpu->mask |= BIT(i);

		if (cpu->trap_port == RTL8365MB_MAX_NUM_PORTS)
			cpu->trap_port = i;
	}
	cpu->enable = cpu->mask > 0;
	ret = rtl8365mb_cpu_config(priv);
	if (ret)
		goto out_teardown_irq;

	/* Configure ports */
	for (i = 0; i < priv->num_ports; i++) {
		struct rtl8365mb_port *p = &mb->ports[i];

		if (dsa_is_unused_port(priv->ds, i))
			continue;

		/* Forward only to the CPU */
		if (uc_optin) {
			struct rt3000_uc_reg_io io = {
				.ctx = priv, .read = rtl8365mb_uc_io_read,
				.write = rtl8365mb_uc_io_write,
			};

			ret = rt3000_uc_write_verify(&io,
				RTL8365MB_PORT_ISOLATION_REG(i), cpu->mask, 0x07ff);
		} else {
			ret = rtl8365mb_port_set_isolation(priv, i, cpu->mask);
		}
		if (ret)
			goto out_teardown_irq;

		/* Disable learning */
		ret = uc_optin ? rtl8365mb_uc_set_learning(priv, i, false) :
			rtl8365mb_port_set_learning(priv, i, false);
		if (ret)
			goto out_teardown_irq;

		/* Set the initial STP state of all ports to DISABLED, otherwise
		 * ports will still forward frames to the CPU despite being
		 * administratively down by default.
		 */
		if (uc_optin) {
			ret = rtl8365mb_uc_set_stp(priv, i, BR_STATE_DISABLED);
			if (ret)
				goto out_teardown_irq;
		} else {
			rtl8365mb_port_stp_state_set(priv->ds, i,
						     BR_STATE_DISABLED);
		}

		/* Set up per-port private data */
		p->priv = priv;
		p->index = i;
	}

	/* Set maximum packet length to 1536 bytes */
	ret = regmap_update_bits(priv->map, RTL8365MB_CFG0_MAX_LEN_REG,
				 RTL8365MB_CFG0_MAX_LEN_MASK,
				 FIELD_PREP(RTL8365MB_CFG0_MAX_LEN_MASK, 1536));
	if (ret)
		goto out_teardown_irq;

	if (priv->setup_interface) {
		ret = priv->setup_interface(ds);
		if (ret) {
			dev_err(priv->dev, "could not set up MDIO bus\n");
			goto out_teardown_irq;
		}
	}

	ret = rtl8365mb_rt3000_age_calibration_setup(priv, mb, cpu->mask);
	if (ret)
		goto out_teardown_irq;

	if (uc_optin) {
		ret = rtl8365mb_uc_enable(ds, mb, cpu->mask);
		if (ret) {
			dev_err(priv->dev,
				"refusing unsafe RTL8367S unicast offload configuration: %d\n",
				ret);
			goto out_teardown_irq;
		}
	}

	/* Start statistics counter polling */
	rtl8365mb_stats_setup(priv);

	return 0;

out_teardown_irq:
	rtl8365mb_irq_teardown(priv);

out_error:
	return ret;
}

static void rtl8365mb_teardown(struct dsa_switch *ds)
{
	struct realtek_priv *priv = ds->priv;
	struct rtl8365mb *mb = priv->chip_data;

	/* Prevent rescheduling and invalidate staged snapshots before waiting. */
	mutex_lock(&mb->uc_lock);
	mb->uc_fdb_sync_ready = false;
	mb->uc_fdb_epoch++;
	mutex_unlock(&mb->uc_lock);
	/* The worker uses rtnl_trylock(), safe when DSA teardown holds RTNL. */
	cancel_delayed_work_sync(&mb->uc_fdb_sync_work);
	kvfree(mb->uc_fdb_rows);
	kvfree(mb->uc_fdb_scan_rows);
	kvfree(mb->uc_fdb_events);
	mb->uc_fdb_rows = NULL;
	mb->uc_fdb_scan_rows = NULL;
	mb->uc_fdb_events = NULL;
	rtl8365mb_stats_teardown(priv);
	rtl8365mb_irq_teardown(priv);
}

static int rtl8365mb_get_chip_id_and_ver(struct regmap *map, u32 *id, u32 *ver)
{
	int ret;

	/* For some reason we have to write a magic value to an arbitrary
	 * register whenever accessing the chip ID/version registers.
	 */
	ret = regmap_write(map, RTL8365MB_MAGIC_REG, RTL8365MB_MAGIC_VALUE);
	if (ret)
		return ret;

	ret = regmap_read(map, RTL8365MB_CHIP_ID_REG, id);
	if (ret)
		return ret;

	ret = regmap_read(map, RTL8365MB_CHIP_VER_REG, ver);
	if (ret)
		return ret;

	/* Reset magic register */
	ret = regmap_write(map, RTL8365MB_MAGIC_REG, 0);
	if (ret)
		return ret;

	return 0;
}

static int rtl8365mb_detect(struct realtek_priv *priv)
{
	struct rtl8365mb *mb = priv->chip_data;
	u32 chip_id;
	u32 chip_ver;
	int ret;

	ret = rtl8365mb_get_chip_id_and_ver(priv->map, &chip_id, &chip_ver);
	if (ret) {
		dev_err(priv->dev, "failed to read chip id and version: %d\n",
			ret);
		return ret;
	}

	switch (chip_id) {
	case RTL8365MB_CHIP_ID_8365MB_VC:
		switch (chip_ver) {
		case RTL8365MB_CHIP_VER_8365MB_VC:
			dev_info(priv->dev,
				 "found an RTL8365MB-VC switch (ver=0x%04x)\n",
				 chip_ver);
			break;
		case RTL8365MB_CHIP_VER_8367RB:
			dev_info(priv->dev,
				 "found an RTL8367RB-VB switch (ver=0x%04x)\n",
				 chip_ver);
			break;
		case RTL8365MB_CHIP_VER_8367S:
			dev_info(priv->dev,
				 "found an RTL8367S switch (ver=0x%04x)\n",
				 chip_ver);
			break;
		default:
			dev_err(priv->dev, "unrecognized switch version (ver=0x%04x)",
				chip_ver);
			return -ENODEV;
		}

		priv->num_ports = RTL8365MB_MAX_NUM_PORTS;

		mb->priv = priv;
		mb->chip_id = chip_id;
		mb->chip_ver = chip_ver;
		mb->port_mask = GENMASK(priv->num_ports - 1, 0);
		mb->learn_limit_max = RTL8365MB_LEARN_LIMIT_MAX;
		mb->jam_table = rtl8365mb_init_jam_8365mb_vc;
		mb->jam_size = ARRAY_SIZE(rtl8365mb_init_jam_8365mb_vc);

		mb->cpu.trap_port = RTL8365MB_MAX_NUM_PORTS;
		mb->cpu.insert = RTL8365MB_CPU_INSERT_TO_ALL;
		mb->cpu.position = RTL8365MB_CPU_POS_AFTER_SA;
		mb->cpu.rx_length = RTL8365MB_CPU_RXLEN_64BYTES;
		mb->cpu.format = RTL8365MB_CPU_FORMAT_8BYTES;

		break;
	default:
		dev_err(priv->dev,
			"found an unknown Realtek switch (id=0x%04x, ver=0x%04x)\n",
			chip_id, chip_ver);
		return -ENODEV;
	}

	return 0;
}

static const struct dsa_switch_ops rtl8365mb_switch_ops_smi = {
	.get_tag_protocol = rtl8365mb_get_tag_protocol,
	.setup = rtl8365mb_setup,
	.teardown = rtl8365mb_teardown,
	.phylink_validate = rtl8365mb_phylink_validate,
	.phylink_mac_config = rtl8365mb_phylink_mac_config,
	.phylink_mac_link_down = rtl8365mb_phylink_mac_link_down,
	.phylink_mac_link_up = rtl8365mb_phylink_mac_link_up,
	.port_stp_state_set = rtl8365mb_port_stp_state_set,
	.get_strings = rtl8365mb_get_strings,
	.get_ethtool_stats = rtl8365mb_get_ethtool_stats,
	.get_sset_count = rtl8365mb_get_sset_count,
};

static const struct dsa_switch_ops rtl8365mb_switch_ops_mdio = {
	.get_tag_protocol = rtl8365mb_get_tag_protocol,
	.setup = rtl8365mb_setup,
	.teardown = rtl8365mb_teardown,
	.phylink_validate = rtl8365mb_phylink_validate,
	.phylink_mac_config = rtl8365mb_phylink_mac_config,
	.phylink_mac_link_down = rtl8365mb_phylink_mac_link_down,
	.phylink_mac_link_up = rtl8365mb_phylink_mac_link_up,
	.phy_read = rtl8365mb_dsa_phy_read,
	.phy_write = rtl8365mb_dsa_phy_write,
	.port_stp_state_set = rtl8365mb_port_stp_state_set,
	.get_strings = rtl8365mb_get_strings,
	.get_ethtool_stats = rtl8365mb_get_ethtool_stats,
	.get_sset_count = rtl8365mb_get_sset_count,
};

static const struct realtek_ops rtl8365mb_ops = {
	.detect = rtl8365mb_detect,
	.phy_read = rtl8365mb_phy_read,
	.phy_write = rtl8365mb_phy_write,
};

const struct realtek_variant rtl8365mb_variant = {
	.ds_ops_smi = &rtl8365mb_switch_ops_smi,
	.ds_ops_mdio = &rtl8365mb_switch_ops_mdio,
	.ops = &rtl8365mb_ops,
	.clk_delay = 10,
	.cmd_read = 0xb9,
	.cmd_write = 0xb8,
	.chip_data_sz = sizeof(struct rtl8365mb),
};
EXPORT_SYMBOL_GPL(rtl8365mb_variant);

MODULE_AUTHOR("Alvin Šipraga <alsi@bang-olufsen.dk>");
MODULE_DESCRIPTION("Driver for RTL8365MB-VC ethernet switch");
MODULE_LICENSE("GPL");
