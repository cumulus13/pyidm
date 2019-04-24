#!/usr/bin/env python2

import imp
version = imp.load_source('version', "../__version__.py")
__version__ 	= version.version
__email__		= "licface@yahoo.com"
__author__		= "licface@yahoo.com"

from idm import *