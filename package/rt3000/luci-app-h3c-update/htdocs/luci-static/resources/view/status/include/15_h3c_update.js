'use strict';
'require baseclass';
'require rpc';

/* Status -> Overview: one line about firmware updates. */

var callStatus = rpc.declare({ object: 'h3c.update', method: 'status' });

return baseclass.extend({
	title: _('Firmware Update'),

	load: function() {
		return L.resolveDefault(callStatus(), null);
	},

	render: function(st) {
		var lt = st && st.latest,
		    last = st && st.last,
		    link = L.url('admin/system/h3c-update'),
		    msg;

		if (!st || !st.group)
			return null;

		if (lt && lt.newer)
			msg = E('a', { 'href': link }, E('strong', {}, _('New firmware %s is available. Open the update page').format(lt.version)));
		else if (lt && last && last.ok)
			msg = [ _('Up to date (checked %s)').format(new Date(last.checked * 1000).toLocaleString()), ' · ',
				E('a', { 'href': link }, _('Details')) ];
		else if (st.config && st.config.auto == '1')
			msg = [ _('Automatic check is on, no result yet'), ' · ', E('a', { 'href': link }, _('Details')) ];
		else
			msg = [ _('Automatic check is off'), ' · ', E('a', { 'href': link }, _('Check now')) ];

		return E('table', { 'class': 'table' }, E('tr', { 'class': 'tr' }, [
			E('td', { 'class': 'td left', 'width': '33%' }, '%s %s'.format(st.line == 'nss' ? 'H3C-Magic-NSS' : 'H3C-Magic', st.release)),
			E('td', { 'class': 'td left' }, msg)
		]));
	}
});
