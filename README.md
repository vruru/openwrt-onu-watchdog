# OpenWrt 光猫断线看门狗

适用于中兴 `ZXHN G7615V2-G-C`（中国联通固件 `V3.0.5P1T2`）的 OpenWrt/iStoreOS 看门狗与 LuCI 管理页面。

当指定 WAN 接口连续无法访问两个独立公网探测地址达到设定时间时，程序使用光猫普通管理账号登录 `192.168.1.1`，按照原厂 Web 页面的 RSA + AES 加密协议提交重启命令。

## 默认策略

- 检测间隔：10 秒
- 连续掉线判定：60 秒
- 重启后静默：300 秒
- 两次自动重启最短间隔：21600 秒（6 小时）
- 探测目标：`223.5.5.5`、`119.29.29.29`，任意一个可达即视为正常

LuCI 页面位于：`服务 → 光猫断线看门狗`。

## 从私有 GitHub 仓库一键安装

私有仓库不能匿名下载。先创建一个仅对此仓库具有 `Contents: Read-only` 权限的 Fine-grained Personal Access Token，然后在 OpenWrt SSH 终端执行下面一行。命令会隐式读取 Token，不会把它写进 shell 历史；随后安装程序会继续提示输入光猫密码：

```sh
printf 'GitHub 只读 Token：'; stty -echo; IFS= read -r GITHUB_TOKEN; stty echo; printf '\n'; export GITHUB_TOKEN; sh -c 'command -v curl >/dev/null 2>&1 || { opkg update && opkg install curl; }; d=$(mktemp -d) || exit 1; trap '\''rm -rf "$d"'\'' EXIT; curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" https://api.github.com/repos/vruru/openwrt-onu-watchdog/tarball/main | tar -xz -C "$d" && p=$(find "$d" -name install.sh | head -n 1) && [ -n "$p" ] && sh "$p"'
```

首次安装会在终端提示输入光猫普通管理密码。密码只写入 OpenWrt 本机的 `/etc/config/onu_watchdog`，权限为 `600`，不会进入 GitHub 仓库。

如果系统没有 `curl`、`openssl` 或 `jsonfilter`，安装脚本会通过 `opkg` 自动补齐。

## 本地安装

将仓库下载并解压到 OpenWrt 后执行：

```sh
sh install.sh
```

已存在的 `/etc/config/onu_watchdog` 会被保留，升级插件不会覆盖密码和策略。

## 卸载

保留配置：

```sh
sh uninstall.sh
```

连配置与重启状态一起删除：

```sh
PURGE=1 sh uninstall.sh
```

## 资源占用

后台只有一个 BusyBox `ash` 常驻进程，当前实测约 1.0～1.1 MiB RSS、1 个线程、4 个文件描述符。每轮检测执行后子进程都会退出，日志写入 OpenWrt 的环形系统日志，不建立持续增长的数据库、队列或日志文件。

## 安全说明

- 不要从 WAN 开放光猫管理页面或 LuCI 页面。
- GitHub Token 只需此私有仓库的只读权限，不应赋予写权限。
- 自动重启不能修复光猫 Web 服务也完全卡死的情况；这种情况需要可远程断电的智能插座。
- 当前加密公钥来自上述型号与固件的 `/js/code.js`。更换光猫或固件后应重新验证重启接口。
