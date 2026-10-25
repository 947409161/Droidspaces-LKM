// SPDX-License-Identifier: GPL-2.0-only
/*
 * MACVLAN, IPv6 NAT and xt_addrtype support for the recorded Android 13 / 5.15
 * kernel.
 *
 * The target vendor kernel builds none of drivers/net/macvlan.c,
 * net/ipv6/netfilter/ip6table_nat.c or net/netfilter/xt_addrtype.c. All three
 * are ordinary mainline modules there; this unit supplies them without touching
 * the native firewall or bridge code.
 * Registration is rolled back in reverse order, and the state of each unit is
 * reported through read-only module parameters for the boot loader.
 *
 * No new links or firewall rules are created here. MACVLAN links appear only
 * when userspace asks for them, and the IPv6 "nat" table is registered as an
 * empty x_tables template, exactly like the native module.
 */
#define pr_fmt(fmt) "droidspaces_net515: " fmt

#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/utsname.h>

#define DS_NET515_DEVICE_RELEASE "5.15.119-android13-8-g6ff5097ee32a-ab1764665171"

extern int ds_nf_init_net515_macvlan(void);
extern void ds_nf_exit_net515_macvlan(void);
extern int ds_nf_init_net515_ip6table_nat(void);
extern void ds_nf_exit_net515_ip6table_nat(void);
extern int ds_nf_init_net515_xt_addrtype(void);
extern void ds_nf_exit_net515_xt_addrtype(void);

static bool macvlan_registered;
static bool ip6table_nat_registered;
static bool xt_addrtype_registered;

module_param(macvlan_registered, bool, 0444);
MODULE_PARM_DESC(macvlan_registered, "MACVLAN link kind registered");
module_param(ip6table_nat_registered, bool, 0444);
MODULE_PARM_DESC(ip6table_nat_registered, "IPv6 xtables nat table registered");
module_param(xt_addrtype_registered, bool, 0444);
MODULE_PARM_DESC(xt_addrtype_registered, "xt_addrtype match registered");

struct ds_net515_unit {
	const char *name;
	int (*init)(void);
	void (*exit)(void);
	bool *registered;
};

static struct ds_net515_unit units[] = {
	{
		.name = "macvlan",
		.init = ds_nf_init_net515_macvlan,
		.exit = ds_nf_exit_net515_macvlan,
		.registered = &macvlan_registered,
	},
	{
		.name = "ip6table_nat",
		.init = ds_nf_init_net515_ip6table_nat,
		.exit = ds_nf_exit_net515_ip6table_nat,
		.registered = &ip6table_nat_registered,
	},
	{
		.name = "xt_addrtype",
		.init = ds_nf_init_net515_xt_addrtype,
		.exit = ds_nf_exit_net515_xt_addrtype,
		.registered = &xt_addrtype_registered,
	},
};

static bool ds_net515_target_supported(void)
{
	const char *release = utsname()->release;

	if (of_machine_is_compatible("qcom,kalama"))
		return !strcmp(release, DS_NET515_DEVICE_RELEASE);
	/* The pinned DDK regression kernels boot as linux,dummy-virt. */
	if (of_machine_is_compatible("linux,dummy-virt"))
		return !strncmp(release, "5.15.", 5);
	return false;
}

static int __init ds_net515_init(void)
{
	int i, ret;

	if (!ds_net515_target_supported()) {
		pr_err("requires Meizu 21 Note %s or a 5.15.x QEMU; got %s\n",
		       DS_NET515_DEVICE_RELEASE, utsname()->release);
		return -EOPNOTSUPP;
	}

	for (i = 0; i < ARRAY_SIZE(units); i++) {
		ret = units[i].init();
		if (ret) {
			pr_err("%s registration failed: %d\n", units[i].name, ret);
			while (i--) {
				units[i].exit();
				*units[i].registered = false;
			}
			return ret;
		}
		*units[i].registered = true;
		pr_info("%s registered\n", units[i].name);
	}

	pr_info("MACVLAN, IPv6 NAT and xt_addrtype registered; no rules installed\n");
	return 0;
}

static void __exit ds_net515_exit(void)
{
	int i = ARRAY_SIZE(units);

	while (i--) {
		units[i].exit();
		*units[i].registered = false;
	}
}

module_init(ds_net515_init);
module_exit(ds_net515_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Shikochin");
MODULE_DESCRIPTION("Droidspaces MACVLAN and IPv6 NAT for the recorded 5.15 kernel");
