// SPDX-License-Identifier: GPL-2.0-only
/*
 * H3C RT3000 (HW-C) RTL8367S port-expander setup.
 *
 * The switch is used without DSA: CPU tagging off, LAN1-3 and CPU port 6 in
 * one forwarding group, port 6 at SGMII 1000/full. h3c-common4 U-Boot already
 * leaves it that way (drivers/net/ipq5018/rtl8367s.c); this driver checks
 * that state and only repeats the same sequence when it is missing.
 *
 * It also registers a read-only swconfig device so LuCI and `swconfig` show
 * per-port link state. The only accepted VLAN layout is the fixed one the
 * hardware has (VLAN 1 = LAN1-3 + CPU, untagged); nothing is reprogrammed.
 */
#include <linux/bitfield.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/kernel.h>
#include <linux/mdio.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_mdio.h>
#include <linux/phy.h>
#include <linux/platform_device.h>
#include <linux/switch.h>

#define RTL_PHY		29
#define R_CTRL0		31
#define R_CTRL1		21
#define R_ADDR		23
#define R_WDATA		24
#define R_RDATA		25
#define OP_ADDR		0x000e
#define OP_READ		0x0001
#define OP_WRITE	0x0003

#define RTL_NUM_PORTS	7
#define RTL_CPU_PORT	6
#define RTL_LAN_MASK	(BIT(1) | BIT(2) | BIT(3) | BIT(RTL_CPU_PORT))

/* Per-port MAC status: [1:0] speed (0=10, 1=100, 2=1000), [2] full duplex,
 * [4] link up.
 */
#define RTL_PORT_STATUS(p)	(0x1352 + (p))
#define RTL_PORT_STATUS_SPEED	GENMASK(1, 0)
#define RTL_PORT_STATUS_DUPLEX	BIT(2)
#define RTL_PORT_STATUS_LINK	BIT(4)

static bool force_init;
module_param(force_init, bool, 0444);
MODULE_PARM_DESC(force_init, "Re-run the switch setup even if it is already configured");

struct rtl_jam {
	u16 reg, val;
};

static const struct rtl_jam jam_8365mb_vc[] = {
	{ 0x13EB, 0x15BB }, { 0x1303, 0x06D6 }, { 0x1304, 0x0700 },
	{ 0x13E2, 0x003F }, { 0x13F9, 0x0090 }, { 0x121E, 0x03CA },
	{ 0x1233, 0x0352 }, { 0x1237, 0x00A0 }, { 0x123A, 0x0030 },
	{ 0x1239, 0x0084 }, { 0x0301, 0x1000 }, { 0x1349, 0x001F },
	{ 0x18E0, 0x4004 }, { 0x122B, 0x241C }, { 0x1305, 0xC000 },
	{ 0x13F0, 0x0000 },
};

static const struct rtl_jam jam_common[] = {
	{ 0x1200, 0x7FCB }, { 0x0884, 0x0003 }, { 0x06EB, 0x0001 },
	{ 0x03Fa, 0x0007 }, { 0x08C8, 0x00C0 }, { 0x0A30, 0x020E },
	{ 0x0800, 0x0000 }, { 0x0802, 0x0000 }, { 0x09DA, 0x0013 },
	{ 0x1D32, 0x0002 },
};

static const struct rtl_jam sds_jam_sgmii[] = {
	{ 0x0480, 0x04D7 }, { 0x0481, 0xF994 }, { 0x0482, 0x2420 },
	{ 0x0483, 0x6960 }, { 0x0484, 0x9728 }, { 0x0423, 0x9D85 },
	{ 0x0424, 0xD810 }, { 0x002E, 0x83F2 },
};

/* LAN ports 1-3 and CPU port 6 share a group; ports 0, 4 and 5 are isolated. */
static const u16 port_masks[7] = {
	0x0001, 0x004e, 0x004e, 0x004e, 0x0010, 0x0020, 0x004e,
};

struct rtlx {
	struct device *dev;
	struct mii_bus *bus;
	struct switch_dev swdev;
};

/* Callers hold bus->mdio_lock. */
static int c22_write(struct rtlx *s, u32 reg, u16 val)
{
	return __mdiobus_write(s->bus, RTL_PHY, reg, val);
}

