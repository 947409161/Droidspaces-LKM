#!/usr/bin/env python3
"""Audit local Meizu 21 Note ABI evidence and package the GitHub-built KSU module."""
import argparse
import hashlib
import importlib.util
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out/gki/android13-5.15'
RELEASE = '5.15.119-android13-8-g6ff5097ee32a-ab1764665171'
BTF_SHA = 'ceb62a44dbeb782434c5956c71c03b635129017399cedbf2a1e6cc072998081c'
spec = importlib.util.spec_from_file_location('compare_btf', ROOT/'scripts/abi/compare-btf.py')
compare_btf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_btf)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit_device():
    device_btf = ROOT/'vmlinux'
    symbols_path = ROOT/'kallsyms'
    config_path = ROOT/'kernel.config'
    for path in (device_btf, symbols_path, config_path):
        require(path.is_file(), f'missing required local device input: {path.name}')
    require(sha(device_btf.read_bytes()) == BTF_SHA, 'device BTF fingerprint differs')
    require('CONFIG_ARM64_4K_PAGES=y' in config_path.read_text().splitlines(),
            'device is not configured for 4K pages')
    require('CONFIG_CFI_CLANG=y' in config_path.read_text().splitlines(),
            'device CFI configuration differs from the audited target')

    module = compare_btf.BTF(OUT/'module.btf')
    baseline = compare_btf.BTF(OUT/'kernel.btf')
    device = compare_btf.BTF(device_btf)
    layouts = compare_btf.compare(OUT/'module.btf', device_btf)
    expected_changed = {
        'perf_event': {'group_generation'},
        'netns_ipv4': {'sysctl_tcp_l3mdev_accept', 'sysctl_udp_l3mdev_accept',
                       'sysctl_raw_l3mdev_accept'},
        'net_device': {'l3mdev_ops'},
        'fuse_conn': {'no_poll', 'big_writes', 'dont_mask', 'no_flock',
                      'no_fallocate', 'no_rename2', 'auto_inval_data',
                      'explicit_inval_data', 'do_readdirplus', 'readdirplus_auto',
                      'async_dio', 'no_lseek', 'posix_acl', 'default_permissions', 'init_security',
                      'allow_other', 'no_copy_file_range', 'destroy', 'delete_stale',
                      'no_control', 'no_force_umount', 'auto_submounts', 'passthrough',
                      'sync_fs', 'no_daemon'},
    }
    require(set(layouts['differences']) == set(expected_changed),
            f'unexpected target structure differences: {set(layouts["differences"])}')
    for name, diff in layouts['differences'].items():
        require(diff['size'][0] == diff['size'][1], f'{name} size changed')
        require(set(diff['changed']) == expected_changed[name], f'unexpected {name} field layout')
        require(not diff['device_only'] or name == 'fuse_conn', f'unexpected {name} target-only fields')
    fuse_used = set(re.findall(r'fc->(\w+)', (ROOT/'src/port515/fuse.c').read_text()))
    require(not (fuse_used & expected_changed['fuse_conn']),
            'module accesses a shifted fuse_conn flag')

    imports = {line.split()[-1] for line in (OUT/'imports.txt').read_text().splitlines() if line.strip()}
    symbols = {line.split()[2] for line in symbols_path.read_text().splitlines()
               if len(line.split()) >= 3}
    require(imports <= symbols, f'unresolved device symbols: {sorted(imports-symbols)}')
    device_functions, baseline_functions = device.functions(), baseline.functions()
    require('dup_fd' in device_functions and 'dup_fd' in baseline_functions,
            'dup_fd BTF prototype missing')
    actual = device_functions['dup_fd']
    require(actual[0] == 'func' and len(actual[2]) == 3 and
            actual[2][1] == ['int', 4, 32] and actual[2][2][0] == 'ptr' and
            actual[2][2][1] == ['int', 4, 16777248],
            f'unexpected device dup_fd prototype: {actual}')
    comparable = imports & baseline_functions.keys() & device_functions.keys()
    prototype_differences = {name for name in comparable
                             if baseline_functions[name] != device_functions[name]}
    require(prototype_differences == {'dup_fd'},
            f'unexpected imported function prototype differences: {sorted(prototype_differences)}')
    diff = layouts
    return dict(device_release=RELEASE, device_btf_sha256=BTF_SHA,
                module_sha256=sha((OUT/'droidspaces_ns.ko').read_bytes()),
                imports=len(imports), resolved_imports=len(imports),
                matching_aggregates=layouts['matching_aggregates'],
                expected_layout_differences=diff['differences'],
                device_dup_fd=actual, baseline_dup_fd=baseline_functions['dup_fd'],
                prototype_differences=sorted(prototype_differences),
                fuse_fields_accessed=sorted(fuse_used))


