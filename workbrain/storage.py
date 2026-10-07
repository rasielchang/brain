"""Private files, atomic replacement, and a lock owned by the running process."""
import contextlib
import json
import os
from pathlib import Path
import tempfile


class BrainError(Exception):
    """A diagnostic that is safe to show without exposing response bodies or tokens."""


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".brain-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


@contextlib.contextmanager
def run_lock(root):
    # flock releases on process exit, including crashes; never delete the lock inode.
    try:
        import fcntl
    except ImportError:
        raise BrainError("Automated runs require macOS or Linux (flock).") from None
    folder = Path(root) / ".brain"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(folder / "run.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BrainError("Another Brain run holds the lock; existing reports were kept.") from None
        yield
    finally:
        os.close(fd)
