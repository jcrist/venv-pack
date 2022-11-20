import os
import tarfile
import zipfile
from os.path import isdir, isfile, islink, join, exists
from subprocess import check_output, STDOUT

import pytest

from venv_pack.formats import archive


@pytest.fixture(scope="module")
def root_and_paths(tmpdir_factory):
    root = str(tmpdir_factory.mktemp('example_dir'))

    def mkfil(*paths):
        with open(join(root, *paths), mode='w'):
            pass

    def mkdir(path):
        os.mkdir(join(root, path))

    def symlink(path, target):
        target = join(root, target)
        path = join(root, path)
        target = os.path.relpath(target, os.path.dirname(path))
        os.symlink(target, path)

    # Build test directory structure
    mkdir("empty_dir")
    symlink("link_to_empty_dir", "empty_dir")

    mkdir("dir")
    mkfil("dir", "one")
    mkfil("dir", "two")
    symlink("link_to_dir", "dir")

    mkfil("file")
    symlink("link_to_file", "file")

    paths = ["empty_dir",
             "link_to_empty_dir",
             join("dir", "one"),
             join("dir", "two"),
             "link_to_dir",
             "file",
             "link_to_file"]

    # make sure the input matches the test
    check(root)

    return root, paths


def checklink(path, sol):
    assert islink(path)
    assert os.readlink(path) == sol


def check(out_dir, links=False):
    assert exists(join(out_dir, "empty_dir"))
    assert isdir(join(out_dir, "empty_dir"))
    assert isdir(join(out_dir, "link_to_empty_dir"))
    assert isdir(join(out_dir, "dir"))
    assert isfile(join(out_dir, "dir", "one"))
    assert isfile(join(out_dir, "dir", "two"))
    assert isdir(join(out_dir, "link_to_dir"))
    assert isfile(join(out_dir, "file"))
    assert isfile(join(out_dir, "link_to_file"))

    if links:
        checklink(join(out_dir, "link_to_dir"), "dir")
        checklink(join(out_dir, "link_to_file"), "file")
        checklink(join(out_dir, "link_to_empty_dir"), "empty_dir")
    else:
        # Check that contents of directories are same
        assert set(os.listdir(join(out_dir, "link_to_dir"))) == {'one', 'two'}


def has_infozip():
    try:
        out = check_output(['unzip', '-h'], stderr=STDOUT).decode()
    except Exception:
        return False
    return "Info-ZIP" in out


@pytest.mark.parametrize('format, symlinks',
                         [('zip', False),
                          ('zip', True),
                          ('tar.gz', True),
                          ('tar.bz2', True),
                          ('tar', True)])
def test_format(tmpdir, format, symlinks, root_and_paths):
    if 'zip' and symlinks and not has_infozip():
        pytest.skip("Info-ZIP not installed")

    root, paths = root_and_paths

    out_path = join(str(tmpdir), 'test.' + format)
    out_dir = join(str(tmpdir), 'test')
    os.mkdir(out_dir)

    with open(out_path, mode='wb') as fil:
        with archive(fil, format, zip_symlinks=symlinks) as arc:
            for rel in paths:
                arc.add(join(root, rel), rel)
            arc.add_bytes(join(root, "file"),
                          b"foo bar",
                          join("dir", "from_bytes"))
            if symlinks:
                arc.add_link(join(root, "link_to_file"),
                             join("dir", "one"),
                             "manual_link_to_file")
                arc.add_link(join(root, "link_to_dir"),
                             "empty_dir",
                             "manual_link_to_dir")

    if format == 'zip':
        if symlinks:
            check_output(['unzip', out_path, '-d', out_dir])
        else:
            with zipfile.ZipFile(out_path) as out:
                out.extractall(out_dir)
    else:
        with tarfile.open(out_path) as out:
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(out, out_dir)

    check(out_dir, links=symlinks)
    assert isfile(join(out_dir, "dir", "from_bytes"))
    with open(join(out_dir, "dir", "from_bytes"), 'rb') as fil:
        assert fil.read() == b"foo bar"

    if symlinks:
        checklink(join(out_dir, "manual_link_to_dir"), "empty_dir")
        checklink(join(out_dir, "manual_link_to_file"),
                  join("dir", "one"))
