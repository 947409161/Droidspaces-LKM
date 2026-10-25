#!/usr/bin/env python3
"""Check the 5.15 devtmpfs port: guards, symbol resolution, wiring and loader."""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / 'src/devtmpfs515'
RELEASE = '5.15.119-android13-8-g6ff5097ee32a-ab1764665171'
RESOLVED = ['device_get_devnode', 'notify_change', 'kern_path_locked',
            'reconfigure_single', 'set_fs_root', 'set_fs_pwd', 'devices_kset']


class Devtmpfs515SourceTests(unittest.TestCase):
    def test_guard_matches_the_loader(self):
        main = (DEV / 'main.c').read_text()
        self.assertIn(f'#define DS_DEVICE_RELEASE "{RELEASE}"', main)
        self.assertIn('of_machine_is_compatible("qcom,kalama")', main)
        self.assertIn(f"DS_RELEASE='{RELEASE}'",
                      (ROOT / 'kernelsu-meizu21note/common.sh').read_text())

    def test_unexported_symbols_are_resolved_not_linked(self):
        port = (DEV / 'port.h').read_text()
        main = (DEV / 'main.c').read_text()
        core = (DEV / 'devtmpfs.c').read_text()
        for symbol in RESOLVED:
            with self.subTest(symbol=symbol):
                self.assertIn(f'ds_{symbol}', port)
                self.assertIn(f'DS_RESOLVE', main)
                self.assertIn(symbol, main)
                # The call sites must go through the pointer, not the symbol.
                self.assertNotRegex(core, r'(?<!ds_)\b' + symbol + r'\(',
                                    f'{symbol} must only be called via ds_{symbol}')
        self.assertIn('DS_RESOLVE(fs_context_init, shmem_init_fs_context)', main)
        self.assertIn('DS_RESOLVE(fs_context_init, ramfs_init_fs_context)', main)

    def test_vfs_calls_use_the_515_idmap_argument(self):
        core = (DEV / 'devtmpfs.c').read_text()
        self.assertNotIn('nop_mnt_idmap', core)
        for call in ('vfs_mkdir', 'vfs_mknod', 'vfs_rmdir', 'vfs_unlink'):
            self.assertIn(f'{call}(&init_user_ns', core)
        self.assertIn('ds_notify_change(&init_user_ns', core)

    def test_block_class_is_not_referenced(self):
        core = (DEV / 'devtmpfs.c').read_text()
        self.assertNotIn('block_class', core)
        self.assertIn('dev->class->name', core)

    def test_module_metadata_and_vfs_namespace(self):
        main = (DEV / 'main.c').read_text()
        self.assertEqual(1, len(re.findall(r'^module_init\(', main, re.M)))
        self.assertIn('MODULE_IMPORT_NS(ANDROID_GKI_VFS_EXPORT_ONLY)', main)
        self.assertIn('module_param(ready, bool, 0400)', main)
        self.assertIn('module_param(errors, uint, 0400)', main)

    def test_hooks_replace_device_lifecycle_only(self):
        hooks = (DEV / 'hooks.c').read_text()
        self.assertEqual(1, hooks.count('"device_add"'))
        self.assertEqual(1, hooks.count('"device_del"'))
        self.assertIn('aarch64_insn_patch_text_nosync', hooks)
        self.assertIn('stop_machine(install_stopped', hooks)

    def test_makefile_and_build_manifest(self):
        makefile = (ROOT / 'Makefile').read_text()
        block = makefile.split('ifeq ($(TARGET),devtmpfs515)', 1)[1].split('\nelse ', 1)[0]
        for obj in ('main', 'devtmpfs', 'hooks', 'original'):
            self.assertIn(f'src/devtmpfs515/{obj}.o', block)
        self.assertIn('vendor/kallrecon', block)
        modules = (ROOT / 'scripts/build-gki.py').read_text()
        self.assertIn("'devtmpfs515'", modules)
        self.assertIn("droidspaces_devtmpfs515.ko", modules)

    def test_loader_requires_and_checks_the_module(self):
        loader = (ROOT / 'kernelsu-meizu21note/common.sh').read_text()
        self.assertIn('DS_DEVTMPFS_SYS=/sys/module/droidspaces_devtmpfs515', loader)
        self.assertIn('kernel/droidspaces_devtmpfs515.ko" ] || return 1', loader)
        self.assertIn('parameters/ready', loader)
        self.assertIn('parameters/errors', loader)
        self.assertIn('ds_devtmpfs_load', loader)

    def test_package_requires_the_audit(self):
        package = (ROOT / 'scripts/package-meizu21note.py').read_text()
        self.assertIn('def audit_devtmpfs()', package)
        self.assertIn('droidspaces_devtmpfs515.ko', package)
        self.assertIn('parmtype=ready:bool', package)


if __name__ == '__main__':
    unittest.main()
