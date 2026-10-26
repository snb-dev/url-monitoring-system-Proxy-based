"""URL Monitor: a local proxy that records the websites visited on this computer
and flags visits to domains on a watch list.

Run `python python_backend.py --help` to see the available commands.
"""

import argparse
import asyncio
import atexit
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.serving import make_server

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import ctypes
    import winreg

# Paths
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = Path(os.environ.get("URLMON_DATA_DIR", BASE_DIR / "data"))
LOG_FILE = DATA_DIR / "traffic_log.json"
FILTERED_LOG_FILE = DATA_DIR / "filtered_traffic_log.json"
BLOCKLIST_FILE = DATA_DIR / "blocklist.txt"
DOWNLOADED_BLOCKLIST_FILE = DATA_DIR / "blocklist_downloaded.txt"
CONFIG_FILE = DATA_DIR / "config.json"
PROXY_STATE_FILE = DATA_DIR / "proxy_state.json"
CERT_DIR = DATA_DIR / "certs"
CA_CERT_FILE = CERT_DIR / "mitmproxy-ca-cert.pem"

# Network
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8081
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 5000
DASHBOARD_USER = "admin"

CA_NAME = "URL Monitor Local CA"
DEFAULT_BLOCKLIST_URL = (
    "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts"
)

BLOCKLIST_HEADER = """\
# Domains to flag, one per line. A domain also matches its subdomains,
# so "example.com" flags "www.example.com" and "m.example.com".
# Lines starting with # are ignored. Hosts-file lines ("0.0.0.0 example.com") work too.
# Restart URL Monitor after editing this file.
"""

# Windows proxy settings (per user, so no administrator rights are needed)
INTERNET_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
RUN_ONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
RUN_ONCE_NAME = "URLMonitorRestoreProxy"
PROXY_VALUE_NAMES = ("ProxyEnable", "ProxyServer", "ProxyOverride")
PROXY_BYPASS = "localhost;127.*;<local>"
REG_SZ = 1
REG_DWORD = 4
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------


def write_json(path, data):
    """Write JSON atomically so a crash never leaves a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def ensure_data_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (LOG_FILE, FILTERED_LOG_FILE):
        if not path.exists():
            path.write_text("[]", encoding="utf-8")
    if not BLOCKLIST_FILE.exists():
        BLOCKLIST_FILE.write_text(BLOCKLIST_HEADER, encoding="utf-8")


def load_config():
    """Load the config, creating it with a random dashboard password on first run."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    config = {"dashboard_password": secrets.token_urlsafe(12)}
    write_json(CONFIG_FILE, config)
    return config


def append_log(path, entry):
    with open(path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data.append(entry)
        f.seek(0)
        json.dump(data, f, indent=4)
        f.truncate()


# ---------------------------------------------------------------------------
# Blocklist matching
# ---------------------------------------------------------------------------

HOSTS_FILE_ADDRESSES = {"0.0.0.0", "127.0.0.1", "::", "::1"}
IGNORED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "local",
    "broadcasthost",
    "ip6-localhost",
    "ip6-loopback",
    "0.0.0.0",
}


def normalize_domain(domain):
    domain = domain.strip().lower().rstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def parse_blocklist(lines):
    """Parse plain domain lists, hosts files and pasted URLs into a set of domains."""
    domains = set()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) > 1 and parts[0] in HOSTS_FILE_ADDRESSES:
            parts = parts[1:]
        for part in parts:
            if "://" in part:
                part = urlsplit(part).hostname or ""
            domain = normalize_domain(part)
            if domain and domain not in IGNORED_HOSTS:
                domains.add(domain)
    return domains


def load_blocklist():
    domains = set()
    for path in (BLOCKLIST_FILE, DOWNLOADED_BLOCKLIST_FILE):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                domains |= parse_blocklist(f)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"Error loading blocklist {path}: {e}")
    return domains


def domain_matches(host, domains):
    """True if host, or any domain it is a subdomain of, is in domains."""
    labels = normalize_domain(host).split(".")
    return any(".".join(labels[i:]) in domains for i in range(len(labels)))


