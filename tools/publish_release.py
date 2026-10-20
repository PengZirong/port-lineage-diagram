#!/usr/bin/env python3
"""Check an existing tag and build assets; only --publish creates a GitHub Release."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from package_skill import ROOT, VERSION_RE, package


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} command failed: {result.stderr.strip()}')
    return result.stdout.strip()


def api(path: str):
    return json.loads(run('gh', 'api', path))


def tagged_commit(repo: str, tag: str) -> str:
    obj = api(f'repos/{repo}/git/ref/tags/{tag}')['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            break
        obj = api(f'repos/{repo}/git/tags/{obj["sha"]}')['object']
    raise ValueError('Remote tag does not resolve to a commit')


def assert_no_release(repo: str, version: str) -> None:
    # Paginate; an API failure is not mistaken for "release absent".
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
    if any(item['tag_name'] == version for page in pages for item in page):
        raise ValueError('A release or draft already exists for this tag; refusing to overwrite it')


def check_tree(repo: str, version: str) -> str:
    if Path(run('git', 'rev-parse', '--show-toplevel')).resolve() != ROOT:
        raise ValueError('Run from a checkout of this repository, not a nested unrelated repository')
    if run('git', 'status', '--porcelain'):
        raise ValueError('Working tree must be clean; commit changes before preparing a release')
    head = run('git', 'rev-parse', 'HEAD')
    local = run('git', 'rev-parse', f'refs/tags/{version}^{{commit}}')
    if local != head or tagged_commit(repo, version) != head:
        raise ValueError('HEAD, local tag and existing remote tag must identify the same commit')
    assert_no_release(repo, version)
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--notes', required=True, type=Path)
    parser.add_argument('--repo', default='PengZirong/port-lineage-diagram')
    parser.add_argument('--publish', action='store_true', help='Explicitly create the Release; default is read-only on GitHub')
    args = parser.parse_args()
    try:
        if not VERSION_RE.fullmatch(args.version):
            raise ValueError('Invalid version tag')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
            raise ValueError('Repository must be owner/name')
        if not shutil.which('git') or not shutil.which('gh'):
            raise ValueError('Git and an authenticated GitHub CLI are required')
        notes = args.notes.resolve()
        if not notes.is_file() or not notes.read_text(encoding='utf-8').strip():
            raise ValueError('Release notes must be an existing, nonempty UTF-8 file')
        repo = api(f'repos/{args.repo}')
        if repo.get('archived') or repo.get('visibility') != 'public':
            raise ValueError('Expected an existing, unarchived public repository')
        head = check_tree(args.repo, args.version)
        assets = package(args.version, ROOT / 'dist' / args.version)
        print(json.dumps({'repository': args.repo, 'tag': args.version, 'commit': head,
                          'assets': [str(p) for p in assets], 'publish': args.publish}, indent=2))
        if not args.publish:
            print('Checks and packaging complete. No GitHub writes were made.')
            return 0
        # Recheck after packaging; never force-push, create tags or clobber assets.
        if check_tree(args.repo, args.version) != head:
            raise ValueError('HEAD changed while packaging; stop and inspect')
        command = ['gh', 'release', 'create', args.version, *map(str, assets),
                   '--repo', args.repo, '--verify-tag', '--title', f'Port Lineage Diagram {args.version}',
                   '--notes-file', str(notes)]
        if '-' in args.version:
            command.append('--prerelease')
        run(*command)
        release = api(f'repos/{args.repo}/releases/tags/{args.version}')
        if release.get('draft') or release.get('prerelease') != ('-' in args.version):
            raise RuntimeError('Release state does not match the requested version')
        uploaded = {item['name']: item['size'] for item in release.get('assets', [])}
        if any(uploaded.get(p.name) != p.stat().st_size for p in assets):
            raise RuntimeError('Release asset names or sizes differ; inspect the remote release')
        print('Release created; tag, state, attachment names and sizes checked (no remote byte-hash verification).')
        print(release['html_url'])
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Stopped: {exc}', file=sys.stderr)
        if args.publish:
            print('Inspect GitHub for a partially created release before retrying; no overwrite was attempted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
