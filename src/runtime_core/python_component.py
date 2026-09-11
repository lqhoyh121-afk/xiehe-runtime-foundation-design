"""Source-bound synchronous JSON component. Trusted pure code only. Laiqh."""
from copy import deepcopy
import ast
import hashlib
import inspect

from runtime_core.contract_adapter import ContractError, canonical_bytes, require

ABI = 'sync-json-v1'
VERSION = 'python-component-v1'


class PythonComponent:
    """Host supplies verified bytes, never a module path or cached callable."""
    def __init__(self, source, expected_sha256):
        require(type(source) is bytes and hashlib.sha256(source).hexdigest() == expected_sha256,
                'VERSION_CONFLICT')
        self._source, self.source_sha256 = source, expected_sha256

    def invoke(self, value):
        source = self._source
        require(hashlib.sha256(source).hexdigest() == self.source_sha256, 'VERSION_CONFLICT')
        try:
            tree = ast.parse(source)
            functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
            require(len(functions) == 1 and functions[0].name == 'normalize')
            function = functions[0]
            require(all(n is function or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and type(n.value.value) is str) for n in tree.body))
            require(not any(isinstance(n, (ast.Import, ast.ImportFrom, ast.AsyncFunctionDef)) for n in ast.walk(tree)))
            args = function.args
            require([a.arg for a in args.args] == ['value'] and not args.posonlyargs and not args.kwonlyargs
                    and args.vararg is None and args.kwarg is None and not args.defaults
                    and not function.decorator_list and function.returns is None and args.args[0].annotation is None)
            before = canonical_bytes(value)
            argument = deepcopy(value)
        except (ContractError, SyntaxError, TypeError, ValueError, RecursionError):
            raise ContractError('CONTRACT_INVALID') from None
        namespace = {'__builtins__': {'isinstance': isinstance, 'dict': dict, 'str': str,
                                     'TypeError': TypeError, 'KeyError': KeyError}}
        try:
            # Compile exactly these checked bytes; never import a path or use pycache.
            exec(compile(source, '<installed-normalize>', 'exec', dont_inherit=True), namespace)
            result = namespace['normalize'](argument)
        except (KeyError, TypeError):
            raise ContractError('CONTRACT_INVALID') from None
        except Exception:
            raise ContractError('INTERNAL_ERROR') from None
        try:
            if inspect.iscoroutine(result) or inspect.isgenerator(result):
                result.close()
                raise ContractError('CONTRACT_INVALID')
            canonical_bytes(result)
            require(canonical_bytes(argument) == before)
            return deepcopy(result)
        except (ContractError, TypeError, ValueError, RecursionError):
            raise ContractError('CONTRACT_INVALID') from None
