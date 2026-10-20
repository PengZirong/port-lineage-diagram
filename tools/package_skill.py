#!/usr/bin/env python3
"""Build a deterministic, runtime-only Agent Skill ZIP; never write to its source."""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'port-lineage-diagram'
VERSION_RE = re.compile(r'^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$')
REQUIRED = {
    'SKILL.md', 'scripts/lineage.py', 'scripts/browser_qa.py',
    'assets/viewer.html', 'assets/examples/order-checkout.json',
    'assets/examples/file-import.json', 'references/model-contract.md',
    'references/drawing-rules.md', 'references/qa-checklist.md',
}
SECRET_PATTERNS = [
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(skill_dir: Path = SKILL) -> list[Path]:
    """Whitelist the installation unit; reject links and unexpected payload files."""
    if not skill_dir.is_dir():
        raise ValueError(f'Skill directory not found: {skill_dir}')
    selected = []
    for path in sorted(skill_dir.rglob('*')):
        rel = path.relative_to(skill_dir)
        if '__pycache__' in rel.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.is_symlink():
            raise ValueError(f'Refusing symlink in package: {rel}')
        if path.is_dir():
            continue
        if rel.as_posix() != 'SKILL.md' and rel.parts[0] not in {'scripts', 'references', 'assets'}:
            raise ValueError(f'Not a runtime resource: {rel}')
        if any(part.startswith('.') for part in rel.parts) or path.suffix not in {'.md', '.py', '.json', '.html'}:
            raise ValueError(f'Unexpected package file: {rel}')
        text = path.read_text(encoding='utf-8')
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise ValueError(f'Possible credential in {rel}; inspect before packaging')
        selected.append(path)
    missing = REQUIRED - {p.relative_to(skill_dir).as_posix() for p in selected}
    if missing:
        raise ValueError(f'Missing runtime resources: {sorted(missing)}')
    return selected


def package(version: str, out: Path, skill_dir: Path = SKILL) -> list[Path]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Version must be vMAJOR.MINOR.PATCH with an optional prerelease suffix')
    skill_dir = skill_dir.resolve()
    out = out.resolve()
    if out.is_relative_to(skill_dir):
        raise ValueError('Package output must be outside the Skill installation directory')
    paths = source_files(skill_dir)
    # Validate fixtures without modifying the install tree or committing generated assets.
    with tempfile.TemporaryDirectory(prefix='port-lineage-build-') as tmp:
        for example in ('order-checkout', 'file-import'):
            subprocess.run([
                sys.executable, str(skill_dir / 'scripts/lineage.py'), 'build',
                str(skill_dir / f'assets/examples/{example}.json'), '--out',
                str(Path(tmp) / example), '--strict',
            ], cwd=tmp, check=True, capture_output=True, text=True)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'port-lineage-diagram-{version}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            rel = path.relative_to(skill_dir)
            info = zipfile.ZipInfo('port-lineage-diagram/' + rel.as_posix(), (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == '.py' else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
    checksums = out / 'SHA256SUMS'
    checksums.write_text(f'{sha256(archive)}  {archive.name}\n', encoding='utf-8')
    return [archive, checksums]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    try:
        for path in package(args.version, args.out):
            print(path)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'Packaging failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
