#include <linux/bitfield.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_net.h>
#include <linux/phy.h>
#include <linux/switch.h>


#define RESET_TIMEOUT_US				100000
#define INTIF_MDIO_TIMEOUT_US				100000


#define YT9215_FAKE_PHY_ID				0xdeaddead
#define YT9215_FAKE_PHY_ID_MASK				0xffffffff
#define YT9215_CHIP_ID					0x90020000
#define YT9215_CHIP_ID_MASK				0xffff0000


#define MDIO_ADDR_SWITCHID_MASK				GENMASK(3, 2)
#define  MDIO_ADDR_SWITCHID(x)				FIELD_PREP(MDIO_ADDR_SWITCHID_MASK, (x))
#define MDIO_ADDR_AD_MASK				GENMASK(1, 1)
#define  MDIO_ADDR_AD(x)				FIELD_PREP(MDIO_ADDR_AD_MASK, (x))
#define  MDIO_ADDR_AD_ADDR				MDIO_ADDR_AD(0)
#define  MDIO_ADDR_AD_DATA				MDIO_ADDR_AD(1)
#define MDIO_ADDR_RW_MASK				GENMASK(0, 0)
#define  MDIO_ADDR_RW(x)				FIELD_PREP(MDIO_ADDR_RW_MASK, (x))
#define  MDIO_ADDR_RW_WRITE				MDIO_ADDR_RW(0)
#define  MDIO_ADDR_RW_READ				MDIO_ADDR_RW(1)


#define RESET_CTRL					0x80000
#define  RESET_CTRL_HW					BIT(31)
#define  RESET_CTRL_SW					BIT(1)

#define FUNC_CTRL					0x80004
#define  FUNC_CTRL_MIB					BIT(1)

#define CHIP_ID						0x80008

#define PORT_IGR_LOOKUP_SVLAN				0x80014

#define EXTIF_CTRL					0x80028
#define  EXTIF_CTRL_EXTIF1_ENABLE			BIT(1)
#define  EXTIF_CTRL_EXTIF0_ENABLE			BIT(0)

#define SGMII_CTRL(port)				(0x8008c + 4 * (port))
#define  SGMII_CTRL_MODE_MASK				GENMASK(9, 7)
#define   SGMII_CTRL_MODE(x)				FIELD_PREP(SGMII_CTRL_MODE_MASK, (x))
#define   SGMII_CTRL_MODE_SGMII_MAC			SGMII_CTRL_MODE(0)
#define   SGMII_CTRL_MODE_SGMII_PHY			SGMII_CTRL_MODE(1)
#define   SGMII_CTRL_MODE_1000BASEX			SGMII_CTRL_MODE(2)
#define   SGMII_CTRL_MODE_100BASEX			SGMII_CTRL_MODE(3)
#define   SGMII_CTRL_MODE_2500BASEX			SGMII_CTRL_MODE(4)
#define   SGMII_CTRL_MODE_BASEX				SGMII_CTRL_MODE(5)
#define   SGMII_CTRL_MODE_DISABLE			SGMII_CTRL_MODE(6)
#define  SGMII_CTRL_LINK				BIT(4)
#define  SGMII_CTRL_DUPLEX_MASK				GENMASK(3, 3)
#define   SGMII_CTRL_DUPLEX(x)				FIELD_PREP(SGMII_CTRL_DUPLEX_MASK, (x))
#define   SGMII_CTRL_DUPLEX_HALF			SGMII_CTRL_DUPLEX(0)
#define   SGMII_CTRL_DUPLEX_FULL			SGMII_CTRL_DUPLEX(1)
#define  SGMII_CTRL_SPEED_MASK				GENMASK(2, 0)
#define   SGMII_CTRL_SPEED(x)				FIELD_PREP(SGMII_CTRL_SPEED_MASK, (x))
#define   SGMII_CTRL_SPEED_10				SGMII_CTRL_SPEED(0)
#define   SGMII_CTRL_SPEED_100				SGMII_CTRL_SPEED(1)
#define   SGMII_CTRL_SPEED_1000				SGMII_CTRL_SPEED(2)
#define   SGMII_CTRL_SPEED_2500				SGMII_CTRL_SPEED(4)

#define PORT_CTRL(port)					(0x80100 + 4 * (port))
#define  PORT_CTRL_FLOWCONTROL_AN			BIT(10)
#define  PORT_CTRL_LINK_AN				BIT(9)
#define  PORT_CTRL_DUPLEX_MASK				GENMASK(7, 7)
#define   PORT_CTRL_DUPLEX(x)				FIELD_PREP(PORT_CTRL_DUPLEX_MASK, (x))
#define   PORT_CTRL_DUPLEX_HALF				PORT_CTRL_DUPLEX(0)
#define   PORT_CTRL_DUPLEX_FULL				PORT_CTRL_DUPLEX(1)
#define  PORT_CTRL_RX_FLOWCONTROL			BIT(6)
#define  PORT_CTRL_TX_FLOWCONTROL			BIT(5)
#define  PORT_CTRL_RX_MAC_EN				BIT(4)
#define  PORT_CTRL_TX_MAC_EN				BIT(3)
#define  PORT_CTRL_SPEED_MASK				GENMASK(2, 0)
#define   PORT_CTRL_SPEED(x)				FIELD_PREP(PORT_CTRL_SPEED_MASK, (x))
#define   PORT_CTRL_SPEED_10				PORT_CTRL_SPEED(0)
#define   PORT_CTRL_SPEED_100				PORT_CTRL_SPEED(1)
#define   PORT_CTRL_SPEED_1000				PORT_CTRL_SPEED(2)
#define   PORT_CTRL_SPEED_2500				PORT_CTRL_SPEED(4)

