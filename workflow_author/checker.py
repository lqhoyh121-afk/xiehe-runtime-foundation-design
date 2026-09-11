"""Read-only, bounded author checks. No import/execution of submitted packages. Laiqh."""
import ast
import json
from pathlib import PurePosixPath
import re
from .authority_bridge import parse_json, shared
from .contracts import (ACCEPTANCE_SECTIONS, COMPONENT, FAILURE_KEYS, MANIFEST, PROFILE,
                        VERSION, diagnostic, report)
from .safety import SafetyError, relfile, snapshot

_SECRET = re.compile(
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
    r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})|'
    r'https?://[^\s/@]+:[^\s/@]+@|'
    r"(?i:(?:password|passwd|access_token|client_secret|api_key)\s*[\"\']?\s*[=:]\s*[\"\'][^\"\'\n]+)")
_LOCAL = re.compile(r'(?i)(?:[a-z]:[/\\]users[/\\]|/home/[^/]+/|file://)')
_PLACEHOLDER = re.compile(r'(?i)\b(?:TODO|FIXME|TBD)\b|【待填写】')
_REQUIRED = ('safety', 'author', 'shared', 'profile', 'source', 'acceptance', 'authority')
_FORBIDDEN = {'eval', 'exec', '__import__', 'compile', 'open', 'getattr', 'setattr', 'globals', 'locals',
              'input', 'sleep', 'write_text', 'write_bytes', 'unlink', 'mkdir', 'rmdir', 'remove',
              'rename', 'replace', 'connect', 'urlopen', 'request_action', 'create_case', 'resume_case',
              'submit_node_result', 'claim_node', 'save_case', 'update_case', 'create_successor'}
_BAD_IMPORTS = {'os', 'sys', 'subprocess', 'socket', 'requests', 'urllib', 'http', 'sqlite3',
                'pickle', 'marshal', 'ctypes', 'multiprocessing', 'threading', 'asyncio', 'importlib'}
_TRUST_KEYS = {'approved', 'auth_context', 'trustedcontext', 'trusted_context', 'grant', 'admission', 'module_path'}
_PURE_IMPORTS = {'math', 'decimal', 'fractions', 'statistics', 're', 'json', 'collections',
                 'itertools', 'functools', 'typing', 'dataclasses', 'enum', 'copy', 'string', 'operator'}


def safe_location(value):
    if value is None or _SECRET.search(value) or _LOCAL.search(value) or len(value) > 240:
        return None
    return value


def _text(value):
    return isinstance(value, str) and bool(value.strip())


