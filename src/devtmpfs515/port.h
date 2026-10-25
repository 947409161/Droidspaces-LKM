/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DS_DEVTMPFS515_PORT_H
#define DS_DEVTMPFS515_PORT_H

#include <linux/device.h>
#include <linux/fs.h>
#include <linux/fs_context.h>
#include <linux/kobject.h>

int ds_devtmpfs_start(void);
void ds_devtmpfs_stop(void);
int ds_devtmpfs_create_node(struct device *dev);
int ds_devtmpfs_delete_node(struct device *dev);
int ds_device_add(struct device *dev);
void ds_device_del(struct device *dev);
int ds_hooks_prepare(void);
int ds_hooks_install(void);
int ds_device_add_original(struct device *dev);
void ds_device_del_original(struct device *dev);

/*
 * 5.15 exports neither of these entry points, so they are resolved through
 * kallsyms at load time (the module already uses KallRecon for the device
 * lifecycle hooks).
 */
extern const char *(*ds_device_get_devnode)(const struct device *dev,
					    umode_t *mode, kuid_t *uid,
					    kgid_t *gid, const char **tmp);
extern int (*ds_notify_change)(struct user_namespace *, struct dentry *,
			       struct iattr *, struct inode **);
extern struct dentry *(*ds_kern_path_locked)(const char *name,
					     struct path *path);
extern int (*ds_reconfigure_single)(struct super_block *sb, int flags,
				    void *data);
extern void (*ds_set_fs_root)(struct fs_struct *fs, const struct path *path);
extern void (*ds_set_fs_pwd)(struct fs_struct *fs, const struct path *path);
extern int (*ds_fs_context_init)(struct fs_context *fc);
extern struct kset *ds_devices_kset;

/* Exported by 5.15, but not declared in a header shipping with the DDK. */
extern int unshare_fs_struct(void);

#endif
