"""Checks against the real Windows registry, console and certificate tools.

They change the current user's proxy and startup settings for a moment, so they
only run when URLMON_WINDOWS_INTEGRATION=1 (set in CI).
"""

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("URLMON_WINDOWS_INTEGRATION") != "1",
    reason="Windows integration tests are opt-in: set URLMON_WINDOWS_INTEGRATION=1",
)

from urlmonitor import certs, winproxy  # noqa: E402
from urlmonitor.winproxy import (  # noqa: E402
    CTRL_CLOSE_EVENT,
    RUN_ONCE_KEY,
    RUN_ONCE_NAME,
    SystemProxy,
)


def run_once_value():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_ONCE_KEY) as key:
            return winreg.QueryValueEx(key, RUN_ONCE_NAME)[0]
    except FileNotFoundError:
        return None


@pytest.fixture
def proxy(tmp_path):
    proxy = SystemProxy(tmp_path / "proxy_state.json", "127.0.0.1:18081")
    yield proxy
    proxy.restore()


def test_enable_and_restore(proxy):
    before = winproxy.read_proxy_settings()
    proxy.enable()
    assert proxy.is_active()
    assert "_restore" in run_once_value()

    assert proxy.restore()
    assert winproxy.read_proxy_settings() == before
    assert not proxy.is_active()
    assert run_once_value() is None


def test_console_close_handler_restores(proxy):
    before = winproxy.read_proxy_settings()
    proxy.install_exit_handlers()
    proxy.enable()
    # Call the handler the way Windows does when the console window is closed.
    proxy._console_handler(CTRL_CLOSE_EVENT)
    assert winproxy.read_proxy_settings() == before


def test_autostart():
    was_enabled = winproxy.is_autostart_enabled()
    try:
        winproxy.set_autostart(True)
        assert winproxy.is_autostart_enabled()
        winproxy.set_autostart(False)
        assert not winproxy.is_autostart_enabled()
    finally:
        winproxy.set_autostart(was_enabled)


def test_new_ca_is_not_trusted(tmp_path):
    certs.ensure_ca(tmp_path)
    assert certs.is_trusted(tmp_path) is False
