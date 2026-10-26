/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../../target/linux/ipq50xx/files/drivers/net/dsa/realtek/rtl8367s_uc_offload.h"

#define NREG 0x1000

struct mock {
	unsigned int regs[NREG];
	unsigned int fail_reg;
	int fail_write;
	int fail_read;
	int mismatch_read;
};

static int mock_read(void *ctx, unsigned int reg, unsigned int *val)
{
	struct mock *m = ctx;

	if (reg >= NREG)
		return -22;
	if (m->fail_read && reg == m->fail_reg) {
		m->fail_read = 0;
		return -5;
	}
	*val = m->regs[reg];
	if (m->mismatch_read && reg == m->fail_reg) {
		m->mismatch_read = 0;
		*val ^= 1;
	}
	return 0;
}

static int mock_write(void *ctx, unsigned int reg, unsigned int val)
{
	struct mock *m = ctx;

	if (reg >= NREG)
		return -22;
	if (m->fail_write && reg == m->fail_reg) {
		m->fail_write = 0;
		return -5;
	}
	m->regs[reg] = val;
	return 0;
}

static void test_l2_codec(void)
{
	static const unsigned int ports[] = { 0, 6, 8, 10 };
	unsigned int i;

	for (i = 0; i < sizeof(ports) / sizeof(ports[0]); i++) {
		struct rt3000_uc_l2_words in = {
			.mac = { 0x02, 0x11, 0x22, 0x33, 0x44, 0x55 },
			.port = ports[i], .age = 5, .efid = 1, .fid = 0,
			.vid = 0, .is_static = 1, .ivl = 0,
		};
		struct rt3000_uc_l2_words out;
		unsigned short words[6];

		rt3000_uc_l2_encode(&in, words);
		assert(words[3] == (ports[i] >= 8 ? 0x8000 : 0));
		assert((words[4] & 0x0007) == 1);
		assert(((words[4] >> 3) & 0xf) == 0);
		assert(((words[4] >> 8) & 7) == (ports[i] & 7));
		assert(((words[4] >> 11) & 7) == 5);
		assert(words[5] == 0x20);
		rt3000_uc_l2_decode(words, &out);
		assert(!memcmp(in.mac, out.mac, 6));
		assert(in.port == out.port && in.age == out.age);
		assert(in.efid == out.efid && in.fid == out.fid);
		assert(in.vid == out.vid && in.is_static == out.is_static);
		assert(in.ivl == out.ivl);
	}
}

static void test_flood_and_dump_guards(void)
{
	struct mock m = { 0 };
	struct rt3000_uc_reg_io io = {
		.ctx = &m, .read = mock_read, .write = mock_write,
	};

	assert(RT3000_UC_TABLE_CVLAN_READ == 0x0003);
	assert(RT3000_UC_TABLE_CVLAN_WRITE == 0x000b);
	assert(RT3000_UC_TABLE_WRITE_L2 == 0x000c);
	assert(RT3000_UC_TABLE_READ_UC_PORT == 0x0074);
	assert(rt3000_uc_set_flood_cpu_only(&io, 1U << 6) == 0);
	assert(m.regs[0x0890] == (1U << 6));
	assert(m.regs[0x0891] == (1U << 6));
	assert(m.regs[0x0892] == (1U << 6));
	assert(rt3000_uc_table_data_words(RT3000_UC_TABLE_CVLAN_READ) == 3);
	assert(rt3000_uc_table_data_words(RT3000_UC_TABLE_CVLAN_WRITE) == 3);
	assert(rt3000_uc_table_data_words(RT3000_UC_TABLE_L2_LOOKUP) == 6);
	assert(rt3000_uc_table_data_words(RT3000_UC_TABLE_READ_UC_PORT) == 6);
	assert(rt3000_uc_table_data_words(0x0005) < 0);
	assert(rt3000_uc_dump_wrapped(2047, 0) == 1);
	assert(rt3000_uc_dump_wrapped(17, 18) == 0);
	/* Consecutive LUT matches: query starts at prior index + 1. */
	assert(rt3000_uc_dump_wrapped(11, 11) == 0);
	assert(rt3000_uc_dump_wrapped(12, 12) == 0);
}

