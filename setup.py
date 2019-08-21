# -*- coding: utf-8 -*-

import warnings

from setuptools import find_packages, setup

# Ignore the normalizing version userwarning so git tagging works better
# UserWarning: Normalizing '2019.01.03.19.01' to '2019.1.3.19.1'
warnings.filterwarnings("ignore", ".*Normalizing.*", UserWarning)

# Pull in __version__ and __version_info__ from _version.py
exec(
    "".join(
        [
            _
            for _ in open("shm_dict/_version.py").readlines()
            if _.startswith("__version")
        ]
    )
)  # pylint: disable=exec-used

setup(
    name="shm_dict",
    version=__version__,  # pylint: disable=undefined-variable
    description="Shared Memory Dictionary",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nate Bohman",
    author_email="natrinicle-shm_dict@natrinicle.com",
    url="https://github.com/Natrinicle/shm_dict",
    license="LGPL-3",
    keywords="posix ipc semaphore shm shared memory dict dictionary",
    project_urls={"Source": "https://github.com/Natrinicle/shm_dict"},
    packages=find_packages(),
    install_requires=open("requirements.txt").read().split("\n"),
    extras_require={"dev": open("requirements-dev.txt").read().split("\n")},
    tests_require=open("requirements-dev.txt").read().split("\n"),
    classifiers=[
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: POSIX :: Linux",
    ],
)
