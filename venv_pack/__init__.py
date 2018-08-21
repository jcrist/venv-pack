from __future__ import absolute_import

from .core import VenvPackException, Env, File, pack

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions, absolute_import
