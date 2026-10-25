# Meizu 21 Note 5.15 — 网络扩展（MACVLAN / IPv6 NAT / addrtype / ipset）

`droidspaces_ns.ko` 只补 PID / IPC namespace，因此 Droidspaces 检查在该设备上
仍报告两项可选能力缺失：Macvlan 与 IPv6 NAT。本扩展用第二个独立模块
`droidspaces_net515.ko` 提供这两项，并补上 Docker 规则会用到的 `xt_addrtype`，
源码位于 `src/net515/`。

## 为什么这两项可以用 LKM 补

两者在主线都是普通模块，设备内核只是没有编入：

| 能力 | 设备内核状态 | 缺失的只是 |
| --- | --- | --- |
| Macvlan | `CONFIG_MACVLAN` 未设置 | `drivers/net/macvlan.c` 的 rtnl link kind 与 netdevice notifier |
| IPv6 NAT | `CONFIG_IP6_NF_NAT` 未设置 | `net/ipv6/netfilter/ip6table_nat.c` 的 IPv6 `nat` 表模板 |
| xt_addrtype | `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE` 未设置 | `net/netfilter/xt_addrtype.c` 的 addrtype 匹配 |
| ipset | `CONFIG_IP_SET` 未设置 | ipset 核心、16 种 set 类型与 `xt_set` 匹配，共 18 个模块 |

IPv6 NAT 的其余部分设备已经内置：`CONFIG_NF_NAT=y`、`CONFIG_IP6_NF_IPTABLES=y`、
`CONFIG_NF_NAT_MASQUERADE=y`。masquerade 目标来自
`CONFIG_NETFILTER_XT_TARGET_MASQUERADE=y` 编入的 `xt_MASQUERADE`：该目标在 5.15 里
同时注册 `NFPROTO_IPV4` 与 `NFPROTO_IPV6`（`net/netfilter/xt_MASQUERADE.c`），
`nf_nat_masquerade_ipv6` 也在运行内核中存在。设备虽未设置
`CONFIG_IP6_NF_TARGET_MASQUERADE`（5.15 已无独立的 `ip6t_MASQUERADE.c`），但该
配置项在 5.15 不再需要。所以只补一张 `ip6table_nat` 表即可，不需要另写
masquerade 目标，也不需要 nftables。

设备未启用 `CONFIG_NF_TABLES`，因此本分支不加入 netfilter 的 nftables 单元；
该设备上 Docker 的 NAT 路径由 iptables-legacy 承担，与现状一致。

## 与内核的契约

模块沿用 `src/netfilter/`（PLZ110 6.12）的单元化做法：一个 `.ko` 内按顺序注册
两个单元，失败时逆序回滚；注册结果通过只读模块参数暴露给开机脚本。

- 单元入口：`ds_nf_init_net515_macvlan`、`ds_nf_init_net515_ip6table_nat`、
  `ds_nf_init_net515_xt_addrtype`，由 `src/net515/main.c` 按序调用；上游文件只把
  `module_init` / `module_exit` 换成包装，其余内容保持原样（含许可证声明）。
- 编译期定义 `CONFIG_MACVLAN=1`，让 `include/linux/if_macvlan.h` 提供内联访问器，
  而不是未启用时的 `BUG()` 占位实现；同时定义 `CONFIG_IP6_NF_IPTABLES=1`，
  让 `xt_addrtype` 保留 IPv6 匹配与 `NFPROTO_IPV6` 注册（上游用该选项守卫整段）。
  设备本身启用 `CONFIG_IP6_NF_IPTABLES=y`，所以运行时语义一致。
- 只读参数：`macvlan_registered`、`ip6table_nat_registered`、
  `xt_addrtype_registered`，加载器据此判断三个单元是否都真正注册成功。
- 目标限制：`qcom,kalama` 且完整版本
  `5.15.119-android13-8-g6ff5097ee32a-ab1764665171`，或 `linux,dummy-virt`
  上的 5.15.x QEMU。其他内核直接返回 `EOPNOTSUPP`。

初始化不创建网卡、不安装任何防火墙规则；MACVLAN 设备只在用户态请求时出现，
IPv6 `nat` 表与原生模块一样注册为空模板。

## 依赖符号

在 5.15.202 源码中确认已导出（`EXPORT_SYMBOL` / `EXPORT_SYMBOL_GPL`）：

