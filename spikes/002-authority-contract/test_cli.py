"""Real process/file boundary tests, disposable paths under this spike."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest
from migration_fixtures import migration_fixture

ROOT = Path(__file__).resolve().parent


def run_cli(*args):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'cli.py'), *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=20)


def test_demo_real_process_reports_normal_and_rejections():
    result = run_cli('--demo')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['contract_status'] == 'DRAFT'
    assert data['synthetic_only'] is True
    assert data['production_authorized'] is False
    assert data['migration_executed'] is False
    cases = {x['case']: x for x in data['cases']}
    assert cases['normal']['verdict'] == 'VALIDATED_LOCAL_ONLY'
    for name, code in {'old-right-active': 'SOURCE_GRANT_NOT_REVOKED', 'old-executor-running': 'SOURCE_EXECUTOR_NOT_STOPPED', 'stale-checkpoint': 'CHECKPOINT_STALE', 'missing-capability': 'TARGET_CAPABILITY_MISSING', 'unknown': 'MIGRATION_UNKNOWN'}.items():
        assert cases[name]['verdict'] == 'REJECTED'
        assert cases[name]['code'] == code


def test_file_input_readonly_repeat_and_non_demo_closed():
    with tempfile.TemporaryDirectory(prefix='ac3 中文 space ', dir=ROOT) as folder:
        path = Path(folder) / 'request.json'
        raw = json.dumps(migration_fixture().migration, ensure_ascii=False).encode('utf-8')
        path.write_bytes(raw)
        first = run_cli('--demo', '--request', str(path))
        second = run_cli('--demo', '--request', str(path))
        assert first.returncode == second.returncode == 0
        assert first.stdout == second.stdout
        assert json.loads(first.stdout)['verdict'] == 'VALIDATED_LOCAL_ONLY'
        closed = run_cli('--request', str(path))
        assert closed.returncode == 2
        assert json.loads(closed.stdout)['code'] == 'TRUSTED_ADAPTER_REQUIRED'
        assert path.read_bytes() == raw


@pytest.mark.parametrize('payload,code', [
    ('{"approved":true}', 'SCHEMA_INVALID'),
    ('{"approved":true,"approved":false}', 'DUPLICATE_JSON_KEY'),
    ('', 'INPUT_INVALID'),
    ('[]', 'SCHEMA_INVALID'),
    ('{"approved":NaN}', 'CANONICALIZATION_INVALID'),
])
def test_demo_file_rejections(payload, code):
    with tempfile.TemporaryDirectory(prefix='ac3-cli-', dir=ROOT) as folder:
        path = Path(folder) / 'request.json'
        path.write_text(payload, encoding='utf-8')
        result = run_cli('--demo', '--request', str(path))
        assert result.returncode == 2
        assert json.loads(result.stdout)['code'] == code
        assert path.read_text(encoding='utf-8') == payload


def test_non_demo_never_accepts_self_approval():
    with tempfile.TemporaryDirectory(prefix='ac3-cli-', dir=ROOT) as folder:
        path = Path(folder) / 'request.json'
        path.write_text('{"approved":true}', encoding='utf-8')
        result = run_cli('--request', str(path))
        assert result.returncode == 2
        assert json.loads(result.stdout)['code'] == 'TRUSTED_ADAPTER_REQUIRED'
