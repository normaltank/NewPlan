"""Paths for source distributions and self-contained desktop bundles."""
import os
from pathlib import Path
import sys

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
VERSION = '3.0.4'


def plans_path():
    external = APP_ROOT / 'source_plans.json'
    return external if external.exists() else ASSETS / 'source_plans.json'


def browser_path():
    """Use the shipped browser first; never depend on the author's user path."""
    if sys.platform == 'win32':
        shipped = APP_ROOT / 'browser' / 'chrome-win' / 'chrome.exe'
        if shipped.exists():
            return str(shipped)
    local = APP_ROOT / '.browsers'
    if local.exists():
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(local)
        return None
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        candidates = list((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win/chrome.exe'))
        if candidates:
            return str(sorted(candidates)[-1])
    return None
