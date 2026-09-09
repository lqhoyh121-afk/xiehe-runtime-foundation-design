import copy
import json
import sqlite3
from datetime import timedelta

import pytest

from input_contract import ContractError, ExcelSource, SQLiteSource, digest, load_snapshot
from snapshot_store import save_snapshot, read_snapshot
from test_contract import NOW, ROWS, prepare, save_excel, sources


@pytest.mark.parametrize('source_index', [0, 1], ids=['excel', 'sqlite'])
@pytest.mark.parametrize('field,value,code', [
    (0, None, 'RECORD_INVALID'),
    (0, 'DEMO-ASSET-Z', 'UNKNOWN_OBJECT'),
    (0, 'DEMO-ASSET-A ', 'RECORD_INVALID'),
    (1, 'bad', 'RECORD_INVALID'),
    (2, 'wrong-unit', 'RECORD_INVALID'),
    (3, '2030-01-01T11:59:00', 'TIMEZONE_REQUIRED'),
    (3, '2029-12-31T11:59:00+00:00', 'STALE_FACT'),
    (3, '2030-01-01T12:01:00+00:00', 'FUTURE_OBSERVATION'),
])
def test_reject_bad_facts(tmp_path, source_index, field, value, code):
    binding = prepare(tmp_path)
    rows = copy.deepcopy(ROWS)
    rows[0][field] = value
    if source_index == 0:
        save_excel(tmp_path / 'input.xlsx', rows)
    else:
        conn = sqlite3.connect(tmp_path / 'input.sqlite3')
        try:
            conn.execute('DELETE FROM observations')
            conn.executemany('INSERT INTO observations VALUES (?,?,?,?)', rows)
            conn.commit()
        finally:
            conn.close()
    with pytest.raises(ContractError) as err:
        load_snapshot(tmp_path / 'model.json', tmp_path / 'objects.json', sources(tmp_path)[source_index], binding['model_ref'], NOW)
    assert err.value.code == code


@pytest.mark.parametrize('source_index', [0, 1])
def test_duplicate_object_rejected(tmp_path, source_index):
    binding = prepare(tmp_path)
    save_excel(tmp_path / 'input.xlsx', [ROWS[0], ROWS[0]])
    conn = sqlite3.connect(tmp_path / 'input.sqlite3')
    try:
        conn.execute('UPDATE observations SET asset_code=?', ('DEMO-ASSET-A',))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ContractError, match='DUPLICATE_OBJECT'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[source_index], binding['model_ref'], NOW)


@pytest.mark.parametrize('source_index', [0, 1])
def test_empty_source_rejected(tmp_path, source_index):
    binding = prepare(tmp_path)
    save_excel(tmp_path/'input.xlsx', [])
    conn = sqlite3.connect(tmp_path/'input.sqlite3')
    try:
        conn.execute('DELETE FROM observations')
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ContractError, match='EMPTY_BATCH'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[source_index], binding['model_ref'], NOW)


def test_changed_model_cannot_use_old_binding(tmp_path):
    binding = prepare(tmp_path)
    model = json.loads((tmp_path/'model.json').read_text())
    model['record_schema']['required'].append('extra_fact')
    (tmp_path/'model.json').write_text(json.dumps(model), encoding='utf-8')
    with pytest.raises(ContractError, match='MODEL_BINDING_MISMATCH'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)


def test_new_version_is_not_silently_accepted(tmp_path):
    binding = prepare(tmp_path)
    model = json.loads((tmp_path/'model.json').read_text())
    model['version'] = '2.0.0'
    (tmp_path/'model.json').write_text(json.dumps(model), encoding='utf-8')
    ref = {'id': model['id'], 'version': model['version'], 'sha256': digest(model)}
    with pytest.raises(ContractError, match='UNSUPPORTED_MODEL_VERSION'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], ref, NOW)


def test_formula_is_not_a_verified_fact(tmp_path):
    binding = prepare(tmp_path)
    rows = copy.deepcopy(ROWS)
    rows[0][1] = '=2+3'
    save_excel(tmp_path/'input.xlsx', rows)
    with pytest.raises(ContractError, match='FORMULA_NOT_ALLOWED'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)


def test_missing_database_does_not_create_database(tmp_path):
    binding = prepare(tmp_path)
    source = SQLiteSource(tmp_path/'missing.sqlite3', 'observations', sources(tmp_path)[1].mapping)
    with pytest.raises(ContractError, match='SOURCE_READ_FAILED'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', source, binding['model_ref'], NOW)
    assert not source.path.exists()


def test_missing_column_not_interpreted_as_sql_literal(tmp_path):
    binding = prepare(tmp_path)
    mapping = dict(sources(tmp_path)[1].mapping, reading='absent')
    source = SQLiteSource(tmp_path/'input.sqlite3', 'observations', mapping)
    with pytest.raises(ContractError, match='MISSING_COLUMN'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', source, binding['model_ref'], NOW)


def test_snapshot_repeat_and_tamper_detection(tmp_path):
    binding = prepare(tmp_path)
    snapshot = load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)
    out = tmp_path/'snapshots'
    path = save_snapshot(snapshot, out)
    assert save_snapshot(snapshot, out) == path
    assert len(list(out.glob('*.json'))) == 1
    assert read_snapshot(path).to_dict() == snapshot.to_dict()
    clone = snapshot.to_dict()
    clone['records'][0]['reading'] = 999
    assert snapshot.to_dict()['records'][0]['reading'] == 5
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ContractError, match='SNAPSHOT_CORRUPT'):
        read_snapshot(path)
    with pytest.raises(ContractError, match='SNAPSHOT_CORRUPT'):
        save_snapshot(snapshot, out)


def test_revalidates_against_requested_clock(tmp_path):
    binding = prepare(tmp_path)
    with pytest.raises(ContractError, match='STALE_FACT'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW + timedelta(hours=1))
