"""Bounded no-follow filesystem operations. No untrusted code execution. Laiqh."""
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_FILE = 2_000_000
MAX_FILES = 256
MAX_TOTAL = 20_000_000


class SafetyError(ValueError):
    def __init__(self, code, file=None):
        self.code, self.file = code, file
        super().__init__(code)


def linklike(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def ensure_plain(path):
    """Inspect every existing ancestor, including Windows junctions."""
    if not isinstance(path, (str, os.PathLike)) or '\x00' in os.fspath(path):
        raise SafetyError('PATH_INVALID')
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if linklike(info):
            raise SafetyError('PATH_LINK_REJECTED')
    return path


def relfile(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise SafetyError('PATH_INVALID')
    parts = value.split('/')
    if value.startswith('/') or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts):
        raise SafetyError('PATH_INVALID')
    if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in parts):
        raise SafetyError('PATH_INVALID')
    if any(ord(c) < 32 for c in value) or not re.fullmatch(r'[\w .()/@+-]+', value):
        raise SafetyError('PATH_INVALID')
    return PurePosixPath(value).as_posix()


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def snapshot(root):
    """Read each regular file once, with limits before and during reads."""
    root = ensure_plain(root)
    if not root.is_dir():
        raise SafetyError('PACKAGE_UNAVAILABLE')
    texts, total, entries = {}, 0, 0
    pending = [root]
    while pending:
        folder = pending.pop()
        ensure_plain(folder)
        with os.scandir(folder) as scan:
            for entry in scan:
                entries += 1
                if entries > MAX_FILES * 2:
                    raise SafetyError('ENTRY_LIMIT')
                path = Path(entry.path)
                name = path.relative_to(root).as_posix()
                relfile(name)
                # Windows DirEntry metadata reports st_nlink=0; lstat supplies real identity.
                info = path.lstat()
                if linklike(info):
                    raise SafetyError('PATH_LINK_REJECTED')
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise SafetyError('SPECIAL_FILE_REJECTED')
                if len(texts) >= MAX_FILES or info.st_size > MAX_FILE or total + info.st_size > MAX_TOTAL:
                    raise SafetyError('INPUT_TOO_LARGE')
                ensure_plain(path)
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                try:
                    fd = os.open(path, flags)
                    with os.fdopen(fd, 'rb') as stream:
                        opened = os.fstat(stream.fileno())
                        if fingerprint(opened) != fingerprint(info):
                            raise SafetyError('INPUT_CHANGED')
                        data = stream.read(min(MAX_FILE, MAX_TOTAL - total) + 1)
                        after = os.fstat(stream.fileno())
                    ensure_plain(path)
                    if fingerprint(after) != fingerprint(info) or fingerprint(path.stat()) != fingerprint(info):
                        raise SafetyError('INPUT_CHANGED')
                except OSError:
                    raise SafetyError('INPUT_UNAVAILABLE') from None
                if len(data) > MAX_FILE or total + len(data) > MAX_TOTAL:
                    raise SafetyError('INPUT_TOO_LARGE')
                total += len(data)
                try:
                    text = data.decode('utf-8')
                    if '\x00' in text:
                        raise UnicodeError()
                except UnicodeError:
                    raise SafetyError('INPUT_ENCODING_INVALID') from None
                texts[name] = text
    return texts
