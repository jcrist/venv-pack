#/usr/bin/env bash
echo "== Setting up environments for testing =="

current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Creating simple environment"
envpath="${current_dir}/environments/simple"
python -m venv $envpath
source "${envpath}/bin/activate"
pip install toolz
deactivate

echo "Creating editable environment"
envpath="${current_dir}/environments/editable"
python -m venv $envpath
source "${envpath}/bin/activate"
pip install toolz
pushd "${current_dir}/.." && python setup.py develop && popd
deactivate