- `ip6t_register_table`、`ip6t_unregister_table_exit`、`ip6t_do_table`、
  `ip6t_alloc_initial_table`（net/ipv6/netfilter/ip6_tables.c）
- `xt_find_table`、`xt_register_template`、`xt_unregister_template`
  （net/netfilter/x_tables.c）
- `nf_nat_ipv6_register_fn`、`nf_nat_ipv6_unregister_fn`
  （net/netfilter/nf_nat_proto.c）
- `xt_register_matches`、`xt_unregister_matches`（net/netfilter/x_tables.c），
  以及 addrtype 使用的 `inet_dev_addr_type`、`__ipv6_addr_type`、
  `ipv6_chk_addr`、`__nf_ip6_route`、`dst_release`

2026-10-25 在目标设备 `/proc/kallsyms` 中核对：上述符号以及 macvlan 使用的一批
`dev_*` / `netdev_*` / `eth_*` 接口全部存在，`net/` 源码中调用的外部符号没有
在设备上缺项。GKI 的导出约定保证同一 KMI（android13-5.15）内符号 CRC 一致。


## ipset

`src/ipset515/` 用的是另一种策略：**上游文件零改动**。ipset 的每个模块本来就是
独立编译、按需加载的主线模块，所以这里不合并成一个 `.ko`，也不替换入口点；
`modules.json` 记录模块组成与加载顺序，Makefile 由它生成，测试逐行核对两者。

- 模块名统一加 `droidspaces_` 前缀（`droidspaces_ip_set`、`droidspaces_ip_set_hash_net`、
  `droidspaces_xt_set` 等），避免与将来原生编入的 ipset 冲突。
- 编译期定义 `CONFIG_IP6_NF_IPTABLES=1`，使 `ip_set_getport()` 能解析 IPv6 端口；
  不定义 `CONFIG_BRIDGE_NETFILTER`，因为设备也没启用，`hash:netiface` 因而编译成
  非 bridge 变体，与宿主行为一致。另外补 `CONFIG_IP_SET_MAX=256`：这个值来自 ipset
  自己的 Kconfig，设备内核连同 `CONFIG_IP_SET` 一起没有，256 是上游默认值。
- 内核在 `insmod` 时解析模块间符号，所以加载顺序固定为：核心 → 16 种 set 类型 →
  `xt_set`。`droidspaces_ip_set` 导出 set 操作与工具符号（参考实现中为 26 个），
  类型模块依赖其中一部分；
  审计脚本会用 `__ksymtab` 精确核对“模块间导入”和“内核导入”，不存在靠猜测的地方。
- 不附带用户态 `ipset` 程序：容器内安装发行版的 ipset 包即可（Debian 为 `ipset`），
  它通过 nfnetlink 直接与内核模块通信，不需要宿主端二进制。

已验证的静态条件：设备 `CONFIG_IP_SET=n`，但 ipset 核心所需的 nfnetlink、
`nf_register_sockopt`、netlink 与内存分配符号全部存在；第三方 IPSET_LKM v2.5 的
android13-5.15 包基于同样的 5.15.202 基线（vermagic 相同），其 `ip_set.ko` 的
导入符号与本设备完全对得上。

真机验证（root shell）：

```sh
# 全部 18 个模块都已加载
for m in droidspaces_ip_set droidspaces_xt_set; do
    test -d "/sys/module/$m" && echo "$m OK"
done

# 基础 set 操作
ipset create dstest hash:ip
ipset add dstest 192.0.2.10
ipset test dstest 192.0.2.10
ipset list dstest
ipset destroy dstest

# 与 iptables 配合
ipset create nets hash:net
ipset add nets 198.51.100.0/24
iptables-legacy -A INPUT -m set --match-set nets src -j ACCEPT
iptables-legacy -L INPUT -n
```

## 构建与验证

模块与 `droidspaces_ns.ko` 使用同一个固定 DDK 镜像，单独输出目录：

```sh
python3 scripts/build-gki.py --module net515 5.15 -j2
python3 scripts/prepare-net515.py 5.15
python3 scripts/build-gki.py --module ipset515 5.15 -j2
python3 scripts/prepare-ipset515.py 5.15
```

