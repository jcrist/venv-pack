from __future__ import absolute_import, print_function

import glob
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections import namedtuple
from fnmatch import fnmatch

from .formats import archive
from .progress import progressbar


__all__ = ('VenvPackException', 'Env', 'File', 'pack')


class VenvPackException(Exception):
    """Internal exception to report to user"""
    pass


SCRIPTS = os.path.join(os.path.dirname(__file__), 'scripts')
on_win = sys.platform == 'win32'

# three capture groups: whole_shebang, executable, options
SHEBANG_REGEX = (
    # pretty much the whole match string
    br'^(#!'
    # allow spaces between #! and beginning of the executable path
    br'(?:[ ]*)'
    # the executable is the next text block without an escaped
    # space or non-space whitespace character
    br'(/(?:\\ |[^ \n\r\t])*)'
    # the rest of the line can contain option flags
    br'(.*)'
    # end whole_shebang group
    br')$')


BIN_DIR = 'Scripts' if on_win else 'bin'


class Env(object):
    """A Virtual Environment for packaging.

    Parameters
    ----------
    prefix : str, optional
        The path to the virtual environment. If not provided, the current
        environment will be used.

    Examples
    --------
    Package the current environment into a zip archive:

    >>> Env().pack(output="environment.tar.gz")
    "/full/path/to/environment.tar.gz"
    """
    def __init__(self, prefix=None):
        prefix, files = load_environment(prefix)

        self.prefix = prefix
        self.files = files
        self._excluded_files = []

    @classmethod
    def _new(cls, prefix, files, excluded_files=None):
        self = object.__new__(Env)
        self.prefix = prefix
        self.files = files
        self._excluded_files = excluded_files or []
        return self

    def __repr__(self):
        return 'Env<%r, %d files>' % (self.prefix, len(self))

    def __len__(self):
        return len(self.files)

    def __iter__(self):
        return iter(self.files)

    @property
    def name(self):
        """The name of the environment"""
        return os.path.basename(self.prefix)

    def exclude(self, pattern):
        """Exclude all files that match ``pattern`` from being packaged.

        This can be useful to remove functionality that isn't needed in the
        archive but is part of the original virtual environment.

        Parameters
        ----------
        pattern : str
            A file pattern. May include shell-style wildcards a-la ``glob``.

        Returns
        -------
        env : Env
            A new env with any matching files excluded.

        Examples
        --------

        Exclude all ``*.pyx`` files, except those from ``cytoolz``.

        >>> env = (Env().exclude("*.pyx")
        ...             .include("lib/python3.6/site-packages/cytoolz/*.pyx"))
        Env<'/full/path/to/environment', 1234 files>

        See Also
        --------
        include
        """
        files = []
        excluded = list(self._excluded_files)  # copy
        include = files.append
        exclude = excluded.append
        for f in self.files:
            if fnmatch(f.target, pattern):
                exclude(f)
            else:
                include(f)
        return Env._new(self.prefix, files, excluded)

    def include(self, pattern):
        """Re-add all excluded files that match ``pattern``

        Parameters
        ----------
        pattern : str
            A file pattern. May include shell-style wildcards a-la ``glob``.

        Returns
        -------
        env : Env
            A new env with any matching files that were previously excluded
            re-included.

        See Also
        --------
        exclude
        """
        files = list(self.files)  # copy
        excluded = []
        include = files.append
        exclude = excluded.append
        for f in self._excluded_files:
            if fnmatch(f.target, pattern):
                include(f)
            else:
                exclude(f)
        return Env._new(self.prefix, files, excluded)

    def _output_and_format(self, output=None, format='infer'):
        if output is None and format == 'infer':
            format = 'tar.gz'
        elif format == 'infer':
            if output.endswith('.zip'):
                format = 'zip'
            elif output.endswith('.tar.gz') or output.endswith('.tgz'):
                format = 'tar.gz'
            elif output.endswith('.tar.bz2') or output.endswith('.tbz2'):
                format = 'tar.bz2'
            elif output.endswith('.tar'):
                format = 'tar'
            else:
                raise VenvPackException("Unknown file extension %r" % output)
        elif format not in {'zip', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar'}:
            raise VenvPackException("Unknown format %r" % format)

        if output is None:
            output = os.extsep.join([self.name, format])

        return output, format

    def pack(self, output=None, format='infer', verbose=False,
             force=False, compress_level=4, zip_symlinks=False, zip_64=True):
        """Package the virtual environment into an archive file.

        Parameters
        ----------
        output : str, optional
            The path of the output file. Defaults to the environment name with a
            ``.tar.gz`` suffix (e.g. ``my_env.tar.gz``).
        format : {'infer', 'zip', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar'}
            The archival format to use. By default this is inferred by the
            output file extension.
        verbose : bool, optional
            If True, progress is reported to stdout. Default is False.
        force : bool, optional
            Whether to overwrite any existing archive at the output path.
            Default is False.
        compress_level : int, optional
            The compression level to use, from 0 to 9. Higher numbers decrease
            output file size at the expense of compression time. Ignored for
            ``format='zip'``. Default is 4.
        zip_symlinks : bool, optional
            Symbolic links aren't supported by the Zip standard, but are
            supported by *many* common Zip implementations. If True, store
            symbolic links in the archive, instead of the file referred to
            by the link. This can avoid storing multiple copies of the same
            files. *Note that the resulting archive may silently fail on
            decompression if the ``unzip`` implementation doesn't support
            symlinks*. Default is False. Ignored if format isn't ``zip``.
        zip_64 : bool, optional
            Whether to enable ZIP64 extensions. Default is True.

        Returns
        -------
        out_path : str
            The path to the archived environment.
        """
        # The output path and archive format
        output, format = self._output_and_format(output, format)

        if os.path.exists(output) and not force:
            raise VenvPackException("File %r already exists" % output)

        if verbose:
            print("Packing environment at %r to %r" % (self.prefix, output))

        fd, temp_path = tempfile.mkstemp()

        try:
            with os.fdopen(fd, 'wb') as temp_file:
                with archive(temp_file, format,
                             compress_level=compress_level,
                             zip_symlinks=zip_symlinks,
                             zip_64=zip_64) as arc:
                    packer = Packer(self.prefix, arc)
                    with progressbar(self.files, enabled=verbose) as files:
                        try:
                            for f in files:
                                packer.add(f)
                            packer.finish()
                        except zipfile.LargeZipFile:
                            raise VenvPackException(
                                "Large Zip File: ZIP64 extensions required "
                                "but were disabled")

        except Exception:
            # Writing failed, remove tempfile
            os.remove(temp_path)
            raise
        else:
            # Writing succeeded, move archive to desired location
            shutil.move(temp_path, output)

        return output


class File(namedtuple('File', ('source', 'target'))):
    """A single archive record.

    Parameters
    ----------
    source : str
        Absolute path to the source.
    target : str
        Relative path from the target prefix (e.g. ``lib/foo/bar.py``).
    """
    pass


def pack(prefix=None, output=None, format='infer', verbose=False, force=False,
         compress_level=4, zip_symlinks=False, zip_64=True, filters=None):
    """Package an existing virtual environment into an archive file.

    Parameters
    ----------
    prefix : str, optional
        A path to a virtual environment to pack.
    output : str, optional
        The path of the output file. Defaults to the environment name with a
        ``.tar.gz`` suffix (e.g. ``my_env.tar.gz``).
    format : {'infer', 'zip', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar'}, optional
        The archival format to use. By default this is inferred by the output
        file extension.
    verbose : bool, optional
        If True, progress is reported to stdout. Default is False.
    force : bool, optional
        Whether to overwrite any existing archive at the output path. Default
        is False.
    compress_level : int, optional
        The compression level to use, from 0 to 9. Higher numbers decrease
        output file size at the expense of compression time. Ignored for
        ``format='zip'``. Default is 4.
    zip_symlinks : bool, optional
        Symbolic links aren't supported by the Zip standard, but are supported
        by *many* common Zip implementations. If True, store symbolic links in
        the archive, instead of the file referred to by the link. This can
        avoid storing multiple copies of the same files. *Note that the
        resulting archive may silently fail on decompression if the ``unzip``
        implementation doesn't support symlinks*. Default is False. Ignored if
        format isn't ``zip``.
    zip_64 : bool, optional
        Whether to enable ZIP64 extensions. Default is True.
    filters : list, optional
        A list of filters to apply to the files. Each filter is a tuple of
        ``(kind, pattern)``, where ``kind`` is either ``'exclude'`` or
        ``'include'`` and ``pattern`` is a file pattern. Filters are applied in
        the order specified.

    Returns
    -------
    out_path : str
        The path to the archived environment.
    """
    if verbose:
        print("Collecting packages...")

    env = Env(prefix=prefix)

    if filters is not None:
        for kind, pattern in filters:
            if kind == 'exclude':
                env = env.exclude(pattern)
            elif kind == 'include':
                env = env.include(pattern)
            else:
                raise VenvPackException("Unknown filter of kind %r" % kind)

    return env.pack(output=output, format=format,
                    verbose=verbose, force=force,
                    compress_level=compress_level,
                    zip_symlinks=zip_symlinks, zip_64=zip_64)


def normalize_prefix(prefix=None):
    if prefix is None:
        if sys.base_prefix == sys.prefix:
            raise VenvPackException("Current environment is not a "
                                    "virtual environment")
        prefix = sys.prefix

    prefix = os.path.abspath(prefix)

    if not os.path.exists(prefix):
        raise VenvPackException("Environment path %r doesn't exist" % prefix)

    if not os.path.exists(os.path.join(prefix, 'pyvenv.cfg')):
        raise VenvPackException("%r is not a valid virtual environment" % prefix)

    return prefix


def find_site_packages(prefix):
    if on_win:
        return 'Lib/site-packages'

    # Ensure there is at most one version of python installed
    pythons = glob.glob(os.path.join(prefix, 'lib', 'python*'))

    if len(pythons) > 1:  # pragma: nocover
        raise VenvPackException("Unexpected failure, multiple versions of "
                                "python found in prefix %r" % prefix)
    elif not pythons:  # pragma: nocover
        raise VenvPackException("Unexpected failure, no version of "
                                "python found in prefix %r" % prefix)

    return os.path.join(pythons[0], 'site-packages')


def check_no_editable_packages(prefix, site_packages):
    pth_files = glob.glob(os.path.join(prefix, site_packages, '*.pth'))
    editable_packages = set()
    for pth_fil in pth_files:
        dirname = os.path.dirname(pth_fil)
        with open(pth_fil) as pth:
            for line in pth:
                if line.startswith('#'):
                    continue
                line = line.rstrip()
                if line:
                    location = os.path.normpath(os.path.join(dirname, line))
                    if not location.startswith(prefix):
                        editable_packages.add(line)
    if editable_packages:
        msg = ("Cannot pack an environment with editable packages\n"
               "installed (e.g. from `python setup.py develop` or\n "
               "`pip install -e`). Editable packages found:\n\n"
               "%s") % '\n'.join('- %s' % p for p in sorted(editable_packages))
        raise VenvPackException(msg)


def load_environment(prefix):
    from os.path import relpath, join, isfile, islink

    prefix = normalize_prefix(prefix)

    site_packages = find_site_packages(prefix)
    check_no_editable_packages(prefix, site_packages)

    # Files to ginore
    remove = {join(BIN_DIR, f) for f in ['activate', 'activate.csh',
                                         'activate.fish', 'deactivate']}

    res = []

    for fn in os.listdir(prefix):
        full_path = join(prefix, fn)
        if isfile(full_path):
            res.append(fn)
        else:
            for root, dirs, files in os.walk(full_path):
                root2 = relpath(root, prefix)

                if not dirs and not files:
                    # root2 is an empty directory, add it
                    res.append(root2)
                    continue

                # Add all files
                res.extend(join(root2, fn2) for fn2 in files)

                for d in dirs:
                    if islink(join(root, d)):
                        # Symbolic link, add it directly
                        res.append(join(root2, d))

    files = [File(os.path.join(prefix, p), p)
             for p in res
             if not (p in remove or p.endswith('~') or p.endswith('.DS_STORE'))]

    return prefix, files


def rewrite_shebang(data, target, prefix):
    """Rewrite a shebang header to ``#!usr/bin/env program...``.

    Returns
    -------
    data : bytes
    fixed : bool
        Whether the file was successfully fixed in the rewrite.
    """
    shebang_match = re.match(SHEBANG_REGEX, data, re.MULTILINE)
    prefix_b = prefix.encode('utf-8')

    if shebang_match:
        if data.count(prefix_b) > 1:
            # More than one occurrence of prefix, can't fully cleanup.
            return data, False

        shebang, executable, options = shebang_match.groups()

        if executable.startswith(prefix_b):
            # shebang points inside environment, rewrite
            executable_name = executable.decode('utf-8').split('/')[-1]
            new_shebang = '#!/usr/bin/env %s%s' % (executable_name,
                                                   options.decode('utf-8'))
            data = data.replace(shebang, new_shebang.encode('utf-8'))

        return data, True

    return data, False


class Packer(object):
    def __init__(self, prefix, archive):
        self.prefix = prefix
        self.archive = archive
        self.prefixes = []

    def add(self, file):
        if (file.target.startswith(BIN_DIR) and not
                (os.path.isdir(file.source) or os.path.islink(file.source))):
            with open(file.source, 'rb') as fil:
                data = fil.read()
            data, _ = rewrite_shebang(data, file.target, self.prefix)
            self.archive.add_bytes(file.source, data, file.target)
        else:
            self.archive.add(file.source, file.target)

    def finish(self):
        script_dirs = ['common']
        if on_win:
            # TODO: windows
            script_dirs.append('nt')
        for d in script_dirs:
            dirpath = os.path.join(SCRIPTS, d)
            for f in os.listdir(dirpath):
                source = os.path.join(dirpath, f)
                target = os.path.join(BIN_DIR, f)
                self.archive.add(source, target)
