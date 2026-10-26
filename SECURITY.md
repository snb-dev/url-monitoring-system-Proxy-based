# Security policy

URL Monitor sits between a browser and the internet and holds a certificate
authority that the computer trusts, so security problems matter. Thank you for
reporting them responsibly.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/snb-dev/url-monitoring-system-Proxy-based/security/advisories/new).

Include what you found, how to reproduce it, and what an attacker could do with
it. You'll get a reply within a week. Once a fix is released, you'll be credited
in the release notes unless you prefer not to be.

## Supported versions

Security fixes are made for the latest release only.

## What counts

Examples of what we want to hear about:

- Ways for another device on the network, or a website, to read the history,
  reach the dashboard or the proxy, or change settings.
- Ways to extract or misuse the certificate authority's private key.
- URL Monitor leaving the computer's proxy or certificate settings changed
  after it stops or is uninstalled.
- Anything that sends browsing data off the computer.

## How URL Monitor protects your data

- The proxy and dashboard only listen on `127.0.0.1`.
- The dashboard needs a randomly generated password and sends a strict Content
  Security Policy.
- Each installation creates its own certificate authority. Its private key is
  stored in the user's data folder and never leaves the computer.
  `uninstall-cert` (also run by the uninstaller) removes the certificate from
  Windows and deletes the key.
- Nothing is sent anywhere. The only network request URL Monitor makes itself is
  `update-blocklist`, which downloads the list you ask for.
