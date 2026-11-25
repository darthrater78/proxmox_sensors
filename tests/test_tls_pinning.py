"""Certificate pinning against a real local HTTPS server (audit H2)."""

import datetime
import hashlib
import ipaddress
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.proxmox_sensors.api import CertificateMismatchError, ProxmoxClient
from custom_components.proxmox_sensors.tls import (
    CertificateNotPinned,
    display_fingerprint,
    fetch_certificate_fingerprint,
    is_fingerprint_mismatch,
    normalize_fingerprint,
    pin_session,
)

WRONG = "00" * 32


def _self_signed(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pve-test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path, key_path, fingerprint


class _FakeProxmox(BaseHTTPRequestHandler):
    seen: list

    def _reply(self, payload):
        body = json.dumps({"data": payload}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.seen.append(("POST", self.path, self.rfile.read(length).decode()))
        self._reply({"ticket": "PVE:test-ticket", "CSRFPreventionToken": "csrf"})

    def do_GET(self):  # noqa: N802
        self.seen.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.endswith("/admin/datastore"):
            self._reply([{"store": "store1"}])
        else:
            self._reply([{"node": "pve1"}])

    def log_message(self, *args):
        pass


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """A pinned client hangs up after a mismatch; that is the expected path."""


@pytest.fixture
def server(tmp_path, socket_enabled):
    """A self-signed HTTPS server on 127.0.0.1 that records every request."""
    cert_path, key_path, fingerprint = _self_signed(tmp_path)
    seen = []
    handler = type("Handler", (_FakeProxmox,), {"seen": seen})
    httpd = _QuietServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"port": httpd.server_address[1], "fingerprint": fingerprint, "seen": seen}
    httpd.shutdown()
    httpd.server_close()


def _client(server, fingerprint, **kwargs):
    defaults = {"user": "root@pam", "password": "secret-password"}
    defaults.update(kwargs)
    return ProxmoxClient(
        host="127.0.0.1", port=server["port"], verify_ssl=False,
        cert_fingerprint=fingerprint, **defaults,
    )


def test_fingerprint_helpers():
    fp = "AB" * 32
    assert normalize_fingerprint(display_fingerprint(fp)) == fp.lower()
    assert display_fingerprint(fp).count(":") == 31
    assert normalize_fingerprint("not a fingerprint") is None


def test_fetch_certificate_fingerprint(server):
    assert fetch_certificate_fingerprint("127.0.0.1", server["port"]) == server["fingerprint"]


def test_pinned_session_accepts_only_the_pinned_certificate(server):
    url = f"https://127.0.0.1:{server['port']}/api2/json/nodes"
    with pin_session(requests.Session(), server["fingerprint"]) as session:
        assert session.get(url, timeout=5).json() == {"data": [{"node": "pve1"}]}
    with pin_session(requests.Session(), WRONG) as session:
        with pytest.raises(requests.exceptions.SSLError) as excinfo:
            session.get(url, timeout=5)
    assert is_fingerprint_mismatch(excinfo.value)


async def test_password_login_goes_through_the_pin(hass, server):
    client = _client(server, server["fingerprint"])
    assert await client.get(hass, "nodes") == [{"node": "pve1"}]
    methods = [(method, path) for method, path, _ in server["seen"]]
    assert ("POST", "/api2/json/access/ticket") in methods
    assert client.certificate_mismatch is False


async def test_wrong_certificate_never_receives_the_password(hass, server):
    client = _client(server, WRONG)
    assert await client.get(hass, "nodes") is None
    assert client.certificate_mismatch is True
    with pytest.raises(CertificateMismatchError):
        await client.get(hass, "nodes", raise_errors=True)
    assert server["seen"] == []  # no request, so no credential, reached the server


async def test_token_auth_is_pinned(hass, server):
    good = _client(server, server["fingerprint"], password=None, token_id="ha", token_secret="tok")
    assert await good.get(hass, "nodes") == [{"node": "pve1"}]
    server["seen"].clear()
    bad = _client(server, WRONG, password=None, token_id="ha", token_secret="tok")
    assert await bad.get(hass, "nodes") is None
    assert bad.certificate_mismatch is True
    assert server["seen"] == []


async def test_pbs_requests_are_pinned(hass, server):
    good = _client(server, server["fingerprint"], password=None, token_id="ha",
                   token_secret="tok", server_type="PBS")
    assert await good.pbs_get(hass, "admin/datastore") == [{"store": "store1"}]
    server["seen"].clear()
    bad = _client(server, WRONG, password=None, token_id="ha", token_secret="tok",
                  server_type="PBS")
    with pytest.raises(CertificateMismatchError):
        await bad.pbs_get(hass, "admin/datastore", raise_errors=True)
    assert server["seen"] == []


async def test_verification_off_without_a_pin_refuses_to_connect(hass, server):
    client = _client(server, None)
    with pytest.raises(CertificateNotPinned):
        await client.get(hass, "nodes", raise_errors=True)
    pbs = _client(server, None, password=None, token_id="ha", token_secret="tok",
                  server_type="PBS")
    with pytest.raises(CertificateNotPinned):
        await pbs.pbs_get(hass, "admin/datastore", raise_errors=True)
    assert server["seen"] == []
