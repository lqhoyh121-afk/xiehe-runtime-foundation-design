"""Synthetic, local-only contract tests. No production identities or systems."""
import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pytest

from input_contract import ExcelSource, SQLiteSource, load_snapshot
from business import evaluate

NOW = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)  # explicit synthetic clock
ROWS = [
    ['DEMO-ASSET-A', 5, 'demo-unit', '2030-01-01T11:59:00+00:00'],
    ['DEMO-ASSET-B', 15, 'demo-unit', '2030-01-01T11:59:00+00:00'],
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    model = {
        'id': 'demo.observation', 'version': '1.0.0', 'max_age_seconds': 300,
        'record_schema': {
            'type': 'object', 'additionalProperties': False,
            'required': ['object_ref', 'reading', 'unit', 'observed_at'],
            'properties': {
                'object_ref': {'type': 'string', 'pattern': '^DEMO-ASSET-[A-Z]+$'},
                'reading': {'type': 'integer'},
                'unit': {'const': 'demo-unit'},
                'observed_at': {'type': 'string', 'format': 'date-time'},
            },
        },
    }
    (root / 'model.json').write_text(canonical(model), encoding='utf-8')
    (root / 'objects.json').write_text(canonical(['DEMO-ASSET-A', 'DEMO-ASSET-B']), encoding='utf-8')
    ref = {'id': model['id'], 'version': model['version'], 'sha256': hashlib.sha256(canonical(model).encode()).hexdigest()}
    binding = {'model_ref': ref, 'max_reading': 10, 'rule_id': 'demo.limit', 'rule_version': '1.0.0'}
    (root / 'business.json').write_text(canonical(binding), encoding='utf-8')
    save_excel(root / 'input.xlsx', ROWS)
    conn = sqlite3.connect(root / 'input.sqlite3')
    try:
        conn.execute('CREATE TABLE observations (asset_code TEXT, value INTEGER, units TEXT, sampled TEXT)')
        conn.executemany('INSERT INTO observations VALUES (?,?,?,?)', ROWS)
        conn.commit()
    finally:
        conn.close()
    return binding


def save_excel(path, rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = 'Observations'
    sheet.append(['对象编号', '读数', '单位', '观测时间'])
    for row in rows:
        sheet.append(row)
    book.save(path)
    book.close()


def sources(root):
    return [
        ExcelSource(root / 'input.xlsx', 'Observations', {'object_ref': '对象编号', 'reading': '读数', 'unit': '单位', 'observed_at': '观测时间'}),
        SQLiteSource(root / 'input.sqlite3', 'observations', {'object_ref': 'asset_code', 'reading': 'value', 'unit': 'units', 'observed_at': 'sampled'}),
    ]


def test_source_switch_without_business_change(tmp_path):
    binding = prepare(tmp_path)
    snapshots = [load_snapshot(tmp_path / 'model.json', tmp_path / 'objects.json', source, binding['model_ref'], NOW) for source in sources(tmp_path)]
    expected = [
        {'object_ref': 'DEMO-ASSET-A', 'verdict': 'WITHIN_LIMIT'},
        {'object_ref': 'DEMO-ASSET-B', 'verdict': 'OVER_LIMIT'},
    ]
    assert [evaluate(s, binding)['decisions'] for s in snapshots] == [expected, expected]
    assert snapshots[0].semantic_digest == snapshots[1].semantic_digest
    assert snapshots[0].snapshot_id != snapshots[1].snapshot_id
    assert {s.to_dict()['source']['kind'] for s in snapshots} == {'excel', 'sqlite'}
