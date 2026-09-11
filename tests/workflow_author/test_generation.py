"""Independent generation acceptance through the real entry. Laiqh."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'tools/workflow_author.py'


def run(*args):
    return subprocess.run([sys.executable, '-B', str(CLI), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8')


def test_init_creates_draft_and_never_overwrites(tmp_path):
    target = tmp_path / '新作者 包'
    result = run('init', '--template', 'single-code-output-v1', '--output', target)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['status'] == 'CREATED'
    assert report['runtime_verified'] is False
    manifest = json.loads((target / 'package-manifest.json').read_text())
    assert manifest['candidate_state'] == 'draft'
    assert manifest['author_contract_version'] == '0.1.0'
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
    again = run('init', '--template', 'single-code-output-v1', '--output', target)
    assert again.returncode == 5
    assert json.loads(again.stdout)['status'] == 'CONFLICT'
    assert before == {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}


def test_two_real_creators_compete_without_overwrite(tmp_path):
    target = tmp_path / 'race'
    command = [sys.executable, '-B', str(CLI), 'init', '--template', 'single-code-output-v1', '--output', str(target)]
    procs = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [(p, p.communicate(timeout=20)) for p in procs]
    assert sorted(p.returncode for p, _ in results) == [0, 5]
    assert sorted(json.loads(out[0])['status'] for _, out in results) == ['CONFLICT', 'CREATED']
    assert not (target / '.workflow-author.lock').exists()


def test_injected_partial_write_rolls_back_only_owned_files(tmp_path, monkeypatch):
    from workflow_author.generator import generate
    target = tmp_path / 'failed'
    original = Path.open

    class Partial:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def fileno(self):
            return self.stream.fileno()
        def write(self, data):
            self.stream.write(data[:4]); self.stream.flush()
            raise OSError('injected partial failure')
        def __exit__(self, *args):
            self.stream.close()

    def failing(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        return Partial(stream) if path.name == 'workflow-projection.json' and args and args[0] == 'xb' else stream

    monkeypatch.setattr(Path, 'open', failing)
    result = generate(target)
    assert result['status'] == 'CONFLICT'
    assert not target.exists() or not list(target.iterdir())


def test_foreign_file_created_mid_generation_is_preserved(tmp_path, monkeypatch):
    from workflow_author.generator import generate
    target = tmp_path / 'interference'
    original = Path.open

    def interfere(path, *args, **kwargs):
        if path.name == 'workflow-projection.json' and args and args[0] == 'xb':
            with original(target / 'foreign.txt', 'w') as stream:
                stream.write('owned by another writer')
            raise FileExistsError('injected conflict')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', interfere)
    result = generate(target)
    assert result['status'] == 'CONFLICT'
    assert (target / 'foreign.txt').read_text() == 'owned by another writer'
    assert not (target / 'package-manifest.json').exists()
