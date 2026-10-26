"""The password-protected web dashboard."""

import hmac

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from .blocklist import read_blocklist
from .config import WEB_DIR
from .storage import MAX_PAGE_SIZE

DASHBOARD_USER = "admin"

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _int_arg(name, default=None):
    value = request.args.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        abort(400, f"{name} must be a number")


def create_app(storage, blocklist, password):
    """blocklist is the Blocklist used by the proxy; its first file is the user's list."""
    app = Flask(__name__, static_folder=None)
    expected = password.encode("utf-8")

    @app.before_request
    def require_login():
        auth = request.authorization
        supplied = (auth.password or "").encode("utf-8") if auth else b""
        if not (
            auth and auth.username == DASHBOARD_USER and hmac.compare_digest(supplied, expected)
        ):
            return Response(
                "Login required.",
                401,
                {"WWW-Authenticate": 'Basic realm="URL Monitor", charset="UTF-8"'},
            )

    @app.after_request
    def add_security_headers(response):
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.route("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/<path:filename>")
    def web_file(filename):
        return send_from_directory(WEB_DIR, filename)

    @app.route("/api/visits")
    def visits():
        limit = max(1, min(_int_arg("limit", 100), MAX_PAGE_SIZE))
        rows = storage.visits(
            flagged_only=request.args.get("flagged") == "1",
            search=request.args.get("q", "").strip(),
            before_id=_int_arg("before_id"),
            after_id=_int_arg("after_id"),
            limit=limit,
        )
        return jsonify({"visits": rows, "has_more": len(rows) == limit})

    @app.route("/api/summary")
    def summary():
        result = storage.summary(since_ms=_int_arg("since", 0))
        result["watched_domains"] = len(blocklist)
        return jsonify(result)

    @app.route("/api/blocklist")
    def get_blocklist():
        return jsonify(sorted(read_blocklist(blocklist.files[0])))

    return app
