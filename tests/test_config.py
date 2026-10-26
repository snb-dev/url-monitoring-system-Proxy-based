import json

import pytest

from urlmonitor.config import (
    ConfigError,
    Paths,
    Settings,
    ensure_config,
    load_settings,
    migrate_legacy_data,
)


@pytest.fixture
def paths(tmp_path):
    return Paths(tmp_path / "data")


def test_first_run_creates_config_with_defaults(paths):
    assert ensure_config(paths) is True
    assert ensure_config(paths) is False
    settings = load_settings(paths)
    assert len(settings.dashboard_password) >= 16
    defaults = Settings(dashboard_password=settings.dashboard_password)
    assert settings == defaults


def test_custom_settings(paths):
    paths.data_dir.mkdir()
    paths.config_file.write_text(
        '[dashboard]\npassword = "pw"\nport = 6000\n'
        '[monitoring]\nlog_mode = "all"\nretention_days = 0\nblock_watched_sites = true\n'
    )
    settings = load_settings(paths)
    assert settings == Settings(
        dashboard_password="pw",
        dashboard_port=6000,
        log_mode="all",
        retention_days=0,
        block_watched_sites=True,
    )


@pytest.mark.parametrize(
    "toml, message",
    [
        ('[dashboard]\npassword = ""', "password must not be empty"),
        ('[dashboard]\npassword = "x"\nport = "80"', "must be a whole number"),
        ('[dashboard]\npassword = "x"\nport = 0', "between 1 and 65535"),
        ('[dashboard]\npassword = "x"\nport = 8081', "must be different"),
        ('[dashboard]\npassword = "x"\n[monitoring]\nlog_mode = "some"', "log_mode"),
        ('[dashboard]\npassword = "x"\n[monitoring]\nblock_watched_sites = 1', "true or false"),
        ('[dashboard]\npassword = "x"\n[monitoring]\nretention_days = -1', "0 or more"),
        ("[dashboard\n", "not valid TOML"),
    ],
)
def test_invalid_settings(paths, toml, message):
    paths.data_dir.mkdir()
    paths.config_file.write_text(toml)
    with pytest.raises(ConfigError, match=message):
        load_settings(paths)


def test_migrates_legacy_folder_and_password(tmp_path, paths):
    legacy = tmp_path / "program" / "data"
    legacy.mkdir(parents=True)
    (legacy / "config.json").write_text(json.dumps({"dashboard_password": "old-pw"}))
    (legacy / "blocklist.txt").write_text("bad.com\n")

    assert migrate_legacy_data(paths, legacy) is True
    assert not legacy.exists()
    assert (paths.data_dir / "blocklist.txt").read_text() == "bad.com\n"
    ensure_config(paths)
    assert load_settings(paths).dashboard_password == "old-pw"
    assert not (paths.data_dir / "config.json").exists()
    # Never overwrites an existing data folder.
    legacy.mkdir()
    assert migrate_legacy_data(paths, legacy) is False
