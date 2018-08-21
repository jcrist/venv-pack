#/usr/bin/env bash
set -e

echo "== Setting up environments for testing =="

current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Creating simple environment"
envpath="${current_dir}/environments/simple"
python -m venv $envpath
${envpath}/bin/pip install toolz

echo "Creating editable environment"
envpath="${current_dir}/environments/editable"
python -m venv $envpath
${envpath}/bin/pip install toolz
pushd "${current_dir}/.." && ${envpath}/bin/python setup.py develop && popd