#define PORT_STATUS(port)				(0x80200 + 4 * (port))
#define  PORT_STATUS_LINK				BIT(8)
#define  PORT_STATUS_DUPLEX_MASK			GENMASK(7, 7)
#define   PORT_STATUS_DUPLEX(x)				FIELD_PREP(PORT_STATUS_DUPLEX_MASK, (x))
#define   PORT_STATUS_DUPLEX_HALF			PORT_STATUS_DUPLEX(0)
#define   PORT_STATUS_DUPLEX_FULL			PORT_STATUS_DUPLEX(1)
#define  PORT_STATUS_RX_FLOWCONTROL			BIT(6)
#define  PORT_STATUS_TX_FLOWCONTROL			BIT(5)
#define  PORT_STATUS_RX_MAC_EN				BIT(4)
#define  PORT_STATUS_TX_MAC_EN				BIT(3)
#define  PORT_STATUS_SPEED_MASK				GENMASK(2, 0)
#define  PORT_STATUS_SPEED(x)				FIELD_PREP(PORT_STATUS_SPEED_MASK, (x))
#define   PORT_STATUS_SPEED_10				PORT_STATUS_SPEED(0)
#define   PORT_STATUS_SPEED_100				PORT_STATUS_SPEED(1)
#define   PORT_STATUS_SPEED_1000			PORT_STATUS_SPEED(2)
#define   PORT_STATUS_SPEED_2500			PORT_STATUS_SPEED(4)

#define EXTIF_SEL					0x80394
#define  EXTIF_SEL_EXTIF0_MASK				GENMASK(1, 1)
#define   EXTIF_SEL_EXTIF0(x)				FIELD_PREP(EXTIF_SEL_EXTIF0_MASK, (x))
#define   EXTIF_SEL_EXTIF0_SERDES			EXTIF_SEL_EXTIF0(0)
#define   EXTIF_SEL_EXTIF0_XMII				EXTIF_SEL_EXTIF0(1)
#define  EXTIF_SEL_EXTIF1_MASK				GENMASK(0, 0)
#define   EXTIF_SEL_EXTIF1(x)				FIELD_PREP(EXTIF_SEL_EXTIF1_MASK, (x))
#define   EXTIF_SEL_EXTIF1_SERDES			EXTIF_SEL_EXTIF1(0)
#define   EXTIF_SEL_EXTIF1_XMII				EXTIF_SEL_EXTIF1(1)

#define MIB_CTRL					0xc0004
#define  MIB_CTRL_OP_CLEAN				BIT(30)
#define  MIB_CTRL_PORT_MASK				GENMASK(6, 3)
#define   MIB_CTRL_PORT(port)				FIELD_PREP(MIB_CTRL_PORT_MASK, (port))
#define  MIB_CTRL_PORT_SEL_MASK				GENMASK(1, 0)
#define   MIB_CTRL_PORT_SEL(x)				FIELD_PREP(MIB_CTRL_PORT_SEL_MASK, (x))
#define   MIB_CTRL_PORT_SEL_ALL				MIB_CTRL_PORT_SEL(0)
#define   MIB_CTRL_PORT_SEL_SINGLE			MIB_CTRL_PORT_SEL(2)

#define MIB_DATA(port, offset)				(0xc0100 + (0x100 * (port)) + (4 * (offset)))

#define INTIF_MDIO_OP					0xf0000
#define  INTIF_MDIO_OP_IDLE				0
#define  INTIF_MDIO_OP_DO				1

#define INTIF_MDIO_CTRL					0xf0004
#define  INTIF_MDIO_CTRL_ADDR_MASK			GENMASK(25, 21)
#define   INTIF_MDIO_CTRL_ADDR(x)			FIELD_PREP(INTIF_MDIO_CTRL_ADDR_MASK, (x))
#define  INTIF_MDIO_CTRL_REG_MASK			GENMASK(20, 16)
#define   INTIF_MDIO_CTRL_REG(x)			FIELD_PREP(INTIF_MDIO_CTRL_REG_MASK, (x))
#define  INTIF_MDIO_CTRL_OP_MASK			GENMASK(3, 2)
#define   INTIF_MDIO_CTRL_OP(x)				FIELD_PREP(INTIF_MDIO_CTRL_OP_MASK, (x))
#define   INTIF_MDIO_CTRL_OP_WRITE			INTIF_MDIO_CTRL_OP(1)
#define   INTIF_MDIO_CTRL_OP_READ			INTIF_MDIO_CTRL_OP(2)

#define INTIF_MDIO_WRITE_DATA				0xf0008

#define INTIF_MDIO_READ_DATA				0xf000c

#define PORT_EGR_CTRL(port)				(0x100000 + 4 * (port))
#define  PORT_EGR_CTRL_CTAG_TPID_SEL_MASK		GENMASK(5, 4)
#define   PORT_EGR_CTRL_CTAG_TPID_SEL(x)		FIELD_PREP(PORT_EGR_CTRL_CTAG_TPID_SEL_MASK, (x))
#define  PORT_EGR_CTRL_STAG_TPID_SEL_MASK		GENMASK(3, 2)
#define   PORT_EGR_CTRL_STAG_TPID_SEL(x)		FIELD_PREP(PORT_EGR_CTRL_STAG_TPID_SEL_MASK, (x))

