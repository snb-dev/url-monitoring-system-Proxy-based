"""End-to-end check of a URL Monitor build.

Starts URL Monitor in manual mode with a temporary data folder, sends page
visits through the proxy, and checks that the dashboard reports them.

    python packaging/smoke_test.py python -m urlmonitor
    python packaging/smoke_test.py dist/URLMonitor/URLMonitor.exe

Needs internet access for the HTTPS check; pass --http-only to skip it.
"""

import base64
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

PROXY = "http://127.0.0.1:8081"
DASHBOARD = "http://127.0.0.1:5000"
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
}


def wait_for_port(port, process, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"URL Monitor exited early with code {process.returncode}")
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError(f"Nothing listening on port {port} after {timeout}s")


def visit(url, ca_file):
    context = ssl.create_default_context(cafile=str(ca_file))
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
        urllib.request.HTTPSHandler(context=context),
    )
    try:
        with opener.open(urllib.request.Request(url, headers=BROWSER_HEADERS), timeout=30):
            pass
    except urllib.error.HTTPError:
        pass  # The visit is recorded whatever the website answers.


def dashboard_get(path, password):
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    request = urllib.request.Request(
        f"{DASHBOARD}{path}", headers={"Authorization": f"Basic {token}"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        return response.read()


def main():
    args = sys.argv[1:]
    http_only = "--http-only" in args
    command = [arg for arg in args if arg != "--http-only"]
    if not command:
        sys.exit(__doc__)

    data_dir = Path(tempfile.mkdtemp(prefix="urlmonitor-smoke-"))
    (data_dir / "blocklist.txt").write_text("example.com\n")
    env = {**os.environ, "URLMON_DATA_DIR": str(data_dir), "PYTHONUNBUFFERED": "1"}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(name, None)

    log_file = data_dir / "output.log"
    with open(log_file, "w") as log:
        process = subprocess.Popen(
            [*command, "start", "--manual"], env=env, stdout=log, stderr=subprocess.STDOUT
        )
    try:
        wait_for_port(8081, process)
        wait_for_port(5000, process)
        ca_file = data_dir / "certs" / "mitmproxy-ca-cert.pem"
        urls = ["http://example.com/smoke-http"]
        if not http_only:
            urls.append("https://example.com/smoke-https")
        for url in urls:
            visit(url, ca_file)

        password = tomllib.loads((data_dir / "config.toml").read_text())["dashboard"]["password"]
        assert b"URL Monitor" in dashboard_get("/", password), "dashboard page missing"
        visits = json.loads(dashboard_get("/api/visits", password))["visits"]
        recorded = {v["url"]: v for v in visits}
        for url in urls:
            assert url in recorded, f"{url} was not recorded: {sorted(recorded)}"
            assert recorded[url]["flagged"], f"{url} was not flagged"
        print(f"OK: {len(urls)} visits recorded and flagged.")
    except Exception:
        print(log_file.read_text())
        raise
    finally:
        process.terminate()
        process.wait(timeout=30)


if __name__ == "__main__":
    main()