static void test_flood_program_failures(void)
{
	static const unsigned int regs[] = {
		RT3000_UC_FLOOD_UC, RT3000_UC_FLOOD_MC, RT3000_UC_FLOOD_BC,
	};
	unsigned int failed, mode;

	for (failed = 0; failed < sizeof(regs) / sizeof(regs[0]); failed++) {
		for (mode = 0; mode < 3; mode++) {
			struct mock m = { 0 };
			struct rt3000_uc_reg_io io = {
				.ctx = &m, .read = mock_read, .write = mock_write,
			};
			unsigned int i;

			/* Start permissive: every flood class must be verified before
			 * the opt-in driver can replace the DSA callbacks.
			 */
			for (i = 0; i < sizeof(regs) / sizeof(regs[0]); i++)
				m.regs[regs[i]] = 0x07ff;
			m.fail_reg = regs[failed];
			if (mode == 0)
				m.fail_write = 1;
			else if (mode == 1)
				m.fail_read = 1;
			else
				m.mismatch_read = 1;

			assert(rt3000_uc_set_flood_cpu_only(&io, 1U << 6) < 0);
			for (i = 0; i < failed; i++)
				assert(m.regs[regs[i]] == (1U << 6));
			assert(m.regs[regs[failed]] ==
			       (mode == 0 ? 0x07ff : (1U << 6)));
			for (i = failed + 1; i < sizeof(regs) / sizeof(regs[0]); i++)
				assert(m.regs[regs[i]] == 0x07ff);
		}
	}
}

static void test_matrix_success(void)
{
	struct mock m = { 0 };
	struct rt3000_uc_reg_io io = {
		.ctx = &m, .read = mock_read, .write = mock_write,
	};
	unsigned int committed = 1U << 1;
	int fault = 0;
	unsigned int available = (1U << 1) | (1U << 2);
	unsigned int next = (1U << 1) | (1U << 2);

	assert(rt3000_uc_program_peer_matrix(&io, available, 1U << 6,
					     next, &committed, &fault) == 0);
	assert(committed == next && !fault);
	assert(m.regs[0x08a3] == ((1U << 6) | (1U << 2)));
	assert(m.regs[0x08a4] == ((1U << 6) | (1U << 1)));
	assert(m.regs[0x08a8] == 0);
}

static void test_matrix_failures(void)
{
	static const unsigned int ports[] = { 1, 2 };
	unsigned int i, mode;

	for (i = 0; i < sizeof(ports) / sizeof(ports[0]); i++) {
		for (mode = 0; mode < 3; mode++) {
			struct mock m = { 0 };
			struct rt3000_uc_reg_io io = {
				.ctx = &m, .read = mock_read, .write = mock_write,
			};
			unsigned int committed = 1U << 1;
			int fault = 0;
			unsigned int reg = RT3000_UC_ISOLATION + ports[i];
			int ret;

			m.fail_reg = reg;
			if (mode == 0)
				m.fail_write = 1;
			else if (mode == 1)
				m.fail_read = 1;
			else
				m.mismatch_read = 1;
			ret = rt3000_uc_program_peer_matrix(&io,
				(1U << 1) | (1U << 2),
				1U << 6, (1U << 1) | (1U << 2),
				&committed, &fault);
			assert(ret < 0 && fault);
			assert(committed == (1U << 1));
		}
	}
}

int main(void)
{
	test_l2_codec();
	test_flood_and_dump_guards();
	test_flood_program_failures();
	test_matrix_success();
	test_matrix_failures();
	puts("rtl8367s known-unicast offload mock tests: PASS");
	return 0;
}
