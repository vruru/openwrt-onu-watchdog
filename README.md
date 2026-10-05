# OpenWrt 光猫断线看门狗

适用于中兴 `ZXHN G7615V2-G-C`（中国联通固件 `V3.0.5P1T2`）的 OpenWrt/iStoreOS 看门狗与 LuCI 管理页面。

当指定 WAN 接口连续无法访问两个独立公网探测地址达到设定时间时，程序使用光猫普通管理账号登录 `192.168.1.1`，按照原厂 Web 页面的 RSA + AES 加密协议提交重启命令。

## 默认策略

- 检测间隔：10 秒
- 连续掉线判定：60 秒
- 重启后静默：300 秒
- 两次自动重启最短间隔：21600 秒（6 小时）
- 探测目标：`223.5.5.5`、`119.29.29.29`，任意一个可达即视为正常

LuCI 页面位于：`服务 → 光猫断线看门狗`，包含“运行设置”和“事件日志”两个页面。

## 事件日志

- 只在断线开始、自动恢复、重启尝试、重启成功/失败以及静默期结束时写入一条，不记录每次正常探测。
- 运行设置页顶部显示最近一次断线/重启、最近 7 天与 30 天的断线和自动重启次数。
- 每条记录包含时间、事件、自动/手动来源、持续时间和结果说明。
- 持久日志保存在 `/etc/onu-watchdog.events`，权限为 `600`；最多 500 条或 128 KiB，超限后仅保留最近 400 条。
- 可以在 LuCI 日志页手动刷新或清空历史。日志不包含光猫密码、Cookie 或响应正文。

## 一键安装

在 OpenWrt SSH 终端执行：

```sh
sh -c 'u=https://raw.githubusercontent.com/vruru/openwrt-onu-watchdog/main/bootstrap.sh; if command -v wget >/dev/null 2>&1; then wget -qO- "$u"; elif command -v uclient-fetch >/dev/null 2>&1; then uclient-fetch -q -O - "$u"; elif command -v curl >/dev/null 2>&1; then curl -fsSL "$u"; else opkg update && opkg install curl ca-bundle >/dev/null && curl -fsSL "$u"; fi' | sh
```

安装完成后打开 `服务 → 光猫断线看门狗`，填写光猫管理地址和普通管理密码，勾选启用并保存。密码只写入 OpenWrt 本机的 `/etc/config/onu_watchdog`，权限为 `600`，不会进入 GitHub 仓库。

在全新系统上，安装器还会自动识别 `network.WAN.device`，创建光猫管理接口 `MODEM`（`192.168.1.2/24`）以及 `lan → modem` 防火墙规则；已有同名配置不会被覆盖。如果 WAN 物理设备无法自动识别，安装器会提示输入，例如 `eth1`。

启动命令会依次尝试 `wget`、`uclient-fetch` 和 `curl`；三者都不存在时会通过 `opkg` 自动安装 `curl`。进入安装器后，缺少的 `curl`、`openssl`（`openssl-util` 包）、`jsonfilter` 和事件日志锁所需的 `flock` 也会自动补齐；安装后再次检查必要命令，检查通过才开始复制文件和配置网络。

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

连配置、重启状态与事件日志一起删除：

```sh
PURGE=1 sh uninstall.sh
```

## 资源占用

后台只有一个 BusyBox `ash` 常驻进程，当前实测约 1.0～1.1 MiB RSS、1 个线程、4 个文件描述符。每轮检测执行后子进程都会退出。持久事件日志只在状态变化时写入，容量有硬上限，不建立持续增长的数据库或队列。

## 安全说明

- 不要从 WAN 开放光猫管理页面或 LuCI 页面。
- 自动重启不能修复光猫 Web 服务也完全卡死的情况；这种情况需要可远程断电的智能插座。
- 当前加密公钥来自上述型号与固件的 `/js/code.js`。更换光猫或固件后应重新验证重启接口。

## 依赖与本地检查

本项目直接发布 shell 脚本、LuCI JavaScript 视图和 JSON 配置，没有语言包管理器依赖清单、锁文件或编译步骤。运行环境需要 OpenWrt/iStoreOS 的 BusyBox `ash` 和常用命令、UCI、ubus、procd、rpcd 与 LuCI（`view`、`form`、`fs`、`ui` 模块）。安装器通过设备的软件源补齐 `curl`、`openssl-util`、`jsonfilter`、`flock`，不固定跨固件的软件包版本。

`npm audit`、`go vet`、`composer audit` 和 `pip-audit` 不适用。设备侧依赖的 CVE 判断需要实际固件版本、已安装软件包版本及厂商补丁信息；仓库中的命令名称不能证明设备没有漏洞。本机检查也不代替真实设备上的 LuCI、procd、网络和光猫协议验证。

在仓库目录执行：

```sh
python3 -B -m unittest discover -s tests -v
for file in bootstrap.sh install.sh uninstall.sh onu-watchdog.init onu-watchdog; do
    sh -n "$file" || exit 1
done
node --check onu-watchdog.js
node --check onu-watchdog-log.js
python3 -c 'import json,pathlib; [json.loads(p.read_text()) for p in pathlib.Path(".").glob("*.json")]'
shellcheck -s ash bootstrap.sh install.sh uninstall.sh
shellcheck -s ash --exclude=SC2034,SC2154 onu-watchdog.init
shellcheck -s ash --exclude=SC1091,SC2015 onu-watchdog
git diff --check
```

测试仅模拟依赖探测和 `opkg` 行为，不写入系统文件。ShellCheck 排除项对应 OpenWrt 服务框架使用的变量（SC2034、SC2154）、设备侧配置文件（SC1091），以及原有登录判断中预期的 `A && B || C` 行为（SC2015）。Node.js、Python 和 ShellCheck 仅用于开发检查，不是设备运行依赖。
