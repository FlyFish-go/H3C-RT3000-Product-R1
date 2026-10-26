/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Narrow RTL8367S known-unicast offload helpers.
 *
 * The L2/CVLAN table encodings below are adapted from Linux upstream
 * rtl8365mb_{l2,vlan,table}.c at fd179f8a05be3ccae366b9b96e176b51fbe54aab
 * (Copyright (C) 2022 Alvin Sipraga). The surrounding bridge policy and
 * fail-closed sequencing are Machine-C additions.
 */
#ifndef _RTL8367S_UC_OFFLOAD_H
#define _RTL8367S_UC_OFFLOAD_H

#define RT3000_UC_MAX_PORTS 11
#define RT3000_UC_CPU_PORT 6
#define RT3000_UC_FLOOD_UC 0x0890
#define RT3000_UC_FLOOD_MC 0x0891
#define RT3000_UC_FLOOD_BC 0x0892
#define RT3000_UC_ISOLATION 0x08a2
#define RT3000_UC_LEARN_LIMIT 0x0a20
#define RT3000_UC_STP 0x0a00
#define RT3000_UC_EFID 0x0a32
#define RT3000_UC_VLAN_TRANSPARENT 0x09d0
#define RT3000_UC_CPU_MASK (1U << RT3000_UC_CPU_PORT)
#define RT3000_UC_TABLE_CVLAN_READ 0x0003
#define RT3000_UC_TABLE_CVLAN_WRITE 0x000b
#define RT3000_UC_TABLE_L2_LOOKUP 0x0004
#define RT3000_UC_TABLE_WRITE_L2 0x000c
#define RT3000_UC_TABLE_READ_UC_PORT 0x0074

/* Kept free of kernel types so the same transaction code is exercised by the
 * host-side mock-regmap test. Callbacks return zero or a negative errno.
 */
struct rt3000_uc_reg_io {
	void *ctx;
	int (*read)(void *ctx, unsigned int reg, unsigned int *val);
	int (*write)(void *ctx, unsigned int reg, unsigned int val);
};

struct rt3000_uc_l2_words {
	unsigned char mac[6];
	unsigned char port;
	unsigned char age;
	unsigned char efid;
	unsigned char fid;
	unsigned short vid;
	unsigned char is_static;
	unsigned char ivl;
};

static inline void rt3000_uc_l2_encode(const struct rt3000_uc_l2_words *e,
				       unsigned short d[6])
{
	d[0] = e->mac[5] | ((unsigned short)e->mac[4] << 8);
	d[1] = e->mac[3] | ((unsigned short)e->mac[2] << 8);
	d[2] = e->mac[1] | ((unsigned short)e->mac[0] << 8);
	d[3] = (e->vid & 0x0fff) | ((unsigned short)(e->ivl & 1) << 13) |
	       ((unsigned short)(e->port >> 3) << 15);
	d[4] = (e->efid & 0x7) | ((unsigned short)(e->fid & 0xf) << 3) |
	       ((unsigned short)(e->port & 0x7) << 8) |
	       ((unsigned short)(e->age & 0x7) << 11);
	d[5] = (unsigned short)(e->is_static & 1) << 5;
}

static inline void rt3000_uc_l2_decode(const unsigned short d[6],
				       struct rt3000_uc_l2_words *e)
{
	e->mac[5] = d[0] & 0xff; e->mac[4] = d[0] >> 8;
	e->mac[3] = d[1] & 0xff; e->mac[2] = d[1] >> 8;
	e->mac[1] = d[2] & 0xff; e->mac[0] = d[2] >> 8;
	e->vid = d[3] & 0x0fff;
	e->fid = (d[4] >> 3) & 0xf;
	e->ivl = !!(d[3] & (1U << 13));
	e->port = ((d[4] >> 8) & 7) | (((d[3] >> 15) & 1) << 3);
	e->efid = d[4] & 7;
	e->age = (d[4] >> 11) & 7;
	e->is_static = !!(d[5] & (1U << 5));
}

static inline int rt3000_uc_write_verify(const struct rt3000_uc_reg_io *io,
					 unsigned int reg,
					 unsigned int value,
					 unsigned int mask)
{
	unsigned int got;
	int ret;

	ret = io->write(io->ctx, reg, value);
	if (ret)
		return ret;
	ret = io->read(io->ctx, reg, &got);
	if (ret)
		return ret;
	return (got & mask) == (value & mask) ? 0 : -5; /* -EIO */
}

