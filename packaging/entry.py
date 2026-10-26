"""Entry point for the PyInstaller build (URLMonitor.exe)."""

import sys

from urlmonitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
