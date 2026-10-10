/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DS_USERNS_LIVE_H
#define DS_USERNS_LIVE_H
#include "test.h"
#include <linux/fs.h>
#include <linux/fs_context.h>
void ds_userns_put_cred_rcu(struct rcu_head *rcu);
int ds_userns_proc_prepare(void);
void ds_userns_proc_cleanup(void);
struct dentry *ds_userns_tgid_lookup(struct inode *, struct dentry *, unsigned int);
struct dentry *ds_userns_tid_lookup(struct inode *, struct dentry *, unsigned int);
int ds_userns_tgid_readdir(struct file *, struct dir_context *);
int ds_userns_tid_readdir(struct file *, struct dir_context *);
struct mnt_namespace;
struct user_namespace;
struct mnt_namespace *ds_userns_alloc_mnt_ns(struct user_namespace *, bool);
void ds_userns_mnt_ns_release(struct mnt_namespace *);
void ds_userns_free_mnt_ns(struct mnt_namespace *);
struct fs_context *ds_userns_alloc_fs_context(struct file_system_type *,
    struct dentry *, unsigned int, unsigned int, enum fs_context_purpose);
struct super_block *ds_userns_alloc_super(struct file_system_type *, int,
    struct user_namespace *);
void ds_userns_destroy_super_work(struct work_struct *);
struct stat;
struct statx;
int ds_userns_cp_statx(const struct kstat *, struct statx __user *);
#endif
