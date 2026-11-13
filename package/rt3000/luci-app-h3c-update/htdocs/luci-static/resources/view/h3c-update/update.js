'use strict';
'require view';
'require form';
'require rpc';
'require ui';
'require uci';
'require poll';
'require dom';

/*
 * Two ways to check:
 *  - "Check from router": the router fetches the signed manifest from GitHub
 *    and Gitee itself (h3c.update check).
 *  - "Check from this browser": this page fetches it through the computer's
 *    own connection (GitHub Pages, Gitee API) and hands it to the router,
 *    which verifies the signature before using it.
 * Downloads and installs are always done by the router.
 */

var callStatus = rpc.declare({ object: 'h3c.update', method: 'status' }),
	callCheck = rpc.declare({ object: 'h3c.update', method: 'check' }),
	callVerify = rpc.declare({ object: 'h3c.update', method: 'verify', params: [ 'source', 'json', 'sig' ] }),
	callDownload = rpc.declare({ object: 'h3c.update', method: 'download' }),
	callCancel = rpc.declare({ object: 'h3c.update', method: 'cancel' }),
	callInstall = rpc.declare({ object: 'h3c.update', method: 'install', params: [ 'keep' ] });

var SOURCE_NAME = { 'github': 'GitHub', 'gitee': 'Gitee' };

function isZh() {
	return (document.documentElement.getAttribute('lang') || '').indexOf('zh') === 0;
}

function fmtTime(ts) {
	return ts ? new Date(ts * 1000).toLocaleString() : '-';
}

function fmtSize(n) {
	return '%.1f MiB'.format((n || 0) / 1048576);
}

function sourceLabel(src) {
	var m = /^(github|gitee)(-browser)?$/.exec(src || '');
	if (!m)
		return src || '-';
	return m[2] ? _('%s (via this browser)').format(SOURCE_NAME[m[1]]) : _('%s (via router)').format(SOURCE_NAME[m[1]]);
}

function resultText(r) {
	switch (r) {
	case 'ok': return _('OK, signature valid');
	case 'fetch': return _('cannot connect');
	case 'notfound': return _('no release list published yet');
	case 'timeout': return _('timed out');
	case 'signature': return _('signature check failed');
	case 'manifest': return _('wrong or damaged release list');
	default: return r || '-';
	}
}

function resultList(results) {
	return E('ul', {}, results.map(function(r) {
		var ok = (r.result == 'ok');
		return E('li', {}, [
			E('strong', {}, SOURCE_NAME[r.source] || r.source), ': ',
			E('span', { 'style': ok ? 'color:#2a2' : 'color:#c33' }, resultText(r.result)),
			r.ms != null ? ' (%.1f s)'.format(r.ms / 1000) : ''
		]);
	}));
}

function fetchText(url, ms) {
	return new Promise(function(resolve, reject) {
		var ctl = (typeof AbortController == 'function') ? new AbortController() : null,
		    done = false,
		    timer = window.setTimeout(function() {
				done = true;
				if (ctl)
					ctl.abort();
				reject(new Error('timeout'));
			}, ms);

		fetch(url, { cache: 'no-store', credentials: 'omit', signal: ctl ? ctl.signal : undefined }).then(function(res) {
			if (!res.ok)
				throw new Error('HTTP ' + res.status);
			return res.text();
		}).then(function(text) {
			window.clearTimeout(timer);
			if (!done)
				resolve(text);
		}, function(err) {
			window.clearTimeout(timer);
			if (!done)
				reject(err);
		});
	});
}

function b64text(s) {
	var bin = window.atob((s || '').replace(/\s+/g, '')),
	    bytes = new Uint8Array(bin.length);

	for (var i = 0; i < bin.length; i++)
		bytes[i] = bin.charCodeAt(i);

	return new TextDecoder('utf-8').decode(bytes);
}

