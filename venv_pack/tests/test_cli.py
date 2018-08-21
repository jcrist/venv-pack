from __future__ import absolute_import, print_function, division

import os
import tarfile

import pytest

import venv_pack
from venv_pack.__main__ import main

from .conftest import venv_path


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["-h"])

    assert exc.value.code == 0

    out, err = capsys.readouterr()
    assert not err
    assert 'usage: venv-pack' in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0

    out, err = capsys.readouterr()
    assert not err
    assert venv_pack.__version__ in out


def test_parse_include_exclude():
    out = {}

    def capture(**kwargs):
        out.update(kwargs)

    with pytest.raises(SystemExit) as exc:
        main(["--exclude", "foo/*",
              "--include", "*.py",
              "--include", "*.pyx",
              "--exclude", "foo/bar/*.pyx"],
             pack=capture)

    assert exc.value.code == 0

    assert out['filters'] == [("exclude", "foo/*"),
                              ("include", "*.py"),
                              ("include", "*.pyx"),
                              ("exclude", "foo/bar/*.pyx")]


def test_cli_roundtrip(capsys, tmpdir):
    out_path = os.path.join(str(tmpdir), 'simple.tar')

    with pytest.raises(SystemExit) as exc:
        main(["-p", venv_path, "-o", out_path])

    assert exc.value.code == 0

    assert os.path.exists(out_path)
    assert tarfile.is_tarfile(out_path)

    out, err = capsys.readouterr()
    assert not err

    bar, percent, time = [i.strip() for i in out.split('\r')[-1].split('|')]
    assert bar == '[' + '#' * 40 + ']'
    assert percent == '100% Completed'
    assert time


def test_quiet(capsys, tmpdir):
    out_path = os.path.join(str(tmpdir), 'simple.tar')

    with pytest.raises(SystemExit) as exc:
        main(["-p", venv_path, "-o", out_path, "-q"])

    assert exc.value.code == 0

    assert os.path.exists(out_path)
    assert tarfile.is_tarfile(out_path)

    out, err = capsys.readouterr()
    assert not err
    assert not out


def test_cli_exceptions(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["-p", "not_a_real_path"])

    assert exc.value.code == 1

    out, err = capsys.readouterr()
    assert "VenvPackError: Environment path" in err

    with pytest.raises(SystemExit) as exc:
        main(["-foo", "-bar"])

    assert exc.value.code != 0

    out, err = capsys.readouterr()
    assert not out
    assert "usage: venv-pack" in err
