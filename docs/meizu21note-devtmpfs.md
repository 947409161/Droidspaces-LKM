# Meizu 21 Note 5.15 — 晚加载 devtmpfs

设备内核 `CONFIG_DEVTMPFS=n`，Droidspaces 的硬件访问模式因此只能回退 tmpfs。
`src/devtmpfs515/` 在运行中的内核上补一个 devtmpfs 文件系统：接管
`device_add` / `device_del`，把已注册设备补成节点，并继续跟踪后续设备。

实现沿用 PLZ110 6.12 版本的晚加载设计（`src/devtmpfs/`），但按 5.15 的
内核 API 与导出情况重写：

- VFS 调用的第一个参数是 `struct user_namespace *`，使用 `&init_user_ns`；
  6.12 的 `nop_mnt_idmap` 在 5.15 不存在。
- 5.15 不导出 `set_fs_root`、`set_fs_pwd`、`notify_change`、`kern_path_locked`、
  `reconfigure_single`、`device_get_devnode`、`devices_kset` 以及
  `shmem_init_fs_context` / `ramfs_init_fs_context`。这些符号在加载时通过
  KallRecon 从 kallsyms 解析，再经函数/数据指针调用，而不是链接引用。
- `is_blockdev()` 在 5.15 的 `drivers/base/base.h` 里不存在，而 `block_class`
  未导出；改为比较 `dev->class->name` 与 `"block"`，避免依赖该符号。
- `vfs_mkdir`、`vfs_rmdir`、`vfs_unlink`、`vfs_getattr` 在 5.15 GKI 中以
  `ANDROID_GKI_VFS_EXPORT_ONLY` 命名空间导出，模块声明
  `MODULE_IMPORT_NS(ANDROID_GKI_VFS_EXPORT_ONLY)`。
- 工作线程用加载进程的凭据创建节点（与 6.12 版本相同的 SELinux 处理），
  使用私有 `fs_struct` 而不是启动期已释放的 `init_mount` / `init_chroot`。

## 接入点

| 路径 | 行为 |
| --- | --- |
| `device_add` / `device_del` 入口 | 校验可搬移的序言后替换为跳转，原始序言保存在模块内的跳板 |
| 已有设备 | 在 `devices_kset` 快照上按 `get_device()` 持有引用后补节点 |
| fs 类型 | 内部实例由 `vfs_kern_mount()` 创建；对外注册名为 `devtmpfs` 的挂载入口 |

模块只读参数 `ready`（已有设备枚举完成且钩子生效）与 `errors`（节点更新失败
计数）。加载器同时要求 `ready=Y` 且 `errors=0`。

## 构建与验证

```sh
python3 scripts/build-gki.py --module devtmpfs515 5.15 -j2
python3 scripts/prepare-devtmpfs515.py 5.15
python3 tests/module/test_devtmpfs515_sources.py
python3 tests/module/test_meizu21note_loader.py
```

CI 会构建该模块并核对：模块 BTF 与 DDK 内核 BTF 的布局完全一致，全部导入
符号可解析。打包时再用设备 BTF 与 `kallsyms` 复核导入符号，并对厂商结构
差异套用与其它载荷相同的白名单规则。

真机验证（root shell，加载后）：

```sh
cat /sys/module/droidspaces_devtmpfs515/parameters/ready    # Y
cat /sys/module/droidspaces_devtmpfs515/parameters/errors   # 0
grep devtmpfs /proc/filesystems
unshare -m sh -c 'mount -t devtmpfs devtmpfs /mnt && ls /mnt | head'
droidspaces check   # devtmpfs 一项应变为可用
```

## 边界

- 替换的是 `device_add` / `device_del` 的函数入口，序言必须落在已验证的
  可搬移集合内；不匹配时加载失败并在 `load.log` 记录实际指令字，不会带病
  替换。该路径属于启动关键路径，失败可能导致设备注册异常，因此只在记录的
  内核版本上启用。
- 钩子安装后模块固定到本次启动；更新或移除需要重启。
- 节点创建依赖加载进程的凭据；SELinux 保持 Enforcing，未修改策略。
  这不代表任意 SELinux 域都能创建或访问这些节点。
- 不包含 QEMU 回归脚本；验证范围限于上述真机检查与 `droidspaces check`。

## 状态

2026-10-25 已在 GitHub Actions（run 40177380401）用固定 DDK 构建并通过审计：
模块 BTF 与 DDK 内核 BTF 布局完全一致，导入符号全部解析。用本设备 BTF 与
`kallsyms` 复核后打包，导入符号全部存在；设备侧结构差异只有已记录的厂商
增量（`perf_event`、`net_device`、`netns_ipv4`、`ipv6_devconf`、`prefix_info`），
大小不变且源码不引用差异字段。v0.2.4 Release 已发布。

真机加载与功能验证仍未完成；在完成上文检查前，不宣称 devtmpfs 可用。
