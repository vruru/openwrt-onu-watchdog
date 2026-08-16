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
	/etc/onu-watchdog.last_reboot \
	/etc/onu-watchdog.events \
	/etc/config/network \
	/etc/config/firewall \
	/usr/share/luci/menu.d/luci-app-onu-watchdog.json \
	/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
	/www/luci-static/resources/view/services/onu-watchdog.js \
	/www/luci-static/resources/view/services/onu-watchdog-log.js; do
	[ ! -e "$file" ] || cp -a "$file" "$BACKUP_DIR/"
done

cp "$ROOT/onu-watchdog" /usr/sbin/onu-watchdog
cp "$ROOT/onu-watchdog.init" /etc/init.d/onu-watchdog
mkdir -p /usr/share/luci/menu.d /usr/share/rpcd/acl.d /www/luci-static/resources/view/services
cp "$ROOT/luci-app-onu-watchdog.menu.json" /usr/share/luci/menu.d/luci-app-onu-watchdog.json
cp "$ROOT/luci-app-onu-watchdog.acl.json" /usr/share/rpcd/acl.d/luci-app-onu-watchdog.json
cp "$ROOT/onu-watchdog.js" /www/luci-static/resources/view/services/onu-watchdog.js
cp "$ROOT/onu-watchdog-log.js" /www/luci-static/resources/view/services/onu-watchdog-log.js

chmod 755 /usr/sbin/onu-watchdog /etc/init.d/onu-watchdog
chmod 644 \
	/usr/share/luci/menu.d/luci-app-onu-watchdog.json \
	/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
	/www/luci-static/resources/view/services/onu-watchdog.js \
	/www/luci-static/resources/view/services/onu-watchdog-log.js

if [ ! -e /etc/config/onu_watchdog ]; then
	cp "$ROOT/onu_watchdog.uci" /etc/config/onu_watchdog
fi

chmod 600 /etc/config/onu_watchdog

# Recreate the management path to a bridge-mode ONU after a clean OpenWrt
# installation.  Existing MODEM/firewall sections are never overwritten.
network_changed=0
firewall_changed=0
if ! uci -q get network.MODEM >/dev/null 2>&1; then
	WAN_DEVICE="${MODEM_DEVICE:-$(uci -q get network.WAN.device || true)}"
	if [ -z "$WAN_DEVICE" ] && [ -t 0 ]; then
		printf '请输入 PPPoE WAN 使用的物理网卡（例如 eth1）：'
		IFS= read -r WAN_DEVICE
	fi
	[ -n "$WAN_DEVICE" ] || {
		echo "无法确定 WAN 物理网卡，请设置 MODEM_DEVICE 后重新运行。" >&2
		exit 1
	}
	uci set network.MODEM='interface'
	uci set network.MODEM.proto='static'
	uci set network.MODEM.device="$WAN_DEVICE"
	uci set network.MODEM.ipaddr='192.168.1.2'
	uci set network.MODEM.netmask='255.255.255.0'
	uci set network.MODEM.defaultroute='0'
	uci set network.MODEM.peerdns='0'
	uci set network.MODEM.delegate='0'
	uci commit network
	network_changed=1
fi

if ! uci -q get firewall.modem >/dev/null 2>&1; then
	uci set firewall.modem='zone'
	uci set firewall.modem.name='modem'
	uci set firewall.modem.input='REJECT'
	uci set firewall.modem.output='ACCEPT'
	uci set firewall.modem.forward='REJECT'
	uci set firewall.modem.masq='1'
	uci add_list firewall.modem.network='MODEM'
	firewall_changed=1
fi

if ! uci -q get firewall.lan_to_modem >/dev/null 2>&1; then
	uci set firewall.lan_to_modem='forwarding'
	uci set firewall.lan_to_modem.src='lan'
	uci set firewall.lan_to_modem.dest='modem'
	firewall_changed=1
fi

if [ "$firewall_changed" = "1" ]; then
	uci commit firewall
fi

[ "$network_changed" = "0" ] || /etc/init.d/network reload
[ "$firewall_changed" = "0" ] || /etc/init.d/firewall reload

rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/* 2>/dev/null || true
/etc/init.d/rpcd restart
/etc/init.d/onu-watchdog enable
/etc/init.d/onu-watchdog restart

sleep 2
if [ "$(uci -q get onu_watchdog.main.enabled)" = "1" ]; then
	if /etc/init.d/onu-watchdog status >/dev/null 2>&1; then
		echo "安装完成，已有配置已保留，光猫断线看门狗正在运行。"
	else
		echo "文件已安装，但已有配置要求启动而服务没有运行，请检查：logread -e onu-watchdog" >&2
		exit 1
	fi
else
	echo "插件安装完成。请进入 LuCI 填写光猫地址和密码，然后勾选启用并保存。"
fi

LAN_IP="$(uci -q get network.lan.ipaddr || true)"
[ -n "$LAN_IP" ] || LAN_IP='OpenWrt地址'
echo "管理页面：http://$LAN_IP/cgi-bin/luci/admin/services/onu-watchdog"
echo "原文件备份：$BACKUP_DIR"
