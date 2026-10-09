# Droidspaces LKM

通过 KernelSU 动态加载内核模块，为未启用 PID / IPC namespace 的 Android 内核补充
Droidspaces 所需的进程与 IPC 隔离能力。无需刷写内核，运行时无需内核源码。

**当前版本为针对指定设备和内核的实验性实现。** 已通过目标设备上的功能测试，
Droidspaces v6.6.0 的全部必需能力检查通过；完整容器启动与长期稳定性仍需进一步验证。

## 功能

- PID namespace：创建、嵌套、切换、PID 1、procfs、孤儿进程回收与容器 reboot。
- IPC namespace：SysV 消息队列、信号量、共享内存及 POSIX 消息队列。
- 相关生命周期：perf、BPF task iterator、FUSE、cgroup-v1 pidlist、pidfd。
- memfd namespace 策略及 IPC proc/sysctl 接口。
- KernelSU 模块：开机自动加载、目标检查、载荷校验、动态状态简介和加载日志。

## 支持范围

| 项目 | 当前支持 |
| --- | --- |
| 设备 | PLZ110，Device Tree compatible 包含 `qcom,canoe` |
| Android | Android 17 |
| 架构 / 页面大小 | ARM64 / 4 KiB |
| 内核 | `6.12.69-android16-6-g242e1a07f878-ab15865446-4k` |
| 加载器 | 支持 `ksud insmod` 的 KernelSU；已验证 `3.3.0-69-gdf03912f` |
| SELinux | 已在 Enforcing 下验证 |

安装器和启动脚本均检查完整内核版本与设备标识。不支持直接用于其他内核版本，
包括同为 6.12 的其他构建。内核升级后需要重新适配和验证。

## 下载与安装