NET515_OUT = ROOT / 'out/gki/android13-5.15-net515'
IPSET_OUT = ROOT / 'out/gki/android13-5.15-ipset515'
IPSET_MANIFEST = json.loads((ROOT/'src/ipset515/modules.json').read_text())


def audit_net515():
    device_btf = ROOT/'vmlinux'
    symbols_path = ROOT/'kallsyms'
    for path in (device_btf, symbols_path):
        require(path.is_file(), f'missing required local device input: {path.name}')
    require(sha(device_btf.read_bytes()) == BTF_SHA, 'device BTF fingerprint differs')

    ko = (NET515_OUT/'droidspaces_net515.ko').read_bytes()
    require(ko[:6] == b'\x7fELF\x02\x01', 'net515 module is not ELF64 little-endian')
    require(b'parmtype=macvlan_registered:bool' in ko and
            b'parmtype=ip6table_nat_registered:bool' in ko and
            b'parmtype=xt_addrtype_registered:bool' in ko,
            'net515 module is missing the registration parameters')
    build = json.loads((NET515_OUT/'build.json').read_text())
    require(build['module_sha256'] == sha(ko), 'net515 module differs from recorded GitHub build')
    require(build.get('module') == 'net515', 'unexpected net515 GitHub build module')
    audit = json.loads((NET515_OUT/'net515.audit.json').read_text())
    require(audit['module_sha256'] == sha(ko), 'net515 audit belongs to another module')

    layouts = compare_btf.compare(NET515_OUT/'module.btf', device_btf)
    require(set(layouts['differences']) <= {'net_device'},
            f'unexpected net515 target structure differences: {set(layouts["differences"])}')
    for name, diff in layouts['differences'].items():
        require(diff['size'][0] == diff['size'][1], f'{name} size changed')
        require(set(diff['changed']) == {'l3mdev_ops'}, f'unexpected {name} field layout')
        require(not diff['device_only'], f'unexpected {name} target-only fields')

    imports = {line.split()[-1] for line in (NET515_OUT/'imports.txt').read_text().splitlines() if line.strip()}
    symbols = {line.split()[2] for line in symbols_path.read_text().splitlines()
               if len(line.split()) >= 3}
    require(imports <= symbols, f'unresolved device symbols: {sorted(imports-symbols)}')
    return dict(device_release=RELEASE, device_btf_sha256=BTF_SHA,
                module_sha256=sha(ko), imports=len(imports),
                resolved_imports=len(imports),
                matching_aggregates=layouts['matching_aggregates'],
                expected_layout_differences=layouts['differences'])


