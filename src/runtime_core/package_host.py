"""Explicit TEST ONLY host for one reviewed normalize package. Laiqh."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import os
import shutil

from .contract_adapter import ContractError, digest, fixture_modules, key, load_json, require
from .package_install import binding_snapshot, verify_installation
from .store import Store
from .synthetic_host import Host, START, END, ident, pid_alive, save

# A separate POSIX lock owner prevents this process (or another thread) closing
# an unrelated SQLite descriptor from silently releasing our advisory locks.
# Whole-file record locks overlap SQLite's rollback and WAL shared main-file
# locks without opening SQLite or creating/checkpointing WAL/SHM files.
SQLITE_CLEANUP_GUARD = '''import fcntl,json,os,stat,sys
handles=[]
try:
 for path in json.loads(sys.argv[1]):
  fd=os.open(path,os.O_RDWR|getattr(os,'O_NOFOLLOW',0));handles.append(fd)
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise OSError('not a single owned file')
  fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 print(json.dumps({'ready':True,'pid':os.getpid()}),flush=True)
 sys.stdin.buffer.read(1)
except OSError:
 print(json.dumps({'ready':False,'pid':os.getpid()}),flush=True)
finally:
 for fd in reversed(handles):os.close(fd)
'''


def package_state(sandbox_id, projection, materials):
    # Reuse the P2 fixture's independent issuance shape, not its demo projection.
    _, p2 = fixture_modules()
    fixture = p2.p2_fixture()
    fixture.authority.records.clear()
    fixture.authority.views.clear()
    for row in materials['records']:
        reference = row['ref']
        fixture.authority.put('provider' if reference['kind'] == 'provider' else 'definition', reference, row)
    deployment, instance, namespace = ident('deployment'), ident('instance'), ident('namespace')
    fixture.context = replace(fixture.context, deployment_id=deployment, instance_id=instance, namespace=namespace)
    fixture.projection = deepcopy(projection)
    admission_ref = {**fixture.admission['ref'], 'id': ident('admission')}
    grant_ref = {**fixture.grant['ref'], 'id': ident('grant')}
    fixture.admission.update(ref=admission_ref, business_ref=projection['business_ref'],
        definition_ref=projection['definition_ref'], projection_digest=digest(projection),
        provider_bindings=deepcopy(projection['provider_bindings']), deployment_ids=[deployment])
    fixture.grant.update(ref=grant_ref, admission_ref=admission_ref, instance_id=instance,
                         deployment_id=deployment, namespace=namespace)
    fixture.policy['namespace'] = namespace
    fixture.ownership.update(grant_ref=grant_ref, instance_id=instance, deployment_id=deployment, namespace=namespace)
    fixture.request.update(projection=deepcopy(projection), admission_ref=admission_ref,
                           ownership_grant_ref=grant_ref, instance_id=instance, deployment_id=deployment, namespace=namespace)
    p2.install_p2(fixture)
    scope = deepcopy(fixture.context.scope)
    source = {'object_type': 'synthetic-source', 'namespace': 'synthetic', 'id': 'normalize-input', 'scope': scope}
    output_source = {**deepcopy(source), 'id': 'normalize-executor'}
    content = {'text': '  SYNTHETIC  sample  '}
    reference = {'evidence_id': ident('input'), 'digest': digest(content), 'scope': deepcopy(scope),
                 'observed_at': START, 'valid_until': END, 'source_ref': source,
                 'retention_policy_ref': 'm1-sandbox-lifetime'}
    return {'sandbox_id': sandbox_id, 'identity': {'sandbox_id': sandbox_id, 'instance_id': instance,
            'deployment_id': deployment, 'namespace': namespace}, 'scope': scope,
            'epoch': fixture.context.epoch, 'now': START, 'time_floor': START, 'revocation_floor': 4,
            'authorization_revision': 1, 'records': [[a, b, c] for (a, b), c in fixture.authority.records.items()],
            'views': [[a, b, c] for (a, b), c in fixture.authority.views.items()], 'request': fixture.request,
            'projection': deepcopy(projection), 'installed': deepcopy(projection['provider_bindings']),
            'permissions': {'operation': True, 'read': True},
            'inputs': {reference['evidence_id']: {'ref': reference, 'content': content}},
            'current_input': reference, 'source': source, 'output_source': output_source,
            'fault': None, 'rule_mode': 'ALLOW', 'output_mode': 'normal', 'package_host_version': 'wf2-host-v1'}


class PackageHost(Host):
    def initialize(self):
        # Never fall back to echo or automatically trust static material.
        require(False, 'UNAUTHORIZED')

    def initialize_package(self, record, projection, materials):
        state = package_state(ident('sandbox'), projection, materials)
        state['storage_path'] = str(self.path)
        record = deepcopy(record)
        record['admission_ref'] = deepcopy(state['request']['admission_ref'])
        record['record_digest'] = digest(record)
        state['package_installation'] = binding_snapshot(record)
        save(self.path / 'host/installation.json', record)
        save(self.path / 'host/state.json', state)
        (self.path / 'host/lock').write_bytes(b'0')
        save(self.path / 'manifest.json', {'sandbox_id': state['sandbox_id'], 'path': str(self.path),
             'synthetic_only': True, 'directories': ['host', 'runtime', 'requests', 'observations']})
        self.state = state
        Store(self.path / 'runtime/runtime.sqlite', state['identity']).initialize()
        payload = {k: deepcopy(projection[k]) for k in ('business_ref', 'definition_ref', 'contract_version', 'provider_bindings')}
        payload['admission_ref'] = deepcopy(record['admission_ref'])
        save(self.path / 'requests/register.json', {'request_id': ident('req'), 'idempotency_key': 'register-one', 'payload': payload})
        return {'installation_id': record['installation_id'], 'record_digest': record['record_digest'],
                'sandbox_id': state['sandbox_id'], 'input_ref': state['current_input'], 'object_refs': [state['source']]}

    def reload(self):
        super().reload()
        require(self.state.get('package_host_version') == 'wf2-host-v1', 'HOST_BINDING_MISMATCH')

    def resolve_binding(self, payload):
        binding = super().resolve_binding(payload)
        record, _, _ = verify_installation(self.path)
        binding['package_installation'] = binding_snapshot(record)
        return binding

    def validate(self, binding):
        super().validate(binding)
        record, _, projection = verify_installation(self.path)
        require(binding.get('package_installation') == self.state.get('package_installation') == binding_snapshot(record),
                'VERSION_CONFLICT')
        require(binding['projection'] == projection and binding['admission_ref'] == record['admission_ref'], 'VERSION_CONFLICT')

    def remember_request(self, path):
        # Requests outside this sandbox remain outside our cleanup ownership.
        if path.parent != self.path / 'requests':
            return
        from .package_install import read_plain, sha256
        with self.lock():
            index_path = self.path / 'host/request-index.json'
            index = load_json(index_path) if index_path.exists() else {}
            index[path.name] = sha256(read_plain(path))
            save(index_path, index)

    @contextmanager
    def cleanup_lock(self):
        """Hold the Host write lock through checked destruction.

        Host.lock intentionally releases its lock before Host.cleanup removes the
        directory, because its normal Windows file handle cannot be deleted. This
        TEST ONLY path uses a delete-share handle instead, so a control command
        cannot mutate state between the inventory check and rmtree.
        """
        from .synthetic_host import safe_path
        lock_path = safe_path(self.path / 'host/lock')
        require(lock_path.is_file(), 'HOST_BINDING_MISMATCH')
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            create = api.CreateFileW
            create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            create.restype = wintypes.HANDLE
            close = api.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close.restype = wintypes.BOOL
            handle = create(str(lock_path), 0xC0010000, 0x00000005, None, 3, 0, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ContractError('IN_PROGRESS') from None
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
            except BaseException:
                close(handle)
                raise
            stream = os.fdopen(fd, 'r+b')
            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                stream.close()
                raise ContractError('IN_PROGRESS') from None
            try:
                self.reload()
                yield stream
            finally:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    stream.close()
            return
        import fcntl
        with lock_path.open('r+b') as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ContractError('IN_PROGRESS') from None
            try:
                self.reload()
                yield stream
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def cleanup_storage_guard(self):
        """Stop SQLite writes before delete; caller must hold cleanup_lock."""
        from contextlib import ExitStack
        import stat
        from .package_install import plain_path
        paths = []
        for path in sorted(self.path.rglob('*')):
            plain_path(path)
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'SANDBOX_INVALID')
            if path != self.path / 'host/lock':
                paths.append(path)
        # Host-owned metadata cannot change under cleanup_lock. Read it before
        # requesting DELETE access: ordinary Python read handles do not opt in
        # to delete sharing and cannot reopen these files afterwards on Windows.
        metadata = {'processes': [(p, load_json(p)) for p in
                                  (self.path / 'observations').glob('process-*.json')]}
        index_path = self.path / 'host/request-index.json'
        metadata['requests'] = set(load_json(index_path)) if index_path.exists() else set()
        with ExitStack() as stack:
            handles = {}
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt
                api = ctypes.WinDLL('kernel32', use_last_error=True)
                create = api.CreateFileW
                create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                create.restype = wintypes.HANDLE
                close = api.CloseHandle
                close.argtypes = [wintypes.HANDLE]
                close.restype = wintypes.BOOL
                for path in paths:
                    # Request DELETE access too: a pre-existing read-only handle
                    # may allow reads but deny deletion. Detect it now, not after
                    # rmtree has already removed the other owned files.
                    handle = create(str(path), 0x80010000, 0x00000005, None, 3, 0, None)
                    if handle == ctypes.c_void_p(-1).value:
                        raise ContractError('IN_PROGRESS') from None
                    try:
                        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
                    except BaseException:
                        close(handle)
                        raise
                    handles[path] = stack.enter_context(os.fdopen(fd, 'rb'))
                yield {'handles': handles, 'process': None, **metadata}
                return
            import selectors
            import subprocess
            import sys
            databases = [str(p) for p in paths if p.name.endswith(('.sqlite', '.sqlite-wal', '.sqlite-shm'))]
            guard = subprocess.Popen([sys.executable, '-B', '-c', SQLITE_CLEANUP_GUARD, json.dumps(databases)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(guard.stdout, selectors.EVENT_READ)
                    require(bool(selector.select(timeout=10)), 'IN_PROGRESS')
                ready = json.loads(guard.stdout.readline(2048))
                require(ready.get('ready') is True and ready.get('pid') == guard.pid and guard.poll() is None,
                        'IN_PROGRESS')
                yield {'handles': handles, 'process': guard, **metadata}
            finally:
                guard.stdin.close()
                try:
                    guard.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    guard.kill()
                    guard.wait(timeout=5)
                guard.stdout.close()
                guard.stderr.close()

    def cleanup(self, manifest, cleanup_digest=None):
        import re
        from .package_install import MATERIALS_FILES, PACKAGE_FILES, plain_path, read_plain, sha256
        from .synthetic_host import safe_path
        require(safe_path(manifest) == self.path / 'manifest.json', 'SANDBOX_INVALID')
        # Legacy non-archival callers remain supported. Evidence callers supply
        # their frozen digest; absence is never accepted by the evidence ledger.
        require(cleanup_digest is None or (type(cleanup_digest) is str and len(cleanup_digest) == 64 and
                all(c in '0123456789abcdef' for c in cleanup_digest)), 'INPUT_INVALID')
        with self.cleanup_lock() as lock_handle, self.cleanup_storage_guard() as guard:
            for process, state in guard['processes']:
                safe_path(process)
                require(not pid_alive(state['pid']), 'IN_PROGRESS')
            requests = guard['requests']
            allowed = {'manifest.json', 'host/state.json', 'host/lock', 'host/installation.json',
                       'host/install-receipt.json', 'host/request-index.json', 'requests/register.json',
                       'requests/register-variant.json', 'observations/install-pending.json',
                       'observations/static-check.json', 'observations/providers.jsonl',
                       'runtime/runtime.sqlite', 'runtime/runtime.sqlite-wal', 'runtime/runtime.sqlite-shm'}
            allowed |= {'host/package/' + name for name in PACKAGE_FILES}
            allowed |= {'host/materials/' + name for name in MATERIALS_FILES}
            allowed |= {'requests/' + name for name in requests}
            inventory = {}
            for path in self.path.rglob('*'):
                plain_path(path)
                if path.is_dir():
                    continue
                name = path.relative_to(self.path).as_posix()
                known_generated = re.fullmatch(r'(?:host/(?:intent-case-|output-|execution-output-)|observations/process-session-)[0-9a-f]{32}\.json', name)
                require(name in allowed or known_generated is not None, 'SANDBOX_INVALID')
                if name != 'host/lock':
                    if os.name == 'nt':
                        require(path in guard['handles'], 'CLEANUP_SNAPSHOT_MISMATCH')
                        stream = guard['handles'][path]
                        stream.seek(0)
                        content = stream.read(32_000_001)
                        require(len(content) <= 32_000_000, 'SANDBOX_INVALID')
                    else:
                        content = read_plain(path, maximum=32_000_000)
                    inventory[name] = sha256(content)
            # Read through the lock-owning handle. On Windows a second handle can
            # be rejected by the byte-range lock even in this same process.
            lock_handle.seek(0)
            inventory['host/lock'] = sha256(lock_handle.read())
            actual_digest = digest(inventory)['value']
            require(cleanup_digest is None or actual_digest == cleanup_digest, 'CLEANUP_SNAPSHOT_MISMATCH')
            for parent, dirs, files in os.walk(self.path, followlinks=False):
                for name in dirs + files:
                    safe_path(Path(parent) / name)
            require(set(p.name for p in self.path.iterdir()) <= {'manifest.json', 'host', 'runtime', 'requests', 'observations'},
                    'SANDBOX_INVALID')
            require(guard['process'] is None or guard['process'].poll() is None, 'IN_PROGRESS')
            shutil.rmtree(self.path)
            require(not self.path.exists(), 'STORAGE_INVALID')
        return {'removed': True, 'cleanup_manifest': {'path': str(self.path), 'files_sha256': inventory},
                'cleanup_digest': actual_digest, 'storage_guarded': True}

    @property
    def reader(self):
        if self.state.get('reader_unavailable'):
            fx, _ = fixture_modules()
            reader = fx.SyntheticAuthority()
            reader.unavailable = True
            return reader
        return super().reader

    def control(self, scenario):
        # Finite host-owned synthetic values; never JSON/code supplied by an author request.
        inputs = {'input-missing': {}, 'input-type': {'text': 1}, 'input-empty': {'text': ''},
                  'input-long': {'text': 'x' * 81}, 'input-extra': {'text': 'ok', 'extra': True},
                  'input-spaces': {'text': '   '}, 'input-tabs': {'text': '  \tinside\t  '},
                  'input-newline': {'text': '  \ninside\n  '}, 'input-nbsp': {'text': '  \u00a0inside\u00a0  '},
                  'input-inner': {'text': '  left  right  '}, 'input-alternate': {'text': '  alternate  '}}
        if scenario in inputs:
            with self.lock():
                s = self.state
                reference = {**deepcopy(s['current_input']), 'evidence_id': ident('input'), 'digest': digest(inputs[scenario])}
                s['inputs'][reference['evidence_id']] = {'ref': reference, 'content': inputs[scenario]}
                s['current_input'] = reference
                s['authorization_revision'] += 1
                save(self.path / 'host/state.json', s)
                return {'scenario': scenario, 'input_ref': reference, 'object_refs': [s['source']]}
        if scenario in {'reader-unavailable', 'publish-unbound'}:
            with self.lock():
                self.authorize('inspect', 'inspector')
                if scenario == 'reader-unavailable':
                    self.state['reader_unavailable'] = True
                else:
                    self.publish_unbound()
                save(self.path / 'host/state.json', self.state)
                return {'fixture': scenario}
        inherited = {'revoke-operation', 'revoke-read', 'revoke-provider', 'revoke-grant', 'authority-gap', 'output-mismatch',
                     'authority-stale', 'authority-rollback', 'unknown-provider', 'missing-implementation',
                     'fake-admission', 'mutate-definition', 'advance-past-deadline', 'disarm-fault'}
        inherited |= {'publish-' + name for name in ('multi-node', 'wait', 'ai', 'human', 'resources', 'retry',
                      'timeout', 'wrong-role', 'condition', 'cycle', 'readback', 'action', 'version-conflict')}
        inherited |= {'fault-' + operation + '-' + point for operation in ('create', 'submit')
                      for point in ('after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response')}
        require(scenario in inherited, 'CAPABILITY_UNSUPPORTED')
        return super().control(scenario)

    def publish_unbound(self):
        # Trusted negative publisher fixture, not an author-supplied projection.
        fx, _ = fixture_modules()
        s, reader = self.state, self.reader
        authority = fx.SyntheticAuthority()
        authority.records, authority.views = deepcopy(reader.records), deepcopy(reader.views)
        projection = deepcopy(s['projection'])
        projection['provider_bindings'].remove(projection['nodes'][0]['executor_ref'])
        body = {k: v for k, v in projection.items() if k != 'definition_ref'}
        projection['definition_ref'] = fx.publish(authority, 'runtime', projection['definition_ref']['id'], body, projection['dependencies'])
        original = s['request']['admission_ref']
        admission = authority.lookup('admission', original, None)
        ref = {**original, 'id': ident('admission')}
        admission.update(ref=ref, definition_ref=projection['definition_ref'], projection_digest=digest(projection),
                         provider_bindings=projection['provider_bindings'])
        authority.put('admission', ref, admission)
        grant_ref = s['request']['ownership_grant_ref']
        grant = authority.lookup('grant', grant_ref, None)
        grant['admission_ref'] = ref
        authority.put('grant', grant_ref, grant)
        s['projection'] = projection
        s['request'].update(admission_ref=ref, projection=deepcopy(projection))
        s['records'] = [[a, b, c] for (a, b), c in authority.records.items()]
        payload = {k: projection[k] for k in ('business_ref', 'definition_ref', 'contract_version', 'provider_bindings')}
        payload['admission_ref'] = ref
        save(self.path / 'requests/register-variant.json', {'request_id': ident('req'), 'idempotency_key': ident('register'), 'payload': payload})

    def install_inspect(self):
        from .package_install import plain_path
        with self.lock():
            self.authorize('inspect', 'inspector')
            record, _, _ = verify_installation(self.path)
            db = self.store.connect(readonly=True)
            db.close()
            proofs = [load_json(plain_path(path)) for path in sorted((self.path / 'host').glob('execution-output-*.json'))]
            calls_path = self.path / 'observations/providers.jsonl'
            calls = [json.loads(line) for line in calls_path.read_text(encoding='utf-8').splitlines()] if calls_path.exists() else []
            return {'installation': record, 'executions': proofs, 'calls': calls}

    def providers(self, node):
        from .package_providers import PackageProviders
        return PackageProviders(self, node)

    def active_attempt(self, input_ref):
        # This pilot runs one attempt per host session, not a multi-worker ABI.
        db = self.store.connect(readonly=True)
        try:
            rows = db.execute('SELECT n.case_id,n.node_run_id,a.attempt_id,n.input_ref FROM attempts a '
                              'JOIN node_runs n ON n.node_run_id=a.node_run_id '
                              "WHERE a.owner=? AND a.released=0 AND n.status='RUNNING'", (self.session,)).fetchall()
            require(len(rows) == 1 and json.loads(rows[0]['input_ref']) == input_ref, 'LEASE_LOST')
            return {name: rows[0][name] for name in ('case_id', 'node_run_id', 'attempt_id')}
        finally:
            db.close()

    def stage_output(self, content, lease):
        record, _, _ = verify_installation(self.path)
        proof = deepcopy(getattr(self, 'pending_invocation', None))
        require(proof is not None and proof['invoked'] is True)
        require(proof['installation_id'] == record['installation_id'] and proof['record_digest'] == record['record_digest']
                and proof['input_snapshot_ref'] == lease['input_snapshot_ref'] and proof['output_digest'] == digest(content)
                and proof['implementation_sha256'] == record['implementation_sha256'], 'VERSION_CONFLICT')
        active = self.active_attempt(lease['input_snapshot_ref'])
        require(all(lease[name] == value for name, value in active.items()), 'LEASE_LOST')
        if self.state['output_mode'] == 'mismatch':
            content = {'normalized': 'SYNTHETIC WRONG OUTPUT'}
        reference = super().stage_output(content, lease)
        proof.update(active, output_ref=deepcopy(reference))
        save(self.path / 'host' / ('execution-' + reference['evidence_id'] + '.json'), proof)
        self.pending_invocation = None
        return reference

    def verify_execution(self, reference, input_ref, content):
        record, _, _ = verify_installation(self.path)
        proof = load_json(self.path / 'host' / ('execution-' + reference['evidence_id'] + '.json'))
        active = self.active_attempt(input_ref)
        require(all(proof[name] == value for name, value in active.items()))
        require(proof['invoked'] is True and proof['provider_ref'] == record['provider_ref']
                and proof['installation_id'] == record['installation_id'] and proof['record_digest'] == record['record_digest']
                and proof['implementation_sha256'] == record['implementation_sha256'] and proof['adapter'] == record['adapter']
                and proof['input_snapshot_ref'] == input_ref and proof['input_digest'] == input_ref['digest']
                and proof['output_ref'] == reference and proof['output_digest'] == digest(content)
                and proof['session'] == self.session)
