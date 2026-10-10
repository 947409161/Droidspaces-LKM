// SPDX-License-Identifier: GPL-2.0-only
/* Keep Android's host FUSE mounts working without inventing namespace ownership
 * for a native entry whose USER_NS argument was eliminated by the compiler.
 */
#include <linux/fs_context.h>
#include <linux/user_namespace.h>
#include "live.h"

extern int ds_userns_fuse_get_tree_original(struct fs_context *);

int ds_userns_fuse_get_tree(struct fs_context *fc)
{
	/* FUSE contains additional inlined !USER_NS credential conversions.
	 * Restrict new mounts to the original host namespace until those paths
	 * are ported; do not silently give a sandbox mount host ownership.
	 */
	if (fc->user_ns != &init_user_ns)
		return -EOPNOTSUPP;
	return ds_userns_fuse_get_tree_original(fc);
}