class Inspection:
    def __init__(self, files):
        self.files = files
        self.checks = dict.fromkeys(_REQUIRED, 'NOT_RUN')
        self.errors, self.drafts, self.incomplete = [], [], []
        self.api = shared()

    def add(self, ident, phase, *, file=None, pointer=None, code=None, draft=False, incomplete=False,
            line=None, column=None):
        item = diagnostic(ident, phase=phase, file=safe_location(file), pointer=safe_location(pointer),
                          source_code=code, line=line, column=column)
        (self.drafts if draft else self.incomplete if incomplete else self.errors).append(item)
        if phase in self.checks:
            self.checks[phase] = 'NOT_RUN' if incomplete else 'FAIL'

    def start(self, phase):
        self.checks[phase] = 'PASS'

    def finish(self):
        if self.errors:
            status = 'REJECTED'
        elif self.drafts:
            status = 'DRAFT'
        elif self.incomplete or 'NOT_RUN' in self.checks.values():
            status = 'INCOMPLETE'
        else:
            status = 'PASSED'
        checks = [dict(id=k, status=v) for k, v in self.checks.items()]
        checks.extend(dict(id=k, status='NOT_APPLICABLE') for k in ['I3-mapping', 'I4-wait', 'I6-external-ports'])
        return report('check', status, checks=checks, diagnostics=self.errors + self.drafts + self.incomplete)

    def scan_content(self):
        self.start('safety')
        for file, text in self.files.items():
            if _SECRET.search(text) or _LOCAL.search(text) or _SECRET.search(file):
                self.add('AUTH-PORT-009', 'safety', file=file)
            if file.startswith(('ports/', 'deployment/')):
                self.add('AUTH-SUPPORT-010', 'profile', file=file)

    def decode(self, file):
        if file not in self.files:
            self.add('AUTH-REQ-001', 'author', file=file)
            return None
        try:
            value = parse_json(self.files[file])
            serialized = json.dumps(value, ensure_ascii=False)
            if _SECRET.search(serialized) or _LOCAL.search(serialized):
                self.add('AUTH-PORT-009', 'safety', file=file)
            stack = [value]
            while stack:
                obj = stack.pop()
                if isinstance(obj, dict):
                    if any(k.lower() in _TRUST_KEYS for k in obj):
                        self.add('AUTH-PERM-007', 'author', file=file)
                    stack.extend(obj.values())
                elif isinstance(obj, list):
                    stack.extend(obj)
            return value
        except self.api.ContractError as exc:
            self.add('AUTH-REF-002', 'shared', code=exc.code, file=file)
            return None

    def fields(self, obj, contract, file, is_draft):
        if not isinstance(obj, dict):
            self.add('AUTH-REQ-001', 'author', file=file)
            return False
        if set(obj) != set(contract):
            self.add('AUTH-REQ-001', 'author', file=file)
        good = True
        for key, (kind, _) in contract.items():
            if key not in obj:
                good = False
                self.add('AUTH-REQ-001', 'author', file=file, pointer='/' + key)
                continue
            value = obj[key]
            if value is None and is_draft:
                self.add('AUTH-DRAFT-011', 'author', file=file, pointer='/' + key, draft=True)
                good = False
                continue
            if not self.value_ok(kind, value):
                self.add('AUTH-REQ-001', 'author', file=file, pointer='/' + key)
                good = False
            if _PLACEHOLDER.search(json.dumps(value, ensure_ascii=False)):
                self.add('AUTH-DRAFT-011', 'author', file=file, pointer='/' + key, draft=True)
        return good and set(obj) == set(contract)

    def value_ok(self, kind, value):
        if kind == 'text':
            return _text(value)
        if kind in ('id', 'version'):
            if not _text(value):
                return False
            schema = self.api.SCHEMA['$defs']['Id'] if kind == 'id' else self.api.SCHEMA['$defs']['DefinitionRef']['properties']['version']
            return re.fullmatch(schema['pattern'], value) is not None
        if kind == 'file':
            try:
                return relfile(value) in self.files
            except SafetyError:
                return False
        if kind in ('files', 'optional_files', 'texts'):
            if not isinstance(value, list) or (not value and kind != 'optional_files'):
                return False
            if not all(isinstance(item, str) for item in value) or len(set(value)) != len(value):
                return False
            return all(self.value_ok('text' if kind == 'texts' else 'file', item) for item in value)
        if kind in ('state', 'implementation', 'profile'):
            choices = {'state': ('draft', 'candidate'), 'implementation': ('unimplemented', 'implemented'), 'profile': (PROFILE,)}
            return isinstance(value, str) and value in choices[kind]
        if kind in ('permissions', 'capabilities'):
            keys = ('need', 'scope_note') if kind == 'permissions' else ('interface', 'requirement')
            if not isinstance(value, list) or not value:
                return False
            if not all(isinstance(v, dict) and set(v) == set(keys) and all(_text(v[k]) for k in keys) for v in value):
                return False
            if len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
                return False
            return kind != 'capabilities' or all(v['interface'] in ('I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7', 'I8') for v in value)
        if kind == 'failures':
            return isinstance(value, dict) and set(value) == set(FAILURE_KEYS) and all(_text(v) for v in value.values())
        if kind == 'effects':
            notes = ('intent_note', 'idempotency_note', 'readback_note')
            if not isinstance(value, dict) or set(value) != {'category', *notes}:
                return False
            if value['category'] == 'none':
                return all(value[k] is None for k in notes)
            return value['category'] == 'controlled-action' and all(_text(value[k]) for k in notes)
        return False

    def screen_sources(self, components):
        self.start('source')
        implementations = {c.get('implementation_file') for c in components if isinstance(c, dict)}
        helpers = {PurePosixPath(h).stem for c in components for h in c.get('allowed_helpers', [])}
        tests = {h for c in components for h in c.get('test_files', [])}
        for file, text in self.files.items():
            if not file.endswith('.py'):
                continue
            try:
                tree = ast.parse(text)
            except (SyntaxError, RecursionError, ValueError):
                self.add('AUTH-BOUNDARY-006', 'source', file=file)
                continue
            if _PLACEHOLDER.search(text):
                self.add('AUTH-DRAFT-011', 'source', file=file, draft=True)
            functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

            def substantive(function):
                body = [n for n in function.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
                return bool(body) and not all(isinstance(n, ast.Pass)
                    or (isinstance(n, ast.Return) and (n.value is None or isinstance(n.value, ast.Constant)))
                    or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
                    or (isinstance(n, ast.Assert) and isinstance(n.test, ast.Constant)) for n in body)

            for function in functions:
                if not substantive(function):
                    self.add('AUTH-DRAFT-011', 'source', file=file, line=function.lineno, draft=True)
            if file in implementations and not any(isinstance(n, ast.Return) and n.value is not None and not isinstance(n.value, ast.Constant) for n in ast.walk(tree)):
                self.add('AUTH-DRAFT-011', 'source', file=file, draft=True)
            for node in ast.walk(tree):
                name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ''
                if name in _FORBIDDEN or name.startswith('__') or re.search(r'(?i)(case_state|case_store|noderun|workflow_cursor)', name):
                    self.add('AUTH-BOUNDARY-006', 'source', file=file, line=getattr(node, 'lineno', None), column=getattr(node, 'col_offset', 0) + 1)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imported = [n.name.split('.')[0] for n in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
                    allowed = _PURE_IMPORTS | helpers
                    if file in tests:
                        allowed = allowed | {'pytest'} | {PurePosixPath(p).stem for p in implementations}
                    if any(n in _BAD_IMPORTS or n not in allowed for n in imported):
                        self.add('AUTH-BOUNDARY-006', 'source', file=file, line=node.lineno, column=node.col_offset + 1)
                if name == 'NotImplementedError':
                    self.add('AUTH-DRAFT-011', 'source', file=file, line=getattr(node, 'lineno', None), draft=True)
            if not functions:
                self.add('AUTH-DRAFT-011', 'source', file=file, draft=True)
            if file in tests:
                top_level_tests = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                                   and node.name.startswith('test_') and substantive(node)]
                class_tests = [method for node in tree.body if isinstance(node, ast.ClassDef) and node.name.startswith('Test')
                               for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                               and method.name.startswith('test_') and substantive(method)]
                if not top_level_tests and not class_tests:
                    self.add('AUTH-DRAFT-011', 'source', file=file, draft=True)

    def inspect(self, authority, context):
        self.scan_content()
        self.start('author')
        # Parse all JSON, including unknown files, without following paths or loading modules.
        decoded = {file: self.decode(file) for file in self.files if file.endswith('.json')}
        manifest = decoded.get('package-manifest.json')
        draft = isinstance(manifest, dict) and manifest.get('candidate_state') == 'draft'
        if draft:
            self.add('AUTH-DRAFT-011', 'author', file='package-manifest.json', pointer='/candidate_state', draft=True)
        if not self.fields(manifest, MANIFEST, 'package-manifest.json', draft):
            self.screen_sources([])
            return self.finish()
        if manifest['author_contract_version'] != VERSION:
            self.add('AUTH-REQ-001', 'author', file='package-manifest.json', pointer='/author_contract_version')
        components = []
        for file in manifest['component_files']:
            c = decoded.get(file)
            if self.fields(c, COMPONENT, file, draft):
                components.append(c)
                if not all(p.endswith('.py') for p in [c['implementation_file'], *c['test_files'], *c['allowed_helpers']]):
                    self.add('AUTH-REQ-001', 'author', file=file)
                if PurePosixPath(file).parts != ('components', c['component_id'], 'declaration.json'):
                    self.add('AUTH-REQ-001', 'author', file=file, pointer='/component_id')
                if c['implementation_state'] == 'unimplemented':
                    self.add('AUTH-DRAFT-011', 'author', file=file, pointer='/implementation_state', draft=True)
                if c['side_effects']['category'] != 'none':
                    self.add('AUTH-SUPPORT-010', 'profile', file=file, pointer='/side_effects')
        expected_declarations = {name for name in self.files if name.startswith('components/') and name.endswith('/declaration.json')}
        if expected_declarations != set(manifest['component_files']):
            self.add('AUTH-REQ-001', 'author', file='package-manifest.json', pointer='/component_files')
        self.screen_sources(components)
        self.start('acceptance')
        acceptance = self.files[manifest['acceptance_file']]
        for section in ACCEPTANCE_SECTIONS:
            bodies = re.findall(r'^## ' + re.escape(section) + r'[^\S\n]*\n(.*?)(?=^## |\Z)', acceptance, re.M | re.S)
            if len(bodies) != 1 or not bodies[0].strip():
                self.add('AUTH-REQ-001', 'acceptance', file=manifest['acceptance_file'])
        if PROFILE not in acceptance and not _PLACEHOLDER.search(acceptance):
            self.add('AUTH-REQ-001', 'acceptance', file=manifest['acceptance_file'])
        if _PLACEHOLDER.search(acceptance):
            self.add('AUTH-DRAFT-011', 'acceptance', file=manifest['acceptance_file'], draft=True)
        for asset in ['skills/development-SKILL.md', 'skills/runtime-SKILL.md']:
            if asset not in self.files or not self.files[asset].strip():
                self.add('AUTH-REQ-001', 'acceptance', file=asset)
        projection_file = manifest['projection_file']
        projection = decoded.get(projection_file)
        self.start('shared')
        if projection is None and draft:
            self.add('AUTH-DRAFT-011', 'shared', file=projection_file, draft=True)
            return self.finish()
        try:
            self.api.shape('Projection', projection)
            self.api.validate_node_graph(projection)
        except self.api.ContractError as exc:
            self.add('AUTH-REF-002', 'shared', file=projection_file, code=exc.code)
            return self.finish()
        nodes = projection['nodes']
        # Source: shared.validate_projection/validate_provider_bindings. These facts need no Reader.
        declared = {self.api.key(ref) for ref in projection['dependencies']}
        bound = {self.api.key(ref) for ref in projection['provider_bindings']}
        required = [projection['business_ref'], *projection['provider_bindings']]
        provider_fields = ('executor_ref', 'data_provider_ref', 'validator_ref', 'rule_provider_ref', 'readback_provider_ref', 'action_adapter_ref')
        for node in nodes:
            required.extend(value for key, value in node.items() if key.endswith('_ref') and value is not None)
            for field in provider_fields:
                ref = node[field]
                if ref is not None and ref['kind'] != 'provider':
                    self.add('AUTH-REF-002', 'shared', file=projection_file, code='PROVIDER_KIND_MISMATCH')
                elif ref is not None and self.api.key(ref) not in bound:
                    self.add('AUTH-REF-002', 'shared', file=projection_file, code='PROVIDER_NOT_BOUND')
        if any(self.api.key(ref) not in declared for ref in required):
            self.add('AUTH-REF-002', 'shared', file=projection_file, code='DEPENDENCY_NOT_DECLARED')
        if sorted(c['node_id'] for c in components) != sorted(n['node_id'] for n in nodes):
            self.add('AUTH-GRAPH-004', 'author', file='package-manifest.json', pointer='/component_files')
        if len({c['component_id'] for c in components}) != len(components):
            self.add('AUTH-REQ-001', 'author', file='package-manifest.json', pointer='/component_files')
        impls = {c['implementation_file'] for c in components}
        if len(impls) != len(components) or any(set(c['allowed_helpers']) & impls for c in components):
            self.add('AUTH-BOUNDARY-006', 'author', file='package-manifest.json', pointer='/component_files')
        if self.checks['profile'] != 'FAIL':
            self.start('profile')
        valid_profile = len(nodes) == 1 and projection['terminal_nodes'] == [nodes[0]['node_id']]
        for node in nodes:
            valid_profile = valid_profile and (node['execution_kind'] == 'CODE' and node['completion'] == 'OUTPUT_VALIDATED'
                and node['depends_on'] == [] and node['resources'] == [] and node['timeout_seconds'] == 30
                and node['retry_policy'] == {'max_attempts': 1, 'backoff_seconds': 0}
                and all(node[k] is None for k in ['wait_spec_ref', 'verification_spec_ref', 'readback_provider_ref', 'action_adapter_ref']))
        if not valid_profile:
            self.add('AUTH-SUPPORT-010', 'profile', file=projection_file)
        if self.errors or self.drafts:
            return self.finish()
        try:
            self.api.validate_projection(projection, authority, context)
            self.start('authority')
        except self.api.ContractError as exc:
            self.add('AUTH-REF-002', 'authority', file=projection_file, code=exc.code,
                     incomplete=exc.code in ('TRUST_CONTEXT_REQUIRED', 'AUTHORITY_UNAVAILABLE'))
        return self.finish()


def check_package(package_root, *, authority=None, context=None):
    try:
        return Inspection(snapshot(package_root)).inspect(authority, context)
    except SafetyError as exc:
        return report('check', 'REJECTED', checks=[dict(id='safety', status='FAIL')],
                      diagnostics=[diagnostic('AUTH-PORT-009', source_code=exc.code, phase='safety')])
    except (OSError, RecursionError):
        return report('check', 'REJECTED', diagnostics=[diagnostic('AUTH-PORT-009', source_code='INPUT_UNAVAILABLE', phase='safety')])
    except Exception:
        return report('check', 'INTERNAL_ERROR', diagnostics=[diagnostic('AUTH-INTERNAL', phase='tool',
                      message='Unexpected tool failure; input and exception text are not disclosed.')])
