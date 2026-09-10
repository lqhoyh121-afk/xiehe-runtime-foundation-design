"""Foreground-only, local SYNTHETIC M1 CLI. Laiqh."""
from pathlib import Path
import argparse
import json
import os
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from runtime_core.contract_adapter import ContractError, load_json, require
from runtime_core.service import Service
from runtime_core.synthetic_host import Host, ident, safe_path
from runtime_core.worker import Worker

FLAGS = {'synthetic_only': True, 'production_authorized': False, 'contract_status': 'DRAFT'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractError('INPUT_INVALID')


def main():
    operation = 'parse'
    process_marker = None
    try:
        parser = Parser(add_help=False, allow_abbrev=False)
        parser.add_argument('--sandbox', required=True)
        parser.add_argument('operation')
        parser.add_argument('--request')
        parser.add_argument('--manifest')
        parser.add_argument('--case-id')
        parser.add_argument('--scenario')
        args, extra = parser.parse_known_args()
        operation = args.operation
        require(not extra, 'CAPABILITY_UNSUPPORTED')
        expected = {'host-init': set(), 'host-inspect': set(), 'host-cleanup': {'manifest'},
                    'host-control': {'scenario'}, 'host-test': {'scenario', 'case_id'},
                    'register': {'request'}, 'set-state': {'request'}, 'create': {'request'},
                    'run-once': {'case_id'}, 'snapshot': {'case_id'}, 'events': {'case_id'}}
        require(operation in expected, 'CAPABILITY_UNSUPPORTED')
        supplied = {k for k in ('request', 'manifest', 'case_id', 'scenario') if getattr(args, k) is not None}
        require(supplied == expected[operation], 'INPUT_INVALID')
        flags = [x.split('=', 1)[0] for x in sys.argv[1:] if x.startswith('--')]
        require(len(flags) == len(set(flags)), 'INPUT_INVALID')
        host = Host(args.sandbox)
        if operation not in {'host-init', 'host-cleanup'}:
            process_marker = host.start_process()
        if operation == 'host-init':
            require(args.request is None and args.manifest is None, 'INPUT_INVALID')
            response = {'result': host.initialize()}
        elif operation == 'host-cleanup':
            require(args.manifest is not None and args.request is None, 'INPUT_INVALID')
            response = {'result': host.cleanup(args.manifest)}
        elif operation == 'host-inspect':
            response = {'result': host.inspect()}
        elif operation == 'host-control':
            require(args.scenario is not None and args.request is None and args.manifest is None and args.case_id is None, 'INPUT_INVALID')
            response = {'result': host.control(args.scenario)}
        elif operation == 'host-test':
            require(args.scenario is not None and args.case_id is not None and args.request is None and args.manifest is None, 'INPUT_INVALID')
            if args.scenario == 'event-overflow':
                response = {'result': host.event_overflow_fixture(args.case_id)}
            elif args.scenario == 'snapshot-barrier':
                response = Service(host).query('snapshot', args.case_id, host.query_barrier)
            else:
                response = Worker(host).test(args.case_id, args.scenario)
        elif operation in {'run-once', 'snapshot', 'events'}:
            require(args.case_id is not None and args.request is None and args.manifest is None, 'INPUT_INVALID')
            response = Worker(host).run(args.case_id) if operation == 'run-once' else Service(host).query(operation, args.case_id)
        elif operation in {'register', 'set-state', 'create'}:
            require(args.request is not None and args.manifest is None, 'INPUT_INVALID')
            request = load_json(safe_path(args.request))
            response = Service(host).execute(operation, request, 'initiator' if operation == 'create' else 'admin')
        else:
            raise ContractError('CAPABILITY_UNSUPPORTED')
        print(json.dumps({**FLAGS, 'operation': operation, 'pid': os.getpid(), **response}, ensure_ascii=False))
        return 0
    except ContractError as exc:
        code = exc.code
    except sqlite3.OperationalError as exc:
        code = 'IN_PROGRESS' if 'locked' in str(exc).lower() else 'STORAGE_INVALID'
    except (sqlite3.DatabaseError, OSError, ValueError, KeyError, TypeError):
        code = 'STORAGE_INVALID'
    except Exception:
        code = 'INTERNAL_ERROR'
    finally:
        if process_marker is not None:
            process_marker.unlink(missing_ok=True)
    temporary = code in {'IN_PROGRESS', 'DEPENDENCY_UNAVAILABLE', 'AUTHORITY_UNAVAILABLE'}
    exit_code = 3 if temporary else 4 if code in {'STORAGE_INVALID', 'INTERNAL_ERROR'} else 2
    retry = 'after_backoff' if temporary else 'after_input' if code == 'INPUT_STALE' else 'never'
    print(json.dumps({**FLAGS, 'operation': operation, 'code': code, 'safe_message': 'M1 command rejected',
                      'retry_class': retry, 'correlation_id': ident('trace')}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
