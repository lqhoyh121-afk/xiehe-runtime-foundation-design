"""Real OS-process package intake tests; no in-memory restart claims. Laiqh."""
from pathlib import Path
import json
import runpy
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
fixture = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))


def test_f01_reference_binding_never_reads_default(monkeypatch):
    """Exercise the original exact-source test, rejecting a default-path fallback."""
    default = ROOT / '.local/reference/l3/package/components/normalize-submission/implementation.py'
    original_read = Path.read_bytes

    def bound_read(path):
        if fixture['REFERENCE'].resolve() != (ROOT / '.local/reference').resolve():
            assert path != default, 'F01: ignored the bound nondefault WF2_REFERENCE_ROOT'
        return original_read(path)

    monkeypatch.setattr(Path, 'read_bytes', bound_read)
    original_test = runpy.run_path(str(Path(__file__).with_name('test_execution.py')))
    original_test['test_component_executes_exact_reviewed_source_bytes']()


def test_e01_archive_precedes_real_removal_and_independent_readback():
    import sqlite3
    import uuid
    evidence = fixture['EvidenceRun'](purpose='export-selftest')
    root = ROOT / '.local' / ('e01-selftest-' + uuid.uuid4().hex)
    evidence.register(root, purpose='synthetic SQLite export selftest')
    root.mkdir()
    (root / 'payload.bin').write_bytes(b'SYNTHETIC archive content')
    db = sqlite3.connect(root / 'sample.sqlite')
    db.execute('CREATE TABLE sample(value TEXT)')
    db.execute("INSERT INTO sample VALUES ('before cleanup')")
    db.commit()
    db.close()
    evidence.remove_tree(root)
    ledger = fixture['read_json'](evidence.path / 'ledger.json')
    assert not root.exists() and ledger['roots'][0]['state'] == 'cleaned'
    snapshot = ledger['snapshots'][0]
    assert snapshot['files']['payload.bin']['sha256'] == fixture['sha256_bytes'](b'SYNTHETIC archive content')
    assert snapshot['sqlite_readback']['sample.sqlite']['tables']['sample'] == [{'value': 'before cleanup'}]
    assert ledger['cleanups'][0]['kind'] == 'api'
    assert ledger['cleanups'][0]['method'] == 'shutil.rmtree'
    assert ledger['cleanups'][0]['returned'] is None
    assert ledger['observations'][-1]['result']['roots'][str(root)]['absent']
    assert evidence.verify()['all_closed']


def test_e01_generated_cleanup_captures_identity_and_raw_cli():
    assert hasattr(fixture['Generated'], 'before_cleanup'), 'E01: generated cleanup has no pre-delete export'
    with fixture['generated']() as g:
        g.setup()
        evidence = g.audit
        root = g.root
    ledger = fixture['read_json'](evidence.path / 'ledger.json')
    first = ledger['snapshots'][0]
    assert 'sandbox/host/installation.json' in first['files']
    assert 'sandbox/manifest.json' in first['files']
    assert 'sandbox/runtime/runtime.sqlite' in first['files']
    assert 'sandbox/runtime/runtime.sqlite' in first['sqlite_readback']
    cli_cleanup = next(c for c in ledger['cleanups'] if c['kind'] == 'cli')
    assert cli_cleanup['command']['exit_code'] == 0
    assert cli_cleanup['command']['launcher_pid'] > 0
    assert bytes.fromhex(cli_cleanup['command']['stdout_raw_hex']).decode('utf-8') == cli_cleanup['command']['stdout']
    assert evidence.verify()['all_closed'] and not root.exists()


def test_e01_verifier_has_explicit_bounded_export():
    import inspect
    module = runpy.run_path(str(ROOT / 'tools/verify_runtime_package.py'))
    assert 'evidence_dir' in inspect.signature(module['Acceptance']).parameters, 'E01: verifier cannot export before cleanup'


def test_e01_rejects_evidence_inside_cleanup_tree_before_creation():
    import uuid
    root = ROOT / '.local' / ('e01-nested-' + uuid.uuid4().hex)
    with pytest.raises(ValueError, match='EVIDENCE_INSIDE_CLEANUP_TREE'):
        fixture['EvidenceRun'](evidence_dir=root / 'evidence', owned_roots=[root])
    assert not root.exists()