return view.extend({
	st: null,
	browserResults: null,
	browserBusy: false,

	load: function() {
		return Promise.all([
			L.resolveDefault(callStatus(), {}),
			uci.load('h3c_update')
		]);
	},

	sources: function() {
		var s = (this.st && this.st.config && this.st.config.source) || 'auto';
		return (s == 'github' || s == 'gitee') ? [ s ] : [ 'github', 'gitee' ];
	},

	/* fetch update.json + signature for one source through this browser */
	browserFetch: function(src) {
		var st = this.st,
		    t0 = Date.now(),
		    test = st.config && st.config.test_base,
		    p;

		if (test) {
			p = Promise.all([
				fetchText(test + '/' + src + '/update.json?t=' + t0, 15000),
				fetchText(test + '/' + src + '/update.json.sig?t=' + t0, 15000)
			]);
		}
		else if (src == 'github') {
			var base = 'https://flyfish-go.github.io/' + st.repo + '/update/';
			p = Promise.all([
				fetchText(base + 'update.json?t=' + t0, 15000),
				fetchText(base + 'update.json.sig?t=' + t0, 15000)
			]);
		}
		else {
			/* Gitee raw files send no CORS header; its API does. */
			var api = 'https://gitee.com/api/v5/repos/FlyFish-go/' + st.repo + '/contents/';
			p = Promise.all([
				fetchText(api + 'update.json?ref=update', 15000),
				fetchText(api + 'update.json.sig?ref=update', 15000)
			]).then(function(r) {
				return [ b64text(JSON.parse(r[0]).content), b64text(JSON.parse(r[1]).content) ];
			});
		}

		return p.then(function(r) {
			return { source: src, json: r[0], sig: r[1], ms: Date.now() - t0 };
		}, function(err) {
			return {
				source: src,
				result: (err && err.message == 'timeout') ? 'timeout' :
					(err && err.message == 'HTTP 404') ? 'notfound' : 'fetch',
				ms: Date.now() - t0
			};
		});
	},

	handleBrowserCheck: function(ev) {
		if (this.browserBusy)
			return;

		this.browserBusy = true;
		this.browserResults = null;
		this.redraw();

		return Promise.all(this.sources().map(L.bind(this.browserFetch, this))).then(L.bind(function(fetched) {
			/* verify one after the other: the router keeps the highest serial */
			var results = [];
			var chain = Promise.resolve();

			fetched.forEach(function(f) {
				chain = chain.then(function() {
					if (f.result) {
						results.push(f);
						return;
					}
					return L.resolveDefault(callVerify(f.source, f.json, f.sig), { result: 'manifest' }).then(function(v) {
						results.push({ source: f.source, result: v.result, ms: f.ms, version: v.version });
					});
				});
			});

			return chain.then(function() { return results; });
		}, this)).then(L.bind(function(results) {
			this.browserResults = results;
		}, this)).finally(L.bind(function() {
			this.browserBusy = false;
			return this.refresh();
		}, this));
	},

	handleRouterCheck: function(ev) {
		return callCheck().then(L.bind(this.refresh, this));
	},

	handleDownload: function(ev) {
		return callDownload().then(L.bind(this.refresh, this));
	},

	handleCancel: function(ev) {
		return callCancel().then(L.bind(this.refresh, this));
	},

	handleInstall: function(ev) {
		var lt = this.st.latest,
		    keepOk = !!lt.keep,
		    cb = E('input', { 'type': 'checkbox', 'id': 'h3c-update-keep', 'checked': keepOk ? '' : null, 'disabled': keepOk ? null : '' });

		ui.showModal(_('Install %s').format(lt.version), [
			E('p', {}, _('The downloaded image has been checked (size, SHA-256 and sysupgrade image test). It is written to the system slot the router is running from now. The other slot is not touched, so you can still boot it from the U-Boot rescue page if anything goes wrong.')),
			E('p', {}, [ cb, ' ', E('label', { 'for': 'h3c-update-keep' }, _('Keep current settings')) ]),
			keepOk ? '' : E('p', { 'class': 'alert-message warning' },
				_('Settings of %s cannot be carried over to %s. The router will start with default settings at 192.168.10.1.').format(this.st.release, lt.version)),
			E('p', { 'class': 'alert-message warning' }, _('Do not power off the router during the upgrade. It takes about 3 to 5 minutes.')),
			E('div', { 'class': 'right' }, [
				E('button', { 'class': 'btn', 'click': ui.hideModal }, _('Cancel')), ' ',
				E('button', {
					'class': 'btn cbi-button-action important',
					'click': L.bind(function() { this.doInstall(cb.checked); }, this)
				}, _('Install'))
			])
		]);
	},

	doInstall: function(keep) {
		ui.showModal(_('Installing…'), [
			E('p', { 'class': 'spinning' }, _('The system is flashing now.<br /> DO NOT POWER OFF THE DEVICE!<br /> Wait a few minutes before you try to reconnect. It might be necessary to renew the address of your computer to reach the device again, depending on your settings.'))
		]);

		return callInstall(!!keep).then(function(r) {
			if (!r || !r.ok) {
				ui.hideModal();
				ui.addNotification(null, E('p', {}, _('Install failed: %s').format(r && r.error ? '%h'.format(r.error) : _('unknown error'))), 'error');
				return;
			}
			poll.stop();
			if (keep)
				ui.awaitReconnect(window.location.host);
			else
				ui.awaitReconnect('192.168.10.1');
		});
	},

	refresh: function() {
		return L.resolveDefault(callStatus(), null).then(L.bind(function(st) {
			if (st)
				this.st = st;
			this.redraw();
		}, this));
	},

	redraw: function() {
		if (this.statusNode)
			dom.content(this.statusNode, this.renderStatus(this.st || {}));
	},

	renderRow: function(label, value) {
		return E('tr', { 'class': 'tr' }, [
			E('td', { 'class': 'td left', 'width': '33%' }, label),
			E('td', { 'class': 'td left' }, value)
		]);
	},

	renderStatus: function(st) {
		var lt = st.latest,
		    last = st.last,
		    dl = st.download || {},
		    lineName = (st.line == 'nss') ? 'H3C-Magic-NSS' : 'H3C-Magic (QSDK)',
		    nodes = [];

		/* this firmware */
		nodes.push(E('div', { 'class': 'cbi-section' }, [
			E('h3', {}, _('This firmware')),
			E('table', { 'class': 'table' }, [
				this.renderRow(_('Firmware'), '%s %s'.format(lineName, st.release || '?')),
				this.renderRow(_('Hardware group'), st.group || _('not supported yet'))
			]),
			st.group ? '' : E('p', { 'class': 'alert-message warning' },
				_('Online update is not available for this hardware group yet. Upgrade from System → Backup / Flash Firmware instead.'))
		]));

		/* checking */
		var checkInfo = [];

		if (st.job == 'check')
			checkInfo.push(E('p', { 'class': 'spinning' }, _('Checking from the router…')));
		else if (last) {
			checkInfo.push(E('p', {}, _('Last check from the router: %s (%s)').format(
				fmtTime(last.checked), last.mode == 'auto' ? _('automatic') : _('manual'))));
			checkInfo.push(resultList(Object.keys(last.sources || {}).map(function(k) {
				return { source: k, result: last.sources[k].result, ms: last.sources[k].ms };
			})));
		}
		else
			checkInfo.push(E('p', {}, _('The router has not checked yet.')));

		if (this.browserBusy)
			checkInfo.push(E('p', { 'class': 'spinning' }, _('Checking from this browser…')));
		else if (this.browserResults) {
			checkInfo.push(E('p', {}, _('Check from this browser:')));
			checkInfo.push(resultList(this.browserResults));
		}

		nodes.push(E('div', { 'class': 'cbi-section' }, [
			E('h3', {}, _('Check for updates')),
			E('p', {}, _('The router asks GitHub and Gitee at the same time and uses whichever answers with a valid signed release list. If the router cannot reach either, try the check from this browser: it uses your computer\'s connection and lets the router verify the result.')),
			E('div', {}, checkInfo),
			E('div', {}, [
				E('button', {
					'class': 'btn cbi-button-action',
					'disabled': (st.job || !st.group) ? '' : null,
					'click': ui.createHandlerFn(this, 'handleRouterCheck')
				}, _('Check from router')), ' ',
				E('button', {
					'class': 'btn cbi-button',
					'disabled': (this.browserBusy || !st.group) ? '' : null,
					'click': ui.createHandlerFn(this, 'handleBrowserCheck')
				}, _('Check from this browser'))
			])
		]));

		/* latest release */
		if (lt) {
			var summary = isZh() ? (lt.summary_zh || lt.summary_en) : (lt.summary_en || lt.summary_zh),
			    links = [],
			    action = [];

			if (lt.release_github)
				links.push(E('a', { 'href': lt.release_github, 'target': '_blank', 'rel': 'noreferrer' }, 'GitHub'));
			if (lt.release_gitee) {
				if (links.length)
					links.push(' · ');
				links.push(E('a', { 'href': lt.release_gitee, 'target': '_blank', 'rel': 'noreferrer' }, 'Gitee'));
			}

			if (lt.newer && st.group && lt.file) {
				switch (dl.state) {
				case 'downloading':
					var pct = lt.size ? Math.floor(100 * dl.bytes / lt.size) : 0;
					action.push(E('p', {}, _('Downloading from %s…').format(SOURCE_NAME[dl.source] || '…')));
					action.push(E('div', { 'class': 'cbi-progressbar', 'title': '%d%% (%s / %s)'.format(pct, fmtSize(dl.bytes), fmtSize(lt.size)) },
						E('div', { 'style': 'width:%d%%'.format(pct) })));
					action.push(E('p', {}, E('button', { 'class': 'btn cbi-button-reset', 'click': ui.createHandlerFn(this, 'handleCancel') }, _('Cancel'))));
					break;

				case 'ready':
					action.push(E('p', {}, _('Downloaded and verified: %s (%s).').format(lt.file, fmtSize(lt.size))));
					action.push(E('p', {}, [
						E('button', { 'class': 'btn cbi-button-action important', 'click': ui.createHandlerFn(this, 'handleInstall') }, _('Install…')), ' ',
						E('button', { 'class': 'btn cbi-button-reset', 'click': ui.createHandlerFn(this, 'handleCancel') }, _('Discard'))
					]));
					break;

				case 'installing':
					action.push(E('p', { 'class': 'spinning' }, _('Installing…')));
					break;

				default:
					if (dl.state == 'error')
						action.push(E('p', { 'class': 'alert-message warning' }, _('Download failed: %s').format('%h'.format(dl.error))));
					action.push(E('p', {}, E('button', {
						'class': 'btn cbi-button-action',
						'disabled': st.job ? '' : null,
						'click': ui.createHandlerFn(this, 'handleDownload')
					}, _('Download %s (%s)').format(lt.version, fmtSize(lt.size)))));
				}
			}

			nodes.push(E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, _('Latest release')),
				E('table', { 'class': 'table' }, [
					this.renderRow(_('Version'), [
						E('strong', {}, lt.version), lt.date ? ' (' + lt.date + ')' : '',
						lt.newer ? E('span', { 'class': 'label', 'style': 'margin-left:.5em' }, _('new')) : ''
					]),
					this.renderRow(_('Release list from'), sourceLabel(lt.source)),
					summary ? this.renderRow(_('Changes'), E('div', { 'style': 'white-space:pre-line' }, '%h'.format(summary))) : '',
					links.length ? this.renderRow(_('Release page'), links) : ''
				]),
				lt.newer ? E('div', {}, action) : E('p', {}, _('This router runs the latest release.'))
			]));
		}

		return nodes;
	},

	render: function(data) {
		var m, s, o;

		this.st = data[0] || {};

		m = new form.Map('h3c_update', null, null);

		s = m.section(form.NamedSection, 'main', 'h3c_update', _('Automatic check'));
		s.addremove = false;

		o = s.option(form.Flag, 'auto', _('Check automatically'),
			_('Off by default. When on, the router checks GitHub and Gitee by itself at the interval below and shows new releases here and on the Status page. It never installs anything by itself.'));
		o.rmempty = false;

		o = s.option(form.Value, 'interval', _('Check interval (hours)'));
		o.datatype = 'range(1,168)';
		o.placeholder = '12';
		o.default = '12';
		o.value('6', _('6 hours'));
		o.value('12', _('12 hours'));
		o.value('24', _('24 hours'));
		o.value('72', _('3 days'));
		o.value('168', _('7 days'));
		o.depends('auto', '1');

		o = s.option(form.ListValue, 'source', _('Download site'));
		o.value('auto', _('Automatic (GitHub and Gitee, use whichever works)'));
		o.value('github', 'GitHub');
		o.value('gitee', _('Gitee (mainland China)'));
		o.default = 'auto';

		return m.render().then(L.bind(function(mapEl) {
			this.statusNode = E('div', {});
			this.redraw();

			poll.add(L.bind(function() {
				var busy = this.st && (this.st.job || (this.st.download && this.st.download.state == 'downloading'));
				this.pollCount = (this.pollCount || 0) + 1;
				if (busy || this.pollCount % 5 == 0)
					return this.refresh();
			}, this), 2);

			return E([], [
				E('h2', {}, _('Firmware Update')),
				E('div', { 'class': 'cbi-map-descr' },
					_('Checks for new H3C Magic releases, downloads the image for this hardware group, verifies it and installs it. Nothing is installed without your confirmation.')),
				this.statusNode,
				mapEl
			]);
		}, this));
	}
});
