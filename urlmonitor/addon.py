"""The mitmproxy addon that records visits and flags or blocks watched sites."""

import html
import logging
import sqlite3
import time

from mitmproxy import http

from .storage import now_ms

log = logging.getLogger(__name__)

BROWSER_SIGNATURES = ("Mozilla", "Chrome", "Safari", "Firefox", "Edg")
DAY_MS = 24 * 60 * 60 * 1000
CLEANUP_INTERVAL = 60 * 60  # seconds

BLOCK_PAGE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site blocked</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; min-height: 100vh;
         display: grid; place-items: center; background: #f6f7f9; color: #1f2933; }}
  main {{ max-width: 32rem; padding: 2rem; text-align: center; }}
  h1 {{ font-size: 1.5rem; }}
  p {{ color: #52606d; line-height: 1.5; }}
</style>
</head>
<body>
<main>
  <h1>This site is blocked</h1>
  <p><strong>{host}</strong> is on this computer's URL Monitor watch list.</p>
</main>
</body>
</html>
"""


def request_kind(method, headers):
    """Classify a request as "page", "frame", "other", or None if not from a browser."""
    if method != "GET":
        return None
    user_agent = headers.get("User-Agent", "")
    if not any(signature in user_agent for signature in BROWSER_SIGNATURES):
        return None
    dest = headers.get("Sec-Fetch-Dest")
    if dest is not None:
        if dest == "document" and headers.get("Sec-Fetch-Mode") == "navigate":
            return "page"
        if dest in ("iframe", "frame"):
            return "frame"
        return "other"
    # Browsers too old to send Fetch Metadata headers: treat HTML requests as pages.
    return "page" if "text/html" in headers.get("Accept", "") else "other"


def should_record(kind, watched, log_mode):
    if kind is None:
        return False
    if log_mode == "all":
        return True
    # Pages, plus frames from watched sites (e.g. embedded videos).
    return kind == "page" or (kind == "frame" and watched)


def block_response(host):
    return http.Response.make(
        403,
        BLOCK_PAGE.format(host=html.escape(host)),
        {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"},
    )


class Monitor:
    def __init__(self, storage, blocklist, settings):
        self.storage = storage
        self.blocklist = blocklist
        self.settings = settings
        self._next_cleanup = 0.0

    def request(self, flow):
        request = flow.request
        host = request.pretty_host
        watched = self.blocklist.matches(host)
        blocked = watched and self.settings.block_watched_sites
        if blocked:
            flow.response = block_response(host)

        kind = request_kind(request.method, request.headers)
        if should_record(kind, watched, self.settings.log_mode):
            try:
                self.storage.add_visit(request.pretty_url, host, watched, blocked)
            except sqlite3.Error as e:
                log.error("Could not record visit: %s", e)
        self._cleanup()

    def _cleanup(self):
        if not self.settings.retention_days:
            return
        now = time.monotonic()
        if now < self._next_cleanup:
            return
        self._next_cleanup = now + CLEANUP_INTERVAL
        cutoff = now_ms() - self.settings.retention_days * DAY_MS
        try:
            deleted = self.storage.delete_older_than(cutoff)
        except sqlite3.Error as e:
            log.error("Could not delete old history: %s", e)
            return
        if deleted:
            log.info("Deleted %d visits older than %d days.", deleted, self.settings.retention_days)


class ProxyStarted:
    """Runs a callback once the proxy is listening."""

    def __init__(self, callback):
        self.callback = callback

    def running(self):
        self.callback()
