"""Relocation probe; same interpreter, explicitly not clean-machine acceptance."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    src = Path(__file__).resolve().parent
    names = ['input_contract.py', 'business.py', 'snapshot_store.py', 'cli.py', 'demo.py', 'demo_fixtures.py']
    with tempfile.TemporaryDirectory(prefix='契约 relocation ') as temporary:
        target = Path(temporary)
        for name in names:
            shutil.copy2(src/name, target/name)
        env = dict(os.environ, PYTHONUTF8='1')
        env.pop('PYTHONPATH', None)
        result = subprocess.run([sys.executable, '-B', str(target/'demo.py'), '--output-dir', str(target/'验收 输出')],
                                cwd=target, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
        summary = json.loads((target/'验收 输出'/'summary.json').read_text(encoding='utf-8')) if result.returncode == 0 else None
        evidence = {'exit_code': result.returncode, 'checks': summary['checks'] if summary else {},
                    'stderr': result.stderr, 'scope': 'relocated source; same installed interpreter; NOT clean-machine acceptance'}
    print(json.dumps(evidence, ensure_ascii=False))
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
