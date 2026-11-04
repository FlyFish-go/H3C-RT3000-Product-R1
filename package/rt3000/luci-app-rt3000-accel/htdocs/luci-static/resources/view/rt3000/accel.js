'use strict';
'require view';
'require form';
'require fs';
'require poll';

function readStatus() {
	return fs.exec_direct('/usr/libexec/rt3000-accel-status', [], 'json').catch(function() {
		return null;
	});
}

function describe(st) {
	if (!st || !st.loaded)
		return _('Not available: the NSS acceleration module is not loaded.');
	if (st.paused == 'off')
		return _('Off: all traffic is handled by the CPU.');
	if (st.paused == 'sqm')
		return _('Paused while SQM (QoS) is enabled: SQM cannot shape accelerated traffic.');
	return _('Running') + ' - ' + _('accelerated connections') + ': ' +
		(st.accelerated_ipv4 + st.accelerated_ipv6) +
		' (IPv4 ' + st.accelerated_ipv4 + ', IPv6 ' + st.accelerated_ipv6 + '), ' +
		_('tracked connections') + ': ' + st.connections;
}

return view.extend({
	load: function() {
		return readStatus();
	},

	render: function(st) {
		var m, s, o;

		m = new form.Map('ecm', _('Hardware Acceleration'),
			_('NSS offloads routed and bridged traffic from the CPU. Keep it on for full speed. Switch it off only to troubleshoot or to compare; SQM (QoS) pauses it automatically while enabled.'));

		s = m.section(form.NamedSection, 'global', 'ecm');
		s.addremove = false;

		o = s.option(form.DummyValue, '_status', _('Status'));
		o.rawhtml = false;
		o.cfgvalue = function() { return describe(st); };
		o.render = function() {
			var node = form.DummyValue.prototype.render.apply(this, arguments);
			poll.add(function() {
				return readStatus().then(function(cur) {
					node.then(function(el) {
						var v = el.querySelector('.cbi-value-field');
						if (v) v.textContent = describe(cur);
					});
				});
			}, 5);
			return node;
		};

		o = s.option(form.Flag, 'enabled', _('Enable hardware acceleration'),
			_('Takes effect at once, no reboot needed. Default: on.'));
		o.default = '1';
		o.rmempty = false;

		return m.render();
	}
});
