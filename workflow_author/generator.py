"""Exclusive creation, with ownership-limited rollback. Laiqh."""
import os
from pathlib import Path
from .contracts import PROFILE, diagnostic, report
from .safety import SafetyError, ensure_plain, fingerprint, relfile, snapshot
from .templates import draft_files


def create_files(output, files, *, operation):
    owned, dirs = [], []
    lock = None
    root = None
    try:
        root = ensure_plain(output)
        if not root.exists():
            root.mkdir()  # Caller must supply an existing parent; do not create arbitrary ancestors.
            dirs.append(root)
        if not root.is_dir() or any(root.iterdir()):
            return report(operation, 'CONFLICT', diagnostics=[diagnostic('AUTH-CONFLICT', phase='generation')])
        lock = root / '.workflow-author.lock'
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b'workflow-author: in progress\n')
        lock_identity = fingerprint(lock.stat())
        for name, text in files.items():
            relfile(name)
            dest = root / name
            ensure_plain(dest)
            for parent in reversed(dest.parents):
                if parent == root or root not in parent.parents:
                    continue
                if not parent.exists():
                    parent.mkdir()
                    dirs.append(parent)
                ensure_plain(parent)
            with dest.open('xb') as stream:
                data = text.encode('utf-8')
                try:
                    stream.write(data)
                    stream.flush()
                finally:
                    # Include partially written self-created files in rollback, before closing.
                    owned.append((dest, fingerprint(os.fstat(stream.fileno())), data))
        # A non-cooperating writer must not turn a nonempty target into a successful create.
        present = snapshot(root)
        if present != {**files, '.workflow-author.lock': 'workflow-author: in progress\n'}:
            raise FileExistsError()
        if fingerprint(lock.stat()) == lock_identity:
            lock.unlink()
            lock = None
        return report(operation, 'CREATED', checks=[{'id': 'exclusive-generation', 'status': 'PASS'}])
    except (FileExistsError, SafetyError, OSError):
        for path, identity, intended in reversed(owned):
            try:
                ensure_plain(path)
                if fingerprint(path.stat()) == identity and intended.startswith(path.read_bytes()):
                    path.unlink()
            except (OSError, SafetyError):
                pass  # Uncertain ownership is never permission to delete.
        if lock is not None:
            try:
                if 'lock_identity' in locals() and fingerprint(lock.stat()) == lock_identity:
                    lock.unlink()
            except OSError:
                pass
        for folder in reversed(dirs):
            try:
                ensure_plain(folder)
                folder.rmdir()  # Only empty, self-created directories.
            except (OSError, SafetyError):
                pass
        return report(operation, 'CONFLICT', diagnostics=[diagnostic('AUTH-CONFLICT',
                      message='Target conflict or unsafe/unavailable creation path; inspect owned residue.', phase='generation')])


def generate(output, template=PROFILE):
    if template != PROFILE:
        return report('init', 'REJECTED', diagnostics=[diagnostic('AUTH-SUPPORT-010')])
    return create_files(output, draft_files(), operation='init')
