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
REFERENCE = Path(os.environ.get('WF2_REFERENCE_ROOT', ROOT / '.local/reference'))
TOOL_ROOT = Path(os.environ.get('WF2_TOOL_ROOT', REFERENCE / 'wf1-tools'))
AUTHOR_FILES = ('package-manifest.json', 'definitions/workflow-projection.json',
                'components/normalize-submission/declaration.json',
                'components/normalize-submission/implementation.py',
                'components/normalize-submission/test_normalize.py', 'acceptance.md')


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
        self.data = {'run_id': self.run_id, 'parent_run_id': parent, 'purpose': purpose,
                     'owner_pid': os.getpid(), 'registered_epoch': time.time(),
                     'roots': [], 'commands': [], 'snapshots': [], 'cleanups': [],
                     'observations': [], 'failures': [], 'children': [], 'local_synthetic_only': True}
        self.save()

    def save(self):
        temp = self.path / ('ledger-' + uuid.uuid4().hex + '.tmp')
        with temp.open('x', encoding='utf-8') as out:
            json.dump(self.data, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, self.path / 'ledger.json')

    def register(self, path, purpose, parent=None):
        import time
        path = local_path(path)
        if self.path.is_relative_to(path) or path.is_relative_to(self.path):
            raise ValueError('EVIDENCE_INSIDE_CLEANUP_TREE')
        if path.exists() or any(r['path'] == str(path) for r in self.data['roots']):
            raise ValueError('ROOT_ALREADY_OCCUPIED')
        self.data['roots'].append({'path': str(path), 'parent': str(parent) if parent else os.environ.get('WF2_PARENT_ROOT'),
            'purpose': purpose, 'run_id': self.run_id, 'owner_pid': os.getpid(),
            'registered_epoch': time.time(), 'state': 'reserved', 'seen_exists': False, 'snapshots': []})
        self.save()
        return path

    def process(self, argv, env=None, cwd=None, timeout=90):
        import time
        argv = list(map(str, argv))
        p = subprocess.Popen(argv, cwd=cwd or ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.live.append(p)
        entry = {'kind': 'process', 'argv': argv, 'cwd': str(cwd or ROOT), 'launcher_pid': p.pid,
                 'runtime_pid': None, 'started_epoch': time.time(), 'exit_code': None, 'exited': False}
        self.data['commands'].append(entry)
        self.save()
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
            handles = {}
            for path in sorted(root.rglob('lock')):
                if path.parent.name != 'host':
                    continue
                local_path(path)
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
            for path in sorted(root.rglob('*.sqlite')):
                local_path(path)
                db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=0)
                stack.callback(db.close)
                db.execute('BEGIN IMMEDIATE')
                stack.callback(db.rollback)
            yield handles

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
                code = '''import json,os,sqlite3,sys
from pathlib import Path
result={}
for p in Path(sys.argv[1]).rglob('*.sqlite'):
 db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:
  integrity=[r[0] for r in db.execute('PRAGMA integrity_check')]
  names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
  tables={n:[dict(r) for r in db.execute('SELECT * FROM "'+n.replace('"','""')+'" ORDER BY rowid')] for n in names}
  result[p.relative_to(sys.argv[1]).as_posix()]={'integrity_check':integrity,'tables':tables}
 finally:db.close()
print(json.dumps({'pid':os.getpid(),'databases':result}))
'''
                observed = self.process([sys.executable, '-B', '-c', code, slot / 'readback-copy'])
                assert observed['exit_code'] == 0, observed
                logical = json.loads(observed['stdout'])['databases']
                assert all(d['integrity_check'] == ['ok'] for d in logical.values()), 'SQLITE_SNAPSHOT_INVALID'
            snapshot = {'id': slot.name, 'root': str(root), 'exported_epoch': time.time(),
                'archive': str(archive), 'archive_sha256': sha256_bytes(archive.read_bytes()),
                'files': {n: {k: v for k, v in info.items() if k != 'bytes'} for n, info in files.items()},
                'directories': directories, 'sqlite_readback': logical,
                'sqlite_observer': observed, 'host_and_sqlite_write_locks_acquired': True}
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
        code = '''import json,os,sys
from pathlib import Path
roots={p:{'absent':not Path(p).exists(),'sqlite_files':[str(x) for x in Path(p).rglob('*') if x.is_file() and ('.sqlite' in x.name or x.suffix in ('.db','-wal','-shm'))]} for p in json.loads(sys.argv[1])}
print(json.dumps({'pid':os.getpid(),'roots':roots}))
'''
        receipt = self.process([sys.executable, '-B', '-c', code, json.dumps([r['path'] for r in self.data['roots']])])
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

    def cleanup_api(self, root, callback, method, args, export_root=None):
        import time
        snapshot = self.export(export_root or root)
        receipt = {'kind': 'api', 'method': method, 'args': list(map(str, args)),
                   'path': str(root), 'snapshot_id': snapshot['id'], 'started_epoch': time.time()}
        try:
            result = callback()
            receipt.update(returned=result, succeeded=True, ended_epoch=time.time())
        except BaseException as exc:
            receipt.update(error=type(exc).__name__ + ': ' + str(exc), succeeded=False, ended_epoch=time.time())
            self.data['cleanups'].append(receipt)
            self.save()
            raise
        self.data['cleanups'].append(receipt)
        self.save()
        self.observe()
        return result

    def remove_tree(self, root):
        return self.cleanup_api(root, lambda: shutil.rmtree(root), 'shutil.rmtree', [root])

    def cli_cleanup_receipt(self, root, snapshot, command):
        self.data['cleanups'].append({'kind': 'cli', 'path': str(root), 'snapshot_id': snapshot['id'],
                                      'command': command, 'succeeded': command['exit_code'] == 0})
        self.save()
        self.observe()

    def verify(self):
        import zipfile
        self.observe()
        for snapshot in self.data['snapshots']:
            archive = Path(snapshot['archive'])
            assert sha256_bytes(archive.read_bytes()) == snapshot['archive_sha256']
            with zipfile.ZipFile(archive) as z:
                assert all(sha256_bytes(z.read(n)) == row['sha256'] for n, row in snapshot['files'].items())
        closed = all(r['state'] in ('cleaned', 'absent_unobserved') for r in self.data['roots'])
        covered = all(not r['seen_exists'] or r['snapshots'] for r in self.data['roots'])
        result = {'all_closed': closed and covered, 'root_count': len(self.data['roots']),
                  'archives_verified': len(self.data['snapshots']), 'owned_processes_exited': all(p.poll() is not None for p in self.live)}
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
        for path, purpose in ((self.package, 'author generated package'), (self.materials, 'synthetic materials'),
                              (self.sandbox, 'installed runtime'), (self.root / 'sandbox.pending', 'installation staging')):
            self.audit.register(path, purpose=purpose, parent=self.root)
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
        return self.audit.export(self.root)

    def cli(self, *args, expected=0, cwd=None):
        snapshot = self.before_cleanup() if args and args[0] in ('host-cleanup', 'install-remove') else None
        result = self.run([sys.executable, '-B', str(ROOT / 'tools/runtime_package_cli.py'),
                          '--sandbox', str(self.sandbox), *args], expected=expected, cwd=cwd)
        if snapshot is not None:
            self.audit.cli_cleanup_receipt(self.sandbox, snapshot, self.commands[-1])
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
        if self.sandbox.exists():
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
