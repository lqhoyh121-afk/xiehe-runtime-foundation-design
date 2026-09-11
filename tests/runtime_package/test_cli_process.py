"""Real OS-process package intake tests; no in-memory restart claims. Laiqh."""
from pathlib import Path
import json
import runpy
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
fixture = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))


@pytest.mark.parametrize('damage', ['missing', 'failed', 'wrong_snapshot', 'wrong_root', 'before_export', 'missing_command', 'early_unlock'])
def test_r26_02_closure_requires_the_actual_ordered_cleanup_receipt(damage):
    from copy import deepcopy
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-receipt-selftest')
    root = audit.register(ROOT / '.local' / ('r26-receipt-' + uuid.uuid4().hex), purpose='owned receipt test')
    root.mkdir()
    (root / 'payload.bin').write_bytes(b'SYNTHETIC receipt binding')
    audit.remove_tree(root)
    assert audit.verify()['all_closed']
    original = deepcopy(audit.data)
    try:
        receipt = audit.data['cleanups'][0]
        if damage == 'missing':
            audit.data['cleanups'].clear()
        elif damage == 'failed':
            receipt['succeeded'] = False
        elif damage == 'wrong_snapshot':
            receipt['snapshot_id'] = 'missing-snapshot'
        elif damage == 'wrong_root':
            receipt['path'] = str(audit.path)
        elif damage == 'before_export':
            receipt['started_epoch'] = 0
        elif damage == 'missing_command':
            audit.data['commands'].clear()
        elif damage == 'early_unlock':
            snapshot = next(s for s in audit.data['snapshots'] if s['id'] == receipt['snapshot_id'])
            snapshot['cleanup_barrier']['released_epoch'] = receipt['started_epoch'] - 1
        with pytest.raises(AssertionError):
            audit.verify()
        assert audit.data['verification']['all_closed'] is False
    finally:
        audit.data = original
        audit.save()
        assert audit.verify()['all_closed']


@pytest.mark.parametrize('damage', ['sqlite_readback', 'sqlite_observer', 'preceding_snapshot'])
def test_r26_02_snapshot_evidence_must_bind_raw_archive_to_logical_readback(damage):
    from copy import deepcopy
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-snapshot-binding')
    root = audit.register(ROOT / '.local' / ('r26-snapshot-' + uuid.uuid4().hex), purpose='owned snapshot test')
    root.mkdir()
    db = sqlite3.connect(root / 'sample.sqlite')
    try:
        db.execute('CREATE TABLE sample(value TEXT)')
        db.execute("INSERT INTO sample VALUES ('SYNTHETIC archive binding')")
        db.commit()
    finally:
        db.close()
    audit.remove_tree(root)
    assert audit.verify()['all_closed']
    original = deepcopy(audit.data)
    try:
        snapshot = audit.data['snapshots'][-1]
        if damage == 'sqlite_readback':
            snapshot['sqlite_readback'] = {}
        elif damage == 'sqlite_observer':
            snapshot.pop('sqlite_observer')
        else:
            snapshot.pop('preceding_snapshot_id')
        with pytest.raises(AssertionError):
            audit.verify()
        assert audit.data['verification']['all_closed'] is False
    finally:
        audit.data = original
        audit.save()
        assert audit.verify()['all_closed']


@pytest.mark.parametrize('damage', ['exit', 'running', 'raw', 'pid', 'argv'])
def test_r26_02_cleanup_requires_a_bound_successful_observer(damage):
    from copy import deepcopy
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-observer-binding')
    root = audit.register(ROOT / '.local' / ('r26-observer-' + uuid.uuid4().hex), purpose='observer binding')
    root.mkdir()
    (root / 'payload.bin').write_bytes(b'SYNTHETIC observer binding')
    audit.remove_tree(root)
    original = deepcopy(audit.data)
    started = audit.data['cleanups'][0]['post_observation']['receipt']['started_epoch']

    def damage_all_copies(value):
        if isinstance(value, dict):
            if 'argv' in value and value.get('started_epoch') == started:
                if damage == 'exit':
                    value['exit_code'] = 99
                elif damage == 'running':
                    value['exited'] = False
                elif damage == 'raw':
                    value['stdout_raw_hex'] = ''
                elif damage == 'pid':
                    value['runtime_pid'] = -1
                else:
                    value['argv'][3] = 'print("not the path observer")'
            for child in value.values():
                damage_all_copies(child)
        elif isinstance(value, list):
            for child in value:
                damage_all_copies(child)

    try:
        damage_all_copies(audit.data)
        with pytest.raises(AssertionError):
            audit.verify()
    finally:
        audit.data = original
        audit.save()
        assert audit.verify()['all_closed']


