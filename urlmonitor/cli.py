"""Command-line interface: `python -m urlmonitor <command>`."""

import argparse
import asyncio
import logging
import socket
import sys
import threading
import webbrowser

from werkzeug.serving import make_server

from . import __version__, certs
from .blocklist import (
    DEFAULT_BLOCKLIST_URL,
    Blocklist,
    domain_matches,
    download_blocklist,
    ensure_blocklist,
)
from .config import (
    ConfigError,
    Paths,
    default_data_dir,
    ensure_config,
    load_settings,
    migrate_legacy_data,
)
from .storage import Storage
from .winproxy import IS_WINDOWS, SystemProxy, is_autostart_enabled, set_autostart

LOCALHOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 8081


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((LOCALHOST, port)) == 0


def prepare(paths):
    """Create or migrate the data folder and load the settings."""
    if migrate_legacy_data(paths):
        print(f"Moved your data from the program folder to {paths.data_dir}")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    created = ensure_config(paths)
    ensure_blocklist(paths.blocklist)
    return load_settings(paths), created


def import_legacy_logs(paths, storage, blocklist):
    log_file = paths.data_dir / "traffic_log.json"
    if not log_file.exists():
        return
    try:
        count = storage.import_json_log(
            log_file, lambda host: domain_matches(host, blocklist.domains)
        )
    except (OSError, ValueError, KeyError) as e:
        print(f"Could not import the previous version's log {log_file}: {e}")
        return
    for old in (log_file, paths.data_dir / "filtered_traffic_log.json"):
        if old.exists():
            old.replace(old.with_name(old.name + ".imported"))
    print(f"Imported {count} visits from the previous version's log.")


def print_manual_setup(paths, proxy_port):
    print(
        "Automatic setup is only available on Windows. To use URL Monitor here:\n"
        f"  1. Trust the certificate {certs.ca_cert_file(paths.cert_dir)}\n"
        "     in your browser or operating system.\n"
        f"  2. Set your browser's HTTP and HTTPS proxy to {LOCALHOST}:{proxy_port}."
    )


def trust_ca(paths):
    """Windows: make sure the CA is trusted, asking the user if needed."""
    if certs.is_trusted(paths.cert_dir):
        return True
    print(
        "\nURL Monitor needs to add its own certificate to your trusted certificates so it\n"
        "can see the addresses of HTTPS pages. The certificate is created on this computer\n"
        "and its private key never leaves it. Windows will ask you to confirm.\n"
        "Uninstalling URL Monitor, or its uninstall-cert command, removes it again.\n"
    )
    return certs.install(paths.cert_dir)


async def run_proxy(addons, port, cert_dir):
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    options = Options(listen_host=LOCALHOST, listen_port=port, confdir=str(cert_dir))
    master = DumpMaster(options, with_termlog=True, with_dumper=False)
    master.addons.add(*addons)
    await master.run()


def cmd_start(paths, args):
    from .addon import Monitor, ProxyStarted
    from .dashboard import DASHBOARD_USER, create_app

    try:
        settings, first_run = prepare(paths)
    except ConfigError as e:
        print(f"There is a problem with {paths.config_file}:\n  {e}")
        return 1

    for port in (settings.proxy_port, settings.dashboard_port):
        if port_in_use(port):
            print(f"Port {port} is already in use. Is URL Monitor already running?")
            return 1

    proxy_address = f"{LOCALHOST}:{settings.proxy_port}"
    if IS_WINDOWS and SystemProxy(paths.proxy_state, proxy_address).restore():
        print("Restored proxy settings left over from a run that did not shut down cleanly.")
    # In manual mode the user points their browser at the proxy themselves.
    automatic = IS_WINDOWS and not getattr(args, "manual", False)
    system_proxy = SystemProxy(paths.proxy_state, proxy_address) if automatic else None

    certs.ensure_ca(paths.cert_dir)
    if automatic:
        if not trust_ca(paths):
            print(
                "The certificate was not installed, so HTTPS websites would stop working.\n"
                "URL Monitor has not changed any settings. Exiting."
            )
            return 1
    else:
        print_manual_setup(paths, settings.proxy_port)

    storage = Storage(paths.database)
    blocklist = Blocklist([paths.blocklist, paths.downloaded_blocklist])
    import_legacy_logs(paths, storage, blocklist)
    print(f"Watching {len(blocklist)} domains.")

    # Hide the per-request log lines from the dashboard polling every few seconds.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    dashboard_url = f"http://{LOCALHOST}:{settings.dashboard_port}"
    dashboard = make_server(
        LOCALHOST,
        settings.dashboard_port,
        create_app(storage, blocklist, settings.dashboard_password),
        threaded=True,
    )
    threading.Thread(target=dashboard.serve_forever, daemon=True).start()
    print(f"Dashboard: {dashboard_url}  (user: {DASHBOARD_USER})")
    if first_run:
        print(f"Dashboard password: {settings.dashboard_password}")
    print(f"Settings and the dashboard password: {paths.config_file}")
    print("Press Ctrl+C to stop. Your proxy settings are restored when URL Monitor stops.\n")

    def on_started():
        if system_proxy:
            system_proxy.enable()
        print(f"Monitoring started. Proxy: {proxy_address}")
        if first_run and IS_WINDOWS:
            webbrowser.open(dashboard_url)

    if system_proxy:
        system_proxy.install_exit_handlers()
    addons = [Monitor(storage, blocklist, settings), ProxyStarted(on_started)]
    try:
        asyncio.run(run_proxy(addons, settings.proxy_port, paths.cert_dir))
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.shutdown()
        if system_proxy and system_proxy.restore():
            print("Proxy settings restored.")
    return 0


