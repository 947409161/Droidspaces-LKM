#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# MODDIR is supplied by the entry script (or MODPATH during installation).
DS_RELEASE=6.12.69-android16-6-g242e1a07f878-ab15865446-4k
DS_COMPATIBLE=/sys/firmware/devicetree/base/compatible
DS_MODULE_SYS=/sys/module/droidspaces_ns
DS_PROC_NS=/proc/self/ns
DS_KSUD=/data/adb/ksud
[ -x "$DS_KSUD" ] || DS_KSUD=/data/adb/ksu/bin/ksud
export KSU_MODULE=droidspaces_lkm

# KernelSU clears --temp configuration at every boot, including for disabled modules.
# The file fallback also covers a missing/older ksud, so failures remain visible.
ds_status() {
    ds_message=$1
    printf '%s\n' "$ds_message"
    printf '%s\n' "$ds_message" > "$MODDIR/status.txt"
    if [ -x "$DS_KSUD" ] && "$DS_KSUD" module config set --temp override.description "$ds_message"; then
        return 0
    fi
    DS_DESCRIPTION="$ds_message" awk '
        !/^description=/ { print }
        END { print "description=" ENVIRON["DS_DESCRIPTION"] }
    ' "$MODDIR/module.prop" > "$MODDIR/module.prop.tmp" &&
        cat "$MODDIR/module.prop.tmp" > "$MODDIR/module.prop"
    rm -f "$MODDIR/module.prop.tmp"
}

ds_target_supported() {
    [ "$(uname -m)" = aarch64 ] &&
    [ "$(uname -r)" = "$DS_RELEASE" ] &&
    [ -r "$DS_COMPATIBLE" ] &&
    tr '\000' '\n' < "$DS_COMPATIBLE" | grep -qx 'qcom,canoe'
}

ds_active() {
    [ "$(cat "$DS_MODULE_SYS/parameters/activate" 2>/dev/null)" = Y ] &&
    [ -e "$DS_PROC_NS/pid" ] && [ -e "$DS_PROC_NS/pid_for_children" ] &&
    [ -e "$DS_PROC_NS/ipc" ]
}

ds_payload_valid() {
    [ -s "$MODDIR/kernel/droidspaces_ns.ko" ] &&
    (cd "$MODDIR/kernel" && sha256sum -c SHA256SUMS)
}

ds_load() {
    if ! ds_target_supported; then
        ds_status '[不支持] 设备或内核不匹配，未加载；仅支持 qcom,canoe / 6.12.69-android16-6-g242e1a07f878-ab15865446-4k。'
        return 1
    fi
    if ds_active; then
        ds_status '[已加载] PID / IPC namespace 已激活（本次开机已加载）；卸载或更换 .ko 需重启。'
        return 0
    fi
    if [ -d "$DS_MODULE_SYS" ]; then
        ds_status '[加载失败] droidspaces_ns 已存在但未激活，或 namespace 接口不完整；请重启后重试。'
        return 1
    fi
    if [ ! -x "$DS_KSUD" ]; then
        ds_status '[加载失败] 找不到可执行的 ksud；请检查 KernelSU，日志见模块目录 load.log。'
        return 1
    fi
    if ! ds_payload_valid; then
        ds_status '[加载失败] .ko 缺失或 SHA-256 校验失败；请重新安装完整模块 ZIP。'
        return 1
    fi
    ds_status '[加载中] 正在通过 ksud insmod 激活 PID / IPC namespace。'
    "$DS_KSUD" insmod "$MODDIR/kernel/droidspaces_ns.ko" activate=1
    ds_result=$?
    if [ "$ds_result" -ne 0 ]; then
        ds_status "[加载失败] ksud insmod 返回 ${ds_result}；详见模块目录 load.log。"
        return 1
    fi
    if ! ds_active; then
        ds_status '[加载失败] insmod 已返回成功，但 activate 或 PID / IPC namespace 检查未通过；详见 load.log。'
        return 1
    fi
    ds_status '[已加载] PID / IPC namespace 已激活；卸载或更换 .ko 需重启。'
}