class TrafficLogger:
    """mitmproxy addon that logs browser requests and flags watched domains."""

    def __init__(self, blocklist=None):
        self.blocklist = load_blocklist() if blocklist is None else blocklist

    def is_personal_request(self, user_agent: str, url: str, method: str) -> bool:
        """
        Determine if the request comes from a user-initiated action based on User-Agent, URL patterns, and method.
        """
        browser_signatures = ["Mozilla", "Chrome", "Safari", "Firefox", "Edg"]
        allowed_methods = ["GET"]

        is_browser = any(signature in user_agent for signature in browser_signatures)
        is_allowed_method = method in allowed_methods

        return is_browser and is_allowed_method

    def is_blocked_site(self, url: str) -> bool:
        """Check if the URL's host is on the blocklist."""
        return domain_matches(urlsplit(url).hostname or "", self.blocklist)

    def request(self, flow):
        """Log each HTTP request."""
        try:
            url = flow.request.url
            user_agent = flow.request.headers.get("User-Agent", "")
            method = flow.request.method

            if self.is_personal_request(user_agent, url, method):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entry = {"timestamp": timestamp, "url": url}
                append_log(LOG_FILE, entry)
                if self.is_blocked_site(url):
                    append_log(FILTERED_LOG_FILE, entry)
        except Exception as e:
            print(f"Error logging request: {e}")


class ProxyStarted:
    """mitmproxy addon that points Windows at the proxy once it is listening."""

    def running(self):
        if IS_WINDOWS:
            enable_system_proxy()
        print(f"Monitoring started. Proxy: {PROXY_HOST}:{PROXY_PORT}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def read_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def create_app(password):
    app = Flask(__name__, static_folder=None)
    expected = password.encode("utf-8")

    @app.before_request
    def require_login():
        auth = request.authorization
        supplied = (auth.password or "").encode("utf-8") if auth else b""
        if not (
            auth
            and auth.username == DASHBOARD_USER
            and hmac.compare_digest(supplied, expected)
        ):
            return Response(
                "Login required.",
                401,
                {"WWW-Authenticate": 'Basic realm="URL Monitor", charset="UTF-8"'},
            )

    @app.route("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/<path:filename>")
    def web_file(filename):
        return send_from_directory(WEB_DIR, filename)

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        try:
            return jsonify(read_json_file(LOG_FILE)), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/filtered_logs", methods=["GET"])
    def get_filtered_logs():
        try:
            return jsonify(read_json_file(FILTERED_LOG_FILE)), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/blocklist", methods=["GET"])
    def get_blocklist():
        try:
            with open(BLOCKLIST_FILE, encoding="utf-8") as f:
                return jsonify(sorted(parse_blocklist(f))), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


# ---------------------------------------------------------------------------
# Windows system proxy
# ---------------------------------------------------------------------------

_proxy_lock = threading.Lock()


def read_proxy_settings():
    settings = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY) as key:
        for name in PROXY_VALUE_NAMES:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
                settings[name] = [value, value_type]
            except FileNotFoundError:
                settings[name] = None
    return settings


def write_proxy_settings(settings):
    """Write proxy registry values; a value of None deletes that registry value."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        for name, stored in settings.items():
            if stored is None:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            else:
                value, value_type = stored
                winreg.SetValueEx(key, name, 0, value_type, value)
    notify_proxy_change()


def notify_proxy_change():
    """Tell running browsers to re-read the proxy settings now."""
    internet_set_option = ctypes.windll.wininet.InternetSetOptionW
    internet_set_option(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    internet_set_option(None, INTERNET_OPTION_REFRESH, None, 0)


def restore_command():
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    return f'"{python}" "{Path(__file__).resolve()}" restore'


def set_restore_on_next_login(enabled):
    """Register a one-time restore at next login, in case this process is killed
    or the computer shuts down before it can undo the proxy settings itself."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_ONCE_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_ONCE_NAME, 0, REG_SZ, restore_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_ONCE_NAME)
            except FileNotFoundError:
                pass


