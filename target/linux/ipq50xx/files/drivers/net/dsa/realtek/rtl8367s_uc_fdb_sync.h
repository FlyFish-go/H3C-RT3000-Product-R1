/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTL8367S_UC_FDB_SYNC_H
#define _RTL8367S_UC_FDB_SYNC_H

/*
 * Pure global-MAC snapshot diff for the opt-in RTL8367S dynamic-unicast
 * mirror. Callers must sort rows lexicographically by MAC before diffing.
 * A move is represented by ADD at the new owner only; DEL is MAC-global in
 * bridge switchdev and must not follow a move.
 */
#define RT3000_UC_FDB_SYNC_ADD 1
#define RT3000_UC_FDB_SYNC_DEL 2
#define RT3000_UC_FDB_EAGAIN -11
#define RT3000_UC_FDB_ENOENT -2
#define RT3000_UC_FDB_EEXIST -17

struct rt3000_uc_fdb_row {
	unsigned char mac[6];
	unsigned char port;
};

struct rt3000_uc_fdb_event {
	unsigned char mac[6];
	unsigned char port;
	unsigned char action;
};

static inline int rt3000_uc_fdb_mac_cmp(const unsigned char a[6],
					const unsigned char b[6])
{
	unsigned int i;

	for (i = 0; i < 6; i++) {
		if (a[i] < b[i])
			return -1;
		if (a[i] > b[i])
			return 1;
	}
	return 0;
}

/* Rows are global-MAC keyed. Any duplicate MAC makes a scan untrustworthy. */
static inline int rt3000_uc_fdb_rows_valid(
		const struct rt3000_uc_fdb_row *rows, unsigned int count)
{
	unsigned int i;

	for (i = 1; i < count; i++)
		if (rt3000_uc_fdb_mac_cmp(rows[i - 1].mac, rows[i].mac) >= 0)
			return 0;
	return 1;
}

/*
 * Produce idempotent ADD/refresh events and true deletions from two complete
 * snapshots. The hardware row is re-announced each full scan so software FDB
 * flushes or ownership transitions can be repaired.
 * The output capacity must be at least old_count + new_count. No caller state
 * is changed; the caller commits the new snapshot only after applying events.
 */
static inline int rt3000_uc_fdb_diff(
		const struct rt3000_uc_fdb_row *old_rows, unsigned int old_count,
		const struct rt3000_uc_fdb_row *new_rows, unsigned int new_count,
		struct rt3000_uc_fdb_event *events, unsigned int event_capacity,
		unsigned int *event_count)
{
	unsigned int old_i = 0, new_i = 0, count = 0, j;

	if (!event_count || (!old_rows && old_count) ||
	    (!new_rows && new_count) || (!events && event_capacity) ||
	    !rt3000_uc_fdb_rows_valid(old_rows, old_count) ||
	    !rt3000_uc_fdb_rows_valid(new_rows, new_count))
		return -22; /* -EINVAL */
	if (event_capacity < old_count + new_count)
		return -28; /* -ENOSPC */

	/* Emit adds and moves first, so a protected add cannot follow a delete. */
	old_i = 0;
	new_i = 0;
	while (new_i < new_count) {
		while (old_i < old_count &&
		       rt3000_uc_fdb_mac_cmp(old_rows[old_i].mac,
					     new_rows[new_i].mac) < 0)
			old_i++;

		events[count].action = RT3000_UC_FDB_SYNC_ADD;
		events[count].port = new_rows[new_i].port;
		for (j = 0; j < 6; j++)
			events[count].mac[j] = new_rows[new_i].mac[j];
		count++;
		new_i++;
	}

	/* Deletes are strictly for MACs absent from the complete new snapshot. */
	old_i = 0;
	new_i = 0;
	while (old_i < old_count) {
		int cmp;

		while (new_i < new_count &&
		       rt3000_uc_fdb_mac_cmp(new_rows[new_i].mac,
					     old_rows[old_i].mac) < 0)
			new_i++;
		if (new_i == new_count)
			cmp = -1;
		else
			cmp = rt3000_uc_fdb_mac_cmp(old_rows[old_i].mac,
						    new_rows[new_i].mac);

		if (cmp < 0) {
			events[count].action = RT3000_UC_FDB_SYNC_DEL;
			events[count].port = old_rows[old_i].port;
			for (j = 0; j < 6; j++)
				events[count].mac[j] = old_rows[old_i].mac[j];
			count++;
		}
		old_i++;
	}

	*event_count = count;
	return 0;
}

typedef int (*rt3000_uc_fdb_notify_fn)(
		void *ctx, const struct rt3000_uc_fdb_event *event);
typedef int (*rt3000_uc_fdb_commit_fn)(
		void *ctx, const struct rt3000_uc_fdb_row *rows,
		unsigned int count);

/* Apply a validated snapshot. No event or commit is allowed for an
 * incomplete scan. Protected ADDs and already-gone DELs are safe per-key
 * skips; other notifier errors preserve the prior snapshot for retry.
 */
static inline int rt3000_uc_fdb_sync_apply(
		int scan_complete,
		const struct rt3000_uc_fdb_row *old_rows, unsigned int old_count,
		const struct rt3000_uc_fdb_row *new_rows, unsigned int new_count,
		struct rt3000_uc_fdb_event *events, unsigned int event_capacity,
		rt3000_uc_fdb_notify_fn notify,
		rt3000_uc_fdb_commit_fn commit, void *ctx)
{
	unsigned int event_count, i;
	int ret;

	if (!scan_complete)
		return RT3000_UC_FDB_EAGAIN;
	if (!notify || !commit)
		return -22; /* -EINVAL */
	ret = rt3000_uc_fdb_diff(old_rows, old_count, new_rows, new_count,
				 events, event_capacity, &event_count);
	if (ret)
		return ret;
	for (i = 0; i < event_count; i++) {
		ret = notify(ctx, &events[i]);
		if ((ret == RT3000_UC_FDB_EEXIST &&
		     events[i].action == RT3000_UC_FDB_SYNC_ADD) ||
		    (ret == RT3000_UC_FDB_ENOENT &&
		     events[i].action == RT3000_UC_FDB_SYNC_DEL))
			continue;
		if (ret)
			return ret;
	}

	return commit(ctx, new_rows, new_count);
}

#endif /* _RTL8367S_UC_FDB_SYNC_H */
