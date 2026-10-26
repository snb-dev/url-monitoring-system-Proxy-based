"""Browsing history, stored in SQLite."""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlsplit

SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY,
    time INTEGER NOT NULL,  -- Unix time in milliseconds
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    flagged INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS visits_time ON visits (time);
CREATE INDEX IF NOT EXISTS visits_flagged ON visits (flagged, id);
"""

MAX_PAGE_SIZE = 500


def now_ms():
    return int(time.time() * 1000)


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Storage:
    def __init__(self, path):
        self.path = path
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        # A connection per call keeps this safe to use from the proxy thread and
        # the dashboard's request threads at the same time.
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=NORMAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_visit(self, url, host, flagged=False, blocked=False, time_ms=None):
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO visits (time, url, host, flagged, blocked) VALUES (?, ?, ?, ?, ?)",
                (time_ms or now_ms(), url, host, int(flagged), int(blocked)),
            )
            return cursor.lastrowid

    def visits(self, *, flagged_only=False, search="", before_id=None, after_id=None, limit=100):
        """Newest visits first. Use before_id to page back, after_id to fetch new ones."""
        where, params = [], []
        if flagged_only:
            where.append("flagged = 1")
        if search:
            where.append("url LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(search)}%")
        if before_id is not None:
            where.append("id < ?")
            params.append(before_id)
        if after_id is not None:
            where.append("id > ?")
            params.append(after_id)
        sql = "SELECT id, time, url, host, flagged, blocked FROM visits"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, MAX_PAGE_SIZE)))
        with self._connect() as db:
            return [
                {**row, "flagged": bool(row["flagged"]), "blocked": bool(row["blocked"])}
                for row in map(dict, db.execute(sql, params))
            ]

    def summary(self, since_ms):
        with self._connect() as db:
            visits, flagged = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(flagged), 0) FROM visits WHERE time >= ?",
                (since_ms,),
            ).fetchone()
            latest_flagged_id = db.execute(
                "SELECT MAX(id) FROM visits WHERE flagged = 1"
            ).fetchone()[0]
            top_flagged = db.execute(
                "SELECT host, COUNT(*) AS count FROM visits WHERE flagged = 1 AND time >= ?"
                " GROUP BY host ORDER BY count DESC, host LIMIT 5",
                (since_ms,),
            ).fetchall()
        return {
            "visits": visits,
            "flagged": flagged,
            "latest_flagged_id": latest_flagged_id,
            "top_flagged_hosts": [dict(row) for row in top_flagged],
        }

    def count(self):
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM visits").fetchone()[0]

    def delete_older_than(self, time_ms):
        with self._connect() as db:
            return db.execute("DELETE FROM visits WHERE time < ?", (time_ms,)).rowcount

    def import_json_log(self, path, is_flagged):
        """Import a version 0.1 JSON log ([{"timestamp", "url"}, ...]). Returns the count."""
        entries = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for entry in entries:
            url = entry["url"]
            when = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
            host = urlsplit(url).hostname or ""
            rows.append((int(when.timestamp() * 1000), url, host, int(is_flagged(host))))
        rows.sort()
        with self._connect() as db:
            db.executemany(
                "INSERT INTO visits (time, url, host, flagged) VALUES (?, ?, ?, ?)", rows
            )
        return len(rows)
