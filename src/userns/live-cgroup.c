// SPDX-License-Identifier: GPL-2.0
#include "kernel/cgroup/cgroup-internal.h"

#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/nsproxy.h>
#include <linux/proc_ns.h>


/* cgroup namespaces */

static struct ucounts *inc_cgroup_namespaces(struct user_namespace *ns)
{
	return inc_ucount(ns, current_euid(), UCOUNT_CGROUP_NAMESPACES);
}

static void dec_cgroup_namespaces(struct ucounts *ucounts)
{
	dec_ucount(ucounts, UCOUNT_CGROUP_NAMESPACES);
}

static struct cgroup_namespace *alloc_cgroup_ns(void)
{
	struct cgroup_namespace *new_ns;
	int ret;

	new_ns = kzalloc(sizeof(struct cgroup_namespace), GFP_KERNEL_ACCOUNT);
	if (!new_ns)
		return ERR_PTR(-ENOMEM);
	ret = ns_alloc_inum(&new_ns->ns);
	if (ret) {
		kfree(new_ns);
		return ERR_PTR(ret);
	}
	refcount_set(&new_ns->ns.count, 1);
	new_ns->ns.ops = &cgroupns_operations;
	return new_ns;
}

void ds_userns_free_cgroup_ns(struct cgroup_namespace *ns)
{
	put_css_set(ns->root_cset);
	dec_cgroup_namespaces(ns->ucounts);
	put_user_ns(ns->user_ns);
	ns_free_inum(&ns->ns);
	kfree(ns);
}


struct cgroup_namespace *ds_userns_copy_cgroup_ns(unsigned long flags,
					struct user_namespace *user_ns,
					struct cgroup_namespace *old_ns)
{
	struct cgroup_namespace *new_ns;
	struct ucounts *ucounts;
	struct css_set *cset;

	BUG_ON(!old_ns);

	if (!(flags & CLONE_NEWCGROUP)) {
		get_cgroup_ns(old_ns);
		return old_ns;
	}

	/* Allow only sysadmin to create cgroup namespace. */
	if (!ns_capable(user_ns, CAP_SYS_ADMIN))
		return ERR_PTR(-EPERM);

	ucounts = inc_cgroup_namespaces(user_ns);
	if (!ucounts)
		return ERR_PTR(-ENOSPC);

	/* It is not safe to take cgroup_mutex here */
	spin_lock_irq(&css_set_lock);
	cset = task_css_set(current);
	get_css_set(cset);
	spin_unlock_irq(&css_set_lock);

	new_ns = alloc_cgroup_ns();
	if (IS_ERR(new_ns)) {
		put_css_set(cset);
		dec_cgroup_namespaces(ucounts);
		return new_ns;
	}

	new_ns->user_ns = get_user_ns(user_ns);
	new_ns->ucounts = ucounts;
	new_ns->root_cset = cset;

	return new_ns;
}
