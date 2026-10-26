# Changelog

All notable changes to URL Monitor are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0]

The first public release.

### Added

- Windows installer (no administrator rights needed) with Start menu shortcuts
  and an option to start at sign-in.
- `autostart on|off` command, and `start --manual` to run without changing
  Windows settings.
- Password-protected dashboard with today's statistics, the most-flagged sites,
  search, paging, in-page and desktop alerts, dark mode and a mobile layout.
- Optional blocking of watched sites (`block_watched_sites`).
- `update-blocklist` command to download a maintained public domain list.
- `status`, `restore`, `install-cert` and `uninstall-cert` commands.
- Settings file (`config.toml`) and automatic deletion of old history.

### Changed

- Records the pages that are opened, not every image, script and tracker
  (`log_mode = "all"` keeps the old behaviour).
- History is stored in SQLite in the user's app data folder. Data from earlier
  versions is moved and imported on the first start.
- Watched domains match by domain and subdomain instead of by text anywhere in
  the URL.
- Only per-user proxy settings are changed, so administrator rights are no
  longer needed.

### Security

- Your previous proxy settings are saved and restored when URL Monitor stops,
  when its window is closed, and at the next sign-in after a crash.
- Each installation creates its own certificate authority and asks before
  trusting it.
- The proxy and dashboard only accept connections from the same computer.

## 0.1.0

The original prototype.

[Unreleased]: https://github.com/snb-dev/url-monitoring-system-Proxy-based/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/snb-dev/url-monitoring-system-Proxy-based/releases/tag/v0.2.0
