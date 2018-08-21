#/usr/bin/env bash
set -e

echo "== Setting up environments for testing =="

PY_VERSION=`python -c "import sys; print('%d.%d' % sys.version_info[:2])"`

current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

envdir="$current_dir/environments$PY_VERSION"

echo "Python version $PY_VERSION"

if [ $PY_VERSION != "2.7" ]; then
    echo "Creating venv environment"
    envpath="$envdir/venv"
    python -m venv $envpath
    ${envpath}/bin/pip install toolz

    echo "Creating venv environment with system site-packages"
    envpath="$envdir/venv-system"
    python -m venv --system-site-packages $envpath
    ${envpath}/bin/pip install toolz
fi

echo "Creating virtualenv environment with editable packages"
envpath="$envdir/editable"
python -m virtualenv $envpath
${envpath}/bin/pip install toolz
pushd "${current_dir}/.." && ${envpath}/bin/python setup.py develop && popd

echo "Creating virtualenv environment"
envpath="$envdir/virtualenv"
python -m virtualenv $envpath
${envpath}/bin/pip install toolz

echo "Creating virtualenv environment with system site-packages"
envpath="$envdir/virtualenv-system"
python -m virtualenv --system-site-packages $envpath
${envpath}/bin/pip install toolz
