"""Explicit synthetic material host is not a fallback or production authority."""
import json
from copy import deepcopy
import hashlib
import pytest
from jsonschema import Draft202012Validator
from conftest import cli, hashes, put_json
from workflow_author.checker import check_package
from workflow_author.synthetic_host import check_synthetic, read_materials


# WF0 §5.1 fixed public fixture. Do not derive from author-tool constants/prepare output.
WF0_CONTENT = {
    ('business', 'wf0-static-normalize'): {'test_only': True, 'purpose': 'normalize-ascii-space'},
    ('model', 'wf0-static-input'): {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['text'], 'additionalProperties': False},
    ('model', 'wf0-static-output'): {'type': 'object', 'properties': {'normalized': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['normalized'], 'additionalProperties': False},
    ('rule', 'wf0-static-rule'): {'test_only': True, 'predicate': 'text contains at least one character other than U+0020'},
    ('provider', 'wf0-static-executor'): {'role': 'NodeExecutor', 'contract_version': '0.1-draft', 'execution_kind': 'CODE', 'capabilities': ['synthetic-capability']},
    ('provider', 'wf0-static-data'): {'role': 'DataProvider', 'contract_version': '0.1-draft', 'execution_kind': None, 'capabilities': ['synthetic-capability']},
    ('provider', 'wf0-static-validator'): {'role': 'ContractValidator', 'contract_version': '0.1-draft', 'execution_kind': None, 'capabilities': ['synthetic-capability']},
    ('provider', 'wf0-static-rule-provider'): {'role': 'RuleProvider', 'contract_version': '0.1-draft', 'execution_kind': None, 'capabilities': ['synthetic-capability']},
}


def test_prepare_exactly_restores_wf0_fixed_records_and_model_rule_boundaries(tmp_path):
    materials = tmp_path / 'materials'
    p, result = cli('prepare', '--output', materials, synthetic=True)
    assert p.returncode == 0 and result['status'] == 'CREATED'
    rows = json.loads((materials / 'authority-records.json').read_text(encoding='utf-8'))['records']
    non_runtime = {(row['ref']['kind'], row['ref']['id']): row for row in rows if row['ref']['kind'] != 'runtime'}
    assert set(non_runtime) == set(WF0_CONTENT)
    for key, content in WF0_CONTENT.items():
        row = non_runtime[key]
        assert row['content'] == content
        assert row['dependencies'] == []
        assert row['ref']['namespace'] == 'synthetic' and row['ref']['version'] == '1.0.0'
        assert row['scope'] == {'tenant': 'synthetic-tenant', 'project': 'synthetic-project'}
        assert row['status'] == 'ACTIVE' and row['valid_from'] == '2030-01-01T00:00:00Z' and row['expires_at'] == '2030-01-02T00:00:00Z'
    runtime = [row for row in rows if row['ref']['kind'] == 'runtime']
    assert len(runtime) == 1 and runtime[0]['ref']['id'] == 'wf0-static-runtime'
    assert len(runtime[0]['dependencies']) == 8
    projection = json.loads((materials / 'workflow-projection.json').read_text(encoding='utf-8'))
    assert projection['business_ref']['id'] == 'wf0-static-normalize'
    assert [ref['id'] for ref in projection['dependencies']] == ['wf0-static-normalize', 'wf0-static-input', 'wf0-static-output', 'wf0-static-rule', 'wf0-static-executor', 'wf0-static-data', 'wf0-static-validator', 'wf0-static-rule-provider']
    input_model = WF0_CONTENT[('model', 'wf0-static-input')]
    output_model = WF0_CONTENT[('model', 'wf0-static-output')]
    for value, valid in [({}, False), ({'text': ''}, False), ({'text': 'a'}, True), ({'text': 'x' * 80}, True), ({'text': 'x' * 81}, False)]:
        assert Draft202012Validator(input_model).is_valid(value) is valid
    for value, valid in [({}, False), ({'normalized': ''}, False), ({'normalized': 'a'}, True), ({'normalized': 'x' * 80}, True), ({'normalized': 'x' * 81}, False)]:
        assert Draft202012Validator(output_model).is_valid(value) is valid
    assert any(char != ' ' for char in ' a ') and not any(char != ' ' for char in '   ')


def test_prepare_is_explicit_nonoverwriting_and_materials_are_not_in_package(tmp_path, draft):
    materials = tmp_path / 'materials'
    before = hashes(draft)
    p, r = cli('prepare', '--output', materials, synthetic=True)
    assert p.returncode == 0 and r['status'] == 'CREATED'
    assert r['runtime_verified'] is False and r['production_authorized'] is False
    assert r['synthetic_only'] is True
    assert (materials / 'authority-records.json').is_file()
    assert hashes(draft) == before
    mb = hashes(materials)
    p, r = cli('prepare', '--output', materials, synthetic=True)
    assert p.returncode == 5 and r['status'] == 'CONFLICT'
    assert hashes(materials) == mb


def test_missing_materials_cannot_trigger_prepare(tmp_path, draft):
    missing = tmp_path / 'no-materials'
    before = hashes(draft)
    p, r = cli('check', '--package', draft, '--materials', missing, synthetic=True)
    # Known draft wins over material unavailability.
    assert p.returncode == 2 and r['status'] == 'DRAFT'
    assert not missing.exists() and hashes(draft) == before


def test_complete_candidate_passes_only_explicit_host_and_remains_readonly(completed):
    package, materials = completed
    before = hashes(package), hashes(materials)
    for _ in range(2):
        p, result = cli('check', '--package', package, '--materials', materials, synthetic=True)
        assert p.returncode == 0 and result['status'] == 'PASSED', result
        assert result['synthetic_only'] is True
        assert result['runtime_verified'] is False and result['production_authorized'] is False
        p, result = cli('check', '--package', package)
        assert p.returncode == 4 and result['status'] == 'INCOMPLETE'
    assert before == (hashes(package), hashes(materials))


@pytest.mark.parametrize('change,expected,code', [
    ('missing-file', 'INCOMPLETE', 'AUTHORITY_UNAVAILABLE'),
    ('missing-record', 'REJECTED', 'DEPENDENCY_UNAVAILABLE'),
    ('duplicate-record', 'REJECTED', 'DUPLICATE_AUTHORITY_RECORD'),
    ('bad-digest', 'REJECTED', 'VERSION_DIGEST_MISMATCH'),
    ('expired', 'REJECTED', 'EXPIRED'),
    ('revoked', 'REJECTED', 'REVOKED'),
    ('bad-scope', 'REJECTED', 'SCOPE_MISMATCH'),
    ('extra-trust', 'REJECTED', 'SCHEMA_INVALID'),
])
def test_material_failures_do_not_repair_or_issue_anything(completed, change, expected, code):
    package, materials = completed
    path = materials / 'authority-records.json'
    m = json.loads(path.read_text(encoding='utf-8'))
    if change == 'missing-file':
        path.unlink()
    else:
        if change == 'missing-record':
            m['records'].pop(0)
        elif change == 'duplicate-record':
            m['records'].append(deepcopy(m['records'][0]))
        elif change == 'bad-digest':
            m['records'][0]['ref']['digest']['value'] = '0' * 64
        elif change == 'expired':
            m['records'][0]['expires_at'] = '2030-01-01T01:00:00Z'
        elif change == 'revoked':
            m['records'][0]['status'] = 'REVOKED'
        elif change == 'bad-scope':
            m['records'][0]['scope']['tenant'] = 'other'
        else:
            m['approved'] = True
        put_json(path, m)
    before = hashes(package), hashes(materials)
    p, result = cli('check', '--package', package, '--materials', materials, synthetic=True)
    assert result['status'] == expected and p.returncode == (4 if expected == 'INCOMPLETE' else 3)
    assert any(d['source_code'] == code for d in result['diagnostics']), result
    assert before == (hashes(package), hashes(materials))


def test_keyword_only_public_host_and_unavailable_reader(completed):
    package, materials = completed
    reader, context = read_materials(materials)
    assert check_package(package, authority=reader, context=context)['status'] == 'PASSED'
    assert check_package(package, authority=reader, context={})['status'] == 'INCOMPLETE'

    class Offline:
        def lookup(self, *args):
            from workflow_author.authority_bridge import shared
            raise shared().AuthorityUnavailable()

    result = check_package(package, authority=Offline(), context=context)
    assert result['status'] == 'INCOMPLETE'
    assert any(d['source_code'] == 'AUTHORITY_UNAVAILABLE' for d in result['diagnostics'])


@pytest.mark.parametrize('field,value,code', [('role', 'DataProvider', 'PROVIDER_ROLE_MISMATCH'),
                                           ('execution_kind', 'AI', 'PROVIDER_EXECUTION_KIND_MISMATCH')])
def test_real_published_provider_wrong_role_or_execution_rejected(completed, field, value, code):
    package, materials = completed
    records_path = materials / 'authority-records.json'
    projection_path = materials / 'workflow-projection.json'
    m = json.loads(records_path.read_text(encoding='utf-8'))
    p = json.loads(projection_path.read_text(encoding='utf-8'))

    def digest(value):
        return {'algorithm': 'sha256', 'canonicalization': 'json-sort-utf8-int-v1',
                'value': hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()}

    row = next(r for r in m['records'] if r['ref']['id'] == 'wf0-static-executor')
    old = deepcopy(row['ref']); row['content'][field] = value
    new = dict(old, digest=digest(row['content']))

    def replace_ref(obj):
        if obj == old:
            return deepcopy(new)
        if isinstance(obj, dict):
            return {k: replace_ref(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [replace_ref(v) for v in obj]
        return obj

    m, p = replace_ref(m), replace_ref(p)
    runtime = next(r for r in m['records'] if r['ref']['kind'] == 'runtime')
    runtime['content'] = {k: v for k, v in p.items() if k != 'definition_ref'}
    runtime['dependencies'] = deepcopy(p['dependencies'])
    runtime['ref']['digest'] = digest(runtime['content']); p['definition_ref'] = deepcopy(runtime['ref'])
    put_json(records_path, m); put_json(projection_path, p)
    put_json(package / 'definitions/workflow-projection.json', p)
    result = check_synthetic(package, materials)
    assert result['status'] == 'REJECTED'
    assert any(d['source_code'] == code for d in result['diagnostics']), result
