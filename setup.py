#!/usr/bin/env python3

import subprocess
import sys
from setuptools import setup, find_packages, Extension

# hum... borrowed from psycopg2
def get_pg_config(kind, pg_config="pg_config"):
    p = subprocess.Popen([pg_config, '--%s' % kind], stdout=subprocess.PIPE)
    r = p.communicate()
    r = r[0].strip().decode('utf8')
    if not r:
        raise Warning(p[2].readline())
    return r

include_dirs = [get_pg_config(d) for d in ("includedir", "pkgincludedir", "includedir-server")]

requires=[]

if sys.version_info[0] < 3 or sys.version_info[1] < 3:
    sys.exit("Sorry, you need at least python 3.3 for pg_gnufind")

setup(
    name='multicorn',
    version='__VERSION__',
    author='Kozea',
    license='GPL2',
    package_dir={'': 'python'},
    packages=[],
    ext_modules = []
)
