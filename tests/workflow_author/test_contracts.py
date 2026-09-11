"""WF0 author-owned keys, independently enumerated; not imported from contracts."""
import json
import pytest
from conftest import put_json
from workflow_author.checker import check_package
from workflow_author.synthetic_host import check_synthetic

MANIFEST_KEYS = ('author_contract_version', 'package_id', 'author_version', 'candidate_state', 'projection_file',
                 'static_profile', 'required_core_capabilities', 'component_files', 'acceptance_file')
COMPONENT_KEYS = ('component_id', 'author_version', 'node_id', 'purpose', 'non_goals', 'implementation_file',
                  'test_files', 'implementation_state', 'allowed_helpers', 'permissions', 'side_effects',
                  'failure_notes', 'completion_evidence_note')


@pytest.mark.parametrize('kind,key', [('manifest', k) for k in MANIFEST_KEYS] + [('component', k) for k in COMPONENT_KEYS])
@pytest.mark.parametrize('mutation', ['missing', 'null', 'wrong-type'])
def test_each_author_key_is_required_and_typed(completed, kind, key, mutation):
    package, materials = completed
    file = package / ('package-manifest.json' if kind == 'manifest' else 'components/normalize-submission/declaration.json')
    obj = json.loads(file.read_text(encoding='utf-8'))
    if mutation == 'missing':
        del obj[key]
    else:
        obj[key] = None if mutation == 'null' else 42
    put_json(file, obj)
    result = check_package(package)
    assert result['status'] == 'REJECTED', result
    assert any(d['id'] == 'AUTH-REQ-001' for d in result['diagnostics'])


@pytest.mark.parametrize('key,value', [('package_id', ''), ('author_version', '1.*'), ('author_version', 'latest'),
                                     ('author_contract_version', '0.2.0'), ('static_profile', 'future'),
                                     ('component_files', []), ('component_files', ['components/normalize-submission/declaration.json'] * 2),
                                     ('required_core_capabilities', []), ('candidate_state', 'activated')])
def test_manifest_invalid_values_are_rejected(completed, key, value):
    package, _ = completed
    file = package / 'package-manifest.json'
    obj = json.loads(file.read_text(encoding='utf-8')); obj[key] = value; put_json(file, obj)
    assert check_package(package)['status'] == 'REJECTED'


@pytest.mark.parametrize('key,value', [('purpose', ''), ('purpose', '   '), ('non_goals', []), ('non_goals', ['x', 'x']),
                                     ('permissions', []), ('permissions', [{}]), ('allowed_helpers', ['missing.py']),
                                     ('node_id', 'other-node'), ('component_id', 'other-component'),
                                     ('failure_notes', {}), ('completion_evidence_note', ''),
                                     ('side_effects', {'category': 'none', 'intent_note': 'hidden write', 'idempotency_note': None, 'readback_note': None})])
def test_component_invalid_values_are_rejected(completed, key, value):
    package, _ = completed
    file = package / 'components/normalize-submission/declaration.json'
    obj = json.loads(file.read_text(encoding='utf-8')); obj[key] = value; put_json(file, obj)
    assert check_package(package)['status'] == 'REJECTED'


@pytest.mark.parametrize('filename', ['package-manifest.json', 'components/normalize-submission/declaration.json'])
@pytest.mark.parametrize('key', ['extra', 'approved', 'auth_context', 'module_path'])
def test_unknown_and_self_authorization_fields_reject(completed, filename, key):
    package, _ = completed
    obj = json.loads((package / filename).read_text(encoding='utf-8')); obj[key] = True
    put_json(package / filename, obj)
    assert check_package(package)['status'] == 'REJECTED'


def test_legal_explicit_none_and_empty_helpers_are_accepted(completed):
    package, materials = completed
    assert check_synthetic(package, materials)['status'] == 'PASSED'


@pytest.mark.parametrize('filename', ['acceptance.md', 'components/normalize-submission/test_normalize.py'])
def test_empty_required_author_content_cannot_pass(completed, filename):
    package, materials = completed
    if filename == 'acceptance.md':
        text = '# Empty acceptance\n' + '\n'.join('## ' + s for s in ['输入', '独立预期', '检查子集', '材料来源', '人工/运行未验证项', '待决表达'])
    else:
        text = 'def test_fake():\n    pass\n'
    (package / filename).write_text(text, encoding='utf-8')
    assert check_synthetic(package, materials)['status'] != 'PASSED'
