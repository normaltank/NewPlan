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
    sub.add_parser('demo')
    for command in ('status','pause','resume'):
        sub.add_parser(command).add_argument('id')
    run = sub.add_parser('run')
    run.add_argument('id')
    run.add_argument('--cache-manifest', type=Path)
    run.add_argument('--live', action='store_true')
    run.add_argument('--max-items', type=int)
    run.add_argument('--fetch-mode', choices=['off','fallback','supplement'],default='off')
    run.add_argument('--model-mode', choices=['off','assist'],default='off')
    run.add_argument('--allow-paid', action='store_true')
    run.add_argument('--paid-max-calls',type=int,default=0)
    enqueue = sub.add_parser('enqueue', parents=[], help='保存显式运行选项；不启动执行')
    enqueue.add_argument('id')
    enqueue.add_argument('--cache-manifest',type=Path)
    enqueue.add_argument('--live',action='store_true')
    enqueue.add_argument('--fetch-mode',choices=['off','fallback','supplement'],default='off')
    enqueue.add_argument('--model-mode',choices=['off','assist'],default='off')
    enqueue.add_argument('--allow-paid',action='store_true')
    enqueue.add_argument('--paid-max-calls',type=int,default=0)
    export = sub.add_parser('export')
    export.add_argument('id')
    export.add_argument('--school')
    args = parser.parse_args(argv)
    try:
        if args.command == 'preview': result = preview(args.paths)
        else:
            service = BatchService(args.data_root)
            if args.command == 'import': result = service.import_files(args.paths)
            elif args.command in {'run','enqueue'}: result = getattr(service,args.command)(args.id, **{k:v for k,v in vars(args).items() if k not in {'id','command','data_root'}})
            elif args.command == 'export': result = service.export(args.id,args.school)
            elif args.command == 'demo': result = service.demo()
            elif args.command == 'list': result = service.list_batches()
            else: result = getattr(service,args.command)(args.id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')

if __name__ == '__main__':
    raise SystemExit(main())
