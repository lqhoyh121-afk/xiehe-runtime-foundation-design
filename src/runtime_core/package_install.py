"""Fixed TEST ONLY package installation; not a general Python installer. Laiqh."""
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys

from .contract_adapter import ContractError, digest, load_json, require
from .synthetic_host import ident, safe_path, save

FIXTURE = 'normalize-l3-v1'
RECORD_VERSION = 'wf2-install-v1'
IMPLEMENTATION = 'components/normalize-submission/implementation.py'
DECLARATION = 'components/normalize-submission/declaration.json'
ADAPTER_SHA256 = 'bf46b5eee99a50fa28320c15e99026c00dfa8d0c54f3f2d6276953d6be76a768'
# Fixed reviewed synthetic inputs, never reconstructed from caller claims.


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def plain_path(path):
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 1024),
                    'SANDBOX_INVALID')
    return path


def read_plain(path, maximum=2_000_000):
    path = plain_path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum, 'SANDBOX_INVALID')
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'VERSION_CONFLICT')
        content = stream.read(maximum + 1)
        require(identity(os.fstat(stream.fileno())) == identity(before), 'VERSION_CONFLICT')
    plain_path(path)
    require(identity(path.lstat()) == identity(before) and len(content) <= maximum, 'VERSION_CONFLICT')
    return content


def snapshot(path):
    root = plain_path(path)
    require(root.is_dir(), 'DEPENDENCY_UNAVAILABLE')
    result, pending, total, entries = {}, [root], 0, 0
    while pending:
        folder = pending.pop()
        plain_path(folder)
        for path in folder.iterdir():
            entries += 1
            require(entries <= 512, 'INPUT_TOO_LARGE')
            plain_path(path)
            if path.is_dir():
                pending.append(path)
                continue
            require(len(result) < 256, 'INPUT_TOO_LARGE')
            content = read_plain(path)
            total += len(content)
            require(total <= 20_000_000, 'INPUT_TOO_LARGE')
            result[path.relative_to(root).as_posix()] = content
    return result


def file_hashes(files):
    return {name: sha256(content) for name, content in sorted(files.items())}


def tree_hash(files, prefix):
    # The reviewed tree convention includes package/ or materials/ in every line.
    return sha256(''.join(prefix + '/' + name + '\0' + h + '\n'
                          for name, h in sorted(files.items())).encode('utf-8'))


def copy_snapshot(files, target):
    target.mkdir()
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())


_PLAN = object()


def trusted_plan(fixture):
    require(fixture == FIXTURE, 'UNAUTHORIZED')
    return _PLAN


def tool_root():
    value = os.environ.get('WF2_TOOL_ROOT')
    require(value is not None, 'DEPENDENCY_UNAVAILABLE')
    root = plain_path(value)
    require(file_hashes(snapshot(root)) == TOOL_FILES, 'VERSION_CONFLICT')
    return root


def runtime_identity():
    dependencies = {}
    for name in ('jsonschema', 'attrs', 'referencing', 'rpds-py', 'jsonschema-specifications'):
        distribution = importlib.metadata.distribution(name)
        files = {}
        for item in distribution.files or ():
            if str(item).endswith(('.py', '.pyd', '.so', '.json')):
                path = distribution.locate_file(item)
                files[str(item)] = sha256(read_plain(path, maximum=32_000_000))
        dependencies[name] = {'version': distribution.version, 'files_digest': digest(files)}
    return {'implementation': sys.implementation.name, 'version': list(sys.version_info[:3]),
            'executable_sha256': sha256(read_plain(sys.executable, maximum=32_000_000))}, dependencies


def adapter_bytes():
    content = read_plain(Path(__file__).with_name('python_component.py'))
    require(sha256(content) == ADAPTER_SHA256, 'VERSION_CONFLICT')
    return content


def component_from_bytes(source, record):
    content = adapter_bytes()
    require(record['adapter'] == {'version': 'python-component-v1', 'sha256': sha256(content)}, 'VERSION_CONFLICT')
    namespace = {'__name__': 'runtime_core._installed_python_adapter'}
    # No import loader / bytecode cache: identity and class use the same bytes.
    exec(compile(content, '<verified-python-adapter>', 'exec', dont_inherit=True), namespace)
    return namespace['PythonComponent'](source, record['implementation_sha256'])


class StaticCheckError(ContractError):
    def __init__(self, report, source_exit):
        super().__init__('STATIC_CHECK_REJECTED')
        self.report, self.source_exit = report, source_exit


