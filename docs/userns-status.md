# PLZ110 user namespace 移植状态

目标为 v0.1.2 的 Sandboxing，限定 PLZ110 当前内核与纯 LKM。
当前已经接入真实任务、凭据、映射文件及部分文件系统路径，但**尚未达到可发布的完整 Sandboxing**。
实验载荷仅允许 QEMU，未在手机加载；v0.1.2 尚未发布。

## 两种测试目标

`TARGET=userns` 生成 `droidspaces_userns_test.ko`，只创建模块私有对象，
提供 `/proc/ds_userns_test`。它不接管任务，适合检查映射、权限和生命周期的独立核心。
此前该目标已在固定 GKI 和 PLZ110 原始内核的 QEMU 环境中通过两轮加载/卸载测试。

`TARGET=namespace USERNS=1` 生成实验性的 `droidspaces_ns.ko`，把 user namespace
和已有 PID/IPC 移植整合。此目标安装原生函数入口及系统调用替换，接管真实任务，
激活后固定在内核中直至重启。初始化在修改代码前检查目标内核及函数入口；
当前明确拒绝非 `linux,dummy-virt` 机器，不能把该实验构建直接拿到手机使用。

## 已接入的实现

| 路径 | 实现 |
| --- | --- |
| 核心 | 原生 user namespace 创建/销毁、UID/GID/project ID 映射、写入权限、setgroups、嵌套及 namespace operations |
| 凭据 | prepare/copy/kernel credentials、释放入口和 RCU 回调；共享原生 cred slab，保留 LSM、key、group、user 和 ucount 处理 |
| 资源计数 | 共享原生 ucounts 表与锁，恢复 namespace 引用及普通、rlimit 计数释放路径 |
| 任务与 procfs | clone/unshare/setns 的移植入口；真实 `/proc/<pid>/{uid_map,gid_map,projid_map,setgroups}`，保留设备原有目录表项 |
| 身份系统调用 | UID/GID 读取与修改、res/fs ID、补充组的映射和 setgroups 策略 |
| UTS | 原生 slab 与 namespace 所有者引用，支持子 user namespace 内修改主机名 |
| mount namespace | 共享原生 mount tree、锁和序列号，恢复所有者及 passive 引用释放，覆盖 statmount/listmount 内联释放路径 |
| 文件系统上下文 | fs_context 创建、复制及释放的 user namespace 引用 |
| superblock | alloc/sget/sget_fc、错误回滚及异步销毁的所有者和引用；保留 FS_USERNS_MOUNT 与 LSM 检查 |
| 文件属性 | arm64 stat/statx 的 UID/GID 输出转换 |

现存原生对象没有获取过初始 user namespace 的引用，因此 live 构建将
`init_user_ns` 作为永久对象；新建的非初始 namespace 始终使用完整引用协议。
独立核心构建保留原生的 get/put 行为。

编译器内联是移植的重要限制。测试已抓到原生 ucount 计数路径和 credential RCU
释放路径绕过入口替换造成的泄漏，随后扩大替换范围修复。mount 和 superblock
销毁也不能只替换单个公开释放函数；相关内联调用者已一并移植。
PLZ110 还内联了普通 stat 的结果转换函数，因此相应实现接管系统调用入口，
不依赖 GKI 上存在但设备上缺失的局部符号。
这不代表其他内联路径已经全部覆盖。

## 已验证范围

live VM 测试以真实非特权 UID 1000 运行，不通过伪造检测结果启用功能：

- `clone(CLONE_NEWUSER)` 和 `unshare(CLONE_NEWUSER)` 创建不同 namespace。
- 映射前返回 overflow ID；允许自身单 ID 映射，拒绝映射宿主 root。
- GID 映射要求先禁用 setgroups，禁止恢复组修改权限。
- UID/GID、res/fs ID、补充组及 stat/statx 返回映射后的值，未映射身份修改被拒绝。
- 子 namespace 仍不能读取宿主 root 的 0600 文件。
- 私有 mount namespace 内绑定挂载、查询、卸载正常。
- 私有 tmpfs 创建和写入正常；归属新 PID namespace 的 procfs 可挂载并访问 PID 1。
- UTS 主机名不影响父进程；嵌套 user namespace 创建及退出正常。
- 测试结束后 user namespace 活跃计数必须为零，控制台不得出现 BUG、WARNING、Oops 或 panic。

固定 GKI 和 PLZ110 原始 boot image 均用于 QEMU 回归。VM 使用 `selinux=0`；
这些结果不涵盖手机上的 Android SELinux 策略，也不等于完整 Sandbox 隔离证明。
独立核心的深度/配额/映射边界测试与 live 任务测试互补。

## 发布前仍需完成

- exec 后的 namespace、凭据和能力语义，以及 `mm->user_ns` 生命周期。
- `cap_task_fix_setuid` 等能力路径仍内联恒等 UID 映射；多 ID 映射下离开 namespace root 时的降权必须补全并做负向验证。
- setns、线程、映射 FD 跨进程和退出竞态的补充回归。
- chown/access/chroot、其他 VFS 与 LSM、keyring、net/cgroup/time 等内联的 USER_NS 假设。
- 完整沙箱程序及负向隔离测试；不能仅凭 Droidspaces 的功能探测通过发布。
- PLZ110 真机验证、开机加载模块、状态报告和 v0.1.2 制品打包。

没有采用统一返回允许的权限替代，也未修改 Droidspaces 的检查结果。
不扩大到替换内核镜像。

## 重现

需要固定 DDK、VM 工具镜像及已记录的内核输入：

```sh
./scripts/build-ddk.sh TARGET=namespace USERNS=1 OUT=/module/out/userns-live -j2
./tests/vm/run-userns-live.sh
```

使用 `scripts/abi/prepare-device-vm.py` 的 `prepare()` 为 PLZ110 原始镜像准备
VM 输入，再设置 `DS_USERNS_KERNEL`、`DS_USERNS_MODULE`、`DS_USERNS_LOG_DIR`。
修改 vermagic 只为 VM 加载匹配，不代替 ABI 核验。

本地 live 证据位于 `out/userns-live/validation.json`、`device-abi.json` 和
`vm/console.log`、`device-vm/console.log`。验证清单记录测试源码、二进制、内核与日志哈希。
BTF 比较核对聚合布局及可比较的导入函数原型，不能证明所有内联语义相容。
已知设备额外保留字段涉及 `mm_struct`、`task_struct` 和 `files_struct`，
没有改变本次比较的同名字段偏移或结构总大小；实验代码不读取这些设备私有字段。

源码来源与适配说明见 [ORIGIN](../src/userns/ORIGIN)。
如需重现已发布 v0.1.1，请使用对应标签；其打包器会拒绝本实验分支的修改后源码。
