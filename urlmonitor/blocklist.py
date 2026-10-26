"""The watch list: which domains to flag."""

import logging
import os
import time
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

DEFAULT_BLOCKLIST_URL = (
    "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts"
)

BLOCKLIST_HEADER = """\
# Domains to flag, one per line. A domain also matches its subdomains,
# so "example.com" flags "www.example.com" and "m.example.com".
# Lines starting with # are ignored. Hosts-file lines ("0.0.0.0 example.com")
# and pasted URLs work too. Changes are picked up within a few seconds.
"""

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


def domain_matches(host, domains):
    """True if host, or any domain it is a subdomain of, is in domains."""
    labels = normalize_domain(host).split(".")
    return any(".".join(labels[i:]) in domains for i in range(len(labels)))


def ensure_blocklist(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(BLOCKLIST_HEADER, encoding="utf-8")


def read_blocklist(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return parse_blocklist(f)
    except FileNotFoundError:
        return set()


class Blocklist:
    """The domains from a set of list files, reloaded when the files change."""

    def __init__(self, files, check_interval=5.0):
        self.files = list(files)
        self.check_interval = check_interval
        self.domains = set()
        self._stamps = None
        self._next_check = 0.0
        self.reload_if_changed()

    def _file_stamps(self):
        stamps = []
        for path in self.files:
            try:
                stat = os.stat(path)
                stamps.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                stamps.append(None)
        return stamps

    def reload_if_changed(self):
        """Reload the files if they changed. Returns True if it reloaded."""
        stamps = self._file_stamps()
        if stamps == self._stamps:
            return False
        domains = set()
        for path in self.files:
            try:
                domains |= read_blocklist(path)
            except OSError as e:
                log.warning("Could not read blocklist %s: %s", path, e)
        self.domains = domains
        self._stamps = stamps
        return True

    def matches(self, host):
        now = time.monotonic()
        if now >= self._next_check:
            self._next_check = now + self.check_interval
            if self.reload_if_changed():
                log.info("Watch list reloaded: %d domains.", len(self.domains))
        return domain_matches(host, self.domains)

    def __len__(self):
        return len(self.domains)


def download_blocklist(url, destination, timeout=60):
    """Download a list to destination. Returns the number of domains in it.

    Raises OSError if the download fails and ValueError if it has no domains;
    the existing file is kept in both cases.
    """
    with urllib.request.urlopen(url, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    domains = parse_blocklist(text.splitlines())
    if not domains:
        raise ValueError("No domains found in the download")
    tmp = destination.with_name(destination.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, destination)
    return len(domains)
