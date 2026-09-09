"""AC-3 public seam tests: expectations from SPEC/design, not validator."""
from copy import deepcopy
import pytest
from migration_fixtures import migration_fixture, install_migration
from migration_checks import check_migration
from validator import ContractError


def test_migration_normal_is_readonly_and_never_authorizes_production():
    f = migration_fixture()
    before = deepcopy((f.migration, f.authority.records, f.authority.views))
    expected = {'verdict': 'VALIDATED_LOCAL_ONLY', 'contract_status': 'DRAFT', 'production_authorized': False, 'synthetic_only': True, 'migration_executed': False}
    assert check_migration(f.migration, f.authority, f.context) == expected
    assert check_migration(f.migration, f.authority, f.context) == expected
    assert (f.migration, f.authority.records, f.authority.views) == before


@pytest.mark.parametrize('record,field,value,code', [
    ('source_grant', 'status', 'ACTIVE', 'SOURCE_GRANT_NOT_REVOKED'),
    ('stop', 'state', 'RUNNING', 'SOURCE_EXECUTOR_NOT_STOPPED'),
    ('stop', 'active_executors', 1, 'SOURCE_EXECUTOR_NOT_STOPPED'),
    ('stop', 'state', 'UNKNOWN', 'MIGRATION_UNKNOWN'),
    ('control', 'state', 'UNKNOWN', 'MIGRATION_UNKNOWN'),
    ('control', 'checkpoint_ref', {'record_kind':'checkpoint','issuer':'synthetic-control','id':'newer-checkpoint'}, 'CHECKPOINT_STALE'),
    ('checkpoint', 'control_revision', 11, 'CHECKPOINT_STALE'),
    ('control', 'target_capabilities', [], 'TARGET_CAPABILITY_MISSING'),
    ('control', 'target_provider_bindings', [], 'TARGET_CAPABILITY_MISSING'),
    ('checkpoint', 'namespace', 'copied-space', 'MIGRATION_BINDING_MISMATCH'),
    ('source_grant', 'namespace', 'copied-space', 'MIGRATION_BINDING_MISMATCH'),
    ('source_grant', 'generation', 8, 'GENERATION_NOT_ADVANCED'),
    ('checkpoint', 'generation', 6, 'MIGRATION_BINDING_MISMATCH'),
    ('stop', 'source_deployment_id', 'wrong-host', 'MIGRATION_BINDING_MISMATCH'),
    ('control', 'revision', 11, 'CONTROL_REVISION_MISMATCH'),
    ('control', 'revocation_revision', 3, 'CONTROL_REVISION_MISMATCH'),
    ('control', 'complete', False, 'AUTHORITY_SYNC_GAP'),
    ('control', 'valid_until', '2030-01-01T12:00:00Z', 'AUTHORITY_VIEW_STALE'),
    ('control', 'observed_at', '2030-01-01T12:01:00Z', 'AUTHORITY_VIEW_STALE'),
    ('checkpoint', 'created_at', '2030-01-01T12:01:00Z', 'CHECKPOINT_STALE'),
    ('checkpoint', 'created_at', '2030-02-31T00:00:00Z', 'TIME_INVALID'),
    ('stop', 'stopped_at', '2030-01-01T11:59:00Z', 'CHECKPOINT_STALE'),
])
def test_migration_rejects_unsafe_control_facts(record, field, value, code):
    f = migration_fixture()
    getattr(f, record)[field] = deepcopy(value)
    install_migration(f)
    with pytest.raises(ContractError) as exc:
        check_migration(f.migration, f.authority, f.context)
    assert exc.value.code == code


def test_source_revocation_needs_current_effective_event():
    f = migration_fixture()
    f.revocations['events'] = []
    install_migration(f)
    with pytest.raises(ContractError, match='SOURCE_REVOCATION_UNPROVEN'):
        check_migration(f.migration, f.authority, f.context)


@pytest.mark.parametrize('name', ['data_evidence', 'dedup_evidence'])
def test_checkpoint_requires_both_retained_evidence_refs(name):
    f = migration_fixture()
    del f.checkpoint[name]
    install_migration(f)
    with pytest.raises(ContractError, match='SCHEMA_INVALID'):
        check_migration(f.migration, f.authority, f.context)


def test_stop_requires_fence_evidence():
    f = migration_fixture()
    del f.stop['fence_evidence']
    install_migration(f)
    with pytest.raises(ContractError, match='SCHEMA_INVALID'):
        check_migration(f.migration, f.authority, f.context)


def test_migration_does_not_bypass_ac2_current_target_ownership():
    f = migration_fixture()
    f.ownership['deployment_id'] = 'deployment-a'
    install_migration(f)
    with pytest.raises(ContractError, match='CURRENT_OWNERSHIP_MISMATCH'):
        check_migration(f.migration, f.authority, f.context)


def test_request_cannot_self_approve():
    f = migration_fixture()
    f.migration['approved'] = True
    with pytest.raises(ContractError, match='SCHEMA_INVALID'):
        check_migration(f.migration, f.authority, f.context)
