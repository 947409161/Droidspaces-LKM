#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
MODDIR=${0%/*}
. "$MODDIR/common.sh"
[ ! -f "$MODDIR/load.log" ] || mv -f "$MODDIR/load.log" "$MODDIR/load.log.previous"
exec >> "$MODDIR/load.log" 2>&1
printf 'Droidspaces LKM Meizu 21 Note: %s\n' "$(date -u)"
printf 'Kernel: %s\n' "$(uname -r)"
ds_load
