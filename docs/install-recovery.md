# 安装失败阶段与受控恢复

安装器预检七个运行源文件可读后才安装依赖；备份目录创建后在 `install-stage.log` 记录阶段。失败输出阶段、退出码和备份位置，保留原退出码。记录不含密码或 UCI 参数。安装仍不是事务，失败时没有自动回滚。

| 阶段 | 失败后可能状态 |
| --- | --- |
| preflight | root/LuCI/源文件预检失败，没有代码复制；没有本次阶段日志 |
| dependencies | opkg 可能部分安装或更新索引；没有本次备份/阶段日志 |
| backup | 备份可能不完整，不能把目录存在当成全部备份完成 |
| runtime-files | 部分代码/菜单/ACL/JS 被复制，旧进程可能仍在运行 |
| uci-config | 原配置保留；首次配置或 MODEM/firewall 新 section 可能已写入/提交，也可能保留 UCI pending changes |
| network-reload / firewall-reload | 配置已提交，reload 可能失败或部分生效 |
| service-restart | LuCI 缓存/rpcd 或 daemon 的服务操作可能只完成部分 |
| acceptance | 安装文件已在位，但 enabled/status 验收未通过 |
| complete | 本次脚本检查成功；不代替浏览器和真实光猫验收 |

恢复先停止唯一 daemon，单独保存失败后的当前 `onu_watchdog`、network/firewall 配置、UCI pending changes、events 和 last_reboot。将当前现场备份与安装前备份分开，限制读取权限。确认安装前备份完整后，只恢复实际被替换的六个运行文件：核心脚本、init、菜单 JSON、ACL JSON、两个 LuCI JS；核对路径、内容和权限。首次安装没有旧文件时，根据本次复制范围和实际文件确认移除或继续安装，不能从空备份猜测恢复。

不要用 `cp -a "$BACKUP_DIR/." /` 或整份旧配置覆盖现有系统。network/firewall/onu_watchdog、事件及冷却状态可能已经有后来的合法改动，必须保留。新增 MODEM/firewall section 或 UCI pending changes 先逐项审阅，再决定应用/撤回；不能全局 `uci revert` 丢弃他人的修改。依赖包可能被其他功能使用，不自动卸载 opkg 安装项。

完成文件核对后只定向恢复相关服务。需要 network/firewall reload 时另选维护窗口并准备管理连接恢复；不能因看门狗恢复而自动 reload 整个网络。根据现有 enabled 配置恢复 daemon，勿无条件启用。恢复后复核唯一实例、事件/冷却保留、日志及 LuCI，真实重启测试另行授权。

`tests/test_install_stages.py` 在临时设备目录运行完整安装器，模拟平台命令，对 dependencies、backup、代码复制、UCI、两种 reload、服务和验收入口注入失败，检查失败阶段/退出码与当前配置状态保留；缺源文件在复制前拒绝。既有依赖和备份回归继续检查实际 opkg/cp 失败以及同名路径备份。未操作生产路由器。
