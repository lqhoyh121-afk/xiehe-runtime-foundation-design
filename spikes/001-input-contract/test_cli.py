"""CLI and portability regressions, all against disposable synthetic inputs."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo_fixtures import CLOCK, prepare_demo
from input_contract import ContractError, load_snapshot, timestamp
from test_contract import NOW, prepare, sources

ROOT = Path(__file__).resolve().parent


def test_datetime_does_not_depend_on_optional_format_extras():
    with pytest.raises(ContractError, match='INVALID_TIME'):
        timestamp('2030-01-01 11:59:00+00:00')


def test_cli_rejects_stale_without_output(tmp_path):
    fixtures = tmp_path/'输入 数据'
    prepare_demo(fixtures)
    output = tmp_path/'result'
    args = [sys.executable, '-B', str(ROOT/'cli.py'), '--source', 'excel',
            '--input', str(fixtures/'input.xlsx'), '--model', str(fixtures/'model.json'),
            '--objects', str(fixtures/'objects.json'), '--binding', str(fixtures/'business.json'),
            '--mapping', str(fixtures/'excel-mapping.json'), '--collection', 'Observations',
            '--as-of', '2030-01-01T13:00:00+00:00', '--output', str(output)]
    result = subprocess.run(args, text=True, capture_output=True, encoding='utf-8', timeout=30,
                            env=dict(os.environ, PYTHONUTF8='1'))
    assert result.returncode == 2
    assert json.loads(result.stdout)['code'] == 'STALE_FACT'
    assert not output.exists()


def test_cli_demo_refuses_existing_output(tmp_path):
    result = subprocess.run([sys.executable, '-B', str(ROOT/'demo.py'), '--output-dir', str(tmp_path)],
                            text=True, capture_output=True, encoding='utf-8', timeout=30,
                            env=dict(os.environ, PYTHONUTF8='1'))
    assert result.returncode == 2
    assert not (tmp_path/'fixtures').exists()


def test_invalid_model_shape_is_structured_failure(tmp_path):
    binding = prepare(tmp_path)
    model = json.loads((tmp_path/'model.json').read_text())
    model['record_schema'] = True
    from input_contract import digest
    binding['model_ref']['sha256'] = digest(model)
    (tmp_path/'model.json').write_text(json.dumps(model), encoding='utf-8')
    with pytest.raises(ContractError, match='MODEL_INVALID'):
        load_snapshot(tmp_path/'model.json', tmp_path/'objects.json', sources(tmp_path)[0], binding['model_ref'], NOW)
