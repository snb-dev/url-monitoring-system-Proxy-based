"""Where URL Monitor keeps its files, and the settings in config.toml."""

import json
import os
import secrets
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
# Version 0.1 kept its data in a "data" folder next to the program.
LEGACY_DATA_DIR = PACKAGE_DIR.parent / "data"

LOG_MODES = ("pages", "all")

CONFIG_TEMPLATE = """\
# URL Monitor settings. Restart URL Monitor after changing this file.

[dashboard]
# Open http://127.0.0.1:<port> and log in as "admin" with this password.
password = "{password}"
port = 5000

[proxy]
port = 8081

[monitoring]
# "pages" records the pages that are opened. "all" also records every image,
# script and tracker those pages load, which is much noisier.
log_mode = "pages"
# Delete history older than this many days. 0 keeps everything.
retention_days = 90
# false: only flag visits to watched sites. true: also block them.
block_watched_sites = false
"""


class ConfigError(Exception):
    pass


def default_data_dir():
    if override := os.environ.get("URLMON_DATA_DIR"):
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "URLMonitor"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "URLMonitor"
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "urlmonitor"


@dataclass(frozen=True)
class Paths:
    data_dir: Path

    @property
    def config_file(self):
        return self.data_dir / "config.toml"

    @property
    def database(self):
        return self.data_dir / "history.db"

    @property
    def blocklist(self):
        return self.data_dir / "blocklist.txt"

    @property
    def downloaded_blocklist(self):
        return self.data_dir / "blocklist_downloaded.txt"

    @property
    def proxy_state(self):
        return self.data_dir / "proxy_state.json"

    @property
    def cert_dir(self):
        return self.data_dir / "certs"


@dataclass(frozen=True)
class Settings:
    dashboard_password: str
    dashboard_port: int = 5000
    proxy_port: int = 8081
    log_mode: str = "pages"
    retention_days: int = 90
    block_watched_sites: bool = False


def migrate_legacy_data(paths, legacy_dir=LEGACY_DATA_DIR):
    """Move a version 0.1 data folder to the new location. Returns True if moved."""
    if paths.data_dir.exists() or not legacy_dir.is_dir():
        return False
    paths.data_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy_dir), str(paths.data_dir))
    return True


def _new_password(paths):
    legacy_config = paths.data_dir / "config.json"
    if legacy_config.exists():
        try:
            password = json.loads(legacy_config.read_text(encoding="utf-8"))
            password = password["dashboard_password"]
            legacy_config.unlink()
            return password
        except (ValueError, KeyError):
            pass
    return secrets.token_urlsafe(12)


def ensure_config(paths):
    """Create config.toml with a random dashboard password if it doesn't exist.

    Returns True if the file was created.
    """
    if paths.config_file.exists():
        return False
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    text = CONFIG_TEMPLATE.format(password=_new_password(paths))
    paths.config_file.write_text(text, encoding="utf-8")
    return True


TYPE_NAMES = {str: "text in quotes", int: "a whole number", bool: "true or false"}


def _get(table, key, expected_type, default, section):
    value = table.get(key, default)
    # bool is a subclass of int, so compare types exactly.
    if type(value) is not expected_type:
        raise ConfigError(
            f"[{section}] {key} must be {TYPE_NAMES[expected_type]}, not {value!r}"
        )
    return value


def load_settings(paths):
    try:
        with open(paths.config_file, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{paths.config_file} is not valid TOML: {e}") from e

    dashboard = data.get("dashboard", {})
    proxy = data.get("proxy", {})
    monitoring = data.get("monitoring", {})
    defaults = Settings(dashboard_password="")
    settings = Settings(
        dashboard_password=_get(dashboard, "password", str, "", "dashboard"),
        dashboard_port=_get(dashboard, "port", int, defaults.dashboard_port, "dashboard"),
        proxy_port=_get(proxy, "port", int, defaults.proxy_port, "proxy"),
        log_mode=_get(monitoring, "log_mode", str, defaults.log_mode, "monitoring"),
        retention_days=_get(
            monitoring, "retention_days", int, defaults.retention_days, "monitoring"
        ),
        block_watched_sites=_get(
            monitoring, "block_watched_sites", bool, defaults.block_watched_sites, "monitoring"
        ),
    )

    if not settings.dashboard_password:
        raise ConfigError("[dashboard] password must not be empty")
    for name in ("dashboard_port", "proxy_port"):
        if not 1 <= getattr(settings, name) <= 65535:
            raise ConfigError(f"{name.replace('_', ' ')} must be between 1 and 65535")
    if settings.dashboard_port == settings.proxy_port:
        raise ConfigError("The dashboard and proxy ports must be different")
    if settings.log_mode not in LOG_MODES:
        raise ConfigError(f"[monitoring] log_mode must be one of {', '.join(LOG_MODES)}")
    if settings.retention_days < 0:
        raise ConfigError("[monitoring] retention_days must be 0 or more")
    return settings
