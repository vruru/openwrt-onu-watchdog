# OpenWrt 光猫断线看门狗

适用于中兴 `ZXHN G7615V2-G-C`（中国联通固件 `V3.0.5P1T2`）的 OpenWrt/iStoreOS 看门狗插件。

当指定的 WAN 逻辑接口连续无法访问公网探测地址达到设定时间时，程序通过光猫普通管理账号登录管理页面，按照原厂 Web 协议的加密流程提交重启命令，以尝试恢复外网中断；光猫 Web 管理服务必须仍然可访问。

## 项目特点与架构

- **直接部署**：直接发布 Shell 脚本、LuCI JavaScript 视图和 JSON 配置。无编译步骤，无 IPK 包构建流程，无语言包管理器依赖清单。
- **安全隔离**：正常 UCI 配置方式下，密码保存在设备本机 `/etc/config/onu_watchdog`，权限为 `600`；不记录光猫密码、Cookie 或 HTTP 响应正文到日志中。
- **事件驱动日志**：仅在状态发生显著变化（服务启动、断线开始、恢复、重启尝试/接受/失败、冷却提示、静默期结束后的检测结果）时写入持久化日志，避免高频探测产生的 IO 压力。
- **自动网络配置**：安装时可自动识别 WAN 物理设备，创建专用的光猫管理接口 (`MODEM`) 及防火墙转发规则，不覆盖已有同名配置。

`procd` 启动常驻的 `onu-watchdog daemon`，通过 `ubus` 读取被检测逻辑接口的状态和 `l3_device`，将 IPv4 ping 绑定到该设备。接口状态不是 up、没有三层设备或两个探测目标均不可达时判为失败；`223.5.5.5`、`119.29.29.29` 任一可达即恢复正常，这两个目标目前固定在脚本中。连续失败达到门槛且不在冷却期时，使用 `curl` 登录光猫并通过 OpenSSL 构造 RSA/PKCS#1 v1.5 与 AES-256-CBC 加密的重启表单。

LuCI 通过 `fs.exec` 和 rpcd ACL 调用设备上的脚本，通过 UCI 读写配置；菜单 JSON 注册“运行设置”和“事件日志”。运行状态由服务管理器提供，历史摘要由保留的事件记录计算。

### 源文件与部署路径对应

| 仓库源文件 | 目标设备路径 | 用途 |
| :--- | :--- | :--- |
| `onu-watchdog` | `/usr/sbin/onu-watchdog` | 核心检测逻辑、重启执行脚本 |
| `onu-watchdog.init` | `/etc/init.d/onu-watchdog` | Procd 服务启动脚本 |
| `onu_watchdog.uci` | `/etc/config/onu_watchdog` | UCI 配置文件模板 |
| `onu-watchdog.js` | `/www/luci-static/resources/view/services/onu-watchdog.js` | LuCI 运行设置页面 |
| `onu-watchdog-log.js` | `/www/luci-static/resources/view/services/onu-watchdog-log.js` | LuCI 事件日志页面 |
| `luci-app-onu-watchdog.menu.json` | `/usr/share/luci/menu.d/luci-app-onu-watchdog.json` | LuCI 菜单注册 |
| `luci-app-onu-watchdog.acl.json` | `/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json` | LuCI 访问控制权限 |

仓库入口：[bootstrap.sh](bootstrap.sh) 下载 `main` 分支归档并调用 [install.sh](install.sh)；[uninstall.sh](uninstall.sh) 停止服务并移除插件文件。[tests/test_install_dependencies.py](tests/test_install_dependencies.py) 仅覆盖安装器的依赖预检。

## 设备前提与构建

安装和运行需要带 LuCI 的 OpenWrt/iStoreOS，安装器必须以 root 身份在目标设备执行。系统需提供 BusyBox `ash` 与常用命令（包括支持脚本参数的 IPv4 `ping`）、UCI、ubus、procd、rpcd，以及 LuCI 的 `view`、`form`、`fs`、`ui` 模块。安装器检查 `/www/luci-static/resources` 是否存在，并在复制文件前检查 `curl`、`openssl`、`sha256sum`、`awk`、`sed`、`jsonfilter`、`flock`、`ubus`、`uci`。

缺少 `curl`、`openssl`、`jsonfilter`、`flock` 时，会通过 `opkg` 安装对应的 `curl`、`openssl-util`、`jsonfilter`、`flock` 软件包；此时需要可用的软件源和联网条件。安装器不会自动补装其他系统组件，也不固定跨固件的软件包版本。

没有编译步骤、OpenWrt SDK 打包规则或 IPK 构建命令。开发机只需取得完整仓库，文末检查使用 Python 3、Node.js 和 ShellCheck；这三项不是设备运行依赖。

