"""Capture real command exit/output; refuse to overwrite evidence."""
import datetime
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
name, *command = sys.argv[1:]
if command and command[0] == 'python':
    command[0] = sys.executable  # Windows child search may pick base Python.
evidence = root / 'evidence'
evidence.mkdir(exist_ok=True)
log = evidence / (name + '.json')
if log.exists():
    raise SystemExit('Evidence exists; use a new name')
result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
data = {'command': command, 'cwd': str(root), 'recorded_at': datetime.datetime.now().astimezone().isoformat(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
log.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(data, ensure_ascii=False, indent=2))
raise SystemExit(result.returncode)
