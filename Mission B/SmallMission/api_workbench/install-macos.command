#!/bin/bash
# Double-click to install the private runtime and open Mission B.
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
/bin/bash ./start-macos.command "$@"
