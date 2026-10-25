#!/usr/bin/env python3
"""Audit the 5.15 ipset modules against the DDK kernel BTF and symbols."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / 'build/gki-targets.json').read_text())
MANIFEST = json.loads((ROOT / 'src/ipset515/modules.json').read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=TARGETS)
    args = parser.parse_args()
    target = TARGETS[args.target]
    out = ROOT / 'out/gki' / (target['kmi'] + '-ipset515')
    missing = [m['name'] + '.ko' for m in MANIFEST['modules']
               if not (out / (m['name'] + '.ko')).is_file()]
    if missing:
        parser.error(f'build the ipset515 modules first; missing {missing}')
    script = '''set -eu
out=/module/out/gki/"$1"-ipset515
llvm-objcopy -O binary -R .note -R .note.gnu.build-id -R .comment -S "$KDIR/vmlinux" "$out/Image"
if llvm-readelf -S "$KDIR/vmlinux" | grep -q ' \\.BTF '; then
    llvm-objcopy --dump-section .BTF="$out/kernel.btf" "$KDIR/vmlinux" /tmp/vmlinux-copy
else
    pahole -F dwarf --btf_gen_optimized --btf_encode_detached="$out/kernel.btf" "$KDIR/vmlinux"
fi
cp "$KDIR/.config" "$out/kernel.config"
cp "$KDIR/include/config/kernel.release" "$out/kernel.release"
llvm-nm "$KDIR/vmlinux" > "$out/symbols.txt"
for ko in "$out"/droidspaces_*.ko; do
    base=$(basename "$ko" .ko)
    pahole -F dwarf --btf_gen_optimized --btf_encode_detached="$out/$base.btf" "$ko" >/dev/null
    llvm-nm -u "$ko" > "$out/$base.imports.txt"
    llvm-nm "$ko" | awk '{n=$NF} n ~ /^__ksymtab(_gpl)?_/ {sub(/^__ksymtab(_gpl)?_/, "", n); print n}' \
        | sort -u > "$out/$base.exports.txt"
done
'''
    subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64', '-v', f'{ROOT}:/module',
                    target['image'], 'sh', '-c', script, 'prepare-ipset515', target['kmi']], check=True)

    import importlib.util
    spec = importlib.util.spec_from_file_location('compare_btf', ROOT/'scripts/abi/compare-btf.py')
    compare_btf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare_btf)

    symbols = {line.split()[-1] for line in (out/'symbols.txt').read_text().splitlines()
               if len(line.split()) >= 3}
    def names(path):
        return {line.split()[-1] for line in path.read_text().splitlines() if line.strip()}

    provided = set()
    for module in MANIFEST['modules']:
        provided |= names(out/(module['name'] + '.exports.txt'))
    core_exports = names(out/(MANIFEST['core'] + '.exports.txt'))

    report = {'target': 'android13-5.15',
              'kernel_btf_sha256': sha(out/'kernel.btf'),
              'core_exports': sorted(core_exports), 'modules': {}}
    for module in MANIFEST['modules']:
        base = module['name']
        layouts = compare_btf.compare(out/(base + '.btf'), out/'kernel.btf')
        if layouts['differences']:
            raise SystemExit(f'{base}: incompatible host layouts: '
                             f'{json.dumps(layouts["differences"], indent=2)}')
        imports = names(out/(base + '.imports.txt'))
        internal = imports & provided
        unresolved = (imports - provided) - symbols
        if unresolved:
            raise SystemExit(f'{base}: unresolved kernel imports: {sorted(unresolved)}')
        report['modules'][base] = dict(sha256=sha(out/(base + '.ko')),
                                      imports=len(imports), internal_imports=len(internal),
                                      matching_aggregates=layouts['matching_aggregates'])
    (out/'ipset515.audit.json').write_text(json.dumps(report, indent=2) + '\n')

    names = ['Image', 'kernel.btf', 'kernel.config', 'kernel.release', 'symbols.txt',
             'ipset515.audit.json']
    for module in MANIFEST['modules']:
        names += [module['name'] + '.ko', module['name'] + '.btf']
    (out/'prepared.json').write_text(json.dumps({name: sha(out/name) for name in names},
                                                indent=2) + '\n')
    print(f'{len(MANIFEST["modules"])} modules audited; '
          f'{len(core_exports)} core exports; {len(provided)} internal symbols')