def test_e01_duplicate_run_id_never_overwrites_prior_evidence():
    import uuid
    first = fixture['EvidenceRun'](run_id='duplicate-' + uuid.uuid4().hex, purpose='exclusive-run-id')
    before = (first.path / 'ledger.json').read_bytes()
    with pytest.raises(FileExistsError):
        fixture['EvidenceRun'](evidence_dir=first.path.parent, run_id=first.run_id)
    assert (first.path / 'ledger.json').read_bytes() == before
    assert first.verify()['all_closed']


def test_e01_export_failure_preserves_scene_before_any_delete(monkeypatch):
    import uuid
    import zipfile
    audit = fixture['EvidenceRun'](purpose='export-failure-selftest')
    root = audit.register(ROOT / '.local' / ('e01-io-' + uuid.uuid4().hex), purpose='owned export failure')
    root.mkdir()
    (root / 'payload.bin').write_bytes(b'SYNTHETIC keep on export failure')
    original = fixture['hashes'](root)
    with monkeypatch.context() as patch:
        def fail_write(*args, **kwargs):
            raise OSError('SYNTHETIC archive I/O failure')
        patch.setattr(zipfile.ZipFile, 'writestr', fail_write)
        with pytest.raises(OSError, match='archive I/O failure'):
            audit.remove_tree(root)
    assert fixture['hashes'](root) == original and not audit.data['cleanups']
    assert audit.data['failures'][-1]['preserved']
    audit.remove_tree(root)
    assert audit.verify()['all_closed']


def test_e01_active_sqlite_writer_blocks_export_and_delete():
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='active-writer-selftest')
    root = audit.register(ROOT / '.local' / ('e01-writer-' + uuid.uuid4().hex), purpose='owned SQLite writer')
    root.mkdir()
    db = sqlite3.connect(root / 'writer.sqlite')
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE sample(value INTEGER)')
        db.execute('INSERT INTO sample VALUES (1)')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO sample VALUES (2)')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            audit.remove_tree(root)
        assert root.exists() and not audit.data['cleanups']
        assert db.execute('SELECT count(*) FROM sample').fetchone()[0] == 2
    finally:
        db.rollback()
        db.close()
    audit.remove_tree(root)
    assert audit.verify()['all_closed']


