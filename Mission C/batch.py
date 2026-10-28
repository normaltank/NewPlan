"""Public batch command line. JSON on stdout; collector progress goes to stderr."""
import argparse
import json
from pathlib import Path
from mission_c.batch import BatchService, preview


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mission C 持久 Excel 批次')
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parent/'data')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('preview','import'):
        sub.add_parser(command).add_argument('paths', nargs='+', type=Path)
    sub.add_parser('list')
    for command in ('status','pause','resume'):
        sub.add_parser(command).add_argument('id')
    args = parser.parse_args(argv)
    try:
        if args.command == 'preview': result = preview(args.paths)
        else:
            service = BatchService(args.data_root)
            if args.command == 'import': result = service.import_files(args.paths)
            elif args.command == 'list': result = service.list_batches()
            else: result = getattr(service,args.command)(args.id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')

if __name__ == '__main__':
    raise SystemExit(main())