static int reg_read(struct rtlx *s, u16 reg, u16 *val)
{
	int ret;

	ret = c22_write(s, R_CTRL0, OP_ADDR);
	if (!ret)
		ret = c22_write(s, R_ADDR, reg);
	if (!ret)
		ret = c22_write(s, R_CTRL1, OP_READ);
	if (ret)
		return ret;
	ret = __mdiobus_read(s->bus, RTL_PHY, R_RDATA);
	if (ret < 0)
		return ret;
	*val = ret;
	return 0;
}

static int reg_write(struct rtlx *s, u16 reg, u16 val)
{
	int ret;

	ret = c22_write(s, R_CTRL0, OP_ADDR);
	if (!ret)
		ret = c22_write(s, R_ADDR, reg);
	if (!ret)
		ret = c22_write(s, R_WDATA, val);
	if (!ret)
		ret = c22_write(s, R_CTRL1, OP_WRITE);
	return ret;
}

static int reg_update(struct rtlx *s, u16 reg, u16 mask, u16 val)
{
	u16 old;
	int ret = reg_read(s, reg, &old);

	return ret ? ret : reg_write(s, reg, (old & ~mask) | (val & mask));
}

static int sds_wait(struct rtlx *s)
{
	u16 v;
	int i, ret;

	for (i = 0; i < 100; i++) {
		ret = reg_read(s, 0x6600, &v);
		if (ret)
			return ret;
		if (!(v & 0x0100))
			return 0;
		udelay(10);
	}
	return -ETIMEDOUT;
}

static int sds_write(struct rtlx *s, u16 addr, u16 val)
{
	int ret = sds_wait(s);

	if (!ret)
		ret = reg_write(s, 0x6602, val);
	if (!ret)
		ret = reg_write(s, 0x6601, addr);
	if (!ret)
		ret = reg_write(s, 0x6600, 0x00c0);
	return ret ? ret : sds_wait(s);
}

static int sds_read(struct rtlx *s, u16 addr, u16 *val)
{
	int ret = sds_wait(s);

	if (!ret)
		ret = reg_write(s, 0x6601, addr);
	if (!ret)
		ret = reg_write(s, 0x6600, 0x0080);
	if (!ret)
		ret = sds_wait(s);
	return ret ? ret : reg_read(s, 0x6602, val);
}

static int read_identity(struct rtlx *s, u16 *id, u16 *ver)
{
	int ret, clr;

	/* Chip-ID reads need this temporary magic, as in U-Boot. */
	ret = reg_write(s, 0x13c2, 0x0249);
	if (!ret)
		ret = reg_read(s, 0x1300, id);
	if (!ret)
		ret = reg_read(s, 0x1301, ver);
	clr = reg_write(s, 0x13c2, 0);
	return ret ? ret : clr;
}

/* True when the bootloader's port-expander setup is in place. */
static bool is_configured(struct rtlx *s)
{
	u16 v;
	int i;

	if (reg_read(s, 0x121a, &v) || v != 0x00b5)
		return false;
	if (reg_read(s, 0x0a00, &v) || v != 0x30fc)
		return false;
	if (reg_read(s, 0x1311, &v) || v != 0x1016)
		return false;
	for (i = 0; i < ARRAY_SIZE(port_masks); i++)
		if (reg_read(s, 0x08a2 + i, &v) || v != port_masks[i])
			return false;
	return true;
}

static int sgmii_setup(struct rtlx *s)
{
	u16 option, nway;
	int i, ret, clr;

	ret = reg_write(s, 0x13c0, 0x0249);
	if (ret)
		return ret;
	ret = reg_read(s, 0x13c1, &option);
	clr = reg_write(s, 0x13c0, 0);
	if (ret || clr)
		return ret ? ret : clr;
	if (!option)
		return -EOPNOTSUPP;
	/* Stop DW8051 and bypass before the SGMII sequence; no firmware upload. */
	ret = reg_update(s, 0x1322, 0x0010, 0x0010);
	if (!ret)
		ret = reg_update(s, 0x130c, 0x0020, 0);
	if (!ret)
		ret = reg_update(s, 0x03f7, 0x0002, 0);
	for (i = 0; !ret && i < ARRAY_SIZE(sds_jam_sgmii); i++)
		ret = sds_write(s, sds_jam_sgmii[i].reg, sds_jam_sgmii[i].val);
	if (!ret)
		ret = reg_update(s, 0x1d11, 0x0840, 0x0040);
	if (!ret)
		ret = reg_update(s, 0x1305, 0x00f0, 0x0090);
	if (!ret)
		ret = sds_write(s, 0x0003, 0x7106);
	if (!ret)
		ret = sds_write(s, 0x0000, 0x1401);
	if (!ret)
		ret = sds_write(s, 0x0000, 0x1403);
	if (!ret)
		ret = sds_read(s, 0x0002, &nway);
	if (ret)
		return ret;
	nway = (nway & ~0x0200) | 0x0100;
	return sds_write(s, 0x0002, nway);
}