def enable_system_proxy():
    with _proxy_lock:
        if not PROXY_STATE_FILE.exists():
            # Save the user's own settings first, so they can always be put back.
            write_json(PROXY_STATE_FILE, read_proxy_settings())
        set_restore_on_next_login(True)
        write_proxy_settings(
            {
                "ProxyEnable": [1, REG_DWORD],
                "ProxyServer": [f"{PROXY_HOST}:{PROXY_PORT}", REG_SZ],
                "ProxyOverride": [PROXY_BYPASS, REG_SZ],
            }
        )


def restore_system_proxy():
    """Put back the proxy settings saved by enable_system_proxy.

    Safe to call more than once; returns True if anything was restored.
    """
    with _proxy_lock:
        if not PROXY_STATE_FILE.exists():
            return False
        try:
            previous = json.loads(PROXY_STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            previous = {"ProxyEnable": [0, REG_DWORD]}
        write_proxy_settings(previous)
        PROXY_STATE_FILE.unlink()
        set_restore_on_next_login(False)
        return True


def turn_off_leftover_proxy():
    """Turn off the proxy if it still points at URL Monitor but no saved state exists,
    e.g. after running an older version that did not save the user's settings."""
    settings = read_proxy_settings()
    server = (settings["ProxyServer"] or [""])[0]
    enabled = (settings["ProxyEnable"] or [0])[0]
    if enabled and server == f"{PROXY_HOST}:{PROXY_PORT}":
        write_proxy_settings({"ProxyEnable": [0, REG_DWORD]})
        return True
    return False


_console_handler = None


def install_exit_handlers():
    global _console_handler
    atexit.register(restore_system_proxy)
    if IS_WINDOWS:
        # Closing the console window skips `finally` blocks and atexit, so undo
        # the proxy from a console control handler too.
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def on_console_event(event):
            if event in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
                restore_system_proxy()
            return False

        _console_handler = handler_type(on_console_event)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)


# ---------------------------------------------------------------------------
# Certificate authority
# ---------------------------------------------------------------------------


def ensure_ca():
    if not (CERT_DIR / "mitmproxy-ca.pem").exists():
        from mitmproxy.certs import CertStore

        CertStore.create_store(
            CERT_DIR, "mitmproxy", 2048, organization="URL Monitor", cn=CA_NAME
        )


def ca_thumbprint():
    der = ssl.PEM_cert_to_DER_cert(CA_CERT_FILE.read_text(encoding="ascii"))
    return hashlib.sha1(der).hexdigest()


def is_ca_trusted():
    result = subprocess.run(
        ["certutil", "-user", "-store", "Root", ca_thumbprint()],
        capture_output=True,
    )
    return result.returncode == 0


def install_ca():
    print(
        "\nURL Monitor needs to add its own certificate to your trusted certificates so it\n"
        "can see the addresses of HTTPS pages. The certificate is created on this computer\n"
        "and its private key never leaves it. Windows will ask you to confirm.\n"
        "Remove it at any time with: python python_backend.py uninstall-cert\n"
    )
    result = subprocess.run(["certutil", "-user", "-addstore", "Root", str(CA_CERT_FILE)])
    return result.returncode == 0 and is_ca_trusted()


