#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
DS_RELEASE='5.15.119-android13-8-g6ff5097ee32a-ab1764665171'
DS_BTF_SHA256='ceb62a44dbeb782434c5956c71c03b635129017399cedbf2a1e6cc072998081c'
DS_MODULE_SYS=/sys/module/droidspaces_ns
DS_NET515_SYS=/sys/module/droidspaces_net515
DS_KERNEL_BTF=${DS_KERNEL_BTF:-/sys/kernel/btf/vmlinux}
DS_PROC_NS=${DS_PROC_NS:-/proc/self/ns}
DS_MODULE_ROOT=${DS_MODULE_ROOT:-/sys/module}
DS_IPSET_MODULES='droidspaces_ip_set droidspaces_ip_set_bitmap_ip droidspaces_ip_set_bitmap_ipmac droidspaces_ip_set_bitmap_port droidspaces_ip_set_hash_ip droidspaces_ip_set_hash_ipmac droidspaces_ip_set_hash_ipmark droidspaces_ip_set_hash_ipport droidspaces_ip_set_hash_ipportip droidspaces_ip_set_hash_ipportnet droidspaces_ip_set_hash_mac droidspaces_ip_set_hash_net droidspaces_ip_set_hash_netiface droidspaces_ip_set_hash_netnet droidspaces_ip_set_hash_netport droidspaces_ip_set_hash_netportnet droidspaces_ip_set_list_set droidspaces_xt_set'
DS_KSUD=/data/adb/ksud
[ -x "$DS_KSUD" ] || DS_KSUD=/data/adb/ksu/bin/ksud
export KSU_MODULE=droidspaces_lkm_meizu21note

ds_status() {
    ds_message=$1
    printf '%s\n' "$ds_message"
    printf '%s\n' "$ds_message" > "$MODDIR/status.txt"
    if [ -x "$DS_KSUD" ] && "$DS_KSUD" module config set --temp override.description "$ds_message"; then
        return 0
    fi
    DS_DESCRIPTION=$ds_message awk '
        !/^description=/ { print }
        END { print "description=" ENVIRON["DS_DESCRIPTION"] }
    ' "$MODDIR/module.prop" > "$MODDIR/module.prop.tmp" &&
        cat "$MODDIR/module.prop.tmp" > "$MODDIR/module.prop"
    rm -f "$MODDIR/module.prop.tmp"
}

ds_target_supported() {
    DS_REASON='只支持指定的 ARM64 设备内核。'
    [ "$(uname -m)" = aarch64 ] || return 1
    DS_REASON="内核版本不匹配：$(uname -r)"
    [ "$(uname -r)" = "$DS_RELEASE" ] || return 1
    DS_REASON='无法读取内核 BTF。'
    [ -r "$DS_KERNEL_BTF" ] || return 1
    ds_btf=$(sha256sum "$DS_KERNEL_BTF") || return 1
    DS_REASON='内核 BTF 与构建目标不匹配。'
    [ "${ds_btf%% *}" = "$DS_BTF_SHA256" ] || return 1
    DS_REASON=''
    return 0
}

ds_payload_valid() {
    [ -s "$MODDIR/kernel/droidspaces_ns.ko" ] || return 1
    [ -s "$MODDIR/kernel/droidspaces_net515.ko" ] || return 1
    for ds_m in $DS_IPSET_MODULES; do
        [ -s "$MODDIR/kernel/$ds_m.ko" ] || return 1
    done
    (cd "$MODDIR/kernel" && sha256sum -c SHA256SUMS)
}

ds_active() {
    [ "$(cat "$DS_MODULE_SYS/parameters/activate" 2>/dev/null)" = Y ] &&
    [ -e "$DS_PROC_NS/pid" ] && [ -e "$DS_PROC_NS/pid_for_children" ] &&
    [ -e "$DS_PROC_NS/ipc" ]
}

ds_net515_active() {
    [ "$(cat "$DS_NET515_SYS/parameters/macvlan_registered" 2>/dev/null)" = Y ] &&
    [ "$(cat "$DS_NET515_SYS/parameters/ip6table_nat_registered" 2>/dev/null)" = Y ] &&
    [ "$(cat "$DS_NET515_SYS/parameters/xt_addrtype_registered" 2>/dev/null)" = Y ]
}

