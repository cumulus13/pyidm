#!/usr/bin/env python3

# File: setup.py
# Author: Hadi Cahyadi <cumulus13@gmail.com>
# Date: 2026-10-26
# Description: 
# License: MIT

import io
from setuptools import setup, find_packages
import shutil
import os

# Ensure the appropriate directory exists and copy __version__.py into it
#if not os.path.exists('idm'):
    #os.makedirs('idm')
shutil.copy2('__version__.py', 'idm')

# Read the README file
with io.open("README.md", "rt", encoding="utf8") as f:
    readme = f.read()

# Read the version from idm/__version__.py
version = {}
with open("idm/__version__.py") as fp:
    exec(fp.read(), version)
version = version['version']

# Install layout (same package, pip picks the right parts by itself):
#
#   pip install idm          auto: portable agent client everywhere; on Windows ONLY it also pulls
#                            comtypes + pywin32 (environment markers) = agent server + COM.
#   pip install idm[agent]   explicit agent client (portable, any OS)
#   pip install idm[com]     + comtypes            (Windows only, ignored elsewhere)
#   pip install idm[win]     + comtypes + pywin32  (Windows only, ignored elsewhere)
#   pip install idm[all]     everything for the current OS
#
# Windows-only packages are NEVER required on Linux/macOS, so install never fails there.
# 'idm-agent' (PYIDM_AGENT_ONLY=1 python -m build) = same code, never installs COM packages, not even on Windows.
AGENT_ONLY = os.environ.get('PYIDM_AGENT_ONLY', '').strip().lower() in ('1', 'true', 'yes', 'on')
COM_ONLY = ['comtypes; sys_platform == "win32"']
WINDOWS_ONLY = COM_ONLY + ['pywin32; sys_platform == "win32"']

# Determine the packages based on the extra provided
extra_packages = ['idm']
if 'pyidm' in os.environ.get('EXTRAS', '').split(','):
    extra_packages = ['pyidm']

setup(
    name="idm-agent" if AGENT_ONLY else "idm",
    version=version,
    url="https://github.com/cumulus13/pyidm",
    project_urls={
        "Documentation": "https://github.com/cumulus13/pyidm",
        "Code": "https://github.com/cumulus13/pyidm",
    },
    license="GPL",
    author="Hadi Cahyadi",
    author_email="cumulus13@gmail.com",
    maintainer="Hadi Cahyadi",
    maintainer_email="cumulus13@gmail.com",
    description="Downloader with Internet Download Manager (Windows)",
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        'envdot',
        'configset',
        'pydebugger',
        'make_colors',
        'clipboard',
    ] + ([] if AGENT_ONLY else WINDOWS_ONLY),
    extras_require={
        'pyidm': [],
        'agent': [],
        'com': COM_ONLY,
        'win': WINDOWS_ONLY,
        'windows': WINDOWS_ONLY,
        'all': WINDOWS_ONLY,
    },
    package_data={'idm': ['idm.ini']},
    entry_points={
        "console_scripts": [
            "idm = idm.__main__:usage",
            "pyidm = idm.__main__:usage",
        ]
    },
    data_files=['__version__.py', 'README.md', 'LICENSE'],
    license_files=["LICENSE"],    
    include_package_data=True,
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        'License :: OSI Approved :: GNU General Public License (GPL)', 
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: Microsoft :: Windows",
    ],
)
