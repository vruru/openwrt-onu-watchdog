# 生产部署与回滚流程

> 最新状态：固定提交 `7305fff` 的修复安装器已部署并验收通过，完整记录见文末“2026-10-05 23:21 升级完成记录”。此前“本次未部署”描述的是 22:43–22:44 的首次核查，作为历史证据保留。

## 本次结论（2026-10-05）

已确认生产设备及可用管理入口，watchdog 已安装且运行正常。**本次未部署**：`install.sh` 的平铺备份会覆盖两组同名文件，无法提供完整的程序回滚备份，不满足本次任务要求的安全升级条件。未运行安装器、安装软件包、修改设备配置或重启服务。

本次待部署提交为 `35dab726c2719fb2d8526aeba201489700583bb3`。核查时 GitHub `main` 为 `95394f21a8941952c6976762973a161d1d93fd3f`，包含该修复；后者只更新 README。下述记录来自现场只读检查，而不是旧运维记录中的状态。

## 生产设备与管理入口

| 项目 | 现场确认结果 |
| --- | --- |
| 生产路由器 | iStoreOS，LAN 地址 `192.168.0.253`，主机名 `iStoreOS` |
| 系统版本 | iStoreOS `24.10.8 2026073111`，`x86/64`，内核 `6.6.144` |
| 虚拟化位置 | PVE `192.168.0.4` 的 VM `100`，VM 名称 `OpenWrt`，运行中，guest agent 可用 |
| 已验证的 SSH 入口 | `root@192.168.0.4:22`，本机已有 SSH 密钥可登录 |
| 来宾执行入口 | 经 PVE SSH 执行 `qm guest exec 100 --pass-stdin 1 -- /bin/sh` |
| 路由器直接 SSH | `root@192.168.0.253:22` 可达，但本机现有密钥的非交互认证被拒绝；未尝试密码 |
| 非目标入口 | `192.168.0.253:12025` 返回 `kubo-debian`，不是该 OpenWrt 来宾，不用于部署 |

本机 `~/.ssh/config` 不存在，`known_hosts` 有相关 LAN 主机记录。`LocalOps` 路由器运维脚本提供 `.253` 的线索，近期运维脚本提供 PVE/VM 100 的入口；最终归属由来宾现场的系统信息、LAN 地址和 watchdog 文件确认。`~/unifi-backups` 中的备份属于 UniFi AP `U7 Long-Range-2FSF`，不是 watchdog 生产设备。

可复用的只读检查入口如下。PVE 返回 JSON，需同时检查 `exitcode`、`out-data` 和 `err-data`；宿主机 SSH 成功不等于来宾命令成功。长任务若只返回来宾 PID，继续用 `qm guest exec-status 100 <PID>` 查询至退出，再判定结果。使用已登记的 SSH 主机密钥，不自动接受变化的主机密钥。

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@192.168.0.4 \
  'qm status 100; qm guest cmd 100 get-osinfo'

ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@192.168.0.4 \
  'qm guest exec 100 --pass-stdin 1 -- /bin/sh' <<'SH'
