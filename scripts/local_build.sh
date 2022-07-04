#!/usr/bin/env bash

set -e

rm -rf dist

python -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate

pip install -e ".[generate]"
pip install -r requirements.txt
pycodestyle
mypy cogment/
python -m build

deactivate

if [[ -n "$1" ]]; then
  cp -v dist/cogment-*.tar.gz "$1/cogment-py-sdk.tar.gz"
fi
