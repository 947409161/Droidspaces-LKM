#!/usr/bin/env python3
"""Package the device-validated .ko, KernelSU ZIP and checksums without rebuilding."""
import argparse
import hashlib
import re
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATED_SHA256 = '33ed20ce38f092d98f4379701d45127522370d13f3d59ba6458916a0b6f592f4'
PAYLOAD_NAME = 'droidspaces_ns-6.12.69-canoe.ko'
MODULE_FILES = ('module.prop', 'common.sh', 'customize.sh', 'post-fs-data.sh',
                'service.sh', 'skip_mount')


def package(module, output):
    payload = module.read_bytes()
    if (payload[:6] != b'\x7fELF\x02\x01' or
            struct.unpack_from('<H', payload, 18)[0] != 183):
        raise ValueError('expected an ELF64 AArch64 kernel module')
    digest = hashlib.sha256(payload).hexdigest()
    if digest != VALIDATED_SHA256:
        raise ValueError('not the device-validated payload; validate and update the pinned hash before releasing')
    metadata = (ROOT / 'kernelsu/module.prop').read_text()
    version = re.search(r'^version=(v[0-9]+\.[0-9]+\.[0-9]+)$', metadata, re.M).group(1)
    output.mkdir(parents=True, exist_ok=True)
    files = {name: (ROOT / 'kernelsu' / name).read_bytes() for name in MODULE_FILES}
    files['kernel/droidspaces_ns.ko'] = payload
    files['kernel/SHA256SUMS'] = f'{digest}  droidspaces_ns.ko\n'.encode()
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    files['SOURCE.txt'] = (
        'Source: https://github.com/Shikochin/Droidspaces-LKM\n'
        f'KernelSU module release: {version}\n'
        'Payload source: 2147acd (only a comment differs from the device-tested build).\n'
        'Build and original source provenance: README.md and src/port/ORIGIN in the repository.\n'
    ).encode()
    archive = output / f'Droidspaces-LKM-KernelSU-{version}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 10, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    standalone = output / PAYLOAD_NAME
    standalone.write_bytes(payload)
    (output / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
        for p in (standalone, archive)))
    print(archive)
    print(standalone)
    print(output / 'SHA256SUMS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, default=ROOT / 'out/release' / PAYLOAD_NAME)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/release')
    args = parser.parse_args()
    package(args.module, args.output)
