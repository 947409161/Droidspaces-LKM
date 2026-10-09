// SPDX-License-Identifier: GPL-2.0-only
/* Experimental, matching-QEMU-only entry replacements. Never enabled on a phone. */
#define pr_fmt(fmt) "droidspaces_ns: " fmt
#include <linux/module.h>
#include <linux/stop_machine.h>
#include <linux/kallsyms.h>
#include <linux/pid_namespace.h>
#include <linux/proc_ns.h>
#include <linux/fs_context.h>
#include <asm/patching.h>
#include <asm/ptrace.h>
#include "core.h"
#include "port.h"

extern const struct file_operations ds_proc_ns_dir_operations;
extern const struct inode_operations ds_proc_ns_dir_inode_operations;
extern long __arm64_sys_ds_setns(const struct pt_regs *regs);
extern void ds_delayed_put_pid(struct rcu_head *rcu);
extern int ds_proc_init_fs_context(struct fs_context *fc);
extern void ds_proc_kill_sb(struct super_block *sb);

struct ds_hook {
	const char *name;
	unsigned long replacement;
	unsigned long address;
	u32 saved[4];
	u32 patch[4];
};

#define HOOK(name, target) { name, (unsigned long)(target), 0, { 0 }, { 0 } }
static struct ds_hook hooks[] = {
	HOOK("do_exit", ds_do_exit),
	HOOK("put_pid", ds_put_pid),
	HOOK("delayed_put_pid", ds_delayed_put_pid),
	HOOK("alloc_pid", ds_alloc_pid),
	HOOK("free_nsproxy", ds_free_nsproxy),
	HOOK("copy_namespaces", ds_copy_namespaces),
	HOOK("unshare_nsproxy_namespaces", ds_unshare_nsproxy_namespaces),
	HOOK("exec_task_namespaces", ds_exec_task_namespaces),
	HOOK("__arm64_sys_setns", __arm64_sys_ds_setns),
	HOOK("proc_init_fs_context", ds_proc_init_fs_context),
	HOOK("proc_kill_sb", ds_proc_kill_sb),
};

static struct ds_hook proc_hooks[2];

static int prepare_hook(struct ds_hook *hook)
{
	char symbol[KSYM_SYMBOL_LEN];
	char *start, *end;
	unsigned long offset, size;

	hook->address = kallsyms_name_to_addr(hook->name);
	if (!hook->address || (hook->address & 3) ||
	    safe_read(hook->saved, (void *)hook->address, sizeof(hook->saved)))
		return -ENOENT;
	sprint_symbol(symbol, hook->address);
	start = strchr(symbol, '+');
	if (!start)
		return -EINVAL;
	offset = simple_strtoul(start + 1, &end, 0);
	if (end == start + 1 || *end != '/')
		return -EINVAL;
	start = end + 1;
	size = simple_strtoul(start, &end, 0);
	if (end == start || offset || size < sizeof(hook->saved))
		return -EINVAL;
	/* ldr x16, .+8; br x16; .quad destination. CFI type prefixes stay intact. */
	hook->patch[0] = 0x58000050;
	hook->patch[1] = 0xd61f0200;
	hook->patch[2] = lower_32_bits(hook->replacement);
	hook->patch[3] = upper_32_bits(hook->replacement);
	return 0;
}

static int write_hook(struct ds_hook *hook, bool restore)
{
	unsigned int i;
	int ret;

	for (i = 0; i < ARRAY_SIZE(hook->saved); i++) {
		ret = aarch64_insn_patch_text_nosync((void *)(hook->address + i * 4),
					 restore ? hook->saved[i] : hook->patch[i]);
		if (ret)
			return ret;
	}
	return 0;
}

static int install_stopped(void *unused)
{
	unsigned int i;
	int ret;

	for (i = 0; i < ARRAY_SIZE(hooks); i++) {
		ret = write_hook(&hooks[i], false);
		if (ret)
			goto rollback;
	}
	for (i = 0; i < ARRAY_SIZE(proc_hooks); i++) {
		ret = write_hook(&proc_hooks[i], false);
		if (ret)
			goto rollback;
	}
	WRITE_ONCE(init_pid_ns.ns.ops, &pidns_operations);
	return 0;

rollback:
	/* Do not resume CPUs with an incomplete set of lifecycle replacements. */
	for (i = 0; i < ARRAY_SIZE(hooks); i++)
		if (write_hook(&hooks[i], true))
			panic("droidspaces_ns: QEMU hook rollback failed");
	for (i = 0; i < ARRAY_SIZE(proc_hooks); i++)
		if (write_hook(&proc_hooks[i], true))
			panic("droidspaces_ns: QEMU proc hook rollback failed");
	return ret;
}

int ds_vm_hooks_install(void)
{
	unsigned int i;
	int ret;

	if (IS_ENABLED(CONFIG_ARM64_BTI_KERNEL) || init_pid_ns.ns.ops)
		return -EOPNOTSUPP;
	proc_hooks[0] = (struct ds_hook)HOOK("proc_ns_dir_readdir",
					ds_proc_ns_dir_operations.iterate_shared);
	proc_hooks[1] = (struct ds_hook)HOOK("proc_ns_dir_lookup",
					ds_proc_ns_dir_inode_operations.lookup);
	for (i = 0; i < ARRAY_SIZE(hooks); i++) {
		ret = prepare_hook(&hooks[i]);
		if (ret) {
			pr_err("cannot prepare hook %s: %d\n", hooks[i].name, ret);
			return ret;
		}
	}
	for (i = 0; i < ARRAY_SIZE(proc_hooks); i++) {
		ret = prepare_hook(&proc_hooks[i]);
		if (ret)
			return ret;
	}
	/* Objects in procfs can retain operation pointers after all tasks exit. */
	__module_get(THIS_MODULE);
	ret = stop_machine(install_stopped, NULL, NULL);
	if (ret)
		module_put(THIS_MODULE);
	return ret;
}
