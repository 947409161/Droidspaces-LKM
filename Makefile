ifneq ($(KERNELRELEASE),)
include $(src)/vendor/kallrecon/deps.mk
ifeq ($(TARGET),namespace)
PORT_DIR ?= src/port
obj-m := droidspaces_ns.o
droidspaces_ns-y := \
	$(PORT_DIR)/main.o $(PORT_DIR)/pid.o $(PORT_DIR)/ipc.o \
	$(PORT_DIR)/nsproxy.o $(PORT_DIR)/pid_alloc.o $(PORT_DIR)/exit.o \
	$(PORT_DIR)/proc_ns.o $(PORT_DIR)/proc_root.o $(PORT_DIR)/hooks.o \
	$(PORT_DIR)/selftest.o $(PORT_DIR)/msg.o $(PORT_DIR)/msgutil.o \
	$(PORT_DIR)/sem.o $(PORT_DIR)/shm.o $(PORT_DIR)/ipc-util.o \
	$(PORT_DIR)/ipc-task.o $(PORT_DIR)/ipc-compat.o $(if $(wildcard $(src)/$(PORT_DIR)/mqueue.c),$(PORT_DIR)/mqueue.o) \
	$(if $(wildcard $(src)/$(PORT_DIR)/mq_sysctl.c),$(PORT_DIR)/mq_sysctl.o) $(PORT_DIR)/ipc_sysctl.o $(PORT_DIR)/fork.o $(if $(wildcard $(src)/$(PORT_DIR)/pidfd.c),$(PORT_DIR)/pidfd.o) $(PORT_DIR)/reboot.o \
	$(PORT_DIR)/fuse.o $(PORT_DIR)/cgroup-pidlist.o $(PORT_DIR)/bpf-pidns.o \
	$(PORT_DIR)/perf.o $(PORT_DIR)/perf-original.o $(PORT_DIR)/memfd.o \
	$(addprefix vendor/kallrecon/,$(DEPS_LIB_OBJS))
ifneq ($(GKI_ANDROID),)
ccflags-y += -DDS_GKI_ANDROID='"$(GKI_ANDROID)"' -DDS_GKI_VERSION='"$(GKI_VERSION)"'
endif
ifeq ($(MEIZU21NOTE),1)
ccflags-y += -DDS_MEIZU21NOTE_515119=1
endif
# Do not enable CONFIG_SYSVIPC: that would change the host task_struct layout.
ccflags-y += -DCONFIG_PID_NS=1 -DCONFIG_IPC_NS=1 -DCONFIG_POSIX_MQUEUE=1
ccflags-y += -DCONFIG_POSIX_MQUEUE_SYSCTL=1 -DCONFIG_SYSVIPC_SYSCTL=1
ccflags-y += -include $(src)/$(PORT_DIR)/names.h
ifeq ($(USERNS),1)
droidspaces_ns-y += src/userns/user_namespace.o src/userns/credentials.o src/userns/utsname.o \
	src/userns/live-credentials.o src/userns/live-ucounts.o src/userns/live-proc.o src/userns/live-syscalls.o src/userns/live-mount.o src/userns/live-fs-context.o src/userns/live-super.o \
	src/userns/live-identity.o src/userns/live-groups.o src/userns/live-stat.o src/userns/live-capabilities.o \
	src/userns/live-fuse.o src/userns/live-fuse-request.o src/userns/live-fuse-inode.o src/userns/live-fuse-dir.o src/userns/live-fuse-acl.o src/userns/fuse-original.o src/userns/live-netlink.o src/userns/live-sock.o src/userns/sock-original.o src/userns/live-scm.o src/userns/live-unix.o src/userns/live-cgroup.o src/userns/live-time.o src/userns/live-sysfs.o src/userns/live-proc-status.o src/userns/live-nsfs.o src/userns/nsfs-original.o src/userns/live-vfs.o src/userns/live-exec.o src/userns/live-mm.o src/userns/mm-original.o
ccflags-y += -DCONFIG_USER_NS=1 -DDS_USERNS_LIVE=1
ccflags-y += -include $(src)/src/userns/live-names.h
LINUXINCLUDE := -I$(src)/src/userns/compat $(LINUXINCLUDE)
endif
ccflags-y += -I$(srctree)/fs/proc -I$(srctree)/fs -I$(srctree)
else ifeq ($(TARGET),compat)
obj-m := droidspaces_compat.o
droidspaces_compat-y := src/compat/main.o
else ifeq ($(TARGET),netfilter)
obj-m := droidspaces_netfilter.o
droidspaces_netfilter-y := src/netfilter/main.o src/netfilter/nat-inet.o
include $(src)/src/netfilter/objects.mk
# NF_TABLES itself changes struct net; keep the native definition intact.
ccflags-y += -DCONFIG_NF_TABLES_IPV4=1 -DCONFIG_NF_TABLES_IPV6=1 -DCONFIG_NF_TABLES_INET=1
LINUXINCLUDE := -I$(src)/src/netfilter/compat $(LINUXINCLUDE)
else ifeq ($(TARGET),net515)
obj-m := droidspaces_net515.o
droidspaces_net515-y := src/net515/main.o src/net515/upstream/macvlan.o \
	src/net515/upstream/ip6table_nat.o src/net515/upstream/xt_addrtype.o
