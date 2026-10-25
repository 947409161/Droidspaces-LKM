// SPDX-License-Identifier: GPL-2.0-only
/*
 * Entry replacement for device_add / device_del on a BTI + shadow-call-stack
 * kernel.
 *
 * The patched entry keeps its leading `bti c` and then loads a small module
 * stub with `ldr`/`br`. The stub starts with `bti j` and tail-branches to the C
 * wrapper with a direct `b`, so both the entry and the target are valid
 * landing pads under CONFIG_ARM64_BTI_KERNEL.
 *
 * The wrapper calls the per-hook trampoline with a direct `bl`. The trampoline
 * runs a copy of the original prologue and resumes the original body with
 * `ret` to entry + N*4, which is not subject to an indirect-branch landing
 * pad. That is only safe because the copied prologue contains the shadow call
 * stack push: the epilogue reloads x30 from the SCS, so the return address is
 * unaffected by the x30 we clobber to aim the `ret`. Kernels without
 * CONFIG_SHADOW_CALL_STACK are rejected.
 */
#define pr_fmt(fmt) "droidspaces_devtmpfs515: " fmt
#include <linux/module.h>
#include <linux/kallsyms.h>
#include <linux/stop_machine.h>
#include <asm/patching.h>
#include "core.h"
#include "port.h"

#define DS_PATCH_WORDS 6
#define DS_SAVED_WORDS 8
#define DS_TRAMPOLINE_WORDS (DS_SAVED_WORDS + 5)

struct ds_hook {
	const char *name;
	unsigned long replacement;
	unsigned long address;
	u32 saved[DS_SAVED_WORDS];
	u32 patch[DS_PATCH_WORDS];
	u32 *original;
	unsigned int copy_words;
};

static struct ds_hook hooks[] = {
	{ "device_add", (unsigned long)ds_device_add_target, 0, {0}, {0},
	  (u32 *)ds_device_add_original, 0 },
	{ "device_del", (unsigned long)ds_device_del_target, 0, {0}, {0},
	  (u32 *)ds_device_del_original, 0 },
};

/* str x30, [x18, #imm] in any addressing mode: the SCS push we rely on. */
static bool shadow_stack_push(u32 op)
{
	if (op & 0x00400000) /* load, not store */
		return false;
	if (((op >> 24) & 0xff) != 0xf8 && ((op >> 24) & 0xff) != 0xf9)
		return false;
	return (op & 0x1f) == 30 && ((op >> 5) & 0x1f) == 18;
}

static bool movable_prologue(u32 op)
{
	/* BTI landing pads, PACIASP, shadow call stack push. */
	if (op == 0xd503241f || op == 0xd503245f ||
	    op == 0xd503249f || op == 0xd50324df)
		return true;
	if (op == 0xd503233f || shadow_stack_push(op))
		return true;
	/* Stack allocation / frame pointer / stack and callee-saved stores. */
	return (op & 0xffc003ff) == 0xd10003ff ||
	       (op & 0xffc003ff) == 0x910003fd ||
	       (op & 0xff8003e0) == 0xa90003e0 ||
	       (op & 0xff8003e0) == 0xa98003e0 ||
	       (op & 0xffc003e0) == 0xf90003e0;
}

static int prepare_hook(struct ds_hook *hook)
{
	char symbol[KSYM_SYMBOL_LEN];
	char *start, *end;
	unsigned long offset, size;
	unsigned int i, scs = DS_SAVED_WORDS;

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
	for (i = 0; i < DS_SAVED_WORDS; i++) {
		if (shadow_stack_push(hook->saved[i])) {
			scs = i;
			break;
		}
	}
	if (scs == DS_SAVED_WORDS) {
		pr_err("%s: no shadow call stack push in %u prologue words:"
		       " %08x %08x %08x %08x %08x %08x %08x %08x\n", hook->name,
		       DS_SAVED_WORDS, hook->saved[0], hook->saved[1], hook->saved[2],
		       hook->saved[3], hook->saved[4], hook->saved[5], hook->saved[6],
		       hook->saved[7]);
		return -EOPNOTSUPP;
	}
	hook->copy_words = DS_PATCH_WORDS > scs + 1 ? DS_PATCH_WORDS : scs + 1;
	for (i = 0; i < hook->copy_words; i++) {
		if (!movable_prologue(hook->saved[i])) {
			pr_err("%s: unsupported prologue word %u: %08x\n",
			       hook->name, i, hook->saved[i]);
			return -EOPNOTSUPP;
		}
	}
	for (i = 0; i < DS_PATCH_WORDS; i++)
		hook->patch[i] = 0xd503201f; /* nop */
	/* Keep the call-compatible landing pad, then jump to the bti j stub. */
	hook->patch[0] = 0xd503245f; /* bti c */
	hook->patch[1] = 0x58000070; /* ldr x16, .+12 -> patch[4] */
	hook->patch[2] = 0xd61f0200; /* br x16 */
	hook->patch[4] = lower_32_bits(hook->replacement);
	hook->patch[5] = upper_32_bits(hook->replacement);
	return 0;
}

static int write_hook(struct ds_hook *hook, bool restore)
{
	unsigned int i;
	int ret;

	for (i = 0; i < DS_PATCH_WORDS; i++) {
		ret = aarch64_insn_patch_text_nosync((void *)(hook->address + i * 4),
					 restore ? hook->saved[i] : hook->patch[i]);
		if (ret)
			return ret;
	}
	return 0;
}

static int install_stopped(void *unused)
{
	unsigned int i, j;
	int ret;

	for (i = 0; i < ARRAY_SIZE(hooks); i++) {
		struct ds_hook *h = &hooks[i];
		u32 code[DS_TRAMPOLINE_WORDS];
		unsigned int n = h->copy_words;

		memcpy(code, h->saved, n * sizeof(u32));
		code[n + 0] = 0x58000070; /* ldr x16, .+12 -> code[n + 3] */
		code[n + 1] = 0xaa1003fe; /* mov x30, x16 */
		code[n + 2] = 0xd65f03c0; /* ret */
		code[n + 3] = lower_32_bits(h->address + n * 4);
		code[n + 4] = upper_32_bits(h->address + n * 4);
		for (j = 0; j < n + 5; j++) {
			ret = aarch64_insn_patch_text_nosync(&h->original[j], code[j]);
			if (ret)
				return ret; /* No native entry changed yet. */
		}
	}
	for (i = 0; i < ARRAY_SIZE(hooks); i++) {
		ret = write_hook(&hooks[i], false);
		if (ret) {
			for (j = 0; j <= i; j++)
				if (write_hook(&hooks[j], true))
					panic("droidspaces_devtmpfs515: rollback failed");
			return ret;
		}
	}
	return 0;
}

int ds_hooks_prepare(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(hooks); i++) {
		int ret = prepare_hook(&hooks[i]);
		if (ret)
			return ret;
	}
	return 0;
}

int ds_hooks_install(void)
{
	return stop_machine(install_stopped, NULL, cpu_online_mask);
}
