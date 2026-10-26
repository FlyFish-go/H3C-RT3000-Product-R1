// SPDX-License-Identifier: GPL-2.0-only
/*
 * Minimal RTL8367S identity probe over the QCA MDIO bus.
 *
 * This driver performs the indirect MDIO transport needed to read the chip
 * ID and revision, but does not configure ports, VLANs, or switch forwarding.
 */

#include <linux/errno.h>
#include <linux/mdio.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/phy.h>

#define RTL8367S_PHY_ADDR		29
#define RTL8367S_PHY_CTRL0		31
#define RTL8367S_PHY_CTRL1		21
#define RTL8367S_PHY_ADDR_REG		23
#define RTL8367S_PHY_DATA_WRITE_REG	24
#define RTL8367S_PHY_DATA_READ_REG	25
#define RTL8367S_PHY_OP_ADDR		0x000e
#define RTL8367S_PHY_OP_READ		0x0001
#define RTL8367S_PHY_OP_WRITE		0x0003

#define RTL8367S_REG_CHIP_ID		0x1300
#define RTL8367S_REG_CHIP_VER		0x1301
#define RTL8367S_REG_SDS_MISC		0x1d11
#define RTL8367S_REG_DIGITAL_INTERFACE_SELECT	0x1305
#define RTL8367S_REG_DIGITAL_INTERFACE1_FORCE	0x1311
#define RTL8367S_REG_TO_ECO4		0x1d41
#define RTL8367S_REG_ACCESS_MAGIC	0x13c2
#define RTL8367S_ACCESS_MAGIC		0x0249
#define RTL8367S_CHIP_ID		0x6367
#define RTL8367S_CHIP_VER		0x00a0

/* Caller must hold bus->mdio_lock for the complete indirect transaction. */
static int rtl8367s_read(struct mii_bus *bus, u16 reg, u16 *value)
{
	int ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_CTRL0,
			      RTL8367S_PHY_OP_ADDR);
	if (ret)
		return ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_ADDR_REG,
			      reg);
	if (ret)
		return ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_CTRL1,
			      RTL8367S_PHY_OP_READ);
	if (ret)
		return ret;

	ret = __mdiobus_read(bus, RTL8367S_PHY_ADDR,
			     RTL8367S_PHY_DATA_READ_REG);
	if (ret < 0)
		return ret;
	if (ret == 0xffff)
		return -EIO;

	*value = ret;
	return 0;
}

/* Caller must hold bus->mdio_lock for the complete indirect transaction. */
static int rtl8367s_write_access(struct mii_bus *bus, u16 reg, u16 value)
{
	int ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_CTRL0,
			      RTL8367S_PHY_OP_ADDR);
	if (ret)
		return ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_ADDR_REG,
			      reg);
	if (ret)
		return ret;

	ret = __mdiobus_write(bus, RTL8367S_PHY_ADDR,
			      RTL8367S_PHY_DATA_WRITE_REG, value);
	if (ret)
		return ret;

	return __mdiobus_write(bus, RTL8367S_PHY_ADDR, RTL8367S_PHY_CTRL1,
			       RTL8367S_PHY_OP_WRITE);
}

