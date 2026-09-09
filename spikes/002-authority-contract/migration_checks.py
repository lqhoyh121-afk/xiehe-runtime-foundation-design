"""AC-3 DRAFT read-only candidate, never a remote stop/fence or migration.

The HOST supplies the synthetic control Reader. Checkpoint/stop record issuer
matching is a binding check, not issuer permission or cryptographic validation.
Shared AC-2 policy does not yet define production control-record authority.
Per-call read memoization prevents reinterpreting an unvalidated second view;
it is NOT a distributed transaction or protection against post-check changes.
"""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from authority_checks import check_consumption
from validator import (
    SCHEMA, ContractError, canonical_bytes, current, lookup, key, shape,
    timestamp, digest, resolve,
)

SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'docs/architecture-track/contracts/migration-contract.schema.json'
MIGRATION_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
Draft202012Validator.check_schema(MIGRATION_SCHEMA)
# An explicit in-memory registry: no remote retrieval and no shared-def copy.
REGISTRY = Registry().with_resources([
    (SCHEMA['$id'], Resource.from_contents(SCHEMA)),
    (MIGRATION_SCHEMA['$id'], Resource.from_contents(MIGRATION_SCHEMA)),
])


def migration_shape(name, value):
    canonical_bytes(value)
    wrapper = {'$ref': MIGRATION_SCHEMA['$id'] + '#/$defs/' + name}
    if next(Draft202012Validator(wrapper, registry=REGISTRY).iter_errors(value), None):
        raise ContractError('SCHEMA_INVALID')


class _CallReads:
    """One invocation only; no permit cache or persisted authority state."""
    def __init__(self, authority):
        self.authority = authority
        self.records = {}
        self.views = {}

    def lookup(self, kind, reference, context):
        ident = (kind, key(reference))
        if ident not in self.records:
            self.records[ident] = lookup(self.authority, kind, reference, context)
        return deepcopy(self.records[ident])

    def current(self, kind, reference, context):
        ident = (kind, reference)
        if ident not in self.views:
            self.views[ident] = current(self.authority, kind, reference, context)
        return deepcopy(self.views[ident])


def _binding(record, expected, fields):
    if any(record[field] != expected[field] for field in fields):
        raise ContractError('MIGRATION_BINDING_MISMATCH')


def _reference(reference, kind, issuer):
    shape('AuthorityRef', reference)
    if reference['record_kind'] != kind or reference['issuer'] != issuer:
        raise ContractError('AUTHORITY_BINDING_MISMATCH')


def _evidence(evidence, context):
    shape('EvidenceRef', evidence)
    if (evidence['scope'] != context.scope
            or evidence['source_ref']['scope'] != context.scope
            or evidence['source_ref']['namespace'] != context.namespace):
        raise ContractError('MIGRATION_BINDING_MISMATCH')
    if not timestamp(evidence['observed_at']) <= context.now < timestamp(evidence['valid_until']):
        raise ContractError('EVIDENCE_STALE')