#define PORT_EGR_VLAN(port)				(0x100080 + 4 * (port))
#define  PORT_EGR_VLAN_STAG_KEEP_MASK			GENMASK(31, 31)
#define   PORT_EGR_VLAN_STAG_KEEP(x)			FIELD_PREP(PORT_EGR_VLAN_STAG_KEEP_MASK, (x))
#define   PORT_EGR_VLAN_STAG_KEEP_ALL			PORT_EGR_VLAN_STAG_KEEP(0)
#define   PORT_EGR_VLAN_STAG_KEEP_TAG_MODE		PORT_EGR_VLAN_STAG_KEEP(1)
#define  PORT_EGR_VLAN_CTAG_KEEP_MASK			GENMASK(30, 30)
#define   PORT_EGR_VLAN_CTAG_KEEPK(x)			FIELD_PREP(PORT_EGR_VLAN_CTAG_KEEP_MASK, (x))
#define   PORT_EGR_VLAN_CTAG_KEEP_ALL			PORT_EGR_VLAN_CTAG_KEEP(0)
#define   PORT_EGR_VLAN_CTAG_KEEP_TAG_MODE		PORT_EGR_VLAN_CTAG_KEEP(1)
#define  PORT_EGR_VLAN_STAG_MODE_MASK			GENMASK(29, 27)
#define   PORT_EGR_VLAN_STAG_MODE(x)			FIELD_PREP(PORT_EGR_VLAN_STAG_MODE_MASK, (x))
#define   PORT_EGR_VLAN_STAG_MODE_UNTAG			PORT_EGR_VLAN_STAG_MODE(0)
#define   PORT_EGR_VLAN_STAG_MODE_TAG			PORT_EGR_VLAN_STAG_MODE(1)
#define   PORT_EGR_VLAN_STAG_MODE_TAG_EXCEPT_PVID	PORT_EGR_VLAN_STAG_MODE(2)
#define   PORT_EGR_VLAN_STAG_MODE_PRIO_TAG		PORT_EGR_VLAN_STAG_MODE(3)
#define   PORT_EGR_VLAN_STAG_MODE_KEEP			PORT_EGR_VLAN_STAG_MODE(4)
#define   PORT_EGR_VLAN_STAG_MODE_LOOKUP		PORT_EGR_VLAN_STAG_MODE(5)
#define  PORT_EGR_VLAN_PVID_SVID_MASK			GENMASK(26, 15)
#define   PORT_EGR_VLAN_PVID_SVID(x)			FIELD_PREP(PORT_EGR_VLAN_PVID_SVID_MASK, (x))
#define  PORT_EGR_VLAN_CTAG_MODE_MASK			GENMASK(14, 12)
#define   PORT_EGR_VLAN_CTAG_MODE(x)			FIELD_PREP(PORT_EGR_VLAN_CTAG_MODE_MASK, (x))
#define   PORT_EGR_VLAN_CTAG_MODE_UNTAG			PORT_EGR_VLAN_CTAG_MODE(0)
#define   PORT_EGR_VLAN_CTAG_MODE_TAG			PORT_EGR_VLAN_CTAG_MODE(1)
#define   PORT_EGR_VLAN_CTAG_MODE_TAG_EXCEPT_PVID	PORT_EGR_VLAN_CTAG_MODE(2)
#define   PORT_EGR_VLAN_CTAG_MODE_PRIO_TAG		PORT_EGR_VLAN_CTAG_MODE(3)
#define   PORT_EGR_VLAN_CTAG_MODE_KEEP			PORT_EGR_VLAN_CTAG_MODE(4)
#define   PORT_EGR_VLAN_CTAG_MODE_LOOKUP		PORT_EGR_VLAN_CTAG_MODE(5)
#define  PORT_EGR_VLAN_PVID_CVID_MASK			GENMASK(11, 0)
#define   PORT_EGR_VLAN_PVID_CVID(x)			FIELD_PREP(PORT_EGR_VLAN_PVID_CVID_MASK, (x))

#define EGR_TPID(x)					(0x100300 + 4 * (x))

#define PORT_IGR_VLAN_FILTER				0x180280

#define PORT_EGR_VLAN_FILTER				0x180598

#define VLAN_CTRL1(vlan)				(0x188000 + 8 * (vlan))
#define  VLAN_CTRL1_MEMBER_MASK				GENMASK(17, 7)
#define   VLAN_CTRL1_MEMBER(x)				FIELD_PREP(VLAN_CTRL1_MEMBER_MASK, (x))

#define VLAN_CTRL2(vlan)				(0x188004 + 8 * (vlan))
#define  VLAN_CTRL2_UNTAG_MEMBER_MASK			GENMASK(18, 8)
#define   VLAN_CTRL2_UNTAG_MEMBER(x)			FIELD_PREP(VLAN_CTRL2_UNTAG_MEMBER_MASK, (x))

#define IGR_TPID(x)					(0x210000 + 4 * (x))

#define PORT_IGR_TPID(port)				(0x210010 + 4 * (port))
#define  PORT_IGR_TPID_STAG_BITMAP_MASK			GENMASK(7, 4)
#define   PORT_IGR_TPID_STAG_BITMAP(x)			FIELD_PREP(PORT_IGR_TPID_STAG_BITMAP_MASK, (x))
#define  PORT_IGR_TPID_CTAG_BITMAP_MASK			GENMASK(3, 0)
#define   PORT_IGR_TPID_CTAG_BITMAP(x)			FIELD_PREP(PORT_IGR_TPID_CTAG_BITMAP_MASK, (x))

