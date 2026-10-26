import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import python_backend as backend  # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    for name, filename in [
        ("DATA_DIR", ""),
        ("LOG_FILE", "traffic_log.json"),
        ("FILTERED_LOG_FILE", "filtered_traffic_log.json"),
        ("BLOCKLIST_FILE", "blocklist.txt"),
        ("DOWNLOADED_BLOCKLIST_FILE", "blocklist_downloaded.txt"),
        ("CONFIG_FILE", "config.json"),
        ("PROXY_STATE_FILE", "proxy_state.json"),
    ]:
        monkeypatch.setattr(backend, name, tmp_path / filename)
    backend.ensure_data_files()
    return tmp_path


# Blocklist matching


def test_parse_blocklist_formats():
    domains = backend.parse_blocklist(
        [
            "# comment",
            "",
            "Example.com.",
            "www.pornhub.com",
            "0.0.0.0 hosts-entry.net  # trailing comment",
            "127.0.0.1 localhost",
            "0.0.0.0 0.0.0.0",
            "https://pasted.org/some/page",
        ]
    )
    assert domains == {"example.com", "pornhub.com", "hosts-entry.net", "pasted.org"}


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://pornhub.com/", True),
        ("https://www.pornhub.com/view", True),
        ("https://de.pornhub.com/", True),
        ("https://PORNHUB.COM/", True),
        ("https://notpornhub.com/", False),
        ("https://pornhub.com.evil.io/", False),
        ("https://www.google.com/search?q=pornhub.com", False),
        ("not a url", False),
    ],
)
def test_is_blocked_site(url, expected):
    logger = backend.TrafficLogger(blocklist={"pornhub.com"})
    assert logger.is_blocked_site(url) is expected


def test_load_blocklist_merges_user_and_downloaded(data_dir):
    backend.BLOCKLIST_FILE.write_text("mine.com\n")
    backend.DOWNLOADED_BLOCKLIST_FILE.write_text("0.0.0.0 public.com\n")
    assert backend.load_blocklist() == {"mine.com", "public.com"}


# Dashboard


def auth_header(password, user=backend.DASHBOARD_USER):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_dashboard_requires_password(data_dir):
    client = backend.create_app("secret").test_client()
    assert client.get("/").status_code == 401
    assert client.get("/api/logs").status_code == 401
    assert client.get("/api/logs", headers=auth_header("wrong")).status_code == 401
    assert client.get("/api/logs", headers=auth_header("secret", "other")).status_code == 401


def test_dashboard_serves_ui_and_logs(data_dir):
    backend.append_log(backend.LOG_FILE, {"timestamp": "t", "url": "https://a.com/"})
    client = backend.create_app("secret").test_client()
    headers = auth_header("secret")
    assert b"URL Monitor" in client.get("/", headers=headers).data
    assert client.get("/script.js", headers=headers).status_code == 200
    assert client.get("/api/logs", headers=headers).json == [
        {"timestamp": "t", "url": "https://a.com/"}
    ]
    assert client.get("/../python_backend.py", headers=headers).status_code == 404


def test_load_config_generates_password_once(data_dir):
    first = backend.load_config()["dashboard_password"]
    assert len(first) >= 16
    assert backend.load_config()["dashboard_password"] == first


# Windows proxy settings, against an in-memory registry


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2

    def __init__(self, values):
        self.keys = {backend.INTERNET_SETTINGS_KEY: dict(values), backend.RUN_ONCE_KEY: {}}

    class _Key:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, path, reserved=0, access=0):
        return self._Key(self.keys[path])

    CreateKey = OpenKey

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
def registry(data_dir, monkeypatch):
    fake = FakeWinreg({"ProxyEnable": (1, 4), "ProxyServer": ("corp:3128", 1)})
    monkeypatch.setattr(backend, "winreg", fake, raising=False)
    monkeypatch.setattr(backend, "notify_proxy_change", lambda: None)
    return fake


def test_enable_then_restore_puts_back_user_settings(registry):
    settings = registry.keys[backend.INTERNET_SETTINGS_KEY]
    run_once = registry.keys[backend.RUN_ONCE_KEY]

    backend.enable_system_proxy()
    assert settings["ProxyServer"] == ("127.0.0.1:8081", 1)
    assert settings["ProxyOverride"][0] == backend.PROXY_BYPASS
    assert backend.RUN_ONCE_NAME in run_once
    assert json.loads(backend.PROXY_STATE_FILE.read_text())["ProxyServer"] == ["corp:3128", 1]

    assert backend.restore_system_proxy() is True
    assert settings == {"ProxyEnable": (1, 4), "ProxyServer": ("corp:3128", 1)}
    assert backend.RUN_ONCE_NAME not in run_once
    assert not backend.PROXY_STATE_FILE.exists()
    assert backend.restore_system_proxy() is False


def test_enable_twice_keeps_original_settings(registry):
    backend.enable_system_proxy()
    backend.enable_system_proxy()
    backend.restore_system_proxy()
    assert registry.keys[backend.INTERNET_SETTINGS_KEY]["ProxyServer"] == ("corp:3128", 1)


def test_turn_off_leftover_proxy(registry):
    settings = registry.keys[backend.INTERNET_SETTINGS_KEY]
    assert backend.turn_off_leftover_proxy() is False
    settings["ProxyServer"] = ("127.0.0.1:8081", 1)
    assert backend.turn_off_leftover_proxy() is True
    assert settings["ProxyEnable"] == (0, 4)
