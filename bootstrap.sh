#!/bin/sh

set -eu

ARCHIVE_URL='https://github.com/vruru/openwrt-onu-watchdog/archive/refs/heads/main.tar.gz'
WORK="$(mktemp -d /tmp/onu-watchdog-install.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT INT TERM

if command -v wget >/dev/null 2>&1; then
	wget -qO "$WORK/source.tar.gz" "$ARCHIVE_URL"
elif command -v uclient-fetch >/dev/null 2>&1; then
	uclient-fetch -q -O "$WORK/source.tar.gz" "$ARCHIVE_URL"
elif command -v curl >/dev/null 2>&1; then
	curl -fsSL "$ARCHIVE_URL" -o "$WORK/source.tar.gz"
else
	echo "系统缺少 wget、uclient-fetch 和 curl，无法下载安装包。" >&2
	exit 1
fi

tar -xzf "$WORK/source.tar.gz" -C "$WORK"
INSTALLER="$(find "$WORK" -name install.sh | head -n 1)"
[ -n "$INSTALLER" ] || {
	echo "下载包中没有找到 install.sh。" >&2
	exit 1
}

sh "$INSTALLER"
