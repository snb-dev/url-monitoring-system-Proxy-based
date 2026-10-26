"""Pointing Windows' per-user proxy settings at URL Monitor, and putting them back."""

import atexit
import json
import os
import sys
import threading
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import ctypes
    import winreg

INTERNET_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
RUN_ONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
RUN_ONCE_NAME = "URLMonitorRestoreProxy"
PROXY_VALUE_NAMES = ("ProxyEnable", "ProxyServer", "ProxyOverride")
PROXY_BYPASS = "localhost;127.*;<local>"
REG_SZ = 1
REG_DWORD = 4
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

RESTORE_SCRIPT = Path(__file__).resolve().with_name("_restore.py")


def write_json(path, data):
    """Write JSON atomically so a crash never leaves a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def read_proxy_settings():
    settings = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY) as key:
        for name in PROXY_VALUE_NAMES:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
                settings[name] = [value, value_type]
            except FileNotFoundError:
                settings[name] = None
    return settings


def write_proxy_settings(settings):
    """Write proxy registry values; a value of None deletes that registry value."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        for name, stored in settings.items():
            if stored is None:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            else:
                value, value_type = stored
                winreg.SetValueEx(key, name, 0, value_type, value)
    notify_proxy_change()


def notify_proxy_change():
    """Tell running browsers to re-read the proxy settings now."""
    internet_set_option = ctypes.windll.wininet.InternetSetOptionW
    internet_set_option(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    internet_set_option(None, INTERNET_OPTION_REFRESH, None, 0)


def restore_command(state_file):
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    return f'"{python}" "{RESTORE_SCRIPT}" "{state_file}"'


class SystemProxy:
    def __init__(self, state_file, address):
        self.state_file = Path(state_file)
        self.address = address
        self._lock = threading.Lock()
        self._console_handler = None

    def set_restore_on_next_login(self, enabled):
        """Register a one-time restore at next login, in case this process is killed
        or the computer shuts down before it can undo the proxy settings itself."""
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_ONCE_KEY) as key:
            if enabled:
                winreg.SetValueEx(
                    key, RUN_ONCE_NAME, 0, REG_SZ, restore_command(self.state_file)
                )
            else:
                try:
                    winreg.DeleteValue(key, RUN_ONCE_NAME)
                except FileNotFoundError:
                    pass

    def enable(self):
        with self._lock:
            if not self.state_file.exists():
                # Save the user's own settings first, so they can always be put back.
                write_json(self.state_file, read_proxy_settings())
            self.set_restore_on_next_login(True)
            write_proxy_settings(
                {
                    "ProxyEnable": [1, REG_DWORD],
                    "ProxyServer": [self.address, REG_SZ],
                    "ProxyOverride": [PROXY_BYPASS, REG_SZ],
                }
            )

    def restore(self):
        """Put back the settings saved by enable().

        Safe to call more than once; returns True if anything was restored.
        """
        with self._lock:
            if not self.state_file.exists():
                return False
            try:
                previous = json.loads(self.state_file.read_text(encoding="utf-8"))
            except ValueError:
                previous = {"ProxyEnable": [0, REG_DWORD]}
            write_proxy_settings(previous)
            self.state_file.unlink()
            self.set_restore_on_next_login(False)
            return True

    def is_active(self):
        """True if Windows is currently set to use this proxy."""
        settings = read_proxy_settings()
        server = (settings["ProxyServer"] or [""])[0]
        enabled = (settings["ProxyEnable"] or [0])[0]
        return bool(enabled) and server == self.address

    def turn_off_leftover(self):
        """Turn off the proxy if it still points here but no saved state exists,
        e.g. after a version that did not save the user's settings."""
        if self.is_active():
            write_proxy_settings({"ProxyEnable": [0, REG_DWORD]})
            self.set_restore_on_next_login(False)
            return True
        return False

    def install_exit_handlers(self):
        atexit.register(self.restore)
        # Closing the console window skips `finally` blocks and atexit, so undo
        # the proxy from a console control handler too.
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def on_console_event(event):
            if event in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
                self.restore()
            return False

        self._console_handler = handler_type(on_console_event)  # keep a reference
        ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_handler, True)