def cmd_status(paths, args):
    print(f"URL Monitor {__version__}")
    print(f"Data folder:     {paths.data_dir}")
    if not paths.config_file.exists():
        print("Not set up yet. Start URL Monitor to set it up.")
        return 0
    try:
        settings = load_settings(paths)
    except ConfigError as e:
        print(f"Settings error:  {e}")
        return 1
    running = port_in_use(settings.proxy_port)
    print(f"Running:         {'yes' if running else 'no'}")
    print(f"Dashboard:       http://{LOCALHOST}:{settings.dashboard_port}")
    print(f"Log mode:        {settings.log_mode}")
    print(f"Blocking:        {'on' if settings.block_watched_sites else 'off (flag only)'}")
    if IS_WINDOWS:
        proxy = SystemProxy(paths.proxy_state, f"{LOCALHOST}:{settings.proxy_port}")
        print(f"System proxy:    {'set' if proxy.is_active() else 'not set'}")
        if certs.ca_cert_file(paths.cert_dir).exists():
            trusted = certs.is_trusted(paths.cert_dir)
            print(f"Certificate:     {'trusted' if trusted else 'NOT trusted'}")
        print(f"Start at sign-in: {'on' if is_autostart_enabled() else 'off'}")
    blocklist = Blocklist([paths.blocklist, paths.downloaded_blocklist])
    print(f"Watched domains: {len(blocklist)}")
    if paths.database.exists():
        print(f"Visits stored:   {Storage(paths.database).count()}")
    return 0


def cmd_restore(paths, args):
    if not IS_WINDOWS:
        print("URL Monitor only changes proxy settings on Windows; nothing to restore.")
        return 0
    port = DEFAULT_PROXY_PORT
    if paths.config_file.exists():
        try:
            port = load_settings(paths).proxy_port
        except ConfigError:
            pass
    proxy = SystemProxy(paths.proxy_state, f"{LOCALHOST}:{port}")
    if proxy.restore():
        print("Your previous proxy settings have been restored.")
    elif proxy.turn_off_leftover():
        print("Turned off a proxy left behind by URL Monitor.")
    else:
        proxy.set_restore_on_next_login(False)
        print("Proxy settings are not set by URL Monitor; nothing to restore.")
    return 0


def cmd_autostart(paths, args):
    if not IS_WINDOWS:
        print("Starting at sign-in is only available on Windows.")
        return 1
    if args.action != "status":
        set_autostart(args.action == "on")
    if is_autostart_enabled():
        print("URL Monitor starts when you sign in to Windows.")
    else:
        print("URL Monitor does not start when you sign in to Windows.")
    return 0


def cmd_install_cert(paths, args):
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    certs.ensure_ca(paths.cert_dir)
    if not IS_WINDOWS:
        print_manual_setup(paths, DEFAULT_PROXY_PORT)
        return 0
    if trust_ca(paths):
        print("The certificate is installed.")
        return 0
    print("The certificate was not installed.")
    return 1


def cmd_uninstall_cert(paths, args):
    if IS_WINDOWS:
        certs.uninstall(paths.cert_dir)
    else:
        print(f"Remove the certificate named '{certs.CA_NAME}' from your browser or system.")
    if certs.delete_files(paths.cert_dir):
        print(f"Deleted the certificate and its private key from {paths.cert_dir}.")
    return 0


def cmd_update_blocklist(paths, args):
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.url} ...")
    try:
        count = download_blocklist(args.url, paths.downloaded_blocklist)
    except (OSError, ValueError) as e:
        print(f"Download failed: {e}. Keeping the existing list.")
        return 1
    print(f"Saved {count} domains to {paths.downloaded_blocklist}.")
    print("A running URL Monitor picks up the new list within a few seconds.")
    return 0


COMMANDS = {
    "start": (cmd_start, "start monitoring (the default)"),
    "status": (cmd_status, "show whether URL Monitor is running and set up"),
    "restore": (cmd_restore, "restore your proxy settings if web pages stopped loading"),
    "autostart": (cmd_autostart, "start URL Monitor when you sign in to Windows (on/off)"),
    "install-cert": (cmd_install_cert, "trust URL Monitor's certificate"),
    "uninstall-cert": (cmd_uninstall_cert, "remove the certificate and its private key"),
    "update-blocklist": (cmd_update_blocklist, "download a public domain list to flag"),
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="urlmonitor",
        description="Record the websites visited on this computer and flag watched domains.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    for name, (_, help_text) in COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        if name == "start":
            command.add_argument(
                "--manual",
                action="store_true",
                help="don't change Windows proxy or certificate settings; "
                "point your browser at the proxy yourself",
            )
        elif name == "autostart":
            command.add_argument(
                "action", nargs="?", choices=["on", "off", "status"], default="status"
            )
        elif name == "update-blocklist":
            command.add_argument(
                "--url",
                default=DEFAULT_BLOCKLIST_URL,
                help="hosts file or plain domain list to download (default: %(default)s)",
            )
    if argv is None:
        argv = sys.argv[1:]
    # Run by Windows at sign-in after a crash (see SystemProxy.set_restore_on_next_login).
    if len(argv) == 2 and argv[0] == "_restore":
        if IS_WINDOWS:
            SystemProxy(argv[1], address=None).restore()
        return 0
    args = parser.parse_args(argv)

    handler = COMMANDS[args.command or "start"][0]
    return handler(Paths(default_data_dir()), args)
