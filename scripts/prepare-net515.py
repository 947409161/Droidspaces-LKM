#!/usr/bin/env python3
"""Prepare BTF/config/imports for the 5.15 MACVLAN + IPv6 NAT module and audit it."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / 'build/gki-targets.json').read_text())
KO = 'droidspaces_net515.ko'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=TARGETS)
    args = parser.parse_args()
    target = TARGETS[args.target]
    out = ROOT / 'out/gki' / (target['kmi'] + '-net515')
    if not (out / KO).is_file():
        parser.error('build the net515 module first')
    script = '''set -eu
out=/module/out/gki/"$1"-net515
llvm-objcopy -O binary -R .note -R .note.gnu.build-id -R .comment -S "$KDIR/vmlinux" "$out/Image"
if llvm-readelf -S "$KDIR/vmlinux" | grep -q ' \\.BTF '; then
    llvm-objcopy --dump-section .BTF="$out/kernel.btf" "$KDIR/vmlinux" /tmp/vmlinux-copy
else
    pahole -F dwarf --btf_gen_optimized --btf_encode_detached="$out/kernel.btf" "$KDIR/vmlinux"
fi
cp "$KDIR/.config" "$out/kernel.config"
cp "$KDIR/include/config/kernel.release" "$out/kernel.release"
pahole -F dwarf --btf_gen_optimized --btf_encode_detached="$out/module.btf" "$out/''' + KO + '''"
llvm-nm -u "$out/''' + KO + '''" > "$out/imports.txt"
llvm-nm "$KDIR/vmlinux" > "$out/symbols.txt"
'''
    subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64', '-v', f'{ROOT}:/module',
                    target['image'], 'sh', '-c', script, 'prepare-net515', target['kmi']], check=True)

    import importlib.util
    spec = importlib.util.spec_from_file_location('compare_btf', ROOT/'scripts/abi/compare-btf.py')
    compare_btf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare_btf)

    report = compare_btf.compare(out/'module.btf', out/'kernel.btf')
    if report['differences']:
        raise SystemExit(f'incompatible host layouts: {json.dumps(report["differences"], indent=2)}')
    imports = {line.split()[-1] for line in (out/'imports.txt').read_text().splitlines() if line.strip()}
    symbols = {line.split()[-1] for line in (out/'symbols.txt').read_text().splitlines()
               if len(line.split()) >= 3}
    if imports - symbols:
        raise SystemExit(f'unresolved kernel imports: {sorted(imports - symbols)}')
    (out/'net515.audit.json').write_text(json.dumps(dict(
        target='android13-5.15', device_release_check='loader',
        matching_aggregates=report['matching_aggregates'],
        module_only_aggregates=report['module_only'],
        resolved_imports=len(imports),
        module_sha256=hashlib.sha256((out/KO).read_bytes()).hexdigest(),
    ), indent=2) + '\n')
    (out/'prepared.json').write_text(json.dumps({name: hashlib.sha256((out/name).read_bytes()).hexdigest()
        for name in (KO, 'Image', 'kernel.config', 'kernel.release', 'kernel.btf',
                     'module.btf', 'net515.audit.json')}, indent=2) + '\n')
    print(f'{report["matching_aggregates"]} layouts match; {len(imports)} imports resolved')
