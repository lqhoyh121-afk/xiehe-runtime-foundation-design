"""RC0 F03/F04/F05/F13/F14/F18 contract gates. Laiqh."""
from pathlib import Path
import runpy
import pytest
import sys
import json
import hashlib
from copy import deepcopy

Harness = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))['Harness']


@pytest.mark.parametrize('scenario,expected,exit_code', [
    ('unknown-provider', 'UNKNOWN_PROVIDER', 2),
    ('missing-implementation', 'CAPABILITY_UNSUPPORTED', 2),
    ('fake-admission', 'DEPENDENCY_UNAVAILABLE', 3),
    ('mutate-definition', 'VERSION_DIGEST_MISMATCH', 2),
    ('revoke-provider', 'REVOKED', 2),
    ('revoke-grant', 'REVOKED', 2),
    ('authority-gap', 'AUTHORITY_SYNC_GAP', 2),
    ('authority-stale', 'AUTHORITY_VIEW_STALE', 2),
    ('authority-rollback', 'REVOCATION_ROLLBACK', 2),
])
def test_current_contract_failure_survives_restart(scenario, expected, exit_code):
    h = Harness()
    try:
        h.setup()
        h.call('host-control', '--scenario', scenario)
        before = h.rows()
        for _ in range(2):
            result = h.request('create', h.create_payload, code=exit_code)
            assert result['code'] == expected
        assert h.rows() == before
    finally:
        h.cleanup()


@pytest.mark.parametrize('variant,expected', [
    ('ai', 'CAPABILITY_UNSUPPORTED'), ('human', 'CAPABILITY_UNSUPPORTED'),
    ('multi-node', 'CAPABILITY_UNSUPPORTED'), ('wait', 'CAPABILITY_UNSUPPORTED'),
    ('readback', 'CAPABILITY_UNSUPPORTED'), ('action', 'CAPABILITY_UNSUPPORTED'),
    ('resources', 'CAPABILITY_UNSUPPORTED'), ('retry', 'CAPABILITY_UNSUPPORTED'),
    ('timeout', 'CAPABILITY_UNSUPPORTED'), ('wrong-role', 'PROVIDER_ROLE_MISMATCH'),
    ('condition', 'SCHEMA_INVALID'), ('cycle', 'NODE_CYCLE'),
])
def test_published_unsupported_or_invalid_definitions(variant, expected):
    h = Harness()
    try:
        h.init()
        h.call('host-control', '--scenario', 'publish-' + variant)
        result = h.call('register', '--request', str(h.sandbox / 'requests/register-variant.json'), code=2)
        assert result['code'] == expected
        assert not h.rows()['registrations']
    finally:
        h.cleanup()


def test_independent_request_digest_vectors():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / 'src'))
    from runtime_core.contract_adapter import request_digest
    scope = {'tenant': 'SYNTHETIC', 'project': 'TEST', 'environment': 'local'}
    payload = {'input_ref': {'digest': {'algorithm': 'sha256', 'value': 'a' * 64}}, 'objects': ['a', 'b']}
    def independent(semantic):
        preimage = {'request_digest_version': 'rc0-m1-request-v1', 'operation': 'create_case', 'scope': scope,
                    'namespace': 'test-ns', 'target': 'registration-test', 'semantic_input': semantic}
        raw = json.dumps(preimage, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()
    def actual(semantic):
        return request_digest('create_case', scope, 'test-ns', 'registration-test', semantic)['value']
    assert actual(payload) == independent(payload)
    assert actual(dict(reversed(list(payload.items())))) == actual(payload)
    requests = [{'request_id': name, 'payload': payload} for name in ('first', 'second')]
    assert actual(requests[0]['payload']) == actual(requests[1]['payload'])
    changed = deepcopy(payload)
    changed['input_ref']['digest']['value'] = 'b' * 64
    assert actual(changed) == independent(changed) != actual(payload)
    changed = deepcopy(payload)
    changed['objects'].reverse()
    assert actual(changed) == independent(changed) != actual(payload)


@pytest.mark.parametrize('body', [
    '{"request_id":"a","request_id":"b"}', '{"n":NaN}', '{"n":1.5}',
    '{"n":9007199254740992}', '{"n":Infinity}', '{"request_id":"\\ud800"}',
    '{}', '[]', '{"approved":true,"auth_context":{}}',
])
def test_strict_json_rejected_without_logical_writes(body):
    h = Harness()
    try:
        h.init()
        request = h.sandbox / 'requests/bad.json'
        request.write_text(body, encoding='utf-8', errors='surrogatepass')
        before = h.rows()
        h.call('register', '--request', str(request), code=2)
        assert h.rows() == before
    finally:
        h.cleanup()


def test_missing_request_is_input_error_not_storage_corruption():
    h = Harness()
    try:
        h.init()
        assert h.call('register', '--request', str(h.sandbox / 'requests/missing.json'), code=2)['code'] == 'INPUT_INVALID'
    finally:
        h.cleanup()


def test_business_field_literals_exist_only_in_synthetic_providers():
    import ast
    root = Path(__file__).resolve().parents[2] / 'src/runtime_core'
    for name in ('service.py', 'store.py', 'worker.py', 'contract_adapter.py', 'synthetic_host.py'):
        tree = ast.parse((root / name).read_text(encoding='utf-8'))
        assert not any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and n.value in {'echo', 'message'} for n in ast.walk(tree)), name


def test_same_business_version_different_digest():
    h = Harness()
    try:
        h.setup()
        before = h.rows()
        h.call('host-control', '--scenario', 'publish-version-conflict')
        result = h.call('register', '--request', str(h.sandbox / 'requests/register-variant.json'), code=2)
        assert result['code'] == 'VERSION_CONFLICT'
        assert h.rows() == before
    finally:
        h.cleanup()