`--module` 必须写在目标之前：`make` 参数用 `REMAINDER` 收集，写在目标之后会被当成
make 参数。

`prepare-net515.py` 在 DDK 容器内导出 `vmlinux` BTF、`.config`、
`llvm-nm -u` 导入表和内核符号表，然后要求：

- 模块 BTF 与 DDK 内核 BTF 的结构布局完全一致（`compare-btf.py` 无差异）；
- 模块的全部未定义符号都能在 DDK 内核符号表中解析。

打包时 `scripts/package-meizu21note.py` 再用真机 `vmlinux` BTF 与 `kallsyms`
复核：结构差异只允许 `net_device.l3mdev_ops`（厂商字段，与 `droidspaces_ns.ko`
的白名单相同），导入符号必须全部存在于设备；ipset 的类型模块允许从本模块组的
核心导出解析符号，其余导入同样必须在设备上存在。全部 `.ko`、三份审计报告
一起进入 ZIP，`kernel/SHA256SUMS` 覆盖每一个载荷。

本地单元测试（不需要内核或设备）：

```sh
python3 tests/module/test_net515_sources.py
python3 tests/module/test_ipset515_sources.py
python3 tests/module/test_meizu21note_loader.py
```

CI（`.github/workflows/build-android13-515.yml`）会构建并审计两个模块，
产物作为 `android13-5.15-abi-inputs` 上传。

## 仍需在真机上完成

以下验证需要 root shell（KernelSU），本轮未执行：

```sh
# 两个单元都已注册
cat /sys/module/droidspaces_net515/parameters/macvlan_registered
cat /sys/module/droidspaces_net515/parameters/ip6table_nat_registered

# Macvlan：先用 dummy 网卡验证 link kind 已注册（与具体 Wi-Fi/蜂窝驱动无关）
ip link add dummytest type dummy
ip link add link dummytest name mvtest type macvlan mode bridge
ip -d link show mvtest
ip link del mvtest
ip link del dummytest

# xt_addrtype：匹配已注册
iptables-legacy -t mangle -A PREROUTING -m addrtype --dst-type LOCAL -j ACCEPT
iptables-legacy -t mangle -L -n

# IPv6 NAT：表已注册且可编程
ip6tables-legacy -t nat -L -n
ip6tables-legacy -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
ip6tables-legacy -t nat -L -n

# Droidspaces 检查中的两项应变为可用
droidspaces check
```

开机加载结果见 `/data/adb/modules/droidspaces_lkm_meizu21note/status.txt`：
两个模块都注册时显示 `[已加载]`，只有 namespace 成功时显示 `[部分加载]`，
并给出 MACVLAN / IPv6 NAT / addrtype 的具体原因。

## 与第三方实现的交叉验证

[IPSET_LKM](https://github.com/TanakaLun/IPSET_LKM) v2.5 提供 android13-5.15 的
`ip6table_nat.ko` 与 `xt_addrtype.ko`（vermagic `5.15.202 SMP preempt mod_unload
modversions aarch64`）。逐项比对后，其未定义符号与本文两个单元使用的符号集合
一致，且全部能在目标设备 `/proc/kallsyms` 中解析。这独立验证了本扩展的依赖选择；
本仓库仍按项目惯例从固定的 5.15.202 源码构建并保留自己的审计链。

## 边界

- 两个 `CONFIG_NF_TABLES` 相关能力不在本分支范围：设备内核没有 nftables，
  也没有 `br_netfilter`，因此 ipset 的 `hash:netiface` 使用非 bridge 变体。
- ipset 模块组共 18 个 `.ko`，ZIP 体积因此增加约 5 MB；它们没有内核内守卫
  （上游文件零改动），由加载器的设备/BTF 门禁统一把关。
- IPv6 NAT 提供的是标准 ip6tables 表语义；不改变宿主防火墙策略，不预置规则。
- 结构与符号检查基于固定 DDK 与目标设备；厂商若改动 `net_device` 之外的结构，
  打包会被拒绝，需要重新审计。
- CPU 带宽（`CONFIG_CFS_BANDWIDTH`）与进程数限制（`CONFIG_CGROUP_PIDS`）是内核
  编译选项，会改变 `cfs_rq` / `task_group` 与 cgroup 子系统布局，LKM 无法补，
  保持为 Droidspaces 检查中的已知缺失项。
