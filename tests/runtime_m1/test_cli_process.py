"""Real CLI process acceptance, SYNTHETIC only. Laiqh."""
from pathlib import Path
import runpy
import json
import subprocess
import sys
import time
import pytest

Harness = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))['Harness']


def test_registration_enable_create_cli():
    h = Harness()
    try:
        initial = h.init()
        registration = h.register()
        assert registration['state'] == 'REGISTERED'
        payload = {'registration_id': registration['registration_id'], 'input_ref': initial['input_ref'],
                   'object_refs': initial['object_refs']}
        denied = h.request('create', payload, code=2)
        assert denied['code'] == 'BUSINESS_NOT_ENABLED'
        h.request('set-state', {'registration_id': registration['registration_id'],
                               'expected_revision': 1, 'target_state': 'ENABLED'})
        case = h.request('create', payload)['result']
        assert case['status'] == 'QUEUED' and case['revision'] == 1
        rows = h.rows()
        assert len(rows['cases']) == len(rows['node_runs']) == len(rows['ready_nodes']) == 1
        assert len(rows['events']) == 4
    finally:
        h.cleanup()


def test_single_node_execution_then_fresh_process_query():
    h = Harness()
    try:
        h.setup().create()
        run = h.call('run-once', '--case-id', h.case)
        assert run['result']['status'] == 'SUCCEEDED'
        before = h.rows()
        snapshot = h.call('snapshot', '--case-id', h.case)['result']
        events = h.call('events', '--case-id', h.case)['result']
        assert snapshot['case_id'] == h.case
        assert snapshot['revision'] == 3 and snapshot['status'] == 'SUCCEEDED'
        assert snapshot['nodes'][0]['output'] == {'echo': 'SYNTHETIC RC0'}
        assert [e['type'] for e in events['items']] == [
            'CASE_CREATED', 'NODE_READY', 'NODE_LEASED', 'NODE_STARTED', 'NODE_SUCCEEDED', 'CASE_SUCCEEDED']
        assert [e['case_revision'] for e in events['items']] == [1, 1, 2, 2, 3, 3]
        assert h.rows() == before
        assert len(before['attempts']) == 1
        again = h.call('run-once', '--case-id', h.case, code=2)
        assert again['code'] == 'ALREADY_TERMINAL'
        assert h.rows() == before
    finally:
        h.cleanup()


def test_query_sees_one_view_while_real_writer_commits():
    h = Harness()
    child = None
    try:
        h.setup().create()
        command = [sys.executable, '-B', 'tools/runtime_core_cli.py', '--sandbox', str(h.sandbox),
                   'host-test', '--case-id', h.case, '--scenario', 'snapshot-barrier']
        child = subprocess.Popen(command, cwd=h.sandbox.parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        ready = h.sandbox / 'observations/query-ready.json'
        deadline = time.monotonic() + 15
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), child.communicate(timeout=2)
        assert h.call('host-cleanup', '--manifest', str(h.sandbox / 'manifest.json'), code=3)['code'] == 'IN_PROGRESS'
        h.call('run-once', '--case-id', h.case)
        assert child.poll() is None
        h.call('host-control', '--scenario', 'release-query')
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode == 0, (stdout, stderr)
        old = json.loads(stdout)['result']
        assert old['status'] == 'QUEUED' and old['revision'] == 1 and old['watermark'] == 4
        new = h.call('snapshot', '--case-id', h.case)['result']
        assert new['status'] == 'SUCCEEDED' and new['watermark'] == 8
    finally:
        if child and child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        h.cleanup()


@pytest.mark.parametrize('args', [
    ('host-inspect', '--request', 'ignored.json'), ('host-init', '--case-id', 'ignored'),
    ('snapshot', '--case-id', 'ignored', '--scenario', 'ignored'),
    ('resume_case',), ('submit_node_result',), ('execute-module', '--module', 'os'),
])
def test_unknown_or_irrelevant_arguments_are_rejected(args):
    h = Harness()
    try:
        h.init()
        assert h.call(*args, code=2)['code'] in {'INPUT_INVALID', 'CAPABILITY_UNSUPPORTED'}
    finally:
        h.cleanup()


@pytest.mark.parametrize('target_state', [[], {}, None, True, False, 0, 1])
def test_set_state_wrong_type_is_input_error_without_writes(target_state):
    h = Harness()
    try:
        h.init()
        registration = h.register()
        before = h.rows()
        try:
            rejected = h.request('set-state', {
                'registration_id': registration['registration_id'],
                'expected_revision': 1, 'target_state': target_state}, code=2)
            assert rejected['code'] in {'SCHEMA_INVALID', 'INPUT_INVALID'}
        finally:
            assert h.rows() == before
    finally:
        h.cleanup()