static int switch_init(struct rtlx *s)
{
	u16 v;
	int i, ret;

	ret = reg_write(s, 0x1322, 0x0001);
	if (ret)
		return ret;
	msleep(100);
	for (i = 0; i < 100; i++) {
		ret = reg_read(s, 0x1322, &v);
		if (ret)
			return ret;
		if (!(v & 1))
			break;
		msleep(10);
	}
	if (i == 100)
		return -ETIMEDOUT;
	for (i = 0; !ret && i < ARRAY_SIZE(jam_8365mb_vc); i++)
		ret = reg_write(s, jam_8365mb_vc[i].reg, jam_8365mb_vc[i].val);
	for (i = 0; !ret && i < ARRAY_SIZE(jam_common); i++)
		ret = reg_write(s, jam_common[i].reg, jam_common[i].val);
	if (!ret)
		ret = sgmii_setup(s);
	/* SGMII link up */
	if (!ret)
		ret = reg_write(s, 0x1311, 0x1016);
	if (!ret)
		ret = reg_update(s, 0x1d11, 0x0780, 0x0700);
	if (!ret)
		ret = reg_write(s, 0x1219, 0x0040);
	/* CPU port enable, insert mode NONE, trap port 6. */
	if (!ret)
		ret = reg_write(s, 0x121a, 0x00b5);
	for (i = 0; !ret && i < ARRAY_SIZE(port_masks); i++)
		ret = reg_write(s, 0x08a2 + i, port_masks[i]);
	/* STP forwarding only on ports 1-3 and CPU 6. */
	if (!ret)
		ret = reg_write(s, 0x0a00, 0x30fc);
	if (!ret)
		ret = reg_update(s, 0x088c, 0x3fff, 1536);
	return ret;
}

static int rtlx_get_port_link(struct switch_dev *swdev, int port,
			      struct switch_port_link *link)
{
	struct rtlx *s = container_of(swdev, struct rtlx, swdev);
	u16 v;
	int ret;

	if (port < 0 || port >= RTL_NUM_PORTS)
		return -EINVAL;
	mutex_lock(&s->bus->mdio_lock);
	ret = reg_read(s, RTL_PORT_STATUS(port), &v);
	mutex_unlock(&s->bus->mdio_lock);
	if (ret)
		return ret;
	link->link = !!(v & RTL_PORT_STATUS_LINK);
	if (!link->link)
		return 0;
	link->duplex = !!(v & RTL_PORT_STATUS_DUPLEX);
	switch (FIELD_GET(RTL_PORT_STATUS_SPEED, v)) {
	case 0:
		link->speed = SWITCH_PORT_SPEED_10;
		break;
	case 1:
		link->speed = SWITCH_PORT_SPEED_100;
		break;
	case 2:
		link->speed = SWITCH_PORT_SPEED_1000;
		break;
	default:
		link->speed = SWITCH_PORT_SPEED_UNKNOWN;
		break;
	}
	return 0;
}

static int rtlx_get_vlan_ports(struct switch_dev *swdev, struct switch_val *val)
{
	int p;

	val->len = 0;
	if (val->port_vlan != 1)
		return 0;
	for (p = 0; p < RTL_NUM_PORTS; p++) {
		if (!(RTL_LAN_MASK & BIT(p)))
			continue;
		val->value.ports[val->len].id = p;
		val->value.ports[val->len].flags = 0;
		val->len++;
	}
	return 0;
}

