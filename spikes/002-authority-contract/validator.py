"""DRAFT local contract checks. No issuance, auth transport or execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'docs/architecture-track/contracts/authority-contract.schema.json'
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AuthorityUnavailable(Exception):
    """Reader cannot obtain a complete, currently authenticated view."""


@dataclass(frozen=True)
class TrustedContext:
    """HOST ONLY: never construct from a request, CLI, token or AI output."""
    scope: dict
    deployment_id: str
    now: datetime
    minimum_revision: int = 0
    synthetic: bool = True


class AuthorityReader(Protocol):
    """Host-injected authenticated, scoped read seam; no issue/write API.

    lookup: exact immutable refs; current: current control facts.
    Provider failures must raise AuthorityUnavailable; returned mappings
    are still schema/binding checked by the consumer.
    """
    def lookup(self, kind: str, reference: dict, context: TrustedContext) -> dict | None: ...
    def current(self, kind: str, key: str, context: TrustedContext) -> dict | None: ...


def canonical_bytes(value):
    def walk(x):
        if x is None or type(x) in (bool, str):
            return
        if type(x) is int and abs(x) <= 9007199254740991:
            return
        if type(x) is list:
            for v in x:
                walk(v)
            return
        if type(x) is dict and all(type(k) is str for k in x):
            for v in x.values():
                walk(v)
            return
        raise ContractError('CANONICALIZATION_INVALID')
    walk(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (UnicodeError, ValueError):
        raise ContractError('CANONICALIZATION_INVALID') from None


def digest(value):
    return {'algorithm': 'sha256', 'canonicalization': 'json-sort-utf8-int-v1', 'value': hashlib.sha256(canonical_bytes(value)).hexdigest()}


def key(value):
    return canonical_bytes(value).decode('utf-8')


def load_json(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ContractError('DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    try:
        content = Path(path).read_bytes()
        if len(content) > 2_000_000:
            raise ContractError('INPUT_TOO_LARGE')
        result = json.loads(content.decode('utf-8'), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ContractError('CANONICALIZATION_INVALID')))
        canonical_bytes(result)
        return result
    except ContractError:
        # Preserve specific codes: ContractError is itself a ValueError.
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ContractError('INPUT_INVALID') from None


def timestamp(s):
    if not isinstance(s, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', s):
        raise ContractError('TIME_INVALID')
    try:
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        raise ContractError('TIME_INVALID') from None


def shape(name, value):
    canonical_bytes(value)
    wrapper = {'$schema': SCHEMA['$schema'], '$defs': SCHEMA['$defs'], '$ref': '#/$defs/' + name}
    if next(Draft202012Validator(wrapper).iter_errors(value), None):
        raise ContractError('SCHEMA_INVALID')


def context_check(context):
    if not isinstance(context, TrustedContext) or context.now.tzinfo is None:
        raise ContractError('TRUST_CONTEXT_REQUIRED')
    shape('Scope', context.scope)
    shape('Id', context.deployment_id)


def lookup(authority, kind, reference, context):
    try:
        result = authority.lookup(kind, reference, context)
    except (AuthorityUnavailable, AttributeError):
        raise ContractError('AUTHORITY_UNAVAILABLE') from None
    if result is None:
        raise ContractError('UNKNOWN_PROVIDER' if kind == 'provider' else 'DEPENDENCY_UNAVAILABLE')
    return result


def current(authority, kind, reference, context):
    try:
        result = authority.current(kind, reference, context)
    except (AuthorityUnavailable, AttributeError):
        raise ContractError('AUTHORITY_UNAVAILABLE') from None
    if result is None:
        raise ContractError('AUTHORITY_UNAVAILABLE')
    return result


def live(record, context):
    if record['scope'] != context.scope:
        raise ContractError('SCOPE_MISMATCH')
    if record['status'] != 'ACTIVE':
        raise ContractError('REVOKED')
    start, end = timestamp(record['valid_from']), timestamp(record['expires_at'])
    if start >= end:
        raise ContractError('TIME_INVALID')
    if context.now < start:
        raise ContractError('NOT_YET_VALID')
    if context.now >= end:
        raise ContractError('EXPIRED')


def resolve(reference, authority, context):
    shape('DefinitionRef', reference)
    record = lookup(authority, 'provider' if reference['kind'] == 'provider' else 'definition', reference, context)
    shape('DefinitionRecord', record)
    if record['ref'] != reference or digest(record['content']) != reference['digest']:
        raise ContractError('VERSION_DIGEST_MISMATCH')
    live(record, context)
    return record


def local_result():
    return {'verdict': 'VALIDATED_LOCAL_ONLY', 'contract_status': 'DRAFT', 'production_authorized': False}


def validate_node_graph(projection):
    nodes = {node['node_id']: node for node in projection['nodes']}
    if len(nodes) != len(projection['nodes']):
        raise ContractError('DUPLICATE_NODE')
    parents = {ident: set(node['depends_on']) for ident, node in nodes.items()}
    if any(parent not in nodes for deps in parents.values() for parent in deps):
        raise ContractError('NODE_DEPENDENCY_MISSING')
    # The Schema caps graphs at 256 nodes; bounded iterative traversal avoids
    # recursion failures and never mutates the submitted projection.
    pending = dict(parents)
    while pending:
        ready = {ident for ident, deps in pending.items() if not deps}
        if not ready:
            raise ContractError('NODE_CYCLE')
        pending = {ident: deps - ready for ident, deps in pending.items()
                   if ident not in ready}
    non_leaves = {parent for deps in parents.values() for parent in deps}
    if set(projection['terminal_nodes']) != set(nodes) - non_leaves:
        raise ContractError('TERMINAL_NODES_INVALID')


def validate_provider_bindings(projection, records):
    providers = {}
    for reference in projection['provider_bindings']:
        if reference['kind'] != 'provider':
            raise ContractError('PROVIDER_KIND_MISMATCH')
        content = records[key(reference)]['content']
        # Published descriptor content excludes its own ref (digest cycle).
        if 'ref' in content:
            raise ContractError('SCHEMA_INVALID')
        shape('ProviderDescriptor', {'ref': reference, **content})
        providers[key(reference)] = content
    roles = {
        'executor_ref': 'NodeExecutor',
        'data_provider_ref': 'DataProvider',
        'validator_ref': 'ContractValidator',
        'rule_provider_ref': 'RuleProvider',
        'readback_provider_ref': 'ReadbackProvider',
        'action_adapter_ref': 'ActionAdapter',
    }
    for node in projection['nodes']:
        for field, role in roles.items():
            reference = node[field]
            if reference is None:
                continue
            if reference['kind'] != 'provider':
                raise ContractError('PROVIDER_KIND_MISMATCH')
            provider = providers.get(key(reference))
            if provider is None:
                raise ContractError('PROVIDER_NOT_BOUND')
            if provider['role'] != role:
                raise ContractError('PROVIDER_ROLE_MISMATCH')
            if role == 'NodeExecutor' and provider['execution_kind'] != node['execution_kind']:
                raise ContractError('PROVIDER_EXECUTION_KIND_MISMATCH')


def validate_projection(projection, authority, context):
    context_check(context)
    shape('Projection', projection)
    record = resolve(projection['definition_ref'], authority, context)
    body = {k: v for k, v in projection.items() if k != 'definition_ref'}
    if record['content'] != body:
        raise ContractError('PROJECTION_BINDING_MISMATCH')
    if projection['scope'] != context.scope:
        raise ContractError('SCOPE_MISMATCH')
    declared = {key(ref) for ref in projection['dependencies']}
    if {key(ref) for ref in record['dependencies']} != declared:
        raise ContractError('DEPENDENCY_BINDING_MISMATCH')
    required = [projection['business_ref'], *projection['provider_bindings']]
    for node in projection['nodes']:
        required.extend(value for field, value in node.items()
                        if field.endswith('_ref') and value is not None)
    records = {}
    for reference in projection['dependencies']:
        dependency = resolve(reference, authority, context)
        records[key(reference)] = dependency
        required.extend(dependency['dependencies'])
    if any(key(reference) not in declared for reference in required):
        raise ContractError('DEPENDENCY_NOT_DECLARED')
    validate_node_graph(projection)
    validate_provider_bindings(projection, records)
    return local_result()