static int rtl8367s_probe(struct mdio_device *mdiodev)
{
	struct mii_bus *bus = mdiodev->bus;
	u16 chip_id, chip_ver;
	u16 sds_misc = 0, digital_interface_select = 0;
	u16 digital_interface1_force = 0, reg_to_eco4 = 0;
	int sds_misc_ret = 0, digital_interface_select_ret = 0;
	int digital_interface1_force_ret = 0, reg_to_eco4_ret = 0;
	int ret, clear_ret;

	/* This experimental MDIO device is valid only on Machine C. */
	if (!of_machine_is_compatible("h3c,rt3000-rtl8367s"))
		return -ENODEV;

	if (!bus)
		return -EINVAL;

	if (mdiodev->addr != RTL8367S_PHY_ADDR)
		return -EINVAL;

	/* Serialize all pseudo-PHY steps so another MDIO user cannot interleave. */
	mutex_lock(&bus->mdio_lock);

	/*
	 * RTL8367S requires this temporary access-control register write before
	 * ID/version reads.  It changes ASIC access control; it is not a switch
	 * configuration write. Always try to clear it, including after a partial
	 * or failed write, because the controller may have completed the transfer.
	 */
	ret = rtl8367s_write_access(bus, RTL8367S_REG_ACCESS_MAGIC,
				    RTL8367S_ACCESS_MAGIC);
	if (ret)
		goto out_clear;

	ret = rtl8367s_read(bus, RTL8367S_REG_CHIP_ID, &chip_id);
	if (ret)
		goto out_clear;

	ret = rtl8367s_read(bus, RTL8367S_REG_CHIP_VER, &chip_ver);
	if (ret)
		goto out_clear;

	/* Read-only snapshots to locate the external switch/uplink RTL state. */
	sds_misc_ret = rtl8367s_read(bus, RTL8367S_REG_SDS_MISC, &sds_misc);
	digital_interface_select_ret = rtl8367s_read(
		bus, RTL8367S_REG_DIGITAL_INTERFACE_SELECT,
		&digital_interface_select);
	digital_interface1_force_ret = rtl8367s_read(
		bus, RTL8367S_REG_DIGITAL_INTERFACE1_FORCE,
		&digital_interface1_force);
	reg_to_eco4_ret = rtl8367s_read(bus, RTL8367S_REG_TO_ECO4,
					&reg_to_eco4);

out_clear:
	clear_ret = rtl8367s_write_access(bus,
					  RTL8367S_REG_ACCESS_MAGIC, 0);
	if (!ret && clear_ret)
		ret = clear_ret;

	mutex_unlock(&bus->mdio_lock);
	if (ret) {
		dev_err(&mdiodev->dev,
			"identity transaction failed: %d (access-control clear %s)\n",
			ret, clear_ret ? "failed" : "ok");
		return ret;
	}

	if (chip_id != RTL8367S_CHIP_ID || chip_ver != RTL8367S_CHIP_VER) {
		dev_err(&mdiodev->dev,
			"unexpected chip identity %04x:%04x (expected %04x:%04x)\n",
			chip_id, chip_ver, RTL8367S_CHIP_ID, RTL8367S_CHIP_VER);
		return -ENODEV;
	}

	dev_info(&mdiodev->dev, "RTL8367S identity %04x:%04x\n",
		 chip_id, chip_ver);
	dev_info(&mdiodev->dev,
		 "switch diag SDS_MISC=0x%04x(err=%d) "
		 "DIGITAL_INTERFACE_SELECT=0x%04x(err=%d) "
		 "DIGITAL_INTERFACE1_FORCE=0x%04x(err=%d) "
		 "REG_TO_ECO4=0x%04x(err=%d)\n",
		 sds_misc, sds_misc_ret, digital_interface_select,
		 digital_interface_select_ret, digital_interface1_force,
		 digital_interface1_force_ret, reg_to_eco4, reg_to_eco4_ret);
	return 0;
}

static const struct of_device_id rtl8367s_of_match[] = {
	{ .compatible = "realtek,rtl8365mb" },
	{ }
};
MODULE_DEVICE_TABLE(of, rtl8367s_of_match);

static struct mdio_driver rtl8367s_driver = {
	.mdiodrv.driver = {
		.name = "rtl8367s-probe",
		.of_match_table = rtl8367s_of_match,
	},
	.probe = rtl8367s_probe,
};

mdio_module_driver(rtl8367s_driver);

MODULE_DESCRIPTION("Minimal RTL8367S identity probe");
MODULE_AUTHOR("OpenAI Codex");
MODULE_LICENSE("GPL");