def test_payload_sibling_types_and_state_string_semantics():
    h = Harness()
    try:
        initial = h.init()
        registration = h.register()['registration_id']
        registration_payload = json.loads((h.sandbox / 'requests/register.json').read_text(encoding='utf-8'))['payload']
        state_payload = {'registration_id': registration, 'expected_revision': 1, 'target_state': 'ENABLED'}
        create_payload = {'registration_id': registration, 'input_ref': initial['input_ref'],
                          'object_refs': initial['object_refs']}
        before = h.rows()
        for command, payload in [('register', registration_payload), ('set-state', state_payload),
                                 ('create', create_payload)]:
            for field in payload:
                for invalid in ([], {}, None, True, 1):
                    if field == 'expected_revision' and type(invalid) is int:
                        continue  # Revision 1 is valid, not a wrong-type fixture.
                    rejected = h.request(command, {**payload, field: invalid}, code=2)
                    assert rejected['code'] != 'STORAGE_INVALID', (command, field, invalid)
                    assert h.rows() == before
        # The shared canonical JSON gate rejects floats before field validation.
        assert h.request('set-state', {**state_payload, 'target_state': 1.5}, code=2)['code'] == 'CANONICALIZATION_INVALID'
        assert h.rows() == before
        for unknown in ('', 'UNKNOWN', 'enabled', ' ENABLED '):
            assert h.request('set-state', {**state_payload, 'target_state': unknown}, code=2)['code'] == 'CAPABILITY_UNSUPPORTED'
            assert h.rows() == before
        enabled = h.request('set-state', state_payload)['result']
        assert enabled['state'] == 'ENABLED' and enabled['revision'] == 2
        stopped = h.request('set-state', {**state_payload, 'expected_revision': 2, 'target_state': 'STOP_NEW'})['result']
        assert stopped['state'] == 'STOP_NEW' and stopped['revision'] == 3
    finally:
        h.cleanup()


@pytest.mark.parametrize('kind', ['missing', 'version', 'corrupt', 'binding-type'])
def test_query_never_creates_or_migrates_storage(kind):
    import sqlite3
    h = Harness()
    try:
        h.setup().create()
        database = h.sandbox / 'runtime/runtime.sqlite'
        if kind == 'missing':
            database.unlink()
        elif kind == 'corrupt':
            database.write_bytes(b'SYNTHETIC invalid SQLite database')
        else:
            db = sqlite3.connect(database)
            try:
                if kind == 'version':
                    db.execute('UPDATE runtime_meta SET schema_version=999 WHERE id=1')
                else:
                    db.execute("UPDATE node_runs SET output_ref='[\"SYNTHETIC wrong stored type\"]'")
                db.commit()
            finally:
                db.close()
        assert h.call('snapshot', '--case-id', h.case, code=4)['code'] == 'STORAGE_INVALID'
        assert database.exists() == (kind != 'missing')
    finally:
        h.cleanup()


def test_same_process_host_init_releases_sqlite_handle():
    h = Harness()
    sys.path.insert(0, str(h.sandbox.parents[1] / 'src'))
    from runtime_core.synthetic_host import Host
    host = Host(h.sandbox)
    host.initialize()
    host.cleanup(h.sandbox / 'manifest.json')
    assert not h.sandbox.exists()


def test_junction_escape_and_cleanup_are_refused():
    import os
    h = Harness()
    linked = False
    target = None
    try:
        h.init()
        target = h.sandbox.parent / (h.sandbox.name + '-outside')
        target.mkdir()
        (target / 'keep.txt').write_text('owned synthetic target', encoding='utf-8')
        link = h.sandbox / 'requests/junction'
        if os.name == 'nt':
            p = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            assert p.returncode == 0, 'Cannot validate junction protection on this host'
        else:
            link.symlink_to(target, target_is_directory=True)
        linked = True
        assert h.call('register', '--request', str(link / 'keep.txt'), code=2)['code'] == 'SANDBOX_INVALID'
        assert h.call('host-cleanup', '--manifest', str(h.sandbox / 'manifest.json'), code=2)['code'] == 'SANDBOX_INVALID'
        assert (target / 'keep.txt').read_text() == 'owned synthetic target'
    finally:
        if linked:
            if os.name == 'nt':
                os.rmdir(link)
            else:
                link.unlink()
        if target is not None and target.exists():
            (target / 'keep.txt').unlink()
            target.rmdir()
        h.cleanup()


def test_real_elapsed_timeout_not_only_synthetic_clock():
    h = Harness()
    try:
        h.setup().create()
        start = time.monotonic()
        assert h.call('host-test', '--case-id', h.case, '--scenario', 'submit-elapsed', code=2)['code'] == 'LEASE_LOST'
        assert time.monotonic() - start >= 30
        assert h.call('snapshot', '--case-id', h.case)['result']['status'] == 'RUNNING'
    finally:
        h.cleanup()
