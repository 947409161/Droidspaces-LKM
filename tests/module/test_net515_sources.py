#!/usr/bin/env python3
"""Check the net515 unit wiring, upstream provenance and boot-loader agreement."""
import json
import re
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
NET515 = ROOT / 'src/net515'
TARGETS = json.loads((ROOT / 'build/gki-targets.json').read_text())
UNITS = {'macvlan': 'drivers/net/macvlan.c',
         'ip6table_nat': 'net/ipv6/netfilter/ip6table_nat.c',
         'xt_addrtype': 'net/netfilter/xt_addrtype.c'}


class Net515SourceTests(unittest.TestCase):
    def test_provenance_matches_pinned_ddk(self):
        sources = json.loads((NET515 / 'upstream/SOURCES.json').read_text())
        self.assertEqual('sha256:' + TARGETS['5.15']['image'].split('@sha256:')[1],
                         sources['ddk'])
        self.assertEqual(set(UNITS.values()), set(sources['files']))
        for name, digest in sources['files'].items():
            self.assertRegex(digest, r'^[0-9a-f]{64}$', name)

    def test_units_have_one_entry_point_pair(self):
        for unit, upstream in UNITS.items():
            with self.subTest(unit=unit):
                text = (NET515 / 'upstream' / Path(upstream).name).read_text()
                self.assertEqual(1, text.count(f'ds_nf_init_net515_{unit}'))
                self.assertEqual(1, text.count(f'ds_nf_exit_net515_{unit}'))
                self.assertNotRegex(text, r'^module_init\(')
                self.assertNotRegex(text, r'^module_exit\(')
                self.assertIn('SPDX-License-Identifier: GPL-2.0', text)

    def test_loader_declares_both_units(self):
        main = (NET515 / 'main.c').read_text()
        for unit in UNITS:
            self.assertIn(f'ds_nf_init_net515_{unit}', main)
            self.assertIn(f'ds_nf_exit_net515_{unit}', main)
        self.assertEqual(1, len(re.findall(r'^module_init\(', main, re.M)))
        self.assertEqual(1, len(re.findall(r'^module_exit\(', main, re.M)))

    def test_registration_parameters_are_reported(self):
        main = (NET515 / 'main.c').read_text()
        for unit in UNITS:
            self.assertIn(f'module_param({unit}_registered, bool, 0444)', main)
        loader = (ROOT / 'kernelsu-meizu21note/common.sh').read_text()
        for unit in UNITS:
            self.assertIn(f'/parameters/{unit}_registered', loader)

    def test_kernel_guard_matches_the_loader(self):
        main = (NET515 / 'main.c').read_text()
        loader = (ROOT / 'kernelsu-meizu21note/common.sh').read_text()
        release = re.search(r'DS_NET515_DEVICE_RELEASE "([^"]+)"', main).group(1)
        self.assertIn(f"DS_RELEASE='{release}'", loader)
        self.assertIn('of_machine_is_compatible("qcom,kalama")', main)

    def test_makefile_builds_both_objects(self):
        makefile = (ROOT / 'Makefile').read_text()
        block = makefile.split('ifeq ($(TARGET),net515)', 1)[1].split('else', 1)[0]
        self.assertIn('src/net515/main.o', block)
        for unit, upstream in UNITS.items():
            self.assertIn(f'src/net515/upstream/{Path(upstream).stem}.o', block)
        self.assertIn('-DCONFIG_MACVLAN=1', block)

    def test_no_nftables_units_are_claimed(self):
        origin = (NET515 / 'ORIGIN').read_text()
        self.assertIn('CONFIG_NF_TABLES is not set', origin)

    def test_module_option_must_precede_target(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/build-gki.py'), '5.15',
             '--module', 'net515', '-j2'],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--module must precede the target', result.stderr)


if __name__ == '__main__':
    unittest.main()
