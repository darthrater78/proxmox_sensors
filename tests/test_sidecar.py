"""Hardware sidecar hardening (audit M1-M4): server, client and Home Assistant side."""

import importlib.util
import socket
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmox_sensors import _track_sidecar_issues, api
from custom_components.proxmox_sensors.api import (
    ProxmoxClient,
    SidecarAuthError,
    SidecarCertificateError,
)
from custom_components.proxmox_sensors.const import DOMAIN
from test_tls_pinning import _self_signed

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pve-sensors-api.py"
TOKEN = "t" * 43
FP_PVE = "11" * 32
FLOW = "custom_components.proxmox_sensors.config_flow"


def _load_sidecar():
    spec = importlib.util.spec_from_file_location("pve_sensors_api", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # importing must not read /etc
    return module


sidecar = _load_sidecar()


# ----- configuration ---------------------------------------------------------

def test_config_secure_mode():
    config = sidecar.parse_config(
        f"ALLOWED_IPS=192.0.2.5, 192.0.2.6\nTOKEN={TOKEN}\n"
        "TLS_CERT=/etc/c.crt\nTLS_KEY=/etc/c.key\n"
    )
    assert config.secure
    assert config.allowed_ips == {"192.0.2.5", "192.0.2.6"}
    assert config.port == 9000


def test_config_legacy_mode_is_ip_only():
    config = sidecar.parse_config("ALLOWED_IPS=192.0.2.5\n")
    assert not config.secure
    assert config.token is None


@pytest.mark.parametrize("text, message", [
    (f"ALLOWED_IPS=192.0.2.5\nTOKEN={TOKEN}\n", "requires TLS_CERT"),
    ("ALLOWED_IPS=192.0.2.5\nTOKEN=short\nTLS_CERT=a\nTLS_KEY=b\n", "at least"),
    ("ALLOWED_IPS=192.0.2.5\nTLS_CERT=a\nTLS_KEY=b\n", "without TOKEN"),
    ("ALLOWED_IPS=\n", "missing or empty"),
    ("ALLOWED_IPS=192.0.2.0/24\n", "Invalid address"),
    ("ALLOWED_IPS=192.0.2.5\nPORT=70000\n", "PORT"),
])
def test_config_rejects_unsafe_or_invalid(text, message):
    with pytest.raises(RuntimeError, match=message):
        sidecar.parse_config(text)


def test_config_with_token_must_not_be_world_readable(tmp_path):
    path = tmp_path / "sidecar.conf"
    path.write_text(f"ALLOWED_IPS=192.0.2.5\nTOKEN={TOKEN}\nTLS_CERT=a\nTLS_KEY=b\n")
    path.chmod(0o644)
    with pytest.raises(RuntimeError, match="chmod 600"):
        sidecar.load_config(str(path))
    path.chmod(0o600)
    assert sidecar.load_config(str(path)).secure


# ----- live server -------------------------------------------------------------

class _Recorder(sidecar.Handler):
    """The real handler, recording which requests passed the IP and token checks."""

    seen: list

    def _handle_health(self):
        self.seen.append(self.path)
        self._send_json_response(b'{"status": "ok"}')


class _QuietSidecar(sidecar.SidecarServer):
    def handle_error(self, request, client_address):
        """Clients that hang up after a refused handshake are expected here."""


@pytest.fixture
def run_sidecar(tmp_path, socket_enabled):
    servers = []

    def start(secure=True, allowed=("127.0.0.1",)):
        cert, key, fingerprint = _self_signed(tmp_path)
        config = sidecar.SidecarConfig(
            allowed, TOKEN if secure else None, str(cert) if secure else None,
            str(key) if secure else None, bind="127.0.0.1", port=0,
        )
        seen = []
        handler = type("H", (_Recorder,), {"seen": seen})
        server = _QuietSidecar(config, handler, sidecar.build_ssl_context(config))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server, fingerprint, seen

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _client(port_server, token=TOKEN, fingerprint=None):
    return ProxmoxClient(
        host="127.0.0.1", user="root@pam", token_id="ha", token_secret="x",
        sidecar_token=token, sidecar_fingerprint=fingerprint,
    )


@pytest.fixture
def sidecar_port(monkeypatch):
    def use(server):
        monkeypatch.setattr(api, "SIDECAR_PORT", server.server_address[1])
    return use


def test_secure_sidecar_accepts_pinned_client_with_token(run_sidecar, sidecar_port):
    server, fingerprint, seen = run_sidecar()
    sidecar_port(server)
    client = _client(server, fingerprint=fingerprint)
    assert client._sidecar_fetch("/health", 5) == {"status": "ok"}
    assert client.sidecar_problem is None
    assert seen == ["/health"]


def test_secure_sidecar_rejects_missing_or_wrong_token(run_sidecar):
    server, _fingerprint, seen = run_sidecar()
    url = f"https://127.0.0.1:{server.server_address[1]}/health"
    assert requests.get(url, verify=False, timeout=5).status_code == 401
    wrong = requests.get(url, verify=False, timeout=5,
                         headers={"Authorization": "Bearer " + "x" * 43})
    assert wrong.status_code == 401
    assert seen == []  # no handler ran for an unauthenticated request


def test_client_reports_a_rejected_token(run_sidecar, sidecar_port):
    server, fingerprint, _seen = run_sidecar()
    sidecar_port(server)
    client = _client(server, token="y" * 43, fingerprint=fingerprint)
    with pytest.raises(SidecarAuthError):
        client._sidecar_fetch("/health", 5)
    assert client.sidecar_problem == "auth_failed"


def test_client_sends_nothing_to_a_different_certificate(run_sidecar, sidecar_port):
    server, _fingerprint, seen = run_sidecar()
    sidecar_port(server)
    client = _client(server, fingerprint="00" * 32)
    with pytest.raises(SidecarCertificateError):
        client._sidecar_fetch("/health", 5)
    assert client.sidecar_problem == "certificate_changed"
    assert seen == []


def test_sidecar_drops_clients_outside_the_allow_list(run_sidecar):
    server, _fingerprint, seen = run_sidecar(allowed=("192.0.2.99",))
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(f"https://127.0.0.1:{server.server_address[1]}/health",
                     verify=False, timeout=5, headers={"Authorization": f"Bearer {TOKEN}"})
    assert seen == []


def test_sidecar_refuses_connections_beyond_the_thread_cap(run_sidecar):
    server, _fingerprint, seen = run_sidecar()
    server._slots = threading.BoundedSemaphore(1)
    server._slots.acquire()  # every slot busy
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(f"https://127.0.0.1:{server.server_address[1]}/health",
                     verify=False, timeout=5, headers={"Authorization": f"Bearer {TOKEN}"})
    assert seen == []


def test_stalled_client_does_not_block_others(run_sidecar, sidecar_port, monkeypatch):
    monkeypatch.setattr(sidecar, "REQUEST_TIMEOUT", 1)
    server, fingerprint, seen = run_sidecar()
    sidecar_port(server)
    staller = socket.create_connection(("127.0.0.1", server.server_address[1]))
    try:  # connected, never sends a TLS ClientHello
        assert _client(server, fingerprint=fingerprint)._sidecar_fetch("/health", 5)
    finally:
        staller.close()
    assert seen == ["/health"]


def test_legacy_sidecar_is_flagged_insecure(run_sidecar, sidecar_port):
    server, _fingerprint, seen = run_sidecar(secure=False)
    sidecar_port(server)
    client = _client(server, token=None)
    assert client._sidecar_fetch("/health", 5) == {"status": "ok"}
    assert client.sidecar_problem == "insecure"


# ----- repair issues -------------------------------------------------------------

async def test_repair_issue_follows_the_sidecar_state(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10"}, title="pve1")
    entry.add_to_hass(hass)
    client = MagicMock(sidecar_problem="insecure")
    listeners = []
    coordinator = MagicMock()
    coordinator.async_add_listener = lambda cb: listeners.append(cb) or (lambda: None)
    registry = ir.async_get(hass)

    _track_sidecar_issues(hass, entry, client, coordinator)
    issue = registry.async_get_issue(DOMAIN, f"sidecar_insecure_{entry.entry_id}")
    assert issue.severity is ir.IssueSeverity.WARNING

    client.sidecar_problem = "certificate_changed"
    listeners[0]()
    assert registry.async_get_issue(DOMAIN, f"sidecar_insecure_{entry.entry_id}") is None
    assert registry.async_get_issue(DOMAIN, f"sidecar_certificate_changed_{entry.entry_id}")

    client.sidecar_problem = None
    listeners[0]()
    assert not [i for i in registry.issues.values() if i.domain == DOMAIN]


# ----- reconfigure ----------------------------------------------------------------

VALID = {"has_minimum": True, "has_all": True}
SIDECAR_FP = "ab" * 32
BASE_INPUT = {"host": "192.0.2.10", "user": "root@pam", "use_token": False, "verify_ssl": False}


def _pve_entry(hass, **extra):
    entry = MockConfigEntry(domain=DOMAIN, version=3, unique_id="pve:192.0.2.10:pve1", data={
        "platform_type": "PVE", "host": "192.0.2.10", "node": "pve1", "user": "root@pam",
        "password": "pw", "verify_ssl": False, "cert_fingerprint": FP_PVE, "server_id": "pve1",
        **extra,
    })
    entry.add_to_hass(hass)
    return entry


async def _reconfigure(hass, entry, check, **fields):
    with patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", AsyncMock(return_value=VALID)), \
         patch(f"{FLOW}.ProxmoxClient.get", AsyncMock(return_value=[{"node": "pve1"}])), \
         patch(f"{FLOW}.ProxmoxClient.check_sidecar", check), \
         patch("custom_components.proxmox_sensors.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**BASE_INPUT, **fields}
        )
        await hass.async_block_till_done()
    return result


