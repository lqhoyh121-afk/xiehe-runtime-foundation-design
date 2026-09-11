"""M1 runtime transitions, common authorization and idempotency gate. Laiqh."""
from copy import deepcopy
import json
import time
from datetime import timedelta

from .contract_adapter import (ContractError, digest, exact, key, request_digest, request_shape, require, shape, timestamp)
from .store import Store, encode
from .synthetic_host import ident


FIELDS = {
    'register': {'business_ref', 'definition_ref', 'contract_version', 'provider_bindings', 'admission_ref'},
    'set-state': {'registration_id', 'expected_revision', 'target_state'},
    'create': {'registration_id', 'input_ref', 'object_refs'},
    'claim': {'instance_id', 'case_id'},
    'submit': {'case_id', 'node_run_id', 'attempt_id', 'lease_token', 'input_snapshot_ref', 'outcome', 'output_ref', 'evidence_refs'},
}
OPERATIONS = {'register': 'register_business', 'set-state': 'set_business_state', 'create': 'create_case', 'claim': 'claim_node', 'submit': 'submit_node_result'}


class Service:
    def __init__(self, host):
        self.host = host

    def execute(self, operation, request, role):
        request_shape(request)
        require(operation in FIELDS, 'CAPABILITY_UNSUPPORTED')
        p = request['payload']
        exact(p, FIELDS[operation])
        if operation in {'claim', 'submit'}:
            return self.node_command(operation, request, role)
        with self.host.lock():
            self.host.authorize(operation, role)
            db = self.host.store.connect(readonly=True)
            try:
                registration = None
                if operation == 'register':
                    shape('DefinitionRef', p['business_ref'])
                    shape('DefinitionRef', p['definition_ref'])
                    shape('AuthorityRef', p['admission_ref'])
                    natural = {k: p['business_ref'][k] for k in ('kind', 'namespace', 'id', 'version')}
                    target = key(natural)
                    registration = Store.one(db, 'registrations', 'natural_key', target)
                    binding = json.loads(registration['binding']) if registration else self.host.resolve_binding(p)
                    semantic = {**deepcopy(p), 'projection_digest': binding['projection_digest']}
                else:
                    shape('Id', p['registration_id'])
                    target = p['registration_id']
                    registration = Store.one(db, 'registrations', 'registration_id', target)
                    require(registration is not None, 'CONTRACT_INVALID')
                    binding = json.loads(registration['binding'])
                    semantic = deepcopy(p)
                    if operation == 'create':
                        shape('EvidenceRef', p['input_ref'])
                        require(type(p['object_refs']) is list and len(p['object_refs']) > 0, 'SCHEMA_INVALID')
                        for ref in p['object_refs']:
                            shape('ObjectRef', ref)
                        require(len({key(r) for r in p['object_refs']}) == len(p['object_refs']), 'SCHEMA_INVALID')
                        semantic['binding'] = binding
                    else:
                        require(type(p['expected_revision']) is int and 1 <= p['expected_revision'] <= 9007199254740991, 'SCHEMA_INVALID')
                        require(type(p['target_state']) is str, 'SCHEMA_INVALID')
                        require(p['target_state'] in {'ENABLED', 'STOP_NEW'}, 'CAPABILITY_UNSUPPORTED')
                slot, hashed = self.identity(operation, request, target, semantic)
                replay = self.replay(db, slot, hashed, request)
                if replay:
                    return replay
            finally:
                db.close()
            if operation == 'register':
                fresh = self.host.resolve_binding(p)
                self.host.validate(fresh)
                if registration:
                    require(fresh == binding, 'VERSION_CONFLICT')
                    result = self.registration_result(registration, binding)
                    return self.commit(operation, request, slot, hashed, result, registration['revision'], [], lambda db: None, lambda db: None)
                binding = fresh
                rid = ident('registration')
                result = self.registration_result({'registration_id': rid, 'state': 'REGISTERED', 'revision': 1}, binding)
                # Explicit column list prevents schema/arity drift.
                def state(db):
                    db.execute('INSERT INTO registrations(registration_id,natural_key,state,revision,binding) VALUES(?,?,?,?,?)',
                               (rid, target, 'REGISTERED', 1, encode(binding)))
                events = [self.event('REGISTRATION_REGISTERED', role, request, details={'registration_id': rid})]
                return self.commit(operation, request, slot, hashed, result, 1, events, state, lambda db: None)
            if operation == 'set-state':
                require(p['expected_revision'] == registration['revision'], 'REVISION_CONFLICT')
                old, new = registration['state'], p['target_state']
                if new == 'ENABLED':
                    require(old != 'STOP_NEW', 'CAPABILITY_UNSUPPORTED')
                    self.host.validate(binding)
                require(old == new or (old, new) in {('REGISTERED', 'ENABLED'), ('ENABLED', 'STOP_NEW')}, 'INVALID_STATE')
                revision = registration['revision'] + int(old != new)
                result = {'registration_id': target, 'state': new, 'revision': revision, 'readiness': 'READY', 'blockers': []}
                def state(db):
                    db.execute('UPDATE registrations SET state=?,revision=? WHERE registration_id=?', (new, revision, target))
                events = [] if old == new else [self.event('BUSINESS_ENABLED' if new == 'ENABLED' else 'BUSINESS_STOPPED', role, request, details={'registration_id': target})]
                return self.commit(operation, request, slot, hashed, result, revision, events, state, lambda db: None)
            require(registration['state'] == 'ENABLED', 'BUSINESS_NOT_ENABLED')
            self.host.validate(binding)
            node = binding['projection']['nodes'][0]
            content = self.host.providers(node).data(p['input_ref'], p['object_refs'])
            cid, nid, bid = ident('case'), ident('node'), ident('binding')
            case_binding = {**deepcopy(binding), 'registration_id': target, 'input_ref': p['input_ref'], 'object_refs': p['object_refs']}
            result = {'case_id': cid, 'revision': 1, 'status': 'QUEUED', 'binding_ref': bid}
            def state(db):
                db.execute('INSERT INTO bindings VALUES(?,?,?)', (bid, target, encode(case_binding)))
                db.execute('INSERT INTO cases VALUES(?,?,?,?)', (cid, 'QUEUED', 1, bid))
                db.execute('INSERT INTO node_runs VALUES(?,?,?,?,?,NULL)', (nid, cid, node['node_id'], 'READY', encode(p['input_ref'])))
                self.evidence(db, p['input_ref'], content)
            def ready(db):
                db.execute('INSERT INTO ready_nodes VALUES(?,0)', (nid,))
            events = [self.event(t, role, request, cid, 1, nid, None, bid) for t in ('CASE_CREATED', 'NODE_READY')]
            return self.commit(operation, request, slot, hashed, result, 1, events, state, ready)

    def identity(self, operation, request, target, semantic):
        s = self.host.state
        op = OPERATIONS[operation]
        slot = (key(s['scope']), s['identity']['namespace'], op, target, request['idempotency_key'])
        hashed = request_digest(op, s['scope'], s['identity']['namespace'], target, semantic)
        return slot, key(hashed)

    def replay(self, db, slot, hashed, request):
        row = db.execute('SELECT * FROM idempotency_results WHERE scope=? AND namespace=? AND operation=? AND target=? AND idempotency_key=?', slot).fetchone()
        if row is None:
            return None
        require(row['digest'] == hashed, 'IDEMPOTENCY_CONFLICT')
        return {'request_id': request['request_id'], 'replayed': True, 'commit_revision': row['commit_revision'], 'result': json.loads(row['result'])}

    def event(self, kind, role, request, case=None, revision=None, node=None, attempt=None, binding=None, details=None):
        return {'event_id': ident('event'), 'case_id': case, 'case_revision': revision, 'node_run_id': node,
                'attempt_id': attempt, 'type': kind, 'recorded_at': self.host.state['now'], 'actor_ref': self.host.actor(role),
                'trace_id': ident('trace'), 'causation_id': request['request_id'], 'binding_ref': binding, 'details': details or {}}

    def commit(self, operation, request, slot, hashed, result, revision, events, state, ready):
        with self.host.store.write() as db:
            state(db)
            self.host.fault(operation, 'after_state')
            db.execute('INSERT INTO idempotency_results VALUES(?,?,?,?,?,?,?,?)', (*slot, hashed, encode(result), revision))
            self.host.fault(operation, 'after_idempotency')
            for event in events:
                cur = db.execute('INSERT INTO events(event_id,case_id,case_revision,type,body) VALUES(?,?,?,?,?)',
                                 (event['event_id'], event['case_id'], event['case_revision'], event['type'], encode(event)))
                event['sequence'] = cur.lastrowid
                db.execute('UPDATE events SET body=? WHERE sequence=?', (encode(event), cur.lastrowid))
            self.host.fault(operation, 'after_events')
            ready(db)
            self.host.fault(operation, 'before_commit')
        self.host.fault(operation, 'after_commit_before_response')
        return {'request_id': request['request_id'], 'replayed': False, 'commit_revision': revision, 'result': result}

    @staticmethod
    def registration_result(row, binding):
        return {'registration_id': row['registration_id'], 'business_ref': binding['projection']['business_ref'],
                'resolved_digest': binding['projection_digest'], 'state': row['state'], 'revision': row['revision'],
                'readiness': 'READY', 'blockers': []}

    @staticmethod
    def evidence(db, ref, content):
        old = Store.one(db, 'evidence', 'evidence_id', ref['evidence_id'])
        if old:
            require(json.loads(old['reference']) == ref and json.loads(old['content']) == content, 'CONTRACT_INVALID')
        else:
            db.execute('INSERT INTO evidence VALUES(?,?,?)', (ref['evidence_id'], encode(ref), encode(content)))

    def case_records(self, db, case_id):
        shape('Id', case_id)
        case = Store.one(db, 'cases', 'case_id', case_id)
        require(case is not None, 'CONTRACT_INVALID')
        node = Store.one(db, 'node_runs', 'case_id', case_id)
        binding = json.loads(Store.one(db, 'bindings', 'binding_ref', case['binding_ref'])['body'])
        attempt = Store.one(db, 'attempts', 'node_run_id', node['node_run_id'])
        return case, node, binding, attempt

    def check_execution(self, lease):
        with self.host.lock():
            self.host.authorize('claim', 'worker')
            db = self.host.store.connect(readonly=True)
            try:
                case, node, binding, attempt = self.case_records(db, lease['case_id'])
                require(case['status'] == node['status'] == 'RUNNING', 'INVALID_STATE')
                require(attempt is not None and attempt['attempt_id'] == lease['attempt_id']
                        and attempt['owner'] == self.host.session and attempt['lease_token'] == lease['lease_token']
                        and not attempt['released'], 'LEASE_LOST')
                require(self.host.now < timestamp(attempt['deadline'])
                        and attempt['attempt_id'] in self.host.monotonic_starts
                        and time.monotonic() - self.host.monotonic_starts[attempt['attempt_id']] < 30, 'LEASE_LOST')
                self.host.validate(binding)
                return binding
            finally:
                db.close()

    def rule(self, providers, case, node, binding):
        ref = json.loads(node['input_ref'])
        actor = self.host.actor('worker')
        decision = providers.rule(case['case_id'], node['node_run_id'], ref, binding['object_refs'], actor)
        require(all(decision[k] == v for k, v in {
            'provider_ref': providers.node['rule_provider_ref'], 'rule_ref': providers.node['rule_ref'],
            'input_snapshot_ref': ref, 'input_digest': ref['digest'], 'case_id': case['case_id'],
            'node_run_id': node['node_run_id'], 'actor_ref': actor,
            'authorization_revision': self.host.state['authorization_revision']}.items()), 'CONTRACT_INVALID')
        require(self.host.now < timestamp(decision['valid_until']), 'INPUT_STALE')
        codes = {'DENY': 'RULE_DENIED', 'NEEDS_INPUT': 'CAPABILITY_UNSUPPORTED', 'UNAVAILABLE': 'DEPENDENCY_UNAVAILABLE'}
        require(decision['decision'] == 'ALLOW', codes.get(decision['decision'], 'CONTRACT_INVALID'))
        return decision

    def node_command(self, operation, request, role):
        p = request['payload']
        with self.host.lock():
            self.host.authorize(operation, role)
            db = self.host.store.connect(readonly=True)
            try:
                case, node, binding, attempt = self.case_records(db, p['case_id'])
                if operation == 'claim':
                    shape('Id', p['instance_id'])
                    semantic = {**p, 'binding_digest': digest(binding), 'node_run_id': node['node_run_id'], 'worker_session_id': self.host.session}
                    target = p['case_id']
                else:
                    for field in ('node_run_id', 'attempt_id', 'lease_token'):
                        shape('Id', p[field])
                    shape('EvidenceRef', p['input_snapshot_ref'])
                    shape('EvidenceRef', p['output_ref'])
                    require(type(p['evidence_refs']) is list, 'SCHEMA_INVALID')
                    for ref in p['evidence_refs']:
                        shape('EvidenceRef', ref)
                    semantic = {k: v for k, v in p.items() if k != 'lease_token'}
                    semantic['binding_digest'] = digest(binding)
                    target = p['node_run_id']
                slot, hashed = self.identity(operation, request, target, semantic)
                replay = self.replay(db, slot, hashed, request)
                if replay:
                    return replay
            finally:
                db.close()
            if operation == 'claim':
                require(case['status'] != 'SUCCEEDED', 'ALREADY_TERMINAL')
                if attempt:
                    raise ContractError('LEASE_LOST' if self.host.now >= timestamp(attempt['deadline']) else 'IN_PROGRESS')
                require(p['instance_id'] == self.host.state['identity']['instance_id'], 'HOST_BINDING_MISMATCH')
                require(case['status'] == 'QUEUED' and node['status'] == 'READY', 'INVALID_STATE')
            else:
                require(case['status'] != 'SUCCEEDED', 'INVALID_STATE')
                require(attempt is not None and case['status'] == node['status'] == 'RUNNING', 'LEASE_LOST')
                require(p['node_run_id'] == node['node_run_id'] and p['attempt_id'] == attempt['attempt_id']
                        and p['lease_token'] == attempt['lease_token'] and attempt['owner'] == self.host.session
                        and not attempt['released'] and self.host.now < timestamp(attempt['deadline'])
                        and attempt['attempt_id'] in self.host.monotonic_starts
                        and time.monotonic() - self.host.monotonic_starts[attempt['attempt_id']] < 30, 'LEASE_LOST')
                require(p['outcome'] == 'SUCCEEDED', 'CONTRACT_INVALID')
                require(p['input_snapshot_ref'] == json.loads(node['input_ref']), 'INPUT_STALE')
            self.host.validate(binding)
            providers = self.host.providers(binding['projection']['nodes'][0])
            decision = self.rule(providers, case, node, binding)
            revision = case['revision'] + 1
            if operation == 'claim':
                aid, lease = ident('attempt'), ident('lease')
                deadline = (self.host.now + timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
                self.host.monotonic_starts[aid] = time.monotonic()
                result = {'lease': {'case_id': p['case_id'], 'node_run_id': node['node_run_id'], 'attempt_id': aid,
                          'lease_token': lease, 'deadline': deadline, 'input_snapshot_ref': json.loads(node['input_ref']),
                          'executor_ref': providers.node['executor_ref'], 'resources': []}}
                def state(db):
                    db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,0)', (aid, node['node_run_id'], self.host.session, lease, deadline))
                    db.execute("UPDATE node_runs SET status='RUNNING' WHERE node_run_id=?", (node['node_run_id'],))
                    db.execute("UPDATE cases SET status='RUNNING',revision=? WHERE case_id=?", (revision, p['case_id']))
                def ready(db):
                    db.execute('UPDATE ready_nodes SET claimed=1 WHERE node_run_id=?', (node['node_run_id'],))
                kinds = ('NODE_LEASED', 'NODE_STARTED')
            else:
                entry = self.host.output_entry(p['output_ref'])
                output, validation = providers.output(p['output_ref'], entry, p['input_snapshot_ref'], binding['object_refs'])
                require(p['evidence_refs'] == [p['output_ref']], 'CONTRACT_INVALID')
                require(validation['valid'] is True and validation['input_snapshot_ref'] == p['input_snapshot_ref']
                        and validation['output_ref'] == p['output_ref'] and validation['validator_ref'] == providers.node['validator_ref']
                        and validation['contract_ref'] == providers.node['output_contract_ref'], 'CONTRACT_INVALID')
                require(self.host.now < timestamp(attempt['deadline'])
                        and time.monotonic() - self.host.monotonic_starts[attempt['attempt_id']] < 30, 'LEASE_LOST')
                aid = attempt['attempt_id']
                result = {'case_id': p['case_id'], 'node_run_id': node['node_run_id'], 'accepted': True,
                          'revision': revision, 'status': 'SUCCEEDED', 'event_refs': []}
                def state(db):
                    self.evidence(db, p['output_ref'], output)
                    db.execute("UPDATE node_runs SET status='SUCCEEDED',output_ref=? WHERE node_run_id=?", (encode(p['output_ref']), node['node_run_id']))
                    # Aggregation belongs to core; the worker supplied only a node outcome.
                    remaining = db.execute("SELECT count(*) FROM node_runs WHERE case_id=? AND status!='SUCCEEDED'", (p['case_id'],)).fetchone()[0]
                    require(remaining == 0 and providers.node['completion'] == 'OUTPUT_VALIDATED', 'INVALID_STATE')
                    db.execute("UPDATE cases SET status='SUCCEEDED',revision=? WHERE case_id=?", (revision, p['case_id']))
                    db.execute('UPDATE attempts SET released=1 WHERE attempt_id=?', (aid,))
                def ready(db):
                    db.execute('DELETE FROM ready_nodes WHERE node_run_id=?', (node['node_run_id'],))
                kinds = ('NODE_SUCCEEDED', 'CASE_SUCCEEDED')
            events = [self.event(t, role, request, p['case_id'], revision, node['node_run_id'], aid, case['binding_ref'],
                                 {'rule_decision': decision}) for t in kinds]
            if operation == 'submit':
                result['event_refs'] = [e['event_id'] for e in events]
            return self.commit(operation, request, slot, hashed, result, revision, events, state, ready)

    def query(self, operation, case_id, barrier=None, role='initiator'):
        require(operation in {'snapshot', 'events'}, 'CAPABILITY_UNSUPPORTED')
        with self.host.lock():
            self.host.authorize(operation, role)
            auth_revision = self.host.state['authorization_revision']
            db = self.host.store.connect(readonly=True)
            db.execute('BEGIN')
            try:
                case, node, binding, attempt = self.case_records(db, case_id)
            except BaseException:
                db.close()
                raise
        try:
            if barrier:
                barrier()
            watermark = db.execute('SELECT COALESCE(MAX(sequence),0) FROM events').fetchone()[0]
            count = db.execute('SELECT count(*) FROM events WHERE case_id=? AND sequence<=?', (case_id, watermark)).fetchone()[0]
            require(count <= 100, 'CAPABILITY_UNSUPPORTED')
            items = [json.loads(r[0]) for r in db.execute('SELECT body FROM events WHERE case_id=? AND sequence<=? ORDER BY sequence', (case_id, watermark))]
            blockers = ['LEASE_LOST'] if attempt and not attempt['released'] and self.host.now >= timestamp(attempt['deadline']) else []
            visible = {k: v for k, v in node.items() if k not in {'input_ref', 'output_ref'}}
            visible.update(input_ref=json.loads(node['input_ref']), output_ref=json.loads(node['output_ref']) if node['output_ref'] else None)
            if attempt:
                visible['attempt'] = {k: v for k, v in attempt.items() if k != 'lease_token'}
            if visible['output_ref']:
                visible['output'] = json.loads(Store.one(db, 'evidence', 'evidence_id', visible['output_ref']['evidence_id'])['content'])
            result = ({'items': items, 'next_cursor': None, 'has_more': False} if operation == 'events' else
                      {**case, 'binding': binding, 'nodes': [visible], 'blockers': blockers})
            result.update(watermark=watermark, observed_at=self.host.state['now'])
            with self.host.lock():
                self.host.authorize(operation, role)
                require(self.host.state['authorization_revision'] == auth_revision, 'UNAUTHORIZED')
            return {'result': result}
        finally:
            db.rollback()
            db.close()
