"""Owned generated fixtures and real process evidence. TEST ONLY. Laiqh."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from runtime_core.contract_adapter import digest
REFERENCE = Path(os.environ.get('WF2_REFERENCE_ROOT', ROOT / '.local/reference'))
TOOL_ROOT = Path(os.environ.get('WF2_TOOL_ROOT', REFERENCE / 'wf1-tools'))
AUTHOR_FILES = ('package-manifest.json', 'definitions/workflow-projection.json',
                'components/normalize-submission/declaration.json',
                'components/normalize-submission/implementation.py',
                'components/normalize-submission/test_normalize.py', 'acceptance.md')
ROOT_OBSERVER = '''import json,os,sys
from pathlib import Path
roots={p:{'absent':not Path(p).exists(),'sqlite_files':[str(x) for x in Path(p).rglob('*') if x.is_file() and ('.sqlite' in x.name or x.suffix in ('.db','-wal','-shm'))]} for p in json.loads(sys.argv[1])}
print(json.dumps({'pid':os.getpid(),'roots':roots}))
'''


def hashes(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def local_path(path):
    """Bound evidence operations to this worktree; never follow reparse points."""
    import stat
    path = Path(os.path.abspath(path))
    if path == ROOT / '.local' or not path.is_relative_to(ROOT / '.local'):
        raise ValueError('EVIDENCE_PATH_OUTSIDE_LOCAL')
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
                raise ValueError('EVIDENCE_REPARSE_REJECTED')
    return path


class EvidenceRun:
    """Local synthetic-root ledger; archive before destruction, fail closed.

    SQLite write reservations exclude active writers during the raw snapshot.
    Host locks exclude legitimate Host mutations. No data SQL is executed on
    the source. Logical reads use a retained archive copy in a fresh process.
    This is an owned-test workflow, not isolation from hostile same-account code.
    """
    def __init__(self, evidence_dir=None, run_id=None, purpose='fixture', owned_roots=()):
        import time
        parent = os.environ.get('WF2_RUN_ID')
        self.run_id = run_id or ((parent or 'wf2') + '-' + uuid.uuid4().hex)
        if not self.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in self.run_id):
            raise ValueError('INVALID_EVIDENCE_RUN_ID')
        base = local_path(evidence_dir or os.environ.get('WF2_EVIDENCE_DIR', ROOT / '.local/engineering-evidence/runs'))
        self.path = local_path(base / self.run_id)
        for root in owned_roots:
            root = local_path(root)
            if self.path.is_relative_to(root) or root.is_relative_to(self.path):
                raise ValueError('EVIDENCE_INSIDE_CLEANUP_TREE')
        # Exclusive creation, including for caller-selected run IDs.
        self.path.mkdir(parents=True, exist_ok=False)
        self.live = []
        self._frozen = None
        self.data = {'run_id': self.run_id, 'parent_run_id': parent, 'purpose': purpose,
                     'owner_pid': os.getpid(), 'registered_epoch': time.time(),
                     'roots': [], 'commands': [], 'snapshots': [], 'cleanups': [],
                     'reservation_evidence': [], 'transitions': [],
                     'observations': [], 'failures': [], 'children': [], 'local_synthetic_only': True}
        self.save()

    def save(self):
        temp = self.path / ('ledger-' + uuid.uuid4().hex + '.tmp')
        with temp.open('x', encoding='utf-8') as out:
            json.dump(self.data, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, self.path / 'ledger.json')

    def register(self, path, purpose, parent=None, creation_argv=None):
        import time
        path = local_path(path)
        if self.path.is_relative_to(path) or path.is_relative_to(self.path):
            raise ValueError('EVIDENCE_INSIDE_CLEANUP_TREE')
        if path.exists() or any(r['path'] == str(path) for r in self.data['roots']):
            raise ValueError('ROOT_ALREADY_OCCUPIED')
        self.data['roots'].append({'path': str(path), 'parent': str(parent) if parent else os.environ.get('WF2_PARENT_ROOT'),
            'purpose': purpose, 'run_id': self.run_id, 'owner_pid': os.getpid(),
            'registered_epoch': time.time(), 'state': 'reserved', 'seen_exists': False, 'snapshots': [],
            'creation_intent': ({'id': 'creation-' + uuid.uuid4().hex, 'argv': list(map(str, creation_argv)),
                                 'bound_epoch': time.time(), 'command': None} if creation_argv is not None else None)})
        self.save()
        return path

    def _has_prior_snapshot(self, row, before):
        return any(row['registered_epoch'] <= s['exported_epoch'] <= before and
                   Path(row['path']).is_relative_to(Path(s['root'])) for s in self.data['snapshots'])

    def bind_creation(self, roots, argv):
        """Bind the initial creation attempt before launch, never after loss."""
        import time
        argv = list(map(str, argv))
        registered = {r['path']: r for r in self.data['roots']}
        rows = [registered[str(local_path(root))] for root in roots]
        bound = [r for r in rows if r.get('creation_intent') and r['creation_intent']['command'] is not None]
        if bound:
            if len(bound) != len(rows):
                raise ValueError('CREATION_LIFECYCLE_MISMATCH')
            if not any(Path(r['path']).exists() for r in rows):
                raise ValueError('CREATION_LIFECYCLE_ALREADY_STARTED')
            return  # An idempotent install does not acquire a new birth proof.
        now = time.time()
        for row in rows:
            if (Path(row['path']).exists() or row['seen_exists'] or row['snapshots'] or
                    self._has_prior_snapshot(row, now) or
                    row.get('creation_intent') and row['creation_intent']['argv'] != argv):
                raise ValueError('CREATION_LIFECYCLE_ALREADY_STARTED')
        for row in rows:
            if row.get('creation_intent') is None:
                row['creation_intent'] = {'id': 'creation-' + uuid.uuid4().hex, 'argv': argv,
                                          'bound_epoch': now, 'command': None}
        self.save()

    def attach_creation_command(self, command):
        """Attach only the first process receipt to its already durable intent."""
        for row in self.data['roots']:
            intent = row.get('creation_intent')
            if intent and intent['command'] is None and intent['argv'] == command.get('argv'):
                assert intent['bound_epoch'] <= command['started_epoch'], 'LATE_CREATION_BINDING'
                intent['command'] = command
        self.save()

    def creation_command(self, root, command):
        try:
            row = next(r for r in self.data['roots'] if r['path'] == str(root))
            intent = row['creation_intent']
            return (intent is not None and intent['argv'] == command['argv'] and intent['command'] == command and
                    command in self.data['commands'] and command['kind'] in ('process', 'cli') and
                    row['registered_epoch'] <= intent['bound_epoch'] <= command['started_epoch'] <= command['ended_epoch'] and
                    not self._has_prior_snapshot(row, command['started_epoch']))
        except (KeyError, TypeError, ValueError, StopIteration):
            return False

    def process(self, argv, env=None, cwd=None, timeout=90):
        import time
        argv = list(map(str, argv))
        intents = [r for r in self.data['roots'] if r.get('creation_intent') and
                   r['creation_intent']['command'] is None and r['creation_intent']['argv'] == argv]
        for row in intents:
            if (row['seen_exists'] or row['snapshots'] or Path(row['path']).exists() or
                    self._has_prior_snapshot(row, time.time())):
                raise ValueError('CREATION_LIFECYCLE_ALREADY_STARTED')
        p = subprocess.Popen(argv, cwd=cwd or ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.live.append(p)
        entry = {'kind': 'process', 'argv': argv, 'cwd': str(cwd or ROOT), 'launcher_pid': p.pid,
                 'runtime_pid': None, 'started_epoch': time.time(), 'exit_code': None, 'exited': False}
        self.data['commands'].append(entry)
        self.attach_creation_command(entry)
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # No cleanup is permitted while an owned process may still write.
            entry['timed_out'] = True
            self.save()
            raise
        entry.update(exit_code=p.returncode, exited=p.poll() is not None, ended_epoch=time.time(),
                     stdout_raw_hex=stdout.hex(), stderr_raw_hex=stderr.hex(),
                     stdout=stdout.decode('utf-8', 'replace'), stderr=stderr.decode('utf-8', 'replace'))
        try:
            value = json.loads(stdout.decode('utf-8'))
            if isinstance(value, dict):
                entry['runtime_pid'] = value.get('pid')
        except (ValueError, UnicodeDecodeError):
            pass
        self.save()
        return entry

    def _inventory(self, root, handles=None):
        import stat
        files, directories, identities = {}, [], {}
        for path in sorted(root.rglob('*')):
            local_path(path)
            info = path.lstat()
            name = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                directories.append(name)
            elif stat.S_ISREG(info.st_mode):
                if handles and path in handles:
                    handle = handles[path]
                    handle.seek(0)
                    content = handle.read()
                elif self._frozen and (path.suffix == '.sqlite' or
                                       path.name.endswith(('.sqlite-wal', '.sqlite-shm'))):
                    # Closing a newly opened SQLite companion on POSIX can drop
                    # the process-wide advisory lock held by the write barrier.
                    raise ValueError('SQLITE_COMPANION_NOT_FROZEN')
                elif os.name == 'nt' and path.name.endswith('.sqlite-shm') and info.st_size:
                    # SQLite itself maps SHM: Windows byte-range locks reject
                    # ReadFile even in the owning process. Read-only mapping
                    # retains every byte while the SQLite writer lock is held.
                    import mmap
                    with path.open('rb') as handle:
                        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
                            content = view[:]
                else:
                    content = path.read_bytes()
                files[name] = {'sha256': sha256_bytes(content), 'size': len(content),
                               'links': info.st_nlink, 'bytes': content}
                identities.setdefault((info.st_dev, info.st_ino), []).append(name)
            else:
                raise ValueError('UNSUPPORTED_SNAPSHOT_FILE')
        for names in identities.values():
            if any(files[n]['links'] != len(names) for n in names):
                raise ValueError('HARDLINK_OUTSIDE_OWNED_SNAPSHOT')
        return files, directories

    @contextmanager
    def _locks(self, root):
        from contextlib import ExitStack
        import sqlite3
        with ExitStack() as stack:
            handles = dict(self._frozen['handles']) if self._frozen else {}
            for path in sorted(root.rglob('lock')):
                if path.parent.name != 'host':
                    continue
                local_path(path)
                if path in handles:
                    continue  # Generic cleanup already owns this Host lock.
                handle = stack.enter_context(path.open('r+b'))
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    def unlock(h=handle):
                        h.seek(0)
                        msvcrt.locking(h.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    def unlock(h=handle):
                        fcntl.flock(h.fileno(), fcntl.LOCK_UN)
                stack.callback(unlock)
                handles[path] = handle
            for path in (() if self._frozen else sorted(root.rglob('*.sqlite'))):
                local_path(path)
                db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=0)
                stack.callback(db.close)
                db.execute('BEGIN IMMEDIATE')
                stack.callback(db.rollback)
            yield handles

    @contextmanager
    def _write_barrier(self, root, delegated_sqlite=False):
        """Keep SQLite writers stopped through deletion; no hostile-code sandbox.

        Windows deny-write/share-delete handles also protect existing file bytes.
        POSIX retains SQLite reservations and advisory file locks. Other fixture
        writers must already have exited; arbitrary namespace mutation is not an
        authorized participant in this owned-test cleanup protocol.
        """
        from contextlib import ExitStack
        import sqlite3
        import time
        if self._frozen or any(p.poll() is None for p in self.live):
            raise ValueError('ACTIVE_OWNED_PROCESS')
        record = {'kind': 'windows-deny-write' if os.name == 'nt' else 'sqlite-and-advisory-locks',
                  'acquired_epoch': None, 'released_epoch': None,
                  'delegated_sqlite': delegated_sqlite}
        with ExitStack() as stack:
            handles = {}
            if os.name != 'nt' and not delegated_sqlite:
                # BEGIN may create WAL/SHM. Do it before freezing file handles,
                # otherwise _inventory would open and close an untracked SHM
                # descriptor and could release SQLite's POSIX advisory locks.
                for path in sorted(root.rglob('*.sqlite')):
                    local_path(path)
                    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=0)
                    stack.callback(db.close)
                    db.execute('BEGIN IMMEDIATE')
                    stack.callback(db.rollback)
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                create = kernel.CreateFileW
                create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                create.restype = wintypes.HANDLE
                close = kernel.CloseHandle
                close.argtypes = [wintypes.HANDLE]
                close.restype = wintypes.BOOL
            for path in sorted(root.rglob('*')):
                local_path(path)
                host_lock = path.name == 'lock' and path.parent.name == 'host'
                if not path.is_file() or (host_lock and delegated_sqlite):
                    continue  # A delegated product cleanup acquires its own lock.
                if os.name == 'nt':
                    # The product CLI checks delete sharing itself, after reading
                    # its Host metadata. Its preflight reads must remain possible.
                    access = 0xC0010000 if host_lock else (0x80000000 if delegated_sqlite else 0x80010000)
                    handle = create(str(path), access, 0x00000005, None, 3, 0, None)
                    if handle == ctypes.c_void_p(-1).value:
                        raise OSError(ctypes.get_last_error(), 'CLEANUP_WRITE_BARRIER_BUSY')
                    try:
                        fd = msvcrt.open_osfhandle(handle, (os.O_RDWR if host_lock else os.O_RDONLY) | os.O_BINARY)
                    except BaseException:
                        close(handle)
                        raise
                    handles[path] = stack.enter_context(os.fdopen(fd, 'r+b' if host_lock else 'rb'))
                    if host_lock:
                        msvcrt.locking(handles[path].fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    handle = stack.enter_context(path.open('rb'))
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles[path] = handle
            record['acquired_epoch'] = time.time()
            self._frozen = {'root': root, 'handles': handles, 'record': record}
            try:
                yield
            finally:
                self._frozen = None
                record['released_epoch'] = time.time()
                self.save()

    @staticmethod
    def _snapshot_identity(snapshot):
        # Closing SQLite's own snapshot connection can checkpoint/remove empty
        # WAL/SHM files. Compare the full logical DB (including schema), not those
        # self-generated transient bytes. Retain both raw archives unchanged.
        databases = set(snapshot['sqlite_readback'])
        sqlite_files = databases | {p + suffix for p in databases for suffix in ('-wal', '-shm')}
        return {'files': {p: value for p, value in snapshot['files'].items() if p not in sqlite_files},
                'directories': snapshot['directories'], 'databases': snapshot['sqlite_readback']}

    @staticmethod
    def _cleanup_files(snapshot, root):
        root, snapshot_root = Path(root), Path(snapshot['root'])
        require = root == snapshot_root or root.is_relative_to(snapshot_root)
        if not require:
            raise ValueError('CLEANUP_SNAPSHOT_ROOT_MISMATCH')
        prefix = '' if root == snapshot_root else root.relative_to(snapshot_root).as_posix() + '/'
        files = {name[len(prefix):]: row['sha256'] for name, row in snapshot['files'].items()
                 if name.startswith(prefix)}
        if not files:
            raise ValueError('CLEANUP_SNAPSHOT_EMPTY')
        return files

    def cleanup_digest(self, snapshot, root):
        return digest(self._cleanup_files(snapshot, root))['value']

    @contextmanager
    def cleanup_window(self, root, delegated_sqlite=False):
        root = local_path(root)
        before = self.export(root)
        try:
            # The real CLI acquires its own SQLite guard and compares this raw
            # digest before deletion. Holding our SQLite reservation too would
            # deadlock two legitimate lock owners on POSIX. General API fixture
            # removals still retain the full outer barrier through rmtree.
            with self._write_barrier(root, delegated_sqlite=delegated_sqlite):
                snapshot = self.export(root)
                if self._snapshot_identity(before) != self._snapshot_identity(snapshot):
                    raise ValueError('SNAPSHOT_CHANGED_BEFORE_CLEANUP')
                snapshot['preceding_snapshot_id'] = before['id']
                self.save()
                yield snapshot
        except BaseException as exc:
            self.data['failures'].append({'phase': 'cleanup_guard', 'root': str(root),
                'error': type(exc).__name__ + ': ' + str(exc), 'preserved': root.exists()})
            self.save()
            raise

    def _sqlite_readback(self, copy_root):
        """Read an archive copy in a fresh process and retain its raw receipt."""
        code = '''import json,os,sqlite3,sys
from pathlib import Path
result={}
for p in Path(sys.argv[1]).rglob('*.sqlite'):
 db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:
  integrity=[r[0] for r in db.execute('PRAGMA integrity_check')]
  names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
  tables={n:[dict(r) for r in db.execute('SELECT * FROM "'+n.replace('"','""')+'" ORDER BY rowid')] for n in names}
  schema=[dict(r) for r in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
  result[p.relative_to(sys.argv[1]).as_posix()]={'integrity_check':integrity,'tables':tables,'schema':schema}
 finally:db.close()
print(json.dumps({'pid':os.getpid(),'databases':result}))
'''
        observed = self.process([sys.executable, '-B', '-c', code, copy_root])
        try:
            payload = json.loads(observed['stdout'])
            logical = payload['databases']
            valid = (observed['exit_code'] == 0 and observed['exited'] is True and
                     observed['launcher_pid'] > 0 and payload['pid'] == observed['runtime_pid'] and
                     all(row['integrity_check'] == ['ok'] for row in logical.values()))
            return logical if valid else None, observed
        except (KeyError, TypeError, ValueError):
            return None, observed

    def export(self, root):
        """Export ALL present bytes (including manifest, identities, DB/WAL/SHM)."""
        import time
        import zipfile
        root = local_path(root)
        if not any(r['path'] == str(root) for r in self.data['roots']) or not root.is_dir():
            raise ValueError('UNOWNED_OR_MISSING_EXPORT_ROOT')
        if any(p.poll() is None for p in self.live):
            raise ValueError('ACTIVE_OWNED_PROCESS')
        for row in self.data['roots']:
            if Path(row['path']).is_relative_to(root) and Path(row['path']).exists():
                row.update(seen_exists=True, state='present')
        slot = self.path / ('snapshot-' + uuid.uuid4().hex)
        slot.mkdir()
        try:
            with self._locks(root) as handles:
                files, directories = self._inventory(root, handles)
                archive = slot / 'raw.zip'
                with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
                    for name in directories:
                        z.writestr(name + '/', b'')
                    for name, info in files.items():
                        z.writestr(name, info['bytes'])
                with zipfile.ZipFile(archive) as z:
                    assert z.testzip() is None
                    assert all(sha256_bytes(z.read(n)) == info['sha256'] for n, info in files.items())
                    # Read only a copy; WAL/SHM changes in this retained readback
                    # copy cannot alter raw.zip or the cleanup target.
                    z.extractall(slot / 'readback-copy')
                again, dirs_after = self._inventory(root, handles)
                assert files == again and directories == dirs_after, 'SNAPSHOT_CHANGED_DURING_EXPORT'
                logical, observed = self._sqlite_readback(slot / 'readback-copy')
                assert logical is not None, observed
            snapshot = {'id': slot.name, 'root': str(root), 'exported_epoch': time.time(),
                'archive': str(archive), 'archive_sha256': sha256_bytes(archive.read_bytes()),
                'files': {n: {k: v for k, v in info.items() if k != 'bytes'} for n, info in files.items()},
                'directories': directories, 'sqlite_readback': logical,
                'sqlite_observer': observed, 'host_and_sqlite_write_locks_acquired':
                    not (self._frozen and self._frozen['record']['delegated_sqlite'])}
            if self._frozen:
                snapshot['cleanup_barrier'] = self._frozen['record']
            self.data['snapshots'].append(snapshot)
            for row in self.data['roots']:
                if Path(row['path']).exists() and Path(row['path']).is_relative_to(root):
                    row['snapshots'].append(snapshot['id'])
            self.save()
            return snapshot
        except BaseException as exc:
            self.data['failures'].append({'phase': 'export', 'root': str(root), 'slot': str(slot),
                                         'error': type(exc).__name__ + ': ' + str(exc), 'preserved': root.exists()})
            self.save()
            raise

    def observe(self):
        receipt = self.process([sys.executable, '-B', '-c', ROOT_OBSERVER, json.dumps([r['path'] for r in self.data['roots']])])
        assert receipt['exit_code'] == 0, receipt
        result = json.loads(receipt['stdout'])
        self.data['observations'].append({'receipt': receipt, 'result': result})
        for row in self.data['roots']:
            if result['roots'][row['path']]['absent']:
                # An unobserved reserved path may have been atomically renamed
                # by the installer. Absence is not proof it never existed.
                row['state'] = 'cleaned' if row['seen_exists'] else 'absent_unobserved'
            else:
                row.update(state='present', seen_exists=True)
        self.save()
        return result

    def cleanup_api(self, root, *, snapshot=None, export_root=None):
        import time
        from contextlib import nullcontext
        from copy import deepcopy
        root = local_path(root)
        window = self.cleanup_window(export_root or root) if snapshot is None else nullcontext(snapshot)
        with window as snapshot:
            if (not self._frozen or self._frozen['record']['delegated_sqlite'] or not root.is_dir() or
                    snapshot is not self.data['snapshots'][-1] or
                    snapshot.get('cleanup_barrier') is not self._frozen['record'] or
                    not self._snapshot_contains(snapshot, root)):
                raise ValueError('UNBOUND_CLEANUP_SNAPSHOT')
            receipt = {'id': 'cleanup-' + uuid.uuid4().hex, 'kind': 'api', 'method': 'shutil.rmtree', 'args': [str(root)],
                       'covered_roots': [r['path'] for r in self.data['roots']
                                         if Path(r['path']).is_relative_to(root) and Path(r['path']).exists()],
                       'path': str(root), 'snapshot_id': snapshot['id'], 'started_epoch': time.time()}
            try:
                # The evidence owner invokes the actual operation. Callers may
                # not replace deletion with a callback and a claimed method tag.
                result = shutil.rmtree(root)
                receipt.update(returned=result, succeeded=True, ended_epoch=time.time())
            except BaseException as exc:
                receipt.update(error=type(exc).__name__ + ': ' + str(exc), succeeded=False, ended_epoch=time.time())
                self.data['commands'].append(deepcopy(receipt))
                self.data['cleanups'].append(receipt)
                self.save()
                raise
            self.observe()
            receipt['post_observation'] = deepcopy(self.data['observations'][-1])
            if not receipt['post_observation']['result']['roots'][str(root)]['absent']:
                receipt.update(succeeded=False, error='CLEANUP_POSTCONDITION_FAILED')
                self.data['commands'].append(deepcopy(receipt))
                self.data['failures'].append({'phase': 'cleanup_postcondition', 'root': str(root),
                                              'error': 'CLEANUP_POSTCONDITION_FAILED', 'preserved': root.exists()})
                self.save()
                raise ValueError('CLEANUP_POSTCONDITION_FAILED')
            self.data['commands'].append(deepcopy(receipt))
            self.data['cleanups'].append(receipt)
            self.save()
        return result

    def remove_tree(self, root):
        return self.cleanup_api(root)

    def cli_cleanup_receipt(self, root, snapshot, command):
        from copy import deepcopy
        root = local_path(root)
        receipt = {'id': 'cleanup-' + uuid.uuid4().hex, 'kind': 'cli',
            'path': str(root), 'snapshot_id': snapshot['id'], 'command': command,
            'started_epoch': command['started_epoch'], 'ended_epoch': command['ended_epoch'],
            'covered_roots': [r['path'] for r in self.data['roots']
                              if Path(r['path']).is_relative_to(root) and self._snapshot_contains(snapshot, r['path'])],
            'succeeded': command['exit_code'] == 0}
        self.observe()
        receipt['post_observation'] = deepcopy(self.data['observations'][-1])
        if not receipt['post_observation']['result']['roots'][str(root)]['absent']:
            receipt.update(succeeded=False, error='CLEANUP_POSTCONDITION_FAILED')
            self.data['failures'].append({'phase': 'cleanup_postcondition', 'root': str(root),
                                          'error': 'CLEANUP_POSTCONDITION_FAILED', 'preserved': root.exists()})
            self.save()
            raise ValueError('CLEANUP_POSTCONDITION_FAILED')
        self.data['cleanups'].append(receipt)
        self.save()

    @staticmethod
    def _snapshot_contains(snapshot, path):
        path, root = Path(path), Path(snapshot['root'])
        return path == root or (path.is_relative_to(root) and
                                path.relative_to(root).as_posix() in snapshot['directories'])

    def _valid_observation(self, observation):
        try:
            command = observation['receipt']
            argv = command['argv']
            raw = bytes.fromhex(command['stdout_raw_hex']).decode('utf-8')
            value = json.loads(raw)
            paths = json.loads(argv[4])
            registered = {r['path']: r for r in self.data['roots']}
            return (observation in self.data['observations'] and command in self.data['commands'] and
                    command['kind'] == 'process' and command['exit_code'] == 0 and command['exited'] is True and
                    not command.get('timed_out', False) and command['launcher_pid'] > 0 and
                    value['pid'] == command['runtime_pid'] and value['pid'] > 0 and
                    command['stdout'] == raw and value == observation['result'] and
                    len(argv) == 5 and argv[:4] == [sys.executable, '-B', '-c', ROOT_OBSERVER] and
                    len(paths) == len(set(paths)) and set(paths) == set(value['roots']) and
                    all(p in registered and registered[p]['registered_epoch'] <= command['started_epoch'] <=
                        command['ended_epoch'] and type(value['roots'][p]['absent']) is bool and
                        (not value['roots'][p]['absent'] or value['roots'][p]['sqlite_files'] == []) for p in paths))
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            return False

    def _valid_cleanup(self, receipt, snapshots, observation):
        """A missing path is not a receipt. Bind the actual action and its order."""
        try:
            snapshot = snapshots[receipt['snapshot_id']]
            root = receipt['path']
            registered = {r['path']: r for r in self.data['roots']}
            barrier = snapshot['cleanup_barrier']
            post = receipt['post_observation']
            post_command = post['receipt']
            if (receipt['succeeded'] is not True or root not in registered or
                    not self._snapshot_contains(snapshot, root) or
                    not registered[root]['registered_epoch'] <= snapshot['exported_epoch'] <=
                    receipt['started_epoch'] <= receipt['ended_epoch'] <= post_command['started_epoch'] <=
                    post_command['ended_epoch'] <= barrier['released_epoch'] or
                    not self._valid_observation(post) or not post['result']['roots'][root]['absent']):
                return False
            if not barrier['acquired_epoch'] <= snapshot['exported_epoch'] <= receipt['ended_epoch'] <= barrier['released_epoch']:
                return False
            if not receipt['covered_roots'] or any(p not in registered or
                    not Path(p).is_relative_to(root) or not self._snapshot_contains(snapshot, p) or
                    not registered[p]['snapshots'] or
                    snapshot['id'] != registered[p]['snapshots'][-1] for p in receipt['covered_roots']):
                return False
            if receipt['kind'] == 'api':
                if barrier.get('delegated_sqlite'):
                    return False
                commands = [c for c in self.data['commands'] if c.get('id') == receipt['id']]
                if commands != [receipt]:
                    return False
                return (receipt['method'] == 'shutil.rmtree' and
                        receipt['args'] == [root] and receipt['returned'] is None)
            if receipt['kind'] != 'cli':
                return False
            command = receipt['command']
            argv = command['argv']
            value = json.loads(bytes.fromhex(command['stdout_raw_hex']).decode('utf-8'))
            return (command in self.data['commands'] and command['exit_code'] == 0 and command['exited'] is True and
                    command['started_epoch'] == receipt['started_epoch'] and command['ended_epoch'] == receipt['ended_epoch'] and
                    command['launcher_pid'] > 0 and value['pid'] == command['runtime_pid'] and
                    argv[:3] == [sys.executable, '-B', str(ROOT / 'tools/runtime_package_cli.py')] and
                    argv[argv.index('--sandbox') + 1] == root and
                    argv[argv.index('--manifest') + 1] == str(Path(root) / 'manifest.json') and
                    argv[argv.index('--cleanup-digest') + 1] == self.cleanup_digest(snapshot, root) and
                    value['operation'] == 'host-cleanup' and value['operation'] in argv and
                    value['result']['storage_guarded'] is True and
                    value['result']['removed'] is True and
                    value['result']['cleanup_manifest'] == {'path': root, 'files_sha256': self._cleanup_files(snapshot, root)} and
                    value['result']['cleanup_digest'] == self.cleanup_digest(snapshot, root))
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            return False

    def record_noncreation(self, root, command):
        """The bounded verifier rejects unsupported export before creating roots."""
        root = local_path(root)
        proof = {'kind': 'verifier_rejected_before_creation', 'path': str(root), 'command': command}
        self.observe()
        proof['observation'] = self.data['observations'][-1]
        assert self._valid_noncreation(proof), 'INVALID_NONCREATION_PROOF'
        self.data['reservation_evidence'].append(proof)
        self.save()

    def _valid_noncreation(self, proof):
        try:
            command = proof['command']
            argv = command['argv']
            row = next(r for r in self.data['roots'] if r['path'] == proof['path'])
            observation = proof['observation']
            intent = row['creation_intent']
            return (proof['kind'] == 'verifier_rejected_before_creation' and
                    self.creation_command(row['path'], command) and
                    intent is not None and intent['argv'] == argv and intent['command'] == command and
                    not row['seen_exists'] and not row['snapshots'] and
                    not any(Path(row['path']).is_relative_to(Path(s['root'])) and
                            s['exported_epoch'] <= command['started_epoch'] for s in self.data['snapshots']) and
                    self._valid_observation(observation) and
                    command in self.data['commands'] and command['exit_code'] == 2 and command['exited'] is True and
                    argv[:3] == [sys.executable, '-B', str(ROOT / 'tools/verify_runtime_package.py')] and '--evidence-dir' in argv and
                    argv[argv.index('--sandbox') + 1] == proof['path'] and argv[argv.index('--scenario') + 1] != 'S01' and
                    'supports S01 only; no temporary root was created' in bytes.fromhex(command['stderr_raw_hex']).decode('utf-8') and
                    row['registered_epoch'] <= command['started_epoch'] <= command['ended_epoch'] <= observation['receipt']['started_epoch'] and
                    observation['result']['roots'][row['path']]['absent'])
        except (KeyError, ValueError, TypeError, IndexError, StopIteration):
            return False

    def record_activation(self, pending, active, command):
        """Record the one allowed pending-to-active transition explicitly."""
        pending, active = local_path(pending), local_path(active)
        proof = {'kind': 'install_activation', 'from': str(pending), 'to': str(active), 'command': command}
        assert not pending.exists() and active.is_dir() and self._valid_activation_command(proof), 'INVALID_ACTIVATION_PROOF'
        self.data['transitions'].append(proof)
        self.save()

    def record_failed_activation(self, pending, active, command):
        """A failed install may close only an explicitly observed inactive root."""
        pending, active = local_path(pending), local_path(active)
        observation = self.observe()
        proof = {'kind': 'install_failed_before_activation', 'path': str(active), 'pending': str(pending),
                 'command': command, 'observation': self.data['observations'][-1]}
        assert pending.is_dir() and not active.exists() and self._valid_failed_activation(proof, {}, []), 'INVALID_FAILED_ACTIVATION'
        self.data['reservation_evidence'].append(proof)
        self.save()

    def _valid_activation_command(self, proof):
        try:
            command = proof['command']
            value = json.loads(bytes.fromhex(command['stdout_raw_hex']).decode('utf-8'))
            registered = {r['path']: r for r in self.data['roots']}
            return (proof['kind'] == 'install_activation' and proof['from'] in registered and proof['to'] in registered and
                    proof['from'] == str(Path(proof['to']).with_name(Path(proof['to']).name + '.pending')) and
                    self.creation_command(proof['from'], command) and self.creation_command(proof['to'], command) and
                    command in self.data['commands'] and command['exit_code'] == 0 and command['exited'] is True and
                    command['launcher_pid'] > 0 and value['pid'] == command['runtime_pid'] and
                    value['operation'] == 'install' and command['argv'][:3] ==
                    [sys.executable, '-B', str(ROOT / 'tools/runtime_package_cli.py')] and
                    command['argv'][command['argv'].index('--sandbox') + 1] == proof['to'] and
                    registered[proof['from']]['registered_epoch'] <= command['started_epoch'] <= command['ended_epoch'])
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            return False

    def _valid_activation(self, proof, snapshots, cleanups):
        if not self._valid_activation_command(proof):
            return False
        registered = {r['path']: r for r in self.data['roots']}
        command = proof['command']
        active = proof['to']
        active_snapshots = [snapshots[sid] for sid in registered[active]['snapshots'] if sid in snapshots]
        return (not registered[proof['from']]['seen_exists'] and not registered[proof['from']]['snapshots'] and
                any(command['ended_epoch'] <= snap['exported_epoch'] and self._snapshot_contains(snap, active)
                    for snap in active_snapshots) and
                any(active in cleanup['covered_roots'] for cleanup in cleanups))

    def _valid_failed_activation(self, proof, snapshots, cleanups):
        try:
            command = proof['command']
            registered = {r['path']: r for r in self.data['roots']}
            observation = proof['observation']
            pending = proof['pending']
            active = proof['path']
            return (proof['kind'] == 'install_failed_before_activation' and pending in registered and active in registered and
                    self.creation_command(pending, command) and self.creation_command(active, command) and
                    pending == str(Path(active).with_name(Path(active).name + '.pending')) and
                    command in self.data['commands'] and command['exit_code'] == 86 and command['exited'] is True and
                    command['argv'][:3] == [sys.executable, '-B', str(ROOT / 'tools/runtime_package_cli.py')] and
                    'install' in command['argv'] and
                    command['argv'][command['argv'].index('--sandbox') + 1] == active and
                    self._valid_observation(observation) and
                    command['ended_epoch'] <= observation['receipt']['started_epoch'] <= observation['receipt']['ended_epoch'] and
                    observation['result']['roots'][active]['absent'] is True and
                    observation['result']['roots'][pending]['absent'] is False and
                    not registered[active]['seen_exists'] and not registered[active]['snapshots'] and
                    (not snapshots and not cleanups or
                     any(self._snapshot_contains(snapshot, pending) for snapshot in snapshots.values()) and
                     any(pending in cleanup['covered_roots'] for cleanup in cleanups)))
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            return False

    def _valid_reservation(self, row, snapshots, cleanups):
        if row['seen_exists'] or row['snapshots']:
            return False
        for proof in self.data['reservation_evidence']:
            if proof['path'] != row['path']:
                continue
            if self._valid_noncreation(proof) or self._valid_failed_activation(proof, snapshots, cleanups):
                return True
        for proof in self.data['transitions']:
            if proof['from'] == row['path'] and self._valid_activation(proof, snapshots, cleanups):
                return True
        return False

    def _valid_sqlite_observer(self, snapshot):
        try:
            observer = snapshot['sqlite_observer']
            archive = Path(snapshot['archive'])
            raw = bytes.fromhex(observer['stdout_raw_hex']).decode('utf-8')
            value = json.loads(raw)
            argv = observer['argv']
            return (observer in self.data['commands'] and observer['kind'] == 'process' and
                    observer['exit_code'] == 0 and observer['exited'] is True and
                    observer['launcher_pid'] > 0 and observer['runtime_pid'] == value['pid'] and
                    observer['stdout'] == raw and argv[-1] == str(archive.parent / 'readback-copy') and
                    value['databases'] == snapshot['sqlite_readback'] and
                    all(row['integrity_check'] == ['ok'] for row in value['databases'].values()))
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            return False

    def _valid_snapshot(self, snapshot, snapshots, positions):
        import zipfile
        copy = None
        try:
            archive = Path(snapshot['archive'])
            if (archive.name != 'raw.zip' or archive.parent.name != snapshot['id'] or
                    not archive.is_relative_to(self.path) or
                    sha256_bytes(archive.read_bytes()) != snapshot['archive_sha256'] or
                    not self._valid_sqlite_observer(snapshot)):
                return False
            if 'cleanup_barrier' in snapshot:
                preceding_id = snapshot.get('preceding_snapshot_id')
                preceding = snapshots.get(preceding_id)
                if (preceding is None or positions[preceding_id] >= positions[snapshot['id']] or
                        preceding['root'] != snapshot['root'] or
                        preceding['exported_epoch'] > snapshot['exported_epoch']):
                    return False
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                if (z.testzip() is not None or
                        set(names) != set(snapshot['files']) | {d + '/' for d in snapshot['directories']} or
                        any(Path(name).is_absolute() or '..' in Path(name).parts for name in names) or
                        not all(sha256_bytes(z.read(name)) == row['sha256'] for name, row in snapshot['files'].items())):
                    return False
                copy = archive.parent / ('verify-readback-' + uuid.uuid4().hex)
                z.extractall(copy)
            logical, _ = self._sqlite_readback(copy)
            return logical is not None and logical == snapshot['sqlite_readback']
        except (KeyError, OSError, TypeError, ValueError, zipfile.BadZipFile):
            return False
        finally:
            if copy is not None:
                shutil.rmtree(copy, ignore_errors=True)

    def verify(self):
        self.observe()
        snapshots = {s['id']: s for s in self.data['snapshots']}
        positions = {s['id']: index for index, s in enumerate(self.data['snapshots'])}
        valid_snapshots = {sid: snapshot for sid, snapshot in snapshots.items()
                           if self._valid_snapshot(snapshot, snapshots, positions)}
        observation = self.data['observations'][-1]
        assert self._valid_observation(observation), 'INVALID_FINAL_OBSERVATION'
        valid = [c for c in self.data['cleanups'] if c.get('snapshot_id') in valid_snapshots and
                 self._valid_cleanup(c, valid_snapshots, observation)]
        reservations = {r['path'] for r in self.data['roots'] if self._valid_reservation(r, valid_snapshots, valid)}
        unclosed = [r['path'] for r in self.data['roots'] if
                    not observation['result']['roots'][r['path']]['absent'] or
                    not (r['path'] in reservations or any(r['path'] in c['covered_roots'] for c in valid))]
        for row in self.data['roots']:
            if row['path'] not in unclosed:
                row['state'] = 'reservation_closed' if row['path'] in reservations else 'cleaned'
        exited = all(p.poll() is not None for p in self.live)
        result = {'all_closed': not unclosed and exited, 'root_count': len(self.data['roots']),
                  'unclosed_roots': unclosed, 'valid_cleanup_count': len(valid), 'reservation_count': len(reservations),
                  'archives_verified': len(valid_snapshots),
                  'invalid_snapshot_ids': [sid for sid in snapshots if sid not in valid_snapshots],
                  'owned_processes_exited': exited}
        self.data['verification'] = result
        self.save()
        assert result['all_closed'] and result['owned_processes_exited'], result
        return result


class Generated:
    def __init__(self):
        self.root = ROOT / '.local' / ('test-package-' + uuid.uuid4().hex)
        self.audit = EvidenceRun(purpose='generated-package', owned_roots=[self.root])
        self.audit.register(self.root, purpose='owned generation and installation')
        self.root.mkdir()
        self.package, self.materials, self.sandbox = (self.root / name for name in ('package', 'materials', 'sandbox'))
        for path, purpose in ((self.package, 'author generated package'), (self.materials, 'synthetic materials')):
            self.audit.register(path, purpose=purpose, parent=self.root)
        self._runtime_registered = False
        self.commands = []
        self.evidence = self.audit.path / 'generated-receipt.json'
        self.env = {**os.environ, 'WF2_TOOL_ROOT': str(TOOL_ROOT), 'WF2_REFERENCE_ROOT': str(REFERENCE),
                    'WF2_PARENT_ROOT': str(self.root),
                    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'}
        self.run([sys.executable, '-B', str(TOOL_ROOT / 'tools/workflow_author.py'), 'init',
                  '--template', 'single-code-output-v1', '--output', str(self.package), '--format', 'json'])
        self.run([sys.executable, '-B', str(TOOL_ROOT / 'tools/workflow_author_synthetic.py'),
                  'prepare', '--output', str(self.materials), '--format', 'json'])
        self.draft_hashes = hashes(self.package)
        # Only author-owned completion fields are filled; generated Skill assets are not replaced.
        for name in AUTHOR_FILES:
            shutil.copyfile(REFERENCE / 'l3/package' / name, self.package / name)
        assert hashes(self.package) == hashes(REFERENCE / 'l3/package')
        assert hashes(self.materials) == hashes(REFERENCE / 'l3/materials')
        dump(self.root / 'generation-manifest.json', {'root': str(self.root), 'files': hashes(self.root),
             'author_completed': list(AUTHOR_FILES), 'draft_hashes': self.draft_hashes})

    def run(self, argv, expected=0, cwd=None):
        entry = self.audit.process(argv, env=self.env, cwd=cwd, timeout=90)
        entry['pid'] = entry['launcher_pid']  # Preserve legacy receipt field.
        self.commands.append(entry)
        self.save()
        assert entry['exit_code'] == expected, entry
        stdout = bytes.fromhex(entry['stdout_raw_hex']).decode('utf-8')
        result = json.loads(stdout) if stdout.strip() else None
        self.save()
        return result

    def before_cleanup(self):
        return self.audit.cleanup_window(self.root, delegated_sqlite=True)

    def ensure_runtime_roots(self):
        if self._runtime_registered:
            return
        self.audit.register(self.sandbox, purpose='installed runtime', parent=self.root)
        self.audit.register(self.sandbox.with_name(self.sandbox.name + '.pending'),
                            purpose='installation staging', parent=self.root)
        self._runtime_registered = True

    def cli(self, *args, expected=0, cwd=None):
        from contextlib import nullcontext
        if args and args[0] == 'install':
            self.ensure_runtime_roots()
            self.audit.bind_creation([self.sandbox, self.sandbox.with_name(self.sandbox.name + '.pending')],
                [sys.executable, '-B', ROOT / 'tools/runtime_package_cli.py', '--sandbox', self.sandbox, *args])
        window = self.before_cleanup() if args and args[0] in ('host-cleanup', 'install-remove') else nullcontext()
        with window as snapshot:
            cli_args = list(args)
            if snapshot is not None and args[0] == 'host-cleanup':
                cli_args.extend(('--cleanup-digest', self.audit.cleanup_digest(snapshot, self.sandbox)))
            result = self.run([sys.executable, '-B', str(ROOT / 'tools/runtime_package_cli.py'),
                              '--sandbox', str(self.sandbox), *cli_args], expected=expected, cwd=cwd)
            if args and args[0] == 'install' and self.audit.creation_command(self.sandbox, self.commands[-1]):
                pending = self.sandbox.with_name(self.sandbox.name + '.pending')
                if self.commands[-1]['exit_code'] == 0:
                    self.audit.record_activation(pending, self.sandbox, self.commands[-1])
                elif pending.is_dir() and not self.sandbox.exists():
                    self.audit.record_failed_activation(pending, self.sandbox, self.commands[-1])
            if snapshot is not None and self.commands[-1]['exit_code'] == 0:
                self.audit.cli_cleanup_receipt(self.sandbox, snapshot, self.commands[-1])
            elif snapshot is not None:
                self.audit.data['failures'].append({'phase': 'cleanup_command', 'root': str(self.sandbox),
                    'error': 'exit_code=' + str(self.commands[-1]['exit_code']), 'preserved': self.sandbox.exists()})
                self.audit.save()
        return result

    def request(self, operation, payload, key=None, expected=0):
        name = uuid.uuid4().hex
        path = self.sandbox / 'requests' / (name + '.json')
        dump(path, {'request_id': 'req-' + name, 'idempotency_key': key or 'key-' + name, 'payload': payload})
        return self.cli(operation, '--request', str(path), expected=expected)

    def setup(self):
        self.initial = self.cli('install', '--package', str(self.package), '--materials', str(self.materials),
                                '--fixture', 'normalize-l3-v1')['result']
        registration = self.cli('register', '--request', self.initial['register_request'])['result']
        self.registration_id = registration['registration_id']
        self.request('set-state', {'registration_id': self.registration_id, 'expected_revision': 1, 'target_state': 'ENABLED'})
        self.create_payload = {'registration_id': self.registration_id, 'input_ref': self.initial['input_ref'],
                               'object_refs': self.initial['object_refs']}
        return self

    def save(self):
        dump(self.evidence, {'commands': self.commands, 'root': str(self.root), 'cleaned': not self.root.exists()})

    def cleanup(self):
        if self._runtime_registered and self.sandbox.exists():
            self.cli('host-cleanup', '--manifest', str(self.sandbox / 'manifest.json'))
        # This test owns the entire generation directory; record its exact inventory first.
        from runtime_core.synthetic_host import safe_path
        for path in self.root.rglob('*'):
            safe_path(path)
            if path.is_file():
                assert path.stat().st_nlink == 1
        inventory = hashes(self.root)
        self.save()
        self.audit.remove_tree(self.root)
        observed = self.run([sys.executable, '-B', '-c',
            'import pathlib,sys,json,os; print(json.dumps({"absent":not pathlib.Path(sys.argv[1]).exists(),"pid":os.getpid()}))', str(self.root)])
        assert observed['absent']
        dump(self.evidence, {'commands': self.commands, 'cleaned': True, 'cleanup_manifest': inventory,
                            'root': str(self.root), 'missing_readback': observed})
        self.audit.verify()


@contextmanager
def generated():
    g = Generated()
    yield g
    # Never erase evidence on an unexpected failure.
    g.cleanup()
