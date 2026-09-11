"""Tests use disposable local paths and independent fixed expected values. Laiqh."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def cli(*args, synthetic=False, cwd=None):
    entry = 'workflow_author_synthetic.py' if synthetic else 'workflow_author.py'
    p = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / entry), *map(str, args)],
                       cwd=cwd or ROOT, capture_output=True, text=True, encoding='utf-8')
    return p, json.loads(p.stdout)


def hashes(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def put_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.fixture
def draft(tmp_path):
    from workflow_author.generator import generate
    path = tmp_path / 'package'
    assert generate(path)['status'] == 'CREATED'
    return path


# Independent author implementation and test expectations, not generator output.
IMPLEMENTATION = '''def normalize(value):
    if not isinstance(value, dict) or set(value) != {'text'} or not isinstance(value['text'], str):
        raise ValueError('MODEL_REJECTED')
    normalized = value['text'].strip(' ')
    return {'normalized': normalized}
'''
COMPONENT_TEST = '''from implementation import normalize

def test_independent_expected_result():
    data = {'text': '  SYNTHETIC  sample  '}
    assert normalize(data) == {'normalized': 'SYNTHETIC  sample'}
    assert data == {'text': '  SYNTHETIC  sample  '}
'''


@pytest.fixture
def completed(draft, tmp_path):
    from workflow_author.synthetic_host import prepare
    materials = tmp_path / 'materials'
    assert prepare(materials)['status'] == 'CREATED'
    (draft / 'definitions/workflow-projection.json').write_bytes((materials / 'workflow-projection.json').read_bytes())
    manifest_path = draft / 'package-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['candidate_state'] = 'candidate'
    put_json(manifest_path, manifest)
    component_path = draft / 'components/normalize-submission/declaration.json'
    component = json.loads(component_path.read_text(encoding='utf-8'))
    component['implementation_state'] = 'implemented'
    put_json(component_path, component)
    (draft / component['implementation_file']).write_text(IMPLEMENTATION, encoding='utf-8')
    (draft / component['test_files'][0]).write_text(COMPONENT_TEST, encoding='utf-8')
    (draft / 'acceptance.md').write_text('''# Static acceptance / Laiqh
## 输入
text: "  SYNTHETIC  sample  "
## 独立预期
normalized: "SYNTHETIC  sample"; input unchanged; invalid model/rule rejected separately.
## 检查子集
single-code-output-v1; metadata only.
## 材料来源
Explicit synthetic prepare; namespace synthetic; no production permission.
## 人工/运行未验证项
No core, real Provider, activation or business verification; component tests separate.
## 待决表达
None used; I3/I4/I6 not applicable to this example.
''', encoding='utf-8')
    return draft, materials