/etc/init.d/onu-watchdog status
printf 'status_exit=%s\n' "$?"
/usr/sbin/onu-watchdog check
printf 'check_exit=%s\n' "$?"
logread -e onu-watchdog | tail -n 30
SH
```

## 当前已安装版本的证据

核查时间为 `2026-10-05 22:43:05 +08:00`，补充健康检查为 `22:44:07 +08:00`。

GitHub releases 和 tags API 均返回空数组，无 release tarball 或语义版本号可供比对。`opkg status onu-watchdog luci-app-onu-watchdog` 无输出，符合本项目直接复制文件、没有 IPK 的发布方式，不能据此判定未安装。

已下载并读取 GitHub 以下固定提交的源码归档，核对其中六个部署文件的 SHA-256；三个归档中的运行文件均与设备一致：

- `6d4a08d7476a9aa0ec4113d8081ce22d679816b6`：当前运行文件最早对应的仓库提交，加入运行设置页的断线摘要。
- `35dab726c2719fb2d8526aeba201489700583bb3`：安装器依赖预检修复，运行文件没有变化。
- `95394f21a8941952c6976762973a161d1d93fd3f`：README 更新，运行文件没有变化。

因此，**当前运行文件与 `6d4a08d`、`35dab72`、`95394f2` 一致，无法区分设备当时执行过哪一版安装器**。没有发现设备 `/root`、`/tmp` 三层目录内保留的 `install.sh`；不能宣称本次或此前已执行 `35dab72` 的安装器。

| 设备文件 | SHA-256 |
| --- | --- |
| `/usr/sbin/onu-watchdog` | `8d9065249e6884f295a3230f526e8800b3795b7c8f5d7178f2c5d32393313604` |
| `/etc/init.d/onu-watchdog` | `2264c21dc260506eb8582ca69714c3516f60f19b001900810c4856f69a593c1a` |
| `/www/luci-static/resources/view/services/onu-watchdog.js` | `97717a9b4244aa73a11e62fd36b0bf3b7e3ff8fb47c76874fd6ffc9fe717c834` |
| `/www/luci-static/resources/view/services/onu-watchdog-log.js` | `85365e0bdefc5fa4e8ed221167f46f00a1c94345b15d05ebf36b23cf57a234ca` |
| `/usr/share/luci/menu.d/luci-app-onu-watchdog.json` | `2c73bbb674358862338cb6916f5b6c953af29a4502b8ebfbbd4fcf30321f43cd` |
| `/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json` | `009997421dca96672013670b3f8213feb0ad2122a033bdbd140dbda817b3e003` |

健康检查结果：`/etc/init.d/onu-watchdog status` 返回 `running`、退出码 `0`；ubus 实例 `running=true`，PID `12813`；开机启动已启用，UCI `enabled=1`。单次 `check` 返回 `internet: ok (device pppoe-WAN)`、退出码 `0`，未调用重启光猫的命令。

`logread -e onu-watchdog` 为空，不能证明历史上没有故障。持久事件文件可读取，尾部有 `service_started`、`offline_started`、`offline_recovered` 记录。

全部安装依赖命令已存在。`/usr/bin/flock` 指向 `../../bin/busybox`，`busybox` 软件包为 `1.36.1-r3`；没有独立 `flock` 软件包记录不等于缺少命令，本设备无需为这次修复补装 `flock`。

## 升级安全检查与本次停止原因

以核查时 `main` 中的 [install.sh](../install.sh) 为准：先检查/安装依赖，然后备份，再替换代码。已有 `/etc/config/onu_watchdog` 的内容确实会保留，只调整权限为 `600`。依赖安装发生在备份之前，不属于该文件备份的保护范围。

但是安装器第 43–55 行使用 `cp -a "$file" "$BACKUP_DIR/"`，全部按 basename 平铺保存：

| 先复制的文件 | 后复制的文件 | 备份结果 |
| --- | --- | --- |
| `/usr/sbin/onu-watchdog` | `/etc/init.d/onu-watchdog` | 只剩 init 脚本，核心脚本备份丢失 |
| `/usr/share/luci/menu.d/luci-app-onu-watchdog.json` | `/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json` | 只剩 ACL，菜单备份丢失 |

已在开发机临时目录用真实源码和相同复制顺序复现：备份 `onu-watchdog` 的哈希等于 init 脚本，备份 JSON 的哈希等于 ACL。生产设备未执行该实验。**不能把这些同名备份分别复制到两个目标路径进行回滚。**

设备已有 `network.MODEM`（`eth1`、`192.168.1.2`）、`firewall.modem`、`firewall.lan_to_modem`，当前安装器不会覆盖这些 section。但安装器不是事务，途中失败不会自动回滚，成功时还会重启 rpcd、启用并重启 watchdog。配置保留不等于完整回滚可用，因此本次跳过部署。

恢复部署的前提是先修复并验证安装器的备份路径冲突，保留各文件原始路径或使用互不冲突的备份名称；现场重新核对脚本后再执行安装流程。本次只新增本文档，没有修改安装器，也没有通过额外备份绕过停止条件。

## 后续升级流程

以下是后续操作规程，**本次未执行其中的写操作**。当前存在上述备份缺陷的 `35dab72` / `95394f2` 安装器仍不满足本次部署门槛。

1. 在开发机核对仓库、远端、目标提交与工作区，完成与变更对应的检查。确认来宾仍为 VM 100、LAN 地址仍为 `.253`，服务和现有文件仍可识别。不要以 SSH 可达代替设备身份检查。
2. 审阅目标 `install.sh`：确认备份冲突已经修复、备份失败会在替换前退出、已有配置保留。确认安装依赖、副作用和原版本到目标版本的差异；检查 `uci changes` 是否有未提交配置，存在时先处理归属，不让安装器意外提交其他人的修改。
3. 记录升级前运行文件哈希、配置/网络/防火墙哈希、UCI 启用开关、服务实际运行状态和开机启动状态。配置含密码，不输出全文、不上传 GitHub；原始证据只保存到受限的设备目录或本机 `LocalOps`。
4. 在运行安装器前创建独立、保留完整路径的备份，并记录升级前缺失的文件。下面的示例在**目标来宾 root shell**执行；不停止服务，事件/重启状态是时间点快照，不能当作跨文件事务快照。

```sh
set -eu
umask 077
BACKUP="/root/onu-watchdog-preupgrade-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$BACKUP"
if /etc/init.d/onu-watchdog enabled; then
    printf '1\n' > "$BACKUP/boot-enabled"