# if_macvlan.h turns the accessors into BUG() stubs without this; the addrtype
# unit compiles its IPv6 match only when the kernel-side tables are enabled.
ccflags-y += -DCONFIG_MACVLAN=1 -DCONFIG_IP6_NF_IPTABLES=1
else ifeq ($(TARGET),ipset515)
IP515 := src/ipset515/upstream
obj-m := droidspaces_ip_set.o \
	droidspaces_ip_set_bitmap_ip.o \
	droidspaces_ip_set_bitmap_ipmac.o \
	droidspaces_ip_set_bitmap_port.o \
	droidspaces_ip_set_hash_ip.o \
	droidspaces_ip_set_hash_ipmac.o \
	droidspaces_ip_set_hash_ipmark.o \
	droidspaces_ip_set_hash_ipport.o \
	droidspaces_ip_set_hash_ipportip.o \
	droidspaces_ip_set_hash_ipportnet.o \
	droidspaces_ip_set_hash_mac.o \
	droidspaces_ip_set_hash_net.o \
	droidspaces_ip_set_hash_netiface.o \
	droidspaces_ip_set_hash_netnet.o \
	droidspaces_ip_set_hash_netport.o \
	droidspaces_ip_set_hash_netportnet.o \
	droidspaces_ip_set_list_set.o \
	droidspaces_xt_set.o
droidspaces_ip_set-y := $(IP515)/ip_set_core.o $(IP515)/ip_set_getport.o $(IP515)/pfxlen.o
droidspaces_ip_set_bitmap_ip-y := $(IP515)/ip_set_bitmap_ip.o
droidspaces_ip_set_bitmap_ipmac-y := $(IP515)/ip_set_bitmap_ipmac.o
droidspaces_ip_set_bitmap_port-y := $(IP515)/ip_set_bitmap_port.o
droidspaces_ip_set_hash_ip-y := $(IP515)/ip_set_hash_ip.o
droidspaces_ip_set_hash_ipmac-y := $(IP515)/ip_set_hash_ipmac.o
droidspaces_ip_set_hash_ipmark-y := $(IP515)/ip_set_hash_ipmark.o
droidspaces_ip_set_hash_ipport-y := $(IP515)/ip_set_hash_ipport.o
droidspaces_ip_set_hash_ipportip-y := $(IP515)/ip_set_hash_ipportip.o
droidspaces_ip_set_hash_ipportnet-y := $(IP515)/ip_set_hash_ipportnet.o
droidspaces_ip_set_hash_mac-y := $(IP515)/ip_set_hash_mac.o
droidspaces_ip_set_hash_net-y := $(IP515)/ip_set_hash_net.o
droidspaces_ip_set_hash_netiface-y := $(IP515)/ip_set_hash_netiface.o
droidspaces_ip_set_hash_netnet-y := $(IP515)/ip_set_hash_netnet.o
droidspaces_ip_set_hash_netport-y := $(IP515)/ip_set_hash_netport.o
droidspaces_ip_set_hash_netportnet-y := $(IP515)/ip_set_hash_netportnet.o
droidspaces_ip_set_list_set-y := $(IP515)/ip_set_list_set.o
droidspaces_xt_set-y := $(IP515)/xt_set.o
# Matches the device: IPv6 tables are built in, bridge netfilter is not.
# CONFIG_IP_SET_MAX comes from the ipset Kconfig, which the device build omits;
# 256 is the upstream default.
ccflags-y += -DCONFIG_IP6_NF_IPTABLES=1 -DCONFIG_IP_SET_MAX=256
else ifeq ($(TARGET),devtmpfs515)
obj-m := droidspaces_devtmpfs515.o
droidspaces_devtmpfs515-y := src/devtmpfs515/main.o src/devtmpfs515/devtmpfs.o \
	src/devtmpfs515/hooks.o src/devtmpfs515/original.o $(addprefix vendor/kallrecon/,$(DEPS_LIB_OBJS))
else ifeq ($(TARGET),userns)
obj-m := droidspaces_userns_test.o
droidspaces_userns_test-y := src/userns/main.o src/userns/user_namespace.o src/userns/credentials.o src/userns/utsname.o
ccflags-y += -DCONFIG_USER_NS=1 -include $(src)/src/userns/names.h
else ifeq ($(TARGET),devtmpfs)
obj-m := droidspaces_devtmpfs.o
droidspaces_devtmpfs-y := src/devtmpfs/main.o src/devtmpfs/devtmpfs.o src/devtmpfs/hooks.o src/devtmpfs/original.o $(addprefix vendor/kallrecon/,$(DEPS_LIB_OBJS))
ccflags-y += -I$(srctree)
ifeq ($(TEST_DEVTMPFS),1)
obj-m += droidspaces_devtmpfs_fixture.o
droidspaces_devtmpfs_fixture-y := tests/vm/devtmpfs-fixture.o
endif
else
obj-m := droidspaces_probe.o
droidspaces_probe-y := src/probe.o $(addprefix vendor/kallrecon/,$(DEPS_LIB_OBJS))
endif
ccflags-y += -I$(src)/vendor/kallrecon/lib -std=gnu11
ccflags-y += -Wno-declaration-after-statement

$(obj)/%.o: $(src)/%.c $(recordmcount_source) FORCE
	$(call if_changed_rule,cc_o_c)
	$(call cmd,force_checksrc)

$(obj)/%.o: $(src)/%.S FORCE
	$(call if_changed_rule,as_o_S)
else
.DEFAULT_GOAL := all
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
OUT ?= $(ROOT)/out/default
.PHONY: all clean
all:
	@test -n "$(KDIR)" || { echo 'Set KDIR to a prepared kernel/DDK build directory.' >&2; exit 1; }
	@mkdir -p "$(OUT)"
	$(MAKE) -C "$(KDIR)" M="$(abspath $(OUT))" src="$(ROOT)" srcroot="$(ROOT)" modules
clean:
	@test -n "$(KDIR)" || { echo 'Set KDIR before cleaning.' >&2; exit 1; }
	$(MAKE) -C "$(KDIR)" M="$(abspath $(OUT))" src="$(ROOT)" srcroot="$(ROOT)" clean
endif
