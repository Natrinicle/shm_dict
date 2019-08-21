#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Standard library imports
import base64

try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping

from contextlib import contextmanager
import hashlib
import logging
from math import ceil
import mmap
import os
import pickle  # nosec
import sys
import threading

# Related third party imports (If you used pip/apt/yum to install)
import posix_ipc
import six

# Local application/library specific imports (Look ma! I wrote it myself!)
from ._version import __version__

__author__ = "Nate Bohman"
__credits__ = ["Nate Bohman"]
__license__ = "LGPL-3"
__maintainer__ = "Nate Bohman"
__email__ = "natrinicle-shm_dict@natrinicle.com"
__status__ = "Production"

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class SHMDict(MutableMapping):
    """Python shared memory dictionary."""

    def __init__(self, name, persist=False, lock_timeout=30, auto_unlock=False):
        """Standard init method.

        :param name: Name for shared memory and semaphore if volatile
                     or path to file if persistent.
        :param persist: True if name is the path to a file and this
                        shared memory dictionary should be written
                        out to the file for persistence between runs
                        and/or processes.
        :param lock_timeout: Time in seconds before giving up on
                             acquiring an exclusive lock to the
                             dictionary.
        :param auto_unlock: If the lock_timeout is hit, and this
                            is True, automatically bypass the
                            lock and use the dictionary anyway.
        :type name: :class:`str`
        :type persist: :class:`bool`
        :type lock_timeout: :class:`int` or :class:`float`
        :type auto_unlock: :class:`bool`
        """
        self.name = name
        self.persist_file = None
        self.lock_timeout = lock_timeout
        self.auto_unlock = auto_unlock
        self._semaphore = None
        self._map_file = None
        self.__thread_local = threading.local()
        self.__thread_local.semaphore = False
        self.__internal_dict = None
        self.__dirty = False

        if persist is True:
            self.persist_file = self.name
            if self.persist_file.startswith("~"):
                self.persist_file = os.path.expanduser(self.persist_file)
            self.persist_file = os.path.abspath(os.path.realpath(self.persist_file))

        super(SHMDict, self).__init__()

    def _safe_name(self, prefix=""):
        """IPC object safe name creator.

        Semaphores and Shared Mmeory names allow up to 256 characters (dependong on OS) and must
        begin with a /.

        :param prefix: A string to prepend followed by _ and
                       then the dictionary's name.
        :type prefix: :class:`str`
        """
        # Hash lengths
        # SHA1: 28
        # SHA256: 44
        # SHA512: 88
        sha_hash = hashlib.sha512()
        sha_hash.update("_".join([prefix, str(self.name)]).encode("utf-8"))
        b64_encode = base64.urlsafe_b64encode(sha_hash.digest())
        return "/{}".format(b64_encode)

    @property
    def safe_sem_name(self):
        """Unique semaphore name based on the dictionary name."""
        return self._safe_name("sem")

    @property
    def safe_shm_name(self):
        """Unique shared memory segment name based on the dictionary name."""
        return self._safe_name("shm")

    @property
    def semaphore(self):
        """Create or return already existing semaphore."""
        if self._semaphore is not None:
            return self._semaphore

        try:
            self._semaphore = posix_ipc.Semaphore(self.safe_sem_name)
        except posix_ipc.ExistentialError:
            self._semaphore = posix_ipc.Semaphore(
                self.safe_sem_name, flags=posix_ipc.O_CREAT, initial_value=1
            )
        return self._semaphore

    @property
    def shared_mem(self):
        """Create or return already existing shared memory object."""
        try:
            return posix_ipc.SharedMemory(
                self.safe_shm_name, size=len(pickle.dumps(self.__internal_dict))
            )
        except posix_ipc.ExistentialError:
            return posix_ipc.SharedMemory(
                self.safe_shm_name, flags=posix_ipc.O_CREX, size=posix_ipc.PAGE_SIZE
            )

    @property
    def map_file(self):
        """Create or return mmap file resizing if necessary."""
        if self._map_file is None:
            self._map_file = mmap.mmap(self.shared_mem.fd, self.shared_mem.size)
            self.shared_mem.close_fd()

        self._map_file.resize(
            int(
                ceil(float(len(pickle.dumps(self.__internal_dict, 2))) / mmap.PAGESIZE)
                * mmap.PAGESIZE
            )
        )
        return self._map_file

    def __load_dict(self):
        """Load dictionary from shared memory or file if persistent and memory empty."""
        # Read in internal data from map_file
        self.map_file.seek(0)
        try:
            self.__internal_dict = pickle.load(self.map_file)  # nosec
        except (KeyError, pickle.UnpicklingError, EOFError):
            # Curtis Pullen found that Python 3.4 throws EOFError
            # instead of UnpicklingError that Python 3.6 throws
            # when attempting to unpickle an empty file.
            pass

        # If map_file is empty and persist_file is true, treat
        # self.name as filename and attempt to load from disk.
        if self.__internal_dict is None and self.persist_file is not None:
            try:
                with open(self.persist_file, "rb") as pfile:
                    self.__internal_dict = pickle.load(pfile)  # nosec
            except IOError:
                pass

        # If map_file is empty, persist_file is False or
        # self.name is empty create a new empty dictionary.
        if self.__internal_dict is None:
            self.__internal_dict = {}

    def __save_dict(self):
        """Save dictionary into shared memory and file if persistent."""
        # Write out internal dict to map_file
        if self.__dirty is True:
            self.map_file.seek(0)
            pickle.dump(self.__internal_dict, self.map_file, 2)

            if self.persist_file is not None:
                with open(self.persist_file, "wb") as pfile:
                    pickle.dump(self.__internal_dict, pfile, 2)

        self.__dirty = False

    def _acquire_lock(self):
        """Acquire an exclusive dict lock.

        Loads dictionary data from memory or disk (if persistent) to
        ensure data is up to date when lock is requested.

        .. warnings also::
            MacOS has a number of shortcomings with regards to
            semaphores and shared memory segments, this is one
            method contains one of them.

                When the timeout is > 0, the call will wait no longer than
                timeout seconds before either returning (having acquired
                the semaphore) or raising a BusyError.
                On platforms that don't support the sem_timedwait() API,
                a timeout > 0 is treated as infinite. The call will not
                return until its wait condition is satisfied.
                Most platforms provide sem_timedwait(). macOS is a notable
                exception. The module's Boolean constant
                SEMAPHORE_TIMEOUT_SUPPORTED is True on platforms that
                support sem_timedwait().

                -- http://semanchuk.com/philip/posix_ipc/
        """
        if self.__thread_local.semaphore is False:
            try:
                self.semaphore.acquire(self.lock_timeout)
                self.__thread_local.semaphore = True
            except posix_ipc.BusyError:
                if self.auto_unlock is True:
                    self.__thread_local.semaphore = True
                else:
                    six.reraise(*sys.exc_info())

        self.__load_dict()

    def _release_lock(self):
        """Release the exclusive semaphore lock."""
        if self.__thread_local.semaphore is True:
            self.__save_dict()
            self.semaphore.release()
            self.__thread_local.semaphore = False

    @contextmanager
    def exclusive_lock(self):
        """A context manager for the lock to allow with statements for exclusive access."""
        self._acquire_lock()
        yield
        self._release_lock()

    def __del__(self):
        """Destroy the object nicely."""
        self.map_file.close()
        self.shared_mem.unlink()
        self.semaphore.unlink()

    def __setitem__(self, key, value):
        """Set a key in the dictionary to a value."""
        with self.exclusive_lock():
            self.__internal_dict[key] = value
            self.__dirty = True

    def __getitem__(self, key):
        """Get the value of a key from the dictionary."""
        with self.exclusive_lock():
            return self.__internal_dict[key]

    def __repr__(self):
        """Represent the dictionary in a human readable format."""
        with self.exclusive_lock():
            return repr(self.__internal_dict)

    def __len__(self):
        """Return the length of the dictionary."""
        with self.exclusive_lock():
            return len(self.__internal_dict)

    def __delitem__(self, key):
        """Remove an item from the dictionary."""
        with self.exclusive_lock():
            del self.__internal_dict[key]
            self.__dirty = True

    def clear(self):
        """Completely clear the dictionary."""
        with self.exclusive_lock():
            self.__dirty = True
            return self.__internal_dict.clear()

    def copy(self):
        """Create and return a copy of the internal dictionary."""
        with self.exclusive_lock():
            return self.__internal_dict.copy()

    def has_key(self, key):
        """Return true if a key is in the internal dictionary."""
        with self.exclusive_lock():
            return key in self.__internal_dict

    def __eq__(self, other):
        """Shared memory dictionary equality check with another shared memory dictionary."""
        return isinstance(other, SHMDict) and self.safe_shm_name == other.safe_shm_name

    def __ne__(self, other):
        """Shared memory dictionary non-equality check with another shared memory dictionary."""
        return not isinstance(other, SHMDict) or (
            isinstance(other, SHMDict) and self.safe_shm_name != other.safe_shm_name
        )

    def __contains__(self, key):
        """Check if a key exists inside the dictionary."""
        with self.exclusive_lock():
            return key in self.__internal_dict

    def __iter__(self):
        """Iterate through the dictionary keys."""
        with self.exclusive_lock():
            return iter(self.__internal_dict)
