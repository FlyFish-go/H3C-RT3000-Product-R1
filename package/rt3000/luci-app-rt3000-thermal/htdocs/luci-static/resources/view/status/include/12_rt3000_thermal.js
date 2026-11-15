'use strict';
'require baseclass';
'require fs';

return baseclass.extend({
	title: _('Temperatures (H3C Magic)'),

	load: function() {
		return L.resolveDefault(fs.exec_direct('/usr/libexec/rt3000-thermal'), '').then(function(out) {
			try { return JSON.parse(out); } catch (e) { return null; }
		});
	},

	render: function(data) {
		if (!data || (!(data.cpu || []).length && !(data.wifi || []).length))
			return null;

		var rows = [], table = E('table', { 'class': 'table' });

		if ((data.cpu || []).length)
			rows.push([ _('SoC (hottest sensor)'), '%d °C'.format(Math.max.apply(null, data.cpu)) ]);

		(data.wifi || []).slice().sort(function(a, b) { return parseFloat(a.band) - parseFloat(b.band); }).forEach(function(w) {
			rows.push([ _('Wi-Fi %s GHz radio').format(w.band), '%d °C'.format(w.temp) ]);
		});

		rows.forEach(function(r) {
			table.appendChild(E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td left', 'width': '33%' }, [ r[0] ]),
				E('td', { 'class': 'td left' }, [ r[1] ])
			]));
		});

		return table;
	}
});
