import base64

import pytest

from urlmonitor.blocklist import Blocklist
from urlmonitor.dashboard import DASHBOARD_USER, create_app
from urlmonitor.storage import Storage


def auth(password="secret", user=DASHBOARD_USER):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def setup(tmp_path):
    watch = tmp_path / "blocklist.txt"
    watch.write_text("# mine\nbad.com\n")
    downloaded = tmp_path / "downloaded.txt"
    downloaded.write_text("0.0.0.0 public.com\n")
    storage = Storage(tmp_path / "history.db")
    client = create_app(storage, Blocklist([watch, downloaded]), "secret").test_client()
    return client, storage


def test_requires_password(setup):
    client, _ = setup
    for path in ("/", "/app.js", "/api/visits", "/api/summary"):
        assert client.get(path).status_code == 401
    assert client.get("/api/visits", headers=auth("wrong")).status_code == 401
    assert client.get("/api/visits", headers=auth(user="other")).status_code == 401


def test_serves_ui_with_security_headers(setup):
    client, _ = setup
    response = client.get("/", headers=auth())
    assert response.status_code == 200
    assert b"URL Monitor" in response.data
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/app.js", headers=auth()).status_code == 200
    assert client.get("/../config.py", headers=auth()).status_code == 404


def test_visits_api(setup):
    client, storage = setup
    for i in range(3):
        storage.add_visit(f"https://a.com/{i}", "a.com")
    storage.add_visit("https://bad.com/", "bad.com", flagged=True)

    data = client.get("/api/visits?limit=2", headers=auth()).json
    assert [v["url"] for v in data["visits"]] == ["https://bad.com/", "https://a.com/2"]
    assert data["has_more"] is True

    flagged = client.get("/api/visits?flagged=1", headers=auth()).json
    assert [v["host"] for v in flagged["visits"]] == ["bad.com"]
    assert flagged["has_more"] is False

    search = client.get("/api/visits?q=a.com/1", headers=auth()).json
    assert [v["url"] for v in search["visits"]] == ["https://a.com/1"]

    assert client.get("/api/visits?before_id=abc", headers=auth()).status_code == 400


def test_summary_and_blocklist_api(setup):
    client, storage = setup
    storage.add_visit("https://bad.com/", "bad.com", flagged=True)
    summary = client.get("/api/summary?since=0", headers=auth()).json
    assert summary["visits"] == 1
    assert summary["watched_domains"] == 2
    # Only the user's own list, not the downloaded one.
    assert client.get("/api/blocklist", headers=auth()).json == ["bad.com"]
