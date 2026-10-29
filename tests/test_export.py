import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('export_public', Path(__file__).resolve().parents[1] / 'bin/export-public.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / 'private'; self.private.mkdir()
        self.target = self.root / 'public'; self.target.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.target), *args], stderr=subprocess.DEVNULL)
        self.git = git
        git('init', '-b', 'main')
        git('config', 'user.name', 'example')
        git('config', 'user.email', 'example' + '@' + 'users.noreply.github.com')
        git('remote', 'add', 'origin', 'https://github.com/example/brain.git')
        (self.target / 'feature.py').write_text('old = True\n')
        git('add', 'feature.py'); git('commit', '-m', 'Synthetic baseline')
        (self.private / 'feature.py').write_text('new = True\n')
        self.path = self.private / 'export.json'
        self.manifest = {'version': 1, 'source_root': '.', 'target_repo': str(self.target),
                         'expected_origin': 'https://github.com/example/brain.git', 'branch': 'main',
                         'author': {'name': 'example', 'email': 'example' + '@' + 'users.noreply.github.com'},
                         'private_markers': ['Synthetic Customer'], 'reviewed_inputs': [],
                         'files': [{'source': 'feature.py', 'target': 'feature.py',
                                    'base_sha256': export.digest((self.target / 'feature.py').read_bytes())}]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.manifest))

    def test_preview_validates_without_touching_target_and_repeat_commit_is_noop(self):
        before = self.git('rev-parse', 'HEAD')
        with patch.object(export, 'validate') as check:
            export.run(self.path)
            self.assertEqual(self.git('rev-parse', 'HEAD'), before)
            self.assertFalse(self.git('status', '--porcelain'))
            check.assert_called_once()
            msg = self.private / 'message.txt'; msg.write_text('Add reusable feature\n')
            commit = export.run(self.path, message_file=msg)
            self.assertTrue(commit)
            self.assertEqual(self.git('log', '-1', '--format=%ae').decode().strip(), self.manifest['author']['email'])
            self.assertIsNone(export.run(self.path, message_file=msg))
            self.assertEqual(self.git('rev-list', '--count', 'HEAD').decode().strip(), '2')

    def test_private_marker_and_credential_fail_before_copy(self):
        for content in ('Synthetic Customer', 'ghp_' + 'x' * 30):
            (self.private / 'feature.py').write_text(content)
            with self.assertRaises(export.ExportError) as result:
                export.prepare(self.path)
            self.assertNotIn(content, str(result.exception))
            self.assertEqual((self.target / 'feature.py').read_text(), 'old = True\n')

    def test_paths_symlinks_and_private_runtime_files_are_rejected(self):
        for name in ('../escape.py', '/absolute.py', './feature.py'):
            with self.assertRaises(export.ExportError):
                export.relative(name)
        self.assertTrue(export.violations('daily/note.md', b'private'))
        self.assertTrue(export.violations('samples/transcript.jsonl', b'{}'))
        (self.private / 'feature.py').unlink()
        (self.private / 'feature.py').symlink_to(self.target / 'feature.py')
        with self.assertRaises(export.ExportError):
            export.prepare(self.path)

    def test_changed_private_input_requires_new_review(self):
        self.manifest['reviewed_inputs'] = [{'path': 'feature.py', 'sha256': 'not-current'}]
        self.save()
        with self.assertRaisesRegex(export.ExportError, 'changed since public review'):
            export.prepare(self.path)

    def test_dirty_or_independently_updated_target_is_preserved(self):
        (self.target / 'feature.py').write_text('independent = True\n')
        with self.assertRaisesRegex(export.ExportError, 'existing changes'):
            export.prepare(self.path)
        self.git('add', 'feature.py'); self.git('commit', '-m', 'Independent public change')
        with self.assertRaisesRegex(export.ExportError, 'changed independently'):
            export.prepare(self.path)

    def test_validation_failure_keeps_target_clean(self):
        with patch.object(export, 'validate', side_effect=export.ExportError('Synthetic failed test')):
            with self.assertRaises(export.ExportError):
                export.run(self.path, apply=True)
        self.assertFalse(self.git('status', '--porcelain'))
        self.assertEqual((self.target / 'feature.py').read_text(), 'old = True\n')

    def test_wrong_remote_cannot_be_exported(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/example/different.git')
        with self.assertRaisesRegex(export.ExportError, 'origin'):
            export.prepare(self.path)

    def test_failed_push_can_resume_only_the_recorded_export_commit(self):
        remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'set-url', 'origin', str(remote))
        self.git('push', 'origin', 'main')
        self.manifest['expected_origin'] = str(remote); self.save()
        msg = self.private / 'message.txt'; msg.write_text('Add reusable feature\n')
        with patch.object(export, 'validate'), patch.object(export, 'publish', side_effect=export.ExportError('Synthetic transport failure')):
            with self.assertRaises(export.ExportError):
                export.run(self.path, message_file=msg, push=True)
        commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertEqual(json.loads(self.path.read_text())['last_export']['commit'], commit)
        export.run(self.path, message_file=msg, push=True)
        self.assertEqual(self.git('ls-remote', '--heads', 'origin', 'refs/heads/main').decode().split()[0], commit)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').decode().strip(), '2')
