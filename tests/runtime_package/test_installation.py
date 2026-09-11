"""Trusted installation and immutable identity acceptance. Laiqh."""
from pathlib import Path
from contextlib import closing
import importlib.util
import json
import runpy
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
helpers = runpy.run_path(str(Path(__file__).with_name('fixtures.py')))
generated = helpers['generated']


def test_generated_package_installs_with_independent_p2_and_stable_identity(monkeypatch):
    assert importlib.util.find_spec('runtime_core.package_install') is not None, 'Trusted installer is missing'
    from runtime_core.package_install import install_package, trusted_plan
    from runtime_core.package_host import PackageHost
    from runtime_core.contract_adapter import load_json
    with generated() as g:
        monkeypatch.setenv('WF2_TOOL_ROOT', str(helpers['TOOL_ROOT']))
        first = install_package(g.package, g.materials, g.sandbox, trusted_plan=trusted_plan('normalize-l3-v1'))
        record = load_json(g.sandbox / 'host/installation.json')
        assert first['installation_id'] == record['installation_id']
        assert record['implementation_sha256'] == 'd25077a74206f536c3fccc859903070d5bb8e14a67b706b28c3f7817d9269bf0'
        assert record['helpers'] == [] and record['entrypoint'] == 'normalize'
        assert record['package_tree_sha256'] == '40feb41e0f10f258e03beb9c543a055a2bd7403800f0f129b7766c3ce089e03d'
        host = PackageHost(g.sandbox)
        with host.lock():
            payload = load_json(first['register_request'])['payload']
            assert set(payload) == {'business_ref', 'definition_ref', 'contract_version', 'provider_bindings', 'admission_ref'}
            binding = host.resolve_binding(payload)
            host.validate(binding)
            assert binding['package_installation']['record_digest'] == record['record_digest']
            with closing(host.store.connect(readonly=True)) as db:
                assert db.execute('SELECT count(*) FROM registrations').fetchone()[0] == 0
                assert db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
        second = install_package(g.package, g.materials, g.sandbox, trusted_plan=trusted_plan('normalize-l3-v1'))
        assert second == first
        assert helpers['hashes'](g.sandbox / 'host/package') == helpers['hashes'](g.package)


def test_self_rehashed_installation_identity_is_not_trusted():
    from runtime_core.contract_adapter import digest
    with generated() as g:
        initial = g.cli('install', '--package', str(g.package), '--materials', str(g.materials),
                        '--fixture', 'normalize-l3-v1')['result']
        path = g.sandbox / 'host/installation.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['installation_id'] = 'installation-forged'
        record['record_digest'] = digest({k: v for k, v in record.items() if k != 'record_digest'})
        helpers['dump'](path, record)
        denied = g.cli('install-inspect', expected=2)
        assert denied['code'] == 'VERSION_CONFLICT'


def test_cleanup_refuses_unowned_nested_file_before_deleting_anything():
    with generated() as g:
        g.cli('install', '--package', str(g.package), '--materials', str(g.materials), '--fixture', 'normalize-l3-v1')
        stranger = g.sandbox / 'host/stranger.txt'
        stranger.write_bytes(b'unowned sentinel')
        before = helpers['hashes'](g.sandbox)
        denied = g.cli('host-cleanup', '--manifest', str(g.sandbox / 'manifest.json'), expected=2)
        assert denied['code'] == 'SANDBOX_INVALID'
        assert helpers['hashes'](g.sandbox) == before
        stranger.unlink()  # Only the injected sentinel is ours to remove.


def test_cleanup_refuses_hardlinked_file_before_deleting_anything():
    import os
    with generated() as g:
        g.cli('install', '--package', str(g.package), '--materials', str(g.materials), '--fixture', 'normalize-l3-v1')
        link = g.root / 'owned-hardlink'
        os.link(g.sandbox / 'host/installation.json', link)
        denied = g.cli('host-cleanup', '--manifest', str(g.sandbox / 'manifest.json'), expected=2)
        assert denied['code'] == 'SANDBOX_INVALID'
        assert g.sandbox.is_dir() and link.is_file()
        link.unlink()
