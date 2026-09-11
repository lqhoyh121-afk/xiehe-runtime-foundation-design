"""Fixed trusted-source bridge; isolated name, no package-controlled imports. Laiqh."""
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sys
from threading import RLock

_LOCK = RLock()


@lru_cache(maxsize=1)
def shared():
    with _LOCK:
        source = Path(__file__).resolve().parents[1] / 'spikes/002-authority-contract/validator.py'
        name = '_workflow_author_trusted_authority_validator'
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            # Compile ONLY this repository-owned source; no pycache or user supplied module path.
            exec(compile(source.read_bytes(), str(source), 'exec'), module.__dict__)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module


def parse_json(text):
    """Decode bounded cached text; canonicalization/shape remain shared authority."""
    api = shared()

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise api.ContractError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def invalid_constant(value):
        raise api.ContractError('CANONICALIZATION_INVALID')

    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
        api.canonical_bytes(result)
        return result
    except api.ContractError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise api.ContractError('INPUT_INVALID') from None
