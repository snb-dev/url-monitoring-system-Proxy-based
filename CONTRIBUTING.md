# Contributing to URL Monitor

Thanks for helping! Bug reports, fixes, documentation and blocklist ideas are
all welcome.

## Before you start

- For anything bigger than a small fix, please open an issue first so we can
  agree on the approach.
- Security problems: don't open an issue. Follow [SECURITY.md](SECURITY.md).
- Never paste real browsing history, dashboard passwords or files from the
  `certs` folder into issues, pull requests or test data.
- By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

You need Python 3.11 or newer.

```bash
git clone https://github.com/snb-dev/url-monitoring-system-Proxy-based.git
cd url-monitoring-system-Proxy-based
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run URL Monitor from your checkout with `python -m urlmonitor start`. Use
`start --manual` and point a browser at `127.0.0.1:8081` if you don't want it to
change your Windows proxy settings while you work.

Set `URLMON_DATA_DIR` to a scratch folder to keep test data away from your real
history.

## Checks

These run in CI on every push; please run them before opening a pull request:

```bash
ruff check .
ruff format --check .      # or `ruff format .` to fix
pytest
python packaging/smoke_test.py python -m urlmonitor
```

On Windows, `URLMON_WINDOWS_INTEGRATION=1 pytest` also runs tests against the
real registry. They change your proxy and start-up settings for a moment and
put them back.

## Pull requests

- Keep each pull request to one change, with tests for new behaviour.
- Add a line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md) for
  anything users will notice.
- Match the style of the surrounding code. Messages shown to users should be
  plain and say what to do next.

## Project layout

| Path | Purpose |
| --- | --- |
| `urlmonitor/` | The application (see the module table in the README) |
| `urlmonitor/web/` | Dashboard HTML, CSS and JavaScript |
| `tests/` | pytest tests |
| `packaging/` | PyInstaller spec, Inno Setup installer, build and smoke-test scripts |
| `.github/workflows/` | CI and release automation |

## Releasing (maintainers)

1. Update the version in `urlmonitor/__init__.py`.
2. In `CHANGELOG.md`, move the `Unreleased` entries under the new version and
   update the links at the bottom.
3. Commit, then tag and push: `git tag v0.3.0 && git push origin v0.3.0`.

The [Release workflow](.github/workflows/release.yml) checks the tag matches the
version, builds and smoke-tests the installer on Windows, and publishes a GitHub
release with the installer and the Python package attached.

### Code signing

Unsigned installers trigger a Windows SmartScreen warning. To sign releases, add
the repository secrets `SIGN_PFX_BASE64` (your `.pfx` code-signing certificate,
base64-encoded) and `SIGN_PFX_PASSWORD`; the build signs `URLMonitor.exe` and the
installer when they are set. Open-source projects can get free signing from the
[SignPath Foundation](https://signpath.org/); Azure Trusted Signing is a
low-cost alternative. Both use their own signing steps instead of a `.pfx`.
