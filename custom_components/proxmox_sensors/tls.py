"""Certificate pinning for Proxmox servers with self-signed certificates.

When certificate verification is off (the usual case for Proxmox's own
self-signed certificates), the integration pins the server certificate's
SHA-256 fingerprint instead of trusting any certificate. The fingerprint is
confirmed by the user during setup, before any credential is sent, and every
later request is refused unless the server presents that exact certificate.
"""

from __future__ import annotations

import hashlib
import re
import socket
import ssl

import requests
from requests.adapters import HTTPAdapter

DEFAULT_PORTS = {"PVE": 8006, "CLUSTER": 8006, "PBS": 8007, "PDM": 8443}

_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_MISMATCH_TEXT = "Fingerprints did not match"


class CertificateNotPinned(Exception):
    """Verification is off and no fingerprint was confirmed: refuse to connect."""


def normalize_fingerprint(value) -> str | None:
    """Return a SHA-256 fingerprint as 64 lowercase hex digits, or None."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().replace(":", "")
    return candidate if _FINGERPRINT.fullmatch(candidate) else None


def display_fingerprint(value: str) -> str:
    """Format a fingerprint the way the Proxmox web UI shows it (AA:BB:...)."""
    normalized = normalize_fingerprint(value) or ""
    return ":".join(normalized[i:i + 2] for i in range(0, len(normalized), 2)).upper()


def _socket_host(host: str) -> str:
    return host[1:-1] if host.startswith("[") and host.endswith("]") else host


def fetch_certificate_fingerprint(host: str, port: int, timeout: float = 10) -> str:
    """Connect once and return the SHA-256 fingerprint of the server certificate.

    Blocking: run it in an executor. The certificate is deliberately not
    verified here; the fingerprint is what the user confirms instead.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((_socket_host(host), port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=_socket_host(host)) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("Server presented no certificate")
    return hashlib.sha256(der).hexdigest()


class PinnedAdapter(HTTPAdapter):
    """HTTPS adapter that accepts only a certificate with one SHA-256 fingerprint."""

    def __init__(self, fingerprint: str, **kwargs):
        normalized = normalize_fingerprint(fingerprint)
        if normalized is None:
            raise ValueError("Invalid SHA-256 certificate fingerprint")
        self._fingerprint = normalized
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["assert_fingerprint"] = self._fingerprint
        kwargs["ssl_minimum_version"] = ssl.TLSVersion.TLSv1_2
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["assert_fingerprint"] = self._fingerprint
        kwargs["ssl_minimum_version"] = ssl.TLSVersion.TLSv1_2
        return super().proxy_manager_for(*args, **kwargs)


def pin_session(session: requests.Session, fingerprint: str) -> requests.Session:
    """Route every HTTPS request of ``session`` through the pinned adapter.

    Chain verification is turned off because the pin replaces it: urllib3
    compares the presented certificate with the fingerprint after the
    handshake and before any request bytes, credentials included, are sent.
    """
    session.mount("https://", PinnedAdapter(fingerprint))
    session.verify = False
    return session


def is_fingerprint_mismatch(err: BaseException | None) -> bool:
    """True if ``err`` (or anything it wraps) is a pinned-certificate mismatch."""
    seen = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        if _MISMATCH_TEXT in str(err):
            return True
        nested = [arg for arg in getattr(err, "args", ()) if isinstance(arg, BaseException)]
        reason = getattr(err, "reason", None)
        if isinstance(reason, BaseException):
            nested.append(reason)
        if any(is_fingerprint_mismatch(arg) for arg in nested):
            return True
        err = err.__cause__ or err.__context__
    return False
