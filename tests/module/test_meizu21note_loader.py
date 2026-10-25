#!/usr/bin/env python3
"""Exercise the Meizu 21 Note boot loader without loading anything into the kernel."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = '5.15.119-android13-8-g6ff5097ee32a-ab1764665171'
BTF_SHA = 'ceb62a44dbeb782434c5956c71c03b635129017399cedbf2a1e6cc072998081c'
IPSET_MODULES = json.loads((ROOT / 'src/ipset515/modules.json').read_text())['load_order']


class MeizuLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / 'module'
        shutil.copytree(ROOT / 'kernelsu-meizu21note', self.module)
        kernel = self.module / 'kernel'
        kernel.mkdir()
        self.payloads = ['droidspaces_ns.ko', 'droidspaces_net515.ko',
                         'droidspaces_devtmpfs515.ko'] + [
            name + '.ko' for name in IPSET_MODULES]
        for name in self.payloads:
            (kernel / name).write_bytes(f'fake {name}'.encode())
        self.write_sums()
        self.btf = self.root / 'vmlinux.btf'
        self.btf.write_bytes(b'mocked device BTF')
        self.ksud = self.root / 'ksud'
        self.ksud.write_text('''#!/bin/sh
if [ "$1" = module ]; then
    printf '%s\\n' "$6" > "$FAKE_ROOT/description"
    exit 0
fi
[ "$1" = insmod ] || exit 2
ko=$2
printf '%s\\n' "$*" >> "$FAKE_ROOT/insmod-calls"
case "$ko:$FAKE_MODE" in
    */droidspaces_ns.ko:error|*/droidspaces_net515.ko:net515_error) exit 17 ;;
    */droidspaces_devtmpfs515.ko:devtmpfs_error) exit 19 ;;
esac
case "$ko" in
    */droidspaces_ns.ko)
        mkdir -p "$FAKE_NS/sys/parameters" "$FAKE_ROOT/procns"
        printf 'Y\\n' > "$FAKE_NS/sys/parameters/activate"
        touch "$FAKE_ROOT/procns/pid" "$FAKE_ROOT/procns/pid_for_children" \
              "$FAKE_ROOT/procns/ipc"
        ;;
    */droidspaces_net515.ko)
        [ "$FAKE_MODE" = silent_net515 ] || {
            mkdir -p "$FAKE_NET/sys/parameters"
            printf 'Y\\n' > "$FAKE_NET/sys/parameters/macvlan_registered"
            printf 'Y\\n' > "$FAKE_NET/sys/parameters/ip6table_nat_registered"
            printf 'Y\\n' > "$FAKE_NET/sys/parameters/xt_addrtype_registered"
        }
        ;;
    */droidspaces_ip_set*.ko|*/droidspaces_xt_set.ko)
        name=$(basename "$ko" .ko)
        case "$FAKE_MODE:$name" in
            ipset_error:droidspaces_ip_set_hash_net) exit 18 ;;
            silent_ipset:*) exit 0 ;;
        esac
        mkdir -p "$FAKE_ROOT/modules/$name"
        ;;
    */droidspaces_devtmpfs515.ko)
        mkdir -p "$FAKE_DEV/sys/parameters"
        if [ "$FAKE_MODE" = devtmpfs_inactive ]; then
            printf 'N\\n' > "$FAKE_DEV/sys/parameters/ready"
            printf '3\\n' > "$FAKE_DEV/sys/parameters/errors"
        else
            printf 'Y\\n' > "$FAKE_DEV/sys/parameters/ready"
            printf '0\\n' > "$FAKE_DEV/sys/parameters/errors"
        fi
        ;;
esac
exit 0
''')
        self.ksud.chmod(0o755)

    def write_sums(self):
        kernel = self.module / 'kernel'
        lines = [f'{hashlib.sha256((kernel / name).read_bytes()).hexdigest()}  {name}\n'
                 for name in self.payloads if (kernel / name).exists()]
        (kernel / 'SHA256SUMS').write_text(''.join(lines))

    def run_loader(self, mode='success', release=RELEASE):
        script = '''
MODDIR=$FAKE_ROOT/module
sha256sum() {
    if [ "$1" = "$DS_KERNEL_BTF" ]; then
        printf '%s  %s\\n' "$DS_BTF_SHA256" "$1"
    else
        command sha256sum "$@"
    fi
}
. "$MODDIR/common.sh"
DS_KSUD=$FAKE_ROOT/ksud
DS_KERNEL_BTF=$FAKE_ROOT/vmlinux.btf
DS_MODULE_SYS=$FAKE_NS/sys
DS_NET515_SYS=$FAKE_NET/sys
DS_PROC_NS=$FAKE_ROOT/procns
DS_MODULE_ROOT=$FAKE_ROOT/modules
DS_DEVTMPFS_SYS=$FAKE_DEV/sys
uname() {
    case "$1" in
        -m) printf 'aarch64\\n';;
        -r) printf '%s\\n' "$FAKE_RELEASE";;
    esac
}
ds_load
'''
        shell = shlex.split(os.environ.get('LOADER_TEST_SHELL', 'sh'))
        result = subprocess.run([*shell, '-c', script], text=True, capture_output=True,
                                env={**os.environ, 'FAKE_ROOT': str(self.root),
                                     'FAKE_NS': str(self.root / 'ns'),
                                     'FAKE_NET': str(self.root / 'net'),
                                     'FAKE_DEV': str(self.root / 'dev'),
                                     'FAKE_MODE': mode, 'FAKE_RELEASE': release})
        self.status = (self.module / 'status.txt').read_text()
        return result

    def insmod_calls(self):
        path = self.root / 'insmod-calls'
        return path.read_text().splitlines() if path.exists() else []

    def test_both_units_load(self):
        result = self.run_loader()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('[已加载]', self.status)
        self.assertIn('MACVLAN', self.status)
        calls = self.insmod_calls()
        self.assertEqual(len(calls), 3 + len(IPSET_MODULES))
        self.assertIn('droidspaces_ns.ko gki=1 activate=1', calls[0])
        self.assertIn('droidspaces_net515.ko', calls[1])
        loaded = [c.split('/kernel/')[-1].split('.ko')[0] for c in calls[2:]]
        self.assertEqual(loaded[:len(IPSET_MODULES)], IPSET_MODULES)
        self.assertEqual(loaded[0], 'droidspaces_ip_set')
        self.assertEqual(loaded[len(IPSET_MODULES) - 1], 'droidspaces_xt_set')
        self.assertEqual(loaded[-1], 'droidspaces_devtmpfs515')
        self.assertEqual(self.status, (self.root / 'description').read_text())

    def test_repeat_is_idempotent(self):
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertEqual(len(self.insmod_calls()), 3 + len(IPSET_MODULES))
        self.assertIn('[已加载]', self.status)

    def test_net515_failure_is_partial(self):
        result = self.run_loader(mode='silent_net515')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)
        self.assertIn('未注册', self.status)

    def test_net515_insmod_error_is_partial(self):
        result = self.run_loader(mode='net515_error')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)

    def test_missing_net515_payload_rejected(self):
        (self.module / 'kernel/droidspaces_net515.ko').unlink()
        self.write_sums()
        result = self.run_loader()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-256', self.status)
        self.assertEqual(self.insmod_calls(), [])

    def test_corrupt_net515_payload_rejected(self):
        (self.module / 'kernel/droidspaces_net515.ko').write_bytes(b'corrupt')
        result = self.run_loader()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-256', self.status)
        self.assertEqual(self.insmod_calls(), [])

    def test_ipset_ready_needs_every_module(self):
        result = self.run_loader(mode='silent_ipset')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)
        self.assertIn('ipset 模块加载后未就绪', self.status)

    def test_ipset_module_error_is_partial(self):
        result = self.run_loader(mode='ipset_error')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)
        self.assertIn('droidspaces_ip_set_hash_net', self.status)

    def test_devtmpfs_failure_is_partial(self):
        result = self.run_loader(mode='devtmpfs_inactive')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)
        self.assertIn('ready/errors', self.status)

    def test_devtmpfs_insmod_error_is_partial(self):
        result = self.run_loader(mode='devtmpfs_error')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[部分加载]', self.status)
        self.assertIn('devtmpfs 加载返回 19', self.status)

    def test_wrong_kernel_rejected(self):
        result = self.run_loader(release='5.15.100-android13-0-g123')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[不兼容]', self.status)
        self.assertEqual(self.insmod_calls(), [])


if __name__ == '__main__':
    unittest.main()
