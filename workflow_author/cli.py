"""Stable author command/report boundary. No untrusted module loading. Laiqh."""
import argparse
import json
from .contracts import EXIT_CODES, diagnostic, report


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs['allow_abbrev'] = False
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise UsageError()


def main(argv=None, *, synthetic=False):
    parser = Parser(add_help=False)
    commands = parser.add_subparsers(dest='operation', required=True, parser_class=Parser)
    create = commands.add_parser('prepare' if synthetic else 'init', add_help=False)
    create.add_argument('--output', required=True)
    if not synthetic:
        create.add_argument('--template', required=True)
    check = commands.add_parser('check', add_help=False)
    check.add_argument('--package', required=True)
    if synthetic:
        check.add_argument('--materials', required=True)
    for command in [create, check]:
        command.add_argument('--format', choices=['json', 'text'], default='json')
    fmt = 'json'
    try:
        args = parser.parse_args(argv)
        fmt = args.format
        if synthetic:
            from .synthetic_host import prepare, check_synthetic
            result = prepare(args.output) if args.operation == 'prepare' else check_synthetic(args.package, args.materials)
        elif args.operation == 'init':
            from .generator import generate
            result = generate(args.output, args.template)
        else:
            from .checker import check_package
            result = check_package(args.package)
    except UsageError:
        result = report('usage', 'USAGE_ERROR', diagnostics=[diagnostic('AUTH-USAGE', message='Invalid arguments; use documented command and options.')])
    except Exception:
        result = report('unknown', 'INTERNAL_ERROR', diagnostics=[diagnostic('AUTH-INTERNAL', message='Unexpected tool failure; no input details are disclosed.')])
    if synthetic:
        result['synthetic_only'] = True
    if fmt == 'json':
        print(json.dumps(result, ensure_ascii=True))
    else:
        print(result['status'] + ' | ' + str(result['profile']))
        for item in result['diagnostics']:
            parts = [item['id']]
            if item['source_code']:
                parts.append('source_code=' + item['source_code'])
            if item['file']:
                parts.append('file=' + item['file'])
            if item['pointer']:
                parts.append('pointer=' + item['pointer'])
            if item['line'] is not None:
                parts.append('line=' + str(item['line']))
            if item['column'] is not None:
                parts.append('column=' + str(item['column']))
            print(' | '.join(parts) + ': ' + item['message'])
            print('  remediation: ' + item['remediation'])
        print('runtime_verified=false production_authorized=false')
        if synthetic:
            print('synthetic_only=true')
    return EXIT_CODES[result['status']]
