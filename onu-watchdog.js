'use strict';
'require view';
'require form';
'require fs';
'require ui';

function parseEvents(text) {
	return (text || '').trim().split('\n').filter(function(line) {
		return line.length > 0;
	}).map(function(line) {
		var fields = line.split('\t');
		return {
			time: Number(fields[0]) || 0,
			type: fields[1] || 'unknown',
			source: fields[2] || 'unknown',
			detail: fields.slice(4).join(' ') || ''
		};
	}).filter(function(item) {
		return item.time > 0;
	});
}

function formatTime(epoch) {
	if (!epoch)
		return '暂无记录';
	return new Date(epoch * 1000).toLocaleString('zh-CN', { hour12: false });
}

function sourceLabel(source) {
	return ({ automatic: '自动', manual: '手动', system: '系统', unknown: '未知' })[source] || source;
}

function latest(events, type) {
	for (var i = events.length - 1; i >= 0; i--)
		if (events[i].type === type)
			return events[i];
	return null;
}

function countSince(events, type, seconds, source) {
	var start = Math.floor(Date.now() / 1000) - seconds;
	return events.filter(function(item) {
		return item.time >= start && item.type === type && (!source || item.source === source);
	}).length;
}

function statCard(title, value, note) {
	return E('div', {
		'style': 'min-width:190px;flex:1;padding:16px;border:1px solid var(--border-color-medium,#d8d8d8);border-radius:8px;background:var(--background-color-high,#fff)'
	}, [
		E('div', { 'style': 'color:var(--text-color-secondary,#666);margin-bottom:8px' }, title),
		E('div', { 'style': 'font-size:1.35rem;font-weight:600;word-break:break-word' }, value),
		E('div', { 'style': 'margin-top:6px;color:var(--text-color-secondary,#777);font-size:.9rem' }, note || '')
	]);
}

