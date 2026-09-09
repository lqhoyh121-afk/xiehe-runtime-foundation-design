"""The fixed observation model rejects unsupported property descriptors."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo_fixtures import CLOCK, prepare_demo
from input_contract import (ContractError, SQLiteSource, canonical, digest,
                            load_snapshot, read_json, timestamp)

ROOT = Path(__file__).resolve().parent


def boolean_model(fixtures, descriptor, field='reading'):
    prepare_demo(fixtures)
    model = read_json(fixtures / 'model.json')
    model['record_schema']['properties'][field] = descriptor
    (fixtures / 'model.json').write_text(canonical(model), encoding='utf-8')
    binding = read_json(fixtures / 'business.json')
    binding['model_ref']['sha256'] = digest(model)
    (fixtures / 'business.json').write_text(canonical(binding), encoding='utf-8')
    return binding


@pytest.mark.parametrize('field', ['reading', 'unit', 'observed_at', 'object_ref'])
@pytest.mark.parametrize('descriptor', [True, False])
def test_boolean_property_model_rejected_before_source_read(tmp_path, field, descriptor):
    fixtures = tmp_path / 'model'
    binding = boolean_model(fixtures, descriptor, field)
    # A missing source establishes that model rejection precedes reading data.
    source = SQLiteSource(tmp_path / 'missing.sqlite3', 'observations',
                          read_json(fixtures / 'sqlite-mapping.json'))
    with pytest.raises(ContractError, match='MODEL_INVALID'):
        load_snapshot(fixtures / 'model.json', fixtures / 'objects.json', source,
                      binding['model_ref'], timestamp(CLOCK))
    assert not source.path.exists()


@pytest.mark.parametrize('source', ['excel', 'sqlite'])
@pytest.mark.parametrize('descriptor', [True, False])
def test_cli_boolean_property_has_structured_rejection(tmp_path, source, descriptor):
    fixtures = tmp_path / '合成模型 inputs'
    boolean_model(fixtures, descriptor)
    before = {p.name: p.read_bytes() for p in fixtures.iterdir()}
    output = tmp_path / 'result'
    result = subprocess.run([
        sys.executable, '-B', str(ROOT / 'cli.py'), '--source', source,
        '--input', str(fixtures / ('input.xlsx' if source == 'excel' else 'input.sqlite3')),
        '--model', str(fixtures / 'model.json'), '--objects', str(fixtures / 'objects.json'),
        '--binding', str(fixtures / 'business.json'),
        '--mapping', str(fixtures / (source + '-mapping.json')),
        '--collection', 'Observations' if source == 'excel' else 'observations',
        '--as-of', CLOCK, '--output', str(output),
    ], capture_output=True, text=True, encoding='utf-8', timeout=30,
        env=dict(os.environ, PYTHONUTF8='1'))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)['code'] == 'MODEL_INVALID'
    assert 'Traceback' not in result.stderr
    assert not output.exists()
    assert {p.name: p.read_bytes() for p in fixtures.iterdir()} == before
