/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Trampolines are populated before the hooks become reachable; only the copied,
 * position-independent prologue plus a return sequence is executed there.
 *
 * The target stubs are entered with `br` from the patched entry, so they start
 * with a jump landing pad and continue with a direct branch: the C wrappers do
 * not have to be BTI-compatible themselves.
 */
.text
.balign 16
.global ds_device_add_original
.type ds_device_add_original, %function
ds_device_add_original:
.rept 20
brk #0
.endr
.size ds_device_add_original, .-ds_device_add_original
.balign 16
.global ds_device_del_original
.type ds_device_del_original, %function
ds_device_del_original:
.rept 20
brk #0
.endr
.size ds_device_del_original, .-ds_device_del_original

.balign 16
.global ds_device_add_target
.type ds_device_add_target, %function
ds_device_add_target:
.inst 0xd503249f	/* bti j */
b ds_device_add
.size ds_device_add_target, .-ds_device_add_target

.balign 16
.global ds_device_del_target
.type ds_device_del_target, %function
ds_device_del_target:
.inst 0xd503249f	/* bti j */
b ds_device_del
.size ds_device_del_target, .-ds_device_del_target
