/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_RT3000_FDB_DOMAIN_H
#define _LINUX_RT3000_FDB_DOMAIN_H

/* Pure guard shared by the bridge caller and the host regression test. */
static inline int rt3000_fdb_domain_event_scope(int sync_event,
		unsigned int event_domain, unsigned int *domain)
{
	if (!domain)
		return -22; /* -EINVAL */
	if (!sync_event) {
		*domain = 0;
		return 0;
	}
	if (!event_domain)
		return -22; /* -EINVAL: scoped events require an allocated ID */
	*domain = event_domain;
	return 0;
}

static inline int rt3000_fdb_domain_add_check(unsigned int domain,
		unsigned int entry_domain, int same_port, int external,
		int local, int is_static, int by_user)
{
	if (!domain)
		return 0;
	if (local || is_static || by_user)
		return -17; /* -EEXIST */
	if (external && entry_domain != domain)
		return -17; /* -EEXIST */
	if (!same_port && (!external || entry_domain != domain))
		return -17; /* -EEXIST */
	return 0;
}

static inline int rt3000_fdb_domain_del_check(unsigned int domain,
		unsigned int entry_domain, int same_port, int external,
		int local, int is_static, int by_user)
{
	if (!domain)
		return 0;
	if (!external || entry_domain != domain || !same_port || local ||
	    is_static || by_user)
		return -2; /* -ENOENT */
	return 0;
}

#endif /* _LINUX_RT3000_FDB_DOMAIN_H */