static inline int rt3000_uc_set_flood_cpu_only(
		const struct rt3000_uc_reg_io *io, unsigned int cpu_mask)
{
	static const unsigned int regs[] = {
		RT3000_UC_FLOOD_UC, RT3000_UC_FLOOD_MC, RT3000_UC_FLOOD_BC,
	};
	unsigned int i;
	int ret;

	for (i = 0; i < sizeof(regs) / sizeof(regs[0]); i++) {
		ret = rt3000_uc_write_verify(io, regs[i], cpu_mask, 0x07ff);
		if (ret)
			return ret;
	}
	return 0;
}

static inline unsigned int rt3000_uc_peer_mask(unsigned int members,
						       unsigned int port,
						       unsigned int cpu_mask)
{
	return cpu_mask | (members & ~(1U << port));
}

/* Transaction used by the driver bridge-join callback and host fault tests. */
static inline int rt3000_uc_program_peer_matrix(
		const struct rt3000_uc_reg_io *io, unsigned int available,
		unsigned int cpu_mask, unsigned int next_members,
		unsigned int *committed_members, int *terminal_fault)
{
	unsigned int port;
	int ret;

	for (port = 0; port < RT3000_UC_MAX_PORTS; port++) {
		unsigned int mask;

		if (!(available & (1U << port)))
			continue;
		mask = (next_members & (1U << port)) ?
			rt3000_uc_peer_mask(next_members, port, cpu_mask) : cpu_mask;
		ret = rt3000_uc_write_verify(io, RT3000_UC_ISOLATION + port,
					     mask, 0x07ff);
		if (ret)
			goto fault;
	}
	*committed_members = next_members;
	return 0;

fault:
	/* Best effort only: a failed bus write prevents a safety guarantee. */
	for (port = 0; port < RT3000_UC_MAX_PORTS; port++) {
		if (!(available & (1U << port)))
			continue;
		io->write(io->ctx, RT3000_UC_ISOLATION + port, cpu_mask);
		io->write(io->ctx, RT3000_UC_LEARN_LIMIT + port, 0);
	}
	*terminal_fault = 1;
	return ret;
}

static inline int rt3000_uc_dump_wrapped(unsigned int start,
					 unsigned int next)
{
	return next < start;
}

static inline int rt3000_uc_table_data_words(unsigned int command)
{
	switch (command & 0x7) {
	case 3:
		return 3;
	case 4:
		return 6;
	default:
		return -1;
	}
}

#ifdef __KERNEL__
#include <linux/etherdevice.h>
#include <linux/regmap.h>
#include <linux/if_bridge.h>
#include <linux/if_vlan.h>
#include <linux/netlink.h>
#include <linux/netdevice.h>
#include "realtek.h"

/* RTL8365MB-family shared L2 table interface, matching the Linux upstream
 * rtl8365mb_table.c encoding. Stage-1 uses only 6-word L2 entries.
 */
#define RTL8367S_UC_TABLE_CTRL 0x0500
#define RTL8367S_UC_TABLE_ADDR 0x0501
#define RTL8367S_UC_TABLE_STATUS 0x0502
#define RTL8367S_UC_TABLE_WRITE 0x0510
#define RTL8367S_UC_TABLE_READ 0x0520
#define RTL8367S_UC_TABLE_BUSY BIT(13)
#define RTL8367S_UC_TABLE_HIT BIT(12)
#define RTL8367S_UC_TABLE_ADDR_MASK GENMASK(10, 0)
#define RTL8367S_UC_TABLE_ADDR_EXT BIT(14)
#define RTL8367S_UC_TABLE_WRITE_L2 RT3000_UC_TABLE_WRITE_L2
#define RTL8367S_UC_TABLE_READ_UC_PORT RT3000_UC_TABLE_READ_UC_PORT
#define RTL8367S_UC_TABLE_CVLAN_WRITE RT3000_UC_TABLE_CVLAN_WRITE
#define RTL8367S_UC_TABLE_CVLAN_READ RT3000_UC_TABLE_CVLAN_READ
#define RTL8367S_UC_L2_WORDS 6
#define RTL8367S_UC_CVLAN_WORDS 3
#define RTL8367S_UC_FID_EFID 1
#define RTL8367S_UC_VID 0

struct rtl8367s_uc_l2 {
	u8 mac[ETH_ALEN];
	u8 port;
	u8 age;
	bool is_static;
	bool ivl;
	u16 vid;
	u8 efid;
	u8 fid;
};

static inline void rtl8367s_uc_l2_encode(const struct rtl8367s_uc_l2 *e,
					 u16 d[RTL8367S_UC_L2_WORDS])
{
	struct rt3000_uc_l2_words words = {
		.port = e->port, .age = e->age, .efid = e->efid,
		.fid = e->fid, .vid = e->vid, .is_static = e->is_static,
		.ivl = e->ivl,
	};

	memcpy(words.mac, e->mac, ETH_ALEN);
	rt3000_uc_l2_encode(&words, d);
}

