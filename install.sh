#!/bin/sh

set -eu

APP=onu-watchdog
ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
BACKUP_DIR="/root/${APP}-backup-$(date +%Y%m%d-%H%M%S)"
INSTALL_STAGE=preflight

set_stage()
{
	INSTALL_STAGE="$1"
	if [ -d "$BACKUP_DIR" ]; then
		printf '%s started\n' "$INSTALL_STAGE" >> "$BACKUP_DIR/install-stage.log"
	fi
}

install_exit()
{
	local result="$1"
	if [ "$result" -ne 0 ]; then
		if [ -d "$BACKUP_DIR" ]; then
			printf '%s failed exit=%s\n' "$INSTALL_STAGE" "$result" >> "$BACKUP_DIR/install-stage.log" || true
		fi
		printf '安装失败：阶段=%s，退出码=%s，备份位置=%s。保留当前配置和状态，按恢复文档处理。\n' \
			"$INSTALL_STAGE" "$result" "$BACKUP_DIR" >&2
	fi
}
trap 'install_exit "$?"' EXIT

[ "$(id -u)" = "0" ] || {
	echo "请使用 root 在 OpenWrt 上运行此安装脚本。" >&2
	exit 1
}

[ -d /www/luci-static/resources ] || {
	echo "没有检测到 LuCI，本插件需要带 LuCI 的 OpenWrt/iStoreOS。" >&2
	exit 1
}

# Fail before installing packages or touching device files if the source is incomplete.
for source in onu-watchdog onu-watchdog.init onu_watchdog.uci \
	luci-app-onu-watchdog.menu.json luci-app-onu-watchdog.acl.json \
	onu-watchdog.js onu-watchdog-log.js; do
	[ -r "$ROOT/$source" ] || { echo "缺少运行文件：$source" >&2; exit 1; }
done

set_stage dependencies
set --
command -v curl >/dev/null 2>&1 || set -- "$@" curl
command -v openssl >/dev/null 2>&1 || set -- "$@" openssl-util
command -v jsonfilter >/dev/null 2>&1 || set -- "$@" jsonfilter
command -v flock >/dev/null 2>&1 || set -- "$@" flock

if [ "$#" -gt 0 ]; then
	command -v opkg >/dev/null 2>&1 || {
		echo "缺少 opkg，无法自动安装依赖：$*" >&2
		exit 1
	}
	echo "正在安装依赖：$*"
	opkg update
	opkg install "$@"
fi

for cmd in curl openssl sha256sum awk sed jsonfilter flock ubus uci; do
	command -v "$cmd" >/dev/null 2>&1 || {
		echo "缺少必要命令：$cmd" >&2
		exit 1
	}
done

set_stage backup
mkdir -p "$BACKUP_DIR"
printf 'backup started\n' > "$BACKUP_DIR/install-stage.log"
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
	if [ -e "$file" ]; then
		backup_file="$BACKUP_DIR$file"
		mkdir -p "$(dirname -- "$backup_file")"
		cp -a "$file" "$backup_file"
	fi
done

set_stage runtime-files
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

set_stage uci-config
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

set_stage network-reload
[ "$network_changed" = "0" ] || /etc/init.d/network reload
set_stage firewall-reload
[ "$firewall_changed" = "0" ] || /etc/init.d/firewall reload

rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/* 2>/dev/null || true
set_stage service-restart
/etc/init.d/rpcd restart
/etc/init.d/onu-watchdog enable
/etc/init.d/onu-watchdog restart

set_stage acceptance
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

set_stage complete
