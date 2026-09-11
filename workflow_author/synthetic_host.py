"""TEST ONLY, explicit isolated metadata host. Never a production authority. Laiqh."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from .authority_bridge import parse_json, shared
from .checker import check_package
from .contracts import VERSION, diagnostic, report
from .generator import create_files
from .safety import SafetyError, ensure_plain, snapshot
from .templates import json_text

SCOPE = {'tenant': 'synthetic-tenant', 'project': 'synthetic-project'}
TEST_ONLY = 'TEST ONLY: synthetic metadata, not permission, installation, runtime or production proof.'


def fixed_context():
    return shared().TrustedContext(deepcopy(SCOPE), 'deployment-a', datetime(2030, 1, 1, 12, tzinfo=timezone.utc), 4, True)


def _prepare_data():
    api = shared()
    records = []

    def publish(kind, ident, content, dependencies=()):
        ref = dict(kind=kind, namespace='synthetic', id=ident, version='1.0.0', digest=api.digest(content))
        records.append(dict(ref=ref, content=deepcopy(content), dependencies=deepcopy(list(dependencies)),
                            scope=deepcopy(SCOPE), status='ACTIVE', valid_from='2030-01-01T00:00:00Z', expires_at='2030-01-02T00:00:00Z'))
        return ref

    # Fixed WF0 §5.1 fixture. This is intentionally literal: no alternative example IDs/content.
    business = publish('business', 'wf0-static-normalize', {'test_only': True, 'purpose': 'normalize-ascii-space'})
    inp = publish('model', 'wf0-static-input', {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['text'], 'additionalProperties': False})
    out = publish('model', 'wf0-static-output', {'type': 'object', 'properties': {'normalized': {'type': 'string', 'minLength': 1, 'maxLength': 80}}, 'required': ['normalized'], 'additionalProperties': False})
    rule = publish('rule', 'wf0-static-rule', {'test_only': True, 'predicate': 'text contains at least one character other than U+0020'})
    providers = {}
    for role, ident in [('NodeExecutor', 'wf0-static-executor'), ('DataProvider', 'wf0-static-data'), ('ContractValidator', 'wf0-static-validator'), ('RuleProvider', 'wf0-static-rule-provider')]:
        providers[role] = publish('provider', ident, dict(role=role, contract_version='0.1-draft', execution_kind='CODE' if role == 'NodeExecutor' else None, capabilities=['synthetic-capability']))
    deps = [business, inp, out, rule, *providers.values()]
    node = dict(node_id='normalize', depends_on=[], execution_kind='CODE', executor_ref=providers['NodeExecutor'],
                input_contract_ref=inp, output_contract_ref=out, rule_ref=rule, data_provider_ref=providers['DataProvider'],
                validator_ref=providers['ContractValidator'], rule_provider_ref=providers['RuleProvider'],
                wait_spec_ref=None, verification_spec_ref=None, readback_provider_ref=None, action_adapter_ref=None,
                resources=[], timeout_seconds=30, retry_policy={'max_attempts': 1, 'backoff_seconds': 0}, completion='OUTPUT_VALIDATED')
    projection = dict(contract_version='0.1-draft', status='DRAFT', scope=deepcopy(SCOPE), business_ref=business,
                      dependencies=deps, provider_bindings=list(providers.values()), nodes=[node], terminal_nodes=['normalize'])
    projection['definition_ref'] = publish('runtime', 'wf0-static-runtime', deepcopy(projection), deps)
    return {'material_version': VERSION, 'test_only': True, 'records': records}, projection


def prepare(output):
    materials, projection = _prepare_data()
    result = create_files(output, {'authority-records.json': json_text(materials),
                         'workflow-projection.json': json_text(projection),
                         'README.md': '# Synthetic materials / Laiqh\n' + TEST_ONLY + '\n'}, operation='prepare')
    result['limitations'].append(TEST_ONLY)
    result['synthetic_only'] = True
    return result


class Reader:
    """Read-only supplied record index. This class grants no rights."""
    def __init__(self, records):
        self._records = deepcopy(records)

    def lookup(self, kind, reference, context):
        return deepcopy(self._records.get((kind, shared().key(reference))))

    def current(self, kind, key, context):
        raise shared().AuthorityUnavailable()


def read_materials(root):
    api = shared()
    files = snapshot(root)
    if not {'authority-records.json', 'workflow-projection.json'} <= files.keys():
        raise api.ContractError('AUTHORITY_UNAVAILABLE')
    materials = parse_json(files['authority-records.json'])
    if not isinstance(materials, dict) or set(materials) != {'material_version', 'test_only', 'records'} or materials['material_version'] != VERSION or materials['test_only'] is not True:
        raise api.ContractError('SCHEMA_INVALID')
    rows = materials['records']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
        raise api.ContractError('SCHEMA_INVALID')
    records = {}
    context = fixed_context()  # Fixed TEST ONLY host code, not deserialized caller claims.
    for row in rows:
        api.shape('DefinitionRecord', row)
        api.live(row, context)
        if row['ref']['namespace'] != 'synthetic':
            raise api.ContractError('SCOPE_MISMATCH')
        if api.digest(row['content']) != row['ref']['digest']:
            raise api.ContractError('VERSION_DIGEST_MISMATCH')
        key = ('provider' if row['ref']['kind'] == 'provider' else 'definition', api.key(row['ref']))
        if key in records:
            raise api.ContractError('DUPLICATE_AUTHORITY_RECORD')
        records[key] = row
    reader = Reader(records)
    projection = parse_json(files['workflow-projection.json'])
    api.validate_projection(projection, reader, context)
    return reader, context


def check_synthetic(package, materials):
    # First discover certain package errors. Missing material must not mask them.
    local = check_package(package)
    if local['status'] != 'INCOMPLETE':
        local['limitations'].append(TEST_ONLY)
        local['synthetic_only'] = True
        return local
    api = shared()
    try:
        package_path, material_path = ensure_plain(package), ensure_plain(materials)
        if package_path == material_path or package_path in material_path.parents or material_path in package_path.parents:
            raise api.ContractError('MATERIALS_NOT_SEPARATE')
        reader, context = read_materials(material_path)
        result = check_package(package, authority=reader, context=context)
    except api.ContractError as exc:
        status = 'INCOMPLETE' if exc.code in ('AUTHORITY_UNAVAILABLE', 'TRUST_CONTEXT_REQUIRED') else 'REJECTED'
        result = report('check', status, diagnostics=[diagnostic('AUTH-REF-002', source_code=exc.code, phase='authority')])
    except (SafetyError, OSError) as exc:
        code = exc.code if isinstance(exc, SafetyError) else 'AUTHORITY_UNAVAILABLE'
        status = 'INCOMPLETE' if code in ('PACKAGE_UNAVAILABLE', 'INPUT_UNAVAILABLE', 'AUTHORITY_UNAVAILABLE') else 'REJECTED'
        result = report('check', status, diagnostics=[diagnostic('AUTH-REF-002', source_code=code, phase='authority')])
    result['limitations'].append(TEST_ONLY)
    result['synthetic_only'] = True
    return result
