/* SPDX-License-Identifier: GPL-2.0-only */
/* Only a checked, position-independent native prologue is copied here. */
.text
.balign 16
.global ds_userns_fuse_get_tree_original
.type ds_userns_fuse_get_tree_original, %function
ds_userns_fuse_get_tree_original:
.rept 8
brk #0
.endr
.size ds_userns_fuse_get_tree_original, .-ds_userns_fuse_get_tree_original
