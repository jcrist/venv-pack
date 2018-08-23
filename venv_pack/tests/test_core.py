from __future__ import absolute_import, print_function, division

import os
import subprocess
import sys
import tarfile
from glob import glob

import pytest

from venv_pack import Env, VenvPackException, pack, File
from venv_pack.core import find_python_lib_include, check_prefix, BIN_DIR, on_win

from .conftest import (venv_path, venv_system_path,
                       virtualenv_path, virtualenv_system_path,
                       editable_path,
                       rel_env_dir, env_dir)


PY2 = sys.version_info.major == 2
PY_LIB, PY_INCLUDE = find_python_lib_include(virtualenv_path)
site_packages = os.path.join(PY_LIB, 'site-packages')


@pytest.fixture(scope="module")
def virtualenv_env():
    return Env(virtualenv_path)


@pytest.mark.skipif(PY2, reason="Python 2 doesn't support venv")
@pytest.mark.parametrize('path', [venv_path, venv_system_path])
def test_check_prefix_venv(path):
    context = check_prefix(path)
    assert context.prefix == os.path.abspath(path)
    assert context.kind == 'venv'
    assert context.orig_prefix == sys.exec_prefix
    assert os.path.exists(os.path.join(context.prefix, context.py_lib))
    assert os.path.exists(os.path.join(context.orig_prefix, context.py_lib))


@pytest.mark.parametrize('path',
                         [virtualenv_path,
                          os.path.join(rel_env_dir, 'virtualenv'),
                          virtualenv_system_path])
def test_check_prefix_virtualenv(path):
    context = check_prefix(path)
    assert context.prefix == os.path.abspath(path)
    assert context.kind == 'virtualenv'
    assert context.orig_prefix == sys.exec_prefix
    assert os.path.exists(os.path.join(context.prefix, context.py_lib))
    if os.path.exists(os.path.join(context.orig_prefix, context.py_include)):
        assert os.path.exists(os.path.join(context.prefix, context.py_include))


@pytest.mark.parametrize('env_path, env_kind',
                         [(virtualenv_path, 'virtualenv')] +
                         ([] if PY2 else [(venv_path, 'venv')]))
def test_check_prefix_from_env(env_path, env_kind):
    try:
        old = os.environ.get('VIRTUAL_ENV')
        os.environ['VIRTUAL_ENV'] = env_path
        context = check_prefix()
        assert context.prefix == env_path
        assert context.kind == env_kind
    finally:
        if old is not None:
            os.environ['VIRTUAL_ENV'] = old


def test_check_prefix_errors():
    # Path is missing
    with pytest.raises(VenvPackException):
        check_prefix(os.path.join(env_dir, "this_path_doesnt_exist"))

    # Path exists, but isn't a python environment
    with pytest.raises(VenvPackException):
        check_prefix(os.path.join(env_dir))

    # Path exists, but isn't a virtual environment
    with pytest.raises(VenvPackException):
        check_prefix(os.path.join(sys.exec_prefix))

    # Not currently in a virtual environment
    try:
        old = os.environ.get('VIRTUAL_ENV')
        del os.environ['VIRTUAL_ENV']

        with pytest.raises(VenvPackException):
            check_prefix()
    finally:
        if old is not None:
            os.environ['VIRTUAL_ENV'] = old


def test_errors_editable_packages():
    with pytest.raises(VenvPackException) as exc:
        Env(editable_path)

    assert "Editable packages found" in str(exc.value)


def test_env_properties(virtualenv_env):
    assert virtualenv_env.name == 'virtualenv'
    assert virtualenv_env.prefix == virtualenv_path
    assert virtualenv_env.kind == 'virtualenv'
    assert virtualenv_env.orig_prefix == sys.exec_prefix

    # Env has a length
    assert len(virtualenv_env) == len(virtualenv_env.files)

    # Env is iterable
    assert len(list(virtualenv_env)) == len(virtualenv_env)

    # Smoketest repr
    assert 'Env<' in repr(virtualenv_env)


def test_include_exclude(virtualenv_env):
    old_len = len(virtualenv_env)
    env2 = virtualenv_env.exclude("*.pyc")
    # No mutation
    assert len(virtualenv_env) == old_len
    assert env2 is not virtualenv_env

    assert len(env2) < len(virtualenv_env)

    # Re-add the removed files, envs are equivalent
    assert len(env2.include("*.pyc")) == len(virtualenv_env)

    env3 = env2.exclude("%s/toolz/*" % site_packages)
    env4 = env3.include("%s/toolz/__init__.py" % site_packages)
    assert len(env3) + 1 == len(env4)


def test_output_and_format(virtualenv_env):
    output, format = virtualenv_env._output_and_format()
    assert output == 'virtualenv.tar.gz'
    assert format == 'tar.gz'

    for format in ['tar.gz', 'tar.bz2', 'tar', 'zip']:
        output = os.extsep.join([virtualenv_env.name, format])

        o, f = virtualenv_env._output_and_format(format=format)
        assert f == format
        assert o == output

        o, f = virtualenv_env._output_and_format(output=output)
        assert o == output
        assert f == format

        o, f = virtualenv_env._output_and_format(output='foo.zip', format=format)
        assert f == format
        assert o == 'foo.zip'

    with pytest.raises(VenvPackException):
        virtualenv_env._output_and_format(format='foo')

    with pytest.raises(VenvPackException):
        virtualenv_env._output_and_format(output='foo.bar')


prefix_systems = [(virtualenv_path, False),
                  (virtualenv_system_path, True)]
if not PY2:
    prefix_systems.extend([(venv_path, False),
                           (venv_system_path, True)])


