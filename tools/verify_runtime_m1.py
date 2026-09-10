"""Independent M1 CLI acceptance. No imports of service/store/providers. Laiqh."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/runtime_core_cli.py'
SCENARIOS = ('normal', 'registration', 'trust', 'idempotency', 'atomicity', 'stale', 'restart', 'query', 'capabilities')
EVENTS = ['CASE_CREATED', 'NODE_READY', 'NODE_LEASED', 'NODE_STARTED', 'NODE_SUCCEEDED', 'CASE_SUCCEEDED']
POINTS = ('after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def local_path(path):
    p = Path(os.path.abspath(path))
    root = ROOT / '.local'
    assert p != root and p.is_relative_to(root), 'Only a new child of this worktree .local is permitted'
    for q in [p, *p.parents]:
        if q.exists() or q.is_symlink():
            st = q.lstat()
            assert not q.is_symlink() and not (getattr(st, 'st_file_attributes', 0) & 1024), 'Reparse path refused'
        if q == ROOT:
            break
    return p


class Acceptance:
    def __init__(self, sandbox, report, show):
        self.root, self.report, self.show = local_path(sandbox), local_path(report), show
        assert not self.root.exists() and not self.report.exists(), 'Never overwrite an earlier run'
        assert not self.report.is_relative_to(self.root), 'Report must survive cleanup'
        self.root.mkdir(parents=True)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.commands, self.checks, self.targets, self.live = [], [], [], []
        self.group = ''
        self.result = {'synthetic_only': True, 'production_authorized': False, 'required_levels': ['L1', 'L2'],
                       'scope': 'this report L2 only; L1 JUnit separate', 'commands': self.commands,
                       'checks': self.checks, 'targets': self.targets, 'all_passed': False}
        dump(self.root / 'acceptance-manifest.json', {'path': str(self.root), 'run_id': uuid.uuid4().hex, 'owned_targets': []})

    def checkpoint(self):
        self.result.update(passed=sum(x['passed'] for x in self.checks), failed=sum(not x['passed'] for x in self.checks))
        dump(self.report, self.result)
        dump(self.root / 'acceptance-manifest.json', {'path': str(self.root), 'owned_targets': self.targets})

    def check(self, condition, label, covers=()):
        self.checks.append({'scenario': self.group, 'label': label, 'passed': bool(condition), 'covers': list(covers)})
        self.checkpoint()
        assert condition, label

    def start(self, argv):
        p = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        self.live.append(p)
        return p

    def finish(self, p, argv, expected=0, parse=True, timeout=55):
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout, stderr = p.communicate(timeout=10)
            self.commands.append({'scenario': self.group, 'argv': argv, 'pid': p.pid, 'exit_code': p.returncode,
                                  'stdout': stdout, 'stderr': stderr, 'timed_out': True})
            self.checkpoint()
            raise AssertionError('Owned child exceeded acceptance timeout')
        self.commands.append({'scenario': self.group, 'argv': argv, 'pid': p.pid, 'exit_code': p.returncode,
                              'expected_exit': expected, 'exited': p.poll() is not None, 'stdout': stdout, 'stderr': stderr})
        self.checkpoint()
        if self.show:
            print(json.dumps(self.commands[-1], ensure_ascii=False), flush=True)
        assert p.returncode == expected, self.commands[-1]
        if expected == 86:
            assert stdout == '', 'Crash must not emit success'
            return None
        return json.loads(stdout) if parse else stdout

    def cli_args(self, h, *args):
        return [sys.executable, '-B', str(CLI), '--sandbox', str(h['path']), *args]

    def call(self, h, *args, code=0):
        argv = self.cli_args(h, *args)
        value = self.finish(self.start(argv), argv, code)
        if value is not None:
            assert value['synthetic_only'] and not value['production_authorized'] and value['contract_status'] == 'DRAFT'
        return value

    def request(self, h, operation, payload, key=None, code=0, request_id=None):
        name = uuid.uuid4().hex
        path = h['path'] / 'requests' / (name + '.json')
        dump(path, {'request_id': request_id or 'req-' + name, 'idempotency_key': key or 'key-' + name, 'payload': payload})
        return self.call(h, operation, '--request', str(path), code=code)

    @contextmanager
    def target(self, label, setup=True):
        h = {'path': self.root / (label + '-' + uuid.uuid4().hex)}
        target = {'path': str(h['path']), 'scenario': self.group, 'cleaned': False}
        self.targets.append(target)
        ok = False
        try:
            h['init'] = self.call(h, 'host-init')['result']
            target.update(sandbox_id=h['init']['sandbox_id'], manifest=h['init']['manifest'])
            if setup:
                self.setup(h)
            yield h
            ok = True
        finally:
            # Failed scenarios preserve owned targets and evidence, never hide a failure.
            if ok:
                observed = self.logical(h)
                target['final_statuses'] = [row[1] for row in observed['cases']]
                self.call(h, 'host-cleanup', '--manifest', str(h['path'] / 'manifest.json'))
                argv = [sys.executable, '-B', '-c', 'import pathlib,sys,json; print(json.dumps({"absent":not pathlib.Path(sys.argv[1]).exists()}))', str(h['path'])]
                fresh = self.finish(self.start(argv), argv)
                target['cleaned'] = fresh['absent'] and all(p.poll() is not None for p in self.live)
                self.check(target['cleaned'], label + ': fresh-process cleanup confirmation')
            self.checkpoint()

    def setup(self, h):
        r = self.call(h, 'register', '--request', str(h['path'] / 'requests/register.json'))['result']
        h['registration'] = r['registration_id']
        self.request(h, 'set-state', {'registration_id': h['registration'], 'expected_revision': 1, 'target_state': 'ENABLED'})
        h['create'] = {'registration_id': h['registration'], 'input_ref': h['init']['input_ref'], 'object_refs': h['init']['object_refs']}

    def create(self, h, key='create-one'):
        value = self.request(h, 'create', h['create'], key=key)
        h['case'] = value['result']['case_id']
        return value

    def logical(self, h):
        # Fresh external observer, stdlib SQLite only; never application Store.
        code = ('import sqlite3,pathlib,sys,json; p=pathlib.Path(sys.argv[1]); '
                'c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True); c.execute("BEGIN"); '
                'names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type=\'table\' ORDER BY name")]; '
                'result={n:c.execute(\'SELECT * FROM "\'+n+\'" ORDER BY rowid\').fetchall() for n in names}; '
                'c.close(); print(json.dumps(result,ensure_ascii=False))')
        argv = [sys.executable, '-B', '-c', code, str(h['path'] / 'runtime/runtime.sqlite')]
        return self.finish(self.start(argv), argv)

    def calls(self, h):
        return self.call(h, 'host-inspect')['result']['calls']

    def control(self, h, scenario):
        return self.call(h, 'host-control', '--scenario', scenario)

    def test(self, h, scenario, code=0):
        return self.call(h, 'host-test', '--case-id', h['case'], '--scenario', scenario, code=code)

    def normal(self):
        with self.target('中文 normal') as h:
            created = self.create(h)
            self.check(created['result']['status'] == 'QUEUED' and created['commit_revision'] == 1, 'create is durable QUEUED', ['F01'])
            run = self.call(h, 'run-once', '--case-id', h['case'])
            previous = self.commands[-1]
            self.check(run['result']['status'] == 'SUCCEEDED' and run['commit_revision'] == 3, 'pure node accepted by core', ['F01'])
            before = self.logical(h)
            snap = self.call(h, 'snapshot', '--case-id', h['case'])
            fresh = self.commands[-1]
            events = self.call(h, 'events', '--case-id', h['case'])['result']
            self.check(previous['exited'] and fresh['pid'] != previous['pid'], 'old process exited, different fresh query PID', ['F12'])
            self.check(snap['result']['case_id'] == h['case'] and snap['result']['revision'] == 3 and
                       snap['result']['nodes'][0]['output'] == {'echo': 'SYNTHETIC RC0'}, 'fresh output and binding')
            self.check([x['type'] for x in events['items']] == EVENTS and [x['case_revision'] for x in events['items']] == [1, 1, 2, 2, 3, 3], 'six independently specified case events')
            self.check(not events['has_more'] and events['next_cursor'] is None and all(x['sequence'] <= events['watermark'] for x in events['items']), 'complete bounded event window')
            self.check(len(before['cases']) == len(before['node_runs']) == len(before['attempts']) == 1 and len(before['evidence']) == 2
                       and len(before['events']) == 8 and len(before['idempotency_results']) == 5 and not before['ready_nodes'], 'independent ledger cardinality and no successor')
            output = snap['result']['nodes'][0]['output_ref']
            self.check(output['digest']['value'] == hashlib.sha256(b'{"echo":"SYNTHETIC RC0"}').hexdigest(), 'stdlib output digest')
            self.check({x['provider'] for x in self.calls(h)} == {'data_provider_ref', 'validator_ref', 'rule_provider_ref', 'executor_ref'}, 'four actual provider call paths')
            self.check(self.logical(h) == before, 'queries never advance logical ledger')
            self.result['normal_case_id'] = h['case']

    def registration(self):
        with self.target('registration', setup=False) as h:
            r = self.call(h, 'register', '--request', str(h['path'] / 'requests/register.json'))['result']
            payload = {'registration_id': r['registration_id'], 'input_ref': h['init']['input_ref'], 'object_refs': h['init']['object_refs']}
            self.check(self.request(h, 'create', payload, code=2)['code'] == 'BUSINESS_NOT_ENABLED', 'registered is not enabled', ['F02'])
            self.request(h, 'set-state', {'registration_id': r['registration_id'], 'expected_revision': 1, 'target_state': 'ENABLED'})
            h['registration'], h['create'] = r['registration_id'], payload
            self.create(h)
            state = {'registration_id': h['registration'], 'expected_revision': 1, 'target_state': 'STOP_NEW'}
            self.check(self.request(h, 'set-state', state, code=2)['code'] == 'REVISION_CONFLICT', 'stale registration revision')
            state['expected_revision'] = 2
            self.request(h, 'set-state', state)
            before = self.logical(h)
            self.check(self.request(h, 'create', payload, key='new', code=2)['code'] == 'BUSINESS_NOT_ENABLED', 'STOP_NEW denies new case')
            self.check(self.request(h, 'create', payload, key='create-one')['replayed'], 'STOP_NEW preserves authorized history')
            self.check(self.logical(h) == before, 'registration rejection no write')
        with self.target('version') as h:
            before = self.logical(h)
            self.control(h, 'publish-version-conflict')
            self.check(self.call(h, 'register', '--request', str(h['path'] / 'requests/register-variant.json'), code=2)['code'] == 'VERSION_CONFLICT', 'same business version different content', ['F03'])
            self.check(self.logical(h) == before, 'no registration replacement')

    def trust(self):
        for scenario, expected, exit_code in [('fake-admission', 'DEPENDENCY_UNAVAILABLE', 3), ('unknown-provider', 'UNKNOWN_PROVIDER', 2),
                ('missing-implementation', 'CAPABILITY_UNSUPPORTED', 2), ('mutate-definition', 'VERSION_DIGEST_MISMATCH', 2),
                ('revoke-grant', 'REVOKED', 2), ('revoke-provider', 'REVOKED', 2), ('authority-gap', 'AUTHORITY_SYNC_GAP', 2),
                ('authority-stale', 'AUTHORITY_VIEW_STALE', 2), ('authority-rollback', 'REVOCATION_ROLLBACK', 2)]:
            with self.target(scenario) as h:
                self.control(h, scenario)
                before = self.logical(h)
                for _ in range(2):
                    response = self.request(h, 'create', h['create'], code=exit_code)
                    self.check(response['code'] == expected, 'persistent trusted refusal ' + scenario, ['F03', 'F04', 'F05', 'F14'])
                self.check(self.logical(h) == before, 'no writes on trust refusal')
        with self.target('forged') as h:
            before = self.logical(h)
            payload = {**h['create'], 'approved': True, 'auth_context': {'role': 'admin'}}
            self.check(self.request(h, 'create', payload, code=2)['code'] == 'SCHEMA_INVALID', 'request cannot supply authority', ['F04'])
            self.check(self.logical(h) == before, 'forged request no writes')
        with self.target('copy-source') as source:
            self.create(source)
            with self.target('copy-destination', setup=False) as dest:
                shutil.copy2(source['path'] / 'runtime/runtime.sqlite', dest['path'] / 'runtime/runtime.sqlite')
                self.check(self.call(dest, 'snapshot', '--case-id', source['case'], code=2)['code'] == 'HOST_BINDING_MISMATCH', 'copying runtime DB cannot copy permission', ['F14'])

    def idempotency(self):
        with self.target('history') as h:
            created = self.create(h)
            completed = self.call(h, 'run-once', '--case-id', h['case'])
            before, calls = self.logical(h), self.calls(h)
            replay = self.request(h, 'create', h['create'], key='create-one', request_id='changed-id')
            self.check(replay['replayed'] and replay['result'] == created['result'] and replay['request_id'] == 'changed-id', 'stable historical create with new transport id', ['F07'])
            changed = deepcopy(h['create'])
            changed['input_ref']['digest']['value'] = 'a' * 64
            self.check(self.request(h, 'create', changed, key='create-one', code=2)['code'] == 'IDEMPOTENCY_CONFLICT', 'same key different content conflict', ['F07'])
            self.control(h, 'advance-past-deadline')
            replay = self.test(h, 'submit-replay')
            self.check(replay['replayed'] and replay['result'] == completed['result'], 'expired historical submit returns original', ['F10'])
            self.check(self.test(h, 'submit-new-key', 2)['code'] == 'INVALID_STATE', 'terminal not reversible via new key', ['F17'])
            self.check(self.logical(h) == before and self.calls(h) == calls, 'history invokes no providers and changes no rows')
        for permission in ('revoke-operation', 'revoke-read'):
            with self.target(permission) as h:
                self.create(h)
                self.control(h, permission)
                before = self.logical(h)
                for key in ('create-one', 'unknown'):
                    result = self.request(h, 'create', h['create'], key=key, code=2)
                    self.check(result['code'] == 'UNAUTHORIZED' and h['case'] not in json.dumps(result), 'current rights before known/unknown history', ['F06'])
                if permission == 'revoke-read':
                    self.check(self.call(h, 'snapshot', '--case-id', h['case'], code=2)['code'] == 'UNAUTHORIZED', 'read rights revoked')
                self.call(h, 'host-inspect')
                self.check(self.logical(h) == before, 'inspector read does not grant original operation')

    def atomicity(self):
        for point in POINTS:
            with self.target('create-' + point) as h:
                before = self.logical(h)
                self.control(h, 'fault-create-' + point)
                self.request(h, 'create', h['create'], key='fault', code=86)
                after = self.logical(h)
                committed = point == 'after_commit_before_response'
                self.check((len(after['cases']) == 1 and len(after['events']) == 4) if committed else after == before, 'create commit boundary ' + point, ['F08', 'F09'])
                calls = self.calls(h)
                self.control(h, 'disarm-fault')
                replay = self.request(h, 'create', h['create'], key='fault')
                self.check(replay['replayed'] == committed and len(self.logical(h)['cases']) == 1, 'original create request retry at most one case')
                if committed:
                    self.check(self.calls(h) == calls, 'commit response loss replay skips providers')
            with self.target('submit-' + point) as h:
                self.create(h)
                self.test(h, 'submit-fault-' + point, 86)
                after = self.logical(h)
                snapshot = self.call(h, 'snapshot', '--case-id', h['case'])['result']
                self.check(snapshot['status'] == ('SUCCEEDED' if committed else 'RUNNING') and snapshot['revision'] == (3 if committed else 2), 'submit commit boundary ' + point, ['F08', 'F09'])
                self.check(len(after['events']) == (8 if committed else 6) and len(after['evidence']) == (2 if committed else 1)
                           and len(after['idempotency_results']) == (5 if committed else 4) and len(after['ready_nodes']) == (0 if committed else 1), 'state/receipt/events/evidence/readiness agree')
                calls = self.calls(h)
                replay = self.test(h, 'submit-replay', 0 if committed else 2)
                self.check(replay.get('replayed') if committed else replay['code'] == 'LEASE_LOST', 'new process history or explicit lost lease')
                self.check(self.logical(h) == after and self.calls(h) == calls, 'no duplicate completion after process crash')

    def stale(self):
        cases = [('bad-owner', 'LEASE_LOST', 2), ('bad-attempt', 'LEASE_LOST', 2), ('bad-lease', 'LEASE_LOST', 2),
                 ('expired', 'LEASE_LOST', 2), ('mutate-input', 'INPUT_STALE', 2), ('tamper-input', 'VERSION_DIGEST_MISMATCH', 2),
                 ('expire-input', 'INPUT_STALE', 2), ('revoke-provider', 'REVOKED', 2), ('revoke-grant', 'REVOKED', 2),
                 ('deny-rule', 'RULE_DENIED', 2), ('needs-input', 'CAPABILITY_UNSUPPORTED', 2),
                 ('rule-unavailable', 'DEPENDENCY_UNAVAILABLE', 3), ('output-mismatch', 'CONTRACT_INVALID', 2), ('elapsed', 'LEASE_LOST', 2)]
        for scenario, expected, exit_code in cases:
            with self.target('stale-' + scenario) as h:
                self.create(h)
                started = time.monotonic()
                result = self.test(h, 'submit-' + scenario, exit_code)
                self.check(result['code'] == expected, 'submission recheck ' + scenario, ['F10', 'F11', 'F15'])
                if scenario == 'elapsed':
                    self.check(time.monotonic() - started >= 30, 'real elapsed deadline, not only synthetic clock')
                rows = self.logical(h)
                self.check(rows['cases'][0][1:3] == ['RUNNING', 2] and len(rows['evidence']) == 1 and len(rows['events']) == 6,
                           'rejected result never advances or publishes output')

    def restart(self):
        with self.target('lost-claim') as h:
            self.create(h)
            self.test(h, 'claim-crash', 86)
            self.control(h, 'advance-past-deadline')
            before = self.logical(h)
            snapshot = self.call(h, 'snapshot', '--case-id', h['case'])['result']
            self.check(snapshot['status'] == 'RUNNING' and snapshot['revision'] == 2 and snapshot['blockers'] == ['LEASE_LOST'], 'restart observes blocked unfinished claim', ['F12'])
            self.check(self.call(h, 'run-once', '--case-id', h['case'], code=2)['code'] == 'LEASE_LOST', 'no automatic reclaim')
            self.check(self.logical(h) == before and len(before['attempts']) == 1, 'no new case or attempt')
        with self.target('claim-history') as h:
            self.create(h)
            self.check(self.test(h, 'claim-replay')['replayed'], 'claim history does not reacquire or execute twice')
            rows = self.logical(h)
            self.check(len(rows['attempts']) == 1 and len(rows['events']) == 6, 'claim replay leaves single attempt')

    def query(self):
        with self.target('query-cross-process') as h:
            self.create(h)
            argv = self.cli_args(h, 'host-test', '--case-id', h['case'], '--scenario', 'snapshot-barrier')
            reader = self.start(argv)
            ready = h['path'] / 'observations/query-ready.json'
            deadline = time.monotonic() + 15
            while not ready.exists() and reader.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.check(ready.exists(), 'reader has opened actual SQLite snapshot')
            self.check(self.call(h, 'host-cleanup', '--manifest', str(h['path'] / 'manifest.json'), code=3)['code'] == 'IN_PROGRESS', 'active reader prevents cleanup')
            self.call(h, 'run-once', '--case-id', h['case'])
            self.check(reader.poll() is None, 'writer committed while old reader remained open', ['F16'])
            self.control(h, 'release-query')
            old = self.finish(reader, argv)['result']
            self.check(old['status'] == 'QUEUED' and old['revision'] == 1 and old['watermark'] == 4, 'snapshot and watermark share old view')
            before = self.logical(h)
            current = self.call(h, 'snapshot', '--case-id', h['case'])['result']
            self.check(current['status'] == 'SUCCEEDED' and current['watermark'] == 8, 'fresh query observes new commit')
            for flag in ('--cursor', '--filter', '--limit'):
                self.check(self.call(h, 'events', '--case-id', h['case'], flag, '1', code=2)['code'] == 'CAPABILITY_UNSUPPORTED', 'unsupported query options reject')
            self.check(self.logical(h) == before, 'read purity by logical rows')
            self.test(h, 'event-overflow')
            before = self.logical(h)
            self.check(self.call(h, 'events', '--case-id', h['case'], code=2)['code'] == 'CAPABILITY_UNSUPPORTED', 'over-cap events refuse rather than truncate', ['F16'])
            self.check(self.logical(h) == before, 'over-cap rejection is read-only')

    def capabilities(self):
        variants = {'ai': 'CAPABILITY_UNSUPPORTED', 'human': 'CAPABILITY_UNSUPPORTED', 'multi-node': 'CAPABILITY_UNSUPPORTED',
                    'wait': 'CAPABILITY_UNSUPPORTED', 'readback': 'CAPABILITY_UNSUPPORTED', 'action': 'CAPABILITY_UNSUPPORTED',
                    'resources': 'CAPABILITY_UNSUPPORTED', 'retry': 'CAPABILITY_UNSUPPORTED', 'timeout': 'CAPABILITY_UNSUPPORTED',
                    'wrong-role': 'PROVIDER_ROLE_MISMATCH', 'condition': 'SCHEMA_INVALID', 'cycle': 'NODE_CYCLE'}
        for variant, expected in variants.items():
            with self.target(variant, setup=False) as h:
                self.control(h, 'publish-' + variant)
                result = self.call(h, 'register', '--request', str(h['path'] / 'requests/register-variant.json'), code=2)
                self.check(result['code'] == expected and not self.logical(h)['registrations'], 'published capability or graph gate ' + variant, ['F13', 'F18'])
        with self.target('unknown-operation') as h:
            self.create(h)
            before = self.logical(h)
            for args in [('resume_case',), ('submit_node_result',), ('execute-module', '--module', 'os'), ('host-inspect', '--request', 'ignored')]:
                self.check(self.call(h, *args, code=2)['code'] in {'INPUT_INVALID', 'CAPABILITY_UNSUPPORTED'}, 'unknown/irrelevant input rejected', ['F17'])
            self.check(self.logical(h) == before, 'no hidden success on unsupported operation')

    def run(self, scenario):
        selected = SCENARIOS if scenario == 'all' else (scenario,)
        try:
            for group in selected:
                self.group = group
                getattr(self, group)()
            covered = sorted({x for c in self.checks if c['passed'] for x in c['covers']})
            if scenario == 'all':
                self.check(set(covered) == {'F%02d' % i for i in range(1, 19)}, 'F01-F18 coverage enumerated')
            self.result.update(all_passed=all(x['passed'] for x in self.checks) and all(t['cleaned'] for t in self.targets),
                               covered=covered, scenario=scenario, passed_levels=['L2'],
                               business_status='synthetic_local_only', unverified=['L1 reported separately', 'controller independent review', 'M2-M6', 'human L3', 'production L4', 'cross-machine authority'])
        except Exception as exc:
            self.result.update(error=type(exc).__name__ + ': ' + str(exc), all_passed=False, passed_levels=[])
            for p in self.live:
                if p.poll() is None:
                    p.kill()
                    p.communicate(timeout=10)
            self.result['owned_processes_exited'] = all(p.poll() is not None for p in self.live)
        self.checkpoint()
        print(json.dumps({k: self.result.get(k) for k in ('all_passed', 'passed', 'failed', 'covered', 'error')}, ensure_ascii=False))
        return 0 if self.result['all_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sandbox', required=True)
    parser.add_argument('--scenario', choices=(*SCENARIOS, 'all'), required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--show-commands', action='store_true')
    args = parser.parse_args()
    return Acceptance(args.sandbox, args.report, args.show_commands).run(args.scenario)


if __name__ == '__main__':
    raise SystemExit(main())