else
    printf '0\n' > "$BACKUP/boot-enabled"
fi
if /etc/init.d/onu-watchdog status >/dev/null 2>&1; then
    printf '1\n' > "$BACKUP/service-running"
else
    printf '0\n' > "$BACKUP/service-running"
fi
: > "$BACKUP/present.files"
: > "$BACKUP/absent.files"
set --
for rel in \
    usr/sbin/onu-watchdog \
    etc/init.d/onu-watchdog \
    etc/config/onu_watchdog \
    etc/onu-watchdog.last_reboot \
    etc/onu-watchdog.events \
    etc/config/network \
    etc/config/firewall \
    usr/share/luci/menu.d/luci-app-onu-watchdog.json \
    usr/share/rpcd/acl.d/luci-app-onu-watchdog.json \
    www/luci-static/resources/view/services/onu-watchdog.js \
    www/luci-static/resources/view/services/onu-watchdog-log.js; do
    if [ -e "/$rel" ]; then
        printf '%s\n' "$rel" >> "$BACKUP/present.files"
        set -- "$@" "$rel"
    else
        printf '%s\n' "$rel" >> "$BACKUP/absent.files"
    fi
done
tar -czpf "$BACKUP/files.tar.gz" -C / "$@"
tar -tzf "$BACKUP/files.tar.gz" > "$BACKUP/archive.files"
sha256sum "$BACKUP/files.tar.gz" > "$BACKUP/archive.sha256"
printf '独立备份：%s\n' "$BACKUP"
```

5. 核对归档包含 `present.files` 的每个路径，特别是两组同名文件；将备份作为敏感文件保管。取得固定提交的完整源码归档并核对哈希，再传到来宾 `/tmp`、解压，进入源码目录执行 README 的 `sh install.sh`。PVE 通道可用 `qm guest exec` 调用已暂存的脚本；操作在来宾执行，不在宿主机运行安装器。`bootstrap.sh` 会下载随时变化的 `main`，需要固定版本审计时优先使用文档支持的完整源码本地安装方式。
6. 安装后检查 guest exec 的来宾退出码、六个运行文件哈希、`/etc/init.d/onu-watchdog status`、ubus 实例、`logread -e onu-watchdog` 和单次 `check`；确认配置内容、网络和防火墙与升级前一致。UCI `enabled=0` 时没有守护进程属于配置预期，不能直接判为安装失败。用 LuCI 检查运行设置与事件页是否可读取，不用 `reboot-now` 测试部署。
7. 健康检查失败时保留输出，使用下面的回滚流程；成功则记录固定提交、安装器退出码、备份路径和检查时间。部署结果与 GitHub 文档推送结果分别记录。

## 回滚流程

仅使用已验证、保留完整路径的独立归档，或修复后的安装器完整备份。核查到的平铺备份不能用来完整回滚。本次没有部署，**无需也未执行回滚**。

1. 保留故障日志和当前配置，确认备份归档哈希正确、文件列表完整；读取升级前的 `boot-enabled`、`service-running`，确认配置启用开关。先停止 watchdog，避免恢复文件时进程继续运行；不重启光猫或整台路由器。
2. 对下表六个代码文件逐项处理：升级前存在的文件从归档按原路径恢复；升级前缺失、由本次安装新增的代码文件才删除。恢复后核对与升级前哈希一致。不要从单个平铺文件恢复两种不同用途的目标。

| 仓库文件 | 归档中的原路径（相对 `/`） |
| --- | --- |
| `onu-watchdog` | `usr/sbin/onu-watchdog` |
| `onu-watchdog.init` | `etc/init.d/onu-watchdog` |
| `onu-watchdog.js` | `www/luci-static/resources/view/services/onu-watchdog.js` |
| `onu-watchdog-log.js` | `www/luci-static/resources/view/services/onu-watchdog-log.js` |
| `luci-app-onu-watchdog.menu.json` | `usr/share/luci/menu.d/luci-app-onu-watchdog.json` |
| `luci-app-onu-watchdog.acl.json` | `usr/share/rpcd/acl.d/luci-app-onu-watchdog.json` |

例如，在来宾 root shell 中将 `BACKUP` 设为核对过的真实备份路径后，单独恢复核心脚本：

```sh
/etc/init.d/onu-watchdog stop
tar -xzpf "$BACKUP/files.tar.gz" -C / usr/sbin/onu-watchdog
```

该命令只是单文件示例，其余代码文件按表逐项恢复；不要直接把整个归档解压到 `/`，那会同时覆盖配置、网络、防火墙、事件和冷却状态。

3. 正常代码回滚保留现有 `/etc/config/onu_watchdog`、事件和最后重启状态。只有确认配置受本次升级破坏时才单独恢复，并保持配置权限 `600`。不要删除或盲目回退 `/etc/onu-watchdog.last_reboot`，否则可能丢失静默/冷却保护；覆盖事件文件会丢失备份之后的新记录。需要恢复状态时先保留当前文件并核对事件时间线。
4. 网络、防火墙未变化时不恢复、不 reload。若安装器确实新增或损坏 section，先核对本次差异及后续合法修改，再制定针对性的恢复；不整文件覆盖他人新配置。`opkg` 的包变更不在文件归档中，不随程序回滚自动卸载依赖。
5. 清理 LuCI 缓存并重启 rpcd，恢复升级前开机启动状态，再按升级前实际运行状态及配置启动服务。原本停用或停止的服务保持该状态；正常启用运行时检查 `status`、ubus、`check` 和日志，并复核运行文件哈希。

## 本次检查与证据保存

本次设备操作仅为只读身份、文件、配置字段、软件包和健康检查；没有获取或记录光猫密码。开发机的 6 项安装依赖回归测试通过，并用临时文件验证了备份覆盖缺陷。这些依赖测试不覆盖回滚完整性。

原始探测 JSON、固定提交源码归档与哈希、备份碰撞复现结果保存在本机 `/Users/tsy/LocalOps/openwrt-onu-watchdog-deploy-20261005/`，不提交这些运维产物。GitHub 仅同步本项目部署文档；本次结论是“生产目标已确认，服务健康，因备份缺陷跳过部署”。

## 2026-10-05 23:21 升级完成记录

### 背景与修复

来源版本无法由相同运行文件确定，故以 GitHub 仓库 `vruru/openwrt-onu-watchdog` main 分支的修复提交 `7305fff34e98ebfec08bcb110d4e1a168abab26e` 为基准。修复仅针对安装器逻辑：`install.sh` 为每个文件设置 `backup_file="$BACKUP_DIR$file"`，创建其父目录后用 `cp -a` 保存，保留原 backup-first 顺序。Bootstrap 未共享此缺陷，未作改动。代码验证结果：12 个 unittest 全部通过（6 依赖 + 6 备份），所有 shell 脚本 `sh -n` 和 `shellcheck` 通过，两份 JS 的 `node --check`、JSON 解析和 `git diff --check` 通过。旧安装器备份测试结果为 4 fail / 1 error / 1 pass，证实修复必要性。

### 部署前置与归档

执行 `git pull --rebase` 同步仓库，无强推。GitHub 固定归档 SHA 为 `5c8bfcd467ea07663246338e635ce0784d01f8e0ef215805aad53bfc01f2e363`，包含全部 16 个 tracked files，与提交内容一致。安装器 SHA 为 `6632b108268679db6c10c0310031ae4c2ab6393fee86b8a55e41ec5a483a2bdf`。通过 PVE `.4` VM100 guest exec 确认身份为路由器 `.253`。部署前基线哈希全部一致，无未应用 `uci changes`，所有依赖命令已存在，无需运行 opkg；`network.MODEM`、`firewall.modem` 和 `firewall.lan_to_modem` 均已存在，无需交互输入。

### 健康证据

最终安装命令 `/bin/sh install.sh </dev/null` 于 23:21:10 执行，`install.exit=0`，PVE guest `exit=0`。23:21:25 健康检查：服务 status 返回 `running`，exit=0，UCI `enabled=1`，开机启动已启用。ubus `instance1.running=true`，PID `24262`。rpcd PID 由 23407 变更为 24185，状态 `running true`。单次 `/usr/sbin/onu-watchdog check` 输出 `internet: ok (device pppoe-WAN)`，exit=0。`logread` 仅含 3 条正常启动 `user.notice`，无警告或错误。LuCI 设置与日志页面通过已授权 guest root 临时 120 秒只读 ubus 会话获得认证 HTTP 200，预期视图 loader 存在，两 JS 文件 HTTP 200 且 SHA 与源文件一致。临时会话已销毁，`luci-auth.conf` 已删除。**注**：未执行真实浏览器登录后完整交互，Chrome 仅验证至登录页。

### 首次误判与回滚

首次部署于 23:19:42 执行，`install` 成功 `exit=0`。但验收脚本错误要求 `logread` 完全为空，将正常 `started` notice 误判为失败。按预案于 23:20:31 执行逐文件回滚：6 个代码路径恢复原哈希，核对后 rpcd/watchdog 恢复运行，internet check ok。配置、网络、防火墙、事件和 `last_reboot` 全部保留。首次备份 `/root/onu-watchdog-preupgrade-20261005-231841`（其中 `files.tar.gz` 的 SHA `7930f5ddd4f32e146b68c433a9433fad6bef2eef2f3845327fcf17c455e083ed`）及 installer 备份 `/root/onu-watchdog-backup-20261005-231942` 均保留未删除。修改验收标准允许精确匹配正常 `started` 通知后，再次部署同 commit 成功。

### 配置状态保留

受保护配置文件升级前后 SHA 完全一致，证明配置未变更：`config watchdog` SHA `baa7a3f74f699a747f67fc8e92bf8e304d3670d7c8f9395eb53624e0abb3d091`（权限 600）；`network` SHA `daf1c13fcbb79ad5a3a494cbc5960d9c63b6b65e4ab7b5632a55fb97feab45c3`；`firewall` SHA `61ca9547e07f2056bbf2d4c5330d04674c37d101bcc8e6624760bcceeb7f0f1e`；`last_reboot` SHA `f281b4313f8ce39066bc6ff1134fe49e272af49f17127f5b16d72ba8d8573333`。`events` 文件正常追加 `service_started` 记录，不覆盖历史。第二次部署前 events SHA `01248a234ad94e2b3a3235b4a702d67d01c5f6d205f543c348db4e536dbea80f`，部署后 SHA `8b662035a67f23164600ef76cac84b2aab42dc2d75de14d315fd246b607ef5a0`。全程未重启光猫/路由器，未 reload 网络/防火墙，未安装额外包。

### 最终备份与运维证据

最终独立备份归档 `/root/onu-watchdog-preupgrade-20261005-232101/files.tar.gz`，SHA `db58da4117aa1798e0f8d097ee0bf39719b2bdcc8f9dc04d0158e624e7309988`。`present.files` 列出 11 个原始路径，`absent.files` 为空，解压至 `verified` 目录逐路径逐哈希核对通过。安装备份目录 `/root/onu-watchdog-backup-20261005-232110`，11 个路径哈希等于独立备份。运维证据保存于本机 `/Users/tsy/LocalOps/openwrt-onu-watchdog-upgrade-20261005/`，包含 guest JSON、脚本、归档及旧版回归输出。部署验收与文档推送分别确认；本节记录的是设备上已经完成的操作。

### 运行文件哈希表

| 文件路径 | SHA256 |
| :--- | :--- |
| `/usr/sbin/onu-watchdog` | `8d9065249e6884f295a3230f526e8800b3795b7c8f5d7178f2c5d32393313604` |
| `/etc/init.d/onu-watchdog` | `2264c21dc260506eb8582ca69714c3516f60f19b001900810c4856f69a593c1a` |
| `/www/luci-static/resources/view/services/onu-watchdog.js` | `97717a9b4244aa73a11e62fd36b0bf3b7e3ff8fb47c76874fd6ffc9fe717c834` |
| `/www/luci-static/resources/view/services/onu-watchdog-log.js` | `85365e0bdefc5fa4e8ed221167f46f00a1c94345b15d05ebf36b23cf57a234ca` |
| `/usr/share/luci/menu.d/luci-app-onu-watchdog.json` | `2c73bbb674358862338cb6916f5b6c953af29a4502b8ebfbbd4fcf30321f43cd` |
| `/usr/share/rpcd/acl.d/luci-app-onu-watchdog.json` | `009997421dca96672013670b3f8213feb0ad2122a033bdbd140dbda817b3e003` |

*注：以上六运行文件升级前后相同，哈希值一致。*

本次只改变安装器与开发机测试/说明，六个部署代码文件的字节内容未变化，因此升级前后哈希相同属于预期；设备实际执行固定提交安装器的证据为归档/安装器哈希、`time-install`、`install.log` 和 `install.exit`，不能只凭运行文件哈希判定安装器版本。旧安装器 SHA-256 为 `3af9ce3b83913c392201732cae20b8c9f7e662245e04c5b13a9277a651589bcc`，修复后为上述 `6632b108…`。

最终健康脚本和来宾退出码均为 `0`。验收中的“日志干净”允许精确匹配正常的 `user.notice onu-watchdog: started: fail=… post-reboot-wait=… cooldown=…` 启动通知；要求没有错误、警告或其他异常，不能要求重启后日志完全为空。每次安装后的健康验收只调用一次 `check`；首次回滚另按回滚规程调用一次恢复检查。

回滚准备已验证：最终独立目录与安装器备份目录权限均为 `700`，归档为 `600`，归档哈希复验通过；事件文件的备份内容仍为当前事件文件的完整前缀，历史没有覆盖。最终独立目录还保存 `rollback-code.sh`（权限 `700`、`sh -n` 通过），只逐项恢复六个代码路径并恢复原开机/运行状态，保留当前配置、事件与冷却状态。该最终备份的回滚脚本仅准备、未执行；首次备份的逐文件回滚已实际执行并验证成功。
