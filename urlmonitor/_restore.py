"""Run by Windows at login (RunOnce) to put the proxy settings back after a crash.

Usage: pythonw _restore.py <proxy_state.json>
"""

import os
import sys


def main(argv):
    from urlmonitor.winproxy import SystemProxy

    SystemProxy(argv[1], address=None).restore()


if __name__ == "__main__":
    # Run as a script, so make the folder containing the package importable
    # (in place of this file's own folder).
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv)
