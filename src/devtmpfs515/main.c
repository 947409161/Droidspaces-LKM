// SPDX-License-Identifier: GPL-2.0-only
#define pr_fmt(fmt) "droidspaces_devtmpfs515: " fmt
#include <linux/module.h>
#include <linux/of.h>
#include <linux/utsname.h>
#include <linux/slab.h>
#include <linux/kobject.h>
#include "core.h"
#include "hint.h"
#include "port.h"

#define DS_DEVICE_RELEASE "5.15.119-android13-8-g6ff5097ee32a-ab1764665171"

static DEFINE_MUTEX(nodes_lock);
static LIST_HEAD(changing_devices);

struct changing_device {
	struct list_head link;
	struct device *dev;
};

static bool ready;
static unsigned int errors;
module_param(ready, bool, 0400);
module_param(errors, uint, 0400);
MODULE_PARM_DESC(ready, "Existing devices populated and device lifecycle hooks active");
MODULE_PARM_DESC(errors, "Device node update errors, excluding existing or removed nodes");

/* Entry points 5.15 does not export. */
const char *(*ds_device_get_devnode)(const struct device *dev, umode_t *mode,
				     kuid_t *uid, kgid_t *gid, const char **tmp);
int (*ds_notify_change)(struct user_namespace *, struct dentry *,
			struct iattr *, struct inode **);
struct dentry *(*ds_kern_path_locked)(const char *name, struct path *path);
int (*ds_reconfigure_single)(struct super_block *sb, int flags, void *data);
void (*ds_set_fs_root)(struct fs_struct *fs, const struct path *path);
void (*ds_set_fs_pwd)(struct fs_struct *fs, const struct path *path);
int (*ds_fs_context_init)(struct fs_context *fc);
struct kset *ds_devices_kset;

#define DS_RESOLVE(target, symbol)					\
	do {								\
		void *addr = (void *)kallsyms_name_to_addr(#symbol);	\
		if (!addr) {						\
			pr_err("missing kernel symbol: %s\n", #symbol);	\
			return -ENOENT;					\
		}							\
		ds_##target = (typeof(ds_##target))addr;			\
	} while (0)

static int ds_resolve_symbols(void)
{
	DS_RESOLVE(device_get_devnode, device_get_devnode);
	DS_RESOLVE(notify_change, notify_change);
	DS_RESOLVE(kern_path_locked, kern_path_locked);
	DS_RESOLVE(reconfigure_single, reconfigure_single);
	DS_RESOLVE(set_fs_root, set_fs_root);
	DS_RESOLVE(set_fs_pwd, set_fs_pwd);
#ifdef CONFIG_TMPFS
	DS_RESOLVE(fs_context_init, shmem_init_fs_context);
#else
	DS_RESOLVE(fs_context_init, ramfs_init_fs_context);
#endif
	DS_RESOLVE(devices_kset, devices_kset);
	return 0;
}

static void update_node(struct device *dev, bool create)
{
	int ret;
	struct changing_device *changing;

	if (create)
		list_for_each_entry(changing, &changing_devices, link)
			if (changing->dev == dev)
				return;
	if (!MAJOR(dev->devt))
		return;
	ret = create ? ds_devtmpfs_create_node(dev) : ds_devtmpfs_delete_node(dev);
	if (ret && ret != -EEXIST && ret != -ENOENT) {
		errors++;
		pr_err("%s %s: %d\n", create ? "create" : "remove", dev_name(dev), ret);
	}
}

int ds_device_add(struct device *dev)
{
	struct changing_device changing = { .dev = dev };
	int ret;

	/* Snapshot enumeration must not publish a partially registered device. */
	mutex_lock(&nodes_lock);
	list_add(&changing.link, &changing_devices);
	mutex_unlock(&nodes_lock);
	ret = ds_device_add_original(dev);
	mutex_lock(&nodes_lock);
	list_del(&changing.link);
	if (!ret && device_is_registered(dev))
		update_node(dev, true);
	mutex_unlock(&nodes_lock);
	return ret;
}

void ds_device_del(struct device *dev)
{
	struct changing_device changing = { .dev = dev };

	mutex_lock(&nodes_lock);
	list_add(&changing.link, &changing_devices);
	update_node(dev, false);
	mutex_unlock(&nodes_lock);
	/* Driver teardown can recursively unregister children; do not hold our lock. */
	ds_device_del_original(dev);
	mutex_lock(&nodes_lock);
	list_del(&changing.link);
	mutex_unlock(&nodes_lock);
}

struct existing_device {
	struct list_head link;
	struct device *dev;
};

static int populate_existing(void)
{
	LIST_HEAD(snapshot);
	struct existing_device *item, *next;
	struct kobject *obj;
	int ret = 0;

	spin_lock(&ds_devices_kset->list_lock);
	list_for_each_entry(obj, &ds_devices_kset->list, entry) {
		struct device *dev = container_of(obj, struct device, kobj);
		if (!MAJOR(dev->devt))
			continue;
		item = kmalloc(sizeof(*item), GFP_ATOMIC);
		if (!item) { ret = -ENOMEM; break; }
		item->dev = get_device(dev);
		list_add_tail(&item->link, &snapshot);
	}
	spin_unlock(&ds_devices_kset->list_lock);
	list_for_each_entry_safe(item, next, &snapshot, link) {
		mutex_lock(&nodes_lock);
		if (device_is_registered(item->dev))
			update_node(item->dev, true);
		mutex_unlock(&nodes_lock);
		put_device(item->dev);
		list_del(&item->link);
		kfree(item);
	}
	return ret;
}

static int __init ds_init(void)
{
	struct kallrecon_hint hint = { .timeout_ms = 15000 };
	bool device = of_machine_is_compatible("qcom,kalama") &&
		!strcmp(utsname()->release, DS_DEVICE_RELEASE);
	bool vm = of_machine_is_compatible("linux,dummy-virt") &&
		!strncmp(utsname()->release, "5.15.", 5);
	struct file_system_type *existing;
	int ret;

	if (!device && !vm)
		return -EOPNOTSUPP;
	existing = get_fs_type("devtmpfs");
	if (existing) { put_filesystem(existing); return -EEXIST; }
	ret = kallrecon_supply(&hint);
	if (ret) return ret;
	find_kallsyms_base();
	if (kallrecon_fail_reason() != KALLRECON_OK || !klnum_val)
		return -ENODATA;
	ret = ds_resolve_symbols();
	if (ret) return ret;
	ret = ds_hooks_prepare();
	if (ret) return ret;
	ret = ds_devtmpfs_start();
	if (ret) return ret;
	__module_get(THIS_MODULE);
	ret = ds_hooks_install();
	if (ret) {
		module_put(THIS_MODULE);
		ds_devtmpfs_stop();
		return ret;
	}
	/* Hooks are permanent; initialization failures after this point stay visible. */
	ret = populate_existing();
	if (ret) { errors++; pr_err("initial device enumeration failed: %d\n", ret); }
	ready = !ret && !errors;
	pr_info("device lifecycle active, ready=%u errors=%u; pinned until reboot\n",
		ready, errors);
	return 0;
}
module_init(ds_init);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Shikochin");
MODULE_DESCRIPTION("Late-loaded devtmpfs for the recorded Meizu 21 Note 5.15 kernel");
MODULE_IMPORT_NS(ANDROID_GKI_VFS_EXPORT_ONLY);
