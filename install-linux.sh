#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/pc-steward-app"
if ! command -v python3 >/dev/null; then
  echo '请先安装 Python 3.10 或更新版本及 venv 模块。' >&2; exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,10), "需要 Python 3.10+"'
mkdir -p "$install_dir"
if [[ "$source_dir" != "$install_dir" ]]; then
  cp "$source_dir/app.py" "$source_dir/core.py" "$source_dir/naming.py" "$source_dir/requirements.txt" "$source_dir/app.ico" "$install_dir/"
fi
python3 -m venv "$install_dir/venv"
"$install_dir/venv/bin/python" -m pip install -r "$install_dir/requirements.txt"
mkdir -p "$HOME/.local/bin" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
python3 - "$install_dir" <<'PY'
import os, shlex, sys
from pathlib import Path
p=Path(sys.argv[1]); launcher=Path.home()/'.local/bin/pc-steward'
launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(p/'venv/bin/python'))+' '+shlex.quote(str(p/'app.py'))+' "$@"\n')
launcher.chmod(0o755)
# Desktop entry escaping differs from shell quoting.
exe=str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
d=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications/pc-steward.desktop'
d.write_text('[Desktop Entry]\nType=Application\nName=电脑管家\nName[en]=PC Steward\nComment=管理自启动、应用、缓存和运行进程\nExec="'+exe+'"\nIcon='+str(p/'app.ico')+'\nTerminal=false\nCategories=System;Utility;\n',encoding='utf-8')
print('已安装：'+str(launcher))
PY
