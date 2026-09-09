"""Local input-contract CLI. All data/results are explicitly non-production."""
import argparse
import json
import sys
from pathlib import Path

from business import evaluate
from input_contract import ContractError, ExcelSource, SQLiteSource, digest, load_snapshot, read_json, timestamp
from snapshot_store import save_snapshot


def main():
    parser = argparse.ArgumentParser(description='SPIKE ONLY — validate local Excel/SQLite with one model')
    parser.add_argument('--source', choices=['excel', 'sqlite'], required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--objects', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--collection', required=True, help='Excel sheet or SQLite table')
    parser.add_argument('--as-of', required=True, help='Explicit evaluation time; demo uses a synthetic clock')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; existing path refused')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ContractError('OUTPUT_EXISTS')
        binding = read_json(args.binding)
        mapping = read_json(args.mapping)
        source = (ExcelSource if args.source == 'excel' else SQLiteSource)(args.input, args.collection, mapping)
        snapshot = load_snapshot(args.model, args.objects, source, binding['model_ref'], timestamp(args.as_of))
        result = evaluate(snapshot, binding)
        args.output.mkdir(parents=True, exist_ok=False)
        snapshot_path = save_snapshot(snapshot, args.output/'snapshots')
        report = {'status': 'validated_local_demo', 'synthetic_demo': True,
                  'source_kind': args.source, 'snapshot_id': snapshot.snapshot_id,
                  'semantic_digest': snapshot.semantic_digest, 'snapshot_file': str(snapshot_path.resolve()),
                  'model_ref': snapshot.to_dict()['model_ref'], 'binding_digest': digest(binding),
                  'result': result}
        with (args.output/'result.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except ContractError as exc:
        print(json.dumps({'status': 'blocked', 'code': exc.code, 'detail': str(exc), 'synthetic_demo': True}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'code': 'LOCAL_IO_OR_CONFIG_ERROR', 'detail': type(exc).__name__}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
