# PLZ110 user namespace 移植状态

目标为 v0.1.2 的 Sandboxing，仍限定 PLZ110 当前内核与纯 LKM。
当前处于核心移植和隔离测试阶段，**尚不能为 Droidspaces 启用 Sandboxing**。
没有发布 v0.1.2，也没有在真机加载这一实验模块。

## 已实现的部分

`src/userns/user_namespace.c` 移植固定 Android common 6.12 的原生实现，
包括 namespace 创建/销毁、UID/GID/project ID 映射、映射写入权限、
setgroups 控制、父子关系和 namespace operations。符号加独立前缀，
初始化改为模块可调用形式，释放使用专用工作队列。

`src/userns/credentials.c` 移植凭据复制与释放路径，保留 user namespace
引用、LSM 凭据处理、group/user/key/ucount 引用及 RCU 释放。当前仅用于
模块自己的凭据对象，不把这些对象提交给任务，也不混用原生凭据释放路径。
这与替换整个内核的凭据生命周期是不同阶段，后者尚未实现。

`src/userns/utsname.c` 补入采用正确 user namespace 引用的 UTS 核心。
测试验证其所有者、共享对象、名称隔离及释放；并与原生构造函数对照，
确认原生函数仍把新对象的所有者设为 `init_user_ns`。这份 UTS 核心同样
尚未接管正在运行的任务。

`droidspaces_userns_test.ko` 仅接受两个已记录的 QEMU `linux,dummy-virt`
内核。它提供 `/proc/ds_userns_test` 测试入口，不增加 `/proc/<pid>/uid_map`，
不更改系统调用、不安装原生函数入口跳转、不提交任务凭据。真机目标会拒绝加载。

## 已通过的测试

固定 GKI 6.12 和 PLZ110 原始 boot image 中的 6.12.69 内核均在 QEMU
中验证。最终组合先加载对应 PID/IPC 与 devtmpfs，再执行 user namespace
核心测试；测试模块连续加载、卸载两轮，退出时 namespace 和私有凭据
计数均归零，已有 PID/IPC 和 devtmpfs 保持正常。

- 空映射、UID/GID 正反向转换、未映射 ID、overflow ID。
- 非法映射、零长度范围、范围溢出、重叠范围、尾随垃圾、无效用户地址和非零写入偏移。
- 映射只允许成功写入一次，六段映射走动态数组及二分查找路径。
- 非特权进程不能写其他所有者的映射，不能映射其他 UID 或宿主 UID 0。
- 所有者的单 ID 映射，以及 GID 映射前必须禁用 setgroups 的规则。
- setgroups 的 deny 不可恢复，已有 GID 映射后不能改为 deny。
- 子 namespace 的原生 `cap_capable()` 判断不能授予父级、初始或兄弟 namespace 的能力。
- 嵌套深度限制、namespace 数量配额、未映射所有者拒绝及失败后的引用回收。
- 私有凭据复制、普通 RCU 释放、`non_rcu` 释放和只创建未提交凭据的 `unshare_userns()`。

这些结果证明独立核心在记录的环境中运行，不证明任务级 Sandbox 已隔离。
测试明确要求原生 `unshare(CLONE_NEWUSER)` 仍失败、`/proc/self/ns/user`
仍不存在，防止把测试入口误认为正式功能。

## 接入任务前的缺口

以下为已经定位的调用链，不是完整安全审计清单：

| 路径 | 目标内核的缺失行为 | 后续工作 |
| --- | --- | --- |
| 凭据 | `prepare_creds`、`prepare_kernel_cred`、释放回调省略 user namespace 引用 | 处理全局接管、现存凭据、错误回滚和 RCU 生命周期 |
| clone/unshare/setns | 原生 `copy_creds` 和已发布 PID/IPC 载荷仍采用未启用 USER_NS 的分支 | 与 PID/IPC 载荷整合，恢复校验、创建、安装和销毁路径 |
| procfs | `fs/proc/base.c` 的 UID/GID/project ID 映射和 setgroups 表项由配置条件移除 | 恢复真实进程入口、任务退出竞态、文件凭据和读写权限 |
| UID/GID 系统调用 | `make_kuid` 等为恒等映射；已检查的 GKI `getuid` 直接读取宿主 UID | 覆盖身份读取/变更、groups、stat、信号等使用映射的路径 |
| 其他 namespace 的所有者 | 禁用 USER_NS 时 `get_user_ns()` 返回 `init_user_ns`；原生 mount、UTS 构造函数使用该内联函数 | UTS 私有实现已测试；尚需全局接入，并恢复 mount/net/cgroup 等的所有者和引用 |
| 资源计数、文件系统、LSM 和 keyring | 存在内联的 current_user_ns、ID 映射及引用假设 | 逐条覆盖相关功能与拒绝路径，不能通过仅增加一个构造函数解决 |

例如，`alloc_mnt_ns()` 和 `clone_uts_ns()` 把 `get_user_ns(user_ns)` 的
返回值保存为所有者；现有内核的该内联函数会返回初始 namespace。
因此，仅向这些原生函数传入新 user namespace 指针仍不能正确创建
归其所有的 mount/UTS namespace。

不使用统一“返回允许”的权限替代，也不以修改 Droidspaces 检查结果
作为实现。下一阶段需要先完成凭据及 namespace 所有者的生命周期衔接，
再连接用户可见的 clone/unshare/proc 接口。

## 重现

前提是已有固定 DDK、VM 工具镜像及对应的内核/载荷输入：

```sh
./scripts/build-ddk.sh TARGET=userns OUT=/module/out/userns -j2
DS_NS_MODULE=/work/out/gki/android16-6.12/droidspaces_ns.ko \
DS_DEV_MODULE=/work/out/devtmpfs/droidspaces_devtmpfs.ko \
./tests/vm/run-userns-core.sh
```

设备原始内核的 VM 通过 `DS_USERNS_KERNEL`、`DS_USERNS_MODULE`、
`DS_USERNS_LOG_DIR` 选择输入，同时指定 v0.1.0 的固定设备 PID/IPC 载荷、
`DS_NS_PARAMS=activate=1` 和 v0.1.1 的 devtmpfs 载荷。
运行时 ABI 核验不由 vermagic 替换代替。

本地证据位于 `out/userns/validation.json`、`out/userns/device-abi.json`
及两份 VM console.log；其中记录源码、二进制和内核的哈希。
源码来源与适配说明见 [ORIGIN](../src/userns/ORIGIN)。

本实验分支修改了 Makefile，因此 v0.1.1 打包器会按设计拒绝当前源码：
如需重现该已发布版本，请使用其 `v0.1.1` 标签及对应已验证输入。
