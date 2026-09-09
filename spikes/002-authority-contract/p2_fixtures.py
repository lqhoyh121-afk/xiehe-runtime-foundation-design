"""SYNTHETIC host-owned P2 read fixtures, NOT a production authority.

Only test code installs these records. No request-to-context or trust-file
loader exists. The inherited mutable store is a test control, not an issuer.
"""
from copy import deepcopy

from authority_checks import ConsumptionContext
from fixtures import fixture, fixture_digest, fixture_key, START, END, SCOPE

ISSUER = 'synthetic-control'
EPOCH = 'synthetic-epoch-1'
NAMESPACE = 'synthetic-instance-space'
CONSUMPTION_SCOPE = 'synthetic-source'
OBSERVED = '2030-01-01T11:59:00Z'
FRESH_UNTIL = '2030-01-01T12:05:00Z'


def p2_fixture():
    f = fixture()
    f.context = ConsumptionContext(
        scope=deepcopy(SCOPE), deployment_id='deployment-a', now=f.context.now,
        minimum_revision=4, synthetic=True, instance_id='instance-a',
        namespace=NAMESPACE, epoch=EPOCH,
    )
    admission_ref = {'record_kind': 'admission', 'issuer': ISSUER, 'id': 'admission-a'}
    grant_ref = {'record_kind': 'grant', 'issuer': ISSUER, 'id': 'grant-a'}
    lifecycle = {'status': 'ACTIVE', 'valid_from': START, 'expires_at': END}
    common = {'contract_version': '0.1-draft', 'scope': deepcopy(SCOPE)}
    f.admission = {
        **deepcopy(common), **lifecycle, 'ref': admission_ref,
        'business_ref': deepcopy(f.projection['business_ref']),
        'definition_ref': deepcopy(f.projection['definition_ref']),
        'projection_digest': fixture_digest(f.projection),
        'provider_bindings': deepcopy(f.projection['provider_bindings']),
        'deployment_ids': ['deployment-a'],
    }
    f.grant = {
        **deepcopy(common), **lifecycle, 'ref': grant_ref,
        'admission_ref': admission_ref, 'instance_id': 'instance-a',
        'deployment_id': 'deployment-a', 'namespace': NAMESPACE,
        'consumption_scope': CONSUMPTION_SCOPE, 'generation': 7, 'epoch': EPOCH,
    }
    f.policy = {
        **deepcopy(common), **lifecycle, 'issuer': ISSUER, 'namespace': NAMESPACE,
        'epoch': EPOCH, 'allowed_record_kinds': ['admission', 'grant', 'revocation'],
    }
    f.ownership = {
        **deepcopy(common), 'instance_id': 'instance-a',
        'deployment_id': 'deployment-a', 'namespace': NAMESPACE,
        'consumption_scope': CONSUMPTION_SCOPE, 'generation': 7, 'epoch': EPOCH,
        'grant_ref': grant_ref, 'revision': 12, 'revocation_revision': 4,
        'complete': True, 'observed_at': OBSERVED, 'valid_until': FRESH_UNTIL,
    }
    f.revocations = {
        **deepcopy(common), 'issuer': ISSUER, 'epoch': EPOCH,
        'revision': 4, 'complete': True, 'observed_at': OBSERVED,
        'valid_until': FRESH_UNTIL, 'events': [],
    }
    f.request = {
        'contract_version': '0.1-draft', 'projection': deepcopy(f.projection),
        'admission_ref': admission_ref, 'ownership_grant_ref': grant_ref,
        'instance_id': 'instance-a', 'deployment_id': 'deployment-a',
        'worker_session_id': 'worker-session-one', 'namespace': NAMESPACE,
        'consumption_scope': CONSUMPTION_SCOPE, 'generation': 7, 'epoch': EPOCH,
    }
    # Independent object graphs: altering a request cannot mutate host records.
    for name in ('request', 'admission', 'grant', 'policy', 'ownership', 'revocations'):
        setattr(f, name, deepcopy(getattr(f, name)))
    install_p2(f)
    return f


def install_p2(f):
    """Install independently supplied host records, never the request."""
    f.authority.put('admission', f.admission['ref'], f.admission)
    f.authority.put('grant', f.grant['ref'], f.grant)
    f.authority.views[('issuer_policy', fixture_key({
        'scope': f.context.scope, 'namespace': f.context.namespace,
    }))] = deepcopy(f.policy)
    f.authority.views[('ownership', fixture_key({
        'scope': f.context.scope, 'instance_id': f.context.instance_id,
        'namespace': f.context.namespace, 'consumption_scope': CONSUMPTION_SCOPE,
    }))] = deepcopy(f.ownership)
    f.authority.views[('revocations', fixture_key(f.context.scope))] = deepcopy(f.revocations)


def revocation_event(f, target=None, **changes):
    event = {
        'issuer': ISSUER, 'event_id': 'revoke-a', 'scope': deepcopy(SCOPE),
        'epoch': EPOCH, 'target_ref': deepcopy(target or f.request['ownership_grant_ref']),
        'issuer_revision': 4, 'effective_at': '2030-01-01T12:00:00Z',
        'reason_ref': 'synthetic-withdrawal',
    }
    event.update(changes)
    return event