def check_migration(request, authority, context):
    """Validate local control facts and target AC-2 rights; execute nothing."""
    migration_shape('MigrationRequest', request)
    target = request['target_consumption']
    reads = _CallReads(authority)
    result = check_consumption(target, reads, context)
    ownership_key = key({'scope': context.scope, 'instance_id': context.instance_id,
                         'namespace': context.namespace, 'consumption_scope': target['consumption_scope']})
    ownership = current(reads, 'ownership', ownership_key, context)
    revocations = current(reads, 'revocations', key(context.scope), context)
    control = current(reads, 'migration_control', ownership_key, context)
    migration_shape('MigrationControl', control)
    _binding(control, target, ('instance_id', 'namespace', 'consumption_scope', 'epoch'))
    if control['scope'] != context.scope:
        raise ContractError('MIGRATION_BINDING_MISMATCH')
    if not control['complete']:
        raise ContractError('AUTHORITY_SYNC_GAP')
    if not timestamp(control['observed_at']) <= context.now < timestamp(control['valid_until']):
        raise ContractError('AUTHORITY_VIEW_STALE')
    if control['state'] == 'UNKNOWN':
        raise ContractError('MIGRATION_UNKNOWN')
    if (control['revision'] != ownership['revision']
            or control['revocation_revision'] != revocations['revision']):
        raise ContractError('CONTROL_REVISION_MISMATCH')
    if control['checkpoint_ref'] != request['checkpoint_ref']:
        raise ContractError('CHECKPOINT_STALE')
    if (control['source_grant_ref'] != request['source_grant_ref']
            or control['target_grant_ref'] != target['ownership_grant_ref']):
        raise ContractError('MIGRATION_BINDING_MISMATCH')
    issuer = target['ownership_grant_ref']['issuer']
    for reference, kind in ((request['source_grant_ref'], 'grant'),
                            (request['checkpoint_ref'], 'checkpoint'),
                            (control['stop_proof_ref'], 'stop-proof')):
        _reference(reference, kind, issuer)
    source = lookup(reads, 'grant', request['source_grant_ref'], context)
    shape('Grant', source)
    if source['ref'] != request['source_grant_ref']:
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    _binding(source, target, ('instance_id', 'namespace', 'consumption_scope', 'epoch', 'admission_ref'))
    if source['scope'] != context.scope or source['deployment_id'] == target['deployment_id']:
        raise ContractError('MIGRATION_BINDING_MISMATCH')
    if source['status'] != 'REVOKED':
        raise ContractError('SOURCE_GRANT_NOT_REVOKED')
    if target['generation'] <= source['generation']:
        raise ContractError('GENERATION_NOT_ADVANCED')
    # AC-2 already validated every issuer/scope/epoch/event in this same view.
    if not any(event['target_ref'] == source['ref']
               and timestamp(event['effective_at']) <= context.now
               for event in revocations['events']):
        raise ContractError('SOURCE_REVOCATION_UNPROVEN')
    checkpoint = lookup(reads, 'checkpoint', request['checkpoint_ref'], context)
    stop = lookup(reads, 'stop-proof', control['stop_proof_ref'], context)
    migration_shape('Checkpoint', checkpoint)
    migration_shape('StopProof', stop)
    if checkpoint['ref'] != request['checkpoint_ref'] or stop['ref'] != control['stop_proof_ref']:
        raise ContractError('AUTHORITY_BINDING_MISMATCH')
    source_binding = {**source, 'source_deployment_id': source['deployment_id'], 'source_grant_ref': source['ref']}
    for record in (checkpoint, stop):
        _binding(record, source_binding, ('scope', 'instance_id', 'namespace', 'consumption_scope',
                                         'epoch', 'generation', 'source_deployment_id', 'source_grant_ref'))
    if stop['checkpoint_ref'] != checkpoint['ref']:
        raise ContractError('CHECKPOINT_STALE')
    if checkpoint['control_revision'] != control['revision']:
        raise ContractError('CHECKPOINT_STALE')
    if (checkpoint['admission_ref'] != target['admission_ref']
            or checkpoint['projection_digest'] != digest(target['projection'])):
        raise ContractError('MIGRATION_BINDING_MISMATCH')
    if stop['state'] == 'UNKNOWN':
        raise ContractError('MIGRATION_UNKNOWN')
    if stop['state'] not in ('STOPPED', 'FENCED') or stop['active_executors'] != 0:
        raise ContractError('SOURCE_EXECUTOR_NOT_STOPPED')
    created, stopped = timestamp(checkpoint['created_at']), timestamp(stop['stopped_at'])
    if not (timestamp(source['valid_from']) <= stopped <= created
            < timestamp(source['expires_at']) and created <= timestamp(control['observed_at'])):
        raise ContractError('CHECKPOINT_STALE')
    for evidence in (checkpoint['data_evidence'], checkpoint['dedup_evidence'], stop['fence_evidence']):
        _evidence(evidence, context)
    required = set(checkpoint['required_capabilities'])
    for reference in target['projection']['provider_bindings']:
        required.update(resolve(reference, reads, context)['content']['capabilities'])
    if (not required.issubset(control['target_capabilities'])
            or {key(r) for r in target['projection']['provider_bindings']}
            != {key(r) for r in control['target_provider_bindings']}):
        raise ContractError('TARGET_CAPABILITY_MISSING')
    return {**result, 'migration_executed': False}
