"""Noninteractive, one-batch server entry point for the shared Mission B engine."""
import argparse
import json
import sys
from pathlib import Path
from run_limits import RunLimits

SERVER_VERSION = '1.0.0'

def parser():
    p = argparse.ArgumentParser(description='Mission B server: one finite roster-link audit batch')
    p.add_argument('--check', action='store_true', help='Validate configuration without network or API credentials')
    p.add_argument('--input', type=Path, help='Input directory (CSV/TSV/TXT/XLSX/XLSM/XLS)')
    p.add_argument('--output', type=Path, help='New output directory; must not already exist')
    p.add_argument('--cache-dir', type=Path, help='External model cache directory')
    p.add_argument('--limits', type=Path, help='JSON object of finite positive integer overrides')
    p.add_argument('--mode', choices=('deepseek', 'rules'), default='deepseek')
    p.add_argument('--plans', type=Path, help='Explicit verified local source plans (required for rules)')
    p.add_argument('--no-browser', action='store_true', help='Disable Chromium fallback')
    p.add_argument('--replay', type=Path, help='Saved page run; deepseek cache misses may still call API')
    return p

def main():
    p = parser()
    args = p.parse_args()
    try:
        args.limits = RunLimits.load(args.limits or {})
        if args.plans:
            plans = json.loads(args.plans.read_text(encoding='utf-8-sig'))
            if not isinstance(plans, dict) or not isinstance(plans.get('plans'), dict):
                raise ValueError('plans must contain a plans object')
        if args.mode == 'rules' and not args.plans:
            raise ValueError('rules requires --plans with verified local roster regions')
        if args.check:
            print(json.dumps({'server_version': SERVER_VERSION, 'mode': args.mode, 'limits': args.limits.as_dict()}))
            return 0
        if not args.input or not args.output or not args.cache_dir:
            raise ValueError('--input, --output and --cache-dir are required for a batch')
        return execute(args)
    except (ValueError, OSError, json.JSONDecodeError):
        # Do not echo untrusted configuration values or credential-bearing exceptions.
        print('Invalid configuration or inaccessible path; check paths, JSON schema and positive limits.', file=sys.stderr)
        return 2

def execute(args):
    import asyncio
    import contextlib
    import os
    from audit import run, write_json
    from server_export import export_download
    if args.output.exists() or not args.input.is_dir():
        raise ValueError('input must exist and output must be new')
    # Never create caches in the source tree; disable bytecode even for readonly installs.
    sys.dont_write_bytecode = True
    args.cache_dir = args.cache_dir.resolve()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    if not args.plans:
        # Empty plan is generated in external cache, never beside the scripts.
        import tempfile
        fd, name = tempfile.mkstemp(prefix='missionb-plans-', suffix='.json', dir=args.cache_dir)
        os.close(fd)
        args.plans = Path(name)
        args.plans.write_text('{"plans": {}}', encoding='utf-8')
        generated = True
    else:
        generated = False
    def progress(event, data):
        # Log only bounded counters: no website text, secrets, or credential-bearing URLs.
        row = {'event': event, **{k: data[k] for k in ('index', 'total') if k in data}}
        line = json.dumps(row)
        print(line, flush=True)
        if args.output.exists():
            with (args.output/'progress.jsonl').open('a', encoding='utf-8') as log:
                log.write(line + '\n')
    try:
        with contextlib.redirect_stdout(sys.stderr):
            out, results, manifest = asyncio.run(run(args, on_progress=progress))
        export_download(out, results)
        write_json(out/'server-status.json', {'status': 'completed', 'exit_code': 0,
                   'server_version': SERVER_VERSION, 'download': 'results.zip'})
        print(json.dumps({'event': 'completed', 'output': str(out), 'download': str(out/'results.zip')}))
        return 0
    except KeyboardInterrupt:
        if args.output.exists():
            write_json(args.output/'server-status.json', {'status': 'cancelled', 'exit_code': 130})
        return 130
    except Exception:
        if args.output.exists():
            write_json(args.output/'server-status.json', {'status': 'failed', 'exit_code': 1})
        print('Batch failed; inspect preserved audit evidence and configuration.', file=sys.stderr)
        return 1
    finally:
        if generated:
            args.plans.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