@pytest.mark.parametrize('prefix, system', prefix_systems)
def test_roundtrip(tmpdir, prefix, system):
    env = Env(prefix)
    out_path = os.path.join(str(tmpdir), 'environment.tar')
    env.pack(out_path)
    assert os.path.exists(out_path)
    assert tarfile.is_tarfile(out_path)

    with tarfile.open(out_path) as fil:
        # Check all files are relative paths
        for member in fil.getnames():
            assert not member.startswith(os.path.sep)

        extract_path = str(tmpdir)
        fil.extractall(extract_path)

    # Shebang rewriting happens before prefixes are fixed
    textfile = os.path.join(extract_path, 'bin', 'pip')
    with open(textfile, 'r') as fil:
        shebang = fil.readline().strip()
        assert shebang == '#!/usr/bin/env python'

    # Check bash scripts all don't error
    packages = 'pytest, toolz' if system else 'toolz'
    command = (". {path}/bin/activate && "
               "python -c 'import {packages}' && "
               "deactivate && "
               "echo 'Done'").format(packages=packages, path=extract_path)

    out = subprocess.check_output(['/usr/bin/env', 'bash', '-c', command],
                                  stderr=subprocess.STDOUT).decode()
    assert out == 'Done\n'


@pytest.mark.skipif(PY2, reason="Python 2 doesn't support venv")
def test_venv_python_prefix(tmpdir):
    env = Env(venv_path)
    out_path = os.path.join(str(tmpdir), 'environment.tar')
    python_prefix = os.path.normpath('/new/path/to/python/prefix/')
    env.pack(out_path, python_prefix=python_prefix)

    with tarfile.open(out_path) as fil:
        pyvenv_cfg = fil.extractfile('pyvenv.cfg').read().decode()
        python = fil.getmember(os.path.join(BIN_DIR, 'python'))
        python3 = fil.getmember(os.path.join(BIN_DIR, 'python3'))

    assert os.path.join(python_prefix, BIN_DIR) in pyvenv_cfg
    assert python.issym()
    exename = 'python' if on_win else 'python%d.%d' % sys.version_info[:2]
    assert python.linkname == os.path.join(python_prefix, BIN_DIR, exename)
    assert python3.issym()
    assert python3.linkname == 'python'


def test_virtualenv_python_prefix(tmpdir):
    env = Env(virtualenv_path)
    out_path = os.path.join(str(tmpdir), 'environment.tar')
    python_prefix = os.path.normpath('/new/path/to/python/prefix/')
    env.pack(out_path, python_prefix=python_prefix)

    with tarfile.open(out_path) as fil:
        extract_path = str(tmpdir)
        fil.extractall(extract_path)

    with open(os.path.join(extract_path, PY_LIB, 'orig-prefix.txt')) as fil:
        assert fil.read() == python_prefix

    # Check includes
    for path in glob(os.path.join(extract_path, PY_INCLUDE + '*')):
        if os.path.islink(path):
            assert os.readlink(path).startswith(python_prefix)

    # Check lib
    for path in glob(os.path.join(extract_path, PY_LIB, '*')):
        if os.path.islink(path):
            assert os.readlink(path).startswith(python_prefix)


def test_python_prefix_not_absolute_path():
    with pytest.raises(VenvPackException) as exc:
        pack(prefix=virtualenv_path,
             python_prefix='not/absolute')

    assert 'absolute' in str(exc.value)


def test_pack_exceptions():
    # Unknown filter type
    with pytest.raises(VenvPackException):
        pack(prefix=virtualenv_path,
             filters=[("exclude", "*.py"),
                      ("foo", "*.pyc")])


@pytest.mark.slow
def test_zip64(tmpdir, virtualenv_env):
    # Create an environment that requires ZIP64 extensions, but doesn't use a
    # lot of disk/RAM
    source = os.path.join(str(tmpdir), 'source.txt')
    with open(source, 'wb') as f:
        f.write(b'0')

    files = [File(source, 'foo%d' % i) for i in range(1 << 16)]
    # Hack to build an env with a large environment
    large_env = virtualenv_env._copy_with_files(files, [])
    out_path = os.path.join(str(tmpdir), 'large.zip')

    # Errors if ZIP64 disabled
    with pytest.raises(VenvPackException) as exc:
        large_env.pack(output=out_path, zip_64=False)
    assert 'ZIP64' in str(exc.value)
    assert not os.path.exists(out_path)

    # Works fine if ZIP64 not disabled
    large_env.pack(output=out_path)
    assert os.path.exists(out_path)


def test_force(tmpdir, virtualenv_env):
    already_exists = os.path.join(str(tmpdir), 'virtualenv.tar')
    with open(already_exists, 'wb'):
        pass

    # file already exists
    with pytest.raises(VenvPackException):
        virtualenv_env.pack(output=already_exists)

    virtualenv_env.pack(output=already_exists, force=True)
    assert tarfile.is_tarfile(already_exists)


def test_pack(tmpdir, virtualenv_env):
    out_path = os.path.join(str(tmpdir), 'virtualenv.tar')

    exclude1 = "*.py"
    exclude2 = "*.pyc"
    include = "%s/toolz/*" % site_packages

    res = pack(prefix=virtualenv_path,
               output=out_path,
               filters=[("exclude", exclude1),
                        ("exclude", exclude2),
                        ("include", include)])

    assert res == out_path
    assert os.path.exists(out_path)
    assert tarfile.is_tarfile(out_path)

    with tarfile.open(out_path) as fil:
        paths = fil.getnames()

    filtered = (virtualenv_env
                .exclude(exclude1)
                .exclude(exclude2)
                .include(include))

    # Files line up with filtering, with extra activate commands
    sol = set(f.target for f in filtered.files)
    res = set(paths)
    diff = res.difference(sol)
    for fil in diff:
        assert 'activate' in fil
