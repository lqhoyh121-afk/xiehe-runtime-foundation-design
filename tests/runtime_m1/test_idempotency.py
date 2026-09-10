"""Current rights before history; immutable historical results. Laiqh."""
from copy import deepcopy
from pathlib import Path
import json
import runpy
import pytest

Harness = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))['Harness']


def test_create_history_is_original_not_latest_snapshot():
    h = Harness()
    try:
        h.setup()
        first = h.request('create', h.create_payload, key='stable-create', request_id='original')
        h.case = first['result']['case_id']
        h.call('run-once', '--case-id', h.case)
        before = h.rows()
        calls = h.call('host-inspect')['result']['calls']
        replay = h.request('create', h.create_payload, key='stable-create', request_id='different')
        assert replay['replayed'] and replay['result'] == first['result']
        assert replay['result']['status'] == 'QUEUED'
        assert replay['commit_revision'] == 1 and replay['request_id'] == 'different'
        changed = deepcopy(h.create_payload)
        changed['input_ref']['digest']['value'] = 'a' * 64
        assert h.request('create', changed, key='stable-create', code=2)['code'] == 'IDEMPOTENCY_CONFLICT'
        assert h.rows() == before
        assert h.call('host-inspect')['result']['calls'] == calls
        assert h.call('snapshot', '--case-id', h.case)['result']['status'] == 'SUCCEEDED'
    finally:
        h.cleanup()


@pytest.mark.parametrize('permission', ['revoke-operation', 'revoke-read'])
def test_current_rights_guard_known_and_unknown_history(permission):
    h = Harness()
    try:
        h.setup().create()
        h.call('host-control', '--scenario', permission)
        before = h.rows()
        for key in ('create-one', 'unknown-key'):
            response = h.request('create', h.create_payload, key=key, code=2)
            assert response['code'] == 'UNAUTHORIZED'
            assert h.case not in json.dumps(response)
        if permission == 'revoke-read':
            assert h.call('snapshot', '--case-id', h.case, code=2)['code'] == 'UNAUTHORIZED'
        h.call('host-inspect')
        assert h.rows() == before
    finally:
        h.cleanup()


def test_terminal_submit_replay_after_expiry_and_new_key_rejected():
    h = Harness()
    try:
        h.setup().create()
        first = h.call('run-once', '--case-id', h.case)
        h.call('host-control', '--scenario', 'advance-past-deadline')
        before = h.rows()
        calls = h.call('host-inspect')['result']['calls']
        replay = h.call('host-test', '--case-id', h.case, '--scenario', 'submit-replay')
        assert replay['replayed'] and replay['result'] == first['result']
        assert h.call('host-test', '--case-id', h.case, '--scenario', 'submit-new-key', code=2)['code'] == 'INVALID_STATE'
        assert h.rows() == before and h.call('host-inspect')['result']['calls'] == calls
    finally:
        h.cleanup()


def test_stop_new_and_revision_conflict_do_not_revoke_historical_create():
    h = Harness()
    try:
        h.setup().create()
        state = {'registration_id': h.registration, 'expected_revision': 1, 'target_state': 'STOP_NEW'}
        assert h.request('set-state', state, code=2)['code'] == 'REVISION_CONFLICT'
        state['expected_revision'] = 2
        h.request('set-state', state)
        before = h.rows()
        assert h.request('create', h.create_payload, key='create-one')['replayed']
        assert h.request('create', h.create_payload, key='new-create', code=2)['code'] == 'BUSINESS_NOT_ENABLED'
        assert h.rows() == before
    finally:
        h.cleanup()
