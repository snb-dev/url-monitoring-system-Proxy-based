"""The certificate authority URL Monitor uses to read HTTPS page addresses."""

import hashlib
import shutil
import ssl
import subprocess

CA_NAME = "URL Monitor Local CA"
# mitmproxy looks for its CA files under this base name in its confdir.
BASENAME = "mitmproxy"


def ca_cert_file(cert_dir):
    return cert_dir / f"{BASENAME}-ca-cert.pem"


def ensure_ca(cert_dir):
    if not (cert_dir / f"{BASENAME}-ca.pem").exists():
        from mitmproxy.certs import CertStore

        CertStore.create_store(cert_dir, BASENAME, 2048, organization="URL Monitor", cn=CA_NAME)


def thumbprint(cert_dir):
    der = ssl.PEM_cert_to_DER_cert(ca_cert_file(cert_dir).read_text(encoding="ascii"))
    return hashlib.sha1(der).hexdigest()


def is_trusted(cert_dir):
    """Windows only: True if the CA is in the user's trusted root store."""
    result = subprocess.run(
        ["certutil", "-user", "-store", "Root", thumbprint(cert_dir)], capture_output=True
    )
    return result.returncode == 0


def install(cert_dir):
    """Windows only: add the CA to the user's trusted roots. Windows asks to confirm."""
    result = subprocess.run(
        ["certutil", "-user", "-addstore", "Root", str(ca_cert_file(cert_dir))]
    )
    return result.returncode == 0 and is_trusted(cert_dir)


def uninstall(cert_dir):
    """Windows only: remove the CA (by name, so earlier ones go too)."""
    subprocess.run(["certutil", "-user", "-delstore", "Root", CA_NAME])


def delete_files(cert_dir):
    if cert_dir.exists():
        shutil.rmtree(cert_dir)
        return True
    return False
