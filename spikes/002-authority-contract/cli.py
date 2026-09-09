"""DRAFT offline CLI. --demo is SYNTHETIC; no production Adapter exists."""
import argparse
import json
from validator import ContractError, load_json
from migration_checks import check_migration


def denied(code, synthetic):
    return {'verdict': 'REJECTED', 'code': code, 'contract_status': 'DRAFT',
            'synthetic_only': synthetic, 'production_authorized': False,
            'migration_executed': False}


def demo_cases():
    from migration_fixtures import migration_fixture, install_migration
    scenarios = [
        ('normal', None, None, None),
        ('old-right-active', 'source_grant', 'status', 'ACTIVE'),
        ('old-executor-running', 'stop', 'state', 'RUNNING'),
        ('stale-checkpoint', 'checkpoint', 'control_revision', 11),
        ('missing-capability', 'control', 'target_capabilities', []),
        ('unknown', 'control', 'state', 'UNKNOWN'),
    ]
    cases = []
    for name, record, field, value in scenarios:
        f = migration_fixture()
        if record:
            getattr(f, record)[field] = value
            install_migration(f)
        try:
            result = check_migration(f.migration, f.authority, f.context)
        except ContractError as exc:
            result = denied(exc.code, True)
        cases.append({'case': name, **result})
    return {'contract_status': 'DRAFT', 'synthetic_only': True,
            'production_authorized': False, 'migration_executed': False,
            'cases': cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--demo', action='store_true', help='Use only built-in SYNTHETIC host records')
    parser.add_argument('--request', metavar='JSON', help='Read-only migration request; never a trust file')
    args = parser.parse_args(argv)
    try:
        # Fail before loading caller files. There is no production trust path,
        # environment fallback, approved flag, context file or dynamic import.
        if not args.demo:
            raise ContractError('TRUSTED_ADAPTER_REQUIRED')
        if args.request:
            from migration_fixtures import migration_fixture
            f = migration_fixture()
            result = check_migration(load_json(args.request), f.authority, f.context)
        else:
            result = demo_cases()
    except ContractError as exc:
        print(json.dumps(denied(exc.code, args.demo), sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
