"""P1 public-seam negatives; SYNTHETIC, no production authority.

Re-publishing a malformed projection avoids accidentally testing only the
outer digest guard. Expected rejection obligations come from SPEC/AC-1.
"""
from copy import deepcopy

import pytest

from fixtures import fixture, fixture_key, publish, republish_projection
from validator import ContractError, validate_projection


def reject(f, code):
    with pytest.raises(ContractError) as exc:
        validate_projection(f.projection, f.authority, f.context)
    assert exc.value.code == code


@pytest.mark.parametrize('target', ['projection', 'dependency', 'provider'])
@pytest.mark.parametrize('mutation', ['version', 'digest', 'namespace', 'content'])
def test_exact_reference_and_content_binding(target, mutation):
    f = fixture()
    reference = (f.projection['definition_ref'] if target == 'projection' else
                 f.providers['NodeExecutor'] if target == 'provider' else f.model)
    lookup_kind = 'provider' if target == 'provider' else 'definition'
    record = f.authority.lookup(lookup_kind, reference, f.context)
    if mutation == 'content':
        record['content']['tampered'] = True
    elif mutation == 'digest':
        record['ref']['digest']['value'] = '0' * 64
    else:
        record['ref'][mutation] = '9.9.9' if mutation == 'version' else 'other-namespace'
    # Simulate a resolver returning a different immutable record for the request.
    f.authority.put(lookup_kind, reference, record)
    reject(f, 'VERSION_DIGEST_MISMATCH')


@pytest.mark.parametrize('case,code', [
    ('unavailable', 'DEPENDENCY_UNAVAILABLE'),
    ('unlisted-node-contract', 'DEPENDENCY_NOT_DECLARED'),
    ('unlisted-transitive', 'DEPENDENCY_NOT_DECLARED'),
    ('root-declarations', 'DEPENDENCY_BINDING_MISMATCH'),
])
def test_dependency_closure_must_be_complete(case, code):
    f = fixture()
    if case == 'unavailable':
        del f.authority.records[('definition', fixture_key(f.model))]
    elif case == 'unlisted-node-contract':
        f.projection['dependencies'].remove(f.model)
        republish_projection(f)
    elif case == 'unlisted-transitive':
        extra = publish(f.authority, 'model', 'nested-model', {'test_only': True})
        record = f.authority.lookup('definition', f.rule, f.context)
        record['dependencies'] = [extra]
        f.authority.put('definition', f.rule, record)
    else:
        reference = f.projection['definition_ref']
        record = f.authority.lookup('definition', reference, f.context)
        record['dependencies'].remove(f.model)
        f.authority.put('definition', reference, record)
    reject(f, code)


def test_unknown_provider_is_rejected():
    f = fixture()
    reference = f.providers['DataProvider']
    del f.authority.records[('provider', fixture_key(reference))]
    reject(f, 'UNKNOWN_PROVIDER')


def test_cross_namespace_reference_cannot_fall_back_to_same_id():
    f = fixture()
    foreign = deepcopy(f.model)
    foreign['namespace'] = 'other-namespace'
    f.projection['dependencies'].append(foreign)
    f.projection['nodes'][0]['input_contract_ref'] = foreign
    republish_projection(f)
    reject(f, 'DEPENDENCY_UNAVAILABLE')


def test_dependency_scope_cannot_cross_tenant_boundary():
    f = fixture()
    record = f.authority.lookup('definition', f.model, f.context)
    record['scope']['tenant'] = 'other-tenant'
    f.authority.put('definition', f.model, record)
    reject(f, 'SCOPE_MISMATCH')


def test_authority_unavailable_fails_closed():
    f = fixture()
    f.authority.unavailable = True
    reject(f, 'AUTHORITY_UNAVAILABLE')


