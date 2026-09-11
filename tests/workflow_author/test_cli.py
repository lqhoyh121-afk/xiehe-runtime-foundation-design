"""Real process reports and usage errors; fixed public contract."""
import json
import subprocess
import sys
import pytest
from conftest import ROOT, cli, hashes

REPORT_KEYS = {'report_version', 'tool_version', 'template_version', 'rules_version', 'operation', 'status',
               'profile', 'checks', 'diagnostics', 'limitations', 'runtime_verified', 'production_authorized'}
DIAGNOSTIC_KEYS = {'id', 'source_code', 'severity', 'file', 'pointer', 'line', 'column', 'message', 'remediation', 'phase'}


@pytest.mark.parametrize('args', [[], ['unknown'], ['init'], ['check'], ['check', '--package', 'absent', '--grant', 'yes'],
                                 ['check', '--package', 'absent', '--format', 'xml'],
                                 ['init', '--template', 'single-code-output-v1', '--output', 'x', '--module-path', 'evil']])
def test_usage_returns_safe_one_json(args):
    p, result = cli(*args)
    assert p.returncode == 64 and result['status'] == 'USAGE_ERROR'
    assert p.stderr == '' and set(result) == REPORT_KEYS
    assert all(set(d) == DIAGNOSTIC_KEYS for d in result['diagnostics'])


def test_json_and_text_match_exit_semantics_from_other_cwd(completed, tmp_path):
    package, materials = completed
    p, report = cli('check', '--package', package, '--materials', materials, '--format', 'json', synthetic=True, cwd=tmp_path)
    assert p.returncode == 0 and report['status'] == 'PASSED'
    assert set(report) == REPORT_KEYS | {'synthetic_only'}
    assert report['synthetic_only'] is True
    assert {report[k] for k in ['report_version', 'tool_version', 'template_version', 'rules_version']} == {'0.1.0'}
    text = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/workflow_author_synthetic.py'), 'check', '--package', str(package),
                           '--materials', str(materials), '--format', 'text'], cwd=tmp_path, capture_output=True, text=True)
    assert text.returncode == 0 and 'PASSED' in text.stdout and 'runtime_verified=false' in text.stdout
    assert not text.stderr


def test_untrusted_cwd_module_is_not_imported(completed, tmp_path):
    package, _ = completed
    marker = tmp_path / 'imported'
    (tmp_path / 'validator.py').write_text('open(' + repr(str(marker)) + ', "w").write("bad")', encoding='utf-8')
    p, r = cli('check', '--package', package, cwd=tmp_path)
    assert p.returncode == 4 and not marker.exists()


def test_unknown_profile_has_explicit_rejection_without_creating_target(tmp_path):
    path = tmp_path / 'not-created'
    p, r = cli('init', '--template', 'waiting-loop', '--output', path)
    assert p.returncode == 3 and r['status'] == 'REJECTED' and not path.exists()


def test_unexpected_error_is_sanitized_and_has_exit_1(tmp_path, monkeypatch, capsys):
    from workflow_author import generator
    from workflow_author.cli import main

    def broken(*args):
        raise RuntimeError('secret-host-error-value')

    monkeypatch.setattr(generator, 'generate', broken)
    # WF1-TASK §4 explicitly assigns INTERNAL_ERROR=1; do not invent sysexits=70.
    assert main(['init', '--template', 'single-code-output-v1', '--output', str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert 'secret-host-error-value' not in captured.out + captured.err
    assert json.loads(captured.out)['status'] == 'INTERNAL_ERROR'


def test_text_rejection_preserves_semantics(draft):
    p = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/workflow_author.py'), 'check', '--package', str(draft),
                        '--format', 'text'], capture_output=True, text=True)
    assert p.returncode == 2 and 'DRAFT' in p.stdout and 'AUTH-DRAFT-011' in p.stdout


def test_text_diagnostic_matches_json_safe_location_source_and_remediation(completed):
    package, materials = completed
    path = package / 'components/normalize-submission/declaration.json'
    data = json.loads(path.read_text(encoding='utf-8')); data['permissions'] = []
    path.write_text(json.dumps(data), encoding='utf-8')
    json_process, report = cli('check', '--package', package, '--materials', materials, synthetic=True)
    text_process = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/workflow_author_synthetic.py'), 'check', '--package', str(package), '--materials', str(materials), '--format', 'text'], capture_output=True, text=True)
    expected = next(d for d in report['diagnostics'] if d['file'] == 'components/normalize-submission/declaration.json' and d['pointer'] == '/permissions')
    assert json_process.returncode == text_process.returncode == 3
    for value in [expected['id'], expected['file'], expected['pointer'], expected['message'], expected['remediation']]:
        assert value in text_process.stdout
    assert 'AUTH-REQ-001' in text_process.stdout
    assert 'C:\\Users\\' not in text_process.stdout and 'Traceback' not in text_process.stdout


def test_text_bottom_level_reference_keeps_source_code_and_location(completed):
    package, materials = completed
    projection = package / 'definitions/workflow-projection.json'
    data = json.loads(projection.read_text(encoding='utf-8'))
    data['nodes'][0]['executor_ref']['kind'] = 'model'
    projection.write_text(json.dumps(data), encoding='utf-8')
    _, report = cli('check', '--package', package, '--materials', materials, synthetic=True)
    process = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/workflow_author_synthetic.py'), 'check', '--package', str(package), '--materials', str(materials), '--format', 'text'], capture_output=True, text=True)
    expected = next(d for d in report['diagnostics'] if d['source_code'] == 'PROVIDER_KIND_MISMATCH')
    assert process.returncode == 3
    for value in [expected['id'], expected['source_code'], expected['file'], expected['message'], expected['remediation']]:
        assert value in process.stdout


def test_abbreviated_options_are_not_a_second_cli_grammar(tmp_path):
    p, result = cli('init', '--templ', 'single-code-output-v1', '--out', tmp_path / 'abbreviated')
    assert p.returncode == 64 and result['status'] == 'USAGE_ERROR'