def test_r26_02_cli_receipt_binds_entrypoint_manifest_digest_and_result():
    from copy import deepcopy
    g = fixture['Generated']()
    try:
        g.setup()
        g.cleanup()
        audit = g.audit
        original = deepcopy(audit.data)
        for damage in ('entrypoint', 'manifest', 'cleanup_digest', 'returned_manifest', 'returned_digest'):
            audit.data = deepcopy(original)
            receipt = next(row for row in audit.data['cleanups'] if row['kind'] == 'cli')
            command = receipt['command']
            if damage == 'entrypoint':
                command['argv'][2] = str(ROOT / 'tools/verify_runtime_package.py')
            elif damage == 'manifest':
                command['argv'][command['argv'].index('--manifest') + 1] = str(audit.path / 'wrong.json')
            elif damage == 'cleanup_digest':
                command['argv'][command['argv'].index('--cleanup-digest') + 1] = '0' * 64
            else:
                result = json.loads(command['stdout'])
                if damage == 'returned_manifest':
                    result['result']['cleanup_manifest']['files_sha256'] = {}
                else:
                    result['result']['cleanup_digest'] = '0' * 64
                command['stdout'] = json.dumps(result)
                command['stdout_raw_hex'] = command['stdout'].encode('utf-8').hex()
            with pytest.raises(AssertionError):
                audit.verify()
            assert audit.data['verification']['all_closed'] is False
        audit.data = original
        audit.save()
        assert audit.verify()['all_closed']
    finally:
        if g.root.exists():
            g.audit.remove_tree(g.root)


def test_r26_01_write_after_export_preserves_scene(monkeypatch):
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-01-export-gap')
    root = audit.register(ROOT / '.local' / ('r26-gap-' + uuid.uuid4().hex), purpose='owned SQLite race')
    root.mkdir()
    with sqlite3.connect(root / 'sample.sqlite') as db:
        db.execute('CREATE TABLE sample(value INTEGER)')
        db.execute('INSERT INTO sample VALUES (1)')
    db.close()
    export = audit.export
    calls = []

    def write_after_first_export(path):
        snapshot = export(path)
        if not calls:
            calls.append(snapshot['id'])
            command = audit.process([sys.executable, '-B', '-c',
                'import sqlite3,sys;db=sqlite3.connect(sys.argv[1]);db.execute("INSERT INTO sample VALUES (2)");db.commit();db.close()',
                root / 'sample.sqlite'])
            assert command['exit_code'] == 0
        return snapshot

    try:
        with monkeypatch.context() as patch:
            patch.setattr(audit, 'export', write_after_first_export)
            with pytest.raises(ValueError, match='SNAPSHOT_CHANGED_BEFORE_CLEANUP'):
                audit.remove_tree(root)
        assert root.exists() and not audit.data['cleanups']
        with sqlite3.connect(root / 'sample.sqlite') as db:
            assert db.execute('SELECT value FROM sample ORDER BY value').fetchall() == [(1,), (2,)]
        db.close()
        assert audit.data['snapshots'][0]['sqlite_readback']['sample.sqlite']['tables']['sample'] == [{'value': 1}]
    finally:
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']


