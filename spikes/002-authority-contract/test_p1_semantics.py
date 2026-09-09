"""R1/R2 DRAFT public-seam regressions. Laiqh; synthetic data only.

Running this file with a scenario is an L2 TEST PROBE, not a projection CLI.
The production cli.py still handles migration requests only.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fixtures import fixture, fixture_digest, publish, republish_projection
from validator import ContractError, SCHEMA, validate_projection

ROOT = Path(__file__).resolve().parent
VALID = {'verdict': 'VALIDATED_LOCAL_ONLY', 'contract_status': 'DRAFT',
         'production_authorized': False}
# Expected kinds come from the approved task, not the implementation's slot rules.
SLOT_KINDS = {
    'business_ref': 'business', 'definition_ref': 'runtime',
    'input_contract_ref': 'model', 'output_contract_ref': 'model',
    'rule_ref': 'rule', 'wait_spec_ref': 'wait',
    'verification_spec_ref': 'verification',
}
KINDS = tuple(SCHEMA['$defs']['DefinitionRef']['properties']['kind']['enum'])


def add_definition(f, kind, ident):
    ref = publish(f.authority, kind, ident, {'test_only': True, 'purpose': ident})
    f.projection['dependencies'].append(ref)
    return ref


def add_provider(f, role, execution_kind=None):
    body = {'role': role, 'contract_version': '0.1-draft',
            'execution_kind': execution_kind, 'capabilities': ['synthetic-capability']}
    ref = publish(f.authority, 'provider', role + '-' + str(execution_kind), body)
    f.projection['dependencies'].append(ref)
    f.projection['provider_bindings'].append(ref)
    return ref


def readback_fixture(case):
    f = fixture()
    node = f.projection['nodes'][0]
    node['completion'] = 'READBACK_VERIFIED'
    if case not in ('missing-both', 'missing-verification'):
        node['verification_spec_ref'] = add_definition(f, 'verification', 'verification-demo')
    if case not in ('missing-both', 'missing-provider'):
        node['readback_provider_ref'] = add_provider(f, 'ReadbackProvider')
    if case == 'wrong-role':
        node['readback_provider_ref'] = deepcopy(f.providers['DataProvider'])
    elif case == 'unbound':
        f.projection['provider_bindings'].remove(node['readback_provider_ref'])
    elif case == 'wrong-kind':
        node['readback_provider_ref'] = deepcopy(f.model)
    elif case == 'absent-verification':
        del node['verification_spec_ref']
    elif case == 'absent-provider':
        del node['readback_provider_ref']
    elif case == 'absent-both':
        del node['verification_spec_ref'], node['readback_provider_ref']
    republish_projection(f)
    return f


def existing_completion_fixture(completion, execution_kind):
    f = fixture()
    node = f.projection['nodes'][0]
    node['completion'] = completion
    if execution_kind != 'CODE':
        node['execution_kind'] = execution_kind
        node['executor_ref'] = add_provider(f, 'NodeExecutor', execution_kind)
    republish_projection(f)
    return f


def slot_fixture(field, kind):
    f = fixture()
    p = f.projection
    # Publishing the wrong-kind root must retain a genuine matching body/digest.
    if field == 'definition_ref':
        if kind == 'absent':
            del p[field]
        elif kind == 'null':
            p[field] = None
        else:
            body = {k: deepcopy(v) for k, v in p.items() if k != 'definition_ref'}
            p[field] = publish(f.authority, kind, 'slot-root', body, p['dependencies'])
        return f
    target = p if field == 'business_ref' else p['nodes'][0]
    if kind == 'absent':
        del target[field]
    elif kind == 'null':
        target[field] = None
    elif kind == 'provider':
        target[field] = deepcopy(f.providers['DataProvider'])
    elif field == 'rule_ref' and kind == 'model':
        # The exact R2 repro: an existing genuine model in the rule slot.
        target[field] = deepcopy(f.model)
    else:
        target[field] = add_definition(f, kind, 'slot-' + field + '-' + kind)
    republish_projection(f)
    return f


def heterogeneous_fixture():
    f = fixture()
    # Existing dependencies already contain business/model/rule/provider.
    for kind in ('runtime', 'wait', 'verification'):
        add_definition(f, kind, 'dependency-' + kind)
    republish_projection(f)
    assert {ref['kind'] for ref in f.projection['dependencies']} == set(KINDS)
    return f


def assert_published_and_closed(f):
    """Verify synthetic setup independently of production shape/kind rules."""
    p = f.projection
    refs = [ref for ref in [p.get('definition_ref'), *p['dependencies']] if ref is not None]
    for ref in refs:
        record = f.authority.lookup('provider' if ref['kind'] == 'provider' else 'definition', ref, f.context)
        assert record is not None
        assert record['ref'] == ref
        assert fixture_digest(record['content']) == ref['digest']
        assert record['scope'] == f.context.scope and record['status'] == 'ACTIVE'
        assert all(dep in p['dependencies'] for dep in record['dependencies'])
    if p.get('definition_ref') is not None:
        root = f.authority.lookup('provider' if p['definition_ref']['kind'] == 'provider' else 'definition',
                                 p['definition_ref'], f.context)
        assert root['content'] == {k: v for k, v in p.items() if k != 'definition_ref'}
        assert root['dependencies'] == p['dependencies']
    # Null/absent cases intentionally violate shape, not publication or kind.
    required = [ref for ref in [p.get('business_ref'), *p['provider_bindings']] if ref is not None]
    for node in p['nodes']:
        required.extend(value for field, value in node.items()
                        if field.endswith('_ref') and value is not None)
    assert all(ref in p['dependencies'] for ref in required)


def outcome(f):
    try:
        return validate_projection(f.projection, f.authority, f.context)
    except ContractError as exc:
        return {'verdict': 'REJECTED', 'code': exc.code,
                'contract_status': 'DRAFT', 'production_authorized': False}


def repeated_outcome(f):
    before = deepcopy((f.projection, f.authority.records, f.authority.views))
    first = outcome(f)
    assert outcome(f) == first
    assert (f.projection, f.authority.records, f.authority.views) == before
    return first


def build_case(scenario):
    parts = scenario.split(':')
    if parts[0] == 'readback':
        return readback_fixture(parts[1])
    if parts[0] == 'completion':
        return existing_completion_fixture(parts[1], parts[2])
    if parts[0] == 'slot':
        return slot_fixture(parts[1], parts[2])
    if parts[0] == 'heterogeneous':
        return heterogeneous_fixture()
    raise ValueError('Unknown synthetic test scenario')


def check_case(scenario, code, entry, tmp_path):
    f = build_case(scenario)
    assert_published_and_closed(f)
    expected = VALID if code is None else {
        'verdict': 'REJECTED', 'code': code, 'contract_status': 'DRAFT',
        'production_authorized': False,
    }
    if entry == 'public':
        assert repeated_outcome(f) == expected
    else:
        result = subprocess.run(
            [sys.executable, '-B', str(Path(__file__).resolve()), scenario], cwd=ROOT,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, encoding='utf-8', timeout=20,
        )
        # Only pytest's disposable path receives process evidence, not source files.
        (tmp_path / 'probe.json').write_text(json.dumps({
            'scenario': scenario, 'returncode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr,
        }), encoding='utf-8')
        assert result.stderr == ''
        assert result.returncode == (0 if code is None else 2), result.stdout
        assert json.loads(result.stdout) == expected


@pytest.mark.parametrize('entry', ['public', 'process'])
@pytest.mark.parametrize('case,code', [
    ('missing-both', 'SCHEMA_INVALID'),
    ('missing-verification', 'SCHEMA_INVALID'),
    ('missing-provider', 'SCHEMA_INVALID'),
    ('complete', None),
    ('wrong-role', 'PROVIDER_ROLE_MISMATCH'),
    ('unbound', 'PROVIDER_NOT_BOUND'),
    ('wrong-kind', 'PROVIDER_KIND_MISMATCH'),
    ('absent-verification', 'SCHEMA_INVALID'),
    ('absent-provider', 'SCHEMA_INVALID'),
    ('absent-both', 'SCHEMA_INVALID'),
])
def test_readback_requirements_and_existing_provider_errors(case, code, entry, tmp_path):
    check_case('readback:' + case, code, entry, tmp_path)


@pytest.mark.parametrize('entry', ['public', 'process'])
@pytest.mark.parametrize('completion', ['OUTPUT_VALIDATED', 'HUMAN_CONFIRMED'])
@pytest.mark.parametrize('execution_kind', ['CODE', 'AI', 'HUMAN'])
def test_existing_completion_does_not_invent_human_or_action_requirements(
        completion, execution_kind, entry, tmp_path):
    check_case('completion:' + completion + ':' + execution_kind, None, entry, tmp_path)


@pytest.mark.parametrize('entry', ['public', 'process'])
@pytest.mark.parametrize('field,kind', [
    (field, kind) for field, expected in SLOT_KINDS.items()
    for kind in KINDS if kind != expected
])
def test_slot_rejects_every_other_real_published_kind(field, kind, entry, tmp_path):
    check_case('slot:' + field + ':' + kind, 'SCHEMA_INVALID', entry, tmp_path)


@pytest.mark.parametrize('entry', ['public', 'process'])
@pytest.mark.parametrize('field,kind', list(SLOT_KINDS.items()))
def test_slot_accepts_its_correct_published_kind(field, kind, entry, tmp_path):
    check_case('slot:' + field + ':' + kind, None, entry, tmp_path)


@pytest.mark.parametrize('entry', ['public', 'process'])
@pytest.mark.parametrize('field', list(SLOT_KINDS))
@pytest.mark.parametrize('value', ['null', 'absent'])
def test_slot_preserves_required_and_nullable_fields(field, value, entry, tmp_path):
    nullable = value == 'null' and field in ('wait_spec_ref', 'verification_spec_ref')
    check_case('slot:' + field + ':' + value, None if nullable else 'SCHEMA_INVALID', entry, tmp_path)


@pytest.mark.parametrize('entry', ['public', 'process'])
def test_heterogeneous_dependencies_keep_the_general_kind_enum(entry, tmp_path):
    check_case('heterogeneous', None, entry, tmp_path)


if __name__ == '__main__':
    synthetic = build_case(sys.argv[1])
    assert_published_and_closed(synthetic)
    result = repeated_outcome(synthetic)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2 if result['verdict'] == 'REJECTED' else 0)
