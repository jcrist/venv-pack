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


class AttrDict(dict):
    def __setattr__(self, key, val):
        self[key] = val

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:  # pragma: nocover
            raise AttributeError(key)


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
    __slots__ = ('_context', 'files', '_excluded_files')

    def __init__(self, prefix=None):
        context, files = load_environment(prefix)

        self._context = context
        self.files = files
        self._excluded_files = []

    def _copy_with_files(self, files, excluded_files):
        out = object.__new__(Env)
        out._context = self._context
        out.files = files
        out._excluded_files = excluded_files
        return out

    @property
    def prefix(self):
        return self._context.prefix

    @property
    def kind(self):
        return self._context.kind

    @property
    def orig_prefix(self):
        return self._context.orig_prefix

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
        return self._copy_with_files(files, excluded)

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
        return self._copy_with_files(files, excluded)

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

    def pack(self, output=None, format='infer', python_prefix=None,
             verbose=False, force=False, compress_level=4, zip_symlinks=False,
             zip_64=True):
        """Package the virtual environment into an archive file.

        Parameters
        ----------
        output : str, optional
            The path of the output file. Defaults to the environment name with a
            ``.tar.gz`` suffix (e.g. ``my_env.tar.gz``).
        format : {'infer', 'zip', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar'}
            The archival format to use. By default this is inferred by the
            output file extension.
        python_prefix : str, optional
            If provided, will be used as the new prefix path for linking
            ``python`` in the packaged environment. Note that this is the path
            to the *prefix*, not the path to the *executable* (e.g. ``/usr/``
            not ``/usr/lib/python3.6``).
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
                    packer = Packer(self._context, arc, python_prefix)
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


def pack(prefix=None, output=None, format='infer', python_prefix=None,
         verbose=False, force=False, compress_level=4, zip_symlinks=False,
         zip_64=True, filters=None):
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
    python_prefix : str, optional
        If provided, will be used as the new prefix path for linking ``python``
        in the packaged environment. Note that this is the path to the
        *prefix*, not the path to the *executable* (e.g. ``/usr/`` not
        ``/usr/lib/python3.6``).
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
                    python_prefix=python_prefix,
                    verbose=verbose, force=force,
                    compress_level=compress_level,
                    zip_symlinks=zip_symlinks, zip_64=zip_64)


def check_prefix(prefix=None):
    if prefix is None:
        prefix = os.environ.get('VIRTUAL_ENV')
        if prefix is None:
            raise VenvPackException("Current environment is not a "
                                    "virtual environment")

    prefix = os.path.abspath(prefix)

    if not os.path.exists(prefix):
        raise VenvPackException("Environment path %r doesn't exist" % prefix)

    for check in [check_venv, check_virtualenv]:
        try:
            return check(prefix)
        except VenvPackException:
            pass

    raise VenvPackException("%r is not a valid virtual environment" % prefix)


def check_venv(prefix):
    pyvenv_cfg = os.path.join(prefix, 'pyvenv.cfg')
    if not os.path.exists(pyvenv_cfg):
        raise VenvPackException("%r is not a valid virtual environment" % prefix)

    with open(pyvenv_cfg) as fil:
        for line in fil:
            key, val = line.split('=')
            if key.strip().lower() == 'home':
                orig_prefix = os.path.dirname(val.strip())
                break
        else:  # pragma: nocover
            raise VenvPackException("%r is not a valid virtual "
                                    "environment" % prefix)

    python_lib, python_include = find_python_lib_include(prefix)

    context = AttrDict()

    context.kind = 'venv'
    context.prefix = prefix
    context.orig_prefix = orig_prefix
    context.py_lib = python_lib
    context.py_include = python_include

    return context


def check_virtualenv(prefix):
    python_lib, python_include = find_python_lib_include(prefix)

    orig_prefix_txt = os.path.join(prefix, python_lib, 'orig-prefix.txt')
    if not os.path.exists(orig_prefix_txt):
        raise VenvPackException("%r is not a valid virtual environment" % prefix)
    with open(orig_prefix_txt) as fil:
        orig_prefix = fil.read().strip()

    context = AttrDict()

    context.kind = 'virtualenv'
    context.prefix = prefix
    context.orig_prefix = orig_prefix
    context.py_lib = python_lib
    context.py_include = python_include

    return context


def find_python_lib_include(prefix):
    if on_win:
        return 'Lib', 'Include'

    # Ensure there is at most one version of python installed
    pythons = glob.glob(os.path.join(prefix, 'lib', 'python*'))

    if len(pythons) > 1:  # pragma: nocover
        raise VenvPackException("Unexpected failure, multiple versions of "
                                "python found in prefix %r" % prefix)
    elif not pythons:  # pragma: nocover
        raise VenvPackException("Unexpected failure, no version of "
                                "python found in prefix %r" % prefix)

    python_ver = os.path.basename(pythons[0])
    return os.path.join('lib', python_ver), os.path.join('include', python_ver)


def check_no_editable_packages(context):
    pth_files = glob.glob(os.path.join(context.prefix,
                                       context.py_lib,
                                       'site-packages',
                                       '*.pth'))
    editable_packages = set()
    for pth_fil in pth_files:
        dirname = os.path.dirname(pth_fil)
        with open(pth_fil) as pth:
            for line in pth:
                if line.startswith('#'):  # pragma: nocover
                    continue
                line = line.rstrip()
                if line:
                    location = os.path.normpath(os.path.join(dirname, line))
                    if not location.startswith(context.prefix):
                        editable_packages.add(line)
    if editable_packages:
        msg = ("Cannot pack an environment with editable packages\n"
               "installed (e.g. from `python setup.py develop` or\n "
               "`pip install -e`). Editable packages found:\n\n"
               "%s") % '\n'.join('- %s' % p for p in sorted(editable_packages))
        raise VenvPackException(msg)


def load_environment(prefix):
    from os.path import relpath, join, isfile, islink

    context = check_prefix(prefix)

    check_no_editable_packages(context)

    # Files to ignore
    remove = {join(BIN_DIR, f) for f in ['activate', 'activate.csh',
                                         'activate.fish']}

    if context.kind == 'virtualenv':
        remove.add(join(context.prefix, context.py_lib, 'orig-prefix.txt'))
    else:
        remove.add(join(context.prefix, 'pyvenv.cfg'))

    res = []

    prefix = context.prefix
    for fn in os.listdir(prefix):
        full_path = join(prefix, fn)
        if isfile(full_path) or islink(full_path):
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

    return context, files


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
        if data.count(prefix_b) > 1:  # pragma: nocover
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


def check_python_prefix(python_prefix, context):
    if python_prefix is None:
        return None, []

    if not os.path.isabs(python_prefix):
        raise VenvPackException("python-prefix must be an absolute path")

    # Remove trailing slashes if present
    python_prefix = os.path.normpath(python_prefix)

    if context.kind == 'venv':
        # For venv environments, only need to rewrite python executables
        exe = os.path.join(context.orig_prefix, BIN_DIR, 'python')
        if not on_win:
            new_exe = os.path.join(python_prefix,
                                   BIN_DIR,
                                   os.path.basename(context.py_lib))
        else:
            new_exe = os.path.join(python_prefix, BIN_DIR, 'python')
        rewrites = [(exe, new_exe)]
    else:
        # For virtualenv environments, need to relink lib and include
        # Extra "''" is to ensure trailing slash
        rewrites = [(os.path.join(context.orig_prefix, context.py_lib, ''),
                     os.path.join(python_prefix, context.py_lib, '')),
                    (os.path.join(context.orig_prefix, context.py_include),
                     os.path.join(python_prefix, context.py_include))]

    return python_prefix, rewrites


class Packer(object):
    def __init__(self, context, archive, python_prefix):
        self.context = context
        self.prefix = context.prefix
        self.archive = archive

        python_prefix, rewrites = check_python_prefix(python_prefix, context)
        self.python_prefix = python_prefix
        self.rewrites = rewrites

    def add(self, file):
        if self.rewrites and os.path.islink(file.source):
            link_target = os.readlink(file.source)
            for orig, new in self.rewrites:
                if link_target.startswith(orig):
                    self.archive.add_link(file.source,
                                          link_target.replace(orig, new),
                                          file.target)
                    return
            self.archive.add(file.source, file.target)
        elif (file.target.startswith(BIN_DIR) and not
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

        if self.context.kind == 'venv':
            pyvenv_cfg = os.path.join(self.prefix, 'pyvenv.cfg')
            if self.python_prefix is None:
                self.archive.add(pyvenv_cfg, 'pyvenv.cfg')
            else:
                with open(pyvenv_cfg) as fil:
                    data = fil.read()
                data = data.replace(self.context.orig_prefix,
                                    self.python_prefix)
                self.archive.add_bytes(pyvenv_cfg, data.encode(), 'pyvenv.cfg')
        else:
            origprefix_txt = os.path.join(self.context.prefix,
                                          self.context.py_lib,
                                          'orig-prefix.txt')
            target = os.path.relpath(origprefix_txt, self.prefix)

            if self.python_prefix is None:
                self.archive.add(origprefix_txt, target)
            else:
                self.archive.add_bytes(origprefix_txt,
                                       self.python_prefix.encode(),
                                       target)
