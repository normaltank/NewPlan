"""Local Mission C page; work persists under --data-root, never in the browser."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mission C 本地操作页面（仅回环地址）')
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parent/'data')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--cache-manifest', type=Path, help='供页面选择的本地缓存清单')
    parser.add_argument('--allow-live', action='store_true', help='允许用户显式选择在线网站访问')
    parser.add_argument('--allow-paid', action='store_true', help='允许用户显式选择在线 Fetch/模型')
    parser.add_argument('--paid-max-calls', type=int, default=0, help='付费持久预算上限，默认0')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.paid_max_calls < 0:
        parser.error('端口或预算无效')
    if args.allow_paid and (not args.allow_live or args.paid_max_calls < 1):
        parser.error('开放付费需同时 --allow-live 和正数 --paid-max-calls')
    try:
        import uvicorn
        from mission_c.web import create_app, WebPolicy
    except ImportError:
        parser.exit(2, '请先安装 Mission C/requirements-web.txt 中的本地页面依赖。\n')
    app = create_app(args.data_root, policy=WebPolicy(args.allow_live,args.allow_paid,args.paid_max_calls), cache_manifest=args.cache_manifest)
    print(f'Mission C 本地页面：http://127.0.0.1:{args.port} （保持服务运行，关闭网页不停止批次）', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