@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
def test_r26_01_late_sqlite_writer_is_blocked_until_removal(journal):
    import shutil
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-01-late-writer')
    root = audit.register(ROOT / '.local' / ('r26-late-' + uuid.uuid4().hex), purpose='owned late writer')
    root.mkdir()
    with sqlite3.connect(root / 'sample.sqlite') as db:
        db.execute('PRAGMA journal_mode=' + journal)
        db.execute('CREATE TABLE sample(value INTEGER)')
        db.execute('INSERT INTO sample VALUES (1)')
    db.close()
    probe = '''import json,sqlite3,sys
db=None
try:
 db=sqlite3.connect(sys.argv[1],timeout=0)
 db.execute('INSERT INTO sample VALUES (?)',(int(sys.argv[2]),));db.commit()
 result={'blocked':False}
except sqlite3.OperationalError as exc:
 result={'blocked':True,'reason':str(exc)}
finally:
 if db is not None:db.close()
print(json.dumps(result))
'''
    # The same real process can write when no barrier is held.
    allowed = audit.process([sys.executable, '-B', '-c', probe, root / 'sample.sqlite', '2'])
    assert allowed['exit_code'] == 0 and json.loads(allowed['stdout'])['blocked'] is False

    try:
        with audit.cleanup_window(root) as snapshot:
            denied = audit.process([sys.executable, '-B', '-c', probe, root / 'sample.sqlite', '3'])
            assert denied['exit_code'] == 0 and json.loads(denied['stdout'])['blocked'] is True
            audit.cleanup_api(root, snapshot=snapshot)
        assert audit.verify()['all_closed']
        snapshot = audit.data['snapshots'][-1]
        assert snapshot['sqlite_readback']['sample.sqlite']['tables']['sample'] == [{'value': 1}, {'value': 2}]
    finally:
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']


@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
def test_r26_01_existing_sqlite_handle_fails_closed_or_is_guarded(journal):
    import os
    import shutil
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-01-existing-handle')
    root = audit.register(ROOT / '.local' / ('r26-existing-' + uuid.uuid4().hex), purpose='owned SQLite handle')
    root.mkdir()
    writer = sqlite3.connect(root / 'sample.sqlite')
    writer.execute('PRAGMA journal_mode=' + journal)
    writer.execute('CREATE TABLE sample(value INTEGER)')
    writer.commit()
    try:
        if os.name == 'nt':
            # SQLite's open handle does not grant delete sharing. The Windows
            # barrier must preserve the root rather than risk a write gap.
            with pytest.raises(OSError, match='CLEANUP_WRITE_BARRIER_BUSY'):
                audit.remove_tree(root)
            assert root.exists() and not audit.data['cleanups']
            assert audit.data['failures'][-1]['preserved'] is True
            writer.close()
            writer = None
            audit.remove_tree(root)
        else:
            # The already-open connection itself must be unable to write while
            # the audit's BEGIN IMMEDIATE barrier remains held through rmtree.
            with audit.cleanup_window(root) as snapshot:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    writer.execute('INSERT INTO sample VALUES (1)')
                    writer.commit()
                audit.cleanup_api(root, snapshot=snapshot)
            writer.close()
            writer = None
        assert audit.verify()['all_closed']
    finally:
        if writer is not None:
            writer.close()
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']


@pytest.mark.skipif(sys.platform == 'win32', reason='requires POSIX unlink semantics for a live WAL reader')
def test_r26_01_nonempty_wal_is_archived_and_read_back_before_removal():
    import sqlite3
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-01-nonempty-wal')
    root = audit.register(ROOT / '.local' / ('r26-wal-' + uuid.uuid4().hex), purpose='owned nonempty WAL')
    root.mkdir()
    writer = sqlite3.connect(root / 'sample.sqlite')
    reader = None
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('CREATE TABLE sample(value INTEGER)')
        writer.execute('INSERT INTO sample VALUES (1)')
        writer.commit()
        reader = sqlite3.connect(root / 'sample.sqlite')
        reader.execute('BEGIN')
        assert reader.execute('SELECT value FROM sample').fetchall() == [(1,)]
        writer.execute('INSERT INTO sample VALUES (2)')
        writer.commit()
        assert (root / 'sample.sqlite-wal').stat().st_size > 0
        writer.close()
        writer = None
        audit.remove_tree(root)
    finally:
        if reader is not None:
            reader.close()
        if writer is not None:
            writer.close()
        if root.exists():
            audit.remove_tree(root)
    snapshot = audit.data['snapshots'][-1]
    assert snapshot['files']['sample.sqlite-wal']['size'] > 0
    assert snapshot['sqlite_readback']['sample.sqlite']['tables']['sample'] == [{'value': 1}, {'value': 2}]
    assert audit.verify()['all_closed']


