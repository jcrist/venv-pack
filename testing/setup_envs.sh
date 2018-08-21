#/usr/bin/env bash
set -e

echo "== Setting up environments for testing =="

current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Creating venv environment"
envpath="${current_dir}/environments/venv"
python -m venv $envpath
${envpath}/bin/pip install toolz

echo "Creating venv environment with system site-packages"
envpath="${current_dir}/environments/venv-system"
python -m venv $envpath
${envpath}/bin/pip install toolz

echo "Creating venv environment with editable packages"
envpath="${current_dir}/environments/venv-editable"
python -m venv $envpath
${envpath}/bin/pip install toolz
pushd "${current_dir}/.." && ${envpath}/bin/python setup.py develop && popd

echo "Creating virtualenv environment"
envpath="${current_dir}/environments/virtualenv"
virtualenv $envpath
${envpath}/bin/pip install toolz

echo "Creating virtualenv environment with system site-packages"
envpath="${current_dir}/environments/virtualenv-system"
virtualenv $envpath
${envpath}/bin/pip install toolz