return view.extend({
	load: function() {
		return Promise.all([
			L.resolveDefault(fs.exec('/etc/init.d/onu-watchdog', [ 'status' ]), { code: 1, stdout: '' }),
			L.resolveDefault(fs.exec('/usr/sbin/onu-watchdog', [ 'events' ]), { code: 1, stdout: '' })
		]);
	},

	handleCheck: function(ev) {
		var btn = ev.currentTarget;
		btn.disabled = true;
		btn.classList.add('spinning');
		return fs.exec('/usr/sbin/onu-watchdog', [ 'check' ]).then(function(res) {
			ui.addNotification(null, E('p', {}, res.code === 0 ?
				'外网检测正常：' + (res.stdout || '').trim() :
				'外网检测失败：' + ((res.stderr || res.stdout || '').trim() || '未知错误')),
				res.code === 0 ? 'info' : 'warning');
		}).catch(function(err) {
			ui.addNotification(null, E('p', {}, '检测命令执行失败：' + err.message), 'error');
		}).finally(function() {
			btn.disabled = false;
			btn.classList.remove('spinning');
		});
	},

	handleReboot: function(ev) {
		ui.showModal('确认重启光猫', [
			E('p', {}, '这会让家庭外网中断约 2～5 分钟。命令成功后，看门狗会等待设置的静默时间再恢复检测。'),
			E('div', { 'class': 'right' }, [
				E('button', { 'class': 'btn', 'click': ui.hideModal }, '取消'),
				' ',
				E('button', {
					'class': 'btn cbi-button-negative important',
					'click': ui.createHandlerFn(this, 'handleRebootConfirm')
				}, '确认重启')
			])
		]);
	},

	handleRebootConfirm: function(ev) {
		ui.showModal('正在发送命令', [ E('p', { 'class': 'spinning' }, '正在登录光猫并提交加密重启请求…') ]);
		return fs.exec('/usr/sbin/onu-watchdog', [ 'reboot-now' ]).then(function(res) {
			if (res.code !== 0)
				throw new Error((res.stderr || res.stdout || '').trim() || '光猫拒绝了重启命令');
			ui.showModal('重启命令已发送', [
				E('p', {}, (res.stdout || '').trim()),
				E('div', { 'class': 'right' }, E('button', { 'class': 'btn', 'click': ui.hideModal }, '关闭'))
			]);
		}).catch(function(err) {
			ui.showModal('重启失败', [
				E('p', {}, err.message),
				E('div', { 'class': 'right' }, E('button', { 'class': 'btn', 'click': ui.hideModal }, '关闭'))
			]);
		});
	},

	render: function(data) {
		var m, s, o;
		var serviceStatus = data[0];
		var events = parseEvents(data[1].stdout);
		var lastOutage = latest(events, 'offline_started');
		var lastReboot = latest(events, 'reboot_accepted');
		var sevenDays = 7 * 86400;
		var thirtyDays = 30 * 86400;
		var summary = E('div', { 'style': 'display:flex;flex-wrap:wrap;gap:12px;margin:0 0 18px' }, [
			statCard('最近一次断线', formatTime(lastOutage && lastOutage.time), lastOutage ? lastOutage.detail : '尚未检测到断线'),
			statCard('最近一次重启', formatTime(lastReboot && lastReboot.time), lastReboot ? sourceLabel(lastReboot.source) + '重启' : '尚未触发重启'),
			statCard('最近7天', '%d 次断线'.format(countSince(events, 'offline_started', sevenDays)),
				'%d 次自动重启'.format(countSince(events, 'reboot_accepted', sevenDays, 'automatic'))),
			statCard('最近30天', '%d 次断线'.format(countSince(events, 'offline_started', thirtyDays)),
				'%d 次自动重启'.format(countSince(events, 'reboot_accepted', thirtyDays, 'automatic')))
		]);

		m = new form.Map('onu_watchdog', '光猫断线看门狗',
			'外网连续不可用达到设定时间后，自动登录光猫并发送重启命令。后台只保留一个轻量 shell 进程，状态变量固定，不会随运行时间增加内存占用。');

		s = m.section(form.NamedSection, 'main', 'watchdog', '运行设置');
		s.anonymous = true;
		s.addremove = false;

		o = s.option(form.DummyValue, '_runtime_status', '当前运行状态');
		o.cfgvalue = function() {
			return serviceStatus && serviceStatus.code === 0 ? '正在运行' : '已停止';
		};

		o = s.option(form.Flag, 'enabled', '启用自动看门狗');
		o.default = o.enabled;
		o.rmempty = false;

		o = s.option(form.Value, 'wan_interface', '被检测的 WAN 接口');
		o.default = 'WAN';
		o.placeholder = 'WAN';
		o.rmempty = false;

		o = s.option(form.Value, 'check_interval', '检测间隔（秒）', '每隔多少秒检测一次。建议不少于 5 秒，当前推荐 10 秒。');
		o.datatype = 'range(5,300)';
		o.default = '10';
		o.rmempty = false;

		o = s.option(form.Value, 'fail_seconds', '连续掉线判定（秒）', '外网连续失败达到这个时间才重启光猫；偶发丢包不会触发。');
		o.datatype = 'range(30,3600)';
		o.default = '60';
		o.rmempty = false;

		o = s.option(form.Value, 'post_reboot_wait', '重启后静默时间（秒）', '发送成功后完全停止检测，等待光猫完成 PON 注册和 PPPoE 拨号。');
		o.datatype = 'range(120,1800)';
		o.default = '300';
		o.rmempty = false;

		o = s.option(form.Value, 'reboot_cooldown', '再次重启冷却时间（秒）', '防止运营商长时间故障时反复重启。21600 秒等于 6 小时。');
		o.datatype = 'range(600,86400)';
		o.default = '21600';
		o.rmempty = false;

		o = s.option(form.Value, 'modem_url', '光猫管理地址');
		o.datatype = 'url';
		o.default = 'http://192.168.1.1';
		o.rmempty = false;

		o = s.option(form.Value, 'modem_password', '光猫普通管理密码');
		o.password = true;
		o.rmempty = false;

		s = m.section(form.NamedSection, 'main', 'watchdog', '手动操作');
		s.anonymous = true;
		s.addremove = false;

		o = s.option(form.Button, '_check_now', '立即检测外网');
		o.inputtitle = '运行一次检测';
		o.inputstyle = 'action';
		o.onclick = this.handleCheck;

		o = s.option(form.Button, '_reboot_now', '手动重启光猫');
		o.inputtitle = '发送重启命令';
		o.inputstyle = 'negative';
		o.onclick = this.handleReboot;

		return Promise.resolve(m.render()).then(function(rendered) {
			return E([], [ summary, rendered ]);
		});
	}
});