@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
def test_r26_01_direct_host_cleanup_blocks_writer_at_destruction(monkeypatch, journal):
    import shutil
    import sqlite3
    from runtime_core.package_host import PackageHost
    g = fixture['Generated']()
    class AtDestruction(Exception):
        pass
    probe = '''import json,sqlite3,sys
db=None
try:
 db=sqlite3.connect(sys.argv[1],timeout=0)
 db.execute('INSERT INTO r26_probe VALUES (2)');db.commit()
 print(json.dumps({'blocked':False}))
except sqlite3.OperationalError:
 print(json.dumps({'blocked':True}))
finally:
 if db is not None:db.close()
'''
    try:
        g.setup()
        db = sqlite3.connect(g.sandbox / 'runtime/runtime.sqlite')
        db.execute('PRAGMA journal_mode=' + journal)
        db.execute('CREATE TABLE r26_probe(value INTEGER)')
        db.commit()
        db.close()
        allowed = g.audit.process([sys.executable, '-B', '-c', probe, g.sandbox / 'runtime/runtime.sqlite'])
        assert allowed['exit_code'] == 0 and json.loads(allowed['stdout'])['blocked'] is False
        expected = fixture['digest'](fixture['hashes'](g.sandbox))['value']

        def before_delete(path):
            assert Path(path) == g.sandbox
            denied = g.audit.process([sys.executable, '-B', '-c', probe, g.sandbox / 'runtime/runtime.sqlite'])
            assert denied['exit_code'] == 0 and json.loads(denied['stdout'])['blocked'] is True
            raise AtDestruction()

        with monkeypatch.context() as patch:
            patch.setattr(shutil, 'rmtree', before_delete)
            with pytest.raises(AtDestruction):
                # No EvidenceRun barrier wraps this product API invocation.
                PackageHost(g.sandbox).cleanup(g.sandbox / 'manifest.json', expected)
        assert g.sandbox.exists()
    finally:
        g.cleanup()


@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
@pytest.mark.parametrize('readonly', [False, True])
def test_r26_01_direct_host_cleanup_preserves_active_reader(monkeypatch, journal, readonly):
    import shutil
    import sqlite3
    from runtime_core.package_host import PackageHost
    from runtime_core.contract_adapter import ContractError
    g = fixture['Generated']()
    reader = None
    try:
        g.setup()
        db_path = g.sandbox / 'runtime/runtime.sqlite'
        prepare = sqlite3.connect(db_path)
        prepare.execute('PRAGMA journal_mode=' + journal)
        prepare.close()
        reader = sqlite3.connect(db_path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True)
        reader.execute('BEGIN')
        reader.execute('SELECT name FROM sqlite_master').fetchall()
        before = sorted(str(p.relative_to(g.sandbox)) for p in g.sandbox.rglob('*'))
        with monkeypatch.context() as patch:
            patch.setattr(shutil, 'rmtree', lambda path: pytest.fail('destruction reached with a live SQLite reader'))
            with pytest.raises(ContractError) as blocked:
                PackageHost(g.sandbox).cleanup(g.sandbox / 'manifest.json')
            assert blocked.value.code == 'IN_PROGRESS'
        assert sorted(str(p.relative_to(g.sandbox)) for p in g.sandbox.rglob('*')) == before
    finally:
        if reader is not None:
            reader.close()
        g.cleanup()


def test_r26_01_host_cleanup_rechecks_the_archived_host_state():
    import os
    g = fixture['Generated']()
    try:
        g.setup()
        with g.before_cleanup() as snapshot:
            expected = g.audit.cleanup_digest(snapshot, g.sandbox)
            if os.name == 'nt':
                # The audit's Windows deny-write barrier blocks Host.control
                # before it can replace state.json. Preservation is the safe
                # outcome for this platform-specific overlap.
                denied = g.cli('host-control', '--scenario', 'input-alternate', expected=4)
                assert denied['code'] == 'STORAGE_INVALID'
                assert g.sandbox.exists()
                return
            controlled = g.cli('host-control', '--scenario', 'input-alternate')
            assert controlled['result']['scenario'] == 'input-alternate'
            rejected = g.run([sys.executable, '-B', ROOT / 'tools/runtime_package_cli.py',
                              '--sandbox', g.sandbox, 'host-cleanup', '--manifest', g.sandbox / 'manifest.json',
                              '--cleanup-digest', expected], expected=2)
            assert rejected['code'] == 'CLEANUP_SNAPSHOT_MISMATCH'
            assert g.sandbox.exists()
    finally:
        # A deliberately failed Windows control can leave its atomic-save temp
        # file behind. Archive that synthetic scene before removing it rather
        # than asking product cleanup to discard the unarchived residue.
        if g.root.exists():
            g.audit.remove_tree(g.root)
        assert g.audit.verify()['all_closed']


