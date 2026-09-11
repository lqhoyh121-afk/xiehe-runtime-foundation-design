"""Check is read-only and does not disguise certain failures as missing authority."""
from pathlib import Path
from conftest import hashes, put_json, cli
from workflow_author.checker import check_package
import json
import pytest
from workflow_author.synthetic_host import check_synthetic


def test_generated_draft_is_nonzero_and_readonly(draft):
    before = hashes(draft)
    result = check_package(draft)
    assert result['status'] == 'DRAFT'
    p, r = cli('check', '--package', draft)
    assert p.returncode == 2 and r['status'] == 'DRAFT'
    assert hashes(draft) == before
    assert r['runtime_verified'] is False and r['production_authorized'] is False


def test_secret_in_unknown_file_is_rejected_not_draft(draft):
    secret = 'ghp_' + 'Z' * 36
    (draft / 'notes.txt').write_text(secret, encoding='utf-8')
    p, r = cli('check', '--package', draft)
    assert p.returncode == 3 and r['status'] == 'REJECTED'
    assert secret not in p.stdout + p.stderr
    assert str(draft) not in p.stdout + p.stderr


def test_check_never_imports_or_runs_component(draft, tmp_path):
    marker = tmp_path / 'must-not-exist'
    evil = 'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\n'
    (draft / 'components/normalize-submission/implementation.py').write_text(evil, encoding='utf-8')
    before = hashes(draft)
    p, r = cli('check', '--package', draft)
    assert r['status'] == 'REJECTED' and p.returncode == 3
    assert not marker.exists()
    assert hashes(draft) == before


