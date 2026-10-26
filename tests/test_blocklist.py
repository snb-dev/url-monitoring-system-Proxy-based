import os

import pytest

from urlmonitor.blocklist import (
    Blocklist,
    domain_matches,
    download_blocklist,
    parse_blocklist,
)


def test_parse_blocklist_formats():
    domains = parse_blocklist(
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
    "host, expected",
    [
        ("pornhub.com", True),
        ("www.pornhub.com", True),
        ("de.pornhub.com", True),
        ("PORNHUB.COM.", True),
        ("notpornhub.com", False),
        ("pornhub.com.evil.io", False),
        ("google.com", False),
        ("", False),
    ],
)
def test_domain_matches(host, expected):
    assert domain_matches(host, {"pornhub.com"}) is expected


def test_blocklist_merges_files_and_reloads_on_change(tmp_path):
    mine = tmp_path / "blocklist.txt"
    downloaded = tmp_path / "downloaded.txt"
    mine.write_text("mine.com\n")
    blocklist = Blocklist([mine, downloaded], check_interval=0)
    assert blocklist.domains == {"mine.com"}

    downloaded.write_text("0.0.0.0 public.com\n")
    assert blocklist.matches("www.public.com")
    assert len(blocklist) == 2

    mine.write_text("")
    os.utime(mine, ns=(0, 0))  # make sure the change is visible on coarse clocks
    assert not blocklist.matches("mine.com")


def test_download_blocklist(tmp_path):
    source = tmp_path / "hosts"
    source.write_text("# list\n0.0.0.0 a.com\n0.0.0.0 b.com\n")
    destination = tmp_path / "downloaded.txt"
    assert download_blocklist(source.as_uri(), destination) == 2
    assert "a.com" in destination.read_text()


def test_download_blocklist_keeps_old_list_when_empty(tmp_path):
    source = tmp_path / "empty"
    source.write_text("# nothing here\n")
    destination = tmp_path / "downloaded.txt"
    destination.write_text("old.com\n")
    with pytest.raises(ValueError):
        download_blocklist(source.as_uri(), destination)
    assert destination.read_text() == "old.com\n"
