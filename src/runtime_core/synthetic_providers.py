"""Fixed synthetic providers; business-specific fields stay here. Laiqh."""
from copy import deepcopy
import uuid
from jsonschema import Draft202012Validator

from .contract_adapter import digest, require, resolve, shape, timestamp


def install_projection(authority, scope, publish):
    """All domain-specific fixture models, fields and code identity live here."""
    business = publish(authority, 'business', 'm1-business', {'synthetic_only': True})
    inp = publish(authority, 'model', 'm1-input', {'type': 'object', 'properties': {'message': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['message'], 'additionalProperties': False})
    out = publish(authority, 'model', 'm1-output', {'type': 'object', 'properties': {'echo': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['echo'], 'additionalProperties': False})
    rule = publish(authority, 'rule', 'm1-rule', {'rule': 'synthetic-prefix-and-exact-echo-v1'})
    providers = {role: publish(authority, 'provider', 'm1-' + role, {'role': role, 'contract_version': '0.1-draft',
                 'execution_kind': 'CODE' if role == 'NodeExecutor' else None, 'capabilities': ['synthetic-echo-v1']})
                 for role in ('NodeExecutor', 'ContractValidator', 'DataProvider', 'RuleProvider')}
    node = {'node_id': 'echo', 'depends_on': [], 'execution_kind': 'CODE', 'executor_ref': providers['NodeExecutor'],
            'input_contract_ref': inp, 'output_contract_ref': out, 'data_provider_ref': providers['DataProvider'],
            'validator_ref': providers['ContractValidator'], 'rule_ref': rule, 'rule_provider_ref': providers['RuleProvider'],
            'wait_spec_ref': None, 'verification_spec_ref': None, 'readback_provider_ref': None, 'action_adapter_ref': None,
            'resources': [], 'timeout_seconds': 30, 'retry_policy': {'max_attempts': 1, 'backoff_seconds': 0}, 'completion': 'OUTPUT_VALIDATED'}
    projection = {'contract_version': '0.1-draft', 'status': 'DRAFT', 'scope': deepcopy(scope), 'business_ref': business,
                  'dependencies': [business, inp, out, rule, *providers.values()], 'provider_bindings': list(providers.values()),
                  'nodes': [node], 'terminal_nodes': ['echo']}
    return projection, {'message': 'SYNTHETIC RC0'}


def changed_input_content(tampered=False):
    return {'message': 'SYNTHETIC TAMPERED' if tampered else 'SYNTHETIC NEW VERSION'}


class Providers:
    def __init__(self, host, node):
        self.host, self.node = host, node

    def record(self, field):
        ref = self.node[field]
        require(ref in self.host.state['installed'], 'CAPABILITY_UNSUPPORTED')
        resolve(ref, self.host.reader, self.host.context)
        self.host.observe(field)

    def evidence(self, reference, entry):
        shape('EvidenceRef', reference)
        require(entry is not None and entry['ref'] == reference, 'INPUT_STALE')
        require(reference['scope'] == self.host.state['scope'], 'SCOPE_MISMATCH')
        require(reference['digest'] == digest(entry['content']), 'VERSION_DIGEST_MISMATCH')
        require(timestamp(reference['observed_at']) <= self.host.now < timestamp(reference['valid_until']), 'INPUT_STALE')
        require(reference['retention_policy_ref'] == 'm1-sandbox-lifetime', 'CONTRACT_INVALID')
        return deepcopy(entry['content'])

    def data(self, reference, object_refs):
        self.record('data_provider_ref')
        require(object_refs == [self.host.state['source']], 'CONTRACT_INVALID')
        require(reference == self.host.state['current_input'], 'INPUT_STALE')
        require(reference['source_ref'] == self.host.state['source'], 'CONTRACT_INVALID')
        content = self.evidence(reference, self.host.state['inputs'].get(reference['evidence_id']))
        self.validate('input_contract_ref', content)
        return content

    def validate(self, contract_field, content):
        self.record('validator_ref')
        model = resolve(self.node[contract_field], self.host.reader, self.host.context)['content']
        require(not list(Draft202012Validator(model).iter_errors(content)), 'CONTRACT_INVALID')
        return {'valid': True, 'reason_codes': [], 'contract_ref': self.node[contract_field],
                'validator_ref': self.node['validator_ref']}

    def rule(self, case_id, node_run_id, reference, object_refs, actor):
        self.record('rule_provider_ref')
        body = resolve(self.node['rule_ref'], self.host.reader, self.host.context)['content']
        require(body == {'rule': 'synthetic-prefix-and-exact-echo-v1'}, 'CAPABILITY_UNSUPPORTED')
        content = self.data(reference, object_refs)
        mode = self.host.state['rule_mode']
        decision = mode if mode != 'ALLOW' else 'ALLOW' if content['message'].startswith('SYNTHETIC') else 'DENY'
        return {'decision': decision, 'decision_id': 'decision-' + uuid.uuid4().hex,
                'provider_ref': self.node['rule_provider_ref'], 'rule_ref': self.node['rule_ref'],
                'input_digest': reference['digest'], 'input_snapshot_ref': reference, 'case_id': case_id,
                'node_run_id': node_run_id, 'actor_ref': actor,
                'authorization_revision': self.host.state['authorization_revision'],
                'valid_until': reference['valid_until'], 'reason_codes': []}

    def execute(self, reference, object_refs):
        content = self.data(reference, object_refs)
        self.record('executor_ref')
        return {'echo': 'SYNTHETIC WRONG OUTPUT' if self.host.state['output_mode'] == 'mismatch' else content['message']}

    def output(self, reference, entry, input_ref, object_refs):
        require(reference['source_ref'] == self.host.state['output_source'], 'CONTRACT_INVALID')
        content = self.evidence(reference, entry)
        result = self.validate('output_contract_ref', content)
        original = self.data(input_ref, object_refs)
        require(content['echo'] == original['message'], 'CONTRACT_INVALID')
        result.update(input_snapshot_ref=input_ref, output_ref=reference)
        return content, result
