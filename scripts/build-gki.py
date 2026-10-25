#!/usr/bin/env python3
"""Build one independent GKI module using its pinned DDK image."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / 'build/gki-targets.json').read_text())
MODULES = {
    'namespace': {'target': 'namespace', 'ko': 'droidspaces_ns.ko', 'suffix': '',
                  'extra_sources': ()},
    'net515': {'target': 'net515', 'ko': 'droidspaces_net515.ko', 'suffix': '-net515',
               'extra_sources': ('src/net515',)},
    'ipset515': {'target': 'ipset515', 'ko': 'droidspaces_ip_set.ko', 'suffix': '-ipset515',
                 'extra_sources': ('src/ipset515',)},
}


def source_hashes(target, extra_sources=()):
    paths = [ROOT/'Makefile', ROOT/'src/gki-target.h']
    paths += [p for directory in (ROOT/target['source'], ROOT/'vendor/kallrecon',
                                  *(ROOT/name for name in extra_sources))
              for p in directory.rglob('*') if p.is_file()
              and not {'.git', '.DS_Store', '__pycache__'}.intersection(p.parts)]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=TARGETS)
    parser.add_argument('--module', choices=MODULES, default='namespace')
    parser.add_argument('make_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if '--module' in args.make_args:
        parser.error('--module must precede the target, e.g. --module net515 5.15 -j2')
    target = TARGETS[args.target]
    module = MODULES[args.module]
    source = ROOT / target['source']
    if not (source / 'main.c').is_file():
        parser.error(f'missing independent source set: {source}')
    for name in module['extra_sources']:
        if not (ROOT / name).is_dir():
            parser.error(f'missing independent source set: {ROOT / name}')
    out = ROOT/'out/gki'/(target['kmi'] + module['suffix'])
    cmd = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
           '-v', f'{ROOT}:/module', '-w', '/module', target['image'],
           'make', f'TARGET={module["target"]}', f'PORT_DIR={target["source"]}',
           f'GKI_ANDROID={target["kmi"].split("-")[0]}', f'GKI_VERSION={args.target}',
           f'OUT=/module/out/gki/{target["kmi"] + module["suffix"]}', *args.make_args]
    record = out/'build.json'
    record.unlink(missing_ok=True)
    before = source_hashes(target, module['extra_sources'])
    subprocess.run(cmd, check=True)
    if before != source_hashes(target, module['extra_sources']):
        raise RuntimeError('build sources changed during compilation')
    required = [module['ko']]
    for name in required:
        if not (out / name).is_file():
            raise RuntimeError(f'missing build output: {out / name}')
    built = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(out.glob('*.ko'))}
    record.write_text(json.dumps(dict(target=target, module=args.module, sources=before,
        module_sha256=built[Path(module['ko']).stem], modules=built), indent=2)+'\n')