## 安装与升级

### 1. 一键安装 (OpenWrt SSH)

在 OpenWrt 的 root SSH 终端执行以下命令；入口下载并运行当前 `main` 分支的安装脚本。安装器会自动尝试使用 `wget`、`uclient-fetch` 或 `curl` 获取源码，若均不存在则通过 `opkg` 安装 `curl`。随后自动补齐 `openssl-util`、`jsonfilter`、`flock` 等依赖。

```sh
sh -c 'u=https://raw.githubusercontent.com/vruru/openwrt-onu-watchdog/main/bootstrap.sh; if command -v wget >/dev/null 2>&1; then wget -qO- "$u"; elif command -v uclient-fetch >/dev/null 2>&1; then uclient-fetch -q -O - "$u"; elif command -v curl >/dev/null 2>&1; then curl -fsSL "$u"; else opkg update && opkg install curl ca-bundle >/dev/null && curl -fsSL "$u"; fi' | sh
```

### 2. 本地安装

将完整仓库源码下载并解压到 OpenWrt 设备后，进入包含 `install.sh` 的仓库目录，在 **root** 权限下执行：

```sh
sh install.sh
```

重复运行同一安装方式即可升级。已有 `/etc/config/onu_watchdog` 会保留，密码和策略不会被模板覆盖；首次安装的模板默认关闭自动看门狗。

**安装会执行的操作：**

- **备份机制**：安装前会自动备份现有的关键文件（脚本、配置、重启状态、事件日志、网络与防火墙配置、LuCI 菜单/ACL/视图）至 `/root/onu-watchdog-backup-YYYYMMDD-HHMMSS`。
- **网络配置**：若不存在 `network.MODEM` 接口，安装器会探测 `network.WAN.device`（逻辑接口名 `WAN` 大小写敏感）。优先使用环境变量 `MODEM_DEVICE` 指定的物理设备，否则读取 `network.WAN.device`。只有标准输入是终端时才会提示输入物理网卡名；无设备信息时安装失败，非交互安装应提前提供 `MODEM_DEVICE`。创建的 `MODEM` 使用静态地址 `192.168.1.2/24`，不设置默认路由、对端 DNS 或 IPv6 委派。
- **防火墙配置**：分别检查 `firewall.modem` 和 `firewall.lan_to_modem`，缺失时创建 `modem` 区域及 `lan → modem` 转发。区域启用 masquerade，策略为 input/forward REJECT、output ACCEPT。已有同名网络或防火墙 section 不覆盖。
- **配置生效**：网络或防火墙有新增配置时分别 reload；随后清理 LuCI 缓存并重启 rpcd。
- **服务状态**：安装完成后自动执行 `enable` 和 `restart`。若原有配置中 `enabled` 为 `1`，服务将立即运行；否则提示去 LuCI 启用。

安装器自动建网只读取固定的 `network.WAN.device`，不会跟随 `wan_interface` 配置查找其他逻辑接口。确认物理设备正确，并检查 `192.168.1.0/24` 是否与现有 LAN 等网段冲突。修改光猫管理 URL 不会自动调整 `MODEM` 的地址；自定义网段或已有同名 section 的路由、防火墙需要自行核对。

### 3. 卸载

在 **root** 权限下执行：

**保留配置卸载**（停止并取消服务开机启动，删除程序和 LuCI 文件，保留 UCI 配置、重启状态文件和事件日志）：

```sh
sh uninstall.sh
```

**完全清除卸载**（删除程序、LuCI 文件、UCI 配置、`/etc/onu-watchdog.last_reboot` 状态文件、`/etc/onu-watchdog.events` 日志文件）：

通过环境变量 `PURGE` 启用脚本定义的清除模式后运行同一卸载脚本；本文只列变量名称，不展示取值。卸载不会删除安装器创建的 `MODEM` 接口、防火墙区域/转发、备份目录、旧版 `/etc/onu-watchdog.conf`，也不会卸载依赖软件包。

## 运行与配置

### 环境变量与配置优先级

1.  **UCI 优先**：当 `uci` 可用且 `onu_watchdog.main` section 存在时，程序优先读取 `/etc/config/onu_watchdog` 中的字段。
2.  **旧版兼容**：不满足上述条件时，程序尝试读取可读的 `/etc/onu-watchdog.conf`（旧版格式）。
3.  **环境变量**：正常 UCI 安装和运行没有必需导出的环境变量。`MODEM_DEVICE` 是可选安装输入，用于指定物理设备；自动探测失败且无法交互输入时需要提供。`PURGE` 是可选卸载控制，用于请求删除配置、重启状态和事件日志。

