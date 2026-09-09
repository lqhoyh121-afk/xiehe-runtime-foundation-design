"""R5 JSON error contracts through the public loader and real CLI.

Laiqh. Synthetic files only; integer limits are pinned in new processes,
never changed on the host interpreter.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from validator import ContractError, load_json

ROOT = Path(__file__).resolve().parent


def run_python(*args):
    return subprocess.run(
        [sys.executable, '-B', *args], cwd=ROOT,
        env={**os.environ, 'PYTHONINTMAXSTRDIGITS': '4300'},
        capture_output=True, text=True, encoding='utf-8', timeout=20,
    )


@pytest.mark.parametrize('sign', ['', '-'], ids=['positive', 'negative'])
def test_load_json_integer_limit_is_safe_contract_error(tmp_path, sign):
    path = tmp_path / 'oversized-integer.json'
    raw = ('{"generation":' + sign + '1' * 4301 + '}').encode('utf-8')
    path.write_bytes(raw)
    # Public load_json is exercised in a fresh interpreter so even a parent
    # configured with a different integer limit cannot hide the regression.
    result = run_python('-c', '''
import sys
from validator import ContractError, load_json
assert sys.get_int_max_str_digits() == 4300
try:
    load_json(sys.argv[1])
except ContractError as exc:
    assert exc.code == 'INPUT_INVALID'
    assert str(exc) == 'INPUT_INVALID'
    print(exc.code)
else:
    raise AssertionError('Oversized integer was accepted')
''', str(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'INPUT_INVALID'
    assert result.stderr == ''
    assert path.read_bytes() == raw


@pytest.mark.parametrize('sign', ['', '-'], ids=['positive', 'negative'])
def test_cli_integer_limit_returns_readonly_rejection(tmp_path, sign):
    path = tmp_path / 'oversized-integer.json'
    raw = ('{"generation":' + sign + '1' * 4301 + '}').encode('utf-8')
    path.write_bytes(raw)
    result = run_python(str(ROOT / 'cli.py'), '--demo', '--request', str(path))
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout) == {
        'verdict': 'REJECTED', 'code': 'INPUT_INVALID',
        'contract_status': 'DRAFT', 'synthetic_only': True,
        'production_authorized': False, 'migration_executed': False,
    }
    assert result.stderr == ''
    assert path.read_bytes() == raw


@pytest.mark.parametrize('raw,code', [
    pytest.param(b'{"a":1,"a":2}', 'DUPLICATE_JSON_KEY', id='duplicate'),
    pytest.param(b'{"a":{"b":1,"b":2}}', 'DUPLICATE_JSON_KEY', id='nested-duplicate'),
    pytest.param(b'{"a":NaN}', 'CANONICALIZATION_INVALID', id='nan'),
    pytest.param(b'{"a":Infinity}', 'CANONICALIZATION_INVALID', id='infinity'),
    pytest.param(b'{"a":-Infinity}', 'CANONICALIZATION_INVALID', id='negative-infinity'),
    pytest.param(b'{"a":1e400}', 'CANONICALIZATION_INVALID', id='float-overflow'),
    pytest.param(b'{"a":9007199254740992}', 'CANONICALIZATION_INVALID', id='unsafe-integer'),
    pytest.param(b'', 'INPUT_INVALID', id='empty'),
    pytest.param(b'{"a":', 'INPUT_INVALID', id='malformed'),
    pytest.param(b'\xff', 'INPUT_INVALID', id='invalid-utf8'),
    pytest.param(b'[' * 2000 + b'0' + b']' * 2000, 'INPUT_INVALID', id='too-deep'),
    pytest.param(b' ' * 2_000_001, 'INPUT_TOO_LARGE', id='too-large'),
])
@pytest.mark.parametrize('entry', ['loader', 'cli'])
def test_existing_json_errors_keep_specific_codes(tmp_path, raw, code, entry):
    path = tmp_path / 'request.json'
    path.write_bytes(raw)
    if entry == 'loader':
        with pytest.raises(ContractError) as exc:
            load_json(path)
        assert exc.value.code == code
        assert str(exc.value) == code
    else:
        result = run_python(str(ROOT / 'cli.py'), '--demo', '--request', str(path))
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout) == {
            'verdict': 'REJECTED', 'code': code,
            'contract_status': 'DRAFT', 'synthetic_only': True,
            'production_authorized': False, 'migration_executed': False,
        }
        assert result.stderr == ''
    assert path.read_bytes() == raw


def test_load_json_keeps_valid_canonical_values_readonly(tmp_path):
    path = tmp_path / 'request.json'
    raw = '{"min":-9007199254740991,"max":9007199254740991,"values":[null,true,"中文"]}'.encode('utf-8')
    path.write_bytes(raw)
    expected = {'min': -9007199254740991, 'max': 9007199254740991,
                'values': [None, True, '中文']}
    assert load_json(path) == expected
    assert load_json(path) == expected
    assert path.read_bytes() == raw


def test_missing_file_still_returns_input_invalid(tmp_path):
    path = tmp_path / 'missing.json'
    with pytest.raises(ContractError) as exc:
        load_json(path)
    assert exc.value.code == 'INPUT_INVALID'
    result = run_python(str(ROOT / 'cli.py'), '--demo', '--request', str(path))
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout) == {
        'verdict': 'REJECTED', 'code': 'INPUT_INVALID',
        'contract_status': 'DRAFT', 'synthetic_only': True,
        'production_authorized': False, 'migration_executed': False,
    }
    assert result.stderr == ''
    assert not path.exists()
