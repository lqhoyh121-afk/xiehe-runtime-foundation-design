"""One claim, pure execution, one submission. No automatic recovery. Laiqh."""
from copy import deepcopy
import json
import os
import time

from .contract_adapter import require, shape, load_json
from .service import Service
from .synthetic_host import ident, save
from .synthetic_providers import Providers


class Worker:
    def __init__(self, host):
        self.host = host
        self.service = Service(host)

    def claim(self, case_id):
        shape('Id', case_id)
        with self.host.lock():
            self.host.authorize('claim', 'worker')
            instance = self.host.state['identity']['instance_id']
        request = {'request_id': ident('req'), 'idempotency_key': ident('claim'),
                   'payload': {'instance_id': instance, 'case_id': case_id}}
        intent_path = self.host.path / 'host' / ('intent-' + case_id + '.json')
        with self.host.lock():
            if not intent_path.exists():
                save(intent_path, {'claim': request})
        claimed = self.service.execute('claim', request, 'worker')
        require(not claimed['replayed'], 'IN_PROGRESS')
        with self.host.lock():
            save(intent_path, {'claim': request, 'claimed': claimed})
        return request, claimed

    def prepare(self, case_id, expire_before_execution=False):
        request, claimed = self.claim(case_id)
        lease = claimed['result']['lease']
        if expire_before_execution:
            self.host.control('advance-past-deadline')
        binding = self.service.check_execution(lease)
        # Pure computation runs outside both the SQLite transaction and host lock.
        output = Providers(self.host, binding['projection']['nodes'][0]).execute(lease['input_snapshot_ref'], binding['object_refs'])
        with self.host.lock():
            reference = self.host.stage_output(output, lease)
            payload = {k: deepcopy(lease[k]) for k in ('case_id', 'node_run_id', 'attempt_id', 'lease_token', 'input_snapshot_ref')}
            payload.update(outcome='SUCCEEDED', output_ref=reference, evidence_refs=[reference])
            submit = {'request_id': ident('req'), 'idempotency_key': 'submit-' + lease['attempt_id'], 'payload': payload}
            save(self.host.path / 'host' / ('intent-' + case_id + '.json'), {'claim': request, 'claimed': claimed, 'submit': submit})
        return claimed, submit

    def run(self, case_id):
        _, submit = self.prepare(case_id)
        return self.service.execute('submit', submit, 'worker')

    def test(self, case_id, scenario):
        """Finite operator fixtures, not a public arbitrary claim/submit API."""
        shape('Id', case_id)
        faults = {'submit-fault-' + p for p in ('after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response')}
        controls = {'mutate-input', 'tamper-input', 'expire-input', 'revoke-provider', 'revoke-grant',
                    'deny-rule', 'needs-input', 'rule-unavailable', 'output-mismatch'}
        permitted = {'submit-replay', 'submit-new-key', 'claim-crash', 'prepare-crash', 'claim-replay',
                     'submit-bad-owner', 'submit-bad-attempt', 'submit-bad-lease', 'submit-expired', 'submit-elapsed', 'execute-expired'}
        require(scenario in permitted | faults | {'submit-' + x for x in controls}, 'CAPABILITY_UNSUPPORTED')
        if scenario in {'submit-replay', 'submit-new-key'}:
            with self.host.lock():
                self.host.authorize('submit', 'worker')
                intent = load_json(self.host.path / 'host' / ('intent-' + case_id + '.json'))
            request = intent['submit']
            request['request_id'] = ident('req')
            if scenario == 'submit-new-key':
                request['idempotency_key'] = ident('new-submit')
            return self.service.execute('submit', request, 'worker')
        if scenario == 'claim-crash':
            self.claim(case_id)
            os._exit(86)
        if scenario == 'submit-output-mismatch':
            self.host.control('output-mismatch')
        claimed, submit = self.prepare(case_id, expire_before_execution=scenario == 'execute-expired')
        if scenario == 'prepare-crash':
            os._exit(86)
        if scenario == 'claim-replay':
            intent = load_json(self.host.path / 'host' / ('intent-' + case_id + '.json'))
            replay = self.service.execute('claim', intent['claim'], 'worker')
            require(replay['replayed'] and replay['result'] == claimed['result'])
            return replay
        if scenario.startswith('submit-fault-'):
            self.host.control('fault-submit-' + scenario[len('submit-fault-'):])
        elif scenario == 'submit-bad-owner':
            self.host.session = ident('different-owner')
        elif scenario in {'submit-bad-attempt', 'submit-bad-lease'}:
            submit['payload']['attempt_id' if scenario == 'submit-bad-attempt' else 'lease_token'] = ident('wrong')
        elif scenario == 'submit-expired':
            self.host.control('advance-past-deadline')
        elif scenario == 'submit-elapsed':
            time.sleep(30.05)  # Deliberately real elapsed guard, not a clock mock.
        elif scenario[7:] in controls and scenario != 'submit-output-mismatch':
            self.host.control(scenario[7:])
        return self.service.execute('submit', submit, 'worker')
