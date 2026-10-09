# Droidspaces LKM experiment

目标：不刷写手机内核，通过 `ksud insmod` 动态补充 Droidspaces 所需能力。

目前已经做出 **PID / IPC namespace 的实验性移植模块**，在关闭这两个配置的
ARM64 Android 6.12 QEMU 内核中验证了创建、切换和回收。它还不是可以给手机开启
Droidspaces 的成品：IPC 仅有 namespace 身份和生命周期，尚无 SysV IPC / POSIX
mqueue 后端，其他内核调用路径与真机 ABI 也没有完成适配。

| 产物 | 已验证范围 |
| --- | --- |
| `out/android16-6.12/droidspaces_probe.ko` | 真机通过 `ksud insmod` 加载、KallRecon 解析、卸载；只探测 |
| `out/android16-6.12-ns/droidspaces_ns.ko` | 匹配 DDK 的 QEMU 中实际运行 PID / IPC namespace 测试；未在手机加载 |

`droidspaces_ns` 默认只执行核心对象自测，不安装钩子。`activate=1` 只接受指定
release 的 QEMU `linux,dummy-virt`，其他设备会被拒绝。激活后模块永久持有引用，
直到重启，不能 `rmmod`。没有安装开机加载服务，也没有修改相邻 Droidspaces-OSS。

## 实现范围

`src/port/` 移植 Android common 内核的 PID namespace、IPC namespace、nsproxy、
PID 分配和释放、进程退出、procfs namespace 和 procfs 挂载路径。
源码来自固定 DDK，原始文件哈希和改动说明见 [ORIGIN](src/port/ORIGIN)。

KallRecon 查找宿主内核符号；测试加载器按 kallsyms 重定位未导出依赖。QEMU 实验
通过 `stop_machine` 下的 ARM64 函数入口替换接入相关路径，并保留原 KCFI 前缀。
新增同名导出符号不能替换宿主中已经内联的空实现，因此必须同时处理生命周期。

QEMU 测试覆盖：

- 未加载时 `unshare -p/-i` 失败；核心模块连续三次加载、自测、卸载。
- `unshare` 和直接 `clone(CLONE_NEWPID | CLONE_NEWIPC)`。
- 容器 PID 1、PID 2、嵌套 PID namespace、独立挂载 `/proc`。
- namespace init 退出后杀死并回收其中的孤儿进程。
- IPC namespace inode 区分、`setns` 恢复原 namespace、非 root 权限拒绝。
- 清理缓存、等待 RCU / workqueue 后 PID / IPC 存活对象计数归零。
- 激活后拒绝卸载；明确检查 `msgget/semget/shmget` 仍返回 `ENOSYS`。

最后一项是当前实现的缺口检查，**不是 IPC 消息、信号量或共享内存隔离测试**。
完整测试和剩余问题见 [移植状态](docs/port-status.md)。

## 复现构建和 QEMU 验证

需要 Docker。默认使用不可变 DDK：

```text
ghcr.io/ylarod/ddk-min@sha256:4dd088dc94b391c926cf09215e0a5958f3dfe7d8eeed3616f9041224f85b1d1a
```

```sh
# 诊断模块
./scripts/build-ddk.sh

# namespace 实验模块，使用独立输出目录
./scripts/build-ddk.sh TARGET=namespace OUT=/module/out/android16-6.12-ns

# 从同一 DDK 提取测试内核，准备 ARM64 QEMU 工具镜像
./tests/vm/prepare.sh
./tests/vm/run.sh
```

测试运行在无网络、无磁盘的 QEMU initramfs 内，不访问手机。成功标志为
`DS_NAMESPACES_PASS`、`remaining pid=0 ipc=0` 和 `DS_VM_RESULT=0`；完整日志在
`out/vm/console.log`。测试加载器只用于实验 VM，不是 `ksud` 本体，也不修改 vermagic。

也可使用已有的内核构建目录：

```sh
make KDIR=/path/to/prepared/kernel OUT="$PWD/out/custom"
```

手机运行模块不需要内核源码；模块开发仍需要头文件、配置和构建接口。当前移植从
DDK 提供的 common 内核源码构建，不依赖厂商完整源码，但尚不具备通用 ABI 兼容性。
DDK 的 release 为 `6.12.76-4k-gae4e2f4f997e-dirty`，与手机并不相同。
`ksud` 的符号重定位不能修复结构布局、CFI 或内联代码差异。

## 已读取的目标设备与探测结果

2026-10-10 通过 adb 读取，实际版本与最初口述版本不同：

- Android 17，ARM64，4 KiB pages。
- 内核 `6.12.69-android16-6-g242e1a07f878-ab15865446-4k`。
- `ksud 3.3.0-69-gdf03912f`。
- 未启用 `CONFIG_PID_NS`、`CONFIG_SYSVIPC`、`CONFIG_POSIX_MQUEUE`、
  `CONFIG_CGROUP_DEVICE`、`CONFIG_CGROUP_PIDS`、`CONFIG_USER_NS`、`CONFIG_DEVTMPFS`。
- `/proc/self/ns` 没有 `pid` 和 `ipc`，root 下两类 `unshare` 均返回 `EINVAL`。
- 启用 `CONFIG_MODULES`、`CONFIG_MODVERSIONS`、`CONFIG_CFI_CLANG`，LTO_NONE。

诊断模块经 `ksud insmod` 真机加载成功，KallRecon 返回 `symbols=132055 layout=2`。
加载前后 boot ID 相同，`kptr_restrict` 恢复为 `2`，模块已卸载。
它没有改变 namespace 能力。日志保存在 `out/validation/load.txt`、`after.txt`。

诊断模块 SHA-256：
`82b8301854f7f296ef7c6cf101d6239bb9bf45f7cd248d882e98197c4657e62e`。

DDK 产物和设备参考模块的 `.gnu.linkonce.this_module` 都为 `0x640` 字节，
但产物 `__versions` 为空，加载有 `no symbol version for module_layout` 日志。
QEMU 加载另有 BTF 基础类型重复候选的提示。因此成功加载并非完整的 CRC / ABI
验证，也不是可以在手机上开启 namespace 钩子的依据。

重新采集设备能力：

```sh
./scripts/collect-device.sh > device-report.txt
```

只加载已验证的诊断模块：

```sh
adb devices -l
adb push out/android16-6.12/droidspaces_probe.ko /data/local/tmp/droidspaces_probe.ko
adb shell su <<'DEVICE'
/data/adb/ksud insmod /data/local/tmp/droidspaces_probe.ko timeout_ms=5000
grep '^droidspaces_probe ' /proc/modules
dmesg | grep droidspaces_probe
rmmod droidspaces_probe
DEVICE
```

参考：[KallRecon](https://github.com/Dere3046/KallRecon)、
[Linux PID namespace 接口](https://github.com/torvalds/linux/blob/v6.12/include/linux/pid_namespace.h)、
[Linux IPC namespace 接口](https://github.com/torvalds/linux/blob/v6.12/include/linux/ipc_namespace.h)。
