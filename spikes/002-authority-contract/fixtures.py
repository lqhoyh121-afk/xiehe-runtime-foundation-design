"""SYNTHETIC fixtures only. Hash construction is independent of validator.

This adapter is not an authorization source. It models a host-controlled read
seam to test hostile REQUESTS, not cryptographic or production trust.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

from validator import TrustedContext, AuthorityUnavailable

SCOPE = {'tenant': 'synthetic-tenant', 'project': 'synthetic-project'}
START = '2030-01-01T00:00:00Z'
END = '2030-01-02T00:00:00Z'


def fixture_digest(x):
    raw = json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return {'algorithm': 'sha256', 'canonicalization': 'json-sort-utf8-int-v1', 'value': hashlib.sha256(raw).hexdigest()}


def fixture_key(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class SyntheticAuthority:
    """TEST ONLY mutable store. Never read from the caller's request file."""
    def __init__(self):
        self.records = {}
        self.views = {}
        self.unavailable = False

    def lookup(self, kind, reference, context):
        if self.unavailable:
            raise AuthorityUnavailable()
        return deepcopy(self.records.get((kind, fixture_key(reference))))

    def current(self, kind, reference, context):
        if self.unavailable:
            raise AuthorityUnavailable()
        return deepcopy(self.views.get((kind, reference)))

    def put(self, kind, reference, value):
        self.records[(kind, fixture_key(reference))] = deepcopy(value)


def publish(a, kind, ident, content, dependencies=()):
    reference = {'kind': kind, 'namespace': 'synthetic', 'id': ident, 'version': '1.0.0', 'digest': fixture_digest(content)}
    record = {'ref': reference, 'content': deepcopy(content), 'dependencies': deepcopy(list(dependencies)), 'scope': deepcopy(SCOPE), 'status': 'ACTIVE', 'valid_from': START, 'expires_at': END}
    a.put('provider' if kind == 'provider' else 'definition', reference, record)
    return reference


def republish_projection(f):
    body = {k: deepcopy(v) for k, v in f.projection.items() if k != 'definition_ref'}
    f.projection['definition_ref'] = publish(f.authority, 'runtime', 'runtime-demo', body, f.projection['dependencies'])


def fixture():
    a = SyntheticAuthority()
    business = publish(a, 'business', 'business-demo', {'test_only': True})
    model = publish(a, 'model', 'model-demo', {'test_only': True, 'shape': 'opaque-model'})
    rule = publish(a, 'rule', 'rule-demo', {'test_only': True, 'semantics': 'not-executed'})
    providers = {}
    for role in ['NodeExecutor', 'ContractValidator', 'DataProvider', 'RuleProvider']:
        # Descriptor content excludes its own ref to avoid a digest cycle.
        body = {'role': role, 'contract_version': '0.1-draft', 'execution_kind': 'CODE' if role == 'NodeExecutor' else None, 'capabilities': ['synthetic-capability']}
        providers[role] = publish(a, 'provider', role, body)
    def node(ident, parents):
        return {'node_id': ident, 'depends_on': parents, 'execution_kind': 'CODE', 'executor_ref': providers['NodeExecutor'], 'input_contract_ref': model, 'output_contract_ref': model, 'data_provider_ref': providers['DataProvider'], 'validator_ref': providers['ContractValidator'], 'rule_ref': rule, 'rule_provider_ref': providers['RuleProvider'], 'wait_spec_ref': None, 'verification_spec_ref': None, 'readback_provider_ref': None, 'action_adapter_ref': None, 'resources': [], 'timeout_seconds': 30, 'retry_policy': {'max_attempts': 2, 'backoff_seconds': 1}, 'completion': 'OUTPUT_VALIDATED'}
    p = {'contract_version': '0.1-draft', 'status': 'DRAFT', 'scope': deepcopy(SCOPE), 'business_ref': business, 'dependencies': [business, model, rule, *providers.values()], 'provider_bindings': list(providers.values()), 'nodes': [node('read', []), node('evaluate', ['read'])], 'terminal_nodes': ['evaluate']}
    f = SimpleNamespace(authority=a, projection=p, providers=providers, model=model, rule=rule, context=TrustedContext(deepcopy(SCOPE), 'deployment-a', datetime(2030, 1, 1, 12, tzinfo=timezone.utc), 4, True))
    republish_projection(f)
    return f
