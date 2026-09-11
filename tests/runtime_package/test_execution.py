"""Single-node package behavior tests, never production permission. Laiqh."""
from pathlib import Path
import sys
import hashlib
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


def test_host_has_compatible_provider_dispatch():
    from runtime_core.synthetic_host import Host
    from runtime_core.synthetic_providers import Providers
    host = Host(ROOT / '.local/dispatch-only-no-files')
    assert callable(getattr(host, 'providers', None)), 'Host provider dispatch seam is missing'
    node = {'node_id': 'dispatch-test'}
    instance = host.providers(node)
    assert type(instance) is Providers
    assert instance.host is host and instance.node is node


def test_service_and_worker_use_host_dispatch():
    from runtime_core.synthetic_host import Host, ident
    from runtime_core.synthetic_providers import Providers
    from runtime_core.contract_adapter import load_json
    from runtime_core.service import Service
    from runtime_core.worker import Worker
    import runpy
    fixture = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))
    path = ROOT / '.local' / ident('test-package-dispatch')
    audit = fixture['EvidenceRun'](purpose='provider-dispatch-api', owned_roots=[path])
    audit.register(path, purpose='in-process synthetic Host')
    host = Host(path)
    initial = host.initialize()
    service = Service(host)
    calls = []

    def providers(node):
        calls.append(node['node_id'])
        return Providers(host, node)

    host.providers = providers
    request = lambda payload: {'request_id': ident('req'), 'idempotency_key': ident('key'), 'payload': payload}
    registered = service.execute('register', load_json(host.path / 'requests/register.json'), 'admin')['result']
    service.execute('set-state', request({'registration_id': registered['registration_id'],
                    'expected_revision': 1, 'target_state': 'ENABLED'}), 'admin')
    created = service.execute('create', request({'registration_id': registered['registration_id'],
                'input_ref': initial['input_ref'], 'object_refs': initial['object_refs']}), 'initiator')['result']
    result = Worker(host).run(created['case_id'])
    assert result['result']['status'] == 'SUCCEEDED'
    # create data, claim rule, Worker execution, submit rule/output.
    assert calls == ['echo'] * 4
    # Dispatch is the subject of this test. The generic audited teardown owns
    # the Host/SQLite locks; legacy Host.cleanup must not reacquire those locks.
    audit.remove_tree(path)
    audit.verify()


def test_component_executes_exact_reviewed_source_bytes():
    import importlib.util
    import hashlib
    assert importlib.util.find_spec('runtime_core.python_component') is not None, 'Source-bound adapter is missing'
    from runtime_core.python_component import PythonComponent
    import runpy
    fixture = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))
    source = (fixture['REFERENCE'] / 'l3/package/components/normalize-submission/implementation.py').read_bytes()
    expected = 'd25077a74206f536c3fccc859903070d5bb8e14a67b706b28c3f7817d9269bf0'
    assert hashlib.sha256(source).hexdigest() == expected
    component = PythonComponent(source, expected)
    value = {'text': '  SYNTHETIC  sample  '}
    assert component.invoke(value) == {'normalized': 'SYNTHETIC  sample'}
    assert value == {'text': '  SYNTHETIC  sample  '}


@pytest.mark.parametrize('body,code', [
    ("raise KeyError('private detail')", 'CONTRACT_INVALID'),
    ("raise TypeError('private detail')", 'CONTRACT_INVALID'),
    ("1 / 0", 'INTERNAL_ERROR'),
    ('return 1.5', 'CONTRACT_INVALID'),
    ('return (x for x in [])', 'CONTRACT_INVALID'),
    ('return lambda: None', 'CONTRACT_INVALID'),
    ('return {1: 2}', 'CONTRACT_INVALID'),
    ('return 9007199254740992', 'CONTRACT_INVALID'),
    ("return '\\ud800'", 'CONTRACT_INVALID'),
    ("value['text'] = 'changed'\n    return {'normalized': 'ok'}", 'CONTRACT_INVALID'),
    ('return value', 'OK'),
])
def test_author_boundary_is_local_and_does_not_leak_errors(body, code):
    from runtime_core.python_component import PythonComponent
    from runtime_core.contract_adapter import ContractError
    source = ('def normalize(value):\n    ' + body + '\n').encode('utf-8')
    component = PythonComponent(source, hashlib.sha256(source).hexdigest())
    value = {'text': 'safe'}
    if code == 'OK':
        assert component.invoke(value) == value
    else:
        with pytest.raises(ContractError) as exc:
            component.invoke(value)
        assert exc.value.code == code
        assert 'private detail' not in str(exc.value)
    assert value == {'text': 'safe'}


