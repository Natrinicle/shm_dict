# -*- coding: utf-8 -*-

# Standard library imports
try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping

import mmap
import mock
import os
from random import SystemRandom
import re
from string import ascii_letters as str_ascii_letters, digits as str_digits

# Related third party imports (If you used pip/apt/yum to install)
import posix_ipc
import pytest

# Local application/library specific imports (Look ma! I wrote it myself!)
import shm_dict
from shm_dict import SHMDict
from shm_dict import __version__

__author__ = "Nate Bohman"
__credits__ = ["Nate Bohman"]
__license__ = "LGPL-3"
__maintainer__ = "Nate Bohman"
__email__ = "natrinicle@natrinicle.com"
__status__ = "Production"


# Global variables
KEY_SEQUENCE = 0
B64_INVALID_CHARS = re.compile(r"[^a-zA-Z0-9+/='-_]")
str_ascii = "".join([str_ascii_letters, str_digits])


def rand_string(num_chars, use_chars=str_ascii):
    """Generate a random string of chars from use_chars.

    :type num_chars: int
    :param num_chars: Desired length of random string.
    :return: A string of length num_chars composed of random characters from use_chars.
    """
    return "".join(SystemRandom().choice(use_chars) for _ in range(num_chars))


@pytest.fixture()
def dict_key():
    global KEY_SEQUENCE
    next_key = "KEY{}".format(KEY_SEQUENCE)
    KEY_SEQUENCE += 1
    return next_key


@pytest.fixture
def os_path_mock(monkeypatch, tmpdir):
    """Disable looking up actual paths."""

    def _return_tmp_file(arg):
        return str(
            os.path.join(str(tmpdir), "".join(["pytest_shm_dict_", rand_string(10)]))
        )

    os_path_mock = mock.Mock()
    attrs = {
        "expanduser.side_effect": _return_tmp_file,
        "realpath.side_effect": _return_tmp_file,
        "abspath.side_effect": _return_tmp_file,
    }
    os_path_mock.configure_mock(**attrs)

    return os_path_mock