async def test_reconfigure_saves_checked_sidecar_settings(hass):
    entry = _pve_entry(hass)
    check = AsyncMock(return_value={"status": "ok"})
    display = ":".join(["AB"] * 32)
    result = await _reconfigure(hass, entry, check,
                                sidecar_token=TOKEN, sidecar_fingerprint=f"sha256 Fingerprint={display}")
    assert result["reason"] == "reconfigure_successful"
    check.assert_awaited_once()
    assert entry.data["sidecar_token"] == TOKEN
    assert entry.data["sidecar_fingerprint"] == SIDECAR_FP


@pytest.mark.parametrize("fields, error", [
    ({"sidecar_token": TOKEN}, "sidecar_fingerprint_required"),
    ({"sidecar_fingerprint": SIDECAR_FP}, "sidecar_token_required"),
    ({"sidecar_token": TOKEN, "sidecar_fingerprint": "not-a-fingerprint"},
     "invalid_sidecar_fingerprint"),
])
async def test_reconfigure_sidecar_field_errors(hass, fields, error):
    entry = _pve_entry(hass)
    check = AsyncMock()
    result = await _reconfigure(hass, entry, check, **fields)
    assert result["errors"] == {"base": error}
    check.assert_not_awaited()


@pytest.mark.parametrize("raised, error", [
    (SidecarCertificateError("x"), "sidecar_certificate_changed"),
    (SidecarAuthError("x"), "sidecar_auth_failed"),
    (requests.exceptions.ConnectionError("x"), "sidecar_cannot_connect"),
])
async def test_reconfigure_reports_sidecar_check_failures(hass, raised, error):
    entry = _pve_entry(hass)
    result = await _reconfigure(hass, entry, AsyncMock(side_effect=raised),
                                sidecar_token=TOKEN, sidecar_fingerprint=SIDECAR_FP)
    assert result["errors"] == {"base": error}
    assert "sidecar_token" not in entry.data


async def test_reconfigure_keeps_token_and_skips_check_when_unchanged(hass):
    entry = _pve_entry(hass, sidecar_token=TOKEN, sidecar_fingerprint=SIDECAR_FP)
    check = AsyncMock()
    result = await _reconfigure(hass, entry, check, sidecar_fingerprint=SIDECAR_FP)
    assert result["reason"] == "reconfigure_successful"
    check.assert_not_awaited()
    assert entry.data["sidecar_token"] == TOKEN


async def test_reconfigure_empty_fingerprint_returns_to_legacy(hass):
    entry = _pve_entry(hass, sidecar_token=TOKEN, sidecar_fingerprint=SIDECAR_FP)
    result = await _reconfigure(hass, entry, AsyncMock(), sidecar_fingerprint="")
    assert result["reason"] == "reconfigure_successful"
    assert "sidecar_token" not in entry.data
    assert "sidecar_fingerprint" not in entry.data
