#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
[ "$KSU" = true ] || abort '! 请在 KernelSU 管理器中安装。'
MODDIR=$MODPATH
. "$MODDIR/common.sh"
ds_target_supported || abort '! 设备/内核不匹配：仅支持 qcom,canoe / 6.12.69-android16-6-g242e1a07f878-ab15865446-4k。'
[ -x "$DS_KSUD" ] || abort '! 未找到 ksud。'
"$DS_KSUD" insmod --help >/dev/null 2>&1 || abort '! 此 ksud 不支持 insmod。'
ds_payload_valid || abort '! .ko 缺失或 SHA-256 校验失败。'
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/post-fs-data.sh" 0 0 0755
ui_print '- 作者：Shikochin'
ui_print '- 下次开机自动加载；管理器简介会显示本次加载状态。'
ui_print '- 当前已激活的 .ko 需重启才会移除；禁用/卸载 ZIP 后请重启。'
