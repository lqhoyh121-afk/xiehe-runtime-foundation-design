"""Normalize Data/Rule/Validator/Executor adapters. TEST ONLY. Laiqh."""
from copy import deepcopy
import os

from .contract_adapter import digest, require, resolve
from .package_install import IMPLEMENTATION, binding_snapshot, component_from_bytes, verify_installation
from .synthetic_host import ident
from .synthetic_providers import Providers


class PackageProviders(Providers):
    """Only the domain-neutral evidence/data/model methods are inherited."""
    def record(self, field):
        require(self.node == self.host.state['projection']['nodes'][0], 'PROVIDER_NOT_BOUND')
        super().record(field)

    def rule(self, case_id, node_run_id, reference, object_refs, actor):
        self.record('rule_provider_ref')
        body = resolve(self.node['rule_ref'], self.host.reader, self.host.context)['content']
        require(body == {'test_only': True, 'predicate': 'text contains at least one character other than U+0020'},
                'CAPABILITY_UNSUPPORTED')
        content = self.data(reference, object_refs)
        decision = 'ALLOW' if any(character != '\u0020' for character in content['text']) else 'DENY'
        return {'decision': decision, 'decision_id': ident('decision'), 'provider_ref': self.node['rule_provider_ref'],
                'rule_ref': self.node['rule_ref'], 'input_digest': reference['digest'], 'input_snapshot_ref': reference,
                'case_id': case_id, 'node_run_id': node_run_id, 'actor_ref': actor,
                'authorization_revision': self.host.state['authorization_revision'],
                'valid_until': reference['valid_until'], 'reason_codes': []}

    def execute(self, reference, object_refs):
        content = self.data(reference, object_refs)
        record, files, projection = verify_installation(self.host.path)
        require(self.node == projection['nodes'][0], 'PROVIDER_NOT_BOUND')
        require(binding_snapshot(record) == self.host.state['package_installation'], 'VERSION_CONFLICT')
        component = component_from_bytes(files[IMPLEMENTATION], record)
        self.record('executor_ref')
        output = component.invoke(content)
        self.validate('output_contract_ref', output)
        self.host.pending_invocation = {'invoked': True, 'provider_ref': deepcopy(self.node['executor_ref']),
            'installation_id': record['installation_id'], 'record_digest': record['record_digest'],
            'implementation_sha256': component.source_sha256, 'adapter': deepcopy(record['adapter']),
            'input_snapshot_ref': deepcopy(reference), 'input_digest': digest(content), 'output_digest': digest(output),
            'pid': os.getpid(), 'session': self.host.session}
        return output

    def output(self, reference, entry, input_ref, object_refs):
        require(reference['source_ref'] == self.host.state['output_source'])
        content = self.evidence(reference, entry)
        result = self.validate('output_contract_ref', content)
        original = self.data(input_ref, object_refs)
        # Independent oracle: boundary scanning, not the author's function/strip call.
        text = original['text']
        left, right = 0, len(text)
        while left < right and ord(text[left]) == 32:
            left += 1
        while right > left and ord(text[right - 1]) == 32:
            right -= 1
        require(content['normalized'] == text[left:right])
        self.host.verify_execution(reference, input_ref, content)
        result.update(input_snapshot_ref=input_ref, output_ref=reference)
        return content, result
