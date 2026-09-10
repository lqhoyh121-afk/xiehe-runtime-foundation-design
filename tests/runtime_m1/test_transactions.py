"""Real process exits, independent SQLite observations; no mocked commits. Laiqh."""
from pathlib import Path
import runpy
import pytest

Harness = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))['Harness']
POINTS = ['after_state', 'after_idempotency', 'after_events', 'before_commit', 'after_commit_before_response']


@pytest.mark.parametrize('point', POINTS)
def test_create_crash_atomicity(point):
    h = Harness()
    try:
        h.setup()
        before = h.rows()
        h.call('host-control', '--scenario', 'fault-create-' + point)
        h.request('create', h.create_payload, key='fault-create', code=86)
        crashed = h.rows()
        if point == 'after_commit_before_response':
            assert len(crashed['cases']) == 1 and len(crashed['events']) == len(before['events']) + 2
        else:
            assert crashed == before
        h.call('host-control', '--scenario', 'disarm-fault')
        replay = h.request('create', h.create_payload, key='fault-create')
        assert replay['replayed'] == (point == 'after_commit_before_response')
        assert len(h.rows()['cases']) == 1 and len(h.rows()['ready_nodes']) == 1
    finally:
        h.cleanup()


@pytest.mark.parametrize('point', POINTS)
def test_submit_crash_atomicity(point):
    h = Harness()
    try:
        h.setup().create()
        h.call('host-test', '--case-id', h.case, '--scenario', 'submit-fault-' + point, code=86)
        crashed = h.rows()
        snap = h.call('snapshot', '--case-id', h.case)['result']
        committed = point == 'after_commit_before_response'
        assert snap['revision'] == (3 if committed else 2)
        assert snap['status'] == ('SUCCEEDED' if committed else 'RUNNING')
        assert len(crashed['events']) == (8 if committed else 6)
        assert len(crashed['evidence']) == (2 if committed else 1)
        assert len(crashed['ready_nodes']) == (0 if committed else 1)
        assert len(crashed['idempotency_results']) == (5 if committed else 4)
        calls = h.call('host-inspect')['result']['calls']
        result = h.call('host-test', '--case-id', h.case, '--scenario', 'submit-replay', code=0 if committed else 2)
        assert result.get('replayed') if committed else result['code'] == 'LEASE_LOST'
        assert h.rows() == crashed and h.call('host-inspect')['result']['calls'] == calls
    finally:
        h.cleanup()


@pytest.mark.parametrize('scenario,expected,code', [
    ('bad-owner', 'LEASE_LOST', 2), ('bad-attempt', 'LEASE_LOST', 2), ('bad-lease', 'LEASE_LOST', 2),
    ('expired', 'LEASE_LOST', 2), ('mutate-input', 'INPUT_STALE', 2),
    ('tamper-input', 'VERSION_DIGEST_MISMATCH', 2), ('expire-input', 'INPUT_STALE', 2),
    ('revoke-provider', 'REVOKED', 2), ('revoke-grant', 'REVOKED', 2),
    ('deny-rule', 'RULE_DENIED', 2), ('needs-input', 'CAPABILITY_UNSUPPORTED', 2),
    ('rule-unavailable', 'DEPENDENCY_UNAVAILABLE', 3), ('output-mismatch', 'CONTRACT_INVALID', 2),
])
def test_submit_current_binding_and_lease(scenario, expected, code):
    h = Harness()
    try:
        h.setup().create()
        result = h.call('host-test', '--case-id', h.case, '--scenario', 'submit-' + scenario, code=code)
        assert result['code'] == expected
        snap = h.call('snapshot', '--case-id', h.case)['result']
        assert snap['status'] == 'RUNNING' and snap['revision'] == 2
        rows = h.rows()
        assert len(rows['evidence']) == 1 and len(rows['events']) == 6 and len(rows['ready_nodes']) == 1
    finally:
        h.cleanup()


def test_expired_before_execution_never_calls_executor():
    h = Harness()
    try:
        h.setup().create()
        result = h.call('host-test', '--case-id', h.case, '--scenario', 'execute-expired', code=2)
        assert result['code'] == 'LEASE_LOST'
        calls = h.call('host-inspect')['result']['calls']
        assert not any(x['provider'] == 'executor_ref' for x in calls)
        assert (h.sandbox / 'host' / ('intent-' + h.case + '.json')).is_file()
    finally:
        h.cleanup()


def test_claim_crash_then_expire_never_automatically_reclaims():
    h = Harness()
    try:
        h.setup().create()
        h.call('host-test', '--case-id', h.case, '--scenario', 'claim-crash', code=86)
        h.call('host-control', '--scenario', 'advance-past-deadline')
        before = h.rows()
        snapshot = h.call('snapshot', '--case-id', h.case)['result']
        assert snapshot['status'] == 'RUNNING' and snapshot['blockers'] == ['LEASE_LOST']
        assert h.call('run-once', '--case-id', h.case, code=2)['code'] == 'LEASE_LOST'
        assert h.rows() == before and len(before['attempts']) == 1
    finally:
        h.cleanup()
