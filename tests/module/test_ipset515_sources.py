#!/usr/bin/env python3
"""Check ipset provenance, module manifest, Makefile wiring and loader order."""
import hashlib
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
IPSET = ROOT / 'src/ipset515'
TARGETS = json.loads((ROOT / 'build/gki-targets.json').read_text())
MANIFEST = json.loads((IPSET / 'modules.json').read_text())
SOURCES = json.loads((IPSET / 'upstream/SOURCES.json').read_text())


class IpSetSourceTests(unittest.TestCase):
    def test_provenance_matches_pinned_ddk(self):
        self.assertEqual('sha256:' + TARGETS['5.15']['image'].split('@sha256:')[1],
                         SOURCES['ddk'])
        self.assertEqual('android13-5.15.202_r00', SOURCES['tag'])

    def test_sources_are_unmodified(self):
        upstream = IPSET / 'upstream'
        on_disk = {p.name for p in upstream.iterdir() if p.suffix in ('.c', '.h')}
        self.assertEqual(set(SOURCES['files']), on_disk)
        for name, digest in SOURCES['files'].items():
            self.assertEqual(digest, hashlib.sha256((upstream / name).read_bytes()).hexdigest(),
                             name)

    def test_every_module_keeps_upstream_entry_points(self):
        upstream = IPSET / 'upstream'
        for module in MANIFEST['modules']:
            with self.subTest(module=module['name']):
                for obj in module['objects']:
                    self.assertTrue((upstream / obj).is_file(), obj)
                entry = [o for o in module['objects']
                         if re.search(r'^module_init\(', (upstream / o).read_text(), re.M)]
                if module['name'] == MANIFEST['core']:
                    self.assertTrue(entry, 'core must own its module_init')
                else:
                    self.assertEqual(1, len(entry), f'{module["name"]} entry point')
                text = (upstream / module['objects'][0]).read_text()
                self.assertNotIn('droidspaces', text)

    def test_manifest_covers_upstream_files(self):
        used = {o for module in MANIFEST['modules'] for o in module['objects']}
        headers = {n for n in SOURCES['files'] if n.endswith('.h')}
        cfiles = {n for n in SOURCES['files'] if n.endswith('.c')}
        self.assertEqual(cfiles, used)
        self.assertEqual({'ip_set_bitmap_gen.h', 'ip_set_hash_gen.h'}, headers)

    def test_load_order_is_core_types_then_xt_set(self):
        order = MANIFEST['load_order']
        self.assertEqual(len(MANIFEST['modules']), len(order))
        self.assertEqual(MANIFEST['core'], order[0])
        self.assertEqual('droidspaces_xt_set', order[-1])
        self.assertEqual({m['name'] for m in MANIFEST['modules']}, set(order))

    def test_makefile_matches_manifest(self):
        makefile = (ROOT / 'Makefile').read_text()
        block = makefile.split('ifeq ($(TARGET),ipset515)', 1)[1].split('\nelse ', 1)[0]
        lines = block.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith('obj-m :='))
        objm = lines[start].split(':=', 1)[1]
        for ln in lines[start + 1:]:
            if not ln.startswith((' ', '\t')):
                break
            objm += ' ' + ln
        names = re.findall(r'([A-Za-z0-9_]+)\.o', objm)
        self.assertEqual(sorted(m['name'] for m in MANIFEST['modules']), sorted(names))
        for module in MANIFEST['modules']:
            line = next(ln for ln in block.splitlines()
                        if ln.strip().startswith(module['name'] + '-y :='))
            objects = re.findall(r'\$\(IP515\)/([A-Za-z0-9_.]+)\.o', line)
            self.assertEqual([o[:-2] for o in module['objects']], objects, module['name'])

    def test_loader_uses_manifest_order(self):
        loader = (ROOT / 'kernelsu-meizu21note/common.sh').read_text()
        listed = re.search(r"DS_IPSET_MODULES='([^']+)'", loader).group(1).split()
        self.assertEqual(MANIFEST['load_order'], listed)
        self.assertIn('DS_MODULE_ROOT', loader)

    def test_origin_records_no_adaptations(self):
        origin = (IPSET / 'ORIGIN').read_text()
        self.assertIn('Adaptations: none', origin)


if __name__ == '__main__':
    unittest.main()