#define PORT_IGR_PVID(port)				(0x230010 + 4 * (port))
#define  PORT_IGR_PVID_SVID_MASK			GENMASK(29, 18)
#define   PORT_IGR_PVID_SVID(x)				FIELD_PREP(PORT_IGR_PVID_SVID_MASK, (x))
#define  PORT_IGR_PVID_CVID_MASK			GENMASK(17, 6)
#define   PORT_IGR_PVID_CVID(x)				FIELD_PREP(PORT_IGR_PVID_CVID_MASK, (x))


#ifndef read_poll_timeout
#define read_poll_timeout(op, val, cond, sleep_us, timeout_us, \
				sleep_before_read, args...) \
({ \
	u64 __timeout_us = (timeout_us); \
	unsigned long __sleep_us = (sleep_us); \
	ktime_t __timeout = ktime_add_us(ktime_get(), __timeout_us); \
	might_sleep_if((__sleep_us) != 0); \
	if (sleep_before_read && __sleep_us) \
		usleep_range((__sleep_us >> 2) + 1, __sleep_us); \
	for (;;) { \
		(val) = op(args); \
		if (cond) \
			break; \
		if (__timeout_us && \
		    ktime_compare(ktime_get(), __timeout) > 0) { \
			(val) = op(args); \
			break; \
		} \
		if (__sleep_us) \
			usleep_range((__sleep_us >> 2) + 1, __sleep_us); \
		cpu_relax(); \
	} \
	(cond) ? 0 : -ETIMEDOUT; \
})
#endif


struct yt9215_priv {
	struct mdio_device *mdiodev;
	int switchid;

	struct mii_bus *int_mdio_bus;

	struct switch_dev swdev;
};


static u32 yt9215_smi_read(struct yt9215_priv *priv, int reg)
{
	struct mii_bus *bus = priv->mdiodev->bus;
	int addr = priv->mdiodev->addr;
	u32 val;

	mutex_lock(&bus->mdio_lock);
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_ADDR | MDIO_ADDR_RW_READ), ((reg >> 16) & 0xffff));
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_ADDR | MDIO_ADDR_RW_READ), ((reg >> 0) & 0xffff));
	val = (bus->read(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_DATA | MDIO_ADDR_RW_READ)) & 0xffff) << 16;
	val |= bus->read(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_DATA | MDIO_ADDR_RW_READ)) & 0xffff;
	mutex_unlock(&bus->mdio_lock);

	return val;
}

static int yt9215_smi_write(struct yt9215_priv *priv, int reg, u32 val)
{
	struct mii_bus *bus = priv->mdiodev->bus;
	int addr = priv->mdiodev->addr;

	mutex_lock(&bus->mdio_lock);
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_ADDR | MDIO_ADDR_RW_WRITE), ((reg >> 16) & 0xffff));
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_ADDR | MDIO_ADDR_RW_WRITE), ((reg >> 0) & 0xffff));
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_DATA | MDIO_ADDR_RW_WRITE), ((val >> 16) & 0xffff));
	bus->write(bus, addr, (MDIO_ADDR_SWITCHID(priv->switchid) | MDIO_ADDR_AD_DATA | MDIO_ADDR_RW_WRITE), ((val >> 0) & 0xffff));
	mutex_unlock(&bus->mdio_lock);

	return 0;
}

static int yt9215_smi_rmw(struct yt9215_priv *priv, int reg, u32 mask, u32 val)
{
	u32 v;
	v = yt9215_smi_read(priv, reg);
	v &= ~mask;
	v |= val;
	return yt9215_smi_write(priv, reg, v);
}


static int yt9215_int_mdio_wait(struct yt9215_priv *priv)
{
	u32 val;
	return read_poll_timeout(yt9215_smi_read, val,
				 val == INTIF_MDIO_OP_IDLE,
				 1000, INTIF_MDIO_TIMEOUT_US, false,
				 priv, INTIF_MDIO_OP);
}

static int yt9215_int_mdio_read(struct mii_bus *bus, int addr, int regnum)
{
	struct yt9215_priv *priv = bus->priv;
	int ret;

	ret = yt9215_int_mdio_wait(priv);
	if(ret)
		return ret;

	yt9215_smi_rmw(priv, INTIF_MDIO_CTRL,
		       (INTIF_MDIO_CTRL_OP_MASK | INTIF_MDIO_CTRL_ADDR_MASK
			| INTIF_MDIO_CTRL_REG_MASK),
		       (INTIF_MDIO_CTRL_OP_READ | INTIF_MDIO_CTRL_ADDR(addr)
			| INTIF_MDIO_CTRL_REG(regnum)));

	yt9215_smi_write(priv, INTIF_MDIO_OP, INTIF_MDIO_OP_DO);
	ret = yt9215_int_mdio_wait(priv);
	if(ret)
		return ret;

	return yt9215_smi_read(priv, INTIF_MDIO_READ_DATA);
}

static int yt9215_int_mdio_write(struct mii_bus *bus, int addr, int regnum, u16 val)
{
	struct yt9215_priv *priv = bus->priv;
	int ret;

	ret = yt9215_int_mdio_wait(priv);
	if(ret)
		return ret;

	yt9215_smi_rmw(priv, INTIF_MDIO_CTRL,
		       (INTIF_MDIO_CTRL_OP_MASK | INTIF_MDIO_CTRL_ADDR_MASK
			| INTIF_MDIO_CTRL_REG_MASK),
		       (INTIF_MDIO_CTRL_OP_WRITE | INTIF_MDIO_CTRL_ADDR(addr)
			| INTIF_MDIO_CTRL_REG(regnum)));

	yt9215_smi_write(priv, INTIF_MDIO_WRITE_DATA, val);

	yt9215_smi_write(priv, INTIF_MDIO_OP, INTIF_MDIO_OP_DO);
	ret = yt9215_int_mdio_wait(priv);
	if(ret)
		return ret;

	return 0;
}