def audit_ipset():
    device_btf = ROOT/'vmlinux'
    symbols_path = ROOT/'kallsyms'
    for path in (device_btf, symbols_path):
        require(path.is_file(), f'missing required local device input: {path.name}')
    require(sha(device_btf.read_bytes()) == BTF_SHA, 'device BTF fingerprint differs')
    audit = json.loads((IPSET_OUT/'ipset515.audit.json').read_text())
    build = json.loads((IPSET_OUT/'build.json').read_text())
    require(build.get('module') == 'ipset515', 'unexpected ipset GitHub build module')
    require({m['name'] for m in IPSET_MANIFEST['modules']} == set(audit['modules']),
            'ipset audit does not cover the manifest')
    provided = set(audit['core_exports'])
    symbols = {line.split()[2] for line in symbols_path.read_text().splitlines()
               if len(line.split()) >= 3}
    modules = {}
    for module in IPSET_MANIFEST['modules']:
        name = module['name']
        ko = IPSET_OUT/(name + '.ko')
        require(ko.is_file(), f'missing ipset module {name}')
        digest = sha(ko.read_bytes())
        require(audit['modules'][name]['sha256'] == digest,
                f'{name} differs from the audited build')
        require(build['modules'].get(name) == digest,
                f'{name} differs from the recorded GitHub build')
        layouts = compare_btf.compare(IPSET_OUT/(name + '.btf'), device_btf)
        require(set(layouts['differences']) <= {'net_device'},
                f'{name}: unexpected target structure differences: {set(layouts["differences"])}')
        for struct, diff in layouts['differences'].items():
            require(diff['size'][0] == diff['size'][1], f'{name}: {struct} size changed')
            require(set(diff['changed']) == {'l3mdev_ops'},
                    f'{name}: unexpected {struct} field layout')
            require(not diff['device_only'], f'{name}: unexpected {struct} target-only fields')
        imports = {line.split()[-1] for line in
                   (IPSET_OUT/(name + '.imports.txt')).read_text().splitlines() if line.strip()}
        unresolved = (imports - provided) - symbols
        require(not unresolved, f'{name}: unresolved device symbols: {sorted(unresolved)}')
        modules[name] = dict(module_sha256=digest, imports=len(imports),
                             internal_imports=len(imports & provided),
                             matching_aggregates=layouts['matching_aggregates'])
    return dict(device_release=RELEASE, device_btf_sha256=BTF_SHA,
                core_exports=sorted(provided), modules=modules)


def package(output):
    report = audit_device()
    net515_report = audit_net515()
    ipset_report = audit_ipset()
    ko = (OUT/'droidspaces_ns.ko').read_bytes()
    net515_ko = (NET515_OUT/'droidspaces_net515.ko').read_bytes()
    require(ko[:6] == b'\x7fELF\x02\x01', 'module is not ELF64 little-endian')
    require(b'parmtype=gki:bool' in ko and b'parmtype=activate:bool' in ko,
            'module is missing the gki / activate parameters')
    build = json.loads((OUT/'build.json').read_text())
    require(build['module_sha256'] == sha(ko), 'module differs from recorded GitHub build')
    require(build['target']['kmi'] == 'android13-5.15', 'unexpected GitHub build target')
    files = {p.name: p.read_bytes() for p in
             (ROOT/'kernelsu-meizu21note').iterdir() if p.is_file()}
    files['kernel/droidspaces_ns.ko'] = ko
    files['kernel/droidspaces_net515.ko'] = net515_ko
    files['kernel/target.json'] = (json.dumps(report, indent=2, ensure_ascii=False)+'\n').encode()
    files['kernel/net515-target.json'] = (json.dumps(net515_report, indent=2, ensure_ascii=False)+'\n').encode()
    for module in IPSET_MANIFEST['modules']:
        files['kernel/' + module['name'] + '.ko'] = (IPSET_OUT/(module['name'] + '.ko')).read_bytes()
    files['kernel/ipset-target.json'] = (json.dumps(ipset_report, indent=2, ensure_ascii=False)+'\n').encode()
    files['kernel/SHA256SUMS'] = ''.join(
        f'{sha(data)}  {name.removeprefix("kernel/")}\n'
        for name, data in sorted(files.items()) if name.startswith('kernel/')).encode()
    files['LICENSE'] = (ROOT/'LICENSE').read_bytes()
    files['README.md'] = (ROOT/'README.md').read_bytes()
    files['SOURCE.txt'] = (
        'Target: Meizu 21 Note, ' + RELEASE + '\n'
        'The installer checks the full release string and the device BTF SHA-256 before loading.\n'
        'ABI comparison evidence is in kernel/target.json and kernel/net515-target.json.\n'
        'droidspaces_ns.ko supplies PID / IPC namespaces; droidspaces_net515.ko supplies\n'
        'the MACVLAN link kind, the IPv6 xtables nat table and xt_addrtype;\n'
        'droidspaces_ip_set*.ko and droidspaces_xt_set.ko supply ipset.\n'
    ).encode()
    files['SHA256SUMS'] = ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(files.items())
                                 if name.startswith('kernel/')).encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output/'Droidspaces-LKM-KernelSU-Meizu21Note-5.15.119.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 10, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    (output/'SHA256SUMS').write_text(f'{sha(archive.read_bytes())}  {archive.name}\n')
    print(f'{archive}\n{output/"SHA256SUMS"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'out/meizu21note-5.15.119')
    package(parser.parse_args().output)
