"""Installation-layout, isolated-use and runtime-only package regression tests."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/port-lineage-diagram'
sys.path.insert(0, str(ROOT / 'tools'))
import package_skill as P
import publish_release as R


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


class SkillPackageTests(unittest.TestCase):
    def test_exactly_one_discoverable_skill(self):
        paths = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob('SKILL.md')
                 if not any(part in {'dist', 'output', '.git'} for part in p.relative_to(ROOT).parts)]
        self.assertEqual(paths, ['skills/port-lineage-diagram/SKILL.md'])

    def test_metadata_and_self_contained_instructions(self):
        text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        front = text.split('---', 2)[1]
        self.assertRegex(front, r'(?m)^name: port-lineage-diagram$')
        description = re.search(r'description: >\n((?:  .+\n)+)', front).group(1)
        self.assertTrue(1 <= len(description) <= 1024)
        self.assertIn('compatibility:', front)
        self.assertNotIn('第一种', text)
        self.assertNotIn('unittest discover', text)
        self.assertNotIn('tools/publish', text)
        self.assertLess(len(text.splitlines()), 500)

    def test_markdown_local_links_exist(self):
        pages = [ROOT / 'README.md', *SKILL.rglob('*.md'),
                 ROOT / 'docs/development.md', * (ROOT / 'evals').rglob('*.md')]
        for page in pages:
            for link in re.findall(r'\]\(([^)]+)\)', page.read_text(encoding='utf-8')):
                if '://' in link or link.startswith('#'):
                    continue
                dest = (page.parent / link.split('#')[0]).resolve()
                self.assertTrue(dest.exists(), f'{page.relative_to(ROOT)}: {link}')
                if page.is_relative_to(SKILL):
                    self.assertTrue(dest.is_relative_to(SKILL), f'Install-external link: {link}')

    def isolated_build(self, installed: Path, project: Path) -> None:
        project.mkdir(parents=True)
        shutil.copyfile(installed / 'assets/examples/file-import.json', project / 'workflow.json')
        before = snapshot(installed)
        result = subprocess.run([
            sys.executable, str(installed / 'scripts/lineage.py'), 'build',
            'workflow.json', '--out', 'output/result', '--strict',
        ], cwd=project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(installed), before)
        self.assertTrue((project / 'output/result/index.html').is_file())
        report = json.loads((project / 'output/result/validation.json').read_text())
        self.assertEqual(len(report['covered_outputs']), 3)
        traced = subprocess.run([
            sys.executable, str(installed / 'scripts/lineage.py'), 'trace',
            'workflow.json', report['outputs'][0],
        ], cwd=project, capture_output=True, text=True)
        self.assertEqual(traced.returncode, 0, traced.stderr)
        self.assertTrue(json.loads(traced.stdout)['roots'])

    def test_installed_copy_works_from_another_project(self):
        with tempfile.TemporaryDirectory(prefix='lineage install ') as tmp:
            installed = Path(tmp) / 'agent skills/port-lineage-diagram'
            shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns('__pycache__'))
            self.isolated_build(installed, Path(tmp) / 'my project')

    @unittest.skipUnless(hasattr(os, 'symlink'), 'Symlinks are unavailable')
    def test_symlinked_install_works_from_another_project(self):
        with tempfile.TemporaryDirectory(prefix='lineage link ') as tmp:
            target = Path(tmp) / 'real skill'
            shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns('__pycache__'))
            installed = Path(tmp) / 'linked skill'
            try:
                installed.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(str(exc))
            self.isolated_build(installed, Path(tmp) / 'project')

    def test_unknown_draft_and_strict_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = json.loads((SKILL / 'assets/examples/file-import.json').read_text())
            model['nodes'][-1]['fields'].append({'id': 'unresolved', 'label': '待确认',
                'type': 'str', 'op': 'unknown', 'note': 'Provided material has no source'})
            model['outputs'] = [model['nodes'][-1]['id'] + '.unresolved']
            source = root / 'unknown.json'
            source.write_text(json.dumps(model), encoding='utf-8')
            cmd = [sys.executable, str(SKILL / 'scripts/lineage.py'), 'build', str(source), '--out', str(root / 'out')]
            draft = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(draft.returncode, 0, draft.stderr)
            strict = subprocess.run(cmd + ['--strict'], capture_output=True, text=True)
            self.assertEqual(strict.returncode, 2)
            self.assertIn('unresolved roots', strict.stderr)

    def test_package_is_runtime_only_and_extractable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, checksums = P.package('v1.1.0-dev', root / 'dist')
            with zipfile.ZipFile(archive) as z:
                expected = {'port-lineage-diagram/' + p.relative_to(SKILL).as_posix() for p in P.source_files()}
                self.assertEqual(set(z.namelist()), expected)
                self.assertTrue(all('/tests/' not in n and '/tools/' not in n and '/docs/' not in n for n in z.namelist()))
                z.extractall(root / 'installed')
            self.assertIn(P.sha256(archive), checksums.read_text())
            self.isolated_build(root / 'installed/port-lineage-diagram', root / 'project')

    def test_package_is_deterministic_and_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = snapshot(SKILL)
            a, _ = P.package('v1.1.0-dev', Path(tmp) / 'a')
            b, _ = P.package('v1.1.0-dev', Path(tmp) / 'b')
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(snapshot(SKILL), before)

    def test_package_rejects_install_tree_output(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            P.package('v1.1.0-dev', SKILL / 'output')

    def test_package_rejects_bad_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ('latest', '../v1.0.0', 'v1.0.0/../../bad'):
                with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'Version'):
                    P.package(version, Path(tmp))

    def test_package_rejects_maintenance_and_font_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / 'skill'
            shutil.copytree(SKILL, install, ignore=shutil.ignore_patterns('__pycache__'))
            extra = install / 'TEST-REPORT.md'
            extra.write_text('Not part of an installation')
            with self.assertRaisesRegex(ValueError, 'runtime resource'):
                P.source_files(install)
            extra.unlink()
            (install / 'assets/unexpected.woff2').write_bytes(b'not a font')
            with self.assertRaisesRegex(ValueError, 'Unexpected package'):
                P.source_files(install)

    def test_current_demos_match_runtime_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('order-checkout', 'file-import'):
                out = Path(tmp) / name
                subprocess.run([sys.executable, str(SKILL / 'scripts/lineage.py'), 'build',
                    str(SKILL / f'assets/examples/{name}.json'), '--out', str(out), '--strict'],
                    check=True, capture_output=True, text=True)
                for filename in ('index.html', 'diagram.svg', 'model.json', 'validation.json'):
                    self.assertEqual((out / filename).read_bytes(), (ROOT / f'docs/demos/{name}' / filename).read_bytes())


class ReleaseSafetyTests(unittest.TestCase):
    def test_annotated_tag_resolves(self):
        responses = [{'object': {'type': 'tag', 'sha': 'tag-sha'}},
                     {'object': {'type': 'commit', 'sha': 'commit-sha'}}]
        with patch.object(R, 'api', side_effect=responses):
            self.assertEqual(R.tagged_commit('owner/repo', 'v1.1.0'), 'commit-sha')

    def test_existing_draft_is_never_overwritten(self):
        with patch.object(R, 'run', return_value=json.dumps([[{'tag_name': 'v1.1.0', 'draft': True}]])):
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                R.assert_no_release('owner/repo', 'v1.1.0')

    def test_api_error_is_not_missing_release(self):
        with patch.object(R, 'run', side_effect=RuntimeError('API unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'API unavailable'):
                R.assert_no_release('owner/repo', 'v1.1.0')

    def test_default_mode_does_not_call_release_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / 'notes.md'
            notes.write_text('Test notes')
            with patch.object(sys, 'argv', ['publish_release.py', '--version', 'v1.1.0', '--notes', str(notes)]), \
                 patch.object(R.shutil, 'which', return_value='/test/tool'), \
                 patch.object(R, 'api', return_value={'visibility': 'public', 'archived': False}), \
                 patch.object(R, 'check_tree', return_value='test-commit'), \
                 patch.object(R, 'package', return_value=[]), \
                 patch.object(R, 'run') as runner:
                self.assertEqual(R.main(), 0)
                runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
