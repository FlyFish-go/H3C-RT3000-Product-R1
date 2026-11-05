'use strict';
'require baseclass';
'require fs';

/* Shown only when preinit found no 5 GHz FEM in this unit's ART (a D-PCB
 * such as RC3000 B0): the HW-D image then runs the HW-B board data, and the
 * proper image for the unit is HW-B. */
return baseclass.extend({
	title: _('Hardware notice'),

	load: function() {
		return L.resolveDefault(fs.read('/tmp/hwd-cal/fem'), '');
	},

	render: function(fem) {
		if (String(fem || '').trim() != 'nofem')
			return null;

		return E('div', { 'class': 'alert-message warning' }, [
			E('p', {}, '本机 5 GHz 没有外置 FEM（RC3000 B0 这类无 FEM 的 D 板），属于 HW-B。当前 HW-D 固件已自动改用 HW-B 的无线校准数据。'),
			E('p', {}, '建议改刷 HW-B 镜像：在“系统 → 备份/升级”上传 HW-B 的 sysupgrade.bin，并取消“保留配置”（跨机型不保留设置）。'),
			E('p', {}, 'No 5 GHz FEM was found in this unit\'s calibration data, so it belongs to HW-B. This HW-D image is already using the HW-B Wi-Fi board data; please flash the HW-B sysupgrade image without keeping settings.')
		]);
	}
});
