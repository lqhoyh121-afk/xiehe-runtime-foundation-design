"""AC-2 DRAFT local checks; host-injected SYNTHETIC authority seam only.

This is NOT an issuer, signature verifier, permission server, consumption
operation or cross-machine fence. The caller must not build context/readers
from request fields. Python type checks cannot defend a compromised host.
No permission result is cached or persisted; no AC-3 migration is provided.
"""
from dataclasses import dataclass
from datetime import datetime

from validator import (
    TrustedContext, ContractError, context_check, shape, lookup, live,
    digest, validate_projection, local_result, current, key, timestamp,
)


@dataclass(frozen=True, kw_only=True)
class ConsumptionContext(TrustedContext):
    """HOST ONLY identity/epoch; never deserialize an untrusted payload here.

    minimum_revision is the host's trusted non-rollback revocation floor.
    Its persistence and epoch establishment are NOT implemented by this spike.
    """
    instance_id: str
    namespace: str
    epoch: str


def _context(context):
    if (not isinstance(context, ConsumptionContext)
            or not isinstance(context.now, datetime)
            or context.synthetic is not True
            or type(context.minimum_revision) is not int
            or not 0 <= context.minimum_revision <= 9007199254740991):
        raise ContractError('TRUST_CONTEXT_REQUIRED')
    context_check(context)
    for name in ('instance_id', 'namespace', 'epoch'):
        shape('Id', getattr(context, name))


def _policy(authority, context):
    # The request cannot name this trust-policy lookup key or supply the result.
    policy = current(authority, 'issuer_policy', key({
        'scope': context.scope, 'namespace': context.namespace,
    }), context)
    shape('IssuerPolicy', policy)
    live(policy, context)
    if policy['namespace'] != context.namespace or policy['epoch'] != context.epoch:
        raise ContractError('ISSUER_UNAUTHORIZED')
    return policy


def _issuer(issuer, kind, policy):
    if issuer != policy['issuer'] or kind not in policy['allowed_record_kinds']:
        raise ContractError('ISSUER_UNAUTHORIZED')


def _admission(request, authority, context, policy):
    reference = request['admission_ref']
    _issuer(reference['issuer'], 'admission', policy)
    if reference['record_kind'] != 'admission':
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    record = lookup(authority, 'admission', reference, context)
    shape('Admission', record)
    if record['ref'] != reference:
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    live(record, context)
    projection = request['projection']
    if (record['business_ref'] != projection['business_ref']
            or record['definition_ref'] != projection['definition_ref']
            or record['projection_digest'] != digest(projection)):
        raise ContractError('ADMISSION_BINDING_MISMATCH')
    if record['provider_bindings'] != projection['provider_bindings']:
        raise ContractError('ADMISSION_PROVIDER_MISMATCH')
    if context.deployment_id not in record['deployment_ids']:
        raise ContractError('DEPLOYMENT_NOT_ADMITTED')
    return record


def _grant(request, authority, context, policy):
    reference = request['ownership_grant_ref']
    _issuer(reference['issuer'], 'grant', policy)
    if reference['record_kind'] != 'grant':
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    grant = lookup(authority, 'grant', reference, context)
    shape('Grant', grant)
    if grant['ref'] != reference:
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    live(grant, context)
    for field in ('admission_ref', 'instance_id', 'deployment_id', 'namespace',
                  'consumption_scope', 'generation', 'epoch'):
        if grant[field] != request[field]:
            raise ContractError('GRANT_BINDING_MISMATCH')
    return grant


def _ownership(request, authority, context):
    ownership_key = key({
        'scope': context.scope, 'instance_id': context.instance_id,
        'namespace': context.namespace, 'consumption_scope': request['consumption_scope'],
    })
    ownership = current(authority, 'ownership', ownership_key, context)
    shape('CurrentOwnership', ownership)
    _fresh_view(ownership, context)
    if ownership['grant_ref'] != request['ownership_grant_ref']:
        raise ContractError('CURRENT_OWNERSHIP_MISMATCH')
    for field in ('instance_id', 'deployment_id', 'namespace', 'consumption_scope',
                  'generation', 'epoch'):
        if ownership[field] != request[field]:
            raise ContractError('CURRENT_OWNERSHIP_MISMATCH')
    return ownership


def _scope_epoch(record, context):
    if record['scope'] != context.scope:
        raise ContractError('SCOPE_MISMATCH')
    if record['epoch'] != context.epoch:
        raise ContractError('EPOCH_MISMATCH')


def _fresh_view(view, context):
    _scope_epoch(view, context)
    if not view['complete']:
        raise ContractError('AUTHORITY_SYNC_GAP')
    observed, until = timestamp(view['observed_at']), timestamp(view['valid_until'])
    if not observed <= context.now < until:
        raise ContractError('AUTHORITY_VIEW_STALE')


def _revocations(request, authority, context, policy, ownership):
    view = current(authority, 'revocations', key(context.scope), context)
    shape('RevocationView', view)
    _issuer(view['issuer'], 'revocation', policy)
    _fresh_view(view, context)
    if view['revision'] < context.minimum_revision:
        raise ContractError('REVOCATION_ROLLBACK')
    if view['revision'] != ownership['revocation_revision']:
        raise ContractError('REVOCATION_WATERMARK_MISMATCH')
    projection = request['projection']
    references = [request['admission_ref'], request['ownership_grant_ref'],
                  projection['business_ref'], projection['definition_ref'],
                  *projection['dependencies'], *projection['provider_bindings']]
    bound = {key(ref) for ref in references}
    revoked = False
    # Validate ALL events before using any as a denial: a forged issuer must
    # never be presented as a valid revocation fact, even for unrelated refs.
    for event in view['events']:
        _issuer(event['issuer'], 'revocation', policy)
        _scope_epoch(event, context)
        if event['issuer_revision'] > view['revision']:
            raise ContractError('REVOCATION_EVENT_INVALID')
        target = event['target_ref']
        if 'record_kind' in target:
            _issuer(target['issuer'], target['record_kind'], policy)
        effective = timestamp(event['effective_at'])
        if key(target) in bound and effective <= context.now:
            revoked = True
    if revoked:
        raise ContractError('REVOKED')
    return view


def check_consumption(request, authority, context):
    """Read-only local candidate. AuthorityReader is injected by the HOST.

    Returned VALIDATED_LOCAL_ONLY is never a token or production permission.
    """
    _context(context)
    shape('ConsumptionRequest', request)
    for field in ('instance_id', 'deployment_id', 'namespace', 'epoch'):
        if request[field] != getattr(context, field):
            raise ContractError('HOST_BINDING_MISMATCH')
    policy = _policy(authority, context)
    validate_projection(request['projection'], authority, context)
    _admission(request, authority, context, policy)
    _grant(request, authority, context, policy)
    ownership = _ownership(request, authority, context)
    _revocations(request, authority, context, policy, ownership)
    return {**local_result(), 'synthetic_only': True}