def check_static(root, package, materials, evidence):
    argv = [sys.executable, '-B', str(root / 'tools/workflow_author_synthetic.py'), 'check',
            '--package', str(package), '--materials', str(materials), '--format', 'json']
    process = subprocess.Popen(argv, cwd=root, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
    receipt = {'argv': argv, 'pid': process.pid, 'exit_code': process.returncode, 'timed_out': timed_out,
               'stdout': stdout.decode('utf-8', errors='replace'), 'stderr': stderr.decode('utf-8', errors='replace')}
    save(evidence, receipt)
    require(not timed_out, 'DEPENDENCY_UNAVAILABLE')
    report = json.loads(stdout)
    if process.returncode != 0 or report.get('status') != 'PASSED':
        raise StaticCheckError(report, process.returncode)
    require(report.get('runtime_verified') is False and report.get('production_authorized') is False)
    require(file_hashes(snapshot(root)) == TOOL_FILES, 'VERSION_CONFLICT')
    return receipt


def verify_installation(path):
    path = safe_path(path)
    record = load_json(plain_path(path / 'host/installation.json'))
    body = {k: v for k, v in record.items() if k != 'record_digest'}
    require(record.get('record_digest') == digest(body), 'VERSION_CONFLICT')
    state = load_json(plain_path(path / 'host/state.json'))
    require(state.get('package_installation') == binding_snapshot(record), 'VERSION_CONFLICT')
    require(record['record_version'] == RECORD_VERSION and record['fixture'] == FIXTURE
            and record['approval_source'] == 'host-fixed-test-only-plan-v1', 'VERSION_CONFLICT')
    package, materials = snapshot(path / 'host/package'), snapshot(path / 'host/materials')
    require(file_hashes(package) == record['package_files'] == PACKAGE_FILES
            and file_hashes(materials) == record['materials_files'] == MATERIALS_FILES, 'VERSION_CONFLICT')
    require(record['package_tree_sha256'] == tree_hash(PACKAGE_FILES, 'package')
            and record['materials_tree_sha256'] == tree_hash(MATERIALS_FILES, 'materials')
            and record['toolchain'] == TOOL_FILES and record['helpers'] == []
            and record['implementation_file'] == IMPLEMENTATION and record['entrypoint'] == 'normalize'
            and record['abi'] == 'sync-json-v1' and record['implementation_sha256'] == PACKAGE_FILES[IMPLEMENTATION]
            and record['declaration_sha256'] == PACKAGE_FILES[DECLARATION], 'VERSION_CONFLICT')
    projection = json.loads(package['definitions/workflow-projection.json'])
    require(record['provider_ref'] == projection['nodes'][0]['executor_ref'], 'VERSION_CONFLICT')
    interpreter, dependencies = runtime_identity()
    require(record['interpreter'] == interpreter and record['dependencies'] == dependencies, 'VERSION_CONFLICT')
    require(record['adapter'] == {'version': 'python-component-v1', 'sha256': sha256(adapter_bytes())}, 'VERSION_CONFLICT')
    return record, package, projection


def binding_snapshot(record):
    return {k: deepcopy(record[k]) for k in ('record_version', 'installation_id', 'record_digest',
                                            'provider_ref', 'implementation_sha256', 'adapter')}


def install_package(package_root, materials_root, sandbox, *, trusted_plan):
    require(trusted_plan is _PLAN, 'UNAUTHORIZED')
    fault = os.environ.get('WF2_INSTALL_FAULT')
    require(fault in {None, 'after_snapshot', 'before_activate', 'after_activate'}, 'INPUT_INVALID')
    destination = safe_path(sandbox)
    source, materials_path = plain_path(package_root), plain_path(materials_root)
    require(not source.is_relative_to(destination) and not destination.is_relative_to(source)
            and not materials_path.is_relative_to(destination) and not destination.is_relative_to(materials_path)
            and not source.is_relative_to(materials_path) and not materials_path.is_relative_to(source), 'SANDBOX_INVALID')
    package, materials = snapshot(source), snapshot(materials_path)
    require(file_hashes(package) == PACKAGE_FILES and file_hashes(materials) == MATERIALS_FILES, 'VERSION_CONFLICT')
    tools = tool_root()
    adapter = {'version': 'python-component-v1', 'sha256': sha256(adapter_bytes())}
    from .package_host import PackageHost
    if destination.exists():
        host = PackageHost(destination)
        with host.lock():
            verify_installation(destination)
            return load_json(destination / 'host/install-receipt.json')
    pending = safe_path(destination.with_name(destination.name + '.pending'))
    require(not pending.exists(), 'IN_PROGRESS')
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.mkdir()
    for name in ('host', 'runtime', 'requests', 'observations'):
        (pending / name).mkdir()
    save(pending / 'observations/install-pending.json', {'target': str(destination), 'pid': os.getpid(),
                                                      'active': False, 'synthetic_only': True})
    copy_snapshot(package, pending / 'host/package')
    copy_snapshot(materials, pending / 'host/materials')
    if fault == 'after_snapshot':
        os._exit(86)
    check_static(tools, pending / 'host/package', pending / 'host/materials', pending / 'observations/static-check.json')
    interpreter, dependencies = runtime_identity()
    projection = json.loads(package['definitions/workflow-projection.json'])
    record = {'record_version': RECORD_VERSION, 'installation_id': ident('installation'), 'fixture': FIXTURE,
              'provider_ref': projection['nodes'][0]['executor_ref'], 'package_files': PACKAGE_FILES,
              'package_tree_sha256': tree_hash(PACKAGE_FILES, 'package'), 'materials_files': MATERIALS_FILES,
              'materials_tree_sha256': tree_hash(MATERIALS_FILES, 'materials'), 'declaration_sha256': PACKAGE_FILES[DECLARATION],
              'implementation_file': IMPLEMENTATION, 'implementation_sha256': PACKAGE_FILES[IMPLEMENTATION],
              'helpers': [], 'entrypoint': 'normalize', 'abi': 'sync-json-v1', 'adapter': adapter,
              'interpreter': interpreter, 'dependencies': dependencies, 'toolchain': TOOL_FILES,
              'approval_source': 'host-fixed-test-only-plan-v1'}
    host = PackageHost(pending)
    receipt = host.initialize_package(record, projection, json.loads(materials['authority-records.json']))
    # Validate every file and P1/P2 before atomically exposing the directory.
    with host.lock():
        host.validate(host.resolve_binding(load_json(pending / 'requests/register.json')['payload']))
        host.state['storage_path'] = str(destination)
        save(pending / 'host/state.json', host.state)
    manifest = load_json(pending / 'manifest.json')
    manifest['path'] = str(destination)
    save(pending / 'manifest.json', manifest)
    receipt.update(manifest=str(destination / 'manifest.json'), register_request=str(destination / 'requests/register.json'))
    save(pending / 'host/install-receipt.json', receipt)
    require(not destination.exists(), 'IN_PROGRESS')
    if fault == 'before_activate':
        os._exit(86)
    pending.rename(destination)
    if fault == 'after_activate':
        os._exit(86)
    with PackageHost(destination).lock():
        verify_installation(destination)
    return receipt

PACKAGE_FILES = {'acceptance.md': 'a5082dfb00136edc289d88e1121de8b318c23f9b7002e9ae83c0ddf9a3c17380', 'components/normalize-submission/declaration.json': '6f716baba2b63859b779fb040829f9b80bac4666707e9528b643592c4a691db8', 'components/normalize-submission/implementation.py': 'd25077a74206f536c3fccc859903070d5bb8e14a67b706b28c3f7817d9269bf0', 'components/normalize-submission/test_normalize.py': '4483a68ea5655ee07d9f36edf90428ba54428fb5a4dbf8c2ab70bd9ca5e28144', 'definitions/workflow-projection.json': '01a5f4703274d056b673360d7248a1222aaacf01323d7b8ba5e9667ae94cc1b2', 'package-manifest.json': '8076994294d078e73081ebe50a2755366a4757622e62aafa137ec30b1d2b90ae', 'skills/development-SKILL.md': '690eede1b87a14e1814577f284e5d339eacd925a7f4f6a1ad3d722d65c097615', 'skills/runtime-SKILL.md': '88c942cd3e0865e5e92ea399f1a3462ba218c09e6e04b346310791cf3f0877d2'}
MATERIALS_FILES = {'README.md': '3d63d8f23cfe82fcdcb58a4d817398cfdf09cd8b392e5df50f80fdc7f6432335', 'authority-records.json': 'c321dc09a96feb1f637d4e69befd67a4b0b1f98663021dd1de56c50e4930cc42', 'workflow-projection.json': '01a5f4703274d056b673360d7248a1222aaacf01323d7b8ba5e9667ae94cc1b2'}
TOOL_FILES = {'PREFLIGHT.md': '61518c08cae37a28dc5c415ac8dcd6a44ef14ba81fee5b6f9c014125495cc874', 'docs/architecture-track/contracts/authority-contract.schema.json': '4599e93aa8b022fff3a480b566a0b056584863291af390594a8f6ce0570dbab9', 'docs/skill-toolchain/wf1-implementation.md': 'c262030ed0d27b8c289231ccc7e3e2bcb9aedeba5a174408d5e6e13c0b31d8ef', 'docs/skill-toolchain/wf1-verification.md': '8e196c0c0b535231e7e3defec498cd5fc6c752048bb55d278e1af4f0c2cb6b36', 'requirements-dev.txt': '78971f58d73bbb30a41f6d5b0a391be0c4e5108d7e6e96dda806be2885c4d048', 'skills/workflow-author/SKILL.md': 'a07cd9f05413833926811c256afa24cb06341f5f55565391d9c72ddfb31029e0', 'skills/workflow-author/references/author-guide.md': '690eede1b87a14e1814577f284e5d339eacd925a7f4f6a1ad3d722d65c097615', 'skills/workflow-author/templates/runtime-SKILL.md': '88c942cd3e0865e5e92ea399f1a3462ba218c09e6e04b346310791cf3f0877d2', 'spikes/002-authority-contract/validator.py': 'd67e3ac3c8f29c4f561978c5a86828514b3313d74bdd321a64c9c11747c1b2ab', 'tests/workflow_author/conftest.py': 'd2e8eb7c7ad0dd3336639b95c9e3daef03e502838ad16d53462c0821ed6e9b56', 'tests/workflow_author/test_checks.py': '29dd48c254373837625a641ce7bf79eca43410f1164e5109aa92a729bab0fde7', 'tests/workflow_author/test_cli.py': 'd6c39d2cb7f000bb0be82d311f62625f7160ee909e9f2231fead91619e6454c8', 'tests/workflow_author/test_component.py': '9ac4f22cafe6985d3be641b4ca56c2d0d3f5d07dba623dcac42b768862eb1bd6', 'tests/workflow_author/test_contracts.py': 'ecd3d3fab47f0c8f28b4aa6f398aeb97d4f193c3a2180c1e8f52e04e72cdb353', 'tests/workflow_author/test_generation.py': '2e89f1e79ed04e09456ede5bded9955a4b68206536ce9d5e0eeecb552313edf3', 'tests/workflow_author/test_paths.py': 'adf68fed8f97712059dcf8046b3681209380afa157b0453acef069276333c220', 'tests/workflow_author/test_skill_assets.py': 'c5e79ae18b9009e28c15427a1b14761ca8cadb9f9e9f93c97685ae4617e5807a', 'tests/workflow_author/test_synthetic_host.py': '8e2c676240e0c6b64ab83155816f986812ff02c00c384c908e58ee41500e04c2', 'tools/workflow_author.py': '1a729f2eff3ee397406f7ac78101ad94537050da2b2ab86da26e4e3900757378', 'tools/workflow_author_synthetic.py': '071d9db2fd5bc1be7d737fcacbb6fc6721efa36106195eecd2bd57dcd2f27dc4', 'workflow_author/__init__.py': 'f4ba0b780ff5702dbbb9c620d2f9f062278df5da4a4175d3de0df84b860d6733', 'workflow_author/authority_bridge.py': '1c9e7b23e57e576a37b4ecc14454e45dcbbacf024e1d130950750142c2cc4f34', 'workflow_author/checker.py': '2da2d53c21bb605a3940f49445313b89bdd23908d88dc141af567477d3b32ed7', 'workflow_author/cli.py': '34037a14702b4f4b42f2b2c5750d15d2ab7354e408720fe81defefb00bd033b8', 'workflow_author/contracts.py': 'd3b7dd866ca18a48e2e0839a7bfbefaa2cd22b2c247213141e5cce68e8e8db21', 'workflow_author/generator.py': '8a1ab811fa6553bfbf5f11b460e8734446e5f7bf7d416c69a61b9855fd944604', 'workflow_author/safety.py': '1e55ab97761a51cd1d6f5cdfd76c1981f9946e2c4de0b57132442892543fe303', 'workflow_author/synthetic_host.py': '07168b6a4bf459916db9584c93cf8df3bf0f21a18fcf81130981349dc169b991', 'workflow_author/templates.py': '0850f3190b004dccdd158c3438ab19f595ba7a1580e8056861de3985c0b1eb41'}