static inline void rtl8367s_uc_l2_decode(const u16 d[RTL8367S_UC_L2_WORDS],
					 struct rtl8367s_uc_l2 *e)
{
	struct rt3000_uc_l2_words words;

	rt3000_uc_l2_decode(d, &words);
	memcpy(e->mac, words.mac, ETH_ALEN);
	e->vid = words.vid;
	e->fid = words.fid;
	e->ivl = words.ivl;
	e->port = words.port;
	e->efid = words.efid;
	e->age = words.age;
	e->is_static = words.is_static;
}

static inline int rtl8367s_uc_table_wait(struct realtek_priv *priv)
{
	u32 val;
	return regmap_read_poll_timeout(priv->map_nolock, RTL8367S_UC_TABLE_STATUS,
					val, !(val & RTL8367S_UC_TABLE_BUSY), 10, 10000);
}

static inline int rtl8367s_uc_table_access(struct realtek_priv *priv,
					   u32 command, u16 *addr,
					   u16 *data, bool write_data,
					   bool read_data)
{
	u32 status;
	int words = rt3000_uc_table_data_words(command);
	int ret;

	if (words < 0)
		return -EINVAL;

	mutex_lock(&priv->map_lock);
	ret = rtl8367s_uc_table_wait(priv);
	if (ret)
		goto out;
	if (write_data) {
		ret = regmap_bulk_write(priv->map_nolock, RTL8367S_UC_TABLE_WRITE,
					data, words);
		if (ret)
			goto out;
	}
	if (addr) {
		ret = regmap_write(priv->map_nolock, RTL8367S_UC_TABLE_ADDR,
				   *addr & 0x1fff);
		if (ret)
			goto out;
	}
	ret = regmap_write(priv->map_nolock, RTL8367S_UC_TABLE_CTRL, command);
	if (ret)
		goto out;
	ret = rtl8367s_uc_table_wait(priv);
	if (ret)
		goto out;
	if ((command & 0x7) == 4) {
		ret = regmap_read(priv->map_nolock, RTL8367S_UC_TABLE_STATUS,
				  &status);
		if (ret)
			goto out;
		if (!(status & RTL8367S_UC_TABLE_HIT)) {
			ret = -ENOENT;
			goto out;
		}
		if (addr)
			*addr = (status & RTL8367S_UC_TABLE_ADDR_MASK) |
				((status & RTL8367S_UC_TABLE_ADDR_EXT) ? BIT(11) : 0);
	}
	if (read_data)
		ret = regmap_bulk_read(priv->map_nolock, RTL8367S_UC_TABLE_READ,
				       data, words);
out:
	mutex_unlock(&priv->map_lock);
	return ret;
}

static inline int rtl8367s_uc_cvlan_access(struct realtek_priv *priv,
					   u16 vid, u16 data[3], bool write)
{
	int ret;

	ret = rtl8367s_uc_table_access(priv,
		write ? RTL8367S_UC_TABLE_CVLAN_WRITE :
			RTL8367S_UC_TABLE_CVLAN_READ,
		&vid, data, write, !write);
	return ret;
}

static inline void rtl8367s_uc_cvlan_encode(u16 member, u16 data[3])
{
	/* D0: member[7:0], untag[7:0]=0; D1: FID=0 and IVL/SVL=0;
	 * D2: member[10:8], untag[10:8]=0; all other fields stay zero.
	 */
	data[0] = member & 0x00ff;
	data[1] = 0;
	data[2] = (member >> 8) & 0x0007;
}

static inline int rtl8367s_uc_l2_write(struct realtek_priv *priv,
				       struct rtl8367s_uc_l2 *entry)
{
	u16 data[RTL8367S_UC_L2_WORDS];
	rtl8367s_uc_l2_encode(entry, data);
	return rtl8367s_uc_table_access(priv, RTL8367S_UC_TABLE_WRITE_L2,
					NULL, data, true, false);
}

static inline int rtl8367s_uc_l2_read_key(struct realtek_priv *priv,
					  struct rtl8367s_uc_l2 *entry)
{
	u16 data[RTL8367S_UC_L2_WORDS];
	int ret;

	rtl8367s_uc_l2_encode(entry, data);
	ret = rtl8367s_uc_table_access(priv, RT3000_UC_TABLE_L2_LOOKUP,
				       NULL, data, true, true);
	if (!ret)
		rtl8367s_uc_l2_decode(data, entry);
	return ret;
}

#endif /* __KERNEL__ */
#endif /* _RTL8367S_UC_OFFLOAD_H */
