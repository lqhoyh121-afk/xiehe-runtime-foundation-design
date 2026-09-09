"""Runs the delivered CLI twice against generated fixtures and independently reads results."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from demo_fixtures import CLOCK, prepare_demo
from snapshot_store import read_snapshot


def main():
    parser = argparse.ArgumentParser(description='真实文件验证，合成数据；不是生产业务演示')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    if root.exists():
        parser.error('Output directory exists; choose a new directory. Nothing overwritten.')
    root.mkdir(parents=True)
    fixtures = root/'fixtures'
    prepare_demo(fixtures)
    code = Path(__file__).resolve().parent
    before = hashlib.sha256((code/'business.py').read_bytes()).hexdigest()
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.iterdir()}
    reports = []
    runs = []
    for kind, filename, collection in [('excel', 'input.xlsx', 'Observations'), ('sqlite', 'input.sqlite3', 'observations')]:
        command = [sys.executable, '-B', str(code/'cli.py'), '--source', kind,
                   '--input', str(fixtures/filename), '--model', str(fixtures/'model.json'),
                   '--objects', str(fixtures/'objects.json'), '--binding', str(fixtures/'business.json'),
                   '--mapping', str(fixtures/(kind+'-mapping.json')), '--collection', collection,
                   '--as-of', CLOCK, '--output', str(root/kind)]
        completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
        runs.append({'source': kind, 'command': command, 'exit_code': completed.returncode,
                     'stdout': completed.stdout, 'stderr': completed.stderr})
        if completed.returncode:
            (root/'failed-runs.json').write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding='utf-8')
            return completed.returncode
        report = json.loads((root/kind/'result.json').read_text(encoding='utf-8'))
        snapshot = read_snapshot(Path(report['snapshot_file']))
        if snapshot.snapshot_id != report['snapshot_id']:
            raise RuntimeError('Snapshot readback mismatch')
        reports.append(report)
    expected = [{'object_ref': 'DEMO-ASSET-A', 'verdict': 'WITHIN_LIMIT'},
                {'object_ref': 'DEMO-ASSET-B', 'verdict': 'OVER_LIMIT'}]
    checks = {
        'same_semantic_facts': reports[0]['semantic_digest'] == reports[1]['semantic_digest'],
        'independent_expected_decisions': all(r['result']['decisions'] == expected for r in reports),
        'distinct_source_snapshots': reports[0]['snapshot_id'] != reports[1]['snapshot_id'],
        'same_model_binding': reports[0]['model_ref'] == reports[1]['model_ref'],
        'handler_unchanged': before == hashlib.sha256((code/'business.py').read_bytes()).hexdigest(),
        'sources_unchanged': source_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.iterdir()},
    }
    summary = {'status': 'PASS' if all(checks.values()) else 'FAIL',
               'synthetic_demo': True, 'clock': CLOCK, 'checks': checks,
               'business_handler_sha256': before, 'runs': runs,
               'limitations': ['Not connected to runtime core', 'Not clean-machine deployment',
                               'No production data or external writes', 'No human-path acceptance']}
    with (root/'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'status': summary['status'], 'checks': checks, 'summary': str(root/'summary.json')}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
