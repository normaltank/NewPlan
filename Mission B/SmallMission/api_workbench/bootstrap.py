"""Install and verify a private environment, then open the local workbench."""
import argparse
from collections import deque
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
IMPORT_CHECK = 'import httpx, bs4, lxml.etree, openpyxl, xlrd, playwright.sync_api'
BROWSER_CHECK = '''from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<title>MissionB setup check</title>')
    assert page.title() == 'MissionB setup check'
    browser.close()
'''


def environment_variables(root):
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER'):
        env.pop(key, None)
    env.update(PYTHONNOUSERSITE='1', PYTHONUTF8='1', PYTHONUNBUFFERED='1',
               PLAYWRIGHT_BROWSERS_PATH=str(root / '.browsers'),
               PIP_CACHE_DIR=str(root / '.runtime' / 'pip-cache'),
               PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_CONFIG_FILE=os.devnull)
    return env


def command(args, root, env, *, timeout=None, quiet=False):
    """Keep detailed install output on disk, never log environment variables."""
    log_dir = root / '.runtime'
    log_dir.mkdir(exist_ok=True)
    with (log_dir / 'setup.log').open('a', encoding='utf-8') as log:
        if timeout is not None:
            result = subprocess.run(args, cwd=root, env=env, text=True, encoding='utf-8',
                                    errors='replace', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=timeout)
            log.write(result.stdout)
            if not quiet and result.stdout:
                print(result.stdout, end='', flush=True)
            return result.returncode, result.stdout
        tail = deque(maxlen=40)
        with subprocess.Popen(args, cwd=root, env=env, text=True, encoding='utf-8',
                              errors='replace', stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            for line in process.stdout:
                log.write(line)
                log.flush()
                tail.append(line)
                if not quiet:
                    print(line, end='', flush=True)
            return process.wait(), ''.join(tail)


def required(args, root, env):
    code, _ = command(args, root, env)
    if code:
        raise RuntimeError('下载或安装未完成。恢复网络后重新启动即可重试；详细原因见 .runtime/setup.log。')


def linux_deps_supported():
    if not sys.platform.startswith('linux'):
        return False
    try:
        info = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines()
                    if '=' in line and not line.startswith('#'))
        distro = info.get('ID', '').strip('"')
        version = info.get('VERSION_ID', '').strip('"')
        return ((distro == 'ubuntu' and version in ('22.04', '24.04', '26.04')) or
                (distro == 'debian' and version in ('12', '13')))
    except OSError:
        return False


def missing_linux_libraries(output):
    text = output.lower()
    return sys.platform.startswith('linux') and any(hint in text for hint in (
        'host system is missing dependencies', 'error while loading shared libraries',
        'missing libraries:', 'playwright install-deps'))


def install_system_dependencies(python, root, env):
    if not linux_deps_supported():
        raise RuntimeError('自动补装系统组件仅支持 Debian 12/13、Ubuntu 22.04/24.04/26.04。请管理员按日志处理。')
    print('浏览器需要额外的 Linux 系统组件。此步骤会通过系统包管理器安装，可能要求输入管理员密码。', flush=True)
    if not sys.stdin.isatty() or input('现在安装？输入 y 确认，直接回车跳过：').strip().lower() not in ('y', 'yes'):
        raise RuntimeError('已跳过系统组件安装。稍后在终端运行 bash run.sh --system-deps 即可继续。')
    subprocess.check_call([str(python), '-m', 'playwright', 'install-deps', 'chromium'], cwd=root, env=env)


def prepare(root, *, check_only=False, system_deps=False):
    environment = root / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    env = environment_variables(root)
    if not python.exists():
        if check_only:
            raise RuntimeError('尚未安装环境。请先运行启动脚本。')
        print('正在工具文件夹内创建独立运行环境…', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    signature = hashlib.sha256(b'setup1\0' + (root / 'requirements.txt').read_bytes()).hexdigest()
    ready = environment / '.missionb-ready'
    installed = ready.exists() and ready.read_text().strip() == signature
    code, _ = command([str(python), '-B', '-c', IMPORT_CHECK], root, env, timeout=60, quiet=True)
    if not check_only and (not installed or code):
        ready.unlink(missing_ok=True)
        print('[3/4] 正在安装所需组件和浏览器，首次下载可能需要几分钟…', flush=True)
        pip_code, _ = command([str(python), '-m', 'pip', '--version'], root, env, timeout=60, quiet=True)
        if pip_code:
            # A cancelled uv --seed/venv install can leave Python without pip.
            required([str(python), '-m', 'ensurepip', '--upgrade'], root, env)
        required([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], root, env)
        required([str(python), '-m', 'playwright', 'install', 'chromium', '--only-shell'], root, env)
        code, _ = command([str(python), '-B', '-c', IMPORT_CHECK], root, env, timeout=60, quiet=True)
    if code:
        raise RuntimeError('Python 组件检查失败。请重新运行启动脚本，详情见 .runtime/setup.log。')
    if system_deps:
        install_system_dependencies(python, root, env)
    print('[4/4] 正在检查浏览器能否实际启动…', flush=True)
    code, output = command([str(python), '-B', '-c', BROWSER_CHECK], root, env, timeout=60, quiet=True)
    if code and not check_only:
        ready.unlink(missing_ok=True)
        if missing_linux_libraries(output):
            install_system_dependencies(python, root, env)
        elif 'executable doesn\'t exist' in output.lower():
            required([str(python), '-m', 'playwright', 'install', 'chromium', '--only-shell'], root, env)
        else:
            raise RuntimeError('浏览器无法启动。详情见 .runtime/setup.log；请确认系统版本符合 README.md 的要求。')
        code, output = command([str(python), '-B', '-c', BROWSER_CHECK], root, env, timeout=60, quiet=True)
    if code:
        raise RuntimeError('浏览器检查未通过，尚不能可靠核验网页。请查看 .runtime/setup.log。')
    if not check_only:
        ready.write_text(signature, encoding='utf-8')
    print('环境检查通过。', flush=True)
    return python, env


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mission B 私有环境安装与检查')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--setup-only', action='store_true', help='安装检查后退出，不启动工作台')
    mode.add_argument('--check', action='store_true', help='仅检查现有环境，不下载、不安装')
    parser.add_argument('--system-deps', action='store_true', help='询问是否补装 Linux 浏览器系统组件')
    args = parser.parse_args(argv)
    if args.check and args.system_deps:
        parser.error('--check 不能与 --system-deps 一起使用')
    if sys.version_info < (3, 11):
        raise RuntimeError('需要 Python 3.11 或更高版本。macOS/Linux 请使用随附启动脚本自动安装。')
    python, env = prepare(ROOT, check_only=args.check, system_deps=args.system_deps)
    if args.check or args.setup_only:
        return
    print('正在打开 Mission B 工作台。关闭网页不会退出后台，请在页面左下角点击“退出工具”。', flush=True)
    subprocess.check_call([str(python), '-B', str(ROOT / 'app.py')], cwd=ROOT, env=env)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('\n启动未完成：' + str(error), file=sys.stderr)
        print('详细安装记录在 .runtime/setup.log；请查看 README.md 的启动排查说明。', file=sys.stderr)
        sys.exit(1)
