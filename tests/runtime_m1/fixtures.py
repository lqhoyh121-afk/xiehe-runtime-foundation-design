"""Independent SYNTHETIC CLI harness. Expected facts come from RC0. Laiqh."""
from pathlib import Path
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'tools/runtime_core_cli.py'


class Harness:
    def __init__(self):
        self.sandbox = ROOT / '.local' / ('test-m1-' + uuid.uuid4().hex)
        self.commands = []

    def call(self, *args, code=0):
        p = subprocess.run([sys.executable, '-B', str(CLI), '--sandbox', str(self.sandbox), *args],
                           cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=50)
        self.commands.append({'args': args, 'code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        assert p.returncode == code, self.commands[-1]
        if code == 86:
            return None
        result = json.loads(p.stdout)
        assert result['synthetic_only'] is True
        assert result['production_authorized'] is False
        assert result['contract_status'] == 'DRAFT'
        return result

    def request(self, command, payload, key=None, code=0, request_id=None):
        key = key or 'key-' + uuid.uuid4().hex
        body = {'request_id': request_id or 'req-' + uuid.uuid4().hex,
                'idempotency_key': key, 'payload': payload}
        path = self.sandbox / 'requests' / ('req-' + uuid.uuid4().hex + '.json')
        path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        return self.call(command, '--request', str(path), code=code)

    def init(self):
        return self.call('host-init')['result']

    def register(self):
        return self.call('register', '--request', str(self.sandbox / 'requests/register.json'))['result']

    def setup(self):
        self.initial = self.init()
        self.registration = self.register()['registration_id']
        self.request('set-state', {'registration_id': self.registration,
                                  'expected_revision': 1, 'target_state': 'ENABLED'})
        self.create_payload = {'registration_id': self.registration, 'input_ref': self.initial['input_ref'],
                               'object_refs': self.initial['object_refs']}
        return self

    def create(self, key='create-one'):
        self.created = self.request('create', self.create_payload, key=key)['result']
        self.case = self.created['case_id']
        return self.created

    def rows(self):
        path = self.sandbox / 'runtime/runtime.sqlite'
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {n: db.execute('SELECT * FROM "' + n + '" ORDER BY rowid').fetchall() for n in names}

    def save(self):
        out = ROOT / '.local/test-evidence'
        out.mkdir(exist_ok=True)
        (out / (self.sandbox.name + '.json')).write_text(json.dumps(self.commands, indent=2), encoding='utf-8')

    def cleanup(self):
        self.save()
        if self.sandbox.exists() and (self.sandbox / 'manifest.json').exists():
            self.call('host-cleanup', '--manifest', str(self.sandbox / 'manifest.json'))
            assert not self.sandbox.exists()
