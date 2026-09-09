"""Synthetic fixtures for CLI demonstration; never real business inputs."""
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from input_contract import canonical, digest

CLOCK = '2030-01-01T12:00:00+00:00'


def prepare_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    model = {
        'id': 'demo.observation', 'version': '1.0.0', 'max_age_seconds': 300,
        'record_schema': {
            'type': 'object', 'additionalProperties': False,
            'required': ['object_ref', 'reading', 'unit', 'observed_at'],
            'properties': {
                'object_ref': {'type': 'string', 'pattern': '^DEMO-ASSET-[A-Z]+$'},
                'reading': {'type': 'integer'}, 'unit': {'const': 'demo-unit'},
                'observed_at': {'type': 'string', 'format': 'date-time'},
            },
        },
    }
    binding = {'model_ref': {'id': model['id'], 'version': model['version'], 'sha256': digest(model)},
               'max_reading': 10, 'rule_id': 'demo.limit', 'rule_version': '1.0.0'}
    for name, value in {'model.json': model, 'business.json': binding,
                        'objects.json': ['DEMO-ASSET-A', 'DEMO-ASSET-B'],
                        'excel-mapping.json': {'object_ref': '对象编号', 'reading': '读数', 'unit': '单位', 'observed_at': '观测时间'},
                        'sqlite-mapping.json': {'object_ref': 'asset_code', 'reading': 'value', 'unit': 'units', 'observed_at': 'sampled'}}.items():
        with (directory/name).open('x', encoding='utf-8') as stream:
            stream.write(canonical(value))
    rows = [('DEMO-ASSET-A', 5, 'demo-unit', '2030-01-01T11:59:00+00:00'),
            ('DEMO-ASSET-B', 15, 'demo-unit', '2030-01-01T11:59:00+00:00')]
    book = Workbook()
    try:
        sheet = book.active
        sheet.title = 'Observations'
        sheet.append(['对象编号', '读数', '单位', '观测时间'])
        for row in rows:
            sheet.append(row)
        book.save(directory/'input.xlsx')
    finally:
        book.close()
    conn = sqlite3.connect(directory/'input.sqlite3')
    try:
        conn.execute('CREATE TABLE observations (asset_code TEXT, value INTEGER, units TEXT, sampled TEXT)')
        conn.executemany('INSERT INTO observations VALUES (?,?,?,?)', rows)
        conn.commit()
    finally:
        conn.close()
