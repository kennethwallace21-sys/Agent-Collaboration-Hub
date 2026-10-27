#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Install Python 3.10 or newer from https://www.python.org/downloads/, then run this installer again.'
  read -r _reply
  exit 1
fi
python3 install.py "$@"
printf '\nPress Enter to close this window.\n'
read -r _reply