若 UCI section 和旧版配置文件都不存在，脚本会报配置缺失并退出，仅导出变量不能跳过这一检查。UCI section 存在时优先读取其中的字段，不会再从旧版配置文件补齐空缺。

**旧版 Shell 配置变量名称**（在 `/etc/onu-watchdog.conf` 中使用，新安装建议使用 UCI；此文件由脚本直接加载，需限制访问权限）：

- `MODEM_URL`
- `MODEM_PASSWORD`
- `WAN_INTERFACE`
- `CHECK_INTERVAL`
- `FAIL_SECONDS`
- `POST_REBOOT_WAIT`
- `REBOOT_COOLDOWN`

### UCI 字段与限制

LuCI 页面路径：`服务 → 光猫断线看门狗`，包含“运行设置”和“事件日志”。在运行设置中填写光猫管理地址、普通管理密码和被检测的 WAN 逻辑接口，勾选启用后“保存并应用”。

| 字段 (UCI Option) | 说明 | LuCI 校验范围/模板默认值 | 备注 |
| :--- | :--- | :--- | :--- |
| `enabled` | 启用开关 | `0` (默认) | 需勾选后保存并应用 |
| `modem_url` | 光猫管理地址 | 默认 `http://192.168.1.1` | 固定创建逻辑接口地址，自定义 URL 不联动更新网络接口 IP |
| `modem_password` | 光猫普通管理密码 | 必填 | 密码字段，不记录明文日志 |
| `wan_interface` | 被检测的 WAN 接口 | 默认 `WAN` | **大小写敏感**，对应 UCI network 中的逻辑接口名 |
| `check_interval` | 检测间隔 (秒) | 5-300, 默认 `10` | 建议不低于 5 秒 |
| `fail_seconds` | 连续掉线判定 (秒) | 30-3600, 默认 `60` | 达到此时间才触发重启逻辑 |
| `post_reboot_wait` | 重启后静默时间 (秒) | 120-1800, 默认 `300` | 重启命令发送后停止检测的时间，用于等待 PON 注册/PPPoE 拨号 |
| `reboot_cooldown` | 重启冷却时间 (秒) | 600-86400, 默认 `21600` | 自动重启相对最后一次已接受的手动/自动重启的冷却间隔 |

这些数值范围由 LuCI 表单校验；直接编辑 UCI 或旧版配置时，脚本不会执行同等的范围校验。

**运行逻辑：**

- **冷却机制**：`reboot_cooldown` 仅针对**自动**触发的重启。手动点击“重启光猫”不受冷却时间限制，且手动重启成功后会更新最后重启时间，从而影响后续的自动重启冷却判断。
- **静默期**：重启命令被接受后（HTTP 200），进入 `post_reboot_wait` 静默期。在此期间不进行外网检测，也不判定断线。
- **重启成功判定**：仅当光猫 Web 服务响应 HTTP 200 时视为“重启命令被接受”。这**不证明**光猫已成功重启并恢复联网。若光猫 Web 服务也完全卡死，HTTP 请求将超时/失败，程序记录“重启命令失败”，重新开始连续失败确认窗口，达到门槛且不在冷却期才会再次尝试。重启请求后的连接重置或超时也按失败处理，即使设备可能已经开始重启。

### 服务管理与运行检查

安装后在 **OpenWrt 的 root SSH 终端**检查配置是否生效。也可用下面的服务命令显式重启并检查运行状态：

```sh
# 启用开机启动，并按当前 UCI enabled 设置重启服务
/etc/init.d/onu-watchdog enable
/etc/init.d/onu-watchdog restart
/etc/init.d/onu-watchdog status

# 检查网络接口连通性逻辑 (输出 internet: ok 或 failed)
/usr/sbin/onu-watchdog check

# 查看最近最多 500 条事件
/usr/sbin/onu-watchdog events

# 查看系统日志
logread -e onu-watchdog
```

`enabled` 关闭时，服务启动脚本不会启动守护进程；只执行 `enable` 不会打开 UCI 开关。停止当前服务使用 `/etc/init.d/onu-watchdog stop`，取消开机启动使用 `/etc/init.d/onu-watchdog disable`。服务由 procd 管理并设置 respawn，注册 `onu_watchdog` 和 `network` 配置重载触发器。

`/usr/sbin/onu-watchdog check` 仅执行一次外网检测，失败返回非零状态；`events` 读取事件记录。`reboot-now` 会实际登录光猫并发送手动重启命令，LuCI 提供确认框；命令行调用没有确认框，且不受自动启用开关或自动冷却条件约束。`clear-events` 会清空事件历史，但保留配置和最后重启状态。`daemon`（省略参数时的默认动作）会持续检测，应交由服务管理器启动，避免重复运行多个实例。

