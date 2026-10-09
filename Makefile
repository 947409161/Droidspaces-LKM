ifneq ($(KERNELRELEASE),)
include $(src)/vendor/kallrecon/deps.mk
ifeq ($(TARGET),namespace)
obj-m := droidspaces_ns.o
droidspaces_ns-y := \
	src/port/main.o src/port/pid.o src/port/ipc.o \
	src/port/nsproxy.o src/port/pid_alloc.o src/port/exit.o \
	src/port/proc_ns.o src/port/proc_root.o src/port/hooks.o \
	src/port/selftest.o src/port/msg.o src/port/msgutil.o \
	src/port/sem.o src/port/shm.o src/port/ipc-util.o \
	src/port/ipc-task.o src/port/ipc-compat.o src/port/mqueue.o \
	src/port/mq_sysctl.o src/port/ipc_sysctl.o src/port/fork.o src/port/pidfd.o src/port/reboot.o \
	src/port/fuse.o src/port/cgroup-pidlist.o src/port/bpf-pidns.o \
	src/port/perf.o src/port/perf-original.o src/port/memfd.o \
	$(addprefix vendor/kallrecon/,$(DEPS_LIB_OBJS))
# Do not enable CONFIG_SYSVIPC: that would change the host task_struct layout.
ccflags-y += -DCONFIG_PID_NS=1 -DCONFIG_IPC_NS=1 -DCONFIG_POSIX_MQUEUE=1
ccflags-y += -DCONFIG_POSIX_MQUEUE_SYSCTL=1 -DCONFIG_SYSVIPC_SYSCTL=1
ccflags-y += -include $(src)/src/port/names.h
ccflags-y += -I$(srctree)/fs/proc -I$(srctree)/fs -I$(srctree)
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