/* Accept only the layout the hardware already has. */
static int rtlx_set_vlan_ports(struct switch_dev *swdev, struct switch_val *val)
{
	u32 mask = 0;
	int i;

	if (val->port_vlan != 1)
		return val->len ? -EOPNOTSUPP : 0;
	for (i = 0; i < val->len; i++) {
		if (val->value.ports[i].flags & BIT(SWITCH_PORT_FLAG_TAGGED))
			return -EOPNOTSUPP;
		mask |= BIT(val->value.ports[i].id);
	}
	return mask == RTL_LAN_MASK ? 0 : -EOPNOTSUPP;
}

static int rtlx_noop(struct switch_dev *swdev)
{
	return 0;
}

static const struct switch_dev_ops rtlx_switch_ops = {
	.get_vlan_ports = rtlx_get_vlan_ports,
	.set_vlan_ports = rtlx_set_vlan_ports,
	.apply_config = rtlx_noop,
	.reset_switch = rtlx_noop,
	.get_port_link = rtlx_get_port_link,
};

static int rtlx_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *bus_np;
	struct gpio_desc *reset;
	struct rtlx *s;
	u16 id = 0, ver = 0;
	int ret;

	s = devm_kzalloc(dev, sizeof(*s), GFP_KERNEL);
	if (!s)
		return -ENOMEM;
	s->dev = dev;
	bus_np = of_parse_phandle(dev->of_node, "mdio-bus", 0);
	if (!bus_np)
		return -EINVAL;
	s->bus = of_mdio_find_bus(bus_np);
	of_node_put(bus_np);
	if (!s->bus)
		return -EPROBE_DEFER;

	mutex_lock(&s->bus->mdio_lock);
	ret = read_identity(s, &id, &ver);
	if (ret || id != 0x6367 || ver != 0x00a0) {
		dev_err(dev, "no RTL8367S 6367:00a0 (id %04x ver %04x, %d); switch untouched\n",
			id, ver, ret);
		ret = ret ? ret : -ENODEV;
		goto out;
	}
	if (!force_init && is_configured(s)) {
		dev_info(dev, "RTL8367S already configured as port expander\n");
		goto out;
	}

	reset = devm_gpiod_get_optional(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(reset)) {
		ret = PTR_ERR(reset);
		goto out;
	}
	if (reset) {
		gpiod_direction_output(reset, 1);
		msleep(25);
		gpiod_set_value(reset, 0);
		msleep(100);
	}
	ret = switch_init(s);
	if (ret)
		dev_err(dev, "RTL8367S port-expander setup failed: %d\n", ret);
	else
		dev_info(dev, "RTL8367S configured as port expander (SGMII 1000/full)\n");
out:
	mutex_unlock(&s->bus->mdio_lock);
	if (ret)
		goto put_bus;

	s->swdev.name = "RTL8367S";
	s->swdev.alias = "rtl8367s";
	s->swdev.cpu_port = RTL_CPU_PORT;
	s->swdev.ports = RTL_NUM_PORTS;
	s->swdev.vlans = 2;
	s->swdev.ops = &rtlx_switch_ops;
	ret = register_switch(&s->swdev, NULL);
	if (ret) {
		dev_err(dev, "swconfig registration failed: %d\n", ret);
		goto put_bus;
	}
	platform_set_drvdata(pdev, s);
	return 0;

put_bus:
	put_device(&s->bus->dev);
	return ret;
}

static int rtlx_remove(struct platform_device *pdev)
{
	struct rtlx *s = platform_get_drvdata(pdev);

	unregister_switch(&s->swdev);
	put_device(&s->bus->dev);
	return 0;
}

static const struct of_device_id rtlx_of_match[] = {
	{ .compatible = "h3c,rt3000-rtl8367s-expander" },
	{ }
};
MODULE_DEVICE_TABLE(of, rtlx_of_match);

static struct platform_driver rtlx_driver = {
	.probe = rtlx_probe,
	.remove = rtlx_remove,
	.driver = {
		.name = "rtl8367s-expander",
		.of_match_table = rtlx_of_match,
	},
};
module_platform_driver(rtlx_driver);

MODULE_DESCRIPTION("H3C RT3000 HW-C RTL8367S port-expander setup");
MODULE_LICENSE("GPL v2");