def test_r26_01_host_cleanup_requires_exact_snapshot_digest():
    with fixture['generated']() as g:
        g.setup()
        with g.before_cleanup() as snapshot:
            rejected = g.run([sys.executable, '-B', ROOT / 'tools/runtime_package_cli.py',
                              '--sandbox', g.sandbox, 'host-cleanup', '--manifest', g.sandbox / 'manifest.json',
                              '--cleanup-digest', '0' * 64], expected=2)
            assert rejected['code'] == 'CLEANUP_SNAPSHOT_MISMATCH'
            assert g.sandbox.exists()


def test_r26_02_api_cleanup_rejects_a_callback_that_did_not_remove_root():
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-api-postcondition')
    root = audit.register(ROOT / '.local' / ('r26-api-post-' + uuid.uuid4().hex), purpose='must actually remove root')
    root.mkdir()
    (root / 'payload.bin').write_bytes(b'SYNTHETIC postcondition')
    try:
        with pytest.raises(TypeError):
            audit.cleanup_api(root, lambda: None, 'shutil.rmtree', [root])
        assert root.exists() and not audit.data['cleanups']
    finally:
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']


@pytest.mark.parametrize('successful', [False, True])
def test_r26_02_late_install_cannot_close_a_previously_lost_root(successful):
    import shutil
    g = fixture['Generated']()
    try:
        g.ensure_runtime_roots()
        pending = g.sandbox.with_name(g.sandbox.name + '.pending')
        lost = pending if successful else g.sandbox
        lost.mkdir()
        (lost / 'lost-synthetic.txt').write_bytes(b'SYNTHETIC deliberately unrecorded content')
        shutil.rmtree(lost)  # Deliberately violate only this disposable test's lifecycle.
        g.audit.export(g.root)
        argv = [sys.executable, '-B', ROOT / 'tools/runtime_package_cli.py', '--sandbox', g.sandbox,
                'install', '--package', g.package, '--materials', g.materials, '--fixture', 'normalize-l3-v1']
        with pytest.raises(ValueError, match='CREATION_LIFECYCLE_ALREADY_STARTED'):
            g.audit.bind_creation([g.sandbox, pending], argv)
        env = dict(g.env)
        if not successful:
            env['WF2_INSTALL_FAULT'] = 'after_snapshot'
        command = g.audit.process(argv, env=env)
        assert command['exit_code'] == (0 if successful else 86)
        with pytest.raises(AssertionError):
            if successful:
                g.audit.record_activation(pending, g.sandbox, command)
            else:
                g.audit.record_failed_activation(pending, g.sandbox, command)
    finally:
        if g.root.exists():
            g.audit.remove_tree(g.root)
        with pytest.raises(AssertionError):
            g.audit.verify()
        assert not g.audit.data['verification']['all_closed']


def test_r26_02_rename_callback_cannot_masquerade_as_rmtree():
    import os
    import uuid
    enclosure = ROOT / '.local' / ('r26-rename-' + uuid.uuid4().hex)
    enclosure.mkdir()
    audit = fixture['EvidenceRun'](purpose='r26-rename-is-not-delete', owned_roots=[enclosure])
    root = audit.register(enclosure / 'root', purpose='must be deleted, not moved')
    root.mkdir()
    moved = enclosure / 'moved'
    try:
        with pytest.raises(TypeError):
            audit.cleanup_api(root, lambda: os.rename(root, moved), 'shutil.rmtree', [root])
        assert root.is_dir() and not moved.exists() and not audit.data['cleanups']
    finally:
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']
        if moved.exists():
            moved.rmdir()
        enclosure.rmdir()


def test_r26_02_idempotent_install_keeps_the_original_creation_proof():
    with fixture['generated']() as g:
        args = ('install', '--package', str(g.package), '--materials', str(g.materials), '--fixture', 'normalize-l3-v1')
        first = g.cli(*args)
        first_creator = next(r['creation_intent']['command']['started_epoch'] for r in g.audit.data['roots']
                             if r['path'] == str(g.sandbox))
        second = g.cli(*args)
        assert first['result'] == second['result'] and len(g.audit.data['transitions']) == 1
        assert g.audit.data['transitions'][0]['command']['started_epoch'] == first_creator


