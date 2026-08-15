#!/bin/sh

set -eu

APP=onu-watchdog
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BACKUP_DIR="/root/${APP}-backup-$(date +%Y%m%d-%H%M%S)"

[ "$(id -u)" = "0" ] || {
	echo "请使用 root 在 OpenWrt 上运行此安装脚本。" >&2
	exit 1
}

[ -d /www/luci-static/resources ] || {
	echo "没有检测到 LuCI，本插件需要带 LuCI 的 OpenWrt/iStoreOS。" >&2
	exit 1
}

need_packages=""
command -v curl >/dev/null 2>&1 || need_packages="$need_packages curl"
command -v openssl >/dev/null 2>&1 || need_packages="$need_packages openssl-util"
command -v jsonfilter >/dev/null 2>&1 || need_packages="$need_packages jsonfilter"

if [ -n "$need_packages" ]; then
	echo "正在安装依赖：$need_packages"
	opkg update
	opkg install $need_packages
fi

for cmd in curl openssl sha256sum awk sed jsonfilter ubus uci; do
	command -v "$cmd" >/dev/null 2>&1 || {
		echo "缺少必要命令：$cmd" >&2
		exit 1
	}
done

mkdir -p "$BACKUP_DIR"
for file in \
	/usr/sbin/onu-watchdog \
	/etc/init.d/onu-watchdog \
	/etc/config/onu_watchdog \
	/usr/share/luci/menu.d/luci-app-onu-watchdog.json \
	/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
	/www/luci-static/resources/view/services/onu-watchdog.js; do
	[ ! -e "$file" ] || cp -a "$file" "$BACKUP_DIR/"
done

cp "$ROOT/onu-watchdog" /usr/sbin/onu-watchdog
cp "$ROOT/onu-watchdog.init" /etc/init.d/onu-watchdog
mkdir -p /usr/share/luci/menu.d /usr/share/rpcd/acl.d /www/luci-static/resources/view/services
cp "$ROOT/luci-app-onu-watchdog.menu.json" /usr/share/luci/menu.d/luci-app-onu-watchdog.json
cp "$ROOT/luci-app-onu-watchdog.acl.json" /usr/share/rpcd/acl.d/luci-app-onu-watchdog.json
cp "$ROOT/onu-watchdog.js" /www/luci-static/resources/view/services/onu-watchdog.js

chmod 755 /usr/sbin/onu-watchdog /etc/init.d/onu-watchdog
chmod 644 \
	/usr/share/luci/menu.d/luci-app-onu-watchdog.json \
	/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
	/www/luci-static/resources/view/services/onu-watchdog.js

if [ ! -e /etc/config/onu_watchdog ]; then
	cp "$ROOT/onu_watchdog.uci" /etc/config/onu_watchdog

	if [ -z "${MODEM_PASSWORD:-}" ]; then
		if [ -t 0 ]; then
			printf '请输入光猫普通管理密码：'
			stty -echo
			IFS= read -r MODEM_PASSWORD
			stty echo
			printf '\n'
		else
			echo "首次安装请在交互式终端运行，或通过 MODEM_PASSWORD 环境变量传入密码。" >&2
			exit 1
		fi
	fi

	[ -n "$MODEM_PASSWORD" ] || {
		echo "光猫密码不能为空。" >&2
		exit 1
	}
	uci set onu_watchdog.main.modem_password="$MODEM_PASSWORD"
	uci commit onu_watchdog
fi

chmod 600 /etc/config/onu_watchdog
rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/* 2>/dev/null || true
/etc/init.d/rpcd restart
/etc/init.d/onu-watchdog enable
/etc/init.d/onu-watchdog restart

sleep 2
if /etc/init.d/onu-watchdog status >/dev/null 2>&1; then
	echo "安装完成，光猫断线看门狗正在运行。"
else
	echo "文件已安装，但服务没有运行，请检查：logread -e onu-watchdog" >&2
	exit 1
fi

LAN_IP="$(uci -q get network.lan.ipaddr || true)"
[ -n "$LAN_IP" ] || LAN_IP='OpenWrt地址'
echo "管理页面：http://$LAN_IP/cgi-bin/luci/admin/services/onu-watchdog"
echo "原文件备份：$BACKUP_DIR"
