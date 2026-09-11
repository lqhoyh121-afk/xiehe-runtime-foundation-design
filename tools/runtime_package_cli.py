"""Foreground TEST ONLY package CLI; core transitions remain in Service. Laiqh."""
from pathlib import Path
import argparse
import json
import os
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from runtime_core.contract_adapter import ContractError, load_json, require
from runtime_core.package_host import PackageHost
from runtime_core.package_install import StaticCheckError, install_package, trusted_plan
from runtime_core.service import Service
from runtime_core.synthetic_host import ident, safe_path
from runtime_core.worker import Worker

FLAGS = {'synthetic_only': True, 'production_authorized': False, 'contract_status': 'DRAFT',
         'scope': 'single-node-package-pilot-not-full-WF2'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractError('INPUT_INVALID')


def main():
    operation, phase, process_marker = 'parse', 'arguments', None
    try:
        parser = Parser(add_help=False, allow_abbrev=False)
        parser.add_argument('--sandbox', required=True)
        parser.add_argument('operation')
        fields = ('package', 'materials', 'fixture', 'request', 'manifest', 'cleanup_digest', 'case_id', 'scenario')
        for name in fields:
            parser.add_argument('--' + name.replace('_', '-'))
        args, extra = parser.parse_known_args()
        operation = args.operation
        expected = {'install': {'package', 'materials', 'fixture'}, 'install-inspect': set(),
                    'register': {'request'}, 'set-state': {'request'}, 'create': {'request'},
                    'run-once': {'case_id'}, 'snapshot': {'case_id'}, 'events': {'case_id'},
                    'host-cleanup': {'manifest'}, 'host-control': {'scenario'}, 'host-test': {'scenario', 'case_id'}}
        require(not extra and operation in expected, 'CAPABILITY_UNSUPPORTED')
        provided = {name for name in fields if getattr(args, name) is not None}
        required = expected[operation]
        require(provided == required or (operation == 'host-cleanup' and provided == required | {'cleanup_digest'}),
                'INPUT_INVALID')
        flags = [x.split('=', 1)[0] for x in sys.argv[1:] if x.startswith('--')]
        require(len(flags) == len(set(flags)), 'INPUT_INVALID')
        host = PackageHost(args.sandbox)
        phase = 'installation' if operation == 'install' else 'runtime'
        if operation == 'install':
            result = install_package(args.package, args.materials, args.sandbox, trusted_plan=trusted_plan(args.fixture))
            response = {'result': result}
        elif operation == 'host-cleanup':
            response = {'result': host.cleanup(args.manifest, args.cleanup_digest)}
        else:
            process_marker = host.start_process()
            if operation == 'install-inspect':
                response = {'result': host.install_inspect()}
            elif operation == 'host-control':
                response = {'result': host.control(args.scenario)}
            elif operation == 'host-test':
                response = Worker(host).test(args.case_id, args.scenario)
            elif operation in {'snapshot', 'events'}:
                response = Service(host).query(operation, args.case_id)
            elif operation == 'run-once':
                response = Worker(host).run(args.case_id)
            else:
                request = load_json(safe_path(args.request))
                host.remember_request(safe_path(args.request))
                response = Service(host).execute(operation, request, 'initiator' if operation == 'create' else 'admin')
        print(json.dumps({**FLAGS, 'operation': operation, 'phase': phase, 'pid': os.getpid(), **response}, ensure_ascii=False))
        return 0
    except StaticCheckError as exc:
        print(json.dumps({**FLAGS, 'operation': operation, 'phase': 'static-check', 'code': exc.code,
                          'source_status': exc.report.get('status'), 'source_exit': exc.source_exit,
                          'report': exc.report, 'pid': os.getpid()}, ensure_ascii=False))
        return exc.source_exit if exc.source_exit else 2
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
    print(json.dumps({**FLAGS, 'operation': operation, 'phase': phase, 'code': code, 'pid': os.getpid(),
                      'safe_message': 'Package command rejected', 'retry_class': retry, 'correlation_id': ident('trace')}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
