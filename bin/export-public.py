#!/usr/bin/env python3
"""Export reviewed, allowlisted functionality to an existing public Brain repo.

Preview is the default. No private Git history, recursive directory copying,
automatic redaction, force push, credentials, or ambient git author identity.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

PRIVATE = {'.brain', '.local', '.git', '.aws', '.codex', 'daily', 'weekly', 'projects', 'inbox'}
PRIVATE_FILES = {'PORTFOLIO.md', 'reminders.md', 'auth.json', 'web-auth.json', 'config/projects.json', 'config/public-export.json'}
RULES = {
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'token': rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{15,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}|figd_[A-Za-z0-9_-]{20,})',
    'cloud key': rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'personal home': rb'/(?:Users|home)/[A-Za-z0-9_.-]+/',
    'email address': rb'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
}


class ExportError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise ExportError('Git operation failed; diagnostic withheld to avoid private data.')
    return result.stdout


def relative(name):
    if not isinstance(name, str):
        raise ExportError("Manifest path must be a string.")
    path = PurePosixPath(name)
    if (not isinstance(name, str) or not name or path.is_absolute() or '..' in path.parts
            or '\\' in name or '\n' in name or '\r' in name or path.as_posix() != name):
        raise ExportError('Manifest paths must be normalized relative paths.')
    return path


def safe_file(root, name, must_exist=True):
    relative(name)
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ExportError('Manifest path escaped its root.')
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink():
            raise ExportError('Symlinks cannot be exported or overwritten.')
    if must_exist and not path.is_file():
        raise ExportError('An allowlisted source is missing or is not a file.')
    return path


def violations(name, data, markers=()):
    issues = []
    parts = PurePosixPath(name).parts
    if ((parts and parts[0] in PRIVATE) or any(p in {'.brain', '.local', '.git', '.aws', '.codex'} or p.startswith('.env') for p in parts) or name in PRIVATE_FILES or PurePosixPath(name).name in PRIVATE_FILES
            or name.endswith(('.jsonl', '.sqlite', '.sqlite3', '.db', '.log'))):
        issues.append('private path or runtime data')
    if b'\x00' in data:
        issues.append('binary file requires a separate reviewed release workflow')
    for label, pattern in RULES.items():
        matches = list(re.finditer(pattern, data))
        if label == 'email address':
            def synthetic(match):
                domain = match.group().split(b'@', 1)[1].lower()
                return (domain in (b'example.com', b'example.net', b'example.org')
                        or domain.endswith((b'.example', b'.invalid', b'.test', b'.example.com', b'.example.net', b'.example.org')))
            matches = [match for match in matches if not synthetic(match)]
        if matches:
            issues.append(label)
    if any(marker.encode().lower() in data.lower() for marker in markers):
        issues.append('private marker')
    return issues


def write_atomic(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.export-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def verify_inputs(root, manifest):
    for row in manifest.get('reviewed_inputs', []):
        if digest(safe_file(root, row['path']).read_bytes()) != row['sha256']:
            raise ExportError('A private implementation changed since public review; update the curated feature and review fingerprint first.')


def clean_target(target, manifest):
    if git(target, 'rev-parse', '--show-toplevel').decode().strip() != str(target):
        raise ExportError('Target must be the root of an existing Git checkout.')
    if git(target, 'remote', 'get-url', 'origin').decode().strip() != manifest['expected_origin']:
        raise ExportError('Target origin does not match the approved public repo.')
    if git(target, 'branch', '--show-current').decode().strip() != manifest['branch']:
        raise ExportError('Target is on a different branch; no automatic switching.')
    if git(target, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ExportError('Target has existing changes; preserve or commit those before exporting.')
    return git(target, 'rev-parse', 'HEAD').decode().strip()


def prepare(manifest_path):
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('version') != 1:
        raise ExportError('Unsupported export manifest version.')
    root = (manifest_path.parent / manifest['source_root']).resolve()
    target = Path(manifest['target_repo']).expanduser().resolve()
    if root == target or root.is_relative_to(target) or target.is_relative_to(root):
        raise ExportError('Public checkout must be separate from the private source tree.')
    head = clean_target(target, manifest)
    verify_inputs(root, manifest)
    markers = manifest.get('private_markers', [])
    if not isinstance(markers, list) or any(not isinstance(m, str) or len(m) < 2 for m in markers):
        raise ExportError('Private markers must be strings of at least two characters.')
    rows, changed = {}, []
    for row in manifest['files']:
        name = row['target']
        if name in rows:
            raise ExportError('Duplicate export target.')
        source = safe_file(root, row['source'])
        path = safe_file(target, name, False)
        data = source.read_bytes()
        current = path.read_bytes() if path.is_file() else None
        if current is not None and digest(current) not in (digest(data), row.get('base_sha256')):
            raise ExportError('Public file changed independently; reconcile it before exporting.')
        if current is None and row.get('base_sha256') is not None:
            raise ExportError('A previously exported public file is missing; reconcile first.')
        rows[name] = {'data': data, 'mode': 0o755 if source.stat().st_mode & 0o111 else 0o644, 'source': row['source']}
        if current != data:
            changed.append(name)
    # Scan the complete would-be public tree, not just this diff.
    tracked = [n for n in git(target, 'ls-files', '-z').decode().split('\0') if n]
    failures = []
    for name in sorted(set(tracked) | set(rows)):
        data = rows[name]['data'] if name in rows else safe_file(target, name).read_bytes()
        failures += [(name, issue) for issue in violations(name, data, markers)]
    if failures:
        # No matched values, file contents, or secret-bearing snippets in errors.
        raise ExportError('Privacy check failed: ' + '; '.join(f'{name} [{issue}]' for name, issue in failures))
    return manifest, root, target, head, rows, changed


def validate(candidate):
    for label, argv in (
        ('tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        ('release content', [sys.executable, 'bin/check-release.py']),
        ('whitespace', ['git', 'diff', '--cached', '--check']),
    ):
        result = subprocess.run(argv, cwd=candidate, capture_output=True, timeout=180)
        if result.returncode:
            raise ExportError(f'Candidate {label} validation failed; target was not changed. Run the check in a reviewed local staging copy for details.')
        print(f'PASS {label}')


def publish(target, manifest, commit, parent):
    remote = git(target, 'ls-remote', '--heads', 'origin', 'refs/heads/' + manifest['branch']).decode().split()
    if not remote or remote[0] not in (parent, commit):
        raise ExportError('Remote changed; reconcile without force push. Local commit is preserved.')
    if remote[0] != commit:
        git(target, 'push', 'origin', commit + ':refs/heads/' + manifest['branch'])
    remote = git(target, 'ls-remote', '--heads', 'origin', 'refs/heads/' + manifest['branch']).decode().split()
    if not remote or remote[0] != commit:
        raise ExportError('Push could not be verified; local commit is preserved.')
    print('Remote commit verified ' + commit)


def run(manifest_path, apply=False, message_file=None, push=False):
    # Serialize this manifest; the process lock releases on errors and exit.
    lock_path = manifest_path.with_suffix('.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ExportError('Another export holds this manifest lock.') from None
        return _run(manifest_path, apply, message_file, push)
    finally:
        os.close(fd)


def _run(manifest_path, apply=False, message_file=None, push=False):
    manifest, root, target, head, rows, changed = prepare(manifest_path)
    if push and not message_file:
        raise ExportError('--push requires --message-file; it never publishes unrelated local commits.')
    if not changed:
        if push:
            saved = manifest.get('last_export', {})
            if saved.get('commit') != head or git(target, 'rev-parse', 'HEAD^').decode().strip() != saved.get('parent'):
                raise ExportError('No recorded export commit to publish; unrelated commits are never pushed.')
            publish(target, manifest, head, saved['parent'])
        print('No functional differences; no files or commits created.')
        return None
    message = message_file.read_bytes() if message_file else None
    if message is not None:
        if not message.strip() or violations('commit-message.txt', message, manifest.get('private_markers', [])):
            raise ExportError('Commit message is empty or failed privacy checks.')
        author = manifest.get('author', {})
        if (not re.fullmatch(r'[A-Za-z0-9-]+', author.get('name', ''))
                or not re.fullmatch(r'(?:[0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com', author.get('email', ''))):
            raise ExportError('Set the public GitHub username and GitHub noreply author explicitly.')
    if push:
        remote = git(target, 'ls-remote', '--heads', 'origin', 'refs/heads/' + manifest['branch']).decode().split()
        if not remote or remote[0] != head:
            raise ExportError('Remote head differs; reconcile without force push before exporting.')
    print('Allowlisted changes:')
    for name in sorted(changed):
        print('  ' + name)
    with tempfile.TemporaryDirectory(prefix='brain-public-candidate-') as folder:
        candidate = Path(folder) / 'repo'
        result = subprocess.run(['git', 'clone', '--quiet', '--no-local', str(target), str(candidate)], capture_output=True)
        if result.returncode:
            raise ExportError('Cannot create isolated public candidate.')
        for name in changed:
            write_atomic(candidate / name, rows[name]['data'], rows[name]['mode'])
        git(candidate, 'add', '--', *changed)
        validate(candidate)
        expected_tree = git(candidate, 'write-tree').decode().strip()
        print(git(candidate, 'diff', '--cached', '--stat').decode().strip())
        if not apply and message is None:
            print('Preview only. Use --message-file to validate, apply and commit.')
            return None
        if clean_target(target, manifest) != head:
            raise ExportError('Public checkout changed during validation; nothing applied.')
        verify_inputs(root, manifest)
        if any(safe_file(root, row['source']).read_bytes() != row['data'] for row in rows.values()):
            raise ExportError('Export sources changed during validation; nothing applied.')
        for name in changed:
            write_atomic(target / name, rows[name]['data'], rows[name]['mode'])
        git(target, 'add', '--', *changed)
        staged = set(git(target, 'diff', '--cached', '--name-only', '-z').decode().strip('\0').split('\0'))
        if staged != set(changed):
            raise ExportError('Staged paths differ from reviewed paths; commit withheld.')
        git(target, 'diff', '--cached', '--check')
        if message is None:
            print('Applied and staged only; no commit or push.')
            return None
        # Use a file, suppress inherited author overrides, and avoid personal global identity.
        msg = Path(folder) / 'message.txt'
        msg.write_bytes(message)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_AUTHOR_', 'GIT_COMMITTER_'))}
        result = subprocess.run(['git', '-C', str(target), '-c', 'user.name=' + author['name'],
                                 '-c', 'user.email=' + author['email'], 'commit', '--file', str(msg)],
                                env=env, capture_output=True)
        if result.returncode:
            raise ExportError('Commit failed; reviewed files remain staged for recovery.')
        commit = git(target, 'rev-parse', 'HEAD').decode().strip()
        if git(target, 'rev-parse', 'HEAD^{tree}').decode().strip() != expected_tree:
            raise ExportError('Committed tree differs from the tested candidate; push withheld.')
        # Advance only reviewed baseline hashes; never add paths automatically.
        for row in manifest['files']:
            row['base_sha256'] = digest(rows[row['target']]['data'])
        manifest['last_export'] = {'commit': commit, 'parent': head}
        write_atomic(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
        print('Committed ' + commit)
        if push:
            publish(target, manifest, commit, head)
        return commit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1] / 'config/public-export.json')
    p.add_argument('--apply', action='store_true', help='apply and stage after validation; do not commit')
    p.add_argument('--message-file', type=Path, help='validate, apply, and commit with this reviewed message')
    p.add_argument('--push', action='store_true', help='also push this exact new commit after remote-head verification')
    args = p.parse_args()
    try:
        run(args.manifest, args.apply, args.message_file, args.push)
    except (ExportError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Export: ' + (str(error) if isinstance(error, ExportError) else 'Invalid manifest or local operation failed; raw output withheld.'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
