import json
from datetime import datetime

import pytest

from urlmonitor.storage import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "history.db")


def test_visits_newest_first_with_paging(storage):
    ids = [storage.add_visit(f"https://site{i}.com/", f"site{i}.com") for i in range(5)]
    page = storage.visits(limit=2)
    assert [v["id"] for v in page] == [ids[4], ids[3]]
    older = storage.visits(before_id=page[-1]["id"], limit=2)
    assert [v["id"] for v in older] == [ids[2], ids[1]]
    newer = storage.visits(after_id=ids[2])
    assert [v["id"] for v in newer] == [ids[4], ids[3]]


def test_flagged_filter_and_search(storage):
    storage.add_visit("https://a.com/cats", "a.com")
    storage.add_visit("https://bad.com/x", "bad.com", flagged=True, blocked=True)
    storage.add_visit("https://a.com/100%_dogs", "a.com")

    flagged = storage.visits(flagged_only=True)
    assert [(v["host"], v["flagged"], v["blocked"]) for v in flagged] == [("bad.com", True, True)]
    assert [v["url"] for v in storage.visits(search="CATS")] == ["https://a.com/cats"]
    # % and _ are matched literally, not as wildcards.
    assert [v["url"] for v in storage.visits(search="%_")] == ["https://a.com/100%_dogs"]


def test_summary(storage):
    storage.add_visit("https://old.com/", "old.com", flagged=True, time_ms=1_000)
    storage.add_visit("https://a.com/", "a.com", time_ms=5_000)
    latest = storage.add_visit("https://bad.com/", "bad.com", flagged=True, time_ms=6_000)
    storage.add_visit("https://bad.com/2", "bad.com", flagged=True, time_ms=4_000)

    summary = storage.summary(since_ms=2_000)
    assert summary["visits"] == 3
    assert summary["flagged"] == 2
    assert summary["latest_flagged_id"] == latest + 1
    assert summary["top_flagged_hosts"] == [{"host": "bad.com", "count": 2}]


def test_summary_when_empty(storage):
    summary = storage.summary(since_ms=0)
    assert summary == {
        "visits": 0,
        "flagged": 0,
        "latest_flagged_id": None,
        "top_flagged_hosts": [],
    }


def test_delete_older_than(storage):
    storage.add_visit("https://old.com/", "old.com", time_ms=1_000)
    storage.add_visit("https://new.com/", "new.com", time_ms=9_000)
    assert storage.delete_older_than(5_000) == 1
    assert [v["host"] for v in storage.visits()] == ["new.com"]


def test_import_json_log(storage, tmp_path):
    log = tmp_path / "traffic_log.json"
    log.write_text(
        json.dumps(
            [
                {"timestamp": "2024-12-15 16:39:59", "url": "https://bad.com/x"},
                {"timestamp": "2024-12-15 13:43:48", "url": "https://ok.com/"},
            ]
        )
    )
    assert storage.import_json_log(log, lambda host: host == "bad.com") == 2
    visits = storage.visits()
    # Imported in time order, so ids follow time.
    assert [v["host"] for v in visits] == ["bad.com", "ok.com"]
    assert visits[0]["flagged"] and not visits[1]["flagged"]
    expected = datetime(2024, 12, 15, 16, 39, 59).timestamp() * 1000
    assert visits[0]["time"] == expected