def test_e01_inconsistent_snapshot_blocks_delete(monkeypatch):
    import uuid
    audit = fixture['EvidenceRun'](purpose='inconsistent-snapshot-selftest')
    root = audit.register(ROOT / '.local' / ('e01-drift-' + uuid.uuid4().hex), purpose='owned changing snapshot')
    root.mkdir()
    sentinel = root / 'payload.bin'
    sentinel.write_bytes(b'before')
    inventory = audit._inventory
    calls = []
    with monkeypatch.context() as patch:
        def mutate_before_second_read(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                sentinel.write_bytes(b'changed during export')
            return inventory(*args, **kwargs)
        patch.setattr(audit, '_inventory', mutate_before_second_read)
        with pytest.raises(AssertionError, match='SNAPSHOT_CHANGED_DURING_EXPORT'):
            audit.remove_tree(root)
    assert sentinel.read_bytes() == b'changed during export' and not audit.data['cleanups']
    audit.remove_tree(root)
    assert audit.verify()['all_closed']


def test_e01_unsupported_cli_export_rejects_before_any_root():
    import uuid
    audit = fixture['EvidenceRun'](purpose='unsupported-export-selftest')
    root = audit.register(ROOT / '.local' / ('e01-unsupported-' + uuid.uuid4().hex), purpose='must never be created')
    report = audit.path / 'must-not-exist.json'
    result = audit.process([sys.executable, '-B', ROOT / 'tools/verify_runtime_package.py',
        '--sandbox', root, '--report', report, '--scenario', 'S02', '--evidence-dir', audit.path.parent])
    assert result['exit_code'] == 2 and 'supports S01 only' in result['stderr']
    assert not root.exists() and not report.exists()
    assert audit.verify()['all_closed']


def test_e01_legacy_byte_constructor_and_both_raw_streams_still_work(monkeypatch):
    import uuid
    audit = fixture['EvidenceRun'](purpose='legacy-byte-compatibility')
    root = audit.register(ROOT / '.local' / ('e01-legacy-' + uuid.uuid4().hex), purpose='legacy constructor owner')
    audit.register(root / 'sandbox', purpose='legacy byte sandbox', parent=root)
    root.mkdir()
    module = runpy.run_path(str(ROOT / 'tools/verify_runtime_package.py'))
    monkeypatch.setenv('WF2_REFERENCE_ROOT', str(fixture['REFERENCE']))
    monkeypatch.setenv('WF2_TOOL_ROOT', str(fixture['TOOL_ROOT']))
    verifier = module['Acceptance'](root / 'sandbox', root / 'report.json')
    assert verifier.audit is None
    result = verifier.command([sys.executable, '-B', '-c',
        'import os;os.write(1,bytes([0xb4]));os.write(2,bytes([0xd0]))'], parse=False, kind='fixture')
    assert result['stdout_raw_hex'] == 'b4' and result['stderr_raw_hex'] == 'd0'
    assert result['exit_code'] == 0 and result['exited']
    audit.data['commands'].extend(verifier.commands)
    audit.save()
    audit.remove_tree(root)
    assert audit.verify()['all_closed']


def test_cli_full_chain_real_code_and_fresh_readback():
    assert (ROOT / 'tools/runtime_package_cli.py').is_file(), 'Package CLI is missing'
    with fixture['generated']() as g:
        g.setup()
        created = g.request('create', g.create_payload, key='create-original')
        case_id = created['result']['case_id']
        run = g.cli('run-once', '--case-id', case_id)
        snapshot = g.cli('snapshot', '--case-id', case_id)
        events = g.cli('events', '--case-id', case_id)
        assert run['pid'] != snapshot['pid'] and g.commands[-3]['exited']
        assert snapshot['result']['nodes'][0]['output'] == {'normalized': 'SYNTHETIC  sample'}
        assert [x['type'] for x in events['result']['items']] == [
            'CASE_CREATED', 'NODE_READY', 'NODE_LEASED', 'NODE_STARTED', 'NODE_SUCCEEDED', 'CASE_SUCCEEDED']
        assert [x['case_revision'] for x in events['result']['items']] == [1, 1, 2, 2, 3, 3]
        replay = g.request('create', g.create_payload, key='create-original')
        assert replay['replayed'] and replay['result'] == created['result']
        assert replay['result']['status'] == 'QUEUED'
        inspected = g.cli('install-inspect')['result']
        assert inspected['installation']['installation_id'] == g.initial['installation_id']
        assert len(inspected['executions']) == 1
        assert inspected['executions'][0]['pid'] == run['pid']
        assert inspected['executions'][0]['case_id'] == case_id


def test_cli_rule_denial_has_no_attempt_or_executor():
    with fixture['generated']() as g:
        g.setup()
        controlled = g.cli('host-control', '--scenario', 'input-spaces')['result']
        g.create_payload['input_ref'] = controlled['input_ref']
        case = g.request('create', g.create_payload)['result']['case_id']
        denied = g.cli('run-once', '--case-id', case, expected=2)
        assert denied['code'] == 'RULE_DENIED'
        inspected = g.cli('install-inspect')['result']
        assert inspected['executions'] == []
        assert all(x['provider'] != 'executor_ref' for x in inspected['calls'])
        snap = g.cli('snapshot', '--case-id', case)['result']
        assert snap['status'] == 'QUEUED' and 'attempt' not in snap['nodes'][0]


def test_install_interruption_never_exposes_partial_activation():
    with fixture['generated']() as g:
        g.env['WF2_INSTALL_FAULT'] = 'before_activate'
        g.cli('install', '--package', str(g.package), '--materials', str(g.materials),
              '--fixture', 'normalize-l3-v1', expected=86)
        assert not g.sandbox.exists()
        pending = g.sandbox.with_name('sandbox.pending')
        assert pending.is_dir()
        denied = g.cli('install-inspect', expected=2)
        assert denied['code'] == 'HOST_BINDING_MISMATCH'


def test_model_valid_wrong_output_is_not_accepted_by_core():
    with fixture['generated']() as g:
        g.setup()
        case = g.request('create', g.create_payload)['result']['case_id']
        denied = g.cli('host-test', '--case-id', case, '--scenario', 'submit-output-mismatch', expected=2)
        assert denied['code'] == 'CONTRACT_INVALID'
        snap = g.cli('snapshot', '--case-id', case)['result']
        assert snap['status'] == 'RUNNING' and snap['revision'] == 2
        assert snap['nodes'][0]['output_ref'] is None


@pytest.mark.parametrize('scenario,code,exit_code', [('publish-unbound', 'PROVIDER_NOT_BOUND', 2),
                                                    ('reader-unavailable', 'AUTHORITY_UNAVAILABLE', 3)])
def test_core_preserves_provider_and_reader_error_codes(scenario, code, exit_code):
    with fixture['generated']() as g:
        initial = g.cli('install', '--package', str(g.package), '--materials', str(g.materials),
                        '--fixture', 'normalize-l3-v1')['result']
        g.cli('host-control', '--scenario', scenario)
        request = str(g.sandbox / 'requests/register-variant.json') if scenario.startswith('publish-') else initial['register_request']
        denied = g.cli('register', '--request', request, expected=exit_code)
        assert denied['code'] == code


def test_independent_verifier_normal_scenario_is_real_process_only():
    with fixture['generated']() as g:
        report = g.root / 'verifier-report.json'
        result = g.run([sys.executable, '-B', str(ROOT / 'tools/verify_runtime_package.py'),
                        '--sandbox', str(g.root / 'verify'), '--scenario', 'S01', '--report', str(report),
                        '--evidence-dir', str(g.audit.path.parent)])
        saved = json.loads(report.read_text())
        assert result['all_passed'] and saved['covered'] == ['S01']
        assert saved['scenario_count'] == 1 and saved['cli_count'] > 0 and saved['observer_count'] > 0
        assert saved['owned_processes_exited'] and saved['generation_cleaned']
        child = fixture['read_json'](saved['evidence_ledger'])
        assert child['verification']['all_closed']
        g.audit.data['children'].append({'ledger': saved['evidence_ledger'], 'run_id': child['run_id']})
        g.audit.save()


def test_verifier_preserves_non_utf8_process_output(monkeypatch):
    import importlib.util
    import uuid
    spec = importlib.util.spec_from_file_location('byte_capture_verifier', ROOT / 'tools/verify_runtime_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('WF2_REFERENCE_ROOT', str(fixture['REFERENCE']))
    monkeypatch.setenv('WF2_TOOL_ROOT', str(fixture['TOOL_ROOT']))
    owned = ROOT / '.local' / ('capture-bytes-' + uuid.uuid4().hex)
    import os
    verifier = module.Acceptance(owned / 'sandbox', owned / 'report.json',
        evidence_dir=os.environ.get('WF2_EVIDENCE_DIR', ROOT / '.local/engineering-evidence/runs'), evidence_scenario='bytes')
    result = verifier.command([sys.executable, '-B', '-c',
        'import os;os.write(1,bytes([0xb4]));os.write(2,bytes([0xd0]))'], kind='fixture', parse=False)
    assert result['stdout_raw_hex'] == 'b4' and result['stderr_raw_hex'] == 'd0'
    assert result['stdout'] == '\ufffd' and result['stderr'] == '\ufffd'
    assert result['exit_code'] == 0 and result['exited']
    assert json.loads((owned / 'report.json').read_text(encoding='utf-8'))['commands'][-1]['stdout_raw_hex'] == 'b4'
    assert verifier.reference == fixture['REFERENCE'] and verifier.tools == fixture['TOOL_ROOT']
    assert verifier.finish_byte_evidence()['all_closed']
