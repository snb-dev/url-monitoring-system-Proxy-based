"""Runs URL Monitor by file path: `python _launcher.py <command>`.

Windows uses this for the commands it runs at sign-in (restoring the proxy after
a crash, and starting automatically), because `python -m urlmonitor` only works
from the folder containing the package unless it was installed with pip.
"""

import os
import sys

if __name__ == "__main__":
    # Make the folder containing the package importable, in place of this
    # file's own folder.
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    from urlmonitor.cli import main

    sys.exit(main())
