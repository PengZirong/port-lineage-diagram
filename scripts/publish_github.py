#!/usr/bin/env python3
"""Publish an explicitly authorized public repository; never force-push or clobber."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from package_release import ROOT, VERSION, package, sha256, source_files

REPO = 'PengZirong/port-lineage-diagram'
OWNER = 'PengZirong'
URL = f'https://github.com/{REPO}.git'
STATE = ROOT / '.publish-state.json'
ENV = dict(os.environ, GH_HOST='github.com', GH_PROMPT_DISABLED='1',
           GIT_TERMINAL_PROMPT='0', GH_PAGER='cat')
IDENTITY = ['-c', 'user.name=PengZirong', '-c',
            'user.email=35917794+PengZirong@users.noreply.github.com']

class PublishError(RuntimeError):
    pass

def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, env=ENV, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PublishError(f'{args[0]} {args[1]} failed:\n{detail}')
    return result

def api(path: str, *, allow_missing: bool = False) -> dict | None:
    result = run(['gh', 'api', '--hostname', 'github.com', path], check=False)
    if result.returncode:
        if allow_missing and '(HTTP 404)' in result.stderr:
            return None
        raise PublishError(f'GitHub read failed: {result.stderr.strip()}')
    return json.loads(result.stdout)

def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(['git', *IDENTITY, *args], check=check)

def save_state(commit: str) -> None:
    STATE.write_text(json.dumps({'repo': REPO, 'commit': commit,
                                 'created_by_this_script': True}, indent=2) + '\n')

def verify_release(assets: list[Path], commit: str) -> dict:
    repo = api(f'repos/{REPO}')
    if not repo or repo.get('private') or repo.get('full_name', '').lower() != REPO.lower():
        raise PublishError('Remote repository visibility or identity does not match.')
    obj = api(f'repos/{REPO}/git/ref/tags/{VERSION}')['object']
    if obj['type'] == 'tag':
        obj = api(f'repos/{REPO}/git/tags/{obj["sha"]}')['object']
    if obj['type'] != 'commit' or obj['sha'] != commit:
        raise PublishError('Remote tag does not point to the expected local commit.')
    release = api(f'repos/{REPO}/releases/tags/{VERSION}')
    if not release or release.get('draft') or release.get('prerelease'):
        raise PublishError('Release is missing, draft, or prerelease; nothing was overwritten.')
    actual = {a['name']: a for a in release.get('assets', [])}
    for path in assets:
        asset = actual.get(path.name)
        if not asset or asset.get('size') != path.stat().st_size:
            raise PublishError(f'Release asset missing/size mismatch: {path.name}')
        digest = asset.get('digest')
        if digest:
            if digest != 'sha256:' + sha256(path):
                raise PublishError(f'Release asset digest mismatch: {path.name}')
        else:
            with tempfile.TemporaryDirectory(prefix='port-lineage-verify-') as folder:
                run(['gh', 'release', 'download', VERSION, '--repo', REPO,
                     '--pattern', path.name, '--dir', folder])
                if sha256(Path(folder) / path.name) != sha256(path):
                    raise PublishError(f'Downloaded asset digest mismatch: {path.name}')
    latest = api(f'repos/{REPO}/releases/latest')
    if not latest or latest.get('id') != release['id']:
        raise PublishError('The verified release is not the latest release; no settings changed.')
    return release

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Local tests/package only; no GitHub calls')
    parser.add_argument('--resume', action='store_true', help='Resume only the repository created by this script')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise PublishError('Python 3.10+ is required.')
    if not args.check:
        for binary in ('git', 'gh'):
            if not shutil.which(binary):
                raise PublishError(f'{binary} is not installed. Install it locally before publishing.')
        auth = run(['gh', 'auth', 'status', '--hostname', 'github.com'], check=False)
        if auth.returncode:
            raise PublishError('Authenticate locally first: gh auth login --hostname github.com')
        account = api('user')
        if account.get('login', '').lower() != OWNER.lower() or account.get('id') != 35917794:
            raise PublishError('Active GitHub account must be PengZirong; refusing to publish to another account.')
    print('Running local unit tests...', flush=True)
    result = run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    print(result.stderr.strip())
    assets = package()
    (ROOT / 'dist/local-unit-results.txt').write_text(result.stdout + result.stderr)
    print('Both examples passed strict build; release assets are ready.')
    if args.check:
        print(f'LOCAL ONLY — target {REPO}, public, {VERSION}. No repository or release was created.')
        return 0

    remote = api(f'repos/{REPO}', allow_missing=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if remote:
        if not args.resume or not state or state.get('repo') != REPO or not state.get('created_by_this_script'):
            raise PublishError('Target repository already exists. Refusing to adopt or overwrite it. '
                               'Use --resume only with the original local state file.')
        if remote.get('private') or remote.get('owner', {}).get('login', '').lower() != OWNER.lower():
            raise PublishError('Existing repository is not the expected public personal repository.')
    elif state:
        raise PublishError('A previous publication state exists but the remote cannot be read. Check permissions; do not recreate it blindly.')

    top = git('rev-parse', '--show-toplevel', check=False)
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() != ROOT:
        raise PublishError('This folder is inside another Git repository. Move it outside that repository first.')
    if not (ROOT / '.git').exists():
        git('init', '-b', 'main')
    origin = git('remote', 'get-url', 'origin', check=False)
    if origin.returncode == 0 and origin.stdout.strip().rstrip('/') not in {
        URL, URL.removesuffix('.git'), f'git@github.com:{REPO}.git'
    }:
        raise PublishError('origin points to another repository; refusing to change it.')

    head = git('rev-parse', '--verify', 'HEAD', check=False)
    if head.returncode:
        paths = [p.relative_to(ROOT).as_posix() for p in source_files()] + ['MANIFEST.sha256']
        git('-c', 'core.autocrlf=false', 'add', '--', *paths)
        git('commit', '-m', 'feat: initial port-lineage-diagram v1.0.0')
    elif git('status', '--porcelain').stdout.strip():
        raise PublishError('Working tree is not clean. Review changes before publishing; nothing was committed automatically.')
    expected_paths = {p.relative_to(ROOT).as_posix() for p in source_files()} | {'MANIFEST.sha256'}
    tracked_paths = set(git('ls-files', '-z').stdout.rstrip('\0').split('\0'))
    if tracked_paths != expected_paths or git('rev-list', '--count', 'HEAD').stdout.strip() != '1':
        raise PublishError('This initial release accepts only the prepared source tree and one initial commit; refusing to publish unrelated files or history.')
    if git('branch', '--show-current').stdout.strip() != 'main':
        raise PublishError('Current branch must be main; refusing to rename it automatically.')
    commit = git('rev-parse', 'HEAD').stdout.strip()
    if remote and state.get('commit') != commit:
        raise PublishError('Local commit differs from the original publication state. Use a new version instead.')
    tag = git('rev-parse', '--verify', f'refs/tags/{VERSION}^{{commit}}', check=False)
    if tag.returncode == 0 and tag.stdout.strip() != commit:
        raise PublishError('Existing local version tag points to another commit; refusing to move it.')
    if tag.returncode:
        git('tag', '-a', VERSION, '-m', 'Port Lineage Diagram v1.0.0')

    if not remote:
        print(f'Creating PUBLIC repository {REPO}...', flush=True)
        run(['gh', 'repo', 'create', REPO, '--public', '--disable-wiki',
             '--description', 'Agent Skill for non-linear workflows and field-level provenance in one port-based dataflow diagram.'])
        save_state(commit)
    if origin.returncode:
        git('remote', 'add', 'origin', URL)
    print('Pushing main and the version tag (no force)...', flush=True)
    # Command-scoped credentials; no global git configuration changes.
    git('-c', 'credential.helper=', '-c', 'credential.https://github.com.helper=!gh auth git-credential',
        'push', '--atomic', URL, 'refs/heads/main:refs/heads/main', f'refs/tags/{VERSION}:refs/tags/{VERSION}')
    existing_release = api(f'repos/{REPO}/releases/tags/{VERSION}', allow_missing=True)
    if existing_release:
        if existing_release.get('draft'):
            raise PublishError('An existing draft uses this tag. Inspect it manually; this script will not replace its assets or publish it blindly.')
        print('Release already exists; verifying only, without modifying it...')
    else:
        print('Creating the release and attaching assets...', flush=True)
        run(['gh', 'release', 'create', VERSION, *[str(a) for a in assets],
             '--repo', REPO, '--verify-tag', '--latest',
             '--title', 'Port Lineage Diagram v1.0.0',
             '--notes-file', str(ROOT / 'RELEASE-NOTES.md')])
    release = verify_release(assets, commit)
    print('VERIFIED: public repository, tag commit, published latest release, and all asset hashes.')
    print(f'Repository: https://github.com/{REPO}')
    print(f'Release: {release["html_url"]}')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (PublishError, RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'\nSTOPPED: {error}', file=sys.stderr)
        if STATE.exists():
            print('Remote work may have partially completed. Keep this directory; inspect the error, then use --resume. '
                  'No force-push or asset overwrite was attempted.', file=sys.stderr)
        raise SystemExit(1)
