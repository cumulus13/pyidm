import io
import re
from setuptools import setup

import os
import shutil

#  try:
    #  shutil.rmtree(os.path.join(os.path.dirname(__file__), 'build'))
#  except:
    #  pass
#  try:
    #  shutil.rmtree(os.path.join(os.path.dirname(__file__), 'dist'))
#  except:
    #  pass
try:
    os.makedirs(os.path.join(os.path.dirname(__file__), 'pyidm'))
except:
    pass
shutil.copy2(os.path.join(os.path.dirname(__file__), 'idm', 'idm.py'), 'pyidm')
shutil.copy2(os.path.join(os.path.dirname(__file__), 'idm', '__main__.py'), 'pyidm')
shutil.copy2(os.path.join(os.path.dirname(__file__), 'idm', '__version__.py'), 'pyidm')
shutil.copy2(os.path.join(os.path.dirname(__file__), 'idm', '__init__.py'), 'pyidm')

with io.open("README.rst", "rt", encoding="utf8") as f:
    readme = f.read()

import __version__
version = __version__.version

setup(
    name="pyidm",
    version=version,
    url="https://bitbucket.org/licface/idm",
    project_urls={
        "Documentation": "https://github.com/cumulus13/pyidm",
        "Code": "https://github.com/cumulus13/pyidm",
    },
    license="GPL",
    author="Hadi Cahyadi LD",
    author_email="cumulus13@gmail.com",
    maintainer="cumulus13 Team",
    maintainer_email="cumulus13@gmail.com",
    description="Downloader with Internet Download Manager (Windows)",
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=["pyidm"],
    install_requires=[
        'argparse',
        'pypiwin32',
        'comtypes'
    ],
    entry_points = {
         "console_scripts": [
             "pyidm = pyidm.__main__:usage",
             "idm = pyidm.__main__:usage"
         ]
    },
    data_files=['__version__.py', 'README.md', 'LICENSE.rst'],
    include_package_data=True,
    python_requires=">=2.7.*",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
    ],
)
s