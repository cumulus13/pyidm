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

# Determine the packages based on the extra provided
extra_packages = ['idm']
if 'pyidm' in os.environ.get('EXTRAS', '').split(','):
    extra_packages = ['pyidm']

setup(
    name="idm",
    version=version,
    url="https://github.com/cumulus13/pyidm",
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
    packages=find_packages(),
    install_requires=[
        'argparse',
        'pypiwin32; platform_system=="Windows"',
        'comtypes; platform_system=="Windows"', 
        'configset', 
        'pydebugger',
        'make_colors'
    ],
    extras_require={
        'pyidm': [],
    },
    entry_points={
        "console_scripts": [
            "idm = idm.__main__:usage",
            "pyidm = idm.__main__:usage",
        ]
    },
    data_files=['__version__.py', 'README.md', 'LICENSE.rst'],
    include_package_data=True,
    python_requires=">=2.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GPL License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
    ],
)