ds_net515_load() {
    DS_EXTRA_STATE=''
    if ds_net515_active; then
        printf 'MACVLAN / IPv6 NAT / addrtype: already active\n'
        return 0
    fi
    if [ -d "$DS_NET515_SYS" ]; then
        DS_EXTRA_STATE='MACVLAN / IPv6 NAT / addrtype 已有未激活模块，请重启后重试。'
        return 1
    fi
    if [ ! -x "$DS_KSUD" ]; then
        DS_EXTRA_STATE='找不到可执行的 ksud。'
        return 1
    fi
    printf 'Loading droidspaces_net515.ko\n'
    "$DS_KSUD" insmod "$MODDIR/kernel/droidspaces_net515.ko"
    ds_result=$?
    if [ "$ds_result" -ne 0 ]; then
        DS_EXTRA_STATE="MACVLAN / IPv6 NAT / addrtype 加载返回 $ds_result。"
        return 1
    fi
    if ! ds_net515_active; then
        DS_EXTRA_STATE='MACVLAN / IPv6 NAT / addrtype 加载后未注册，详见 load.log。'
        return 1
    fi
    printf 'MACVLAN / IPv6 NAT / addrtype: activated\n'
    return 0
}

ds_ipset_active() {
    for ds_m in $DS_IPSET_MODULES; do
        [ -d "$DS_MODULE_ROOT/$ds_m" ] || return 1
    done
    return 0
}

ds_ipset_load() {
    DS_IPSET_STATE=''
    if ds_ipset_active; then
        printf 'ipset: already active\n'
        return 0
    fi
    if [ ! -x "$DS_KSUD" ]; then
        DS_IPSET_STATE='找不到可执行的 ksud。'
        return 1
    fi
    for ds_m in $DS_IPSET_MODULES; do
        [ -d "$DS_MODULE_ROOT/$ds_m" ] && continue
        printf 'Loading %s.ko\n' "$ds_m"
        "$DS_KSUD" insmod "$MODDIR/kernel/$ds_m.ko"
        ds_result=$?
        if [ "$ds_result" -ne 0 ]; then
            DS_IPSET_STATE="ipset 模块 $ds_m 加载返回 $ds_result。"
            return 1
        fi
    done
    if ! ds_ipset_active; then
        DS_IPSET_STATE='ipset 模块加载后未就绪，详见 load.log。'
        return 1
    fi
    printf 'ipset: activated\n'
    return 0
}

ds_load() {
    ds_ns_new=''
    if ! ds_target_supported; then
        ds_status "[不兼容] $DS_REASON；未加载。"
        return 1
    fi
    if ds_active; then
        printf 'PID / IPC namespace: already active\n'
    else
        if [ -d "$DS_MODULE_SYS" ]; then
            ds_status '[加载失败] 已有未激活的 droidspaces_ns；请重启后重试。'
            return 1
        fi
        if [ ! -x "$DS_KSUD" ]; then
            ds_status '[加载失败] 找不到可执行的 ksud。'
            return 1
        fi
        if ! ds_payload_valid; then
            ds_status '[加载失败] .ko 缺失或 SHA-256 校验失败。'
            return 1
        fi
        ds_status '[加载中] 正在激活 PID / IPC namespace。'
        "$DS_KSUD" insmod "$MODDIR/kernel/droidspaces_ns.ko" gki=1 activate=1
        ds_result=$?
        if [ "$ds_result" -ne 0 ]; then
            ds_status "[加载失败] ksud insmod 返回 $ds_result；详见 load.log。"
            return 1
        fi
        if ! ds_active; then
            ds_status '[加载失败] insmod 成功，但 namespace 接口未激活；详见 load.log。'
            return 1
        fi
        ds_ns_new=1
    fi
    if ds_net515_load; then ds_net_ok=1; else ds_net_ok=0; fi
    if ds_ipset_load; then ds_ipset_ok=1; else ds_ipset_ok=0; fi
    if [ "$ds_net_ok" = 1 ] && [ "$ds_ipset_ok" = 1 ]; then
        if [ -n "$ds_ns_new" ]; then
            ds_status '[已加载] PID / IPC namespace 与网络扩展（MACVLAN / IPv6 NAT / addrtype / ipset）已激活。'
        else
            ds_status '[已加载] PID / IPC namespace 与网络扩展（MACVLAN / IPv6 NAT / addrtype / ipset）已激活；更换模块需重启。'
        fi
        return 0
    fi
    ds_reason=''
    [ "$ds_net_ok" = 1 ] || ds_reason="$DS_EXTRA_STATE"
    if [ "$ds_ipset_ok" = 0 ]; then
        ds_reason="${ds_reason:+$ds_reason }$DS_IPSET_STATE"
    fi
    if [ -n "$ds_ns_new" ]; then
        ds_status "[部分加载] PID / IPC namespace 已激活；$ds_reason"
    else
        ds_status "[部分加载] PID / IPC namespace 可用；$ds_reason"
    fi
    return 1
}
