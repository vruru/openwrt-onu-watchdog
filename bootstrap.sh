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
	echo "未找到下载工具，正在通过 opkg 安装 curl…"
	command -v opkg >/dev/null 2>&1 || {
		echo "系统既没有下载工具，也没有 opkg，无法继续安装。" >&2
		exit 1
	}
	opkg update
	opkg install curl ca-bundle
	curl -fsSL "$ARCHIVE_URL" -o "$WORK/source.tar.gz"
fi

tar -xzf "$WORK/source.tar.gz" -C "$WORK"
INSTALLER="$(find "$WORK" -name install.sh | head -n 1)"
[ -n "$INSTALLER" ] || {
	echo "下载包中没有找到 install.sh。" >&2
	exit 1
}

sh "$INSTALLER"
