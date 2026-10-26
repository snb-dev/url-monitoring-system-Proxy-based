import json

import pytest

from urlmonitor import cli
from urlmonitor.blocklist import Blocklist
from urlmonitor.config import Paths
from urlmonitor.storage import Storage


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("URLMON_DATA_DIR", str(tmp_path / "data"))
    return Paths(tmp_path / "data")


def test_prepare_first_run(paths):
    settings, created = cli.prepare(paths)
    assert created
    assert paths.config_file.exists()
    assert paths.blocklist.read_text().startswith("# Domains to flag")
    assert cli.prepare(paths)[1] is False


def test_import_legacy_logs(paths):
    cli.prepare(paths)
    (paths.data_dir / "traffic_log.json").write_text(
        json.dumps([{"timestamp": "2024-12-15 16:39:59", "url": "https://www.bad.com/x"}])
    )
    (paths.data_dir / "filtered_traffic_log.json").write_text("[]")
    paths.blocklist.write_text("bad.com\n")
    storage = Storage(paths.database)

    cli.import_legacy_logs(paths, storage, Blocklist([paths.blocklist]))
    assert [(v["host"], v["flagged"]) for v in storage.visits()] == [("www.bad.com", True)]
    assert (paths.data_dir / "traffic_log.json.imported").exists()
    assert (paths.data_dir / "filtered_traffic_log.json.imported").exists()
    # A second start doesn't import again.
    cli.import_legacy_logs(paths, storage, Blocklist([paths.blocklist]))
    assert storage.count() == 1


def test_status(paths, capsys):
    assert cli.main(["status"]) == 0
    assert "Not set up yet" in capsys.readouterr().out
    cli.prepare(paths)
    Storage(paths.database).add_visit("https://a.com/", "a.com")
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Running:         no" in out
    assert "Visits stored:   1" in out


def test_update_blocklist(paths, tmp_path, capsys):
    source = tmp_path / "hosts"
    source.write_text("0.0.0.0 a.com\n")
    assert cli.main(["update-blocklist", "--url", source.as_uri()]) == 0
    assert "Saved 1 domains" in capsys.readouterr().out
    assert paths.downloaded_blocklist.exists()


def test_config_error_is_reported(paths, capsys):
    paths.data_dir.mkdir(parents=True)
    paths.config_file.write_text('[dashboard]\npassword = ""\n')
    assert cli.main(["start"]) == 1
    assert "password must not be empty" in capsys.readouterr().out
