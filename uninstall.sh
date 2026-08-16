#!/bin/sh

set -eu

[ "$(id -u)" = "0" ] || {
	echo "请使用 root 运行。" >&2
	exit 1
}

/etc/init.d/onu-watchdog disable 2>/dev/null || true
/etc/init.d/onu-watchdog stop 2>/dev/null || true

rm -f \
	/usr/sbin/onu-watchdog \
	/etc/init.d/onu-watchdog \
	/usr/share/luci/menu.d/luci-app-onu-watchdog.json \
	/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
	/www/luci-static/resources/view/services/onu-watchdog.js \
	/www/luci-static/resources/view/services/onu-watchdog-log.js

if [ "${PURGE:-0}" = "1" ]; then
	rm -f /etc/config/onu_watchdog /etc/onu-watchdog.last_reboot /etc/onu-watchdog.events
	echo "插件与配置均已删除。"
else
	echo "插件已删除，配置、重启状态与事件日志均已保留。"
fi

rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/* 2>/dev/null || true
/etc/init.d/rpcd restart
