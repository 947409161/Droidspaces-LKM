#!/usr/bin/env python3
"""Exercise boot-loader decisions without loading anything into the host kernel."""
import hashlib
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = '6.12.69-android16-6-g242e1a07f878-ab15865446-4k'


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / 'module'
        shutil.copytree(ROOT / 'kernelsu', self.module)
        kernel = self.module / 'kernel'
        kernel.mkdir()
        data = b'fake kernel payload, never passed to the real insmod'
        (kernel / 'droidspaces_ns.ko').write_bytes(data)
        (kernel / 'SHA256SUMS').write_text(f'{hashlib.sha256(data).hexdigest()}  droidspaces_ns.ko\n')
        (self.root / 'compatible').write_bytes(b'qcom,canoe-mtp\0qcom,canoe\0')
        self.ksud = self.root / 'ksud'
        self.ksud.write_text('''#!/bin/sh
if [ "$1" = module ]; then
    [ "$FAKE_CONFIG" != fail ] || exit 1
    printf '%s\\n' "$6" > "$FAKE_ROOT/description"
    exit 0
fi
[ "$1" = insmod ] || exit 2
printf '%s\\n' "$*" >> "$FAKE_ROOT/insmod-calls"
[ "$FAKE_MODE" != error ] || exit 17
[ "$FAKE_MODE" != incomplete ] || exit 0
mkdir -p "$FAKE_ROOT/sys/parameters" "$FAKE_ROOT/ns"
printf 'Y\\n' > "$FAKE_ROOT/sys/parameters/activate"
touch "$FAKE_ROOT/ns/pid" "$FAKE_ROOT/ns/pid_for_children" "$FAKE_ROOT/ns/ipc"
''')
        self.ksud.chmod(0o755)

    def run_loader(self, mode='success', release=RELEASE, config='ok', command='ds_load'):
        script = '''
MODDIR=$FAKE_ROOT/module
. "$MODDIR/common.sh"
DS_KSUD=$FAKE_ROOT/ksud
DS_COMPATIBLE=$FAKE_ROOT/compatible
DS_MODULE_SYS=$FAKE_ROOT/sys
DS_PROC_NS=$FAKE_ROOT/ns
uname() {
    case "$1" in
        -m) printf 'aarch64\\n';;
        -r) printf '%s\\n' "$FAKE_RELEASE";;
    esac
}
''' + command
        shell = shlex.split(os.environ.get('LOADER_TEST_SHELL', 'sh'))
        result = subprocess.run([*shell, '-c', script], text=True, capture_output=True,
                                env={**os.environ, 'FAKE_ROOT': str(self.root),
                                     'FAKE_MODE': mode, 'FAKE_RELEASE': release, 'FAKE_CONFIG': config})
        self.status = (self.module / 'status.txt').read_text()
        return result

    def test_load_and_verify_activation(self):
        r = self.run_loader()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('[已加载]', self.status)
        self.assertIn('activate=1', (self.root / 'insmod-calls').read_text())
        self.assertEqual(self.status, (self.root / 'description').read_text())
        self.assertIn('description=[待加载]', (self.module / 'module.prop').read_text())

    def test_repeat_does_not_load_twice(self):
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertEqual(len((self.root / 'insmod-calls').read_text().splitlines()), 1)
        self.assertIn('本次开机已加载', self.status)

    def test_wrong_kernel_rejected(self):
        self.assertNotEqual(self.run_loader(release='6.12.other').returncode, 0)
        self.assertIn('[不支持]', self.status)
        self.assertFalse((self.root / 'insmod-calls').exists())

    def test_wrong_device_rejected(self):
        (self.root / 'compatible').write_bytes(b'qcom,other\0')
        self.assertNotEqual(self.run_loader().returncode, 0)
        self.assertFalse((self.root / 'insmod-calls').exists())

    def test_corrupt_payload_rejected(self):
        (self.module / 'kernel/droidspaces_ns.ko').write_bytes(b'corrupt')
        self.assertNotEqual(self.run_loader().returncode, 0)
        self.assertIn('SHA-256', self.status)
        self.assertFalse((self.root / 'insmod-calls').exists())

    def test_insmod_failure_visible(self):
        self.assertNotEqual(self.run_loader(mode='error').returncode, 0)
        self.assertIn('返回 17', self.status)

    def test_success_exit_without_activation_is_failure(self):
        self.assertNotEqual(self.run_loader(mode='incomplete').returncode, 0)
        self.assertIn('检查未通过', self.status)

    def test_inactive_existing_module_is_not_reloaded(self):
        (self.root / 'sys/parameters').mkdir(parents=True)
        (self.root / 'sys/parameters/activate').write_text('N\n')
        self.assertNotEqual(self.run_loader().returncode, 0)
        self.assertIn('未激活', self.status)
        self.assertFalse((self.root / 'insmod-calls').exists())

    def test_missing_loader_uses_visible_fallback(self):
        self.ksud.unlink()
        self.assertNotEqual(self.run_loader().returncode, 0)
        self.assertIn('找不到', self.status)
        self.assertIn('description=[加载失败]', (self.module / 'module.prop').read_text())

    def test_fallback_and_boot_reset(self):
        self.assertEqual(self.run_loader(config='fail').returncode, 0)
        self.assertIn('description=[已加载]', (self.module / 'module.prop').read_text())
        self.assertEqual(self.run_loader(config='fail', command="ds_status '[待加载] 本次开机尚未加载'").returncode, 0)
        self.assertIn('description=[待加载]', (self.module / 'module.prop').read_text())
        self.assertEqual((self.module / 'module.prop').read_text().count('description='), 1)


if __name__ == '__main__':
    unittest.main()