static void yt9215_init_ports(struct yt9215_priv *priv)
{
	struct device_node *ports, *port, *fixed;
	struct device *dev = &priv->mdiodev->dev;
	phy_interface_t mode;
	u32 reg, speed, full_duplex;
	u32 val;

	ports = of_get_child_by_name(dev_of_node(dev), "ports");
	if (!ports)
		return;

	for_each_available_child_of_node(ports, port) {
		speed = 0;
		full_duplex = 0;

		if (of_property_read_u32(port, "reg", &reg))
			continue;

		if (reg > priv->swdev.ports)
			continue;

		val = PORT_CTRL_RX_MAC_EN | PORT_CTRL_TX_MAC_EN;
		fixed = of_get_child_by_name(port, "fixed-link");
		if (fixed) {
			if (!of_property_read_u32(fixed, "speed", &speed)) {
				switch (speed) {
					case 10:
						val |= PORT_CTRL_SPEED_10;
						break;
					case 100:
						val |= PORT_CTRL_SPEED_100;
						break;
					case 1000:
						val |= PORT_CTRL_SPEED_1000;
						break;
					case 2500:
						val |= PORT_CTRL_SPEED_2500;
						break;
				}
			}
			if (of_property_read_bool(fixed, "full-duplex")) {
				full_duplex = 1;
				val |= PORT_CTRL_DUPLEX_FULL;
			} else
				val |= PORT_CTRL_DUPLEX_HALF;
			if (of_property_read_bool(fixed, "pause"))
				val |= PORT_CTRL_RX_FLOWCONTROL;
			if (of_property_read_bool(fixed, "asym-pause"))
				val |= PORT_CTRL_TX_FLOWCONTROL;

			/* TODO: phy setting */
		} else { /* !fixed */
			val |= PORT_CTRL_LINK_AN | PORT_CTRL_FLOWCONTROL_AN;
		}
		yt9215_smi_write(priv, PORT_CTRL(reg), val);

		mode = of_get_phy_mode(port);
		switch(mode) {
			case PHY_INTERFACE_MODE_INTERNAL:
				break;
			case PHY_INTERFACE_MODE_SGMII:
			case PHY_INTERFACE_MODE_2500BASEX:
				if (reg != 8)
					break;

				yt9215_smi_rmw(priv, EXTIF_CTRL,
					       EXTIF_CTRL_EXTIF0_ENABLE,
					       EXTIF_CTRL_EXTIF0_ENABLE);
				yt9215_smi_rmw(priv, EXTIF_SEL,
					       EXTIF_SEL_EXTIF1_MASK,
					       EXTIF_SEL_EXTIF1_XMII);
				yt9215_smi_rmw(priv, EXTIF_SEL,
					       EXTIF_SEL_EXTIF0_MASK,
					       EXTIF_SEL_EXTIF0_SERDES);

				val = SGMII_CTRL_LINK;
				switch (mode) {
					case PHY_INTERFACE_MODE_SGMII:
						val |= SGMII_CTRL_MODE_SGMII_PHY;
						break;
					case PHY_INTERFACE_MODE_2500BASEX:
						val |= SGMII_CTRL_MODE_2500BASEX;
						break;
					default: /* avoid warning */
						break;
				}
				switch (speed) {
					case 10:
						val |= SGMII_CTRL_SPEED_10;
						break;
					case 100:
						val |= SGMII_CTRL_SPEED_100;
						break;
					case 1000:
						val |= SGMII_CTRL_SPEED_1000;
						break;
					case 2500:
						val |= SGMII_CTRL_SPEED_2500;
						break;
				}
				if (full_duplex)
					val |= SGMII_CTRL_DUPLEX_FULL;
				else
					val |= SGMII_CTRL_DUPLEX_HALF;
				yt9215_smi_write(priv, SGMII_CTRL(0), val);

				break;
			case PHY_INTERFACE_MODE_RGMII:
			case PHY_INTERFACE_MODE_RGMII_ID:
			case PHY_INTERFACE_MODE_RGMII_RXID:
			case PHY_INTERFACE_MODE_RGMII_TXID:
				/* TODO */
				break;
			default:
				break;
		}
	}
}

