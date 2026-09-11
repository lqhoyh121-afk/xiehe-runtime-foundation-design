"""Independent fresh-process/stdlib-SQLite WF2 pilot acceptance. TEST ONLY. Laiqh.

This observer does not import Service, Store, Worker or any runtime implementation.
Synthetic negative mutations only affect this run's owned, derived host fixtures.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/runtime_package_cli.py'
SCENARIOS = tuple('S%02d' % n for n in range(1, 11))
AUTHOR_FILES = ('package-manifest.json', 'definitions/workflow-projection.json',
                'components/normalize-submission/declaration.json',
                'components/normalize-submission/implementation.py',
                'components/normalize-submission/test_normalize.py', 'acceptance.md')
TABLES = ('runtime_meta', 'registrations', 'bindings', 'cases', 'node_runs', 'attempts',
          'ready_nodes', 'evidence', 'idempotency_results', 'events')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def hashes(root):
    result = {}
    for path in sorted(Path(root).rglob('*')):
        attrs = path.lstat()
        assert not stat.S_ISLNK(attrs.st_mode) and not getattr(attrs, 'st_file_attributes', 0) & 1024
        if path.is_file():
            assert attrs.st_nlink == 1
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class Acceptance:
    def __init__(self, root, report, show_commands=False, evidence_dir=None, evidence_scenario=None):
        if evidence_dir is not None and evidence_scenario not in ('S01', 'bytes'):
            raise ValueError('EVIDENCE_SCENARIO_UNSUPPORTED')
        self.root, self.report = Path(os.path.abspath(root)), Path(os.path.abspath(report))
        for path in (self.root, self.report):
            assert path.is_relative_to(ROOT / '.local') and path != ROOT / '.local'
            for part in (path, *path.parents):
                if part.exists():
                    assert not part.is_symlink() and not getattr(part.lstat(), 'st_file_attributes', 0) & 1024
        assert not self.root.exists() and not self.report.exists() and not self.report.is_relative_to(self.root)
        self.audit = None
        self.evidence_scenario = evidence_scenario
        if evidence_dir is not None:
            import runpy
            evidence = runpy.run_path(str(ROOT / 'tests/runtime_package/fixtures.py'))['EvidenceRun']
            self.evidence_owner = self.report.parent if evidence_scenario == 'bytes' else self.root
            if evidence_scenario == 'bytes':
                assert self.root.parent == self.evidence_owner and not self.evidence_owner.exists()
            self.audit = evidence(evidence_dir=evidence_dir, purpose='verifier-' + evidence_scenario,
                                  owned_roots=[self.evidence_owner])
            self.audit.register(self.evidence_owner, purpose='verifier owned ' + evidence_scenario)
            if self.root != self.evidence_owner:
                self.audit.register(self.root, purpose='byte capture sandbox', parent=self.evidence_owner)
        self.root.mkdir(parents=True)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        self.reference = Path(self.env['WF2_REFERENCE_ROOT'])
        self.tools = Path(self.env['WF2_TOOL_ROOT'])
        self.source_before = {'reference': hashes(self.reference), 'tools': hashes(self.tools)}
        self.commands, self.checks, self.targets, self.live, self.embedded = [], [], [], [], []
        self.group, self.show_commands = 'generation', show_commands
        self.result = {'synthetic_only': True, 'production_authorized': False, 'contract_status': 'DRAFT',
                       'scope': 'single-node-pilot-not-full-WF2', 'commands': self.commands, 'checks': self.checks,
                       'targets': self.targets, 'embedded_checker_commands': self.embedded,
                       'unverified': ['controller independent review', 'M2/SC01-SC05', 'human L3', 'production L4',
                                      'untrusted-code sandbox', 'real authority or external systems']}
        if self.audit:
            self.result['evidence_ledger'] = str(self.audit.path / 'ledger.json')
        self.checkpoint()

    def checkpoint(self):
        self.result.update(passed=sum(c['passed'] for c in self.checks), failed=sum(not c['passed'] for c in self.checks),
                           cli_count=sum(c['kind'] == 'cli' for c in self.commands) + len(self.embedded),
                           observer_count=sum(c['kind'] == 'observer' for c in self.commands),
                           probe_count=sum(c['kind'] == 'probe' for c in self.commands),
                           process_command_count=len(self.commands),
                           owned_processes_exited=all(p.poll() is not None for p in self.live))
        write(self.report, self.result)

    def check(self, condition, name):
        self.checks.append({'scenario': self.group, 'name': name, 'passed': bool(condition)})
        self.checkpoint()
        assert condition, self.group + ': ' + name

    def command(self, argv, expected=0, kind='cli', env=None, cwd=None, timeout=90, parse=True):
        if self.show_commands:
            print(subprocess.list2cmdline(list(map(str, argv))), flush=True)
        p = subprocess.Popen(list(map(str, argv)), cwd=cwd or ROOT, env=env or self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.live.append(p)
        started = time.time()
        timed_out = False
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True, timeout=15)
            else:
                p.kill()
            stdout, stderr = p.communicate(timeout=15)
        entry = {'scenario': self.group, 'kind': kind, 'argv': list(map(str, argv)), 'cwd': str(cwd or ROOT),
                 'launcher_pid': p.pid, 'runtime_pid': None, 'exit_code': p.returncode, 'expected_exit_code': expected,
                 'started_epoch': started, 'ended_epoch': time.time(),
                 'timed_out': timed_out, 'exited': p.poll() is not None}
        # Windows native tools need not emit UTF-8. Capture bytes before decoding:
        # a text-mode reader-thread exception can otherwise drop output despite exit=0.
        invalid_utf8 = False
        for stream, content in (('stdout', stdout), ('stderr', stderr)):
            entry[stream + '_raw_hex'] = content.hex()
            try:
                entry[stream] = content.decode('utf-8')
            except UnicodeDecodeError:
                entry[stream] = content.decode('utf-8', errors='replace')
                if stream == 'stdout':
                    invalid_utf8 = True
        self.commands.append(entry)
        self.checkpoint()
        self.check(not timed_out and p.returncode == expected, 'process exit: ' + str(argv[-1]))
        if parse and invalid_utf8:
            raise ValueError('Non-UTF8 JSON protocol output; exact bytes retained in receipt')
        stdout = entry['stdout']
        payload = (json.loads(stdout) if stdout.strip() else None) if parse else entry
        if isinstance(payload, dict):
            entry['runtime_pid'] = payload.get('pid')
        if self.audit:
            self.audit.data['commands'].append(entry)
            self.audit.live.append(p)
            self.audit.save()
        self.checkpoint()
        return payload

    def call(self, h, *args, code=0, env=None, cwd=None):
        snapshot = self.audit.export(self.root) if self.audit and args and args[0] in ('host-cleanup', 'install-remove') else None
        result = self.command([sys.executable, '-B', CLI, '--sandbox', h['path'], *args], code, env=env, cwd=cwd)
        if snapshot:
            self.audit.cli_cleanup_receipt(h['path'], snapshot, self.commands[-1])
        return result

    def generate(self):
        self.generated = self.root / 'generated'
        if self.audit:
            self.audit.register(self.generated, purpose='generated workflow sources', parent=self.root)
            self.audit.register(self.generated / 'package', purpose='author generated package', parent=self.generated)
            self.audit.register(self.generated / 'materials', purpose='synthetic materials', parent=self.generated)
        self.generated.mkdir()
        self.package, self.materials = self.generated / 'package', self.generated / 'materials'
        self.command([sys.executable, '-B', self.tools / 'tools/workflow_author.py', 'init',
                      '--template', 'single-code-output-v1', '--output', self.package, '--format', 'json'])
        for relative in AUTHOR_FILES:
            (self.package / relative).write_bytes((self.reference / 'l3/package' / relative).read_bytes())
        self.command([sys.executable, '-B', self.tools / 'tools/workflow_author_synthetic.py', 'prepare',
                      '--output', self.materials, '--format', 'json'])
        static = self.command([sys.executable, '-B', self.tools / 'tools/workflow_author.py', 'check',
                               '--package', self.package, '--format', 'json'], expected=4)
        self.check(static['status'] == 'INCOMPLETE' and static['diagnostics'][0]['source_code'] == 'TRUST_CONTEXT_REQUIRED',
                   'standalone checker keeps INCOMPLETE/4; not a core storage failure')
        self.command([sys.executable, '-B', self.tools / 'tools/workflow_author_synthetic.py', 'check',
                      '--package', self.package, '--materials', self.materials, '--format', 'json'])
        self.generated_hashes = hashes(self.generated)
        self.check(hashes(self.package) == hashes(self.reference / 'l3/package') and
                   hashes(self.materials) == hashes(self.reference / 'l3/materials'), 'real init + author fields + prepare exact sources')

    @contextmanager
    def target(self, name, setup=True, install=True, source_package=None):
        h = {'name': name, 'path': self.root / (name + '-' + uuid.uuid4().hex), 'cleaned': False}
        if self.audit:
            self.audit.register(h['path'], purpose='installed S01 runtime', parent=self.root)
            self.audit.register(h['path'].with_name(h['path'].name + '.pending'), purpose='installation staging', parent=self.root)
        self.targets.append({**h, 'path': str(h['path'])})
        target_record = self.targets[-1]
        try:
            if install:
                h['init'] = self.call(h, 'install', '--package', source_package or self.package, '--materials', self.materials,
                                      '--fixture', 'normalize-l3-v1')['result']
                checker = h['path'] / 'observations/static-check.json'
                if checker.is_file():
                    self.embedded.append(read(checker))
                if setup:
                    registered = self.call(h, 'register', '--request', h['init']['register_request'])
                    h['registration_id'] = registered['result']['registration_id']
                    self.request(h, 'set-state', {'registration_id': h['registration_id'], 'expected_revision': 1, 'target_state': 'ENABLED'})
                    h['payload'] = {'registration_id': h['registration_id'], 'input_ref': h['init']['input_ref'],
                                    'object_refs': h['init']['object_refs']}
            yield h
        except BaseException:
            target_record['preserved_after_error'] = True
            self.checkpoint()
            raise
        else:
            if h['path'].exists():
                cleanup = self.call(h, 'host-cleanup', '--manifest', h['path'] / 'manifest.json')
                target_record['cleanup_manifest'] = cleanup['result']['cleanup_manifest']
            self.check(not h['path'].exists(), 'owned target removed: ' + name)
            self.check(self.absent_observer(h['path'])['absent'], 'new OS process confirms removal: ' + name)
            target_record['cleaned'] = True
            self.checkpoint()

    def request(self, h, operation, payload, key=None, code=0):
        path = h['path'] / 'requests' / (uuid.uuid4().hex + '.json')
        write(path, {'request_id': 'req-' + uuid.uuid4().hex, 'idempotency_key': key or 'key-' + uuid.uuid4().hex, 'payload': payload})
        return self.call(h, operation, '--request', path, code=code)

    def create(self, h, key=None, code=0):
        result = self.request(h, 'create', h['payload'], key=key, code=code)
        if code == 0:
            h['case_id'] = result['result']['case_id']
        return result

    def control(self, h, scenario):
        return self.call(h, 'host-control', '--scenario', scenario)['result']

    def logical(self, h):
        code = """import sqlite3,json,sys,os
