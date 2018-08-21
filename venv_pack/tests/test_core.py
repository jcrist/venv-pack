from __future__ import absolute_import, print_function, division

import os
import subprocess
import tarfile

import pytest

from venv_pack import Env, VenvPackException, pack, File
from venv_pack.core import find_site_packages

from .conftest import venv_path, venv_editable_path, rel_env_dir, env_dir


site_packages = os.path.relpath(find_site_packages(venv_path), venv_path)


@pytest.fixture(scope="module")
def venv_env():
    return Env(venv_path)


def test_from_prefix():
    env = Env(os.path.join(rel_env_dir, 'venv'))
    assert len(env)
    # relative path is normalized
    assert env.prefix == venv_path

    # Path is missing
    with pytest.raises(VenvPackException):
        Env(os.path.join(env_dir, "this_path_doesnt_exist"))

    # Path exists, but isn't a conda environment
    with pytest.raises(VenvPackException):
        Env(os.path.join(env_dir))


def test_errors_editable_packages():
    with pytest.raises(VenvPackException) as exc:
        Env(venv_editable_path)

    assert "Editable packages found" in str(exc.value)


def test_env_properties(venv_env):
    assert venv_env.name == 'venv'
    assert venv_env.prefix == venv_path

    # Env has a length
    assert len(venv_env) == len(venv_env.files)

    # Env is iterable
    assert len(list(venv_env)) == len(venv_env)

    # Smoketest repr
    assert 'Env<' in repr(venv_env)


def test_include_exclude(venv_env):
    old_len = len(venv_env)
    env2 = venv_env.exclude("*.pyc")
    # No mutation
    assert len(venv_env) == old_len
    assert env2 is not venv_env

    assert len(env2) < len(venv_env)

    # Re-add the removed files, envs are equivalent
    assert len(env2.include("*.pyc")) == len(venv_env)

    env3 = env2.exclude("%s/toolz/*" % site_packages)
    env4 = env3.include("%s/toolz/__init__.py" % site_packages)
    assert len(env3) + 1 == len(env4)


def test_output_and_format(venv_env):
    output, format = venv_env._output_and_format()
    assert output == 'venv.tar.gz'
    assert format == 'tar.gz'

    for format in ['tar.gz', 'tar.bz2', 'tar', 'zip']:
        output = os.extsep.join([venv_env.name, format])

        o, f = venv_env._output_and_format(format=format)
        assert f == format
        assert o == output

        o, f = venv_env._output_and_format(output=output)
        assert o == output
        assert f == format

        o, f = venv_env._output_and_format(output='foo.zip', format=format)
        assert f == format
        assert o == 'foo.zip'

    with pytest.raises(VenvPackException):
        venv_env._output_and_format(format='foo')

    with pytest.raises(VenvPackException):
        venv_env._output_and_format(output='foo.bar')


def test_roundtrip(tmpdir, venv_env):
    out_path = os.path.join(str(tmpdir), 'venv.tar')
    venv_env.pack(out_path)
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
    command = (". {path}/bin/activate && "
               "python -c 'import toolz' && "
               "deactivate && "
               "echo 'Done'").format(path=extract_path)

    out = subprocess.check_output(['/usr/bin/env', 'bash', '-c', command],
                                  stderr=subprocess.STDOUT).decode()
    assert out == 'Done\n'


def test_pack_exceptions(venv_env):
    # Unknown filter type
    with pytest.raises(VenvPackException):
        pack(prefix=venv_path,
             filters=[("exclude", "*.py"),
                      ("foo", "*.pyc")])


@pytest.mark.slow
def test_zip64(tmpdir):
    # Create an environment that requires ZIP64 extensions, but doesn't use a
    # lot of disk/RAM
    source = os.path.join(str(tmpdir), 'source.txt')
    with open(source, 'wb') as f:
        f.write(b'0')

    files = [File(source, 'foo%d' % i) for i in range(1 << 16)]
    large_env = Env._new('large', files=files)

    out_path = os.path.join(str(tmpdir), 'large.zip')

    # Errors if ZIP64 disabled
    with pytest.raises(VenvPackException) as exc:
        large_env.pack(output=out_path, zip_64=False)
    assert 'ZIP64' in str(exc.value)
    assert not os.path.exists(out_path)

    # Works fine if ZIP64 not disabled
    large_env.pack(output=out_path)
    assert os.path.exists(out_path)


def test_force(tmpdir, venv_env):
    already_exists = os.path.join(str(tmpdir), 'venv.tar')
    with open(already_exists, 'wb'):
        pass

    # file already exists
    with pytest.raises(VenvPackException):
        venv_env.pack(output=already_exists)

    venv_env.pack(output=already_exists, force=True)
    assert tarfile.is_tarfile(already_exists)


def test_pack(tmpdir, venv_env):
    out_path = os.path.join(str(tmpdir), 'venv.tar')

    exclude1 = "*.py"
    exclude2 = "*.pyc"
    include = "%s/toolz/*" % site_packages

    res = pack(prefix=venv_path,
               output=out_path,
               filters=[("exclude", exclude1),
                        ("exclude", exclude2),
                        ("include", include)])

    assert res == out_path
    assert os.path.exists(out_path)
    assert tarfile.is_tarfile(out_path)

    with tarfile.open(out_path) as fil:
        paths = fil.getnames()

    filtered = (venv_env
                .exclude(exclude1)
                .exclude(exclude2)
                .include(include))

    # Files line up with filtering, with extra activate commands
    sol = set(f.target for f in filtered.files)
    res = set(paths)
    diff = res.difference(sol)
    for fil in diff:
        assert 'activate' in fil