class TestSHMDict(object):

    _tmpfile_prefix = "pytest_shm_dict_"
    _tmpfile_rand = ""
    per_shm_dict = None
    vol_shm_dict = None

    def create_per_shm_dict(self, temp_dir):
        """Create a persistent shared memory dictionary for testing."""
        self.per_shm_dict = SHMDict(
            self.dict_filename(temp_dir), persist=True, lock_timeout=0
        )
        return self.per_shm_dict

    def create_vol_shm_dict(self):
        """Create a volatile shared memory dictionary for testing."""
        self.vol_shm_dict = SHMDict("PyTestSHMDict", lock_timeout=0)
        return self.vol_shm_dict

    def dict_filename(self, temp_dir):
        return os.path.join(
            str(temp_dir), "".join([self._tmpfile_prefix, self._tmpfile_rand])
        )

    def setup_method(self, method):
        # Set up one time random string for temp filename and make
        # sure the temp test file doesn't already exist
        self._tmpfile_rand = rand_string(10)

    def teardown_method(self, method):
        if self.per_shm_dict is not None:
            while self.per_shm_dict.semaphore.value > 0:
                self.per_shm_dict.semaphore.acquire()
            while self.per_shm_dict.semaphore.value <= 0:
                self.per_shm_dict.semaphore.release()
            del self.per_shm_dict

        if self.vol_shm_dict is not None:
            while self.vol_shm_dict.semaphore.value > 0:
                self.vol_shm_dict.semaphore.acquire()
            while self.vol_shm_dict.semaphore.value <= 0:
                self.vol_shm_dict.semaphore.release()
            del self.vol_shm_dict

    def test_types(self):
        self.create_per_shm_dict("test")
        self.create_vol_shm_dict()

        assert isinstance(self.per_shm_dict, MutableMapping)
        assert isinstance(self.vol_shm_dict, MutableMapping)
        assert isinstance(self.per_shm_dict, SHMDict)
        assert isinstance(self.vol_shm_dict, SHMDict)

        assert isinstance(self.per_shm_dict.semaphore, posix_ipc.Semaphore)
        assert isinstance(self.vol_shm_dict.semaphore, posix_ipc.Semaphore)

        assert isinstance(self.per_shm_dict.shared_mem, posix_ipc.SharedMemory)
        assert isinstance(self.vol_shm_dict.shared_mem, posix_ipc.SharedMemory)

        assert isinstance(self.per_shm_dict.map_file, mmap.mmap)
        assert isinstance(self.vol_shm_dict.map_file, mmap.mmap)

    def test_persist_filename(self, monkeypatch, os_path_mock):
        with monkeypatch.context() as monkey:
            monkey.setattr("os.path", os_path_mock)
            self.create_per_shm_dict("test")
            self.create_vol_shm_dict()

            # Ensure persistent shm_dict has a str representation
            # of a path in persist_file
            assert isinstance(self.per_shm_dict.persist_file, str)
            assert self.per_shm_dict.persist_file == os.path.abspath("test")

            # Ensure volatile shm_dict has no persist_file
            assert self.vol_shm_dict.persist_file is None

    def test_persist_filename_homedir(self, monkeypatch, os_path_mock):
        with monkeypatch.context() as monkey:
            monkey.setattr("os.path", os_path_mock)
            self.create_per_shm_dict("~/test")

            # Ensure persistent shm_dict has a str representation
            # of a path in persist_file
            assert isinstance(self.per_shm_dict.persist_file, str)
            assert self.per_shm_dict.persist_file == os.path.abspath("test")

    def test_safe_names(self, tmpdir):
        self.create_per_shm_dict(tmpdir)

        # Ensure both sem and shm names begin with / per
        # http://semanchuk.com/philip/posix_ipc
        assert self.per_shm_dict.safe_sem_name.startswith("/")
        assert self.per_shm_dict.safe_shm_name.startswith("/")

        # Ensure only base64 characters are used
        assert B64_INVALID_CHARS.search(self.per_shm_dict.safe_sem_name) is None
        assert B64_INVALID_CHARS.search(self.per_shm_dict.safe_shm_name) is None

    def test_persistent_file(self, tmpdir, dict_key):
        """Test that a persistent file is written to disk """
        test_rand_string = rand_string(10)
        self.create_per_shm_dict(tmpdir)
        self.create_vol_shm_dict()

        # File should be created after first dict release
        self.per_shm_dict[dict_key] = test_rand_string

        # Make sure the file exists and the contents are correct
        assert os.path.isfile(self.dict_filename(tmpdir))
        assert self.per_shm_dict.get(dict_key) == test_rand_string

        # Ensure the file exists after dict is deleted
        del self.per_shm_dict
        assert os.path.isfile(self.dict_filename(tmpdir))

        # Re-open dict from test file
        self.create_per_shm_dict(tmpdir)

        # Make sure the contents are still the same after reopening
        assert self.per_shm_dict.get(dict_key) == test_rand_string

    def test_get_set(self, tmpdir, dict_key):
        test_rand_string = rand_string(10)
        self.create_per_shm_dict(tmpdir)
        self.create_vol_shm_dict()

        # Assign value to key and make sure it gets set
        self.per_shm_dict[dict_key] = test_rand_string

        # Check that the persistent dict has the key
        assert self.per_shm_dict.has_key(dict_key) is True

        # Check the value of the key to ensure no corruption
        assert self.per_shm_dict[dict_key] == test_rand_string

        # Use update to set the key in the volatile dict
        # from the value in the persistent dict
        self.vol_shm_dict.update(self.per_shm_dict)

        # Check the keys and values of the volatile dict
        assert list(self.vol_shm_dict.keys()) == [dict_key]
        assert list(self.vol_shm_dict.values()) == [test_rand_string]
        assert list(self.vol_shm_dict.items()) == [(dict_key, test_rand_string)]
        for key in iter(self.vol_shm_dict):
            assert self.vol_shm_dict[key] == test_rand_string

        # Test popping a key from the dictionary
        assert self.vol_shm_dict.pop(dict_key) == test_rand_string
        assert (dict_key in self.vol_shm_dict) == False

        # Delete key and make sure it's deleted
        del self.per_shm_dict[dict_key]
        assert self.per_shm_dict.get(dict_key) is None

    def test_copy(self, tmpdir, dict_key):
        test_rand_string = rand_string(10)
        self.create_per_shm_dict(tmpdir)

        # Assign value to a key and then copy to a
        # testing dictionary object.
        self.per_shm_dict[dict_key] = test_rand_string
        dict_copy = self.per_shm_dict.copy()

        # Delete key from persistent dict and make sure
        # it's deleted only from the persistent dict as
        # the dict copy should be a new dict and not a
        # pointer to the persistent dict.
        assert self.per_shm_dict[dict_key] == test_rand_string
        del self.per_shm_dict[dict_key]
        assert self.per_shm_dict.get(dict_key) is None
        assert dict_copy[dict_key] == test_rand_string
        del dict_copy[dict_key]
        assert dict_copy.get(dict_key) is None

    def test_equality(self, tmpdir, dict_key):
        test_rand_string = rand_string(10)
        self.create_per_shm_dict(tmpdir)
        self.create_vol_shm_dict()

        # Assign value to a key and then copy the pointer
        # to the volatile dict to another object.
        self.vol_shm_dict[dict_key] = test_rand_string
        self.per_shm_dict[dict_key] = test_rand_string
        dict_dup = self.vol_shm_dict

        assert self.vol_shm_dict == dict_dup
        assert (self.vol_shm_dict == {dict_key: test_rand_string}) == False

        assert self.vol_shm_dict != {dict_key: test_rand_string}
        assert self.vol_shm_dict != self.per_shm_dict

    def test_len(self, dict_key):
        self.create_vol_shm_dict()

        # Make sure dict starts out empty
        assert len(self.vol_shm_dict) == 0

        # Add 1 key to the dict and make sure dict has 1 key
        self.vol_shm_dict[dict_key] = rand_string(10)
        assert len(self.vol_shm_dict) == 1

    def test_clear(self, dict_key):
        test_rand_string = rand_string(10)
        self.create_vol_shm_dict()

        # Assign value to key and make sure it gets set
        self.vol_shm_dict[dict_key] = test_rand_string
        assert self.vol_shm_dict[dict_key] == test_rand_string

        # Clean dict and ensure it's empty again
        self.vol_shm_dict.clear()
        assert len(self.vol_shm_dict) == 0

    def test_lock(self):
        self.create_vol_shm_dict()

        # Simulate another thread/process having a lock
        # with the semaphore value at 0 and the internal
        # semaphore not set to true.
        while self.vol_shm_dict.semaphore.value > 0:
            self.vol_shm_dict.semaphore.acquire()

        with pytest.raises(posix_ipc.BusyError, match=r".*Semaphore is busy.*"):
            repr(self.vol_shm_dict)

        # Set auto_unlock to True to ensure the semaphore
        # is automatically released
        self.vol_shm_dict.auto_unlock = True

        repr(self.vol_shm_dict)
