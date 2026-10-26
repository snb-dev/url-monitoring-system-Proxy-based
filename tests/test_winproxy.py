"""SystemProxy against an in-memory stand-in for the Windows registry."""

import json
import subprocess
import sys

import pytest

from urlmonitor import cli, winproxy
from urlmonitor.winproxy import (
    INTERNET_SETTINGS_KEY,
    PROXY_BYPASS,
    RUN_ONCE_KEY,
    RUN_ONCE_NAME,
    SystemProxy,
)


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2

    def __init__(self, values):
        self.keys = {INTERNET_SETTINGS_KEY: dict(values), RUN_ONCE_KEY: {}}

    class _Key:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, path, reserved=0, access=0):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self._Key(self.keys[path])

    def CreateKey(self, root, path):
        return self._Key(self.keys.setdefault(path, {}))

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name]

    def SetValueEx(self, key, name, reserved, value_type, value):
        key.values[name] = (value, value_type)

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


@pytest.fixture
def registry(monkeypatch):
    fake = FakeWinreg({"ProxyEnable": (1, 4), "ProxyServer": ("corp:3128", 1)})
    monkeypatch.setattr(winproxy, "winreg", fake, raising=False)
    monkeypatch.setattr(winproxy, "notify_proxy_change", lambda: None)
    return fake


@pytest.fixture
def proxy(tmp_path):
    return SystemProxy(tmp_path / "proxy_state.json", "127.0.0.1:8081")


def test_enable_then_restore_puts_back_user_settings(registry, proxy):
    settings = registry.keys[INTERNET_SETTINGS_KEY]
    run_once = registry.keys[RUN_ONCE_KEY]

    proxy.enable()
    assert settings["ProxyServer"] == ("127.0.0.1:8081", 1)
    assert settings["ProxyOverride"][0] == PROXY_BYPASS
    assert proxy.is_active()
    assert str(proxy.state_file) in run_once[RUN_ONCE_NAME][0]
    assert json.loads(proxy.state_file.read_text())["ProxyServer"] == ["corp:3128", 1]

    assert proxy.restore() is True
    assert settings == {"ProxyEnable": (1, 4), "ProxyServer": ("corp:3128", 1)}
    assert RUN_ONCE_NAME not in run_once
    assert not proxy.state_file.exists()
    assert proxy.restore() is False


def test_enable_twice_keeps_original_settings(registry, proxy):
    proxy.enable()
    proxy.enable()
    proxy.restore()
    assert registry.keys[INTERNET_SETTINGS_KEY]["ProxyServer"] == ("corp:3128", 1)


def test_restore_with_corrupt_state_turns_proxy_off(registry, proxy):
    proxy.enable()
    proxy.state_file.write_text("{not json")
    assert proxy.restore() is True
    assert registry.keys[INTERNET_SETTINGS_KEY]["ProxyEnable"] == (0, 4)


def test_turn_off_leftover(registry, proxy):
    settings = registry.keys[INTERNET_SETTINGS_KEY]
    assert proxy.turn_off_leftover() is False
    settings["ProxyServer"] = ("127.0.0.1:8081", 1)
    assert proxy.turn_off_leftover() is True
    assert settings["ProxyEnable"] == (0, 4)


def test_restore_command_restores(registry, proxy, monkeypatch):
    monkeypatch.setattr(cli, "IS_WINDOWS", True)
    proxy.enable()
    command = winproxy.restore_command(proxy.state_file)
    assert '"_restore"' in command
    assert cli.main(["_restore", str(proxy.state_file)]) == 0
    assert registry.keys[INTERNET_SETTINGS_KEY]["ProxyServer"] == ("corp:3128", 1)


def test_launcher_runs_standalone(tmp_path):
    # Windows runs it by path at sign-in, from an unrelated working directory.
    result = subprocess.run(
        [sys.executable, str(winproxy.LAUNCHER_SCRIPT), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("urlmonitor ")


def test_program_command(tmp_path, monkeypatch):
    command = winproxy.program_command("_restore", tmp_path / "proxy state.json")
    assert f'"{winproxy.LAUNCHER_SCRIPT}"' in command
    assert f'"{tmp_path / "proxy state.json"}"' in command
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert winproxy.program_command("start") == f'"{sys.executable}" "start"'


def test_autostart(registry):
    run = registry.keys[winproxy.RUN_KEY] = {}
    assert not winproxy.is_autostart_enabled()
    winproxy.set_autostart(True)
    assert winproxy.is_autostart_enabled()
    assert run[winproxy.RUN_NAME][0].endswith('"start"')
    winproxy.set_autostart(False)
    winproxy.set_autostart(False)
    assert not winproxy.is_autostart_enabled()