从 [GitHub Releases](https://github.com/Shikochin/Droidspaces-LKM/releases) 下载：

| 文件 | 用途 |
| --- | --- |
| `Droidspaces-LKM-KernelSU-v*.zip` | KernelSU 管理器安装包，内含 `.ko` |
| `droidspaces_ns-6.12.69-canoe.ko` | 独立内核模块，供手动加载 |
| `SHA256SUMS` | 发布资产的 SHA-256 校验值 |

### KernelSU 自动加载

1. 在 KernelSU 管理器中选择模块 ZIP 并安装。
2. 重启设备，模块在 `service.sh` 阶段执行 `ksud insmod ... activate=1`。
3. 刷新管理器模块列表，确认简介显示 **`[已加载]`**。
4. 运行 `droidspaces check` 检查运行环境。

此模块不挂载或替换系统文件，不需要 metamodule，也不修改 SELinux 策略。
安装过程不立即加载内核模块；开机时执行一次加载，失败后记录结果，不循环重试。

### 简介与日志

| 状态 | 含义 |
| --- | --- |
| `[待加载]` | 本次开机尚未执行加载 |
| `[加载中]` | 正在调用 `ksud insmod` |
| `[已加载]` | `activate=Y`，且 PID、pid_for_children、IPC namespace 接口均存在 |
| `[加载失败]` | 加载器、载荷校验、insmod 或激活检查失败 |
| `[不支持]` | 设备或完整内核版本不匹配 |

优先使用 KernelSU 的临时 `override.description`，在下次开机自动清除；不支持该
接口时回退到更新 `module.prop`，并在 `post-fs-data.sh` 重置为待加载状态。
状态机制遵循 [KernelSU Module Configuration](https://kernelsu.org/guide/module-config.html#overriding-module-description)。

日志与状态文件位于 `/data/adb/modules/droidspaces_lkm/`：

- `load.log`：最近一次启动加载记录。
- `load.log.previous`：上一次记录。
- `status.txt`：最近一次状态文本。

**激活后的内核模块不能热卸载。** 在管理器中禁用或卸载安装包后，需要重启设备
才能移除当前内核中的模块；更新 `.ko` 同样需要重启。

### 手动加载

将独立 `.ko` 上传到设备后，在 root shell 执行：

```sh
/data/adb/ksud insmod /data/local/tmp/droidspaces_ns-6.12.69-canoe.ko activate=1
DS_NO_PROXY=1 /data/local/Droidspaces/bin/droidspaces check
```

也可通过仓库脚本加载本地产物：

```sh
./scripts/load-device.sh out/release/droidspaces_ns-6.12.69-canoe.ko
```

多设备环境使用 `ANDROID_SERIAL` 选择目标。不要对已加载的模块重复执行 insmod。
省略 `activate=1` 时只执行入口预检和可卸载的核心对象自测，不接入 namespace
系统调用；自测模式仍会临时注册相关 proc/sysctl 和 mqueue 接口。

## 构建与打包

内核模块使用固定 Android DDK 构建，依赖 Docker：

```sh
./scripts/build-ddk.sh TARGET=namespace OUT=/module/out/android16-6.12-ns
```

DDK 镜像：

```text
ghcr.io/ylarod/ddk-min@sha256:4dd088dc94b391c926cf09215e0a5958f3dfe7d8eeed3616f9041224f85b1d1a
```

KernelSU 模块源码位于 [`kernelsu/`](kernelsu/)。打包脚本生成 ZIP、独立 `.ko` 和
`SHA256SUMS`，不会重新编译内核模块：

```sh
python3 scripts/package-module.py \
  --module /path/to/droidspaces_ns-6.12.69-canoe.ko \
  --output out/release
```

v0.1.0 固定使用已在真机验证的二进制，SHA-256 为：

```text
33ed20ce38f092d98f4379701d45127522370d13f3d59ba6458916a0b6f592f4
```

重新构建的二进制可能因调试信息和构建元数据具有不同哈希。打包脚本不会自动放行：
发布新产物前应完成验证并更新脚本中的固定哈希。源码与构建来源见
[`src/port/ORIGIN`](src/port/ORIGIN)。默认 `./scripts/build-ddk.sh` 构建只探测的
`droidspaces_probe.ko`。

## 独立 6.6 实验构建

Android 15 / Linux 6.6 GKI 的移植位于 `src/port66/`，使用独立 DDK 和输出目录。
该构建仅面向匹配的 QEMU 测试内核，尚未验证 6.6 真机。构建命令、测试结果与限制见
[`docs/android15-6.6.md`](docs/android15-6.6.md)。上述设备支持及下载说明仍指 6.12 版本。

## 验证

已在 DDK 内核、目标设备提取的实际内核 Image（QEMU）和目标 Android 设备上验证：

- namespace 创建、切换、权限检查、独立 procfs、嵌套 PID 与孤儿回收。
- 容器 reboot、pidfd ioctl、perf/BPF 保留 FD、cgroup 与 FUSE 引用生命周期。
- SysV IPC 访问、阻塞、隔离、SEM_UNDO、共享内存继承与回收。
- POSIX mqueue 挂载、优先级、超时、通知、隔离与 unlink 后 FD 生命周期。
- memfd 可执行策略、seal、父 namespace 策略约束与宿主隔离。

真机测试保持 SELinux Enforcing，宿主未重启，PID / IPC namespace 测试对象完成回收。
详细范围与证据说明见 [`docs/port-status.md`](docs/port-status.md)。KernelSU 启动脚本
另有隔离测试，实际安装后的重启流程不包含在上述内核功能测试中。

```sh
# KernelSU 加载逻辑测试（不加载内核模块）
python3 tests/module/test_loader.py -v

# DDK 内核 QEMU 测试
./tests/vm/prepare.sh
./tests/vm/run.sh

# 使用已采集的目标 boot image 和参考模块
python3 scripts/abi/prepare-device-vm.py \
  out/device/boot_b.img out/android16-6.12-ns/droidspaces_ns.ko \
  out/device/reference.ko out/vm-device
DS_VM_KERNEL=/work/out/vm-device/Image \
DS_VM_MODULE=/work/out/vm-device/droidspaces_ns.ko ./tests/vm/run.sh
```

QEMU 使用无网络、无磁盘的 initramfs。设备采集文件、测试日志和构建产物不存入 Git。
ABI 对比工具为 [`scripts/abi/compare-btf.py`](scripts/abi/compare-btf.py)；vermagic
调整和 kallsyms 重定位不能替代结构布局、函数签名与生命周期验证。

## 限制

- 当前仅适配上述设备内核，不提供跨版本 ABI 兼容性。
- 使用实验性入口替换，激活后保持模块引用直到重启。
- 未覆盖完整 rootfs / systemd 启动、长期高并发、OOM 及所有 SELinux 域。
- 未接入 32 位 IPC 兼容系统调用；SIGEV_THREAD 与 hugetlb 共享内存尚未完整验证。
- 不提供 user namespace、devtmpfs 或额外 cgroup 控制器。

## 许可证与来源

项目采用 [GPL-2.0](LICENSE)。移植代码和依赖保留各自的版权及许可证声明。

- [KallRecon](https://github.com/Dere3046/KallRecon)：内核符号解析。
- Android common kernel：PID / IPC namespace 及相关实现，来源与哈希见
  [`src/port/ORIGIN`](src/port/ORIGIN)。
- [KernelSU](https://github.com/tiann/KernelSU)：模块加载与启动脚本框架。
