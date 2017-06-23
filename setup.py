#!/usr/bin/env python3

import sys
from setuptools import setup

if sys.version_info[0] < 3 or sys.version_info[1] < 3:
    sys.exit("Sorry, you need at least python 3.3 for pg_gnufind")

setup(
    name='ttfkam',
    version='__VERSION__',
    author='ttfkam',
    license='GPL2',
    package_dir={'': 'python'},
    packages=[],
    ext_modules = []
)