static int yt9215_config(struct yt9215_priv *priv)
{
	u32 val;
	int i;

	/* Reset */
	yt9215_smi_write(priv, RESET_CTRL, RESET_CTRL_HW);
	if (read_poll_timeout(yt9215_smi_read, val, val == 0,
			      10000, RESET_TIMEOUT_US, false,
			      priv, RESET_CTRL))
		dev_err(&priv->mdiodev->dev, "reset timeout");

	/* RESET_CTRL_HW is almost same as GPIO hard reset.
	 * So we need this delay.
	 */
	msleep(10);

	/* MIB */
	yt9215_smi_rmw(priv, FUNC_CTRL, FUNC_CTRL_MIB, FUNC_CTRL_MIB);
	yt9215_smi_write(priv, MIB_CTRL, MIB_CTRL_PORT_SEL_ALL | MIB_CTRL_OP_CLEAN);

	/* VLAN */
	yt9215_smi_write(priv, EGR_TPID(0), ETH_P_8021Q);
	yt9215_smi_write(priv, PORT_EGR_VLAN_FILTER, GENMASK(10, 0));

	yt9215_smi_write(priv, IGR_TPID(0), ETH_P_8021Q);
	yt9215_smi_write(priv, IGR_TPID(1), ETH_P_8021AD);
	yt9215_smi_write(priv, PORT_IGR_LOOKUP_SVLAN, 0x00000);
	yt9215_smi_write(priv, PORT_IGR_VLAN_FILTER, GENMASK(10, 0));

	yt9215_smi_write(priv, VLAN_CTRL1(1),
			 VLAN_CTRL1_MEMBER(GENMASK(10, 0)));
	yt9215_smi_write(priv, VLAN_CTRL2(1),
			 VLAN_CTRL2_UNTAG_MEMBER(GENMASK(10, 0)));

	for(i = 0; i < 11; i++) {
		yt9215_smi_write(priv, PORT_EGR_CTRL(i),
				 PORT_EGR_CTRL_CTAG_TPID_SEL(0));
		yt9215_smi_write(priv, PORT_EGR_VLAN(i),
				 (PORT_EGR_VLAN_STAG_MODE_UNTAG |
				  PORT_EGR_VLAN_CTAG_MODE_LOOKUP));

		/* only care about the outer VID */
		yt9215_smi_write(priv, PORT_IGR_TPID(i),
				 (PORT_IGR_TPID_STAG_BITMAP(0) |
				  PORT_IGR_TPID_CTAG_BITMAP(BIT(0) | BIT(1))));
		yt9215_smi_write(priv, PORT_IGR_PVID(i),
				 PORT_IGR_PVID_CVID(1));
	}

	/* MAC */
	yt9215_init_ports(priv);

	return 0;
}


static int yt9215_get_pvid(struct switch_dev *dev, int port, int *vlan)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	*vlan = FIELD_GET(PORT_IGR_PVID_CVID_MASK,
			  yt9215_smi_read(priv, PORT_IGR_PVID(port)));
	return 0;
}

static int yt9215_set_pvid(struct switch_dev *dev, int port, int vlan)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	dev_info(&priv->mdiodev->dev, "Set Port%d default VLAN to %d", port, vlan);
	yt9215_smi_rmw(priv, PORT_IGR_PVID(port),
		       PORT_IGR_PVID_CVID_MASK,
		       PORT_IGR_PVID_CVID(vlan));
	return 0;
}

static int yt9215_get_vlan(struct switch_dev *dev, struct switch_val *val)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	u32 members, untag_members;
	int i, num;

	if (val->port_vlan >= dev->vlans || val->port_vlan < 0)
		return -EINVAL;

	members = FIELD_GET(VLAN_CTRL1_MEMBER_MASK,
			    yt9215_smi_read(priv, VLAN_CTRL1(val->port_vlan)));
	untag_members = FIELD_GET(VLAN_CTRL2_UNTAG_MEMBER_MASK,
				  yt9215_smi_read(priv, VLAN_CTRL2(val->port_vlan)));

	num = 0;
	for(i = 0; i < dev->ports; i++)
		if(members & (1 << i)) {
			val->value.ports[num].id = i;
			val->value.ports[num].flags = (!(untag_members & (1 << i))) << SWITCH_PORT_FLAG_TAGGED;
			num++;
		}
	val->len = num;

	return 0;
}

static int yt9215_set_vlan(struct switch_dev *dev, struct switch_val *val)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	u32 members, untag_members;
	int i;

	dev_info(&priv->mdiodev->dev, "Set VLAN%d members:", val->port_vlan);

	if (val->port_vlan >= dev->vlans || val->port_vlan < 0)
		return -EINVAL;

	members = 0;
	untag_members = 0;
	for(i = 0; i < val->len; i++) {
		members |= 1 << val->value.ports[i].id;
		if (!(val->value.ports[i].flags & (1 << SWITCH_PORT_FLAG_TAGGED)))
			untag_members |= 1 << val->value.ports[i].id;

		dev_info(&priv->mdiodev->dev, "\t%d: %s", val->value.ports[i].id,
			 ((val->value.ports[i].flags & (1 << SWITCH_PORT_FLAG_TAGGED)) ? "tag" : "untag"));
	}

	yt9215_smi_write(priv, VLAN_CTRL1(val->port_vlan),
			 VLAN_CTRL1_MEMBER(members));
	yt9215_smi_write(priv, VLAN_CTRL2(val->port_vlan),
			 VLAN_CTRL2_UNTAG_MEMBER(untag_members));

	return 0;
}

// static int yt9215_apply(struct switch_dev *dev)
// {
// 	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
// 	dev_info(&priv->mdiodev->dev, "%s", __FUNCTION__);
// 	return 0;
// }

static int yt9215_reset_switch(struct switch_dev *dev)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	return yt9215_config(priv);
}

