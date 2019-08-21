# -*- coding: utf-8 -*-

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from ._version import __version__
from .shm_dict import SHMDict
