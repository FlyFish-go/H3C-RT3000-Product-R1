'use strict';
'require baseclass';
'require rpc';

/*
 * Status -> Overview: stays hidden unless a newer release has been found
 * (by the automatic check or a manual one).
 */

var callStatus = rpc.declare({ object: 'h3c.update', method: 'status' });

return baseclass.extend({
	title: _('Firmware Update'),

	load: function() {
		return L.resolveDefault(callStatus(), null);
	},

	render: function(st) {
		var lt = st && st.latest;

		if (!st || !st.group || !lt || !lt.newer)
			return null;

		return E('p', {}, [
			_('New firmware %s is available.').format(lt.version), ' ',
			E('a', { 'href': L.url('admin/system/flash/update') }, _('View update'))
		]);
	}
});