static int yt9215_get_link(struct switch_dev *dev, int port,
			   struct switch_port_link *link)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	u32 val;

	val = yt9215_smi_read(priv, PORT_STATUS(port));
	link->aneg = true;
	link->link = (val & PORT_STATUS_RX_MAC_EN) && (val & PORT_STATUS_TX_MAC_EN);
	link->duplex = ((val & PORT_STATUS_DUPLEX_MASK) == PORT_STATUS_DUPLEX_FULL);
	link->tx_flow = !!(val & PORT_STATUS_TX_FLOWCONTROL);
	link->rx_flow = !!(val & PORT_STATUS_RX_FLOWCONTROL);

	if((val & PORT_STATUS_SPEED_MASK) == PORT_STATUS_SPEED_10)
		link->speed = SWITCH_PORT_SPEED_10;
	else if((val & PORT_STATUS_SPEED_MASK) == PORT_STATUS_SPEED_100)
		link->speed = SWITCH_PORT_SPEED_100;
	else if((val & PORT_STATUS_SPEED_MASK) == PORT_STATUS_SPEED_1000)
		link->speed = SWITCH_PORT_SPEED_1000;
	else if((val & PORT_STATUS_SPEED_MASK) == PORT_STATUS_SPEED_2500)
		link->speed = SWITCH_PORT_SPEED_2500;
	else
		link->speed = SWITCH_PORT_SPEED_UNKNOWN;

	return 0;
}

static int yt9215_get_stats(struct switch_dev *dev, int port,
			    struct switch_port_stats *stats)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	stats->tx_bytes = (unsigned long long) yt9215_smi_read(priv, MIB_DATA(port, 33));
	stats->tx_bytes |= (unsigned long long) yt9215_smi_read(priv, MIB_DATA(port, 34)) << 32;
	stats->rx_bytes = (unsigned long long) yt9215_smi_read(priv, MIB_DATA(port, 15));
	stats->rx_bytes |= (unsigned long long) yt9215_smi_read(priv, MIB_DATA(port, 16)) << 32;
	return 0;
}


static int yt9215_port_get_mib(struct switch_dev *dev, const struct switch_attr *attr,
			       struct switch_val *val)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	val->value.i = yt9215_smi_read(priv, MIB_DATA(val->port_vlan, attr->ofs));
	return 0;
}

static int yt9215_port_get_mib_dword(struct switch_dev *dev, const struct switch_attr *attr,
				     struct switch_val *val)
{
	struct yt9215_priv *priv = container_of(dev, struct yt9215_priv, swdev);
	static char buf[64];
	u64 v;

	v = (u64) yt9215_smi_read(priv, MIB_DATA(val->port_vlan, attr->ofs));
	v |= (u64) yt9215_smi_read(priv, MIB_DATA(val->port_vlan, attr->ofs + 1)) << 32;

	val->len = snprintf(buf, sizeof(buf), "%llu", v);
	val->value.s = buf;
	return 0;
}

static struct switch_attr yt9215_global_attrs[] = {
	// {
	// 	.type = SWITCH_TYPE_INT,
	// 	.name = "enable_vlan",
	// 	.description = "Enable VLANs",
	// 	.set = yt9215_set_enable_vlan,
	// 	.get = yt9215_get_enable_vlan,
	// },
};

#define YT9215_PORT_ATTR_MIB(attr, offset)			\
	{							\
		.type = SWITCH_TYPE_INT,			\
		.name = attr,					\
		.description = "Get port's " attr " counters",	\
		.get = yt9215_port_get_mib,			\
		.set = NULL,					\
		.ofs = offset,					\
	}

/* switch_attr doesn't support 64bit int. So we need to use string. */
#define YT9215_PORT_ATTR_MIB_DWORD(attr, offset)		\
	{							\
		.type = SWITCH_TYPE_STRING,			\
		.name = attr,					\
		.description = "Get port's " attr " counters",	\
		.get = yt9215_port_get_mib_dword,		\
		.set = NULL,					\
		.ofs = offset,					\
	}

static struct switch_attr yt9215_port_attrs[] = {
	YT9215_PORT_ATTR_MIB("RX_BROADCAST", 0),
	YT9215_PORT_ATTR_MIB("RX_PAUSE", 1),
	YT9215_PORT_ATTR_MIB("RX_MULTICAST", 2),
	YT9215_PORT_ATTR_MIB("RX_FCS_ERR", 3),
	YT9215_PORT_ATTR_MIB("RX_ALIGNMENT_ERR", 4),
	YT9215_PORT_ATTR_MIB("RX_UNDERSIZE", 5),
	YT9215_PORT_ATTR_MIB("RX_FRAGMENT", 6),
	YT9215_PORT_ATTR_MIB("RX_64B", 7),
	YT9215_PORT_ATTR_MIB("RX_65_127B", 8),
	YT9215_PORT_ATTR_MIB("RX_128_255B", 9),
	YT9215_PORT_ATTR_MIB("RX_256_511B", 10),
	YT9215_PORT_ATTR_MIB("RX_512_1023B", 11),
	YT9215_PORT_ATTR_MIB("RX_1024_1518B", 12),
	YT9215_PORT_ATTR_MIB("RX_JUMBO", 13),
	YT9215_PORT_ATTR_MIB_DWORD("RX_OKBYTE", 15),
	YT9215_PORT_ATTR_MIB_DWORD("RX_NOT_OKBYTE", 17),
	YT9215_PORT_ATTR_MIB("RX_OVERSIZE", 19),
	YT9215_PORT_ATTR_MIB("RX_DISCARD", 20),
	YT9215_PORT_ATTR_MIB("TX_BROADCAST", 21),
	YT9215_PORT_ATTR_MIB("TX_PAUSE", 22),
	YT9215_PORT_ATTR_MIB("TX_MULTICAST", 23),
	YT9215_PORT_ATTR_MIB("TX_UNDERSIZE", 24),
	YT9215_PORT_ATTR_MIB("TX_64B", 25),
	YT9215_PORT_ATTR_MIB("TX_65_127B", 26),
	YT9215_PORT_ATTR_MIB("TX_128_255B", 27),
	YT9215_PORT_ATTR_MIB("TX_256_511B", 28),
	YT9215_PORT_ATTR_MIB("TX_512_1023B", 29),
	YT9215_PORT_ATTR_MIB("TX_1024_1518B", 30),
	YT9215_PORT_ATTR_MIB("TX_JUMBO", 31),
	YT9215_PORT_ATTR_MIB_DWORD("TX_OKBYTE", 33),
	YT9215_PORT_ATTR_MIB("TX_COLLISION", 35),
	YT9215_PORT_ATTR_MIB("TX_EXCESSIVE_COLLISION", 36),
	YT9215_PORT_ATTR_MIB("TX_MULTI_COLLISION", 37),
	YT9215_PORT_ATTR_MIB("TX_SINGLE_COLLISION", 38),
	YT9215_PORT_ATTR_MIB("TX_OK_PKT", 39),
	YT9215_PORT_ATTR_MIB("TX_DEFER", 40),
	YT9215_PORT_ATTR_MIB("TX_LATE_COLLISION", 41),
	YT9215_PORT_ATTR_MIB("RX_OAM_COUNTER", 42),
	YT9215_PORT_ATTR_MIB("TX_OAM_COUNTER", 43),
};

