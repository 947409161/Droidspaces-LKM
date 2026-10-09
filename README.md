# Droidspaces LKM

为自己的 Android 17 手机动态补齐 PID / IPC namespace，无需刷写内核或取得厂商
完整源码。**已在真机通过 `ksud insmod` 激活，Droidspaces v6.6.0 检查全部必需项通过。**

当前仅支持这台已验证的设备：

- PLZ110 / `qcom,canoe`，ARM64，4 KiB pages。
- 内核 `6.12.69-android16-6-g242e1a07f878-ab15865446-4k`。
- KernelSU `ksud 3.3.0-69-gdf03912f`，SELinux Enforcing。

实际读取的版本是 6.12.69，与最初口述的 6.12.59 不同。内核更新后不能直接沿用。
模块包含内核函数入口替换，仍属于实验实现；激活后永久持有引用，**重启才能移除或
替换**。没有安装开机自启，不修改 Droidspaces 程序或配置。

## 产物与使用

已验证的产物：`out/release/droidspaces_ns-6.12.69-canoe.ko`，4,923,672 字节。
SHA-256：

```text
33ed20ce38f092d98f4379701d45127522370d13f3d59ba6458916a0b6f592f4
```

手机当前已经激活。重启后如需重新加载：

```sh
./scripts/load-device.sh out/release/droidspaces_ns-6.12.69-canoe.ko
```

脚本固定目标设备序列号，核对完整内核版本，上传模块后运行：

```sh
/data/adb/ksud insmod /data/local/tmp/droidspaces-lkm/droidspaces_ns.ko activate=1
DS_NO_PROXY=1 /data/local/Droidspaces/bin/droidspaces check
```

不传 `activate=1` 时，只执行入口预检和可卸载的核心对象自测，不接入 namespace
系统调用；该模式仍会临时注册 IPC proc/sysctl/mqueue 和 memfd sysctl 接口。

## 已完成与验证

模块移植 PID / IPC namespace、nsproxy、PID 分配/释放、进程退出和 procfs 路径，
补齐 SysV 消息队列、信号量、共享内存、POSIX mqueue 及相关 proc/sysctl。
额外恢复 perf、BPF task iterator、FUSE、cgroup-v1 pidlist、pidfd 对 namespace
的引用，并接入容器 reboot 和 memfd namespace 策略。

先在 DDK 内核和从手机 `boot_b` 只读提取的实际 Image 上运行 QEMU 测试，再在手机
SELinux Enforcing 下运行同一组用户态功能测试。真机全部通过：

- PID 1、嵌套 PID、独立 procfs、孤儿回收、clone、setns、权限拒绝、pidfd ioctl。
- 容器 reboot 结束 namespace init，宿主 boot ID 不变。
- SysV IPC 收发、等待/删除、隔离、SEM_UNDO、共享 clone、失败回滚、共享内存回收。
- POSIX mqueue 挂载、优先级、超时、通知、隔离、sysctl、unlink 后 FD 生命周期。
- perf 继承及保留 FD、BPF iterator 保留 FD、cgroup pidlist、FUSE 挂载释放。
- memfd 可执行策略、seal、父 namespace 策略下限、宿主隔离。

随后真机 PID / IPC namespace 存活计数均回到 0；IPC 任务状态表仍用于存活的 Android
线程，不能要求全机该计数为 0。手机未重启，`kptr_restrict` 保持 2，SELinux 始终
Enforcing。Droidspaces 输出 `All required features found!`。

尚未启动完整 Droidspaces rootfs / systemd 容器，也未做长期压力验证。devtmpfs 和
user namespace 仍缺失，分别影响硬件访问模式和可选沙箱功能。

技术说明、验证记录和限制见 [移植状态](docs/port-status.md)。

## 构建与离线验证

需要 Docker。使用固定 DDK，开发时仍需其 common 内核源码、头文件和构建接口；
手机加载时不需要这些文件。

```sh
# namespace 模块
./scripts/build-ddk.sh TARGET=namespace OUT=/module/out/android16-6.12-ns

# DDK 内核的 QEMU 测试
./tests/vm/prepare.sh
./tests/vm/run.sh

# 使用已经采集到的手机 boot image 和参考模块
python3 scripts/abi/prepare-device-vm.py \
  out/device/boot_b.img out/android16-6.12-ns/droidspaces_ns.ko \
  out/device/reference.ko out/vm-device
DS_VM_KERNEL=/work/out/vm-device/Image \
DS_VM_MODULE=/work/out/vm-device/droidspaces_ns.ko ./tests/vm/run.sh
```

QEMU 使用无网络、无磁盘的 initramfs，日志为 `out/vm/console.log`。准备脚本只调整
模块 vermagic 供目标内核加载，不改变代码或 ABI；真机由 `ksud` 完成相同的版本字符串
适配和 kallsyms 重定位。二者都不能代替结构布局、函数签名或生命周期适配。

ABI 对比工具：

```sh
python3 scripts/abi/compare-btf.py out/abi/module.btf out/device/vmlinux.btf \
  --kernel-btf out/abi/ddk.btf --imports out/abi/imports.txt \
  --symbols out/device/kallsyms.txt
```

这些输入由设备采集、`pahole -F dwarf --btf_encode_detached=...`、DDK vmlinux 的
`.BTF` 节和 `llvm-nm -u` 得到，不存入 Git。源码来源、原始哈希见
[src/port/ORIGIN](src/port/ORIGIN)。DDK 固定为：

```text
ghcr.io/ylarod/ddk-min@sha256:4dd088dc94b391c926cf09215e0a5958f3dfe7d8eeed3616f9041224f85b1d1a
```

默认 `./scripts/build-ddk.sh` 仍构建只探测的 `droidspaces_probe.ko`。

参考：[KallRecon](https://github.com/Dere3046/KallRecon)、
[Linux PID namespace](https://github.com/torvalds/linux/blob/v6.12/include/linux/pid_namespace.h)、
[Linux IPC namespace](https://github.com/torvalds/linux/blob/v6.12/include/linux/ipc_namespace.h)。
