"""AC-3 SYNTHETIC host control records; no remote stop or migration occurs."""
from copy import deepcopy
from dataclasses import replace
from p2_fixtures import p2_fixture, install_p2, revocation_event, ISSUER, OBSERVED, FRESH_UNTIL
from fixtures import fixture_digest, fixture_key


def migration_fixture():
    f = p2_fixture()
    f.source_grant = deepcopy(f.grant)
    f.source_grant['status'] = 'REVOKED'
    f.context = replace(f.context, deployment_id='deployment-b')
    f.admission['deployment_ids'].append('deployment-b')
    for obj in (f.request, f.grant, f.ownership):
        obj['deployment_id'] = 'deployment-b'
        obj['generation'] = 8
    f.grant['ref']['id'] = 'grant-b'
    f.request['ownership_grant_ref'] = deepcopy(f.grant['ref'])
    f.ownership['grant_ref'] = deepcopy(f.grant['ref'])
    f.revocations['events'] = [revocation_event(f, f.source_grant['ref'], effective_at='2030-01-01T11:57:00Z')]
    base = {k: deepcopy(f.source_grant[k]) for k in ('contract_version', 'scope', 'instance_id', 'namespace', 'consumption_scope', 'epoch', 'generation')}
    base['source_deployment_id'] = 'deployment-a'
    checkpoint_ref = {'record_kind': 'checkpoint', 'issuer': ISSUER, 'id': 'checkpoint-a'}
    stop_ref = {'record_kind': 'stop-proof', 'issuer': ISSUER, 'id': 'stop-a'}
    def evidence(ident):
        return {'evidence_id': ident, 'digest': fixture_digest({'synthetic': ident}), 'scope': deepcopy(f.context.scope), 'observed_at': OBSERVED, 'valid_until': FRESH_UNTIL,
                'source_ref': {'object_type': 'checkpoint-store', 'namespace': f.context.namespace, 'id': 'synthetic-store', 'scope': deepcopy(f.context.scope)}, 'retention_policy_ref': 'synthetic-retention'}
    f.checkpoint = {**deepcopy(base), 'ref': checkpoint_ref, 'source_grant_ref': deepcopy(f.source_grant['ref']), 'control_revision': 12,
                    'created_at': '2030-01-01T11:58:00Z', 'projection_digest': fixture_digest(f.projection), 'admission_ref': deepcopy(f.admission['ref']),
                    'data_evidence': evidence('snapshot-a'), 'dedup_evidence': evidence('dedup-a'), 'required_capabilities': ['synthetic-capability']}
    f.stop = {**deepcopy(base), 'ref': stop_ref, 'checkpoint_ref': deepcopy(checkpoint_ref), 'source_grant_ref': deepcopy(f.source_grant['ref']), 'state': 'STOPPED', 'active_executors': 0,
              'stopped_at': '2030-01-01T11:57:00Z', 'fence_evidence': evidence('fence-a')}
    f.control = {'contract_version': '0.1-draft', 'scope': deepcopy(f.context.scope), 'instance_id': f.context.instance_id, 'namespace': f.context.namespace,
                 'consumption_scope': f.request['consumption_scope'], 'epoch': f.context.epoch, 'source_grant_ref': deepcopy(f.source_grant['ref']),
                 'checkpoint_ref': deepcopy(checkpoint_ref), 'stop_proof_ref': deepcopy(stop_ref), 'target_grant_ref': deepcopy(f.grant['ref']),
                 'revision': 12, 'revocation_revision': 4, 'state': 'READY', 'complete': True, 'observed_at': OBSERVED, 'valid_until': FRESH_UNTIL,
                 'target_capabilities': ['synthetic-capability'], 'target_provider_bindings': deepcopy(f.projection['provider_bindings'])}
    f.migration = {'contract_version': '0.1-draft', 'target_consumption': deepcopy(f.request), 'source_grant_ref': deepcopy(f.source_grant['ref']), 'checkpoint_ref': deepcopy(checkpoint_ref)}
    install_migration(f)
    return f


def install_migration(f):
    install_p2(f)
    f.authority.put('grant', f.source_grant['ref'], f.source_grant)
    f.authority.put('checkpoint', f.checkpoint['ref'], f.checkpoint)
    f.authority.put('stop-proof', f.stop['ref'], f.stop)
    control_key = fixture_key({'scope': f.context.scope, 'instance_id': f.context.instance_id, 'namespace': f.context.namespace, 'consumption_scope': f.request['consumption_scope']})
    f.authority.views[('migration_control', control_key)] = deepcopy(f.control)
