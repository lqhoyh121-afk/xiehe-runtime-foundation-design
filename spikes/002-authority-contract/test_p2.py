"""AC-2 L1 only: hostile requests against a SYNTHETIC host read seam.

Expected decisions come from interfaces.md 1/2.1/3.1 and AC-2, not from
validator-generated oracle data. No credentials, issuance or external writes.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

from authority_checks import check_consumption
from p2_fixtures import p2_fixture, install_p2, revocation_event
from validator import ContractError


def reject(f, code):
    with pytest.raises(ContractError) as exc:
        check_consumption(f.request, f.authority, f.context)
    assert exc.value.code == code


def test_host_supplied_admission_and_current_grant_are_local_only():
    f = p2_fixture()
    assert check_consumption(f.request, f.authority, f.context) == {
        'verdict': 'VALIDATED_LOCAL_ONLY', 'contract_status': 'DRAFT',
        'production_authorized': False, 'synthetic_only': True,
    }


@pytest.mark.parametrize('field,value', [
    ('approved', True), ('restore', True), ('auth_context', {'approved': True}),
    ('minimum_revision', 0), ('issuer', 'attacker'), ('authority', {}),
])
def test_request_cannot_supply_approval_restore_or_trust(field, value):
    f = p2_fixture()
    f.request[field] = value
    reject(f, 'SCHEMA_INVALID')


def test_forged_approved_claim_has_no_admission_even_after_flag_removed():
    f = p2_fixture()
    f.request['admission_ref']['id'] = 'self-approved-not-published'
    f.request['approved'] = True
    reject(f, 'SCHEMA_INVALID')
    del f.request['approved']
    reject(f, 'DEPENDENCY_UNAVAILABLE')


def test_context_mapping_from_request_is_not_a_host_context():
    f = p2_fixture()
    f.context = asdict(f.context)
    reject(f, 'TRUST_CONTEXT_REQUIRED')


@pytest.mark.parametrize('field,value', [
    ('instance_id', 'copied-instance'), ('deployment_id', 'copied-deployment'),
    ('namespace', 'copied-namespace'), ('epoch', 'obsolete-epoch'),
])
def test_request_identity_must_match_host_not_copied_fields(field, value):
    f = p2_fixture()
    f.request[field] = value
    reject(f, 'HOST_BINDING_MISMATCH')


def test_verbatim_copied_request_on_different_host_has_no_consumption_right():
    f = p2_fixture()
    f.context = replace(f.context, deployment_id='copied-deployment')
    reject(f, 'HOST_BINDING_MISMATCH')


@pytest.mark.parametrize('field,value', [
    ('instance_id', 'other-instance'), ('deployment_id', 'other-deployment'),
    ('namespace', 'other-namespace'), ('consumption_scope', 'other-source'),
    ('generation', 8), ('epoch', 'other-epoch'),
])
def test_host_grant_must_bind_every_consumption_dimension(field, value):
    f = p2_fixture()
    f.grant[field] = value
    install_p2(f)
    reject(f, 'GRANT_BINDING_MISMATCH')


def test_grant_must_bind_exact_admission_not_just_a_valid_one():
    f = p2_fixture()
    f.grant['admission_ref']['id'] = 'unrelated-admission'
    install_p2(f)
    reject(f, 'GRANT_BINDING_MISMATCH')


def test_issued_old_grant_is_not_current_ownership():
    f = p2_fixture()
    f.ownership['grant_ref']['id'] = 'replacement-grant'
    f.ownership['generation'] = 8
    install_p2(f)
    reject(f, 'CURRENT_OWNERSHIP_MISMATCH')


def test_matching_copied_deployment_claim_still_needs_a_new_host_grant():
    f = p2_fixture()
    f.context = replace(f.context, deployment_id='copied-deployment')
    f.request['deployment_id'] = 'copied-deployment'
    f.admission['deployment_ids'].append('copied-deployment')
    install_p2(f)
    reject(f, 'GRANT_BINDING_MISMATCH')


def test_forged_issuer_is_not_authorized_by_returning_a_record():
    f = p2_fixture()
    f.request['admission_ref']['issuer'] = 'attacker'
    f.admission['ref']['issuer'] = 'attacker'
    install_p2(f)
    reject(f, 'ISSUER_UNAUTHORIZED')


@pytest.mark.parametrize('field,value,code', [
    ('contract_version', '99.0', 'SCHEMA_INVALID'),
    ('scope', {'tenant': 'other', 'project': 'synthetic-project'}, 'SCOPE_MISMATCH'),
    ('deployment_ids', ['other-deployment'], 'DEPLOYMENT_NOT_ADMITTED'),
    ('provider_bindings', [], 'SCHEMA_INVALID'),
])
def test_admission_scope_version_and_deployment_are_enforced(field, value, code):
    f = p2_fixture()
    f.admission[field] = value
    install_p2(f)
    reject(f, code)


@pytest.mark.parametrize('field', ['business_ref', 'definition_ref'])
def test_admission_pins_exact_reference_version(field):
    f = p2_fixture()
    f.admission[field]['version'] = '1.0.1'
    install_p2(f)
    reject(f, 'ADMISSION_BINDING_MISMATCH')


def test_admission_pins_projection_digest():
    f = p2_fixture()
    f.admission['projection_digest']['value'] = '0' * 64
    install_p2(f)
    reject(f, 'ADMISSION_BINDING_MISMATCH')


def test_admission_provider_versions_are_exact_not_just_provider_names():
    f = p2_fixture()
    f.admission['provider_bindings'][0]['version'] = '1.0.1'
    install_p2(f)
    reject(f, 'ADMISSION_PROVIDER_MISMATCH')


@pytest.mark.parametrize('target_name', [
    'admission', 'grant', 'business', 'runtime', 'model', 'rule', 'provider',
])
def test_effective_revocation_blocks_exact_bound_dependency(target_name):
    f = p2_fixture()
    targets = {
        'admission': f.request['admission_ref'], 'grant': f.request['ownership_grant_ref'],
        'business': f.projection['business_ref'], 'runtime': f.projection['definition_ref'],
        'model': f.model, 'rule': f.rule, 'provider': f.providers['NodeExecutor'],
    }
    f.revocations['events'] = [revocation_event(f, targets[target_name])]
    install_p2(f)
    reject(f, 'REVOKED')


@pytest.mark.parametrize('view_name,field,value,code', [
    ('ownership', 'complete', False, 'AUTHORITY_SYNC_GAP'),
    ('revocations', 'complete', False, 'AUTHORITY_SYNC_GAP'),
    ('ownership', 'valid_until', '2030-01-01T12:00:00Z', 'AUTHORITY_VIEW_STALE'),
    ('revocations', 'valid_until', '2030-01-01T12:00:00Z', 'AUTHORITY_VIEW_STALE'),
    ('ownership', 'observed_at', '2030-01-01T12:00:01Z', 'AUTHORITY_VIEW_STALE'),
    ('revocations', 'observed_at', '2030-01-01T12:00:01Z', 'AUTHORITY_VIEW_STALE'),
    ('revocations', 'revision', 3, 'REVOCATION_ROLLBACK'),
    ('revocations', 'revision', 5, 'REVOCATION_WATERMARK_MISMATCH'),
    ('ownership', 'revocation_revision', 5, 'REVOCATION_WATERMARK_MISMATCH'),
    ('revocations', 'epoch', 'old-epoch', 'EPOCH_MISMATCH'),
    ('revocations', 'scope', {'tenant': 'other', 'project': 'synthetic-project'}, 'SCOPE_MISMATCH'),
    ('revocations', 'issuer', 'attacker', 'ISSUER_UNAUTHORIZED'),
])
def test_current_view_integrity_freshness_and_watermarks_fail_closed(view_name, field, value, code):
    f = p2_fixture()
    getattr(f, view_name)[field] = value
    install_p2(f)
    reject(f, code)


@pytest.mark.parametrize('field,value,code', [
    ('issuer', 'attacker', 'ISSUER_UNAUTHORIZED'),
    ('scope', {'tenant': 'other', 'project': 'synthetic-project'}, 'SCOPE_MISMATCH'),
    ('epoch', 'old-epoch', 'EPOCH_MISMATCH'),
    ('issuer_revision', 5, 'REVOCATION_EVENT_INVALID'),
    ('effective_at', '2030-02-30T12:00:00Z', 'TIME_INVALID'),
    ('restore', True, 'SCHEMA_INVALID'),
])
def test_forged_or_unbound_revocation_event_is_rejected_not_applied(field, value, code):
    f = p2_fixture()
    event = revocation_event(f)
    event[field] = value
    f.revocations['events'] = [event]
    install_p2(f)
    reject(f, code)


def test_malformed_revocation_reference_is_not_treated_as_an_empty_snapshot():
    f = p2_fixture()
    event = revocation_event(f, f.rule)
    del event['target_ref']['digest']
    f.revocations['events'] = [event]
    install_p2(f)
    reject(f, 'SCHEMA_INVALID')


def test_future_effective_revocation_blocks_only_when_host_clock_reaches_time():
    f = p2_fixture()
    f.revocations['events'] = [revocation_event(f, effective_at='2030-01-01T12:00:01Z')]
    install_p2(f)
    assert check_consumption(f.request, f.authority, f.context)['verdict'] == 'VALIDATED_LOCAL_ONLY'
    f.context = replace(f.context, now=datetime(2030, 1, 1, 12, 0, 1, tzinfo=timezone.utc))
    reject(f, 'REVOKED')


def test_revocation_does_not_match_other_exact_versions_by_name():
    f = p2_fixture()
    different_version = deepcopy(f.rule)
    different_version['version'] = '1.0.1'
    f.revocations['events'] = [revocation_event(f, different_version)]
    install_p2(f)
    assert check_consumption(f.request, f.authority, f.context)['verdict'] == 'VALIDATED_LOCAL_ONLY'


@pytest.mark.parametrize('record_name', ['admission', 'grant', 'policy'])
@pytest.mark.parametrize('field,value,code', [
    ('status', 'REVOKED', 'REVOKED'),
    ('valid_from', '2030-01-01T12:00:01Z', 'NOT_YET_VALID'),
    ('expires_at', '2030-01-01T12:00:00Z', 'EXPIRED'),
    ('valid_from', '2030-01-02T00:00:00Z', 'TIME_INVALID'),
])
def test_authority_record_lifecycle_is_rechecked(record_name, field, value, code):
    f = p2_fixture()
    getattr(f, record_name)[field] = value
    install_p2(f)
    reject(f, code)


def test_success_does_not_cache_rights_after_trusted_revocation():
    f = p2_fixture()
    assert check_consumption(f.request, f.authority, f.context)['verdict'] == 'VALIDATED_LOCAL_ONLY'
    f.revocations['events'] = [revocation_event(f, issuer_revision=5)]
    f.revocations['revision'] = 5
    f.ownership['revocation_revision'] = 5
    install_p2(f)
    reject(f, 'REVOKED')


def test_missing_current_revocation_view_is_not_no_revocations():
    f = p2_fixture()
    f.authority.views = {k: v for k, v in f.authority.views.items() if k[0] != 'revocations'}
    reject(f, 'AUTHORITY_UNAVAILABLE')
