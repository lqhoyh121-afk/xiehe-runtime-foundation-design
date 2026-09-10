"""Read-only, privately named imports of the existing contract. Laiqh."""
import builtins
import importlib.util
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[2] / 'spikes/002-authority-contract'
_MODULES = {}


def _load(name):
    if name in _MODULES:
        return _MODULES[name]
    qualified = 'runtime_core._authority_' + name
    spec = importlib.util.spec_from_file_location(qualified, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    original = builtins.__import__

    def local_import(target, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and target in {'validator', 'authority_checks', 'fixtures', 'p2_fixtures'}:
            return _load(target)
        return original(target, globals, locals, fromlist, level)

    module.__dict__['__builtins__'] = {**vars(builtins), '__import__': local_import}
    sys.modules[qualified] = module  # dataclass requires its actual qualified module.
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(qualified, None)
        raise
    _MODULES[name] = module
    return module


validator = _load('validator')
authority_checks = _load('authority_checks')
ContractError = validator.ContractError
canonical_bytes = validator.canonical_bytes
digest = validator.digest
key = validator.key
load_json = validator.load_json
shape = validator.shape
resolve = validator.resolve
timestamp = validator.timestamp
check_consumption = authority_checks.check_consumption
ConsumptionContext = authority_checks.ConsumptionContext


def fixture_modules():
    """Only called by the synthetic host initializer, never from request input."""
    return _load('fixtures'), _load('p2_fixtures')


def require(condition, code='CONTRACT_INVALID'):
    if not condition:
        raise ContractError(code)


def exact(value, fields):
    require(type(value) is dict and set(value) == set(fields), 'SCHEMA_INVALID')


def request_shape(request):
    canonical_bytes(request)
    exact(request, ('request_id', 'idempotency_key', 'payload'))
    shape('Id', request['request_id'])
    shape('Id', request['idempotency_key'])
    require(type(request['payload']) is dict, 'SCHEMA_INVALID')


def request_digest(operation, scope, namespace, target, semantic_input):
    return digest({'request_digest_version': 'rc0-m1-request-v1', 'operation': operation,
                   'scope': scope, 'namespace': namespace, 'target': target,
                   'semantic_input': semantic_input})


def capabilities(projection, installed):
    nodes = projection['nodes']
    require(len(nodes) == 1, 'CAPABILITY_UNSUPPORTED')
    n = nodes[0]
    require(n['execution_kind'] == 'CODE' and n['completion'] == 'OUTPUT_VALIDATED'
            and n['depends_on'] == [] and projection['terminal_nodes'] == [n['node_id']]
            and n['resources'] == [] and n['timeout_seconds'] == 30
            and n['retry_policy'] == {'max_attempts': 1, 'backoff_seconds': 0}
            and all(n[f] is None for f in ('wait_spec_ref', 'verification_spec_ref',
                                          'readback_provider_ref', 'action_adapter_ref')),
            'CAPABILITY_UNSUPPORTED')
    require(all(ref in installed for ref in projection['provider_bindings']), 'CAPABILITY_UNSUPPORTED')
