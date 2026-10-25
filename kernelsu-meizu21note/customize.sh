#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
[ "$KSU" = true ] || abort '! 请在 KernelSU 管理器中安装。'
[ -s "$MODPATH/kernel/droidspaces_ns.ko" ] || abort '! droidspaces_ns.ko 缺失。'
[ -s "$MODPATH/kernel/droidspaces_net515.ko" ] || abort '! droidspaces_net515.ko 缺失。'
(cd "$MODPATH/kernel" && sha256sum -c SHA256SUMS) || abort '! .ko SHA-256 校验失败。'
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
ui_print '- ZIP 安装完成；设备内核版本与 BTF 将在开机加载前核对。'
ui_print '- 开机加载 PID / IPC namespace 与 MACVLAN / IPv6 NAT 两个模块。'
ui_print '- 加载状态和错误原因见模块目录 status.txt / load.log。'
