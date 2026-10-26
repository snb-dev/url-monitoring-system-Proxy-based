# URL Monitor

URL Monitor records the websites visited on a Windows computer and flags (or
blocks) visits to domains on a watch list, such as adult sites. It is intended
for **parents supervising their own children's computers** and for **people who
want to hold themselves accountable**.

It works as a local proxy built on [mitmproxy](https://mitmproxy.org/). Browser
traffic goes through it, and a password-protected dashboard at
`http://127.0.0.1:5000` shows the history, today's flagged visits and alerts as
they happen. Everything stays on the computer: nothing is sent anywhere.

## Use it responsibly

URL Monitor can read the addresses of every page visited, including HTTPS pages.
Only install it on a computer you own or administer, and only monitor people who
know about it and have agreed to it, or children in your care. Secretly recording
another adult's internet use is illegal in many countries. You are responsible
for complying with the laws where you live.

## Requirements

- Windows 10 or 11. Proxy and certificate setup are automatic only on Windows.
  On macOS and Linux it runs, but you configure the browser yourself (see below).
- Python 3.11 or newer from [python.org](https://www.python.org/downloads/).
  Tick **"Add python.exe to PATH"** during setup.

Administrator rights are **not** needed.

## Installation

Download the code (**Code → Download ZIP** on GitHub, then extract it) or clone it:

```bat
git clone https://github.com/snb-dev/url-monitoring-system-Proxy-based.git
```

Then double-click **`start.bat`**. On the first run it installs the Python
packages URL Monitor needs.

To install it as a command instead, run `py -3 -m pip install .` in the folder.
You can then start it from anywhere with `urlmonitor start`.

## First start

On the first start, URL Monitor:

1. Creates a certificate authority that exists only on this computer, and asks
   Windows to trust it. Windows shows a security warning: click **Yes**. Without
   it, URL Monitor can't read HTTPS pages, so it exits without changing anything.
2. Generates a dashboard password and prints it. It is also stored in the
   settings file (see [Settings](#settings)). The dashboard user name is `admin`.
3. Points the Windows proxy settings at itself (`127.0.0.1:8081`) and opens the
   dashboard.

Press **Ctrl+C** in the console window to stop. Your original proxy settings are
put back when it stops.

## Commands

Run these with `start.bat <command>`, `py -3 -m urlmonitor <command>`, or
`urlmonitor <command>` if you installed it.

| Command | What it does |
| --- | --- |
| `start` | Start monitoring (the default). |
| `status` | Show whether it is running, the proxy and certificate state, and how much history is stored. |
| `restore` | Put your proxy settings back if web pages stop loading. |
| `update-blocklist [--url URL]` | Download a public domain list to flag. |
| `install-cert` | Trust URL Monitor's certificate. |
| `uninstall-cert` | Remove the certificate and delete its private key. |

## What gets recorded

By default URL Monitor records **the pages that are opened**: one entry per page,
not every image, script and tracker the page loads. Frames embedded from watched
sites (for example, an embedded video) are recorded too. Set `log_mode = "all"`
to record every request a browser makes.

Only browser traffic is recorded. History older than 90 days is deleted
automatically; change this with `retention_days`.

## The watch list

Add domains to `blocklist.txt` in the data folder, one per line. A domain also
matches its subdomains, so `example.com` flags `www.example.com` and
`m.example.com`. Hosts-file lines (`0.0.0.0 example.com`) and pasted URLs work
too. Changes are picked up within a few seconds; no restart needed.

To flag adult sites without maintaining a list yourself, run:

```bat
start.bat update-blocklist
```

This downloads the [StevenBlack/hosts](https://github.com/StevenBlack/hosts)
"porn-only" list (over 60,000 domains) to `blocklist_downloaded.txt`. That list
is maintained by its own authors under its own license. Use `--url` to download
any other hosts file or plain domain list. Run it again to update.

To **block** watched sites instead of only flagging them, set
`block_watched_sites = true`. Blocked pages show a "This site is blocked" page,
and the attempt is recorded.

## Settings

Settings are in `config.toml` in the data folder. Restart URL Monitor after
changing it.

```toml
[dashboard]
password = "generated on first run"
port = 5000

[proxy]
port = 8081

[monitoring]
log_mode = "pages"          # or "all"
retention_days = 90         # 0 keeps everything
block_watched_sites = false
```

## Where data is stored

| System | Data folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\URLMonitor` |
| macOS | `~/Library/Application Support/URLMonitor` |
| Linux | `~/.local/share/urlmonitor` |

Set the `URLMON_DATA_DIR` environment variable to use another folder. Version 0.1
kept its data in a `data` folder next to the program; it is moved to the new
location, and its JSON logs are imported, on the first start.

| File | Contents |
| --- | --- |
| `history.db` | Browsing history (SQLite) |
| `config.toml` | Settings and the dashboard password |
| `blocklist.txt` | Your watch list |
| `blocklist_downloaded.txt` | Downloaded public list |
| `certs/` | The certificate authority, including its **private key** |
| `proxy_state.json` | Your proxy settings, saved while monitoring is on |

Keep `certs/` private: anyone with that key could intercept HTTPS traffic on any
computer that trusts the certificate. `uninstall-cert` removes the certificate
from Windows and deletes the key.

## If web pages stop loading

URL Monitor restores your proxy settings when you press Ctrl+C or close its
window, and it also arranges a restore at your next Windows login in case the
computer crashes. If pages still don't load, double-click **`restore_proxy.bat`**.

To do it by hand: **Settings → Network & internet → Proxy → Manual proxy setup
→ Use a proxy server: Off**.

## Firefox

Firefox has its own certificate list. If it shows certificate errors, open
`about:config` and set `security.enterprise_roots.enabled` to `true`.

## macOS and Linux

Run `python3 -m urlmonitor start`, then:

1. Trust `certs/mitmproxy-ca-cert.pem` from the data folder in your browser or
   operating system.
2. Set the browser's HTTP and HTTPS proxy to `127.0.0.1:8081`.

## Uninstalling

1. Stop URL Monitor (Ctrl+C).
2. Run `start.bat uninstall-cert`.
3. Delete the program folder and the data folder.

## Security

- The proxy and dashboard listen on `127.0.0.1` only, so other devices on the
  network can't reach them.
- The dashboard requires a password and sends a strict Content Security Policy.
- Each installation creates its own certificate. No certificate or key ships
  with URL Monitor.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The code is in the `urlmonitor` package:

| Module | Purpose |
| --- | --- |
| `cli.py` | Commands and start-up |
| `addon.py` | mitmproxy addon: decides what to record, flag and block |
| `storage.py` | SQLite history |
| `blocklist.py` | Watch list parsing, matching and downloads |
| `dashboard.py` | Flask API and login; the UI is in `web/` |
| `winproxy.py`, `_restore.py` | Windows proxy settings and crash recovery |
| `certs.py` | Certificate creation and trust |
| `config.py` | Data folder and `config.toml` |

## License

[MIT](LICENSE)