def print_manual_setup():
    print(
        "Automatic setup is only available on Windows. To use URL Monitor here:\n"
        f"  1. Trust the certificate {CA_CERT_FILE} in your browser or operating system.\n"
        f"  2. Set your browser's HTTP and HTTPS proxy to {PROXY_HOST}:{PROXY_PORT}."
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


async def run_proxy(addons):
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    options = Options(listen_host=PROXY_HOST, listen_port=PROXY_PORT, confdir=str(CERT_DIR))
    master = DumpMaster(options, with_termlog=True, with_dumper=False)
    master.addons.add(*addons)
    await master.run()


def cmd_start(args):
    for port in (PROXY_PORT, DASHBOARD_PORT):
        if port_in_use("127.0.0.1", port):
            print(f"Port {port} is already in use. Is URL Monitor already running?")
            return 1

    ensure_data_files()
    first_run = not CONFIG_FILE.exists()
    config = load_config()

    if IS_WINDOWS and restore_system_proxy():
        print("Restored proxy settings left over from a run that did not shut down cleanly.")

    ensure_ca()
    if IS_WINDOWS:
        if not is_ca_trusted() and not install_ca():
            print(
                "The certificate was not installed, so HTTPS websites would stop working.\n"
                "URL Monitor has not changed any settings. Exiting."
            )
            return 1
    else:
        print_manual_setup()

    logger = TrafficLogger()
    print(f"Watching {len(logger.blocklist)} domains.")

    # Hide the per-request log lines from the dashboard polling every few seconds.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    dashboard = make_server(
        DASHBOARD_HOST, DASHBOARD_PORT, create_app(config["dashboard_password"]), threaded=True
    )
    threading.Thread(target=dashboard.serve_forever, daemon=True).start()
    print(f"Dashboard: http://{DASHBOARD_HOST}:{DASHBOARD_PORT}  (user: {DASHBOARD_USER})")
    if first_run:
        print(f"Dashboard password: {config['dashboard_password']}")
    print(f"The dashboard password is stored in {CONFIG_FILE}")
    print("Press Ctrl+C to stop. Your proxy settings are restored when URL Monitor stops.\n")

    if IS_WINDOWS:
        install_exit_handlers()
    addons = [logger, ProxyStarted()]
    try:
        asyncio.run(run_proxy(addons))
    except KeyboardInterrupt:
        pass
    finally:
        if IS_WINDOWS and restore_system_proxy():
            print("Proxy settings restored.")
    return 0


def cmd_restore(args):
    if not IS_WINDOWS:
        print("URL Monitor only changes proxy settings on Windows; nothing to restore.")
        return 0
    if restore_system_proxy():
        print("Your previous proxy settings have been restored.")
    elif turn_off_leftover_proxy():
        print("Turned off a proxy left behind by URL Monitor.")
    else:
        set_restore_on_next_login(False)
        print("Proxy settings are not set by URL Monitor; nothing to restore.")
    return 0


def cmd_install_cert(args):
    ensure_data_files()
    ensure_ca()
    if not IS_WINDOWS:
        print_manual_setup()
        return 0
    if is_ca_trusted():
        print("The certificate is already installed.")
        return 0
    if install_ca():
        print("Certificate installed.")
        return 0
    print("The certificate was not installed.")
    return 1


def cmd_uninstall_cert(args):
    if IS_WINDOWS:
        # Delete by name so certificates from earlier installs are removed too.
        subprocess.run(["certutil", "-user", "-delstore", "Root", CA_NAME])
    else:
        print(f"Remove the certificate named '{CA_NAME}' from your browser or system.")
    if CERT_DIR.exists():
        shutil.rmtree(CERT_DIR)
        print(f"Deleted the certificate and its private key from {CERT_DIR}.")
    return 0


def cmd_update_blocklist(args):
    ensure_data_files()
    print(f"Downloading {args.url} ...")
    try:
        with urllib.request.urlopen(args.url, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
    except OSError as e:
        print(f"Download failed: {e}")
        return 1
    domains = parse_blocklist(text.splitlines())
    if not domains:
        print("No domains found in the download; keeping the existing list.")
        return 1
    tmp = DOWNLOADED_BLOCKLIST_FILE.with_name(DOWNLOADED_BLOCKLIST_FILE.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, DOWNLOADED_BLOCKLIST_FILE)
    print(f"Saved {len(domains)} domains to {DOWNLOADED_BLOCKLIST_FILE}.")
    print("Restart URL Monitor to use the new list.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the websites visited on this computer and flag watched domains."
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("start", help="start monitoring (the default)")
    commands.add_parser(
        "restore", help="restore your proxy settings if internet access stopped working"
    )
    commands.add_parser("install-cert", help="trust URL Monitor's certificate")
    commands.add_parser(
        "uninstall-cert", help="remove URL Monitor's certificate and its private key"
    )
    update = commands.add_parser(
        "update-blocklist", help="download a public domain list to flag"
    )
    update.add_argument(
        "--url",
        default=DEFAULT_BLOCKLIST_URL,
        help="hosts-file or plain domain list to download (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    handlers = {
        None: cmd_start,
        "start": cmd_start,
        "restore": cmd_restore,
        "install-cert": cmd_install_cert,
        "uninstall-cert": cmd_uninstall_cert,
        "update-blocklist": cmd_update_blocklist,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