def test_exact_scoped_cross_namespace_closure_is_repeatable_and_read_only():
    # A namespace is part of identity, not a blanket same-namespace policy.
    # The injected authority must supply the exact explicitly declared record.
    f = fixture()
    foreign = deepcopy(f.model)
    foreign['namespace'] = 'other-namespace'
    record = f.authority.lookup('definition', f.model, f.context)
    record['ref'] = foreign
    f.authority.put('definition', foreign, record)
    rule = f.authority.lookup('definition', f.rule, f.context)
    rule['dependencies'] = [foreign]
    f.authority.put('definition', f.rule, rule)
    f.projection['dependencies'].append(foreign)
    republish_projection(f)
    before = deepcopy((f.projection, f.authority.records))
    expected = {'verdict': 'VALIDATED_LOCAL_ONLY', 'contract_status': 'DRAFT',
                'production_authorized': False}
    assert validate_projection(f.projection, f.authority, f.context) == expected
    assert validate_projection(f.projection, f.authority, f.context) == expected
    assert (f.projection, f.authority.records) == before


@pytest.mark.parametrize('case,code', [
    ('cycle', 'NODE_CYCLE'),
    ('self-cycle', 'NODE_CYCLE'),
    ('missing-parent', 'NODE_DEPENDENCY_MISSING'),
    ('duplicate-id', 'DUPLICATE_NODE'),
    ('unknown-terminal', 'TERMINAL_NODES_INVALID'),
    ('non-leaf-terminal', 'TERMINAL_NODES_INVALID'),
    ('omitted-leaf', 'TERMINAL_NODES_INVALID'),
])
def test_invalid_node_graph_is_rejected(case, code):
    f = fixture()
    nodes = f.projection['nodes']
    if case == 'cycle':
        nodes[0]['depends_on'] = ['evaluate']
    elif case == 'self-cycle':
        nodes[0]['depends_on'] = ['read']
    elif case == 'missing-parent':
        nodes[1]['depends_on'] = ['absent']
    elif case == 'duplicate-id':
        duplicate = deepcopy(nodes[0])
        duplicate['timeout_seconds'] = 31  # Not rejected by Schema uniqueItems.
        nodes.append(duplicate)
    elif case == 'unknown-terminal':
        f.projection['terminal_nodes'] = ['absent']
    elif case == 'non-leaf-terminal':
        f.projection['terminal_nodes'] = ['read', 'evaluate']
    else:
        extra = deepcopy(nodes[1])
        extra['node_id'] = 'unlisted-leaf'
        nodes.append(extra)
    republish_projection(f)
    reject(f, code)


@pytest.mark.parametrize('field', [
    'executor_ref', 'data_provider_ref', 'validator_ref', 'rule_provider_ref',
    'readback_provider_ref', 'action_adapter_ref',
])
def test_provider_must_match_the_node_slot_role(field):
    f = fixture()
    role = 'DataProvider' if field == 'executor_ref' else 'NodeExecutor'
    f.projection['nodes'][0][field] = f.providers[role]
    republish_projection(f)
    reject(f, 'PROVIDER_ROLE_MISMATCH')


@pytest.mark.parametrize('case,code', [
    ('wrong-kind', 'PROVIDER_KIND_MISMATCH'),
    ('unbound', 'PROVIDER_NOT_BOUND'),
    ('execution-kind', 'PROVIDER_EXECUTION_KIND_MISMATCH'),
    ('descriptor-version', 'SCHEMA_INVALID'),
])
def test_provider_contract_and_binding_are_required(case, code):
    f = fixture()
    if case == 'wrong-kind':
        f.projection['nodes'][0]['executor_ref'] = f.model
    elif case == 'unbound':
        f.projection['provider_bindings'].remove(f.providers['NodeExecutor'])
    elif case == 'execution-kind':
        f.projection['nodes'][0]['execution_kind'] = 'AI'
    else:
        body = f.authority.lookup('provider', f.providers['NodeExecutor'], f.context)['content']
        body['contract_version'] = 'unknown-contract'
        reference = publish(f.authority, 'provider', 'bad-executor', body)
        f.projection['dependencies'].append(reference)
        f.projection['provider_bindings'].append(reference)
        f.projection['nodes'][0]['executor_ref'] = reference
    republish_projection(f)
    reject(f, code)
