"""Make six's namespace importer compatible with Python 3.12 module repr inspection.

Shiboken inspects modules imported by pynput.  Python 3.12 expects namespace
loaders to expose ``_path``, which six's meta-path importer does not provide.
"""

import sys

import six


for finder in sys.meta_path:
    if finder.__class__.__name__ == "_SixMetaPathImporter" and not hasattr(finder, "_path"):
        finder._path = []
