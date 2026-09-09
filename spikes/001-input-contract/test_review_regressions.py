"""Regression tests for independent review findings (synthetic files only)."""
import hashlib
import json
import sqlite3

import pytest

from business import evaluate
from input_contract import ContractError, load_snapshot, timestamp
from test_contract import NOW, ROWS, prepare, sources


def test_integer_schema_normalizes_integral_real_storage(tmp_path):
    binding = prepare(tmp_path)
    conn = sqlite3.connect(tmp_path/'input.sqlite3')
    try:
        conn.execute('DROP TABLE observations')
        conn.execute('CREATE TABLE observations (asset_code TEXT, value REAL, units TEXT, sampled TEXT)')
        conn.executemany('INSERT INTO observations VALUES (?,?,?,?)', ROWS)
        conn.commit()
    finally:
        conn.close()
    excel, sql = [load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', s, binding['model_ref'], NOW) for s in sources(tmp_path)]
    assert excel.semantic_digest == sql.semantic_digest
    assert type(sql.to_dict()['records'][0]['reading']) is int
    assert evaluate(excel, binding) == evaluate(sql, binding)


@pytest.mark.parametrize('value', ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00'])
def test_utc_overflow_is_a_contract_error(value):
    with pytest.raises(ContractError, match='INVALID_TIME'):
        timestamp(value)


def test_array_mapping_rejected_with_structured_error(tmp_path):
    binding = prepare(tmp_path)
    source = sources(tmp_path)[1]
    object.__setattr__(source, 'mapping', ['object_ref', 'reading', 'unit', 'observed_at'])
    with pytest.raises(ContractError, match='MAPPING_MISMATCH'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', source, binding['model_ref'], NOW)


@pytest.mark.parametrize('value', ['20300101T115900+0000', '2030-01-01T11:59:00+00:00:30'])
def test_non_rfc_timestamp_rejected(value):
    with pytest.raises(ContractError, match='INVALID_TIME'):
        timestamp(value)


def test_provenance_digest_scope_is_explicit(tmp_path):
    binding = prepare(tmp_path)
    excel, sql = [load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', s, binding['model_ref'], NOW).to_dict() for s in sources(tmp_path)]
    assert excel['source']['digest_scope'] == 'file_bytes'
    assert excel['source']['sha256'] == hashlib.sha256((tmp_path/'input.xlsx').read_bytes()).hexdigest()
    assert sql['source']['digest_scope'] == 'selected_rows'
