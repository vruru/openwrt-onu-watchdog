'use strict';
'require view';
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
			duration: Number(fields[3]) || 0,
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

function formatDuration(seconds) {
	if (!seconds)
		return '—';
	if (seconds < 60)
		return '%d 秒'.format(seconds);
	if (seconds < 3600)
		return '%d 分 %d 秒'.format(Math.floor(seconds / 60), seconds % 60);
	return '%d 小时 %d 分'.format(Math.floor(seconds / 3600), Math.floor((seconds % 3600) / 60));
}

function eventLabel(type) {
	return ({
		service_started: '服务启动',
		offline_started: '检测到断线',
		offline_recovered: '断线后自动恢复',
		reboot_attempt: '发送重启命令',
		reboot_accepted: '光猫接受重启',
		reboot_failed: '光猫重启失败',
		reboot_cooldown: '重启冷却中',
		reboot_recovered: '重启后恢复',
		reboot_unrecovered: '重启后仍断线'
	})[type] || type;
}

function sourceLabel(source) {
	return ({ automatic: '自动', manual: '手动', system: '系统', unknown: '未知' })[source] || source;
}

return view.extend({
	load: function() {
		return L.resolveDefault(fs.exec('/usr/sbin/onu-watchdog', [ 'events' ]), {
			code: 1,
			stdout: '',
			stderr: '读取事件日志失败'
		});
	},

	handleRefresh: function() {
		window.location.reload();
	},

	handleClear: function() {
		ui.showModal('确认清空事件日志', [
			E('p', {}, '这会永久删除当前保存的断线与重启历史，但不会改变看门狗配置。'),
			E('div', { 'class': 'right' }, [
				E('button', { 'class': 'btn', 'click': ui.hideModal }, '取消'),
				' ',
				E('button', {
					'class': 'btn cbi-button-negative important',
					'click': ui.createHandlerFn(this, 'handleClearConfirm')
				}, '确认清空')
			])
		]);
	},

	handleClearConfirm: function() {
		ui.showModal('正在清空', [ E('p', { 'class': 'spinning' }, '正在清空事件日志…') ]);
		return fs.exec('/usr/sbin/onu-watchdog', [ 'clear-events' ]).then(function(res) {
			if (res.code !== 0)
				throw new Error((res.stderr || res.stdout || '').trim() || '清空失败');
			window.location.reload();
		}).catch(function(err) {
			ui.showModal('清空失败', [
				E('p', {}, err.message),
				E('div', { 'class': 'right' }, E('button', { 'class': 'btn', 'click': ui.hideModal }, '关闭'))
			]);
		});
	},

	render: function(result) {
		var events = parseEvents(result.stdout);
		var rows = events.slice().reverse().slice(0, 100);
		var tableRows = rows.map(function(item) {
			return E('tr', {}, [
				E('td', {}, formatTime(item.time)),
				E('td', {}, eventLabel(item.type)),
				E('td', {}, sourceLabel(item.source)),
				E('td', {}, formatDuration(item.duration)),
				E('td', { 'style': 'white-space:normal;min-width:220px' }, item.detail || '—')
			]);
		});

		if (!tableRows.length)
			tableRows.push(E('tr', {}, E('td', { 'colspan': 5, 'style': 'text-align:center;padding:28px' }, '暂无事件记录')));

		return E([], [
			E('h2', {}, '光猫断线看门狗 · 事件日志'),
			E('div', { 'class': 'cbi-map-descr' },
				'这里只记录断线、恢复和重启等状态变化，不记录每次正常探测。最多保留500条，超限后自动保留最近400条。'),
			E('div', { 'style': 'display:flex;gap:8px;margin:12px 0' }, [
				E('button', { 'class': 'btn cbi-button-action', 'click': ui.createHandlerFn(this, 'handleRefresh') }, '刷新'),
				E('button', { 'class': 'btn cbi-button-negative', 'click': ui.createHandlerFn(this, 'handleClear') }, '清空日志')
			]),
			E('div', { 'class': 'table', 'style': 'overflow-x:auto' },
				E('table', { 'class': 'table' }, [
					E('thead', {}, E('tr', { 'class': 'tr table-titles' }, [
						E('th', { 'class': 'th' }, '时间'),
						E('th', { 'class': 'th' }, '事件'),
						E('th', { 'class': 'th' }, '来源'),
						E('th', { 'class': 'th' }, '持续时间'),
						E('th', { 'class': 'th' }, '说明')
					])),
					E('tbody', {}, tableRows)
				]))
		]);
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
