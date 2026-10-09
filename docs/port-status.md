# PID / IPC namespace 移植状态

## 验证环境

2026-10-10，在固定 DDK 的 `6.12.76-4k-gae4e2f4f997e-dirty` 内核上运行
QEMU virt、ARM64、2 vCPU、2 GiB RAM。原内核未启用 PID_NS、IPC_NS、SYSVIPC、
POSIX_MQUEUE；保留 CFI。测试从该内核的 vmlinux 提取 Image，不重编内核。

测试先重复三次不安装钩子的模块核心自测与卸载，再以 `activate=1` 安装实验入口
替换。用户态运行八轮 unshare + fork，以及一轮直接 clone；每轮均有嵌套 namespace、
procfs 挂载和孤儿进程回收。IPC 测试检查 namespace 身份和 setns，权限检查以
setuid 后的非 root 进程执行。

一次测试在功能检查通过后立即读取计数，仍有 13 个 PID namespace 存活。
加入缓存回收并等待延迟释放后，PID / IPC 均归零。最终测试保留有上限的等待，
不把用户进程退出立即等同于所有内核对象已销毁。

最终测试退出码为 0，日志包含以下结果，没有 BUG / WARNING / Oops / panic：

```text
DS_IPC_BACKENDS_ABSENT: msgget/semget/shmget still return ENOSYS
DS_NAMESPACES_PASS: PID 1, nested PID, procfs, orphan reaping, IPC identity, setns, clone, permissions
DS_VM: remaining pid=0 ipc=0
rmmod: can't unload module 'droidspaces_ns': Resource temporarily unavailable
DS_VM_RESULT=0
```

本次 namespace 模块为 ARM64 ELF，1,809,056 字节，SHA-256：
`9187c849b83b2c18a05832b9e84cb2af776dca1ce441b320a08a8639e3e3f95e`。
测试加载日志仍有空版本表、未签名模块和 BTF 重复候选提示，不属于完整 ABI 验证。

## 接入点

| 宿主入口 | 模块提供的行为 |
| --- | --- |
| alloc_pid、put_pid、delayed_put_pid | 多层 PID 分配及 namespace 引用 |
| do_exit | namespace init 退出时的 zap、孤儿回收 |
| copy_namespaces、unshare_nsproxy_namespaces、free_nsproxy、exec_task_namespaces | namespace 复制、创建、共享、释放 |
| ARM64 setns 系统调用入口 | 类型校验、权限检查和 namespace 切换 |
| proc namespace lookup / readdir | 展示 pid、pid_for_children、ipc |
| proc_init_fs_context、proc_kill_sb | procfs 对 PID namespace 的引用与释放 |

替换前校验目标地址对齐、符号边界和入口长度，在 stop_machine 内写入四条 ARM64
指令宽度的跳转。失败时恢复原入口；无法恢复则在实验 VM 中 panic，避免恢复执行
不完整的生命周期替换。激活后模块永久 pin，不支持热卸载。

这不是生产级 livepatch 协议。测试中只有可控的少量进程，没有验证宿主各入口已有
调用栈、跨版本编译器优化、厂商补丁和所有并发路径的过渡一致性。

## 真机启用前的具体缺口

1. **SysV IPC 后端未移植。** msgget、semget、shmget 仍为 ENOSYS；POSIX mqueue
   也未实现。不能把 `/proc/self/ns/ipc` 出现当作 IPC 子系统完成。开启 SYSVIPC
   会牵涉宿主 task_struct 中当前不存在的 SysV 状态及 fork / exit 钩子；不能只对
   模块全局加编译宏再按改变后的布局访问宿主任务。
2. **PID 引用路径不完整。** 尚未逐一适配 perf、BPF task iterator、FUSE、cgroup
   pidlist、pidfd namespace ioctl 等调用点。CONFIG_PID_NS=n 的 get/put 内联空
   操作不会因为模块导出函数而自动恢复。当前测试没有覆盖这些设施。
3. **容器 reboot 未接入宿主系统调用。** 虽然移植了 reboot_pid_ns 实现，宿主
   reboot 路径仍是原先编译后的路径，不能让常规容器 init 使用它。PID namespace
   sysctl 注册、memfd namespace 策略等也未完成。
4. **设备 ABI 未覆盖。** 已对比设备 BTF 的 pid、pid_namespace、nsproxy、
   user_namespace、ucounts 和部分 task_struct 布局；这不覆盖 exit / proc / IPC
   所有依赖。设备 task_struct 的部分 vendor 保留位置已有实际用途，不可当空白槽。
5. **加载器与版本校验。** QEMU 的辅助加载器模拟 kallsyms 重定位；实验模块尚未
   在手机通过 ksud 加载。DDK 的空版本表和 BTF 提示仍需解决，不能用 vermagic
   重试掩盖这些差异。
6. **Droidspaces 整体验证未完成。** 没有启动真实容器或跑 systemd / SysV IPC
   工作负载；设备还缺少其他配置，两个 namespace 出现并不等于全部需求满足。

所以当前激活代码明确拒绝手机，只对匹配的 QEMU 开放。接下来的技术重点是 IPC
后端与额外任务状态的实现、剩余 PID 生命周期调用点、真机 ABI 核对和过渡一致性，
而不是移除激活条件。
