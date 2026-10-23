#!/usr/bin/env bash
# Private Python bootstrap; compatible with macOS's built-in Bash 3.2.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd -- "$ROOT"
check_only=0
setup_only=0
system_deps=0
for option in "$@"; do
  case "$option" in
    --check) check_only=1 ;;
    --setup-only) setup_only=1 ;;
    --system-deps) system_deps=1 ;;
    --help|-h) echo '运行 bash run.sh 自动安装并启动；--setup-only 仅安装；--check 仅检查；--system-deps 询问补装 Linux 系统库。'; exit 0 ;;
    *) printf '未知选项：%s。使用 bash run.sh --help 查看用法。\n' "$option"; exit 2 ;;
  esac
done
if [ "$check_only" -eq 1 ] && { [ "$setup_only" -eq 1 ] || [ "$system_deps" -eq 1 ]; }; then
  echo '--check 不能与安装选项一起使用。'; exit 2
fi
mkdir -p "$ROOT/.runtime"
exec > >(tee -a "$ROOT/.runtime/install.log") 2>&1
trap 'status=$?; if [ "$status" -ne 0 ]; then printf "\n安装或启动未完成。恢复网络后可重试；日志：%s/.runtime/install.log\n" "$ROOT"; fi' EXIT
printf '\nMission B · 环境安装与启动\n'
export PYTHONNOUSERSITE=1 PYTHONUTF8=1 PYTHONUNBUFFERED=1
unset PYTHONHOME PYTHONPATH
export UV_NO_CONFIG=1 UV_NO_MODIFY_PATH=1 UV_PYTHON_INSTALL_BIN=0
export UV_PYTHON_INSTALL_DIR="$ROOT/.runtime/python"
export UV_PYTHON_CACHE_DIR="$ROOT/.runtime/python-cache"
export UV_PYTHON_BIN_DIR="$ROOT/.runtime/bin"
export UV_CACHE_DIR="$ROOT/.runtime/cache"
export PIP_CACHE_DIR="$ROOT/.runtime/pip-cache"
system="$(uname -s)"
arch="$(uname -m)"
case "$system/$arch" in
  Darwin/arm64|Darwin/aarch64)
    target=aarch64-apple-darwin
    expected=cfe454573412ff7380d15fc7dae5997ab53ffce72fce0a78e91ddbc84001acd2 ;;
  Darwin/x86_64)
    target=x86_64-apple-darwin
    expected=bb7b805bdcf3d0bc8c74ceb94569e6b3e8aa35bd492acdbb9d46bf46d9d4ff6b ;;
  Linux/aarch64|Linux/arm64)
    target=aarch64-unknown-linux-gnu
    expected=9041c73c99fdc5892cf128140beb354eca9231d502068cc36e6cb53a8e59ad14 ;;
  Linux/x86_64)
    target=x86_64-unknown-linux-gnu
    expected=eadd9d27c134ab5ac1ffd4473b97a741407f3ea238288f03121fc4deddf90220 ;;
  *) printf '暂不支持此系统/架构：%s / %s。请查看 README.md。\n' "$system" "$arch"; exit 1 ;;
esac
if [ "$system" = Darwin ]; then
  mac_version="$(sw_vers -productVersion)"
  if [ "${mac_version%%.*}" -lt 14 ]; then
    echo '本包浏览器要求 macOS 14 或更新版本。'; exit 1
  fi
elif command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; then
  echo '本包的浏览器不支持 Alpine/musl；请使用受支持的 Debian 或 Ubuntu。'; exit 1
fi
python="$ROOT/.venv/bin/python"
if ! [ -x "$python" ] || ! "$python" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)' 2>/dev/null; then
  if [ "$check_only" -eq 1 ]; then
    echo '尚未建立可用环境。请先运行 bash run.sh 安装。'; exit 1
  fi
  version=0.13.1
  uv_dir="$ROOT/.runtime/uv-$version-$target"
  uv="$uv_dir/uv"
  if ! [ -x "$uv" ]; then
    echo '[1/4] 正在下载环境安装器（约 15–18 MB）…'
    mkdir -p "$uv_dir"
    archive="$uv_dir/download.tar.gz"
    url="https://github.com/astral-sh/uv/releases/download/$version/uv-$target.tar.gz"
    if command -v curl >/dev/null 2>&1; then
      curl --fail --location --retry 3 --connect-timeout 20 --max-time 600 --proto '=https' --tlsv1.2 --output "$archive" "$url"
    elif command -v wget >/dev/null 2>&1; then
      wget --https-only --timeout=60 --tries=3 -O "$archive" "$url"
    else
      echo '需要 curl 或 wget 下载环境，请让电脑管理员安装其中一个后重试。'; exit 1
    fi
    if command -v shasum >/dev/null 2>&1; then
      actual="$(shasum -a 256 "$archive")"
    elif command -v sha256sum >/dev/null 2>&1; then
      actual="$(sha256sum "$archive")"
    else
      echo '缺少 SHA256 校验工具（shasum / sha256sum），已停止安装。'; exit 1
    fi
    actual="${actual%% *}"
    if [ "$actual" != "$expected" ]; then
      echo '下载文件校验不通过，未执行。请检查网络后重试。'; exit 1
    fi
    # Extract only the expected binary from the hash-verified release archive.
    tar -xzf "$archive" -C "$uv_dir" --strip-components=1 "uv-$target/uv"
    chmod u+x "$uv"
  fi
  echo '[2/4] 正在安装工具专用 Python 3.12（不替换系统 Python）…'
  "$uv" python install 3.12 --no-bin
  if [ -e "$ROOT/.venv" ]; then
    backup="$ROOT/.venv.previous-$(date +%Y%m%d-%H%M%S)-$$"
    mv -- "$ROOT/.venv" "$backup"
    printf '原有不可用环境已保留为：%s\n' "$backup"
  fi
  "$uv" venv --python 3.12 --managed-python --seed "$ROOT/.venv"
fi
"$python" -B "$ROOT/bootstrap.py" "$@"
