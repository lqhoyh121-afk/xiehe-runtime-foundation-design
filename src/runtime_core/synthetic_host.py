"""Isolated SYNTHETIC host. Not an authentication or production boundary. Laiqh."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import json
import os
import shutil
import stat
import time
import uuid

from .contract_adapter import (ContractError, ConsumptionContext, capabilities, check_consumption,
                               digest, fixture_modules, key, load_json, require, resolve, timestamp)
from .store import Store, encode
from .synthetic_providers import install_projection, changed_input_content

ROOT = Path(__file__).resolve().parents[2]
START = '2030-01-01T12:00:00Z'
END = '2030-01-01T12:05:00Z'


def ident(prefix):
    return prefix + '-' + uuid.uuid4().hex


def safe_path(path):
    path = Path(os.path.abspath(path))
    local = ROOT / '.local'
    require(path != local and path.is_relative_to(local), 'SANDBOX_INVALID')
    for part in [path, *path.parents]:
        if part.exists() or part.is_symlink():
            attrs = part.lstat()
            require(not stat.S_ISLNK(attrs.st_mode) and not (getattr(attrs, 'st_file_attributes', 0) & 1024),
                    'SANDBOX_INVALID')
        if part == ROOT:
            break
    require(path.resolve().is_relative_to(local.resolve()), 'SANDBOX_INVALID')
    return path


def save(path, value):
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temp.open('x', encoding='utf-8') as out:
        out.write(encode(value))
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def pid_alive(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied is not proof of exit.
        try:
            return api.WaitForSingleObject(handle, 0) != 0
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Reader:
    def __init__(self, state):
        self.records = {(a, b): c for a, b, c in state['records']}
        self.views = {(a, b): c for a, b, c in state['views']}

    def lookup(self, kind, reference, context):
        return deepcopy(self.records.get((kind, key(reference))))

    def current(self, kind, reference, context):
        return deepcopy(self.views.get((kind, reference)))


def build_fixture(sandbox_id):
    fx, p2 = fixture_modules()
    f = p2.p2_fixture()
    a = f.authority
    f.projection, content = install_projection(a, f.context.scope, fx.publish)
    business, providers = f.projection['business_ref'], f.projection['provider_bindings']
    f.projection['definition_ref'] = fx.publish(a, 'runtime', 'm1-runtime', deepcopy(f.projection), f.projection['dependencies'])
    deployment, instance, namespace = ident('deployment'), ident('instance'), ident('namespace')
    f.context = replace(f.context, deployment_id=deployment, instance_id=instance, namespace=namespace)
    f.admission.update(business_ref=business, definition_ref=f.projection['definition_ref'], projection_digest=digest(f.projection),
                       provider_bindings=providers, deployment_ids=[deployment])
    f.grant.update(instance_id=instance, deployment_id=deployment, namespace=namespace)
    f.policy['namespace'] = namespace
    f.ownership.update(instance_id=instance, deployment_id=deployment, namespace=namespace)
    f.request.update(projection=deepcopy(f.projection), instance_id=instance, deployment_id=deployment, namespace=namespace)
    a.views.clear()
    p2.install_p2(f)
    source = {'object_type': 'synthetic-source', 'namespace': 'synthetic', 'id': 'source-m1', 'scope': deepcopy(f.context.scope)}
    output_source = {**deepcopy(source), 'id': 'executor-m1'}

    ref = {'evidence_id': ident('input'), 'digest': digest(content), 'scope': deepcopy(f.context.scope),
           'observed_at': START, 'valid_until': END, 'source_ref': source, 'retention_policy_ref': 'm1-sandbox-lifetime'}
    return {'sandbox_id': sandbox_id, 'identity': {'sandbox_id': sandbox_id, 'instance_id': instance,
            'deployment_id': deployment, 'namespace': namespace}, 'scope': deepcopy(f.context.scope),
            'epoch': f.context.epoch, 'now': START, 'time_floor': START, 'revocation_floor': 4, 'authorization_revision': 1,
            'records': [[a, b, c] for (a, b), c in f.authority.records.items()],
            'views': [[a, b, c] for (a, b), c in f.authority.views.items()], 'request': f.request,
            'projection': f.projection, 'installed': providers, 'permissions': {'operation': True, 'read': True},
            'inputs': {ref['evidence_id']: {'ref': ref, 'content': content}}, 'current_input': ref,
            'source': source, 'output_source': output_source, 'fault': None, 'rule_mode': 'ALLOW', 'output_mode': 'normal'}


class Host:
    def __init__(self, path):
        self.path = safe_path(path)
        self.session = ident('session')
        self.monotonic_starts = {}
        self.state = None

    def initialize(self):
        require(not self.path.exists(), 'INVALID_STATE')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.mkdir()
        for d in ('host', 'runtime', 'requests', 'observations'):
            (self.path / d).mkdir()
        state = build_fixture(ident('sandbox'))
        state['storage_path'] = str(self.path)
        save(self.path / 'host/state.json', state)
        (self.path / 'host/lock').write_bytes(b'0')
        save(self.path / 'manifest.json', {'sandbox_id': state['sandbox_id'], 'path': str(self.path),
             'synthetic_only': True, 'directories': ['host', 'runtime', 'requests', 'observations']})
        self.state = state
        Store(self.path / 'runtime/runtime.sqlite', state['identity']).initialize()
        p = state['projection']
        payload = {k: deepcopy(p[k]) for k in ('business_ref', 'definition_ref', 'contract_version', 'provider_bindings')}
        payload['admission_ref'] = deepcopy(state['request']['admission_ref'])
        save(self.path / 'requests/register.json', {'request_id': ident('req'), 'idempotency_key': 'register-one', 'payload': payload})
        return {'sandbox_id': state['sandbox_id'], 'input_ref': state['current_input'], 'object_refs': [state['source']],
                'manifest': str(self.path / 'manifest.json')}

    @contextmanager
    def lock(self):
        safe_path(self.path / 'host/lock')
        require((self.path / 'host/lock').is_file(), 'HOST_BINDING_MISMATCH')
        with (self.path / 'host/lock').open('r+b') as handle:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ContractError('IN_PROGRESS') from None
            try:
                self.reload()
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def reload(self):
        for p in ('host/state.json', 'manifest.json', 'runtime/runtime.sqlite'):
            safe_path(self.path / p)
        self.state = load_json(self.path / 'host/state.json')
        manifest = load_json(self.path / 'manifest.json')
        require(manifest['path'] == str(self.path) == self.state['storage_path']
                and manifest['sandbox_id'] == self.state['sandbox_id'], 'HOST_BINDING_MISMATCH')
        require(timestamp(self.state['now']) >= timestamp(self.state['time_floor']), 'AUTHORITY_VIEW_STALE')

    @property
    def store(self):
        return Store(self.path / 'runtime/runtime.sqlite', self.state['identity'])

    @property
    def now(self):
        return timestamp(self.state['now'])

    @property
    def reader(self):
        return Reader(self.state)

    @property
    def context(self):
        s = self.state
        return ConsumptionContext(scope=s['scope'], deployment_id=s['identity']['deployment_id'], now=self.now,
            minimum_revision=s['revocation_floor'], synthetic=True, instance_id=s['identity']['instance_id'],
            namespace=s['identity']['namespace'], epoch=s['epoch'])

    def authorize(self, operation, role):
        require(role in {'admin', 'initiator', 'worker', 'inspector'}, 'UNAUTHORIZED')
        require(self.state['permissions']['read'] or role == 'inspector', 'UNAUTHORIZED')
        if operation not in {'snapshot', 'events', 'inspect'}:
            require(self.state['permissions']['operation'], 'UNAUTHORIZED')
        require((operation in {'register', 'set-state'} and role == 'admin')
                or (operation == 'create' and role == 'initiator')
                or (operation in {'claim', 'submit'} and role == 'worker')
                or operation in {'snapshot', 'events', 'inspect'}, 'UNAUTHORIZED')

    def actor(self, role):
        return {'object_type': 'synthetic-actor', 'namespace': 'synthetic', 'id': role, 'scope': deepcopy(self.state['scope'])}

    def validate(self, binding):
        req = deepcopy(self.state['request'])
        req.update(projection=deepcopy(binding['projection']), admission_ref=deepcopy(binding['admission_ref']), worker_session_id=self.session)
        check_consumption(req, self.reader, self.context)
        capabilities(req['projection'], self.state['installed'])

    def resolve_binding(self, payload):
        record = resolve(payload['definition_ref'], self.reader, self.context)
        projection = {**record['content'], 'definition_ref': payload['definition_ref']}
        require(all(payload[k] == projection[k] for k in ('business_ref', 'contract_version', 'provider_bindings')),
                'PROJECTION_BINDING_MISMATCH')
        return {'projection': projection, 'projection_digest': digest(projection), 'admission_ref': payload['admission_ref']}

    def observe(self, provider):
        path = safe_path(self.path / 'observations/providers.jsonl')
        with path.open('a', encoding='utf-8') as out:
            out.write(encode({'provider': provider, 'pid': os.getpid(), 'session': self.session}) + '\n')
            out.flush()

    def fault(self, operation, point):
        if self.state['fault'] == operation + ':' + point:
            os._exit(86)

    def inspect(self):
        with self.lock():
            self.authorize('inspect', 'inspector')
            db = self.store.connect(readonly=True)
            db.close()
            path = self.path / 'observations/providers.jsonl'
            calls = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
            return {'authorization_revision': self.state['authorization_revision'], 'revocation_floor': self.state['revocation_floor'],
                    'now': self.state['now'], 'calls': calls, 'instance_id': self.state['identity']['instance_id']}

    def stage_output(self, content, lease):
        reference = {'evidence_id': ident('output'), 'digest': digest(content), 'scope': deepcopy(self.state['scope']),
                     'observed_at': self.state['now'], 'valid_until': min(lease['deadline'], lease['input_snapshot_ref']['valid_until']),
                     'source_ref': deepcopy(self.state['output_source']), 'retention_policy_ref': 'm1-sandbox-lifetime'}
        save(self.path / 'host' / (reference['evidence_id'] + '.json'), {'ref': reference, 'content': content})
        return reference

    def control(self, scenario):
        """Operator-only finite negative fixtures. No arbitrary code or permission restore."""
        if scenario == 'release-query':
            with self.lock():
                save(self.path / 'observations/query-release.json', {'released': True})
            return {'scenario': scenario}
        variants = {'ai', 'human', 'multi-node', 'wait', 'readback', 'action', 'resources', 'retry',
                    'timeout', 'wrong-role', 'condition', 'cycle', 'version-conflict'}
        permitted = {'revoke-operation', 'revoke-read', 'advance-past-deadline', 'revoke-provider', 'revoke-grant',
                     'authority-gap', 'authority-stale', 'authority-rollback', 'mutate-input', 'tamper-input',
                     'output-mismatch', 'deny-rule', 'needs-input', 'rule-unavailable', 'unknown-provider',
                     'missing-implementation', 'fake-admission', 'mutate-definition', 'expire-input'}
        faults = {'fault-' + op + '-' + point: op + ':' + point for op in ('create', 'submit')
                  for point in ('after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response')}
        permitted |= set(faults) | {'disarm-fault'}
        require(scenario in permitted or scenario in {'publish-' + v for v in variants}, 'CAPABILITY_UNSUPPORTED')
        with self.lock():
            s = self.state
            p = s['projection']
            if scenario in faults or scenario == 'disarm-fault':
                s['fault'] = faults.get(scenario)
            elif scenario.startswith('publish-'):
                self.publish_variant(scenario[8:])
            elif scenario in {'revoke-operation', 'revoke-read'}:
                s['permissions']['operation' if scenario == 'revoke-operation' else 'read'] = False
            elif scenario == 'advance-past-deadline':
                s['now'] = (self.now + timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
                s['time_floor'] = s['now']
            elif scenario in {'deny-rule', 'needs-input', 'rule-unavailable'}:
                s['rule_mode'] = {'deny-rule': 'DENY', 'needs-input': 'NEEDS_INPUT', 'rule-unavailable': 'UNAVAILABLE'}[scenario]
            elif scenario == 'output-mismatch':
                s['output_mode'] = 'mismatch'
            elif scenario == 'missing-implementation':
                s['installed'] = []
            elif scenario in {'unknown-provider', 'fake-admission'}:
                kind, ref = ('provider', p['nodes'][0]['executor_ref']) if scenario == 'unknown-provider' else ('admission', s['request']['admission_ref'])
                s['records'] = [r for r in s['records'] if (r[0], r[1]) != (kind, key(ref))]
            elif scenario == 'mutate-definition':
                for kind, ref, record in s['records']:
                    if kind == 'definition' and ref == key(p['definition_ref']):
                        record['content']['status'] = 'MUTATED'
            elif scenario in {'mutate-input', 'tamper-input', 'expire-input'}:
                old = s['current_input']
                entry = s['inputs'][old['evidence_id']]
                if scenario == 'tamper-input':
                    entry['content'] = changed_input_content(tampered=True)
                else:
                    new = deepcopy(entry)
                    new['ref']['evidence_id'] = ident('input')
                    if scenario == 'expire-input':
                        new['ref']['valid_until'] = s['now']
                    else:
                        new['content'] = changed_input_content()
                        new['ref']['digest'] = digest(new['content'])
                    s['inputs'][new['ref']['evidence_id']] = new
                    s['current_input'] = new['ref']
            else:
                for kind, _, view in s['views']:
                    if scenario == 'authority-gap' and kind == 'ownership':
                        view['complete'] = False
                    if scenario == 'authority-stale' and kind in {'ownership', 'revocations'}:
                        view['valid_until'] = s['now']
                    if scenario == 'authority-rollback' and kind == 'revocations':
                        view['revision'] = s['revocation_floor'] - 1
                    if scenario in {'revoke-provider', 'revoke-grant'}:
                        new_revision = s['revocation_floor'] + 1
                        if kind == 'revocations':
                            view['revision'] = new_revision
                            target = p['nodes'][0]['executor_ref'] if scenario == 'revoke-provider' else s['request']['ownership_grant_ref']
                            view['events'].append({'issuer': view['issuer'], 'event_id': ident('revocation'), 'scope': s['scope'],
                                'epoch': s['epoch'], 'target_ref': target, 'issuer_revision': new_revision,
                                'effective_at': s['now'], 'reason_ref': 'synthetic-withdrawal'})
                        if kind == 'ownership':
                            view['revocation_revision'] = new_revision
                if scenario in {'revoke-provider', 'revoke-grant'}:
                    s['revocation_floor'] += 1
            s['authorization_revision'] += 1
            save(self.path / 'host/state.json', s)
            return {'scenario': scenario, 'authorization_revision': s['authorization_revision']}

    def publish_variant(self, variant):
        # Trusted test installation changes published content and recomputes refs,
        # never derives an installation from a caller-supplied projection.
        fx, _ = fixture_modules()
        s = self.state
        a = fx.SyntheticAuthority()
        a.records = {(x, y): deepcopy(z) for x, y, z in s['records']}
        p = deepcopy(s['projection'])
        n = p['nodes'][0]
        if variant in {'ai', 'human'}:
            kind = variant.upper()
            ref = fx.publish(a, 'provider', 'm1-executor-' + variant, {'role': 'NodeExecutor', 'contract_version': '0.1-draft',
                             'execution_kind': kind, 'capabilities': ['synthetic-negative-fixture']})
            p['dependencies'].append(ref)
            p['provider_bindings'].append(ref)
            n.update(executor_ref=ref, execution_kind=kind)
        elif variant == 'multi-node':
            p['nodes'].append({**deepcopy(n), 'node_id': 'second', 'depends_on': [n['node_id']]})
            p['terminal_nodes'] = ['second']
        elif variant == 'condition':
            n['condition'] = 'synthetic-condition'
        elif variant == 'cycle':
            n['depends_on'] = [n['node_id']]
        elif variant == 'wrong-role':
            n['executor_ref'] = n['data_provider_ref']
        elif variant == 'resources':
            n['resources'] = [{'resource_ref': s['source'], 'mode': 'EXCLUSIVE'}]
        elif variant == 'retry':
            n['retry_policy']['max_attempts'] = 2
        elif variant == 'timeout':
            n['timeout_seconds'] = 31
        elif variant == 'version-conflict':
            ref = fx.publish(a, 'business', p['business_ref']['id'], {'synthetic_only': True, 'revision_fixture': 2})
            p['dependencies'] = [ref if x == p['business_ref'] else x for x in p['dependencies']]
            p['business_ref'] = ref
        elif variant == 'wait':
            ref = fx.publish(a, 'wait', 'm1-wait', {'synthetic_only': True})
            p['dependencies'].append(ref)
            n['wait_spec_ref'] = ref
        elif variant in {'readback', 'action'}:
            role = 'ReadbackProvider' if variant == 'readback' else 'ActionAdapter'
            ref = fx.publish(a, 'provider', 'm1-' + role, {'role': role, 'contract_version': '0.1-draft', 'execution_kind': None, 'capabilities': ['synthetic-negative-fixture']})
            p['dependencies'].append(ref)
            p['provider_bindings'].append(ref)
            n['readback_provider_ref' if variant == 'readback' else 'action_adapter_ref'] = ref
            if variant == 'readback':
                verify = fx.publish(a, 'verification', 'm1-verification', {'synthetic_only': True})
                p['dependencies'].append(verify)
                n.update(verification_spec_ref=verify, completion='READBACK_VERIFIED')
        body = {k: v for k, v in p.items() if k != 'definition_ref'}
        p['definition_ref'] = fx.publish(a, 'runtime', p['definition_ref']['id'], body, p['dependencies'])
        original = s['request']['admission_ref']
        admission = deepcopy(a.lookup('admission', original, None))
        ref = {**original, 'id': ident('admission')}
        admission.update(ref=ref, business_ref=p['business_ref'], definition_ref=p['definition_ref'], projection_digest=digest(p), provider_bindings=p['provider_bindings'])
        a.put('admission', ref, admission)
        # Separate trusted grant binding for this test installation.
        grant_ref = s['request']['ownership_grant_ref']
        grant = a.lookup('grant', grant_ref, None)
        grant['admission_ref'] = ref
        a.put('grant', grant_ref, grant)
        s['request'].update(admission_ref=ref, projection=deepcopy(p))
        s['projection'] = p
        s['records'] = [[x, y, z] for (x, y), z in a.records.items()]
        payload = {k: p[k] for k in ('business_ref', 'definition_ref', 'contract_version', 'provider_bindings')}
        payload['admission_ref'] = ref
        save(self.path / 'requests/register-variant.json', {'request_id': ident('req'), 'idempotency_key': ident('register'), 'payload': payload})

    def output_entry(self, reference):
        from .contract_adapter import shape
        shape('EvidenceRef', reference)
        require(reference['evidence_id'].startswith('output-'), 'CONTRACT_INVALID')
        path = safe_path(self.path / 'host' / (reference['evidence_id'] + '.json'))
        require(path.parent == self.path / 'host', 'CONTRACT_INVALID')
        return load_json(path)

    def cleanup(self, manifest):
        require(safe_path(manifest) == self.path / 'manifest.json', 'SANDBOX_INVALID')
        with self.lock():
            for process in (self.path / 'observations').glob('process-*.json'):
                safe_path(process)
                require(not pid_alive(load_json(process)['pid']), 'IN_PROGRESS')
            for parent, dirs, files in os.walk(self.path, followlinks=False):
                for name in dirs + files:
                    safe_path(Path(parent) / name)
            require(set(p.name for p in self.path.iterdir()) <= {'manifest.json', 'host', 'runtime', 'requests', 'observations'}, 'SANDBOX_INVALID')
        shutil.rmtree(self.path)
        require(not self.path.exists(), 'STORAGE_INVALID')
        return {'removed': True}

    def start_process(self):
        with self.lock():
            path = self.path / 'observations' / ('process-' + self.session + '.json')
            save(path, {'pid': os.getpid(), 'session': self.session, 'sandbox_id': self.state['sandbox_id']})
            return path

    def event_overflow_fixture(self, case_id):
        """Poison only an owned SYNTHETIC test case to exercise the event cap."""
        from .contract_adapter import shape
        shape('Id', case_id)
        with self.lock():
            self.authorize('inspect', 'inspector')
            with self.store.write() as db:
                case = Store.one(db, 'cases', 'case_id', case_id)
                require(case is not None, 'CONTRACT_INVALID')
                for _ in range(101):
                    event = {'event_id': ident('synthetic-overflow'), 'case_id': case_id,
                             'case_revision': case['revision'], 'type': 'SYNTHETIC_OVERFLOW_FIXTURE'}
                    db.execute('INSERT INTO events(event_id,case_id,case_revision,type,body) VALUES(?,?,?,?,?)',
                               (event['event_id'], case_id, case['revision'], event['type'], encode(event)))
            return {'fixture': 'SYNTHETIC_OVERFLOW_FIXTURE', 'case_id': case_id}

    def query_barrier(self):
        release = self.path / 'observations/query-release.json'
        require(not release.exists(), 'INVALID_STATE')
        save(self.path / 'observations/query-ready.json', {'pid': os.getpid(), 'session': self.session})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if release.exists():
                return
            time.sleep(0.02)
        raise ContractError('IN_PROGRESS')
