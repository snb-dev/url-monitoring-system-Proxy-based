# URL Monitor

URL Monitor records the websites visited on a Windows computer and flags visits
to domains on a watch list (for example, adult sites). It is intended for
**parents supervising their own children's computers** and for **people who
want to hold themselves accountable**.

It works as a local proxy built on [mitmproxy](https://mitmproxy.org/). Browser
traffic goes through it, it logs the pages requested, and a password-protected
dashboard at `http://127.0.0.1:5000` shows the history and the flagged visits.
Everything stays on the computer: nothing is sent anywhere.

> **Note:** URL Monitor *flags* watched sites. It does not block them.

## Use it responsibly

URL Monitor can read the addresses of every page visited, including HTTPS pages.
Only install it on a computer you own or administer, and only monitor people who
know about it and have agreed to it, or children in your care. Secretly recording
another adult's internet use is illegal in many countries. You are responsible
for complying with the laws where you live.

## Requirements

- Windows 10 or 11. Proxy and certificate setup are automatic only on Windows.
  On macOS and Linux it runs, but you configure the browser yourself (see below).
- Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
  Tick **"Add python.exe to PATH"** during setup.

Administrator rights are **not** needed.

## Installation

```bat
git clone https://github.com/snb-dev/url-monitoring-system-Proxy-based.git
cd url-monitoring-system-Proxy-based
py -3 -m pip install -r requirements.txt
```

## Usage

Double-click **`start.bat`**, or run:

```bat
py -3 python_backend.py start
```

On the first start, URL Monitor:

1. Creates a certificate authority that exists only on this computer, and asks
   Windows to trust it. Windows shows a security warning: click **Yes**. Without
   it, URL Monitor can't read HTTPS pages, so it exits without changing anything.
2. Generates a dashboard password and prints it. It is also stored in
   `data/config.json`. The dashboard user name is `admin`.
3. Points the Windows proxy settings at itself (`127.0.0.1:8081`).

Open `http://127.0.0.1:5000` to see the dashboard. Press **Ctrl+C** in the
console window to stop. Your original proxy settings are put back when it stops.

### Commands

| Command | What it does |
| --- | --- |
| `python_backend.py start` | Start monitoring (default when no command is given). |
| `python_backend.py restore` | Put your proxy settings back if web pages stop loading. |
| `python_backend.py update-blocklist [--url URL]` | Download a public domain list to flag. |
| `python_backend.py install-cert` | Trust URL Monitor's certificate. |
| `python_backend.py uninstall-cert` | Remove the certificate and delete its private key. |

## The watch list

Add domains to `data/blocklist.txt`, one per line. A domain also matches its
subdomains, so `example.com` flags `www.example.com` and `m.example.com`.
Hosts-file lines (`0.0.0.0 example.com`) and pasted URLs work too.

To flag adult sites without maintaining a list yourself, run:

```bat
py -3 python_backend.py update-blocklist
```

This downloads the [StevenBlack/hosts](https://github.com/StevenBlack/hosts)
"porn-only" list to `data/blocklist_downloaded.txt`. That list is maintained by
its own authors under its own license. Use `--url` to download any other hosts
file or plain domain list. Restart URL Monitor after changing either list.

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

Run `python3 python_backend.py start`, then:

1. Trust `data/certs/mitmproxy-ca-cert.pem` in your browser or operating system.
2. Set the browser's HTTP and HTTPS proxy to `127.0.0.1:8081`.

## Where data is stored

Everything is in the `data/` folder next to the program. This folder is
excluded from git, so it can't be committed by accident.

| File | Contents |
| --- | --- |
| `traffic_log.json` | Every page request logged |
| `filtered_traffic_log.json` | Requests to watched domains |
| `blocklist.txt` | Your watch list |
| `blocklist_downloaded.txt` | Downloaded public list |
| `config.json` | Dashboard password |
| `certs/` | The certificate authority, including its **private key** |
| `proxy_state.json` | Your proxy settings, saved while monitoring is on |

Keep `data/certs/` private: anyone with that key could intercept HTTPS traffic
on any computer that trusts the certificate. `uninstall-cert` removes the
certificate from Windows and deletes the key.

## Uninstalling

1. Stop URL Monitor (Ctrl+C).
2. Run `py -3 python_backend.py uninstall-cert`.
3. Delete the folder.

## Security

- The proxy and dashboard listen on `127.0.0.1` only, so other devices on the
  network can't reach them.
- The dashboard requires a password.
- Each installation creates its own certificate. No certificate or key ships
  with URL Monitor.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

[MIT](LICENSE)