## 事件日志详解

- **存储位置**：`/etc/onu-watchdog.events`
- **权限**：`600`
- **记录策略**：
    - 不记录每次正常的 Ping 探测。
    - 记录事件类型：服务启动、检测到断线、断线后自动恢复、发送重启命令、光猫接受重启、光猫重启失败、重启冷却中、重启后恢复、重启后仍断线。
    - 包含时间戳、事件类型、来源（自动/手动/系统）、持续时间和详情。
- **容量限制**：
    - 硬性触发裁剪条件：行数超过 500 条 **或** 文件大小超过 128 KiB。
    - 裁剪操作：保留最近 400 条记录。
    - 128 KiB 是裁剪触发条件，裁剪只按行数保留 400 条，不保证裁剪后的文件必定小于 128 KiB。
- **LuCI 展示**：日志页面显示最近 100 条记录，支持手动刷新和清空。运行设置页显示最近一次断线/已接受的重启，以及最近 7 天、30 天的断线和自动重启次数；统计只基于保留的日志，裁剪或清空后不代表完整期间历史。
- **状态与锁**：`/etc/onu-watchdog.last_reboot` 保存最后一次已接受重启的时间和来源，权限为 `600`，服务重启后仍据此判断静默与冷却。事件写入和清空使用 `flock` 锁 `/var/lock/onu-watchdog-events.lock`。
- **临时文件**：光猫登录与重启请求的 Cookie、响应正文及加密中间文件保存在 `/tmp/onu-reboot.*` 工作目录，进程退出时清理；不会写入事件或系统日志。

## 资源占用

- **进程模型**：后台常驻一个 BusyBox `ash` 进程 (`/usr/sbin/onu-watchdog daemon`)。
- **子进程**：按需启动 ping、curl、OpenSSL 等命令，调用完成后退出。常驻状态变量数量固定；具体 RSS、文件描述符和 CPU 占用应在目标设备上测量。
- **I/O**：持久日志仅在状态变化时写入，无持续增长的数据库或队列。

## 开发机本地检查

在仓库根目录执行以下命令，仅在**开发机**上执行，用于代码静态检查和单元测试，**不触发设备真实运行**。

```sh
# 运行安装器依赖模拟测试
python3 -B -m unittest discover -s tests -v

# 检查 Shell 脚本语法
for file in bootstrap.sh install.sh uninstall.sh onu-watchdog.init onu-watchdog; do
    sh -n "$file" || exit 1
done

# 检查 JavaScript 语法 (需安装 Node.js)
node --check onu-watchdog.js
node --check onu-watchdog-log.js

# 检查 JSON 文件格式 (需安装 Python3)
python3 -B -c 'import json,pathlib; [json.loads(p.read_text()) for p in pathlib.Path(".").glob("*.json")]'

# ShellCheck 检查 (需安装 ShellCheck)
shellcheck -s ash bootstrap.sh install.sh uninstall.sh
shellcheck -s ash --exclude=SC2034,SC2154 onu-watchdog.init
shellcheck -s ash --exclude=SC1091,SC2015 onu-watchdog
git diff --check
```

测试只模拟安装器的依赖探测和 `opkg` 行为，不写入设备系统文件。以上检查不代替目标设备上的 LuCI、procd、网络及光猫协议验证。

*ShellCheck 排除说明：SC2034/SC2154 为 OpenWrt 服务框架变量；SC1091 为设备侧动态源文件；SC2015 为预期的 `A && B || C` 逻辑。*

## 安全与限制

1.  **管理访问**：不要从 WAN 侧开放光猫管理页面或 OpenWrt LuCI 页面。
2.  **协议绑定**：加密公钥来自上述型号与固件的 `/js/code.js`，登录流程也与该固件绑定。更换光猫型号或固件版本后，RSA/AES 加密接口和登录 Token 获取方式可能变更，需重新验证。
3.  **Web 卡死场景**：若光猫 Web 管理服务彻底挂起（无 HTTP 响应），本插件无法通过 Web 接口触发重启。此类情况建议配合可远程控制的智能插座使用。
4.  **版本与依赖检查**：仓库没有 npm、Go、Composer 或 Python 运行依赖清单，`npm audit`、`go vet`、`composer audit`、`pip-audit` 不适用于本项目。设备侧依赖的 CVE 判断需要实际固件、软件包版本及厂商补丁信息，不能仅凭命令名称判断。

## 许可证

[MIT License](LICENSE)。