@pytest.mark.parametrize('source', [
    b'async def normalize(value):\n    return value\n',
    b'def normalize(value):\n    import os\n    return value\n',
    b'def helper(value):\n    return value\ndef normalize(value):\n    return helper(value)\n',
])
def test_undeclared_helpers_and_async_are_not_supported(source):
    from runtime_core.python_component import PythonComponent
    from runtime_core.contract_adapter import ContractError
    with pytest.raises(ContractError) as exc:
        PythonComponent(source, hashlib.sha256(source).hexdigest()).invoke({'text': 'safe'})
    assert exc.value.code == 'CONTRACT_INVALID'


def test_component_rejects_hash_callable_mismatch_without_cache():
    from runtime_core.python_component import PythonComponent
    from runtime_core.contract_adapter import ContractError
    source = b'def normalize(value):\n    return value\n'
    component = PythonComponent(source, hashlib.sha256(source).hexdigest())
    component._source = b'def normalize(value):\n    return {"normalized": "wrong"}\n'
    with pytest.raises(ContractError) as exc:
        component.invoke({'text': 'safe'})
    assert exc.value.code == 'VERSION_CONFLICT'


def test_package_pipeline_executes_source_and_binds_sqlite_identity(monkeypatch):
    import runpy
    from runtime_core.package_install import install_package, trusted_plan
    from runtime_core.package_host import PackageHost
    from runtime_core.contract_adapter import load_json, digest
    from runtime_core.synthetic_host import ident
    from runtime_core.service import Service
    from runtime_core.worker import Worker
    fixture = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))
    monkeypatch.setenv('WF2_TOOL_ROOT', str(fixture['TOOL_ROOT']))
    with fixture['generated']() as g:
        installed = install_package(g.package, g.materials, g.sandbox, trusted_plan=trusted_plan('normalize-l3-v1'))
        host = PackageHost(g.sandbox)
        service = Service(host)
        request = lambda payload: {'request_id': ident('req'), 'idempotency_key': ident('key'), 'payload': payload}
        registered = service.execute('register', load_json(installed['register_request']), 'admin')['result']
        service.execute('set-state', request({'registration_id': registered['registration_id'],
                        'expected_revision': 1, 'target_state': 'ENABLED'}), 'admin')
        created = service.execute('create', request({'registration_id': registered['registration_id'],
                    'input_ref': installed['input_ref'], 'object_refs': installed['object_refs']}), 'initiator')['result']
        result = Worker(host).run(created['case_id'])
        assert result['result']['status'] == 'SUCCEEDED'
        fresh = PackageHost(g.sandbox)
        snap = Service(fresh).query('snapshot', created['case_id'])['result']
        assert snap['nodes'][0]['output'] == {'normalized': 'SYNTHETIC  sample'}
        identity = snap['binding']['package_installation']
        assert identity['installation_id'] == installed['installation_id']
        proof = load_json(g.sandbox / 'host' / ('execution-' + snap['nodes'][0]['output_ref']['evidence_id'] + '.json'))
        assert proof['case_id'] == created['case_id'] and proof['node_run_id'] == snap['nodes'][0]['node_run_id']
        assert proof['attempt_id'] == snap['nodes'][0]['attempt']['attempt_id']
        assert proof['installation_id'] == installed['installation_id'] and proof['invoked'] is True
        assert proof['input_digest'] == installed['input_ref']['digest']
        assert proof['output_digest'] == digest({'normalized': 'SYNTHETIC  sample'})
        assert proof['implementation_sha256'] == 'd25077a74206f536c3fccc859903070d5bb8e14a67b706b28c3f7817d9269bf0'
