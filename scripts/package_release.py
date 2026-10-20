#!/usr/bin/env python3
"""Build deterministic release assets using only the Python standard library."""
from __future__ import annotations
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v1.0.0'
ROOT_FILES = {
    'SKILL.md', 'README.md', 'TEST-REPORT.md', 'CHANGELOG.md',
    'RELEASE-NOTES.md', 'PUBLICATION-CHECK.md', 'PUBLISHING.md',
    '.gitignore', '.gitattributes', 'publish.sh',
}
DIRS = {'assets', 'examples', 'references', 'scripts', 'tests'}
SECRET_PATTERNS = [
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b'),
]

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_files() -> list[Path]:
    selected = []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if rel.parts[0] not in DIRS and rel.as_posix() not in ROOT_FILES:
            continue
        if '__pycache__' in rel.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.is_symlink():
            raise RuntimeError(f'Refusing symlink: {rel}')
        if not path.is_file():
            continue
        if path.name.startswith('.env') or path.suffix.lower() in {
            '.pem', '.key', '.p12', '.pfx', '.ttf', '.otf', '.woff', '.woff2'
        }:
            raise RuntimeError(f'Refusing potentially sensitive/disallowed file: {rel}')
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            text = ''
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise RuntimeError(f'Possible credential in {rel}; inspect locally before publishing')
        selected.append(path)
    missing = ROOT_FILES - {p.relative_to(ROOT).as_posix() for p in selected}
    if missing:
        raise RuntimeError(f'Missing source files: {sorted(missing)}')
    return selected

def package() -> list[Path]:
    if not re.search(r'version:\s*"1\.0\.0"', (ROOT / 'SKILL.md').read_text()):
        raise RuntimeError('SKILL.md version must match v1.0.0')
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    for example in ('order-checkout', 'file-import'):
        subprocess.run([
            sys.executable, str(ROOT / 'scripts/lineage.py'), 'build',
            str(ROOT / f'examples/{example}.json'), '--out',
            str(out / 'validation' / example), '--strict',
        ], cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True)
    paths = source_files()
    manifest = ROOT / 'MANIFEST.sha256'
    manifest.write_text(''.join(
        f'{sha256(p)}  {p.relative_to(ROOT).as_posix()}\n' for p in paths
    ), encoding='utf-8')
    archive = out / f'port-lineage-diagram-{VERSION}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths + [manifest]):
            info = zipfile.ZipInfo(
                'port-lineage-diagram/' + p.relative_to(ROOT).as_posix(),
                date_time=(2026, 10, 19, 0, 0, 0),
            )
            info.create_system = 3
            mode = 0o100755 if p.name == 'publish.sh' else 0o100644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    assets = [archive]
    mapping = {
        'order-checkout-example.html': 'examples/order-checkout/index.html',
        'order-checkout-diagram.svg': 'examples/order-checkout/diagram.svg',
        'order-checkout-preview.png': 'examples/order-checkout/qa/overview.png',
        'file-import-example.html': 'examples/file-import/index.html',
    }
    for name, rel in mapping.items():
        dest = out / name
        shutil.copyfile(ROOT / rel, dest)
        assets.append(dest)
    checksums = out / 'SHA256SUMS'
    checksums.write_text(''.join(
        f'{sha256(p)}  {p.name}\n' for p in sorted(assets)
    ), encoding='utf-8')
    assets.append(checksums)
    return assets

if __name__ == '__main__':
    for path in package():
        print(path.relative_to(ROOT))
