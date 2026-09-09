"""A deterministic TEST-ONLY handler; no spreadsheet/SQL imports or branches."""
import math

from input_contract import ContractError, Snapshot


def evaluate(snapshot: Snapshot, binding: dict) -> dict:
    if not isinstance(snapshot, Snapshot):
        raise ContractError('SNAPSHOT_REQUIRED')
    doc = snapshot.to_dict()
    if doc['model_ref'] != binding.get('model_ref'):
        raise ContractError('MODEL_BINDING_MISMATCH')
    limit = binding.get('max_reading')
    if type(limit) not in (int, float) or not math.isfinite(limit):
        raise ContractError('RULE_INVALID')
    if binding.get('rule_id') != 'demo.limit' or binding.get('rule_version') != '1.0.0':
        raise ContractError('RULE_INVALID')
    return {'synthetic_demo': True, 'rule_id': binding['rule_id'], 'rule_version': binding['rule_version'],
            'decisions': [{'object_ref': r['object_ref'],
                           'verdict': 'OVER_LIMIT' if r['reading'] > limit else 'WITHIN_LIMIT'}
                          for r in doc['records']]}