def test_r26_02_missing_child_needs_real_transition_evidence():
    import shutil
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-missing-child')
    root = audit.register(ROOT / '.local' / ('r26-parent-' + uuid.uuid4().hex), purpose='parent')
    child = audit.register(root / 'child', purpose='child', parent=root)
    root.mkdir()
    child.mkdir()
    (child / 'payload.bin').write_bytes(b'SYNTHETIC child evidence that must not disappear')
    # Simulate a prior unrecorded removal. Parent cleanup must not relabel this as
    # a harmless unused reservation merely because the child is gone at export.
    shutil.rmtree(child)
    audit.remove_tree(root)
    with pytest.raises(AssertionError):
        audit.verify()
    assert str(child) in audit.data['verification']['unclosed_roots']
    later = audit.process([sys.executable, '-B', ROOT / 'tools/verify_runtime_package.py',
        '--sandbox', child, '--report', audit.path / 'late.json', '--scenario', 'S02',
        '--evidence-dir', audit.path.parent])
    assert later['exit_code'] == 2
    with pytest.raises(AssertionError, match='INVALID_NONCREATION_PROOF'):
        audit.record_noncreation(child, later)
    with pytest.raises(AssertionError):
        audit.verify()
    assert str(child) in audit.data['verification']['unclosed_roots']


def test_r26_02_unused_reservation_needs_separate_evidence():
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-02-unused-reservation')
    root = ROOT / '.local' / ('r26-unused-' + uuid.uuid4().hex)
    argv = [sys.executable, '-B', ROOT / 'tools/verify_runtime_package.py',
        '--sandbox', root, '--report', audit.path / 'unused.json', '--scenario', 'S02',
        '--evidence-dir', audit.path.parent]
    audit.register(root, purpose='never created', creation_argv=argv)
    with pytest.raises(AssertionError):
        audit.verify()
    assert audit.data['verification']['all_closed'] is False
    command = audit.process(argv)
    audit.record_noncreation(root, command)
    assert audit.verify()['all_closed']
    assert audit.data['roots'][0]['state'] == 'reservation_closed'
    assert not audit.data['cleanups'] and not root.exists()


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


def test_r26_01_legacy_verifier_cleanup_without_export_still_works():
    import os
    import uuid
    audit = fixture['EvidenceRun'](purpose='r26-legacy-verifier-entry')
    root = audit.register(ROOT / '.local' / ('r26-legacy-verifier-' + uuid.uuid4().hex), purpose='legacy verifier owner')
    root.mkdir()
    try:
        result = audit.process([sys.executable, '-B', ROOT / 'tools/verify_runtime_package.py',
            '--sandbox', root / 'sandbox', '--report', root / 'report.json', '--scenario', 'S01'],
            env={**os.environ, 'WF2_REFERENCE_ROOT': str(fixture['REFERENCE']),
                 'WF2_TOOL_ROOT': str(fixture['TOOL_ROOT'])}, timeout=120)
        assert result['exit_code'] == 0, result
        report = fixture['read_json'](root / 'report.json')
        assert report['all_passed'] and report['covered'] == ['S01']
        assert report['generation_cleaned'] and all(target['cleaned'] for target in report['targets'])
    finally:
        if root.exists():
            audit.remove_tree(root)
        assert audit.verify()['all_closed']


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
    root = ROOT / '.local' / ('e01-unsupported-' + uuid.uuid4().hex)
    report = audit.path / 'must-not-exist.json'
    argv = [sys.executable, '-B', ROOT / 'tools/verify_runtime_package.py',
        '--sandbox', root, '--report', report, '--scenario', 'S02', '--evidence-dir', audit.path.parent]
    audit.register(root, purpose='must never be created', creation_argv=argv)
    result = audit.process(argv)
    assert result['exit_code'] == 2 and 'supports S01 only' in result['stderr']
    assert not root.exists() and not report.exists()
    audit.record_noncreation(root, result)
    assert audit.verify()['all_closed']


def test_e01_legacy_byte_constructor_and_both_raw_streams_still_work(monkeypatch):
    import uuid
    audit = fixture['EvidenceRun'](purpose='legacy-byte-compatibility')
    root = audit.register(ROOT / '.local' / ('e01-legacy-' + uuid.uuid4().hex), purpose='legacy constructor owner')
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