static struct switch_attr yt9215_vlan_attrs[] = {
};

static const struct switch_dev_ops yt9215_ops = {
	.attr_global = {
		.attr = yt9215_global_attrs,
		.n_attr = ARRAY_SIZE(yt9215_global_attrs),
	},
	.attr_port = {
		.attr = yt9215_port_attrs,
		.n_attr = ARRAY_SIZE(yt9215_port_attrs),
	},
	.attr_vlan = {
		.attr = yt9215_vlan_attrs,
		.n_attr = ARRAY_SIZE(yt9215_vlan_attrs),
	},
	.get_port_pvid = yt9215_get_pvid,
	.set_port_pvid = yt9215_set_pvid,
	.get_vlan_ports = yt9215_get_vlan,
	.set_vlan_ports = yt9215_set_vlan,
	// .apply_config = yt9215_apply,
	.reset_switch = yt9215_reset_switch,
	.get_port_link = yt9215_get_link,
	// .set_port_link = yt9215_set_link,
	.get_port_stats = yt9215_get_stats,
};

static int yt9215_smi_probe(struct mdio_device *mdiodev)
{
	struct device *dev = &mdiodev->dev;
	struct yt9215_priv *priv;
	struct switch_dev *swdev;
	static int index;
	u32 chipid;
	int ret;

	priv = kzalloc(sizeof(*priv), GFP_KERNEL);
	if(!priv)
		return -ENOMEM;

	dev_set_drvdata(&mdiodev->dev, priv);
	priv->mdiodev = mdiodev;
	if (!of_property_read_u32(dev_of_node(dev), "switchid", &priv->switchid))
		priv->switchid = 0;

	chipid = yt9215_smi_read(priv, CHIP_ID);
	if ((chipid & YT9215_CHIP_ID_MASK) != YT9215_CHIP_ID)
		dev_err(dev, "chipid incorrect: %08x", chipid);
	else
		dev_info(dev, "detected chipid: %08x", chipid);

	priv->int_mdio_bus = devm_mdiobus_alloc(dev);
	if (priv->int_mdio_bus == NULL)
		goto out_free_priv;

	priv->int_mdio_bus->name = "YT9215 internal mdio";
	priv->int_mdio_bus->read = yt9215_int_mdio_read;
	priv->int_mdio_bus->write = yt9215_int_mdio_write;
	snprintf(priv->int_mdio_bus->id, MII_BUS_ID_SIZE, "YT9215-%d-int", index);
	priv->int_mdio_bus->parent = dev;
	priv->int_mdio_bus->phy_mask = (u32) ~GENMASK(7, 0);
	priv->int_mdio_bus->priv = priv;

	ret = mdiobus_register(priv->int_mdio_bus);
	if(ret < 0)
		goto out_free_priv;

	swdev = &priv->swdev;
	swdev->name = "YT9215";
	swdev->cpu_port = 8;
	swdev->ports = 11;
	swdev->vlans = 4096;
	swdev->ops = &yt9215_ops;
	swdev->alias = dev_name(dev);

	ret = register_switch(swdev, NULL);
	if(ret < 0)
		goto out_unregister_mdio;

	dev_info(dev, "Registered %s as %s\n", swdev->name, swdev->devname);

	ret = yt9215_config(priv);
	if(ret < 0)
		goto out_free_switch;

	index++;
	return 0;

out_free_switch:
	unregister_switch(&priv->swdev);
out_unregister_mdio:
	mdiobus_unregister(priv->int_mdio_bus);
out_free_priv:
	kfree(priv);
	return ret;
}

static void yt9215_smi_remove(struct mdio_device *mdiodev)
{
	struct yt9215_priv *priv = dev_get_drvdata(&mdiodev->dev);
	unregister_switch(&priv->swdev);
	mdiobus_unregister(priv->int_mdio_bus);
	kfree(priv);
	return;
}

static const struct of_device_id yt9215_of_match[] = {
	{ .compatible = "motorcomm,yt9215-smi" },
	{},
};

static struct mdio_driver yt9215_mdio_driver = {
	.probe  = yt9215_smi_probe,
	.remove = yt9215_smi_remove,
	.mdiodrv.driver = {
		.name = "yt9215-smi",
		.of_match_table = yt9215_of_match,
	},
};
mdio_module_driver(yt9215_mdio_driver);
