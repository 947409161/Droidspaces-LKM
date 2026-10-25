# Meizu 21 Note（Android 13 / 5.15）真机测试

记录 `codex/a13-5.15.119-build` 分支构建的 Meizu 21 Note 专用模块在真机上的
加载与功能验证结果。该模块沿用 `src/port515/` 的 GKI 5.15 移植，仅提供
PID / IPC namespace，与 GKI v0.2.0 的功能范围一致，不含 devtmpfs、
Sandboxing（user namespace）或 Docker netfilter 扩展。

## 目标与安装

- 设备：Meizu 21 Note，ARM64、4 KiB 页面。
- 完整内核版本：`5.15.119-android13-8-g6ff5097ee32a-ab1764665171`。
- BTF SHA256：`ceb62a44dbeb782434c5956c71c03b635129017399cedbf2a1e6cc072998081c`。
- 模块：`droidspaces_lkm_meizu21note` v0.2.1-m21n1，KernelSU ZIP 安装，
  开机由 `service.sh` 核对设备、内核版本与 BTF 指纹后经 `ksud insmod`
  以 `gki=1 activate=1` 加载。

加载前的静态核对与 [打包器](../scripts/package-meizu21note.py) 一致：
设备 BTF 指纹、`CONFIG_ARM64_4K_PAGES=y`、`CONFIG_CFI_CLANG=y`，以及
`perf_event`、`netns_ipv4`、`net_device`、`fuse_conn` 四个结构与基线差异
白名单的对比。

## 2026-10-25 真机结果

SELinux 保持 Enforcing。`lsmod` 显示 `droidspaces_ns` 已加载，引用计数 16，
说明容器进程正在使用模块提供的 namespace 接口。

Droidspaces v7.0.0 `check` 输出：

```text
[MUST HAVE] 全部通过：Root、Linux version、PID / Mount / UTS / IPC namespace、
pivot_root、/proc、/sys、Seccomp —— All required features found!
```

必选项之外的缺失项均属预期，与 GKI 5.15 移植范围一致：

| 缺失项 | 原因 |
| --- | --- |
| devtmpfs | v0.2.3 前不含 devtmpfs 载荷；v0.2.4 起由 `droidspaces_devtmpfs515.ko` 提供，见 [devtmpfs 移植](meizu21note-devtmpfs.md) |
| Sandboxing (user namespaces) | 5.15 移植不含 user namespace |
| CPU / Process limit | 内核编译选项 `CONFIG_CFS_BANDWIDTH` / `CONFIG_CGROUP_PIDS` 未设置，非模块范围 |
| Macvlan、IPv6 NAT | 内核未启用 `CONFIG_MACVLAN` / `CONFIG_IP6_NF_NAT`；v0.2.2 起由 `droidspaces_net515.ko` 提供，见 [扩展说明](meizu21note-net-extras.md) |

上述结果来自 v0.2.1-m21n1（仅 namespace 模块）。2026-10-25 的真机检查已确认
v0.2.3 中 Macvlan 与 IPv6 NAT 变为可用（`droidspaces_net515.ko` 生效）。
v0.2.4 增加 `droidspaces_devtmpfs515.ko`，devtmpfs 一项待真机确认；
Sandboxing（user namespace）仍未覆盖。

## 容器内功能验证

在模块激活后创建的 Droidspaces 容器（Debian 13 trixie，systemd 为 PID 1，
约 112 个进程）内以普通用户（UID 1000）验证：

| 项目 | 结果 |
| --- | --- |
| PID namespace | 容器拥有独立 PID 视图，PID 1 为 systemd |
| SysV 消息队列 | `ipcmk -Q` 创建、`ipcs -q` 可见 |
| POSIX mqueue | `/dev/mqueue` 已挂载；`mq_open(O_RDWR\|O_CREAT)` 创建与 `mq_unlink` 成功 |
| IPC proc/sysctl | `kernel.msgmax`、`kernel.msgmnb`、`kernel.shmmax` 可读 |

`unshare --pid` 在无特权的 UID 1000 下按预期返回 EPERM：namespace 创建
由宿主端 Droidspaces 以 root 完成，普通用户经 `clone` 获得共享 namespace。

## 边界

- 本轮未执行 `activate=0` 预检 / 卸载回路，也未重复 [port-status](port-status.md)
  中的完整 QEMU 套件；5.15 目标的 QEMU 回归见 [GKI 构建与验证](gki-builds.md)。
- 模块激活后不可热卸载；更换或移除需重启。
- 结果仅适用于与上述内核版本和 BTF 指纹完全一致的二进制。
