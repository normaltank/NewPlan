#!/bin/bash
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
/bin/bash ./run.sh "$@"
result=$?
if [ "$result" -ne 0 ]; then
  printf '\n未完成安装或启动。请查看 README.md 与 .runtime/install.log。按回车关闭。\n'
  read -r answer
fi
exit "$result"