@pytest.mark.parametrize('text', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1.5}', '{"x":' + '9' * 5000 + '}', '{bad'])
def test_all_json_uses_strict_bounded_parser(draft, text):
    (draft / 'extra.json').write_text(text, encoding='utf-8')
    result = check_package(draft)
    assert result['status'] == 'REJECTED'
    assert any(d['source_code'] in ('DUPLICATE_JSON_KEY', 'CANONICALIZATION_INVALID', 'INPUT_INVALID') for d in result['diagnostics'])


@pytest.mark.parametrize('field,value,code', [('rule_ref', 'input_contract_ref', 'SCHEMA_INVALID'), ('depends_on', ['ghost'], 'NODE_DEPENDENCY_MISSING'), ('depends_on', ['normalize'], 'NODE_CYCLE')])
def test_local_shared_errors_win_without_a_reader(completed, field, value, code):
    package, _ = completed
    p = package / 'definitions/workflow-projection.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    data['nodes'][0][field] = data['nodes'][0][value] if isinstance(value, str) else value
    put_json(p, data)
    result = check_package(package)
    assert result['status'] == 'REJECTED'
    assert any(d['source_code'] == code for d in result['diagnostics'])


@pytest.mark.parametrize('change,code', [('binding', 'PROVIDER_NOT_BOUND'), ('dependency', 'DEPENDENCY_NOT_DECLARED'), ('terminal', 'TERMINAL_NODES_INVALID')])
def test_local_binding_and_closure_errors_win_without_reader(completed, change, code):
    package, _ = completed
    path = package / 'definitions/workflow-projection.json'
    p = json.loads(path.read_text(encoding='utf-8'))
    if change == 'binding':
        p['provider_bindings'].remove(p['nodes'][0]['executor_ref'])
    elif change == 'dependency':
        p['dependencies'].remove(p['business_ref'])
    else:
        p['terminal_nodes'] = ['other']
    put_json(path, p)
    result = check_package(package)
    assert result['status'] == 'REJECTED', result
    assert any(d['source_code'] == code for d in result['diagnostics'])


# These are untrusted source strings for a non-executing scanner, never evaluated by tests.
@pytest.mark.parametrize('statement', ['import sibling\n', 'from components.other import run\n', 'import requests\n', 'import sqlite3\n', 'import subprocess\n', 'eval("1")\n', 'create_case()\n', 'workflow_cursor = 1\n'])
def test_undeclared_imports_and_private_state_are_rejected(completed, statement):
    package, materials = completed
    path = package / 'components/normalize-submission/implementation.py'
    path.write_text(statement + path.read_text(encoding='utf-8'), encoding='utf-8')
    result = check_synthetic(package, materials)
    assert result['status'] == 'REJECTED', result
    assert any(d['id'] == 'AUTH-BOUNDARY-006' for d in result['diagnostics'])


@pytest.mark.parametrize('change', ['multi', 'human', 'ai', 'retry', 'resources', 'readback', 'wait', 'ports', 'action'])
def test_unsupported_profile_rejects_without_runtime_simulation(completed, change):
    package, _ = completed
    path = package / 'definitions/workflow-projection.json'
    p = json.loads(path.read_text(encoding='utf-8')); n = p['nodes'][0]
    if change == 'multi':
        other = dict(n, node_id='next', depends_on=['normalize']); p['nodes'].append(other); p['terminal_nodes'] = ['next']
    elif change in ('human', 'ai'):
        n['execution_kind'] = change.upper()
    elif change == 'retry':
        n['retry_policy']['max_attempts'] = 2
    elif change == 'resources':
        n['resources'] = ['shared-resource']
    elif change == 'readback':
        n['completion'] = 'READBACK_VERIFIED'
    elif change == 'wait':
        n['wait_spec_ref'] = dict(n['rule_ref'], kind='wait')
    elif change == 'ports':
        (package / 'ports').mkdir(); (package / 'ports/input-port.json').write_text('{}')
    else:
        n['action_adapter_ref'] = n['executor_ref']
    put_json(path, p)
    assert check_package(package)['status'] == 'REJECTED'


def test_orphan_component_declaration_is_not_ignored(completed):
    package, _ = completed
    orphan = package / 'components/orphan/declaration.json'
    orphan.parent.mkdir()
    orphan.write_bytes((package / 'components/normalize-submission/declaration.json').read_bytes())
    assert check_package(package)['status'] == 'REJECTED'


def test_implemented_label_does_not_hide_empty_source(completed):
    package, materials = completed
    (package / 'components/normalize-submission/implementation.py').write_text('def normalize(value):\n    pass\n')
    assert check_synthetic(package, materials)['status'] == 'DRAFT'


@pytest.mark.parametrize('text', ['', 'def helper(value):\n    return dict(value)\n', 'def test_empty():\n    pass\n'])
def test_declared_test_file_without_collectable_test_cannot_pass(completed, text):
    package, materials = completed
    path = package / 'components/normalize-submission/test_normalize.py'
    path.write_text(text, encoding='utf-8')
    result = check_synthetic(package, materials)
    assert result['status'] != 'PASSED'
    assert any(d['file'] == 'components/normalize-submission/test_normalize.py' for d in result['diagnostics'])


def test_supported_class_test_entry_can_pass_without_execution(completed):
    package, materials = completed
    path = package / 'components/normalize-submission/test_normalize.py'
    path.write_text('''class TestNormalize:
    def test_result(self):
        assert {'normalized': 'x'} == {'normalized': 'x'}
''', encoding='utf-8')
    assert check_synthetic(package, materials)['status'] == 'PASSED'


def test_unrecognized_dynamic_test_collection_requires_manual_gate(completed):
    package, materials = completed
    path = package / 'components/normalize-submission/test_normalize.py'
    path.write_text("globals()['test_generated'] = lambda: True\n", encoding='utf-8')
    result = check_synthetic(package, materials)
    assert result['status'] != 'PASSED'
    assert any(d['file'] == 'components/normalize-submission/test_normalize.py' for d in result['diagnostics'])


def test_check_does_not_swallow_in_process_source_growth(draft, monkeypatch):
    import os
    original = os.open
    changed = False

    def grow(path, flags, *args, **kwargs):
        nonlocal changed
        if not changed and str(path).endswith('package-manifest.json'):
            changed = True
            Path(path).write_bytes(b'x' * 2_000_001)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', grow)
    result = check_package(draft)
    assert changed and result['status'] == 'REJECTED'
    assert any(d['source_code'] in ('INPUT_CHANGED', 'INPUT_TOO_LARGE') for d in result['diagnostics'])