from pathlib import Path
p=Path(sys.argv[1]); db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); db.row_factory=sqlite3.Row
try:
 result={t:[dict(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in json.loads(sys.argv[2])}
finally: db.close()
print(json.dumps({'pid':os.getpid(),'tables':result}))
"""
        return self.command([sys.executable, '-B', '-c', code, h['path'] / 'runtime/runtime.sqlite', json.dumps(TABLES)],
                            kind='observer')['tables']

    def source_observer(self, h):
        code = """import json,hashlib,os,sys
from pathlib import Path
p=Path(sys.argv[1]); record=json.loads((p/'host/installation.json').read_text());
proofs=[json.loads(x.read_text()) for x in (p/'host').glob('execution-output-*.json')]
source=(p/'host/package/components/normalize-submission/implementation.py').read_bytes()
print(json.dumps({'pid':os.getpid(),'record':record,'proofs':proofs,'source_sha256':hashlib.sha256(source).hexdigest()}))
"""
        return self.command([sys.executable, '-B', '-c', code, h['path']], kind='observer')

    def S01(self):
        with self.target('normal') as h:
            original = self.create(h, key='normal-create')
            run = self.call(h, 'run-once', '--case-id', h['case_id'])
            snapshot = self.call(h, 'snapshot', '--case-id', h['case_id'])
            events = self.call(h, 'events', '--case-id', h['case_id'])['result']['items']
            self.check(snapshot['pid'] != run['pid'] and snapshot['result']['status'] == 'SUCCEEDED', 'worker exit then fresh snapshot')
            self.check(snapshot['result']['nodes'][0]['output'] == {'normalized': 'SYNTHETIC  sample'}, 'actual author output equals independent oracle')
            self.check([e['type'] for e in events] == ['CASE_CREATED', 'NODE_READY', 'NODE_LEASED', 'NODE_STARTED', 'NODE_SUCCEEDED', 'CASE_SUCCEEDED']
                       and [e['case_revision'] for e in events] == [1, 1, 2, 2, 3, 3], 'persisted event/revision sequence')
            replay = self.create(h, key='normal-create')
            self.check(replay['replayed'] and replay['result'] == original['result'] and replay['result']['status'] == 'QUEUED', 'original result replayed, not current snapshot')
            sql = self.logical(h)
            source = self.source_observer(h)
            proof = source['proofs'][0]
            node, attempt, case = sql['node_runs'][0], sql['attempts'][0], sql['cases'][0]
            bindings = [json.loads(sql['registrations'][0]['binding']), json.loads(sql['bindings'][0]['body'])]
            self.check(len(sql['cases']) == len(sql['node_runs']) == len(sql['attempts']) == len(source['proofs']) == 1,
                       'one case, node, attempt and genuine invocation')
            self.check(proof['case_id'] == case['case_id'] and proof['node_run_id'] == node['node_run_id']
                       and proof['attempt_id'] == attempt['attempt_id'] and proof['pid'] == run['pid']
                       and proof['provider_ref'] == source['record']['provider_ref']
                       and proof['implementation_sha256'] == source['source_sha256'] == source['record']['implementation_sha256'],
                       'readonly SQLite joins actual PID/source/provider/install identity')
            self.check(all(b['package_installation']['record_digest'] == source['record']['record_digest'] for b in bindings),
                       'registration and case binding contain stable installation record')
            installed = self.call(h, 'install-inspect')['result']
            self.check(installed['installation'] == source['record'] and installed['executions'] == source['proofs'], 'install-inspect readback matches independent observer')

    def S02(self):
        with self.target('not-enabled', setup=False) as h:
            registered = self.call(h, 'register', '--request', h['init']['register_request'])['result']
            payload = {'registration_id': registered['registration_id'], 'input_ref': h['init']['input_ref'],
                       'object_refs': h['init']['object_refs']}
            before = self.logical(h)
            denied = self.request(h, 'create', payload, code=2)
            self.check(denied['code'] == 'BUSINESS_NOT_ENABLED' and self.logical(h) == before,
                       'registered is not enabled; no case, input evidence, event or attempt')
        with self.target('not-initialized', install=False) as h:
            self.check(self.call(h, 'install-inspect', code=2)['code'] == 'HOST_BINDING_MISMATCH', 'no implicit host or echo initialization')
            self.check(self.call(h, 'install', '--package', self.package, '--materials', self.materials,
                                 '--fixture', 'approved=true', code=2)['code'] == 'UNAUTHORIZED', 'caller approval is not trusted plan')
            self.check(self.call(h, 'install', '--package', self.package, '--materials', self.materials, code=2)['code'] == 'INPUT_INVALID',
                       'plan selection required')
            self.check(not h['path'].exists(), 'no database or activation after plan/host denial')
        for control, code in [('fake-admission', 'DEPENDENCY_UNAVAILABLE'), ('reader-unavailable', 'AUTHORITY_UNAVAILABLE')]:
            with self.target(control, setup=False) as h:
                before = self.logical(h)
                self.control(h, control)
                denied = self.call(h, 'register', '--request', h['init']['register_request'], code=3)
                self.check(denied['code'] == code and self.logical(h) == before, 'static pass cannot replace P2: ' + code)
                self.check(not list((h['path'] / 'host').glob('execution-output-*.json')), 'no author execution after P2/Reader denial')

    def S03(self):
        controls = [('unknown-provider', 'UNKNOWN_PROVIDER'), ('missing-implementation', 'CAPABILITY_UNSUPPORTED'),
                    ('publish-unbound', 'PROVIDER_NOT_BOUND'), ('publish-wrong-role', 'PROVIDER_ROLE_MISMATCH'),
                    ('publish-condition', 'SCHEMA_INVALID'), ('publish-cycle', 'NODE_CYCLE')]
        controls += [('publish-' + variant, 'CAPABILITY_UNSUPPORTED') for variant in
                     ('multi-node', 'wait', 'ai', 'human', 'readback', 'action', 'resources', 'retry', 'timeout')]
        for control, expected in controls:
            with self.target(control, setup=False) as h:
                before = self.logical(h)
                self.control(h, control)
                request = h['path'] / 'requests/register-variant.json' if control.startswith('publish-') else h['init']['register_request']
                denied = self.call(h, 'register', '--request', request, code=2)
                self.check(denied['code'] == expected and self.logical(h) == before, 'unchanged core gate, no registration: ' + control)
                self.check(not list((h['path'] / 'host').glob('execution-output-*.json')), 'unsupported workflow never invokes executor or action')
        with self.target('malformed-reference', setup=False) as h:
            before = self.logical(h)
            payload = read(h['init']['register_request'])['payload']
            payload['provider_bindings'][0]['approved'] = True
            denied = self.request(h, 'register', payload, code=2)
            self.check(denied['code'] == 'PROJECTION_BINDING_MISMATCH' and self.logical(h) == before,
                       'provider payload differs from published bindings; exact core mismatch preserved')
            payload = read(h['init']['register_request'])['payload']
            payload['business_ref']['approved'] = True
            denied = self.request(h, 'register', payload, code=2)
            self.check(denied['code'] == 'SCHEMA_INVALID' and self.logical(h) == before, 'malformed DefinitionRef rejected before lookup')

    def absent_observer(self, path):
        return self.command([sys.executable, '-B', '-c',
            'import os,sys,json; from pathlib import Path; print(json.dumps({"pid":os.getpid(),"absent":not Path(sys.argv[1]).exists()}))', path], kind='observer')

    @contextmanager
    def derived(self, name, source=None):
        path = self.root / (name + '-' + uuid.uuid4().hex)
        if source:
            shutil.copytree(source, path)
        else:
            path.mkdir()
        yield path
        manifest = {'path': str(path), 'files_sha256': hashes(path)}
        self.result.setdefault('derived_cleanup_manifests', []).append(manifest)
        self.checkpoint()
        shutil.rmtree(path)
        self.check(self.absent_observer(path)['absent'], 'owned derived fixture removed')

    def S04(self):
        implementation = 'components/normalize-submission/implementation.py'
        mutations = [(implementation, b'def normalize(value):\n    return {"normalized": "DIFFERENT"}\n'),
                     ('components/normalize-submission/declaration.json', b'{}\n'),
                     ('components/normalize-submission/helper.py', b'helper = 1\n'),
                     ('undeclared.txt', b'SYNTHETIC UNDECLARED\n'),
                     ('components/normalize-submission/__pycache__/implementation.pyc', b'SYNTHETIC STALE CACHE')]
        for index, (relative, content) in enumerate(mutations):
            with self.derived('source-drift', self.package) as package:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                with self.target('reject-source-' + str(index), install=False) as h:
                    denied = self.call(h, 'install', '--package', package, '--materials', self.materials,
                                       '--fixture', 'normalize-l3-v1', code=2)
                    self.check(denied['code'] == 'VERSION_CONFLICT' and denied['phase'] == 'installation'
                               and not h['path'].exists(), 'original approval rejects source/declaration/helper/cache drift')
        for relative, content in mutations:
            with self.target('installed-drift') as h:
                self.create(h)
                before = self.logical(h)
                target = h['path'] / 'host/package' / relative
                existed = target.exists()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                denied = self.call(h, 'run-once', '--case-id', h['case_id'], code=2)
                self.check(denied['code'] == 'VERSION_CONFLICT' and self.logical(h) == before,
                           'existing Case rejects installed source drift before claim or invocation')
                if not existed:
                    self.result.setdefault('injected_file_cleanup', []).append({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
                    self.checkpoint()
                    target.unlink()
        with self.derived('installation-source', self.package) as package, self.derived('shadow-cwd') as shadow:
            with self.target('detached-copy', source_package=package) as h:
                (package / implementation).write_text('def normalize(value):\n    return {"normalized":"WRONG"}\n', encoding='utf-8')
                bait = shadow / 'implementation.py'
                bait.write_text('def normalize(value):\n    return {"normalized":"CWD BAIT"}\n', encoding='utf-8')
                self.command([sys.executable, '-B', '-c',
                              'import py_compile,sys,json,os; py_compile.compile(sys.argv[1],doraise=True); print(json.dumps({"pid":os.getpid(),"compiled":True}))', bait], kind='probe')
                self.create(h)
                run = self.call(h, 'run-once', '--case-id', h['case_id'], cwd=shadow)
                snap = self.call(h, 'snapshot', '--case-id', h['case_id'])['result']
                observed = self.source_observer(h)
                self.check(snap['nodes'][0]['output'] == {'normalized': 'SYNTHETIC  sample'}
                           and observed['proofs'][0]['pid'] == run['pid']
                           and observed['source_sha256'] == hashes(self.package)[implementation],
                           'mutable original, cwd name and real pycache cannot replace verified installed bytes')

    def process_exited_observer(self, pid):
        code = '''import os,sys,json
pid=int(sys.argv[1])
if os.name=='nt':
 import ctypes
 from ctypes import wintypes
 k=ctypes.WinDLL('kernel32',use_last_error=True)
 k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
 k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.CloseHandle.argtypes=[wintypes.HANDLE]
 handle=k.OpenProcess(0x00100000,False,pid)
 if handle:
  exited=k.WaitForSingleObject(handle,0)==0;k.CloseHandle(handle)
 else: exited=ctypes.get_last_error()==87
else:
 try: os.kill(pid,0);exited=False
 except ProcessLookupError: exited=True
print(json.dumps({'pid':os.getpid(),'target_pid':pid,'exited':exited}))
'''
        return self.command([sys.executable, '-B', '-c', code, str(pid)], kind='observer')

    def S05(self):
        with self.target('install-replay', setup=False) as h:
            before = self.logical(h)
            replay = self.call(h, 'install', '--package', self.package, '--materials', self.materials, '--fixture', 'normalize-l3-v1')['result']
            self.check(replay == h['init'] and self.logical(h) == before, 'stable install replay is separate from registration; no core rows')
        for field in ('implementation_sha256', 'adapter', 'installation_id', 'interpreter'):
            with self.target('self-rehash') as h:
                self.create(h)
                before = self.logical(h)
                record_path = h['path'] / 'host/installation.json'
                record = read(record_path)
                if field == 'adapter':
                    record[field]['sha256'] = '0' * 64
                elif field == 'interpreter':
                    record[field]['executable_sha256'] = '0' * 64
                elif field == 'implementation_sha256':
                    source = h['path'] / 'host/package/components/normalize-submission/implementation.py'
                    source.write_text('def normalize(value):\n    return {"normalized":"TAMPERED"}\n', encoding='utf-8')
                    record[field] = hashlib.sha256(source.read_bytes()).hexdigest()
                    record['package_files']['components/normalize-submission/implementation.py'] = record[field]
                else:
                    record[field] = 'installation-forged'
                record.pop('record_digest')
                canonical = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
                record['record_digest'] = {'algorithm': 'sha256', 'canonicalization': 'json-sort-utf8-int-v1', 'value': hashlib.sha256(canonical).hexdigest()}
                write(record_path, record)
                denied = self.call(h, 'run-once', '--case-id', h['case_id'], code=2)
                self.check(denied['code'] == 'VERSION_CONFLICT' and self.logical(h) == before,
                           'self-rehashed ' + field + ' cannot replace original Case binding')
        code = '''import hashlib,json,sys,os
sys.path.insert(0,sys.argv[1])
from runtime_core.python_component import PythonComponent
from runtime_core.contract_adapter import ContractError
from pathlib import Path
source=Path(sys.argv[2]).read_bytes();p=PythonComponent(source,hashlib.sha256(source).hexdigest())
p._callable=lambda value:{'normalized':'CACHED WRONG CALLABLE'}
result=p.invoke({'text':'  SYNTHETIC  sample  '})
p._source=b'def normalize(value):\\n    return {"normalized":"TAMPERED"}\\n'
try: p.invoke({'text':'value'});code='UNEXPECTED_SUCCESS'
except ContractError as exc: code=exc.code
print(json.dumps({'pid':os.getpid(),'real_result':result,'tamper_code':code,'layer':'component-source-unit-probe'}))
'''
        probe = self.command([sys.executable, '-B', '-c', code, ROOT / 'src', self.package / 'components/normalize-submission/implementation.py'], kind='probe')
        self.check(probe['tamper_code'] == 'VERSION_CONFLICT' and probe['real_result'] == {'normalized': 'SYNTHETIC  sample'},
                   'adapter compiles validated bytes instead of a substituted cached callable')
        for fault in ('after_snapshot', 'before_activate', 'after_activate'):
            with self.target('install-' + fault, install=False) as h:
                self.call(h, 'install', '--package', self.package, '--materials', self.materials, '--fixture', 'normalize-l3-v1',
                          env={**self.env, 'WF2_INSTALL_FAULT': fault}, code=86)
                pending = h['path'].with_name(h['path'].name + '.pending')
                stage = h['path'] if fault == 'after_activate' else pending
                marker = read(stage / 'observations/install-pending.json')
                self.check(self.process_exited_observer(marker['pid'])['exited'], 'abrupt installer really exited at ' + fault)
                if fault == 'after_activate':
                    inspected = self.call(h, 'install-inspect')['result']['installation']
                    replay = self.call(h, 'install', '--package', self.package, '--materials', self.materials, '--fixture', 'normalize-l3-v1')['result']
                    self.check(replay['installation_id'] == inspected['installation_id'] and not self.logical(h)['registrations'],
                               'activation survived response loss; replay returns identity without guessing registration')
                else:
                    self.check(not h['path'].exists() and self.call(h, 'install-inspect', code=2)['code'] == 'HOST_BINDING_MISMATCH',
                               'partial installation is not publicly usable')
                    self.check(self.call(h, 'install', '--package', self.package, '--materials', self.materials,
                                         '--fixture', 'normalize-l3-v1', code=3)['code'] == 'IN_PROGRESS', 'pending state never silently activated or replaced')
                    if fault == 'before_activate':
                        self.check(not self.logical({'path': pending})['registrations'], 'prepared storage has no registrations or Case')
                    else:
                        self.check(not (pending / 'runtime/runtime.sqlite').exists(), 'snapshot interruption has no database')
                    self.result.setdefault('pending_cleanup_manifests', []).append({'path': str(pending), 'files_sha256': hashes(pending), 'installer_pid': marker['pid']})
                    self.checkpoint()
                    shutil.rmtree(pending)
                    self.check(self.absent_observer(pending)['absent'], 'known failed pending snapshot removed with evidence')

    def S06(self):
        with self.target('input-model-and-rule') as h:
            before = self.logical(h)
            for variant in ('missing', 'type', 'empty', 'long', 'extra'):
                control = self.control(h, 'input-' + variant)
                h['payload']['input_ref'] = control['input_ref']
                denied = self.create(h, code=2)
                self.check(denied['code'] == 'CONTRACT_INVALID' and self.logical(h) == before,
                           'input model rejects ' + variant + ' without materializing a Case')
            control = self.control(h, 'input-spaces')
            h['payload']['input_ref'] = control['input_ref']
            self.create(h)
            before_claim = self.logical(h)
            denied = self.call(h, 'run-once', '--case-id', h['case_id'], code=2)
            observed = self.call(h, 'install-inspect')['result']
            self.check(denied['code'] == 'RULE_DENIED' and self.logical(h) == before_claim and not observed['executions']
                       and all(c['provider'] != 'executor_ref' for c in observed['calls']),
                       'U+0020-only denial precedes attempt/lease and actual execution')
        with self.target('text-boundaries') as h:
            for variant, expected in [('inner', 'left  right'), ('tabs', '\tinside\t'),
                                      ('newline', '\ninside\n'), ('nbsp', '\u00a0inside\u00a0')]:
                control = self.control(h, 'input-' + variant)
                h['payload']['input_ref'] = control['input_ref']
                self.create(h)
                self.call(h, 'run-once', '--case-id', h['case_id'])
                snap = self.call(h, 'snapshot', '--case-id', h['case_id'])['result']
                self.check(snap['status'] == 'SUCCEEDED' and snap['nodes'][0]['output'] == {'normalized': expected},
                           'only boundary U+0020 removed: ' + variant)
            sql = self.logical(h)
            self.check(len(sql['cases']) == len(sql['attempts']) == 4, 'each accepted text uses one real Case and attempt')
        with self.target('valid-model-wrong-relation') as h:
            self.create(h)
            denied = self.call(h, 'host-test', '--case-id', h['case_id'], '--scenario', 'submit-output-mismatch', code=2)
            sql = self.logical(h)
            self.check(denied['code'] == 'CONTRACT_INVALID' and sql['cases'][0]['status'] == 'RUNNING'
                       and sql['cases'][0]['revision'] == 2 and sql['node_runs'][0]['output_ref'] is None
                       and not any(e['type'] == 'CASE_SUCCEEDED' for e in sql['events']),
                       'model-valid but mismatched candidate is not accepted or auto FAILED')

    def S07(self):
        # Alternative source snippets exercise ONLY the local ABI, not installation approval.
        # Every probe is a real subprocess; it cannot claim these snippets ran as a Case.
        vectors = [("raise KeyError('PRIVATE SENTINEL')", 'CONTRACT_INVALID'),
                   ("raise TypeError('PRIVATE SENTINEL')", 'CONTRACT_INVALID'),
                   ('return 1.5', 'CONTRACT_INVALID'), ('return (x for x in [])', 'CONTRACT_INVALID'),
                   ("return TypeError('PRIVATE SENTINEL')", 'CONTRACT_INVALID'),
                   ("value['text']='changed'; return {'normalized':'ok'}", 'CONTRACT_INVALID'),
                   ('return 1/0', 'INTERNAL_ERROR')]
        sources = [('def normalize(value):\n    ' + body + '\n', expected) for body, expected in vectors]
        sources += [("async def normalize(value):\n    return {'normalized':'ok'}\n", 'CONTRACT_INVALID'),
                    ("def normalize(value):\n    import os\n    return {'normalized':'ok'}\n", 'CONTRACT_INVALID')]
        code = '''import sys,json,hashlib,os
sys.path.insert(0,sys.argv[1])
from runtime_core.python_component import PythonComponent
from runtime_core.contract_adapter import ContractError
source=sys.argv[2].encode('utf-8');original={'text':'  safe  '}
try: PythonComponent(source,hashlib.sha256(source).hexdigest()).invoke(original);code='UNEXPECTED_SUCCESS'
except ContractError as exc: code=exc.code
print(json.dumps({'pid':os.getpid(),'code':code,'original':original,'layer':'component-boundary-unit-probe'}))
'''
        for source, expected in sources:
            observed = self.command([sys.executable, '-B', '-c', code, ROOT / 'src', source], kind='probe')
            self.check(observed['code'] == expected and observed['original'] == {'text': '  safe  '}
                       and 'PRIVATE SENTINEL' not in self.commands[-1]['stdout'], 'local author error class and caller copy preserved: ' + expected)
        with self.target('output-model-probes') as h:
            before = self.logical(h)
            code = '''import sys,json,os
sys.path.insert(0,sys.argv[1])
from runtime_core.package_host import PackageHost
from runtime_core.contract_adapter import ContractError
host=PackageHost(sys.argv[2]);results=[]
with host.lock():
 providers=host.providers(host.state['projection']['nodes'][0])
 for value in ({'normalized':''},{'normalized':'x'*81},{'normalized':'ok','extra':True},{'normalized':42}):
  try: providers.validate('output_contract_ref',value);results.append('UNEXPECTED_SUCCESS')
  except ContractError as exc: results.append(exc.code)
print(json.dumps({'pid':os.getpid(),'codes':results,'layer':'model-unit-probe'}))
'''
            probe = self.command([sys.executable, '-B', '-c', code, ROOT / 'src', h['path']], kind='probe')
            self.check(probe['codes'] == ['CONTRACT_INVALID'] * 4 and self.logical(h) == before,
                       'actual output model rejects empty/long/extra/type without a runtime transition')
        with self.target('actual-corrupt-sqlite', setup=False) as h:
            path = h['path'] / 'runtime/runtime.sqlite'
            path.write_bytes(b'SYNTHETIC CORRUPT SQLITE')
            expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            denied = self.call(h, 'install-inspect', code=4)
            self.check(denied['code'] == 'STORAGE_INVALID' and hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash,
                       'real database corruption remains STORAGE_INVALID/4; not repaired or auto initialized')

    def S08(self):
        with self.target('idempotency-revocation') as h:
            original = self.create(h, key='one-intent')
            self.call(h, 'run-once', '--case-id', h['case_id'])
            before = self.logical(h)
            calls = (h['path'] / 'observations/providers.jsonl').read_bytes()
            replay = self.create(h, key='one-intent')
            self.check(replay['replayed'] and replay['request_id'] != original['request_id']
                       and replay['result'] == original['result'] and replay['result']['status'] == 'QUEUED'
                       and self.logical(h) == before and (h['path'] / 'observations/providers.jsonl').read_bytes() == calls,
                       'new request_id replays original QUEUED Case, without new events or provider calls')
            changed = json.loads(json.dumps(h['payload']))
            changed['input_ref']['digest']['value'] = '0' * 64
            self.check(self.request(h, 'create', changed, key='one-intent', code=2)['code'] == 'IDEMPOTENCY_CONFLICT',
                       'same key different digest is not business deduplication')
            self.control(h, 'revoke-operation')
            for key in ('one-intent', 'unseen-intent'):
                denied = self.create(h, key=key, code=2)
                self.check(denied['code'] == 'UNAUTHORIZED' and 'result' not in denied, 'revoked known/unknown intent does not reveal history')
            self.check(self.logical(h) == before and (h['path'] / 'observations/providers.jsonl').read_bytes() == calls,
                       'conflict and revocation do not mutate core or invoke provider')
        points = ('after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response')
        for point in points:
            with self.target('create-atomic-' + point) as h:
                before = self.logical(h)
                self.control(h, 'fault-create-' + point)
                self.create(h, key='create-response-loss', code=86)
                after = self.logical(h)
                committed = point == 'after_commit_before_response'
                if not committed:
                    self.check(after == before, 'all SQLite tables roll back at create ' + point)
                    self.control(h, 'disarm-fault')
                retry = self.create(h, key='create-response-loss')
                final = self.logical(h)
                self.check(retry['replayed'] is committed and len(final['cases']) == len(final['node_runs']) == 1
                           and len(final['attempts']) == 0 and len(final['bindings']) == 1
                           and sum(e['case_id'] is not None for e in final['events']) == 2,
                           'create retry yields exactly one atomic original result')
        for point in points:
            with self.target('submit-atomic-' + point) as h:
                self.create(h)
                self.call(h, 'host-test', '--case-id', h['case_id'], '--scenario', 'submit-fault-' + point, code=86)
                after = self.logical(h)
                committed = point == 'after_commit_before_response'
                self.check(after['cases'][0]['status'] == ('SUCCEEDED' if committed else 'RUNNING')
                           and after['cases'][0]['revision'] == (3 if committed else 2)
                           and bool(after['node_runs'][0]['output_ref']) is committed
                           and bool(after['attempts'][0]['released']) is committed
                           and any(r['operation'] == 'submit_node_result' for r in after['idempotency_results']) is committed
                           and sum(e['case_id'] is not None for e in after['events']) == (6 if committed else 4),
                           'node, Case, evidence, intent result and events agree after submit ' + point)
                code = 0 if committed else 2
                replay = self.call(h, 'host-test', '--case-id', h['case_id'], '--scenario', 'submit-replay', code=code)
                self.check((replay.get('replayed') is True if committed else replay['code'] == 'LEASE_LOST')
                           and self.logical(h) == after, 'committed result replays; uncommitted attempt cannot be resumed by new PID')
                self.check(len(self.source_observer(h)['proofs']) == 1, 'failed commit does not retry author execution')

    def S09(self):
        with self.target('readonly-fresh-processes') as h:
            self.create(h)
            run = self.call(h, 'run-once', '--case-id', h['case_id'])
            self.check(self.process_exited_observer(run['pid'])['exited'], 'actual Worker PID exited before new reads')
            before = self.logical(h)
            calls = (h['path'] / 'observations/providers.jsonl').read_bytes()
            source_before = self.source_observer(h)
            snapshot = self.call(h, 'snapshot', '--case-id', h['case_id'])
            events = self.call(h, 'events', '--case-id', h['case_id'])
            source_after = self.source_observer(h)
            self.check(snapshot['pid'] != run['pid'] and events['pid'] != run['pid']
                       and self.logical(h) == before and (h['path'] / 'observations/providers.jsonl').read_bytes() == calls,
                       'fresh snapshot/events are read-only and call no provider')
            snap = snapshot['result']
            binding = json.loads(before['bindings'][0]['body'])
            node = before['node_runs'][0]
            output_ref = json.loads(node['output_ref'])
            evidence = next(row for row in before['evidence'] if row['evidence_id'] == output_ref['evidence_id'])
            persisted_events = [json.loads(row['body']) for row in before['events'] if row['case_id'] == h['case_id']]
            self.check(snap['binding'] == binding and snap['status'] == before['cases'][0]['status']
                       and snap['revision'] == before['cases'][0]['revision']
                       and snap['nodes'][0]['output'] == json.loads(evidence['content'])
                       and snap['nodes'][0]['output_ref'] == json.loads(evidence['reference'])
                       and events['result']['items'] == persisted_events
                       and events['result']['watermark'] == max(row['sequence'] for row in before['events']),
                       'SQLite URI mode=ro independently agrees with binding/evidence/events/Case')
            self.check(all(source_before[key] == source_after[key] for key in ('record', 'proofs', 'source_sha256')),
                       'fresh observer reads stable installed source, not cached callable')
            self.check(self.call(h, 'run-once', '--case-id', h['case_id'], code=2)['code'] == 'ALREADY_TERMINAL', 'repeat run-once is not result replay')
            self.control(h, 'revoke-read')
            for operation in ('snapshot', 'events'):
                denied = self.call(h, operation, '--case-id', h['case_id'], code=2)
                self.check(denied['code'] == 'UNAUTHORIZED' and 'result' not in denied, 'read revocation blocks ' + operation)
            self.check(self.logical(h) == before, 'read denial and terminal run leave ledger unchanged')
        with self.target('claim-crash-boundary') as h:
            self.create(h)
            self.call(h, 'host-test', '--case-id', h['case_id'], '--scenario', 'claim-crash', code=86)
            marker = next((h['path'] / 'observations').glob('process-session-*.json'))
            self.check(self.process_exited_observer(read(marker)['pid'])['exited'], 'claimed worker actually exited')
            before = self.logical(h)
            self.check(self.call(h, 'snapshot', '--case-id', h['case_id'])['result']['status'] == 'RUNNING', 'abandoned claim remains queryable')
            self.check(self.call(h, 'run-once', '--case-id', h['case_id'], code=3)['code'] == 'IN_PROGRESS', 'new process cannot take over live lease')
            self.control(h, 'advance-past-deadline')
            self.check(self.call(h, 'run-once', '--case-id', h['case_id'], code=2)['code'] == 'LEASE_LOST'
                       and self.logical(h) == before and not self.source_observer(h)['proofs'],
                       'expired claim is not auto resumed, retried, FAILED or executed')

    def S10(self):
        with self.derived('protected-neighbor', self.package) as neighbor:
            baseline = hashes(neighbor)
            with self.target('cleanup-guards', setup=False) as h:
                wrong = self.call(h, 'host-cleanup', '--manifest', neighbor / 'manifest.json', code=2)
                self.check(wrong['code'] == 'SANDBOX_INVALID' and h['path'].exists(), 'cleanup requires exact owning manifest')
                marker = h['path'] / 'observations' / ('process-session-' + 'a' * 32 + '.json')
                write(marker, {'pid': os.getpid(), 'synthetic_only': True})
                self.check(self.call(h, 'host-cleanup', '--manifest', h['path'] / 'manifest.json', code=3)['code'] == 'IN_PROGRESS',
                           'live owned-process marker blocks cleanup')
                marker.unlink()
                unknown = h['path'] / 'host/foreign.txt'
                unknown.write_text('SYNTHETIC UNOWNED CANDIDATE', encoding='utf-8')
                self.check(self.call(h, 'host-cleanup', '--manifest', h['path'] / 'manifest.json', code=2)['code'] == 'SANDBOX_INVALID'
                           and unknown.exists(), 'unrecognized nested file is preserved, not silently deleted')
                self.result.setdefault('injected_file_cleanup', []).append({'path': str(unknown), 'sha256': hashlib.sha256(unknown.read_bytes()).hexdigest()})
                self.checkpoint()
                unknown.unlink()
            self.check(hashes(neighbor) == baseline, 'cleanup left neighboring package untouched')
            link = self.root / ('junction-' + uuid.uuid4().hex)
            if os.name == 'nt':
                self.command(['cmd.exe', '/d', '/c', 'mklink', '/J', link, neighbor], kind='fixture', parse=False)
            else:
                link.symlink_to(neighbor, target_is_directory=True)
            with self.target('reject-junction', install=False) as h:
                self.check(self.call(h, 'install', '--package', link, '--materials', self.materials,
                                     '--fixture', 'normalize-l3-v1', code=2)['code'] == 'SANDBOX_INVALID', 'junction/symlink source rejected before reading code')
            self.result.setdefault('link_cleanup', []).append({'path': str(link), 'target': str(neighbor), 'reparse': True})
            self.checkpoint()
            os.rmdir(link) if os.name == 'nt' else link.unlink()
            self.check(hashes(neighbor) == baseline, 'link removal does not follow or modify target')
        with self.derived('hardlink-source', self.package) as package:
            alias = package / 'alias.bin'
            os.link(package / 'components/normalize-submission/implementation.py', alias)
            with self.target('reject-hardlink', install=False) as h:
                self.check(self.call(h, 'install', '--package', package, '--materials', self.materials,
                                     '--fixture', 'normalize-l3-v1', code=2)['code'] == 'SANDBOX_INVALID', 'hardlinked source rejected')
            self.result.setdefault('link_cleanup', []).append({'path': str(alias), 'hardlink': True})
            self.checkpoint()
            alias.unlink()
        for kind in ('large-file', 'file-count'):
            with self.derived(kind, self.package) as package:
                if kind == 'large-file':
                    (package / 'oversize.bin').write_bytes(b'x' * 2_000_001)
                    expected = 'SANDBOX_INVALID'
                else:
                    for index in range(257):
                        (package / (str(index) + '.txt')).write_text('SYNTHETIC', encoding='utf-8')
                    expected = 'INPUT_TOO_LARGE'
                with self.target('reject-' + kind, install=False) as h:
                    self.check(self.call(h, 'install', '--package', package, '--materials', self.materials,
                                         '--fixture', 'normalize-l3-v1', code=2)['code'] == expected, 'bounded snapshot rejects ' + kind)
        # Real complete legacy/unit regressions. Raw output + JUnit survive fixture cleanup.
        import xml.etree.ElementTree as ET
        suites = ('tests/runtime_m1', 'spikes/001-input-contract', 'spikes/002-authority-contract', 'tests/test_collaboration_docs.py')
        for suite in suites:
            junit = self.report.with_name(self.report.stem + '-' + suite.replace('/', '-') + '.xml')
            self.check(not junit.exists(), 'never overwrite earlier regression evidence')
            command = self.command([sys.executable, '-B', '-m', 'pytest', suite, '-q', '-p', 'no:cacheprovider',
                                    '--junitxml=' + str(junit)], kind='regression', timeout=900, parse=False)
            cases = ET.parse(junit).getroot().findall('.//testcase')
            self.check(bool(cases) and all(case.find(tag) is None for case in cases for tag in ('failure', 'error', 'skipped')),
                       'entire regression passed without skip: ' + suite)
            self.result.setdefault('regressions', []).append({'suite': suite, 'tests': len(cases), 'junit': str(junit),
                'junit_sha256': hashlib.sha256(junit.read_bytes()).hexdigest(), 'exit_code': command['exit_code']})
            self.checkpoint()

    def run(self, scenario):
        if self.audit and (scenario != 'S01' or self.evidence_scenario != 'S01'):
            raise ValueError('EVIDENCE_SCENARIO_UNSUPPORTED')
        selected = SCENARIOS if scenario == 'all' else (scenario,)
        self.result.update(scenario=scenario, scenario_count=len(selected), covered=[], all_passed=False)
        try:
            self.generate()
            for group in selected:
                self.group = group
                getattr(self, group)()
                self.result['covered'].append(group)
                self.checkpoint()
            self.check(self.source_before == {'reference': hashes(self.reference), 'tools': hashes(self.tools)}, 'original snapshots unchanged')
            self.check(hashes(self.generated) == self.generated_hashes, 'generated author sources unchanged')
            self.result['generation_cleanup_manifest'] = {'path': str(self.generated), 'files_sha256': self.generated_hashes}
            if self.audit:
                self.audit.remove_tree(self.generated)
            else:
                shutil.rmtree(self.generated)
            self.result['generation_cleaned'] = not self.generated.exists()
            self.check(all(t['cleaned'] for t in self.targets) and self.result['generation_cleaned'], 'all owned fixtures cleaned')
            self.check(set(self.result['covered']) == set(selected), 'requested scenarios enumerated exactly')
            if self.audit:
                self.audit.remove_tree(self.root)
                self.result['evidence_verification'] = self.audit.verify()
            self.result.update(all_passed=True, passed_levels=['L2'])
        except Exception as exc:
            self.result.update(error=type(exc).__name__ + ': ' + str(exc), all_passed=False, passed_levels=[])
        self.checkpoint()
        print(json.dumps({k: self.result.get(k) for k in ('all_passed', 'passed', 'failed', 'covered', 'error', 'evidence_ledger')}, ensure_ascii=False))
        return 0 if self.result['all_passed'] else 1

    def finish_byte_evidence(self):
        if not self.audit or self.evidence_scenario != 'bytes':
            raise ValueError('BYTE_EVIDENCE_NOT_ENABLED')
        self.audit.remove_tree(self.evidence_owner)
        return self.audit.verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sandbox', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--scenario', choices=(*SCENARIOS, 'all'), default='all')
    parser.add_argument('--show-commands', action='store_true')
    parser.add_argument('--evidence-dir', help='Local pre-cleanup export; supported only for S01')
    args = parser.parse_args()
    if args.evidence_dir is not None and args.scenario != 'S01':
        parser.error('--evidence-dir supports S01 only; no temporary root was created')
    return Acceptance(args.sandbox, args.report, args.show_commands,
                      evidence_dir=args.evidence_dir, evidence_scenario=args.scenario).run(args.scenario)


if __name__ == '__main__':
    raise SystemExit(main())
