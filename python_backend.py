import os
import json
import subprocess
import ctypes
from mitmproxy import http
from flask import Flask, jsonify
from datetime import datetime
import threading

# Configuration
app = Flask(__name__)
LOG_FILE = "traffic_log.json"
FILTERED_LOG_FILE = "filtered_traffic_log.json"
BLOCKLIST_FILE = "adult_sites_blocklist.txt"
PROXY_PORT = 8081
FLASK_PORT = 5000
VERBOSE = True  # Verbose subprocess logging

# Ensure log and blocklist files exist
for file_name, content in [
    (LOG_FILE, []),
    (FILTERED_LOG_FILE, []),
    (BLOCKLIST_FILE, "# Add domains to block\n"),
]:
    if not os.path.exists(file_name):
        with open(file_name, "w") as f:
            if isinstance(content, list):
                json.dump(content, f, indent=4)
            else:
                f.write(content)


# Check if running as administrator
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if not is_admin():
    print("Error: Please run this script as an administrator.")
    exit(1)


# Proxy configuration
def enable_proxy_globally(proxy_address, proxy_port):
    """Enable proxy for both WinHTTP and WinINET."""
    try:
        # Set WinHTTP proxy
        subprocess.run(
            ["netsh", "winhttp", "set", "proxy", f"{proxy_address}:{proxy_port}"],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        if VERBOSE:
            print("WinHTTP proxy set.")

        # Set WinINET proxy (for browsers and system-wide use)
        subprocess.run(
            [
                "powershell",
                "-Command",
                f"Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' -Name ProxyServer -Value '{proxy_address}:{proxy_port}'",
            ],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        subprocess.run(
            [
                "powershell",
                "-Command",
                "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' -Name ProxyEnable -Value 1",
            ],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        print("Proxy enabled globally.")
    except subprocess.CalledProcessError as e:
        print(f"Error enabling proxy: {e.stderr if e.stderr else e}")


def disable_proxy_globally():
    """Disable proxy for both WinHTTP and WinINET."""
    try:
        # Reset WinHTTP proxy
        subprocess.run(
            ["netsh", "winhttp", "reset", "proxy"],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        if VERBOSE:
            print("WinHTTP proxy reset.")

        # Reset WinINET proxy
        subprocess.run(
            [
                "powershell",
                "-Command",
                "Remove-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' -Name ProxyEnable -ErrorAction SilentlyContinue",
            ],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        subprocess.run(
            [
                "powershell",
                "-Command",
                "Remove-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' -Name ProxyServer -ErrorAction SilentlyContinue",
            ],
            check=True,
            capture_output=VERBOSE,
            text=True,
        )
        print("Proxy disabled globally.")
    except subprocess.CalledProcessError as e:
        print(f"Error disabling proxy: {e.stderr if e.stderr else e}")


class TrafficLogger:
    """Class to log HTTP traffic and filter based on a blocklist."""

    def __init__(self):
        self.blocklist = self.load_blocklist()

    def load_blocklist(self):
        """Load the blocklist from the file."""
        try:
            with open(BLOCKLIST_FILE, "r") as f:
                return set(
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                )
        except Exception as e:
            print(f"Error loading blocklist: {e}")
            return set()

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
        """Check if the URL is in the blocklist."""
        return any(domain in url for domain in self.blocklist)

    def request(self, flow: http.HTTPFlow):
        """Log each HTTP request."""
        try:
            url = flow.request.url
            user_agent = flow.request.headers.get("User-Agent", "")
            method = flow.request.method

            if self.is_personal_request(user_agent, url, method):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entry = {"timestamp": timestamp, "url": url}

                with open(LOG_FILE, "r+") as f:
                    data = json.load(f)
                    data.append(entry)
                    f.seek(0)
                    json.dump(data, f, indent=4)

                if self.is_blocked_site(url):
                    with open(FILTERED_LOG_FILE, "r+") as f:
                        data = json.load(f)
                        data.append(entry)
                        f.seek(0)
                        json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error logging request: {e}")


addons = [TrafficLogger()]


@app.route("/api/logs", methods=["GET"])
def get_logs():
    try:
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
        return jsonify(logs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/filtered_logs", methods=["GET"])
def get_filtered_logs():
    try:
        with open(FILTERED_LOG_FILE, "r") as f:
            logs = json.load(f)
        return jsonify(logs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/blocklist", methods=["GET"])
def get_blocklist():
    try:
        with open(BLOCKLIST_FILE, "r") as f:
            blocklist = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return jsonify(blocklist), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_flask():
    try:
        app.run(host="0.0.0.0", port=FLASK_PORT)
    except Exception as e:
        print(f"Error starting Flask server: {e}")


def run_mitmproxy():
    try:
        from mitmproxy.tools.main import mitmdump
        mitmdump(["-s", __file__, "--listen-port", str(PROXY_PORT)])
    except Exception as e:
        print(f"Error starting Mitmproxy: {e}")


if __name__ == "__main__":
    try:
        enable_proxy_globally("127.0.0.1", PROXY_PORT)

        # Start Flask server in a separate thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        # Start Mitmproxy in the main thread
        run_mitmproxy()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        disable_proxy_globally()
