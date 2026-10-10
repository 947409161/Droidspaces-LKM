#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
[ "$KSU" = true ] || abort '! 请在 KernelSU 管理器中安装。'
MODDIR=$MODPATH
. "$MODDIR/common.sh"
ds_target_supported || abort "! $DS_REASON"
[ -x "$DS_KSUD" ] || abort '! 未找到 ksud。'
"$DS_KSUD" insmod --help >/dev/null 2>&1 || abort '! 此 ksud 不支持 insmod。'
ds_payload_valid || abort '! .ko 缺失或 SHA-256 校验失败。'
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
ui_print '- 已匹配 Meizu 21 Note / 5.15.119 内核。'
ui_print '- 开机加载前核对完整内核版本与 BTF SHA-256。'
ui_print '- 首次加载失败时查看模块目录 load.log。'
