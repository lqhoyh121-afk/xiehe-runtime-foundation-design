import copy
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from input_contract import ContractError, load_snapshot, digest
from test_contract import NOW, ROWS, prepare, save_excel, sources


def test_duplicate_excel_header_is_not_guessed(tmp_path):
    binding = prepare(tmp_path)
    book = Workbook()
    try:
        book.active.title = 'Observations'
        book.active.append(['对象编号', '读数', '读数', '观测时间'])
        book.active.append(ROWS[0])
        book.save(tmp_path/'input.xlsx')
    finally:
        book.close()
    with pytest.raises(ContractError, match='DUPLICATE_HEADER'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)


def test_batch_limit_does_not_silently_truncate(tmp_path):
    binding = prepare(tmp_path)
    save_excel(tmp_path/'input.xlsx', [ROWS[0]] * 1001)
    with pytest.raises(ContractError, match='BATCH_TOO_LARGE'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)


def test_schema_cannot_fetch_external_references(tmp_path):
    binding = prepare(tmp_path)
    model = json.loads((tmp_path/'model.json').read_text())
    model['record_schema']['properties']['reading'] = {'$ref': 'https://invalid.example/schema'}
    (tmp_path/'model.json').write_text(json.dumps(model), encoding='utf-8')
    binding['model_ref']['sha256'] = digest(model)
    with pytest.raises(ContractError, match='SCHEMA_REF_NOT_SUPPORTED'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)


def test_mapping_must_cover_exact_contract_fields(tmp_path):
    binding = prepare(tmp_path)
    source = sources(tmp_path)[0]
    source.mapping.pop('unit')
    with pytest.raises(ContractError, match='MAPPING_MISMATCH'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', source, binding['model_ref'], NOW)
