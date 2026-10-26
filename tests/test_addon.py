import pytest
from mitmproxy import http
from mitmproxy.test import tflow

from urlmonitor.addon import Monitor, request_kind, should_record
from urlmonitor.blocklist import Blocklist
from urlmonitor.config import Settings
from urlmonitor.storage import Storage

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"
PAGE = {"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}
IMAGE = {"Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors"}
FRAME = {"Sec-Fetch-Dest": "iframe", "Sec-Fetch-Mode": "navigate"}


@pytest.mark.parametrize(
    "method, headers, expected",
    [
        ("GET", {"User-Agent": CHROME, **PAGE}, "page"),
        ("GET", {"User-Agent": CHROME, **IMAGE}, "other"),
        ("GET", {"User-Agent": CHROME, **FRAME}, "frame"),
        ("POST", {"User-Agent": CHROME, **PAGE}, None),
        ("GET", {"User-Agent": "Windows-Update-Agent", **PAGE}, None),
        # Older browsers without Fetch Metadata headers
        ("GET", {"User-Agent": CHROME, "Accept": "text/html,*/*"}, "page"),
        ("GET", {"User-Agent": CHROME, "Accept": "image/png"}, "other"),
    ],
)
def test_request_kind(method, headers, expected):
    assert request_kind(method, headers) == expected


def test_should_record():
    assert should_record("page", False, "pages")
    assert not should_record("other", True, "pages")
    assert not should_record("frame", False, "pages")
    assert should_record("frame", True, "pages")
    assert should_record("other", False, "all")
    assert not should_record(None, True, "all")


def make_flow(url, headers):
    request = http.Request.make("GET", url, headers={"User-Agent": CHROME, **headers})
    return tflow.tflow(req=request)


@pytest.fixture
def make_monitor(tmp_path):
    def make(**settings):
        watch = tmp_path / "blocklist.txt"
        watch.write_text("bad.com\n")
        storage = Storage(tmp_path / "history.db")
        monitor = Monitor(storage, Blocklist([watch]), Settings(dashboard_password="x", **settings))
        return monitor, storage

    return make


def test_records_pages_and_flags_watched(make_monitor):
    monitor, storage = make_monitor()
    monitor.request(make_flow("https://www.bad.com/video", PAGE))
    monitor.request(make_flow("https://news.com/", PAGE))
    monitor.request(make_flow("https://news.com/logo.png", IMAGE))

    visits = storage.visits()
    assert [(v["host"], v["flagged"], v["blocked"]) for v in visits] == [
        ("news.com", False, False),
        ("www.bad.com", True, False),
    ]


def test_all_mode_records_resources(make_monitor):
    monitor, storage = make_monitor(log_mode="all")
    monitor.request(make_flow("https://news.com/logo.png", IMAGE))
    assert storage.count() == 1


def test_blocking(make_monitor):
    monitor, storage = make_monitor(block_watched_sites=True)
    page = make_flow("https://bad.com/", PAGE)
    image = make_flow("https://cdn.bad.com/x.jpg", IMAGE)
    allowed = make_flow("https://news.com/", PAGE)
    for flow in (page, image, allowed):
        monitor.request(flow)

    assert page.response.status_code == 403
    assert b"bad.com" in page.response.content
    assert image.response.status_code == 403
    assert allowed.response is None
    assert [(v["host"], v["blocked"]) for v in storage.visits()] == [
        ("news.com", False),
        ("bad.com", True),
    ]


def test_block_page_escapes_host(make_monitor, tmp_path):
    monitor, _ = make_monitor(block_watched_sites=True)
    flow = make_flow("https://bad.com/", PAGE)
    flow.request.headers["Host"] = "<script>.bad.com"
    monitor.request(flow)
    assert b"<script>" not in flow.response.content


def test_retention_cleanup(make_monitor):
    monitor, storage = make_monitor(retention_days=1)
    storage.add_visit("https://ancient.com/", "ancient.com", time_ms=1_000)
    monitor.request(make_flow("https://news.com/", PAGE))
    assert [v["host"] for v in storage.visits()] == ["news.com"]
